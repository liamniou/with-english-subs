#!/usr/bin/env python3
"""
DateTime Normalization Script

This script normalizes datetime formats across all film data sources to a consistent ISO 8601 format.
It also creates simplified display formats for the frontend.
"""

import json
import os
import sys
import re
from datetime import datetime, timedelta
from dateutil import parser as date_parser
import argparse

class DateTimeNormalizer:
    def __init__(self):
        self.swedish_months = {
            'januari': 'January', 'februari': 'February', 'mars': 'March',
            'april': 'April', 'maj': 'May', 'juni': 'June',
            'juli': 'July', 'augusti': 'August', 'september': 'September',
            'oktober': 'October', 'november': 'November', 'december': 'December'
        }
        
        self.swedish_days = {
            'måndag': 'Monday', 'tisdag': 'Tuesday', 'onsdag': 'Wednesday',
            'torsdag': 'Thursday', 'fredag': 'Friday', 'lördag': 'Saturday', 'söndag': 'Sunday',
            'mån': 'Mon', 'tis': 'Tue', 'ons': 'Wed', 'tor': 'Thu', 'fre': 'Fri', 'lör': 'Sat', 'sön': 'Sun'
        }
        
        self.current_year = datetime.now().year

    def translate_swedish_datetime(self, text):
        """Translate Swedish datetime text to English for parsing."""
        if not text:
            return text
            
        text = text.lower()
        
        # Handle "i morgon" (tomorrow)
        if 'i morgon' in text:
            tomorrow = datetime.now() + timedelta(days=1)
            time_match = re.search(r'(\d{1,2}):(\d{2})', text)
            if time_match:
                hour, minute = int(time_match.group(1)), int(time_match.group(2))
                return tomorrow.replace(hour=hour, minute=minute, second=0, microsecond=0)
            return tomorrow
        
        # Translate Swedish month names
        for swedish, english in self.swedish_months.items():
            text = text.replace(swedish, english.lower())
        
        # Translate Swedish day names
        for swedish, english in self.swedish_days.items():
            text = text.replace(swedish, english.lower())
        
        return text

    def parse_cinemateket_format(self, display_text):
        """Parse Cinemateket format: 'Sun 24/8 at 4:00 PM' (Swedish DD/MM format)"""
        if not display_text:
            return None
            
        # Pattern: "Day DD/MM at HH:MM AM/PM"
        pattern = r'(\w+)\s+(\d{1,2})/(\d{1,2})\s+at\s+(\d{1,2}):(\d{2})\s*(AM|PM)'
        match = re.match(pattern, display_text)
        
        if match:
            day_name, day, month, hour, minute, ampm = match.groups()
            hour = int(hour)
            if ampm.upper() == 'PM' and hour != 12:
                hour += 12
            elif ampm.upper() == 'AM' and hour == 12:
                hour = 0
                
            try:
                # Swedish format: DD/MM (day/month), not MM/DD
                dt = datetime(self.current_year, int(month), int(day), hour, int(minute))
                return dt
            except ValueError:
                return None
        
        return None

    def parse_swedish_date_format(self, text):
        """Parse Swedish date formats like 'lör 1/11 kl. 18:30' (DD/MM format)"""
        if not text:
            return None
            
        # Pattern: "dayname DD/MM kl. HH:MM" (Swedish format)
        pattern = r'(\w+)\s+(\d{1,2})/(\d{1,2})\s+kl\.\s+(\d{1,2}):(\d{2})'
        match = re.search(pattern, text)
        
        if match:
            day_name, day, month, hour, minute = match.groups()
            
            try:
                # Swedish format: DD/MM (day/month)
                dt = datetime(self.current_year, int(month), int(day), int(hour), int(minute))
                return dt
            except ValueError:
                return None
        
        return None

    def parse_zita_malformed(self, datetime_str):
        """Fix malformed Zita datetime strings like '2025-08-21T8:15:00'"""
        if not datetime_str:
            return None
            
        # Fix missing leading zero in time
        pattern = r'(\d{4}-\d{2}-\d{2}T)(\d{1}):(\d{2}):(\d{2})'
        match = re.match(pattern, datetime_str)
        if match:
            date_part, hour, minute, second = match.groups()
            fixed_datetime = f"{date_part}{hour.zfill(2)}:{minute}:{second}"
            try:
                return datetime.fromisoformat(fixed_datetime)
            except ValueError:
                return None
        
        return None

    def normalize_datetime(self, showtime):
        """Normalize a single showtime's datetime to ISO format."""
        dt = None
        
        # Try to parse existing datetime field
        if showtime.get('datetime'):
            datetime_str = showtime['datetime']
            
            try:
                # Try standard ISO parsing first
                dt = date_parser.isoparse(datetime_str)
            except:
                # Try fixing malformed Zita format
                dt = self.parse_zita_malformed(datetime_str)
                
        # If datetime field failed, try display_text or original_display_text
        if not dt:
            for text_field in ['original_display_text', 'display_text']:
                if showtime.get(text_field):
                    text = showtime[text_field]
                    
                    # Try Swedish date format first (DD/MM kl. HH:MM)
                    dt = self.parse_swedish_date_format(text)
                    if dt:
                        break
                    
                    # Try Cinemateket format (DD/MM at HH:MM AM/PM)
                    dt = self.parse_cinemateket_format(text)
                    if dt:
                        break
                    
                    # Try Swedish translation and parsing
                    try:
                        translated = self.translate_swedish_datetime(text)
                        if isinstance(translated, datetime):
                            dt = translated
                        else:
                            # Use dayfirst=True to handle DD/MM format
                            dt = date_parser.parse(translated, fuzzy=True, dayfirst=True)
                        break
                    except:
                        continue
        
        # If we successfully parsed a datetime
        if dt:
            # Ensure timezone-naive datetime (convert to local)
            if dt.tzinfo:
                dt = dt.replace(tzinfo=None)
            
            # Create normalized fields
            showtime['normalized_datetime'] = dt.isoformat()
            showtime['normalized_date'] = dt.strftime('%d.%m')
            if dt.year != self.current_year:
                showtime['normalized_date'] = dt.strftime('%d.%m.%Y')
            showtime['normalized_time'] = dt.strftime('%H:%M')
            
            return True
        
        return False

    def normalize_file(self, filepath):
        """Normalize all datetimes in a JSON file."""
        print(f"🔄 Normalizing datetimes in: {filepath}")
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            print(f"❌ Error reading {filepath}: {e}")
            return False
        
        if not isinstance(data, list):
            print(f"❌ Expected list format in {filepath}")
            return False
        
        normalized_count = 0
        total_showtimes = 0
        
        for film in data:
            if 'showtimes' in film and isinstance(film['showtimes'], list):
                for showtime in film['showtimes']:
                    total_showtimes += 1
                    if self.normalize_datetime(showtime):
                        normalized_count += 1
        
        # Save the normalized data
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            print(f"✅ Normalized {normalized_count}/{total_showtimes} showtimes in {os.path.basename(filepath)}")
            return True
            
        except Exception as e:
            print(f"❌ Error writing {filepath}: {e}")
            return False

def main():
    parser = argparse.ArgumentParser(description='Normalize datetime formats in film data')
    parser.add_argument('files', nargs='*', help='JSON files to normalize (default: all *_films_with_english_subs.json)')
    parser.add_argument('--data-dir', default='data', help='Data directory (default: data)')
    
    args = parser.parse_args()
    
    normalizer = DateTimeNormalizer()
    
    # Determine files to process
    if args.files:
        files_to_process = args.files
    else:
        # Find all cinema data files
        import glob
        pattern = os.path.join(args.data_dir, '*_films_with_english_subs.json')
        files_to_process = glob.glob(pattern)
    
    if not files_to_process:
        print("❌ No files found to process")
        return 1
    
    print(f"🕒 Starting datetime normalization for {len(files_to_process)} files...")
    
    success_count = 0
    for filepath in files_to_process:
        if os.path.exists(filepath):
            if normalizer.normalize_file(filepath):
                success_count += 1
        else:
            print(f"❌ File not found: {filepath}")
    
    print(f"\n📊 Normalization complete: {success_count}/{len(files_to_process)} files processed successfully")
    
    if success_count == len(files_to_process):
        print("🎉 All files normalized successfully!")
        return 0
    else:
        print("⚠️  Some files had errors")
        return 1

if __name__ == "__main__":
    sys.exit(main())
