#!/usr/bin/env python3
"""
Capitolbio (Bio & Bistro Capitol) scraper.

Strategy
--------
The listing page at https://www.capitolbio.se/filmer is a Next.js App Router
page. Each scroll fires a Server Action that POSTs back to ``/filmer`` with a
``next-action`` header and an integer page index in the body, returning the
next day's screenings as an RSC stream.

We:
  1. GET ``/filmer`` once (page 1 = today, tomorrow, day after).
  2. Locate the page-chunk JS file and pull the Server Action ID out of it.
  3. POST page 2, 3, ... until no new ``/boka/`` rows appear.
  4. Parse each chunk's payload, group rows by film, keep only those with
     ``EN text`` (English subtitles), and write the standard JSON shape.
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx


BASE = "https://www.capitolbio.se"
LISTING_URL = f"{BASE}/filmer"
CINEMA_NAME = "Capitol"
SOURCE_KEY = "capitolbio"

# When the page first loads it shows "today + tomorrow + day after". Each
# subsequent scroll loads one more day. We cap at 60 to avoid a runaway loop.
MAX_PAGES = 60

ROUTER_STATE_TREE = (
    "%5B%22%22%2C%7B%22children%22%3A%5B%22(frontend)%22%2C%7B%22children%22%3A"
    "%5B%22(site)%22%2C%7B%22children%22%3A%5B%22filmer%22%2C%7B%22children%22"
    "%3A%5B%22__PAGE__%22%2C%7B%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2C"
    "null%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D%7D%2Cnull%2Cnull%5D"
)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)

# Swedish month abbreviations as used in date headings ("Sön 26 apr").
SV_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "maj": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "okt": 10, "nov": 11, "dec": 12,
}

# Patterns inside the RSC payload.
RE_NEXT_F = re.compile(r'self\.__next_f\.push\(\[1,(".*?")\]\)', re.DOTALL)
RE_DATE_HEADING = re.compile(
    r'"(Idag|Imorgon|(?:Mån|Tis|Ons|Tor|Fre|Lör|Sön) \d{1,2} (?:jan|feb|mar|apr|maj|jun|jul|aug|sep|okt|nov|dec))"'
)
RE_BOKA = re.compile(r'"href":"/boka/(\d+)"[^\n]*?"children":\["([^"\\]+)"')
RE_TIME = re.compile(r'\((\d{1,2}:\d{2})\)')
RE_HALL = re.compile(r'"sr-only","children":"Salong "\}\],\["\$","span",null,\{"className":"[^"]*","children":(\d+)\}')
RE_LANG = re.compile(r'\["([A-Z]{2})"," tal"," \| ([A-Z]{2}) text"\]')
RE_FILMER = re.compile(r'"href":"/filmer/([^"/]+)/(\d+)"')
RE_PAGE_CHUNK = re.compile(
    r'/_next/static/chunks/app/\(frontend\)/\(site\)/filmer/page-[a-f0-9]+\.js'
)
RE_ACTION_ID = re.compile(r'"([a-f0-9]{40})"')


class Capitolbio:
    def __init__(self) -> None:
        self.client = httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )
        self.films_with_english_subs: list[dict[str, Any]] = []

    # -- HTML / RSC fetching --------------------------------------------------

    def fetch_initial(self) -> tuple[str, list[str]]:
        """Return (combined RSC text from initial GET, candidate action ids)."""
        resp = self.client.get(LISTING_URL)
        resp.raise_for_status()
        html = resp.text
        combined = self._decode_next_f(html)

        chunk_match = RE_PAGE_CHUNK.search(html)
        action_ids: list[str] = []
        if chunk_match:
            chunk_url = BASE + chunk_match.group(0)
            try:
                chunk_resp = self.client.get(chunk_url)
                chunk_resp.raise_for_status()
                action_ids = list(dict.fromkeys(RE_ACTION_ID.findall(chunk_resp.text)))
            except httpx.HTTPError as exc:
                print(f"   ⚠️  could not fetch page chunk: {exc}")
        return combined, action_ids

    def fetch_page(self, page: int, action_id: str) -> str:
        """POST a Server Action call for the given page index; return body."""
        resp = self.client.post(
            LISTING_URL,
            content=json.dumps([
                page,
                "$undefined", "$undefined", "$undefined", "$undefined",
                "$undefined", "$undefined", "$undefined",
            ]),
            headers={
                "next-action": action_id,
                "next-router-state-tree": ROUTER_STATE_TREE,
                "content-type": "text/plain;charset=UTF-8",
                "accept": "text/x-component",
                "referer": LISTING_URL,
            },
        )
        resp.raise_for_status()
        return resp.text

    @staticmethod
    def _decode_next_f(html: str) -> str:
        """Concatenate every ``self.__next_f.push([1, "..."])`` payload."""
        out: list[str] = []
        for raw in RE_NEXT_F.findall(html):
            try:
                out.append(json.loads(raw))
            except json.JSONDecodeError:
                pass
        return "".join(out)

    # -- date heading parsing -------------------------------------------------

    @staticmethod
    def _parse_date_heading(label: str, today: date) -> date | None:
        if label == "Idag":
            return today
        if label == "Imorgon":
            return today + timedelta(days=1)
        m = re.match(r"\S+ (\d{1,2}) ([a-zåäö]{3})", label)
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

    # -- showtime extraction --------------------------------------------------

    def extract_showtimes(self, payload: str, today: date) -> list[dict[str, Any]]:
        """Find each /boka/<id> block, attach the nearest preceding date.

        The RSC payload is mostly a flat string. We walk through it once,
        recording date headings as we go, and emit a row for every booking
        link that carries an ``EN text`` language tag.
        """
        # Build a sorted list of (position, date) for date headings.
        date_marks: list[tuple[int, date]] = []
        for m in RE_DATE_HEADING.finditer(payload):
            d = self._parse_date_heading(m.group(1), today)
            if d:
                date_marks.append((m.start(), d))

        rows: list[dict[str, Any]] = []
        for m in RE_BOKA.finditer(payload):
            pos = m.start()
            booking_id = m.group(1)
            title = m.group(2).strip()

            # Window from this booking link to the next booking link or +4000 chars.
            end = min(len(payload), pos + 4000)
            window = payload[pos:end]

            lang = RE_LANG.search(window)
            if not lang or lang.group(2) != "EN":
                continue  # skip Swedish-subtitled showings

            time_m = RE_TIME.search(window)
            if not time_m:
                continue
            hhmm = time_m.group(1)

            hall_m = RE_HALL.search(window)
            hall = f"Salong {hall_m.group(1)}" if hall_m else ""

            film_m = RE_FILMER.search(window)
            if not film_m:
                continue
            slug, film_id = film_m.group(1), film_m.group(2)

            # Find the most recent date heading at or before pos.
            d = None
            for mark_pos, mark_date in date_marks:
                if mark_pos <= pos:
                    d = mark_date
                else:
                    break
            if not d:
                continue

            iso_dt = datetime.combine(d, datetime.strptime(hhmm, "%H:%M").time())
            rows.append({
                "booking_id": booking_id,
                "title": title,
                "slug": slug,
                "film_id": film_id,
                "hall": hall,
                "audio": lang.group(1),
                "datetime": iso_dt,
            })
        return rows

    # -- film detail enrichment ----------------------------------------------

    def fetch_film_details(self, slug: str, film_id: str) -> dict[str, str]:
        url = f"{BASE}/filmer/{slug}/{film_id}"
        try:
            resp = self.client.get(url)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            print(f"   ⚠️  could not fetch {url}: {exc}")
            return {"url": url}
        combined = self._decode_next_f(resp.text)

        poster = ""
        m = re.search(r'(https://capitol\.mycloudcinema\.com/media/stills/\d+/1920/[a-f0-9-]+\.jpg)', combined)
        if m:
            poster = m.group(1)

        director = ""
        m = re.search(r'"Regiss[öo]r"[^"]*"children":"([^"]+)"', combined)
        if m:
            director = m.group(1)

        duration = ""
        m = re.search(r'(\d+)\s*min', combined)
        if m:
            duration = f"{m.group(1)} min"

        description = ""
        # Synopses on capitolbio.se are HTML fragments starting with <p>.
        # Pick the longest such fragment and clean it up.
        candidates = re.findall(r'((?:<p[^>]*>.*?</p>\s*)+)', combined)
        if candidates:
            best = max(candidates, key=len)
            # Decode HTML entities and strip tags for a plain-text synopsis.
            import html as _html
            text = _html.unescape(best)
            text = re.sub(r'<br\s*/?>', '\n', text)
            text = re.sub(r'</p>\s*<p[^>]*>', '\n\n', text)
            text = re.sub(r'<[^>]+>', '', text)
            description = text.strip()

        return {
            "url": url,
            "poster_url": poster,
            "director": director,
            "duration": duration,
            "description": description,
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
            "ticket_url": f"{BASE}/boka/{row['booking_id']}",
            "booking_id": row["booking_id"],
            "hall": row["hall"],
            "audio_language": row["audio"],
            "subtitle_language": "EN",
            "normalized_datetime": iso,
            "normalized_date": dt.strftime("%d.%m"),
            "normalized_time": dt.strftime("%H:%M"),
        }

    def aggregate(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_film: dict[str, dict[str, Any]] = {}
        seen_bookings: set[str] = set()
        for row in rows:
            if row["booking_id"] in seen_bookings:
                continue
            seen_bookings.add(row["booking_id"])
            film_id = row["film_id"]
            entry = by_film.get(film_id)
            if entry is None:
                entry = {
                    "film_id": row["slug"],
                    "url": f"{BASE}/filmer/{row['slug']}/{film_id}",
                    "title": row["title"],
                    "director": "",
                    "duration": "",
                    "language": "",
                    "description": "",
                    "poster_url": "",
                    "showtimes": [],
                    "cinemas": [CINEMA_NAME],
                    "scraped_at": datetime.now(timezone.utc).isoformat(),
                    "source": SOURCE_KEY,
                    "_capitol_film_id": film_id,
                }
                by_film[film_id] = entry
            entry["showtimes"].append(self._normalize_showtime(row))

        for entry in by_film.values():
            entry["showtimes"].sort(key=lambda s: s["normalized_datetime"])

        return list(by_film.values())

    # -- entry point ----------------------------------------------------------

    def scrape_films(self) -> list[dict[str, Any]]:
        print("🎬 Capitolbio scraper starting...")
        today = date.today()

        combined, action_ids = self.fetch_initial()
        print(f"📡 Initial GET: {len(combined)} chars; action ids found: {len(action_ids)}")
        all_rows = self.extract_showtimes(combined, today)
        print(f"   Initial page yielded {len(all_rows)} EN-text rows")

        if not action_ids:
            print("⚠️  no Server Action ID found; falling back to initial page only")
        else:
            # Try each candidate action id by POSTing page 2; keep whichever
            # returns the largest response (the pagination action) — the page
            # has multiple Server Actions and only one is the "load more" one.
            seen_bookings = {r["booking_id"] for r in all_rows}
            best: tuple[int, str, str] | None = None  # (size, id, body)
            for candidate in action_ids:
                try:
                    body = self.fetch_page(2, candidate)
                except httpx.HTTPError as exc:
                    print(f"   ⚠️  page 2 with {candidate[:8]} failed: {exc}")
                    continue
                if "/boka/" not in body:
                    continue
                if best is None or len(body) > best[0]:
                    best = (len(body), candidate, body)

            working_id = None
            if best is not None:
                working_id = best[1]
                body = best[2]
                print(f"✅ Server Action id: {working_id} (page 2 = {best[0]} bytes)")
                new_rows = self.extract_showtimes(body, today)
                new = [r for r in new_rows if r["booking_id"] not in seen_bookings]
                seen_bookings.update(r["booking_id"] for r in new)
                all_rows.extend(new)
                print(f"   page 2: +{len(new)} new rows")

            if working_id:
                empty_streak = 0
                for page in range(3, MAX_PAGES + 1):
                    try:
                        body = self.fetch_page(page, working_id)
                    except httpx.HTTPError as exc:
                        print(f"   ⚠️  page {page} failed: {exc}")
                        break
                    new_rows = self.extract_showtimes(body, today)
                    new = [r for r in new_rows if r["booking_id"] not in seen_bookings]
                    seen_bookings.update(r["booking_id"] for r in new)
                    all_rows.extend(new)
                    if not new:
                        empty_streak += 1
                        print(f"   page {page}: no new rows (streak {empty_streak})")
                        if empty_streak >= 3:
                            break
                    else:
                        empty_streak = 0
                        print(f"   page {page}: +{len(new)} new rows")
                    time.sleep(0.15)

        films = self.aggregate(all_rows)
        print(f"📋 {len(films)} unique films, {sum(len(f['showtimes']) for f in films)} showtimes")

        for film in films:
            film_id = film.pop("_capitol_film_id", "")
            print(f"🔍 Fetching details for '{film['title']}'...")
            details = self.fetch_film_details(film["film_id"], film_id)
            film["url"] = details.get("url", film["url"])
            if details.get("poster_url"):
                film["poster_url"] = details["poster_url"]
            if details.get("director"):
                film["director"] = details["director"]
            if details.get("duration"):
                film["duration"] = details["duration"]
            if details.get("description"):
                film["description"] = details["description"]
            time.sleep(0.15)

        self.films_with_english_subs = films
        self.save_results()
        return films

    def save_results(self) -> None:
        os.makedirs("data", exist_ok=True)
        output_file = f"./data/{SOURCE_KEY}_films_with_english_subs.json"
        with open(output_file, "w", encoding="utf-8") as fh:
            json.dump(self.films_with_english_subs, fh, ensure_ascii=False, indent=2)
        total_showtimes = sum(len(f["showtimes"]) for f in self.films_with_english_subs)
        print("\n📊 SCRAPING COMPLETE!")
        print(f"✅ {len(self.films_with_english_subs)} films with English subtitles")
        print(f"💾 Results saved to: {output_file}")
        print(f"📈 Total showtimes: {total_showtimes}")


if __name__ == "__main__":
    Capitolbio().scrape_films()
