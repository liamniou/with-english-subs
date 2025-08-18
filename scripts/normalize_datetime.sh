#!/bin/bash

# =============================================================================
# DateTime Normalization Shell Script
# =============================================================================
# Wrapper script for normalizing datetime formats across all film data sources
# =============================================================================

set -e

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

# Check if Python script exists
check_requirements() {
    local script_path="$(dirname "$0")/normalize_datetime.py"
    
    if [[ ! -f "$script_path" ]]; then
        log_error "normalize_datetime.py not found at: $script_path"
        exit 1
    fi
    
    # Check if python3 is available
    if ! command -v python3 &> /dev/null; then
        log_error "python3 is not installed"
        exit 1
    fi
    
    # Check if required Python packages are available
    if ! python3 -c "import dateutil" 2>/dev/null; then
        log_warning "python-dateutil not found. Installing..."
        pip3 install python-dateutil
    fi
    
    log_success "Requirements check passed"
}

# Main normalization function
normalize_datetimes() {
    local data_dir="${1:-data}"
    local script_path="$(dirname "$0")/normalize_datetime.py"
    
    log_header "DATETIME NORMALIZATION"
    
    log_info "Data directory: $data_dir"
    log_info "Looking for *_films_with_english_subs.json files..."
    
    # Find JSON files
    local json_files=($(find "$data_dir" -name "*_films_with_english_subs.json" 2>/dev/null || true))
    
    if [[ ${#json_files[@]} -eq 0 ]]; then
        log_error "No film data files found in $data_dir"
        exit 1
    fi
    
    log_info "Found ${#json_files[@]} files to process:"
    for file in "${json_files[@]}"; do
        echo "  • $(basename "$file")"
    done
    
    echo
    
    # Create backup directory
    local backup_dir="$data_dir/backups/$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$backup_dir"
    log_info "Creating backups in: $backup_dir"
    
    # Backup original files
    for file in "${json_files[@]}"; do
        cp "$file" "$backup_dir/"
    done
    log_success "Backups created"
    
    # Run normalization
    echo
    log_info "Starting datetime normalization..."
    
    if python3 "$script_path" --data-dir "$data_dir"; then
        log_success "DateTime normalization completed successfully!"
        
        # Show summary
        echo
        log_info "Summary of changes:"
        for file in "${json_files[@]}"; do
            local basename=$(basename "$file")
            local backup_file="$backup_dir/$basename"
            
            # Count normalized entries (rough estimate)
            local before_count=$(grep -c "datetime.*:" "$backup_file" 2>/dev/null || echo "0")
            local after_count=$(grep -c "normalized_datetime" "$file" 2>/dev/null || echo "0")
            
            echo "  • $basename: $after_count normalized showtimes"
        done
        
        echo
        log_info "Original files backed up to: $backup_dir"
        log_success "You can now run the static generator with normalized data"
        
    else
        log_error "DateTime normalization failed"
        
        # Restore backups
        log_info "Restoring original files..."
        for file in "${json_files[@]}"; do
            local basename=$(basename "$file")
            cp "$backup_dir/$basename" "$file"
        done
        log_info "Original files restored"
        
        exit 1
    fi
}

# Show usage
show_usage() {
    echo "DateTime Normalization Script"
    echo ""
    echo "Usage: $0 [options] [data_directory]"
    echo ""
    echo "Options:"
    echo "  --help, -h          Show this help message"
    echo "  --check             Only check requirements"
    echo ""
    echo "Arguments:"
    echo "  data_directory      Directory containing JSON files (default: data)"
    echo ""
    echo "This script normalizes datetime formats across all film data sources"
    echo "to a consistent ISO 8601 format with simplified display formats."
    echo ""
    echo "Examples:"
    echo "  $0                  # Normalize files in ./data/"
    echo "  $0 /path/to/data    # Normalize files in custom directory"
    echo "  $0 --check          # Check if requirements are met"
}

# Handle command line arguments
case "${1:-}" in
    --help|-h)
        show_usage
        exit 0
        ;;
    --check)
        check_requirements
        log_success "All requirements are met"
        exit 0
        ;;
    *)
        check_requirements
        normalize_datetimes "$1"
        ;;
esac
