#!/usr/bin/env python3
"""Alert on Discord when a cinema has had no English-subtitled screenings for N days."""

import argparse
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path

import httpx


def count_showtimes(data_file):
    try:
        films = json.loads(data_file.read_text(encoding='utf-8'))
    except (FileNotFoundError, json.JSONDecodeError):
        return 0
    if not isinstance(films, list):
        return 0
    return sum(len(f.get('showtimes') or []) for f in films if isinstance(f, dict))


def post_to_discord(webhook, content):
    try:
        response = httpx.post(
            webhook,
            json={'content': content, 'allowed_mentions': {'parse': []}},
            headers={'User-Agent': 'with-english-subs-stale-check'},
            timeout=10,
        )
        response.raise_for_status()
        return True
    except httpx.HTTPError as e:
        print(f"⚠️  Discord notification failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--days', type=int, default=14)
    parser.add_argument('--scrapers-dir', default='scrapers')
    parser.add_argument('--data-dir', default='data')
    parser.add_argument('--state-file', default='data/state/cinema_last_seen.json')
    args = parser.parse_args()

    state_file = Path(args.state_file)
    state = json.loads(state_file.read_text(encoding='utf-8')) if state_file.exists() else {}
    today = datetime.now(timezone.utc).date()

    cinemas = sorted(p.stem for p in Path(args.scrapers_dir).glob('*.py'))
    stale = []
    for cinema in cinemas:
        count = count_showtimes(Path(args.data_dir) / f'{cinema}_films_with_english_subs.json')
        entry = state.setdefault(cinema, {'last_seen': today.isoformat(), 'alerted': False})

        if count > 0:
            entry.update(last_seen=today.isoformat(), alerted=False)
            print(f"✅ {cinema}: {count} showtimes")
            continue

        days = (today - date.fromisoformat(entry['last_seen'])).days
        print(f"⚠️  {cinema}: no showtimes (last seen {entry['last_seen']}, {days} days ago)")
        if days >= args.days and not entry['alerted']:
            stale.append((cinema, entry['last_seen'], days))

    if stale:
        lines = [f"- **{c}**: none since {seen} ({d} days)" for c, seen, d in stale]
        content = (
            f"⚠️ **with-english-subs**: no English-subtitled screenings found "
            f"for {args.days}+ days. The scraper may be broken.\n" + "\n".join(lines)
        )
        webhook = os.environ.get('DISCORD_WEBHOOK')
        if not webhook:
            print("DISCORD_WEBHOOK not set; skipping Discord notification")
            print(content)
        elif post_to_discord(webhook, content):
            for cinema, _, _ in stale:
                state[cinema]['alerted'] = True

    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state, indent=2, sort_keys=True) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
