#!/bin/bash

# =============================================================================
# Films with English Subtitles - Full Pipeline Script (Reworked)
# =============================================================================
# This script runs the complete pipeline for each scraper individually:
# For each scraper:
#   1. Run scraper
#   2. Enrich with TMDB data
#   3. Translate JSON fields
# Finally:
#   4. Generate static HTML with all data
# =============================================================================

# set -e  # Exit on any error

# Load environment variables from .env file if it exists
if [ -f .env ]; then
    echo "📄 Loading environment variables from .env file..."
    set -a  # automatically export all variables
    source .env
    set +a  # disable automatic export
else
    echo "📄 No .env file found, using system environment variables"
fi

# Configuration
GEMINI_API_KEY=${GEMINI_API_KEY:-""}
TMDB_API_KEY=${TMDB_API_KEY:-""}
BATCH_SIZE=50
FIELDS_TO_TRANSLATE="showtimes.display_text,showtimes.datetime"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

# Functions
log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

log_header() {
    local separator=$(printf '=%.0s' {1..70})
    echo -e "\n${PURPLE}${separator}${NC}"
    echo -e "${PURPLE}$1${NC}"
    echo -e "${PURPLE}${separator}${NC}\n"
}

log_step() {
    echo -e "\n${BLUE}🔸 $1${NC}"
}

check_requirements() {
    log_header "CHECKING REQUIREMENTS"
    
    # Check Python
    if ! command -v python3 &> /dev/null; then
        log_error "python3 is not installed"
        exit 1
    fi
    log_success "Python3 found: $(python3 --version)"
    
    # Discover all scrapers
    local scrapers=(scrapers/*.py)
    if [[ ${#scrapers[@]} -eq 0 ]]; then
        log_error "No scrapers found in scrapers/ directory"
        exit 1
    fi
    
    # Check required files
    local required_files=("scripts/tmdb_enricher.py" "scripts/translate_json_fields.py" "scripts/static_generator.py")
    for file in "${required_files[@]}"; do
        if [[ ! -f "$file" ]]; then
            log_error "Required file not found: $file"
            exit 1
        fi
    done
    log_success "All required files found"
    
    # Check scrapers
    for scraper in "${scrapers[@]}"; do
        if [[ -f "$scraper" ]]; then
            log_success "Found scraper: $scraper"
        fi
    done
    
    # Check API keys
    if [[ -z "$GEMINI_API_KEY" ]]; then
        log_warning "GEMINI_API_KEY not set - translation will be skipped"
    else
        log_success "Gemini API key configured"
    fi
    
    if [[ -z "$TMDB_API_KEY" ]]; then
        log_warning "TMDB_API_KEY not set - TMDB enrichment will be skipped"
    else
        log_success "TMDB API key configured"
    fi
}

run_scraper() {
    local scraper_path="$1"
    local scraper_name=$(basename "$scraper_path" .py)
    local output_file="data/${scraper_name}_films_with_english_subs.json"
    
    log_step "Running $scraper_name scraper..."
    
    # Temporarily disable exit on error for scraper execution
    set +e
    python3 "$scraper_path"
    local scraper_exit_code=$?
    # set -e  # Re-enable exit on error
    
    if [[ $scraper_exit_code -eq 0 ]] && [[ -f "$output_file" ]]; then
        local film_count=$(python3 -c "import json; data=json.load(open('$output_file')); print(len(data))" 2>/dev/null || echo "0")
        log_success "$scraper_name scraper completed - Found $film_count films"
        return 0
    else
        log_error "$scraper_name scraper failed (exit code: $scraper_exit_code)"
        return 1
    fi
}

enrich_with_tmdb() {
    local json_file="$1"
    local scraper_name="$2"
    
    if [[ -z "$TMDB_API_KEY" ]]; then
        log_warning "Skipping TMDB enrichment for $scraper_name - no API key"
        return 0
    fi
    
    if [[ ! -f "$json_file" ]]; then
        log_warning "JSON file not found: $json_file - skipping TMDB enrichment"
        return 0
    fi
    
    log_step "Enriching $scraper_name data with TMDB..."
    
    # Temporarily disable exit on error for TMDB enrichment step
    set +e
    python3 scripts/tmdb_enricher.py "$json_file" --api-key "$TMDB_API_KEY"
    local tmdb_exit_code=$?
    # set -e  # Re-enable exit on error
    
    if [[ $tmdb_exit_code -eq 0 ]]; then
        log_success "TMDB enrichment completed for $scraper_name"
        return 0
    else
        log_error "TMDB enrichment failed for $scraper_name (exit code: $tmdb_exit_code)"
        log_warning "Continuing with next step..."
        return 1
    fi
}

translate_json_fields() {
    local json_file="$1"
    local scraper_name="$2"
    
    if [[ -z "$GEMINI_API_KEY" ]]; then
        log_warning "Skipping translation for $scraper_name - no API key"
        return 0
    fi
    
    if [[ ! -f "$json_file" ]]; then
        log_warning "JSON file not found: $json_file - skipping translation"
        return 0
    fi
    
    log_step "Translating $scraper_name JSON fields..."
    
    # Temporarily disable exit on error for translation step
    set +e
    python3 scripts/translate_json_fields.py "$json_file" \
        --fields "$FIELDS_TO_TRANSLATE" \
        --api-key "$GEMINI_API_KEY" \
        --batch-size "$BATCH_SIZE"
    local translation_exit_code=$?
    # set -e  # Re-enable exit on error
    
    if [[ $translation_exit_code -eq 0 ]]; then
        # Replace original file with translated version
        local translated_file="${json_file%%.json}_translated.json"
        if [[ -f "$translated_file" ]]; then
            log_step "Replacing original with translated version..."
            mv "$translated_file" "$json_file"
            log_success "Translation completed for $scraper_name - original file updated"
        else
            log_warning "Translated file not found: $translated_file"
        fi
        return 0
    else
        log_error "Translation failed for $scraper_name (exit code: $translation_exit_code)"
        log_warning "Continuing with next scraper..."
        return 1
    fi
}

process_scraper() {
    local scraper_path="$1"
    local scraper_name=$(basename "$scraper_path" .py)
    local output_file="data/${scraper_name}_films_with_english_subs.json"
    
    log_header "PROCESSING: $scraper_name"
    
    # Step 1: Run scraper
    if ! run_scraper "$scraper_path"; then
        log_error "Failed to run $scraper_name - continuing with next scraper"
        return 1
    fi
    
    # Step 2: Enrich with TMDB
    if ! enrich_with_tmdb "$output_file" "$scraper_name"; then
        log_warning "TMDB enrichment failed for $scraper_name - continuing"
    fi
    
    # Step 3: Translate fields
    if ! translate_json_fields "$output_file" "$scraper_name"; then
        log_warning "Translation failed for $scraper_name - continuing"
    fi
    
    log_success "Completed processing $scraper_name"
    return 0
}

normalize_datetime_data() {
    log_header "NORMALIZING DATETIME DATA"
    
    log_step "Running datetime normalization..."
    
    # Check if normalization script exists
    if [[ ! -f "scripts/normalize_datetime.sh" ]]; then
        log_warning "DateTime normalization script not found - skipping normalization"
        return 0
    fi
    
    # Run datetime normalization
    if scripts/normalize_datetime.sh; then
        log_success "DateTime normalization completed"
        return 0
    else
        log_error "DateTime normalization failed"
        log_warning "Continuing with next step..."
        return 1
    fi
}

generate_static_site() {
    log_header "GENERATING STATIC WEBSITE"
    
    log_step "Running static site generator..."
    
    python3 scripts/static_generator.py --output index.html
    
    if [[ $? -eq 0 ]] && [[ -f "index.html" ]]; then
        log_success "Static website generated: index.html"
        
        # Get file size
        local file_size=$(du -h index.html | cut -f1)
        log_info "File size: $file_size"
        
        # Count total films
        local total_films=$(python3 -c "
import json
import os
import glob

total = 0
sources = []
for json_file in glob.glob('*_films_with_english_subs.json'):
    if os.path.exists(json_file):
        try:
            with open(json_file, 'r') as f:
                data = json.load(f)
                count = len(data)
                total += count
                sources.append(f'{json_file}: {count} films')
        except:
            pass

print(f'Total films: {total}')
for source in sources:
    print(f'  - {source}')
" 2>/dev/null)
        
        echo -e "${GREEN}$total_films${NC}"
        
        return 0
    else
        log_error "Static site generation failed"
        return 1
    fi
}

tmdb_only_mode() {
    log_header "TMDB ENRICHMENT ONLY MODE"
    
    check_requirements
    
    if [[ -z "$TMDB_API_KEY" ]]; then
        log_error "TMDB_API_KEY not found. Please set it in environment or .env file"
        exit 1
    fi
    
    # Find all JSON files in data directory
    local json_files=(data/*_films_with_english_subs.json)
    local processed_count=0
    
    if [ ! -d "data" ]; then
        log_error "Data directory not found. Run scrapers first or ensure JSON files exist."
        exit 1
    fi
    
    # Check if any JSON files exist (handle case where glob doesn't match)
    if [[ ! -f "${json_files[0]}" ]]; then
        log_error "No JSON files found in data/ directory. Run scrapers first."
        exit 1
    fi
    
    log_step "Found ${#json_files[@]} JSON files to process"
    
    for json_file in "${json_files[@]}"; do
        if [[ -f "$json_file" ]]; then
            local scraper_name=$(basename "$json_file" _films_with_english_subs.json)
            log_step "Enriching $scraper_name data with TMDB..."
            
            if enrich_with_tmdb "$json_file" "$scraper_name"; then
                ((processed_count++))
                log_success "TMDB enrichment completed for $scraper_name"
            else
                log_error "TMDB enrichment failed for $scraper_name"
            fi
        fi
    done
    
    if [[ $processed_count -eq 0 ]]; then
        log_error "No JSON files were processed successfully"
        exit 1
    fi
    
    log_success "Processed $processed_count JSON files with TMDB enrichment"
    
    # Optionally generate static site with updated data
    read -p "Generate static HTML with enriched data? (y/N): " -r
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        if generate_static_site; then
            log_success "Static HTML generated: index.html"
        else
            log_error "Static site generation failed"
        fi
    fi
    
    log_header "TMDB ENRICHMENT COMPLETED! 🎉"
}

show_results() {
    log_header "PIPELINE COMPLETED SUCCESSFULLY! 🎉"
    
    echo -e "${GREEN}📁 Generated files:${NC}"
    echo -e "   ${GREEN}• index.html${NC} - Main website file"
    
    echo -e "\n${GREEN}📊 Data sources:${NC}"
    for json_file in data/*_films_with_english_subs.json; do
        if [[ -f "$json_file" ]]; then
            local count=$(python3 -c "import json; data=json.load(open('$json_file')); print(len(data))" 2>/dev/null || echo "0")
            echo -e "   ${GREEN}• $json_file${NC} - $count films"
        fi
    done
    
    echo -e "\n${BLUE}🌐 Next steps:${NC}"
    echo -e "   ${BLUE}• Open index.html in your web browser${NC}"
    echo -e "   ${BLUE}• The website works without a server${NC}"
    echo -e "   ${BLUE}• All data is embedded in the HTML file${NC}"
}

# Main execution
main() {
    echo -e "${PURPLE}"
    echo "🎬 Films with English Subtitles - Full Pipeline (Reworked)"
    echo "=========================================================="
    echo -e "${NC}"
    
    check_requirements
    
    # Process each scraper individually
    local scrapers=(scrapers/*.py)
    local processed_count=0
    
    for scraper in "${scrapers[@]}"; do
        if [[ -f "$scraper" ]]; then
            if process_scraper "$scraper"; then
                ((processed_count++))
            fi
        fi
    done
    
    if [[ $processed_count -eq 0 ]]; then
        log_error "No scrapers were processed successfully"
        exit 1
    fi
    
    log_success "Processed $processed_count scrapers successfully"
    
    # Normalize datetime data
    normalize_datetime_data
    
    # Generate final static site
    if ! generate_static_site; then
        exit 1
    fi
    
    rm -rf data/backups/
    show_results
}

# Handle command line arguments
case "${1:-}" in
    --help|-h)
        echo "Films with English Subtitles - Full Pipeline"
        echo ""
        echo "Usage: $0 [options]"
        echo ""
        echo "Options:"
        echo "  --help, -h     Show this help message"
        echo "  --skip-tmdb    Skip TMDB enrichment for all scrapers"
        echo "  --skip-translate Skip translation for all scrapers"
        echo "  --tmdb-only    Run only TMDB enrichment on existing JSON files"
        echo ""
        echo "Environment Variables:"
        echo "  TMDB_API_KEY     API key for TMDB enrichment"
        echo "  GEMINI_API_KEY   API key for translation"
        echo ""
        echo "The script will:"
        echo "  1. Find all Python scrapers in scrapers/ directory"
        echo "  2. For each scraper:"
        echo "     a. Run the scraper"
        echo "     b. Enrich with TMDB data"
        echo "     c. Translate JSON fields"
        echo "  3. Generate static HTML with all data"
        echo ""
        echo "TMDB-only mode (--tmdb-only):"
        echo "  1. Find all existing JSON files in data/ directory"
        echo "  2. Run TMDB enrichment on each file"
        echo "  3. Optionally generate static HTML with enriched data"
        echo ""
        exit 0
        ;;
    --skip-tmdb)
        TMDB_API_KEY=""
        main
        ;;
    --skip-translate)
        GEMINI_API_KEY=""
        main
        ;;
    --tmdb-only)
        tmdb_only_mode
        ;;
    "")
        main
        ;;
    *)
        echo "Unknown option: $1"
        echo "Use --help for usage information"
        exit 1
        ;;
esac