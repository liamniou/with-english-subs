#!/usr/bin/env python3
"""
Bio Bristol scraper.

Bio Bristol uses the Filmgrail platform. The pages are SSR'd as Vue
components, with all data embedded as URL-encoded JSON inside
``<script>const data = JSON.parse(decodeURIComponent("..."))</script>``
blobs.

We:
  1. GET the listing page and extract the movies list (one blob holds
     a "movies" array with movieId/title/poster/etc).
  2. For each movie, GET ``/f/x/<movieId>`` and walk every JSON blob to
     collect ``showtimes`` arrays.
  3. Keep only showtimes whose ``notes`` includes ``engelsk text``.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
from datetime import datetime, timezone
from typing import Any

import httpx


BASE = "https://www.biobristol.se"
LISTING_URL = f"{BASE}/actual-content?tab=playingnow"
CINEMA_NAME = "Bio Bristol"
SOURCE_KEY = "biobristol"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)

RE_BLOB = re.compile(r'JSON\.parse\(decodeURIComponent\("([^"]+)"\)')


class BioBristol:
    def __init__(self) -> None:
        self.client = httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )
        self.films_with_english_subs: list[dict[str, Any]] = []

    # -- blob extraction ------------------------------------------------------

    @staticmethod
    def _decode_blobs(html: str) -> list[Any]:
        blobs: list[Any] = []
        for m in RE_BLOB.finditer(html):
            try:
                blobs.append(json.loads(urllib.parse.unquote(m.group(1))))
            except (json.JSONDecodeError, ValueError):
                continue
        return blobs

    @staticmethod
    def _find_first(blobs: list[Any], key: str) -> Any:
        """Return the first occurrence of ``key`` anywhere in the blob trees."""
        for blob in blobs:
            stack = [blob]
            while stack:
                node = stack.pop()
                if isinstance(node, dict):
                    if key in node:
                        return node[key]
                    stack.extend(node.values())
                elif isinstance(node, list):
                    stack.extend(node)
        return None

    @staticmethod
    def _collect_showtimes(blobs: list[Any]) -> list[dict[str, Any]]:
        """Collect every ``showtimes`` list embedded anywhere in the blobs,
        deduplicated by ``showId``."""
        seen: dict[str, dict[str, Any]] = {}
        for blob in blobs:
            stack = [blob]
            while stack:
                node = stack.pop()
                if isinstance(node, dict):
                    sts = node.get("showtimes")
                    if isinstance(sts, list):
                        for st in sts:
                            if isinstance(st, dict) and st.get("showId"):
                                seen.setdefault(st["showId"], st)
                    stack.extend(node.values())
                elif isinstance(node, list):
                    stack.extend(node)
        return list(seen.values())

    # -- listing --------------------------------------------------------------

    def fetch_movie_list(self) -> list[dict[str, Any]]:
        resp = self.client.get(LISTING_URL)
        resp.raise_for_status()
        blobs = self._decode_blobs(resp.text)
        movies: list[dict[str, Any]] = []
        seen_ids: set[int] = set()
        for blob in blobs:
            stack = [blob]
            while stack:
                node = stack.pop()
                if isinstance(node, dict):
                    if "movies" in node and isinstance(node["movies"], list):
                        for m in node["movies"]:
                            mid = m.get("movieId")
                            if mid and mid not in seen_ids:
                                seen_ids.add(mid)
                                movies.append(m)
                    stack.extend(node.values())
                elif isinstance(node, list):
                    stack.extend(node)
        return movies

    # -- film detail ----------------------------------------------------------

    def fetch_film(self, movie_id: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        url = f"{BASE}/f/x/{movie_id}"
        try:
            resp = self.client.get(url)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            print(f"   ⚠️  could not fetch {url}: {exc}")
            return [], {}
        blobs = self._decode_blobs(resp.text)
        showtimes = self._collect_showtimes(blobs)

        # Pull richer movie metadata from the detail page if present.
        movie_meta: dict[str, Any] = {}
        for blob in blobs:
            stack = [blob]
            while stack:
                node = stack.pop()
                if isinstance(node, dict):
                    if node.get("movieId") == movie_id and "title" in node:
                        for k in ("title", "titleOriginal", "overview", "poster",
                                  "director", "runtime", "language",
                                  "releaseYear", "genres"):
                            if k in node and k not in movie_meta:
                                movie_meta[k] = node[k]
                    stack.extend(node.values())
                elif isinstance(node, list):
                    stack.extend(node)
        return showtimes, movie_meta

    # -- normalization --------------------------------------------------------

    @staticmethod
    def _normalize_showtime(st: dict[str, Any]) -> dict[str, Any] | None:
        start = st.get("startTime")
        if not start:
            return None
        # ``startTime`` is a UTC-formatted string but actually carries the
        # Stockholm wall-clock time (Filmgrail quirk). Treat it as naive
        # and rely on ``startTimeTransformed`` for the displayed clock.
        try:
            dt = datetime.fromisoformat(start.replace("Z", ""))
        except ValueError:
            return None

        local_time = (st.get("startTimeTransformed") or "").strip()
        if re.fullmatch(r"\d{1,2}:\d{2}", local_time):
            try:
                hh, mm = (int(p) for p in local_time.split(":"))
                dt = dt.replace(hour=hh, minute=mm)
            except ValueError:
                pass

        iso = dt.strftime("%Y-%m-%dT%H:%M:%S")
        time_str = dt.strftime("%H:%M")
        return {
            "datetime": iso,
            "display_text": dt.strftime("%A %-d %B %Y at %H:%M"),
            "time": time_str,
            "date_section": dt.strftime("%d.%m"),
            "ticket_url": f"{BASE}/checkout?showId={st.get('showId','')}",
            "show_id": st.get("showId"),
            "hall": st.get("screenName") or "",
            "audio_language": "",
            "subtitle_language": "EN",
            "normalized_datetime": iso,
            "normalized_date": dt.strftime("%d.%m"),
            "normalized_time": time_str,
        }

    # -- entry point ----------------------------------------------------------

    def scrape_films(self) -> list[dict[str, Any]]:
        print("🎬 Bio Bristol scraper starting...")
        movies = self.fetch_movie_list()
        print(f"📋 Found {len(movies)} movies on listing page")

        for movie in movies:
            movie_id = movie["movieId"]
            title = movie.get("title", "")
            print(f"🔍 {title} (movieId={movie_id})")
            showtimes, detail_meta = self.fetch_film(movie_id)
            en_showtimes = [st for st in showtimes if "engelsk text" in (st.get("notes") or [])]
            if not en_showtimes:
                print(f"   ❌ no English-subtitle showtimes")
                time.sleep(0.15)
                continue
            print(f"   ✅ {len(en_showtimes)} English-subtitle showtime(s)")

            normalized = [n for st in en_showtimes if (n := self._normalize_showtime(st))]
            normalized.sort(key=lambda s: s["normalized_datetime"])

            slug = re.sub(r"[^a-z0-9]+", "-", (movie.get("title") or "").lower()).strip("-") or str(movie_id)
            poster = movie.get("poster") or detail_meta.get("poster") or ""
            description = movie.get("overview") or detail_meta.get("overview") or ""
            director = movie.get("director") or detail_meta.get("director") or ""
            runtime = movie.get("runtime") or detail_meta.get("runtime")
            duration = f"{runtime} min" if runtime else ""

            self.films_with_english_subs.append({
                "film_id": slug,
                "url": f"{BASE}/f/{slug}/{movie_id}",
                "title": movie.get("title") or detail_meta.get("title") or "",
                "director": director,
                "duration": duration,
                "language": movie.get("language") or "",
                "description": description,
                "poster_url": poster,
                "showtimes": normalized,
                "cinemas": [CINEMA_NAME],
                "scraped_at": datetime.now(timezone.utc).isoformat(),
                "source": SOURCE_KEY,
            })
            time.sleep(0.15)

        self.save_results()
        return self.films_with_english_subs

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
    BioBristol().scrape_films()
