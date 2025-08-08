# Films with English Subtitles - Cinemateket Stockholm

This project scrapes the Swedish Film Institute's Cinemateket Stockholm website to find films with English subtitles.

## Features

- 🎬 Finds films with English subtitles from Cinemateket Stockholm
- 📝 Extracts detailed film information (titles, showtimes, descriptions, cinemas)
- 🎭 Optional TMDb enrichment with separate script (`tmdb_enricher.py`)
- 🌐 Static HTML generator for self-contained web display (`static_generator.py`)
- 💾 Saves results in multiple formats (JSON, human-readable summaries)
- 🔧 Built with modern libraries (`httpx`, `selectolax`)

## Quick Start

### 1. Install dependencies:
```bash
python -m venv venv
source venv/bin/activate 
pip install -r requirements.txt
```

### 2. Set up TMDb API (optional but recommended):
1. Create a free account at [The Movie Database](https://www.themoviedb.org/)
2. Go to [API Settings](https://www.themoviedb.org/settings/api) and request an API key
3. Create a `.env` file in the project root:
```bash
cp env.example .env
# Edit .env and add your API key:
TMDB_API_KEY=your_actual_api_key_here
```

### 3. Run the scraper:
```bash
# Basic scraping (no TMDb data)
python run_scraper.py

# Optional: Add TMDb data to existing results
python tmdb_enricher.py films_with_english_subs.json

# Optional: Generate static HTML page
python static_generator.py
```

### Or use the scraper directly:
```bash
python scrapers/cinemateket.py
```

## Output Files

The scraper generates three files:
- `films_with_english_subs.json` - Complete data in JSON format
- `films_with_english_subs_summary.txt` - Detailed human-readable format
- `films_with_english_subs_list.txt` - Simple list format

## How it works

1. Scrapes the Cinemateket program page
2. Finds all film links in article divs
3. Visits each film page to check for "engelsk text" 
4. Extracts additional details (showtimes, descriptions, cinemas) for films with English subtitles
5. Optionally enriches data with TMDb information using separate script
6. Saves complete data in multiple formats

## TMDb Integration

Use the separate `tmdb_enricher.py` script to add movie data from The Movie Database API:

```bash
# First run the basic scraper
python run_scraper.py

# Then enrich with TMDb data
python tmdb_enricher.py films_with_english_subs.json
```

TMDb enrichment adds:
- Movie ratings and vote counts
- Genres and production countries
- Director and main cast
- Runtime and release dates
- Movie posters and backdrop images
- Plot overviews and more

This separation allows you to:
- Run fast scraping without API dependencies
- Enrich data only when needed
- Re-enrich existing data with updated information

### Manual TMDb IDs

For films that aren't found automatically or are matched incorrectly, you can manually specify TMDb IDs by adding a `manual_tmdb` field to any film in the JSON:

```json
{
  "film_id": "13909",
  "title": "Helfen können wir uns nur selbst / Women's Camera",
  "manual_tmdb": 123456,
  "showtimes": [...],
  ...
}
```

The enricher will use the manual ID instead of searching when provided:

```bash
# Re-run enrichment to apply manual TMDb IDs
python tmdb_enricher.py films_with_english_subs.json
```

## Static HTML Generation

Generate self-contained HTML files that work without a web server:

```bash
# Generate with default settings
python static_generator.py

# Use custom files
python static_generator.py --json films_updated.json --output my_page.html

# Check if all required files exist
python static_generator.py --check-files
```

The static generator combines:
- HTML template (`index.html`)
- CSS styles (`styles.css`) 
- JavaScript code (`script.js`)
- JSON data (film listings)

Into a single `.html` file that can be:
- Opened directly in any browser
- Shared via email or file transfer
- Hosted on any web server
- Used offline without dependencies