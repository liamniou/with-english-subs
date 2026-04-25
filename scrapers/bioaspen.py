#!/usr/bin/env python3
"""
Bio Aspen scraper.

The listing page at https://www.bioaspen.se/visningar/filmer/ already
contains every upcoming screening grouped under Swedish weekday headings
("fredag, 24 april", ...). Each screening block links to the film's detail
page and exposes the audio and subtitle languages as ``TAL XX`` and
``TEXT XX`` badges. We keep only screenings labelled ``TEXT EN``.
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import date, datetime, timezone
from typing import Any

import httpx
from selectolax.parser import HTMLParser


BASE = "https://www.bioaspen.se"
LISTING_URL = f"{BASE}/visningar/filmer/"
CINEMA_NAME = "Bio Aspen"
SOURCE_KEY = "bioaspen"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)

SV_MONTHS = {
    "januari": 1, "februari": 2, "mars": 3, "april": 4, "maj": 5, "juni": 6,
    "juli": 7, "augusti": 8, "september": 9, "oktober": 10,
    "november": 11, "december": 12,
}

RE_DATE = re.compile(r"\w+,\s+(\d{1,2})\s+([a-zåäö]+)", re.IGNORECASE)


class BioAspen:
    def __init__(self) -> None:
        self.client = httpx.Client(
            timeout=20.0,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )
        self.films_with_english_subs: list[dict[str, Any]] = []

    # -- listing parsing ------------------------------------------------------

    def fetch_listing(self) -> str:
        resp = self.client.get(LISTING_URL)
        resp.raise_for_status()
        return resp.text

    @staticmethod
    def _parse_date(label: str, today: date) -> date | None:
        m = RE_DATE.search(label)
        if not m:
            return None
        day = int(m.group(1))
        month = SV_MONTHS.get(m.group(2).lower())
        if not month:
            return None
        year = today.year
        candidate = date(year, month, day)
        if candidate < today:
            candidate = date(year + 1, month, day)
        return candidate

    def parse_showtimes(self, html: str, today: date) -> list[dict[str, Any]]:
        """Walk the listing in document order, attaching the most recent
        date heading to every screening block."""
        tree = HTMLParser(html)
        rows: list[dict[str, Any]] = []
        current_date: date | None = None

        # Single recursive preorder walk so date headings and screening blocks
        # are encountered in document order.
        def walk(node):
            nonlocal current_date
            tag = node.tag
            classes = node.attributes.get("class", "") or "" if node.attributes else ""
            if tag == "h2" and "font-display" in classes and "font-normal" in classes:
                d = self._parse_date(node.text(strip=True), today)
                if d:
                    current_date = d
                return  # date heading has no nested screening blocks
            if tag == "div" and "my-3" in classes.split() and current_date:
                row = self._parse_block(node, current_date)
                if row:
                    rows.append(row)
                return
            for child in node.iter():
                walk(child)

        walk(tree.body or tree.root)
        return rows

    def _parse_block(self, block, current_date: date) -> dict[str, Any] | None:
        link = block.css_first("a[href*='/movies/']")
        if not link:
            return None
        url = link.attributes.get("href", "") or ""
        time_h2 = link.css_first("h2")
        title_h3 = link.css_first("h3")
        time_text = (time_h2.text(strip=True) if time_h2 else "").strip()
        title = (title_h3.text(strip=True) if title_h3 else "").strip()
        time_match = re.match(r"(\d{1,2}:\d{2})", time_text)
        if not time_match or not title:
            return None
        hhmm = time_match.group(1)

        audio = subtitle = hall = duration = age = ""
        for span in link.css("span.font-menu"):
            t = (span.text(strip=True) or "").strip()
            if t.startswith("TAL "):
                audio = t[4:].strip()
            elif t.startswith("TEXT "):
                subtitle = t[5:].strip()
            elif "Salong" in t or t in {"Lusoperan", "Tellus"}:
                hall = t
            elif "tim" in t or t.endswith("min"):
                duration = t
            elif t.startswith("Från"):
                age = t

        if subtitle != "EN":
            return None

        slug = url.rstrip("/").rsplit("/", 1)[-1]
        iso_dt = datetime.combine(
            current_date,
            datetime.strptime(hhmm, "%H:%M").time(),
        )
        return {
            "slug": slug,
            "url": url,
            "title": title,
            "datetime": iso_dt,
            "hall": hall,
            "audio": audio,
            "duration": duration,
            "age": age,
        }

    # -- film detail enrichment ----------------------------------------------

    def fetch_film_details(self, url: str) -> dict[str, str]:
        try:
            resp = self.client.get(url)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            print(f"   ⚠️  could not fetch {url}: {exc}")
            return {}
        tree = HTMLParser(resp.text)

        poster = ""
        # Poster comes from biljetter.bioaspen.se/media/posters
        for img in tree.css("img"):
            src = img.attributes.get("src", "") or ""
            if "biljetter.bioaspen.se" in src and "/posters/" in src:
                poster = src
                break

        # Description: the WordPress content is inside the main article. Pick
        # the longest <p> text on the page that isn't bistro/info boilerplate.
        description = ""
        for p in tree.css("p"):
            t = (p.text(strip=True) or "").strip()
            if not t or len(t) < 60:
                continue
            low = t.lower()
            if "bistro" in low or "fullständiga rättigheter" in low or "filmstart" in low:
                continue
            if len(t) > len(description):
                description = t

        director = ""
        # The detail page exposes structured metadata as
        # <h3>Regissör</h3><span>Name</span> pairs.
        m = re.search(
            r"<h3[^>]*>\s*Regiss[öo]r\s*</h3>\s*<span[^>]*>([^<]+)</span>",
            resp.text,
        )
        if m:
            director = m.group(1).strip()

        return {
            "poster_url": poster,
            "description": description,
            "director": director,
        }

    # -- aggregation ----------------------------------------------------------

    @staticmethod
    def _normalize_showtime(row: dict[str, Any]) -> dict[str, Any]:
        dt: datetime = row["datetime"]
        iso = dt.strftime("%Y-%m-%dT%H:%M:%S")
        return {
            "datetime": iso,
            "display_text": dt.strftime("%A %-d %B %Y at %H:%M"),
            "time": dt.strftime("%H:%M"),
            "date_section": dt.strftime("%d.%m"),
            "ticket_url": row["url"],
            "hall": row["hall"],
            "audio_language": row["audio"],
            "subtitle_language": "EN",
            "normalized_datetime": iso,
            "normalized_date": dt.strftime("%d.%m"),
            "normalized_time": dt.strftime("%H:%M"),
        }

    def aggregate(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_slug: dict[str, dict[str, Any]] = {}
        for row in rows:
            entry = by_slug.get(row["slug"])
            if entry is None:
                entry = {
                    "film_id": row["slug"],
                    "url": row["url"],
                    "title": row["title"],
                    "director": "",
                    "duration": row["duration"],
                    "language": row["audio"],
                    "description": "",
                    "poster_url": "",
                    "showtimes": [],
                    "cinemas": [CINEMA_NAME],
                    "scraped_at": datetime.now(timezone.utc).isoformat(),
                    "source": SOURCE_KEY,
                }
                by_slug[row["slug"]] = entry
            entry["showtimes"].append(self._normalize_showtime(row))
        for entry in by_slug.values():
            entry["showtimes"].sort(key=lambda s: s["normalized_datetime"])
        return list(by_slug.values())

    # -- entry point ----------------------------------------------------------

    def scrape_films(self) -> list[dict[str, Any]]:
        print("🎬 Bio Aspen scraper starting...")
        today = date.today()
        html = self.fetch_listing()
        rows = self.parse_showtimes(html, today)
        print(f"📋 Found {len(rows)} screenings with TEXT EN")

        films = self.aggregate(rows)
        print(f"   {len(films)} unique films")

        for film in films:
            print(f"🔍 Fetching details for '{film['title']}'...")
            details = self.fetch_film_details(film["url"])
            if details.get("poster_url"):
                film["poster_url"] = details["poster_url"]
            if details.get("description"):
                film["description"] = details["description"]
            if details.get("director"):
                film["director"] = details["director"]
            time.sleep(0.2)

        self.films_with_english_subs = films
        self.save_results()
        return films

    def save_results(self) -> None:
        os.makedirs("data", exist_ok=True)
        output_file = f"./data/{SOURCE_KEY}_films_with_english_subs.json"
        with open(output_file, "w", encoding="utf-8") as fh:
            json.dump(self.films_with_english_subs, fh, ensure_ascii=False, indent=2)
        total = sum(len(f["showtimes"]) for f in self.films_with_english_subs)
        print("\n📊 SCRAPING COMPLETE!")
        print(f"✅ {len(self.films_with_english_subs)} films with English subtitles")
        print(f"💾 Results saved to: {output_file}")
        print(f"📈 Total showtimes: {total}")


if __name__ == "__main__":
    BioAspen().scrape_films()
