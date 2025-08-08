# GitHub Pages Deployment Setup

This repository includes GitHub Actions workflows to automatically scrape film data and deploy the results to GitHub Pages.

## Setup Instructions

### 1. Enable GitHub Pages

1. Go to your repository settings
2. Navigate to "Pages" in the left sidebar
3. Under "Source", select "GitHub Actions"
4. Save the settings

**Important**: If you see your README content instead of the film website, make sure:
- GitHub Pages is set to "GitHub Actions" (not "Deploy from branch")
- Wait a few minutes after the first workflow run
- The `index.html` file exists in your repository root

### 2. Configure TMDB API Key (Optional)

To enable TMDB data enrichment (movie posters, ratings, etc.):

1. Go to [TMDB](https://www.themoviedb.org/) and create an account
2. Request an API key from your account settings
3. In your GitHub repository, go to Settings → Secrets and variables → Actions
4. Add a new repository secret:
   - Name: `TMDB_API_KEY`
   - Value: Your TMDB API key

### 3. Workflows Available

#### Full Scraping Pipeline (`scrape-and-deploy.yml`)
- **Triggers:** 
  - Daily at 6:00 AM UTC (scheduled)
  - Manual trigger via Actions tab
  - Push to main branch (scraper/template changes)
- **What it does:**
  - Runs all cinema scrapers (Cinemateket, Bio Rio, Fågel Blå, Zita)
  - Enriches data with TMDB information
  - Generates static HTML site
  - Deploys to GitHub Pages

#### Quick Deploy (`deploy-only.yml`)
- **Triggers:**
  - Manual trigger via Actions tab
  - Push to main branch (UI changes only)
- **What it does:**
  - Uses existing JSON data files
  - Regenerates static HTML with updated UI
  - Deploys to GitHub Pages

## Manual Workflow Triggers

You can manually trigger workflows:

1. Go to the "Actions" tab in your repository
2. Select the workflow you want to run
3. Click "Run workflow"
4. Choose the branch (usually `main`)
5. Click "Run workflow"

## Monitoring

- Check the "Actions" tab to monitor workflow runs
- View deployment status and logs
- Access your site at: `https://[username].github.io/[repository-name]`

## Troubleshooting

### Workflow Fails
- Check the logs in the Actions tab
- Common issues:
  - TMDB API key missing (workflow will continue without enrichment)
  - Scraper timeouts (workflow will continue with available data)
  - Invalid JSON format

### Site Not Updating
- Ensure GitHub Pages is configured correctly
- Check if workflows are completing successfully
- GitHub Pages may take a few minutes to update after deployment

### Scraper Issues
- Individual scraper failures won't stop the entire pipeline
- Check logs for specific error messages
- Some cinema websites may be temporarily unavailable

## File Structure

```
.github/workflows/
├── scrape-and-deploy.yml    # Full pipeline with scraping
└── deploy-only.yml          # Quick UI-only deployments

data/                        # Scraped film data
├── cinemateket_films_with_english_subs.json
├── biorio_films_with_english_subs.json
├── fagelbla_films_with_english_subs.json
└── zita_films_with_english_subs.json

assets/                      # Frontend resources
├── script.js               # JavaScript for film display
└── styles.css              # CSS styling

templates/                   # HTML templates
└── index_template.html     # Base template

scripts/                     # Python processing scripts
├── static_generator.py     # Generates final HTML
├── tmdb_enricher.py       # Adds TMDB data
├── translate_json_fields.py # Translation utilities
└── run_full_pipeline.sh   # Complete pipeline script

scrapers/                    # Cinema website scrapers
├── cinemateket.py
├── biorio.py
├── fagelbla.py
└── zita.py

Generated files:
├── index.html              # Deployed to GitHub Pages
└── films_static.html       # Generated before rename
```

## Customization

To modify the schedule:
1. Edit the `cron` expression in `scrape-and-deploy.yml`
2. Use [crontab.guru](https://crontab.guru/) to help with cron syntax

To add more scrapers:
1. Add your scraper to the `scrapers/` directory
2. Update the workflow to include your scraper in the pipeline

## Local Development

Run the full pipeline locally:
```bash
# Make script executable
chmod +x scripts/run_full_pipeline.sh

# Run with TMDB enrichment
TMDB_API_KEY=your_key_here scripts/run_full_pipeline.sh

# Generate static site only
python scripts/static_generator.py
```

Run individual components:
```bash
# Run a specific scraper
python scrapers/cinemateket.py

# Enrich with TMDB data
python scripts/tmdb_enricher.py data/cinemateket_films_with_english_subs.json

# Generate static HTML
python scripts/static_generator.py --output index.html
```