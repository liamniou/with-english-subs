# =============================================================================
# Films with English Subtitles - Makefile
# =============================================================================
# Local equivalent of .github/workflows/scrape-and-deploy.yml
#
# Quick start:
#   make install    # install python deps
#   make pipeline   # full scrape + enrich + translate + normalize + generate
#   make serve      # preview locally at http://localhost:8000
#
# Run `make help` for the full target list.
# =============================================================================

PYTHON       ?= python3
VENV         := .venv
VENV_PYTHON  := $(VENV)/bin/python
VENV_PIP     := $(VENV)/bin/pip
# Use venv python if it exists, otherwise system python
PY           := $(shell [ -x $(VENV_PYTHON) ] && echo $(VENV_PYTHON) || echo $(PYTHON))
DATA_DIR     := data
SCRAPERS_DIR := scrapers
SCRIPTS_DIR  := scripts
INDEX        := index.html
PORT         ?= 8000

BATCH_SIZE          ?= 50
FIELDS_TO_TRANSLATE ?= showtimes.display_text,showtimes.datetime

# Auto-load .env if present (TMDB_API_KEY, GEMINI_API_KEY, ...)
ifneq (,$(wildcard ./.env))
    include .env
    export
endif

# Discover scrapers and their output JSON files
SCRAPERS   := $(notdir $(basename $(wildcard $(SCRAPERS_DIR)/*.py)))
DATA_FILES := $(addprefix $(DATA_DIR)/,$(addsuffix _films_with_english_subs.json,$(SCRAPERS)))

.DEFAULT_GOAL := help
.PHONY: help install scrape enrich translate normalize generate pipeline \
        clean clean-all serve check FORCE

## help: Show this help message
help:
	@echo "Films with English Subtitles - Make targets:"
	@echo ""
	@awk 'BEGIN {FS = ":.*?## "} /^## / {sub(/^## /, ""); split($$0, a, ": "); printf "  \033[36m%-18s\033[0m %s\n", a[1], a[2]}' $(MAKEFILE_LIST)
	@echo ""
	@echo "Discovered scrapers: $(SCRAPERS)"
	@echo "Per-scraper targets: $(addprefix scrape-,$(SCRAPERS))"

## install: Create venv (if missing) and install Python dependencies
install: $(VENV_PYTHON)
	$(VENV_PIP) install --upgrade pip
	$(VENV_PIP) install -r requirements.txt
	@echo "✅ Installed into $(VENV). Activate with: source $(VENV)/bin/activate"

$(VENV_PYTHON):
	@echo "🔸 Creating virtual environment in $(VENV)..."
	$(PYTHON) -m venv $(VENV)

## check: Verify required tools and warn about missing API keys
check:
	@command -v $(PYTHON) >/dev/null || { echo "❌ $(PYTHON) not found"; exit 1; }
	@echo "✅ $(PY): $$($(PY) --version)"
	@[ -x $(VENV_PYTHON) ] && echo "✅ venv: $(VENV)" || echo "⚠️  No venv at $(VENV) - run 'make install' to create one"
	@[ -n "$$TMDB_API_KEY" ]   && echo "✅ TMDB_API_KEY set"   || echo "⚠️  TMDB_API_KEY not set - TMDB enrichment will be skipped"
	@[ -n "$$GEMINI_API_KEY" ] && echo "✅ GEMINI_API_KEY set" || echo "⚠️  GEMINI_API_KEY not set - translation will be skipped"

## scrape: Run all scrapers
scrape: $(addprefix scrape-,$(SCRAPERS))

# Per-scraper rule: `make scrape-biorio`, `make scrape-zita`, ...
scrape-%: FORCE
	@echo "🔸 Running $* scraper..."
	@mkdir -p $(DATA_DIR)
	$(PY) $(SCRAPERS_DIR)/$*.py

FORCE:

## enrich: Enrich all data files with TMDB metadata (requires TMDB_API_KEY)
enrich:
	@if [ -z "$$TMDB_API_KEY" ]; then echo "⚠️  TMDB_API_KEY not set - skipping"; exit 0; fi
	@for f in $(DATA_DIR)/*_films_with_english_subs.json; do \
		[ -f "$$f" ] || continue; \
		echo "🔸 Enriching $$f..."; \
		$(PY) $(SCRIPTS_DIR)/tmdb_enricher.py "$$f" --api-key "$$TMDB_API_KEY" || echo "⚠️  failed: $$f"; \
	done

## translate: Translate JSON fields with Gemini (requires GEMINI_API_KEY)
translate:
	@if [ -z "$$GEMINI_API_KEY" ]; then echo "⚠️  GEMINI_API_KEY not set - skipping"; exit 0; fi
	@for f in $(DATA_DIR)/*_films_with_english_subs.json; do \
		[ -f "$$f" ] || continue; \
		echo "🔸 Translating $$f..."; \
		$(PY) $(SCRIPTS_DIR)/translate_json_fields.py "$$f" \
			--fields "$(FIELDS_TO_TRANSLATE)" \
			--api-key "$$GEMINI_API_KEY" \
			--batch-size $(BATCH_SIZE) || { echo "⚠️  failed: $$f"; continue; }; \
		translated="$${f%.json}_translated.json"; \
		[ -f "$$translated" ] && mv "$$translated" "$$f" && echo "  ✅ replaced $$f"; \
	done

## normalize: Normalize datetime fields across all data files
normalize:
	@chmod +x $(SCRIPTS_DIR)/normalize_datetime.sh
	$(SCRIPTS_DIR)/normalize_datetime.sh

## generate: Build static index.html with embedded data
generate:
	$(PY) $(SCRIPTS_DIR)/static_generator.py --output $(INDEX)
	@echo "✅ Generated $(INDEX) ($$(du -h $(INDEX) | cut -f1))"

## pipeline: Full pipeline - scrape, enrich, translate, normalize, generate
pipeline: check scrape enrich translate normalize generate
	@rm -rf $(DATA_DIR)/backups/
	@echo ""
	@echo "🎉 Pipeline complete. Open $(INDEX) or run 'make serve'."

## serve: Serve the site locally (PORT=8000 by default)
serve:
	@echo "Serving at http://localhost:$(PORT) (Ctrl+C to stop)"
	$(PY) -m http.server $(PORT)

## clean: Remove generated index.html and backup files
clean:
	rm -f $(INDEX)
	rm -rf $(DATA_DIR)/backups/

## clean-all: Also remove all scraped JSON data files
clean-all: clean
	rm -f $(DATA_DIR)/*_films_with_english_subs.json
	rm -f $(DATA_DIR)/*_translated.json
