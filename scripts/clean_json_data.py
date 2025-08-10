#!/usr/bin/env python3
"""
Clean JSON data files by removing unnecessary fields that contain large HTML content.
"""

import json
import os
from pathlib import Path

def clean_film_data(film_data):
    """Remove unnecessary fields from film data."""
    # Fields to remove that contain large HTML content or are not needed for display
    fields_to_remove = ['original_details', 'raw_html', 'page_content']
    
    for field in fields_to_remove:
        if field in film_data:
            del film_data[field]
    
    return film_data

def clean_json_file(file_path):
    """Clean a single JSON file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if isinstance(data, list):
            # Clean each film in the list
            cleaned_data = [clean_film_data(film) for film in data]
        elif isinstance(data, dict):
            # Clean single film object
            cleaned_data = clean_film_data(data)
        else:
            print(f"⚠️ Unexpected data format in {file_path}")
            return False
        
        # Write back the cleaned data
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(cleaned_data, f, ensure_ascii=False, indent=2)
        
        print(f"✅ Cleaned {file_path}")
        return True
        
    except Exception as e:
        print(f"❌ Error cleaning {file_path}: {e}")
        return False

def main():
    """Clean all JSON files in the data directory."""
    print("🧹 Cleaning JSON data files...")
    
    data_dir = Path('data')
    if not data_dir.exists():
        print("❌ Data directory not found!")
        return
    
    # Find all JSON files
    json_files = list(data_dir.glob('*.json'))
    
    if not json_files:
        print("⚠️ No JSON files found in data directory")
        return
    
    cleaned_count = 0
    for json_file in json_files:
        if clean_json_file(json_file):
            cleaned_count += 1
    
    print(f"\n🎉 Cleaned {cleaned_count}/{len(json_files)} JSON files")
    
    # Show file sizes after cleaning
    print("\n📏 File sizes after cleaning:")
    for json_file in json_files:
        size_mb = json_file.stat().st_size / (1024 * 1024)
        print(f"  • {json_file.name}: {size_mb:.2f} MB")

if __name__ == '__main__':
    main()