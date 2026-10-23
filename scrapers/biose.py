#!/usr/bin/env python3
"""
bio.se scraper for independent Stockholm cinemas that sell tickets through bio.se.

Cinemas: Reflexen, Bio Skandia, Älvsjö Bio Park, Årsta Folkets Hus, Biocafé Tellus.

bio.se is a client-rendered Next.js app, so the HTML has no screening data. It reads:
- GET  /api/cinemas/slug/<slug>   -> cinema details (numeric id)
- POST /api/cinemas/films         -> {"cinemaId": <id>} -> {"movies": [{movie, sessions}]}

A session has English subtitles when its subtitle "text" field is "Engelska" or "En".
"""

import html
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone

import httpx

BASE_URL = "https://bio.se"
SOURCE_KEY = "biose"
OUTPUT_FILE = f"./data/{SOURCE_KEY}_films_with_english_subs.json"

# slug on bio.se -> name shown on the site
CINEMAS = {
    "reflexen-2": "Reflexen",
    "stockholm-skandia": "Bio Skandia",
    "alvsjo-bio-park": "Älvsjö Bio Park",
    "arsta-folkets-hus": "Årsta Folkets Hus",
    "biocafe-tellus": "Biocafé Tellus",
}

ENGLISH_SUBTITLE_VALUES = {"engelska", "en"}

# e.g. "Fjord eng txt", "Fjord (eng text)", "Fjord - eng. subs"
TITLE_SUBTITLE_NOTE = re.compile(
    r"\s*[-–—:(]?\s*\beng(?:elsk(?:a)?)?\.?\s*(?:txt|text|subs?|subtitles?|undertext(?:er)?)\b\.?\)?\s*$",
    re.IGNORECASE,
)


def has_english_subtitles(text):
    return (text or "").strip().rstrip(".").lower() in ENGLISH_SUBTITLE_VALUES


def clean_title(title):
    cleaned = TITLE_SUBTITLE_NOTE.sub("", title or "").strip()
    return cleaned or (title or "").strip()


def clean_html(value):
    value = html.unescape(value or "")
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    value = re.sub(r"<[^>]+>", "", value)
    value = html.unescape(value)
    lines = [" ".join(line.split()) for line in value.splitlines()]
    return re.sub(r"\n{2,}", "\n", "\n".join(lines)).strip()


def slugify(title):
    text = (title or "").lower().translate(str.maketrans({"å": "a", "ä": "a", "ö": "o"}))
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


class BioSe:
    def __init__(self, cinemas=None):
        self.cinemas = cinemas or CINEMAS
        self.client = httpx.Client(
            timeout=20.0,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"},
        )

    def fetch_movies(self, slug):
        """Return the cinema's movies with sessions, or None on failure."""
        try:
            cinema = self.client.get(f"{BASE_URL}/api/cinemas/slug/{slug}")
            cinema.raise_for_status()
            films = self.client.post(f"{BASE_URL}/api/cinemas/films", json={"cinemaId": cinema.json()["id"]})
            films.raise_for_status()
            return films.json().get("movies", [])
        except (httpx.HTTPError, KeyError, ValueError) as e:
            print(f"  ❌ Failed to fetch {slug}: {e}")
            return None

    def build_showtime(self, slug, film_url, session):
        dt = datetime.fromisoformat(session["show_date_time"])
        iso = dt.strftime("%Y-%m-%dT%H:%M:%S")
        payment_link = session.get("payment_link") or ""
        return {
            "datetime": iso,
            "display_text": dt.strftime("%A %-d %B %Y at %H:%M"),
            "time": dt.strftime("%H:%M"),
            "date_section": dt.strftime("%d.%m"),
            "ticket_url": f"{BASE_URL}{payment_link}" if payment_link else film_url,
            "hall": session.get("screen_name") or "",
            "audio_language": session.get("language") or "",
            "subtitle_language": "EN",
            "normalized_datetime": iso,
            "normalized_date": dt.strftime("%d.%m"),
            "normalized_time": dt.strftime("%H:%M"),
        }

    def build_film(self, slug, cinema_name, entry):
        movie = entry.get("movie", {})
        movie_text = movie.get("text")

        sessions = []
        seen = set()
        for session in entry.get("sessions", []):
            # Fall back to the film-level value when the session has none
            text = session.get("text") or movie_text
            if not has_english_subtitles(text) or session.get("id") in seen:
                continue
            seen.add(session.get("id"))
            sessions.append(session)
        if not sessions:
            return None

        title = movie.get("title", "")
        movie_id = movie.get("id")
        film_url = f"{BASE_URL}/biografer/{slug}/film/{movie_id}/{slugify(title)}"
        run_time = movie.get("run_time")

        showtimes = sorted(
            (self.build_showtime(slug, film_url, s) for s in sessions),
            key=lambda s: s["normalized_datetime"],
        )
        return {
            "film_id": f"{slug}-{movie_id}",
            "url": film_url,
            "title": clean_title(title),
            "director": "",
            "duration": f"{run_time} min" if run_time else "",
            "language": movie.get("language") or "",
            "genre": ", ".join(g.strip() for g in (movie.get("genre") or "").split(",") if g.strip()),
            "description": clean_html(movie.get("synopsis")),
            "poster_url": movie.get("poster_url") or "",
            "showtimes": showtimes,
            "cinemas": [cinema_name],
            "data_source": cinema_name,
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "source": SOURCE_KEY,
        }

    def scrape_films(self):
        print("🎬 bio.se scraper starting...")
        films = []
        failed = 0
        for slug, cinema_name in self.cinemas.items():
            print(f"🔗 {cinema_name} ({slug})")
            movies = self.fetch_movies(slug)
            if movies is None:
                failed += 1
                continue
            found = [f for f in (self.build_film(slug, cinema_name, m) for m in movies) if f]
            print(f"  📋 {len(movies)} films, {len(found)} with English subtitles")
            films.extend(found)
            time.sleep(0.3)

        if failed == len(self.cinemas):
            print("❌ All cinemas failed - keeping existing data")
            return None

        self.save_results(films)
        return films

    def save_results(self, films):
        os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(films, f, indent=2, ensure_ascii=False)
        total = sum(len(f["showtimes"]) for f in films)
        print(f"💾 Saved {len(films)} films ({total} showtimes) to {OUTPUT_FILE}")


if __name__ == "__main__":
    sys.exit(0 if BioSe().scrape_films() is not None else 1)
