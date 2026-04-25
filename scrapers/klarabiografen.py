#!/usr/bin/env python3
"""
Klarabiografen (Kulturhuset Stadsteatern) scraper.

Strategy
--------
The listing page at https://kulturhusetstadsteatern.se/bio/klarabiografen is
rendered client-side and pages results through an Elasticsearch endpoint:

    POST https://elastic.kulturhusetstadsteatern.se/khst-events/_search

Each hit is one *showtime*. We:
  1. Page through all upcoming Klarabiografen events via the API.
  2. Group hits by drupalLink (one entry per film).
  3. Fetch each film's detail page once and check for "Engelska undertexter".
  4. Keep only films with English subtitles and write the standard JSON shape.
"""

from __future__ import annotations

import base64
import json
import os
import time
from datetime import datetime, timezone
from typing import Any

import httpx


ES_URL = "https://elastic.kulturhusetstadsteatern.se/khst-events/_search"
# "elastic:elastic" - the public credential the website itself uses.
ES_AUTH = "Basic " + base64.b64encode(b"elastic:elastic").decode()

# drupalCategory id 6 = Bio, tixVenue id 205 = Sergels torg (Klarabiografen).
DRUPAL_CATEGORY_ID = "6"
TIX_VENUE_ID = "205"

CINEMA_NAME = "Klarabiografen"
SOURCE_KEY = "klarabiografen"
PAGE_SIZE = 50

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)


class Klarabiografen:
    def __init__(self) -> None:
        self.client = httpx.Client(
            timeout=20.0,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )
        self.films_with_english_subs: list[dict[str, Any]] = []

    # -- API ------------------------------------------------------------------

    def _search_body(self, from_: int, size: int) -> dict[str, Any]:
        today = datetime.now().strftime("%Y-%m-%d")
        return {
            "query": {
                "bool": {
                    "must": [{"range": {"tixStartDate": {"gte": today}}}],
                    "filter": [
                        {
                            "nested": {
                                "path": "drupalCategory",
                                "query": {
                                    "bool": {
                                        "filter": [
                                            {"terms": {"drupalCategory.id.keyword": [DRUPAL_CATEGORY_ID]}}
                                        ]
                                    }
                                },
                            }
                        },
                        {
                            "nested": {
                                "path": "tixVenue",
                                "query": {
                                    "bool": {
                                        "filter": [
                                            {"terms": {"tixVenue.id.keyword": [TIX_VENUE_ID]}}
                                        ]
                                    }
                                },
                            }
                        },
                    ],
                }
            },
            "sort": [{"tixStartDate": {"order": "asc"}}],
            "size": size,
            "from": from_,
        }

    def fetch_all_events(self) -> list[dict[str, Any]]:
        """Page through the Elasticsearch endpoint and return every hit's _source."""
        events: list[dict[str, Any]] = []
        from_ = 0
        while True:
            body = self._search_body(from_, PAGE_SIZE)
            print(f"📡 Fetching events {from_}..{from_ + PAGE_SIZE}")
            resp = self.client.post(
                ES_URL,
                content=json.dumps(body),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": ES_AUTH,
                    "Origin": "https://kulturhusetstadsteatern.se",
                    "Referer": "https://kulturhusetstadsteatern.se/",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            hits = data.get("hits", {}).get("hits", [])
            if not hits:
                break
            events.extend(h.get("_source", {}) for h in hits)
            total = data.get("hits", {}).get("total", {}).get("value", 0)
            print(f"   got {len(hits)} hits (running total {len(events)} / {total})")
            from_ += PAGE_SIZE
            if from_ >= total:
                break
            time.sleep(0.2)
        return events

    # -- detail page ----------------------------------------------------------

    def has_english_subtitles(self, film_url: str) -> bool:
        """Fetch the film detail page and look for an English-subtitle marker."""
        try:
            resp = self.client.get(film_url)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            print(f"   ⚠️  could not fetch {film_url}: {exc}")
            return False
        text = resp.text.lower()
        # The site uses headings like "OBS! Engelska undertexter" or
        # "Engelska undertexter" inline. Match either spelling.
        return "engelska undertexter" in text or "english subtitles" in text

    # -- aggregation ----------------------------------------------------------

    @staticmethod
    def _slug_from_url(url: str) -> str:
        return url.rstrip("/").rsplit("/", 1)[-1]

    @staticmethod
    def _normalize_showtime(event: dict[str, Any]) -> dict[str, Any]:
        start = event.get("tixStartDate", "")
        # tixStartDate is ISO with offset, e.g. 2026-04-24T18:00:00+02:00
        normalized_dt = ""
        normalized_date = ""
        normalized_time = ""
        try:
            dt = datetime.fromisoformat(start)
            normalized_dt = dt.strftime("%Y-%m-%dT%H:%M:%S")
            normalized_date = dt.strftime("%d.%m")
            normalized_time = dt.strftime("%H:%M")
            display = dt.strftime("%A %-d %B %Y at %H:%M")
        except (TypeError, ValueError):
            display = start

        hall = ""
        halls = event.get("tixHall") or []
        if halls and isinstance(halls, list):
            hall = halls[0].get("label", "")

        return {
            "datetime": start,
            "display_text": display,
            "time": normalized_time,
            "date_section": normalized_date,
            "ticket_url": event.get("tixTicketLink", ""),
            "tix_event_id": event.get("tixEventId"),
            "tix_event_group_id": event.get("tixEventGroupId"),
            "hall": hall,
            "normalized_datetime": normalized_dt,
            "normalized_date": normalized_date,
            "normalized_time": normalized_time,
        }

    def aggregate_films(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Group events by drupalLink; one film entry per unique URL."""
        by_url: dict[str, dict[str, Any]] = {}
        for event in events:
            url = event.get("drupalLink")
            if not url:
                continue
            if url not in by_url:
                lead = ""
                lead_list = event.get("drupalLeadText") or []
                if lead_list and isinstance(lead_list, list):
                    lead = lead_list[0].get("value", "")
                hero = ""
                hero_list = event.get("drupalHeroImage") or []
                if hero_list and isinstance(hero_list, list):
                    hero = hero_list[0].get("src", "")
                by_url[url] = {
                    "film_id": self._slug_from_url(url),
                    "url": url,
                    "title": event.get("drupalTitle") or event.get("tixName") or "",
                    "director": "",
                    "duration": event.get("tixDuration", ""),
                    "language": "",
                    "description": lead,
                    "poster_url": hero,
                    "showtimes": [],
                    "cinemas": [CINEMA_NAME],
                    "scraped_at": datetime.now(timezone.utc).isoformat(),
                    "source": SOURCE_KEY,
                }
            by_url[url]["showtimes"].append(self._normalize_showtime(event))
        return list(by_url.values())

    # -- entry point ----------------------------------------------------------

    def scrape_films(self) -> list[dict[str, Any]]:
        print("🎬 Klarabiografen scraper starting...")
        events = self.fetch_all_events()
        films = self.aggregate_films(events)
        print(f"📋 Found {len(films)} unique films, {sum(len(f['showtimes']) for f in films)} showtimes")

        for film in films:
            print(f"🔍 Checking '{film['title']}' for English subtitles...")
            if self.has_english_subtitles(film["url"]):
                print("  ✅ English subtitles")
                self.films_with_english_subs.append(film)
            else:
                print("  ❌ no English subtitles")
            time.sleep(0.3)

        self.save_results()
        return self.films_with_english_subs

    def save_results(self) -> None:
        os.makedirs("data", exist_ok=True)
        output_file = f"./data/{SOURCE_KEY}_films_with_english_subs.json"
        with open(output_file, "w", encoding="utf-8") as fh:
            json.dump(self.films_with_english_subs, fh, ensure_ascii=False, indent=2)

        total_showtimes = sum(len(f["showtimes"]) for f in self.films_with_english_subs)
        print("\n📊 SCRAPING COMPLETE!")
        print(f"✅ Found {len(self.films_with_english_subs)} films with English subtitles")
        print(f"💾 Results saved to: {output_file}")
        print(f"📈 Total showtimes: {total_showtimes}")


if __name__ == "__main__":
    Klarabiografen().scrape_films()
