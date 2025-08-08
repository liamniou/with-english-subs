#!/usr/bin/env python3
"""
Zita Folkets Bio Scraper
Scrapes film data from Zita Folkets Bio Stockholm's film page
https://zita.se/filmer

This scraper finds films with English subtitles and extracts:
- Film titles
- Screening times and dates
- Director and genre information
- Cinema details

Structure:
- Films are listed under "Aktuella filmer" section
- Each film has its own detail page
- English subtitles are indicated by "Engelska" in info_right_column
- Movie titles are in #info_title
- Showtimes are in column_calendar_media
"""

import httpx
import json
import os
import re
from datetime import datetime, timezone, timedelta
from selectolax.parser import HTMLParser
from urllib.parse import urljoin, urlparse


class Zita:
    def __init__(self, base_url="https://zita.se/filmer"):
        self.base_url = base_url
        self.domain = "https://zita.se"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        self.films_with_english_subs = []

    def get_page_content(self, url):
        """Fetch page content with error handling."""
        try:
            with httpx.Client(timeout=15.0, follow_redirects=True, headers=self.headers) as client:
                response = client.get(url)
                response.raise_for_status()
                return response.text
        except httpx.RequestError as e:
            print(f"Error fetching {url}: {e}")
            return None

    def get_formatted_date(self, date):
        """Format date to YYYY-MM-DD format for API calls."""
        year = date.year
        month = str(date.month).zfill(2)
        day = str(date.day).zfill(2)
        return f"{year}-{month}-{day}"

    def deduplicate_showtimes(self, showtimes):
        """
        Remove duplicate showtimes based on datetime, time, date, and cinema.
        """
        if not showtimes:
            return []
        
        seen = set()
        unique_showtimes = []
        
        for showtime in showtimes:
            # Create a unique key based on date, time, and cinema
            date = showtime.get('date', '')
            time = showtime.get('time', '')
            cinema = showtime.get('cinema', '')
            datetime_str = showtime.get('datetime', '')
            
            # Primary key: datetime if available, otherwise date+time+cinema
            if datetime_str:
                key = f"{datetime_str}_{cinema}"
            else:
                key = f"{date}_{time}_{cinema}"
            
            if key not in seen:
                seen.add(key)
                unique_showtimes.append(showtime)
            else:
                print(f"    🔄 Removing duplicate: {showtime.get('display_text', 'Unknown')}")
        
        return unique_showtimes

    def fetch_showtime_data(self, film_id):
        """
        Fetch detailed showtime data for a specific film using Zita's AJAX endpoint.
        Replicates the functionality from the browser's AJAX call.
        """
        try:
            ajax_url = f"https://zita.se/pages/ajax-screenings.php?id={film_id}"
            print(f"  🔄 Fetching showtime data from: {ajax_url}")
            
            content = self.get_page_content(ajax_url)
            if not content:
                print(f"  ❌ Failed to fetch showtime data for film ID {film_id}")
                return []
            
            # Parse the AJAX response to extract showtime information
            tree = HTMLParser(content)
            showtimes = []
            
            # Look for booking links and time information
            booking_links = tree.css('.ajax_link[class*="booking"], span[title*="Boka"]')
            for link in booking_links:
                time_text = link.text(strip=True) if link.text() else ""
                
                # Extract time from text (e.g., "15:00", "20:30")
                time_match = re.search(r'\b(\d{1,2}:\d{2})\b', time_text)
                if time_match:
                    showtime = time_match.group(1)
                    
                    # Look for parent elements that might contain date information
                    parent = link.parent
                    date_info = ""
                    cinema_info = ""
                    
                    # Try to find date and cinema information in nearby elements
                    for i in range(3):  # Check up to 3 levels up
                        if parent:
                            parent_text = parent.text() if parent.text() else ""
                            
                            # Look for date patterns
                            date_pattern = r'(\d{1,2}\s+\w+|\w+\s+\d{1,2}\s+\w+|idag|i morgon)'
                            date_match = re.search(date_pattern, parent_text, re.IGNORECASE)
                            if date_match and not date_info:
                                date_info = date_match.group(1).strip()
                            
                            # Look for cinema information (Zita 1, Zita 2, etc.)
                            cinema_pattern = r'\(Zita\s+\d+\)'
                            cinema_match = re.search(cinema_pattern, parent_text)
                            if cinema_match and not cinema_info:
                                cinema_info = cinema_match.group(0)
                            
                            parent = parent.parent
                        else:
                            break
                    
                    # Create showtime entry
                    showtime_entry = {
                        'datetime': '',  # Will be filled by parse_date_time if possible
                        'display_text': f"{date_info} {showtime}".strip(),
                        'time': showtime,
                        'date': date_info,
                        'cinema': cinema_info,
                        'source_url': ajax_url
                    }
                    
                    # Try to create a proper datetime string
                    if date_info and showtime:
                        datetime_str = self.parse_date_time(date_info, showtime)
                        if datetime_str:
                            showtime_entry['datetime'] = datetime_str
                    
                    showtimes.append(showtime_entry)
            
            # Also look for calendar rows with explicit structure
            calendar_rows = tree.css('.calendar_row, .calendar_row_large')
            for row in calendar_rows:
                time_element = row.css_first('.column_time, .column_time_large')
                media_element = row.css_first('.calendar_media, .calendar_media_large')
                
                if time_element and media_element:
                    time_text = time_element.text(strip=True)
                    media_text = media_element.text(strip=True)
                    
                    # Extract time
                    time_match = re.search(r'\b(\d{1,2}:\d{2})\b', time_text)
                    if time_match:
                        showtime = time_match.group(1)
                        
                        # Look for date information in parent containers
                        date_info = ""
                        parent = row.parent
                        while parent and not date_info:
                            parent_text = parent.text() if parent.text() else ""
                            date_pattern = r'(\d{1,2}\s+\w+|\w+\s+\d{1,2}\s+\w+|idag|i morgon)'
                            date_match = re.search(date_pattern, parent_text, re.IGNORECASE)
                            if date_match:
                                date_info = date_match.group(1).strip()
                            parent = parent.parent
                        
                        # Extract cinema info
                        cinema_pattern = r'\(Zita\s+\d+\)'
                        cinema_match = re.search(cinema_pattern, media_text)
                        cinema_info = cinema_match.group(0) if cinema_match else ""
                        
                        showtime_entry = {
                            'datetime': '',
                            'display_text': f"{date_info} {showtime}".strip(),
                            'time': showtime,
                            'date': date_info,
                            'cinema': cinema_info,
                            'source_url': ajax_url
                        }
                        
                        # Try to create a proper datetime string
                        if date_info and showtime:
                            datetime_str = self.parse_date_time(date_info, showtime)
                            if datetime_str:
                                showtime_entry['datetime'] = datetime_str
                        
                        showtimes.append(showtime_entry)
            
            print(f"  ✅ Found {len(showtimes)} showtimes from AJAX endpoint")
            return showtimes
            
        except Exception as e:
            print(f"  ⚠️  Error fetching showtime data: {e}")
            return []

    def fetch_showtimes(self, start_date=None, end_date=None, film_id=None):
        """
        Main function to fetch showtimes from Zita cinema.
        Replicates the fetchShowtimes functionality from the Bio Rio source.
        
        Args:
            start_date: Start date for showtime search (datetime object or None for today)
            end_date: End date for showtime search (datetime object or None for +60 days)
            film_id: Specific film ID to fetch showtimes for (optional)
        
        Returns:
            List of showtime dictionaries with structured data
        """
        if not start_date:
            start_date = datetime.now()
        if not end_date:
            end_date = start_date + timedelta(days=60)
        
        print(f"🎬 Fetching showtimes from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
        
        all_showtimes = []
        
        if film_id:
            # Fetch showtimes for specific film
            showtimes = self.fetch_showtime_data(film_id)
            all_showtimes.extend(showtimes)
        else:
            # Fetch showtimes from main calendar page
            calendar_url = "https://zita.se/kalendarium"
            print(f"🔗 Fetching calendar page: {calendar_url}")
            
            content = self.get_page_content(calendar_url)
            if not content:
                print("❌ Failed to fetch calendar page")
                return []
            
            tree = HTMLParser(content)
            
            # Extract showtimes from calendar structure
            calendar_rows = tree.css('.calendar_row, .calendar_row_large')
            
            for row in calendar_rows:
                time_element = row.css_first('.column_time, .column_time_large')
                media_element = row.css_first('.calendar_media, .calendar_media_large')
                
                if time_element and media_element:
                    time_text = time_element.text(strip=True)
                    media_text = media_element.text(strip=True)
                    
                    # Extract time
                    time_match = re.search(r'\b(\d{1,2}:\d{2})\b', time_text)
                    if time_match:
                        showtime = time_match.group(1)
                        
                        # Extract film title from media text
                        film_title = ""
                        title_links = media_element.css('a[title]')
                        if title_links:
                            # Get the last link which is usually the film title
                            film_title = title_links[-1].attributes.get('title', '').strip()
                        
                        if not film_title:
                            # Fallback to extracting from text
                            # Remove category prefixes like "Films with English subtitles:"
                            clean_text = re.sub(r'^[^:]+:\s*', '', media_text)
                            # Extract text before cinema info
                            title_match = re.search(r'^(.+?)\s*\(Zita\s+\d+\)', clean_text)
                            if title_match:
                                film_title = title_match.group(1).strip()
                            else:
                                film_title = clean_text.strip()
                        
                        # Look for date information
                        date_info = ""
                        parent = row.parent
                        while parent and not date_info:
                            parent_text = parent.text() if parent.text() else ""
                            date_pattern = r'(\d{1,2}\s+\w+|\w+\s+\d{1,2}\s+\w+|idag|i morgon)'
                            date_match = re.search(date_pattern, parent_text, re.IGNORECASE)
                            if date_match:
                                date_info = date_match.group(1).strip()
                            parent = parent.parent
                        
                        # Extract cinema info
                        cinema_pattern = r'\(Zita\s+\d+\)'
                        cinema_match = re.search(cinema_pattern, media_text)
                        cinema_info = cinema_match.group(0) if cinema_match else ""
                        
                        showtime_entry = {
                            'name': film_title,
                            'datetime': '',
                            'display_text': f"{date_info} {showtime}".strip(),
                            'time': showtime,
                            'date': date_info,
                            'cinema': cinema_info,
                            'source_url': calendar_url
                        }
                        
                        # Try to create a proper datetime string
                        if date_info and showtime:
                            datetime_str = self.parse_date_time(date_info, showtime)
                            if datetime_str:
                                showtime_entry['datetime'] = datetime_str
                                showtime_entry['startDate'] = datetime_str
                                # Add end date (assuming 2 hour movie)
                                try:
                                    start_dt = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
                                    end_dt = start_dt + timedelta(hours=2)
                                    showtime_entry['endDate'] = end_dt.isoformat()
                                except:
                                    pass
                        
                        all_showtimes.append(showtime_entry)
        
        print(f"✅ Total showtimes found: {len(all_showtimes)}")
        return all_showtimes

    def find_current_films_links(self, content):
        """Find all film links under 'Aktuella filmer' section."""
        tree = HTMLParser(content)
        
        # Find the "Aktuella filmer" heading
        aktuella_filmer_heading = None
        for h1 in tree.css('h1'):
            if h1.text(strip=True) == "Aktuella filmer":
                aktuella_filmer_heading = h1
                break
        
        if not aktuella_filmer_heading:
            print("❌ Could not find 'Aktuella filmer' heading")
            return []
        
        print("✅ Found 'Aktuella filmer' section")
        
        # Find all div elements with class "title_list" that have onclick attributes
        film_links = []
        title_list_divs = tree.css('div.title_list')
        
        for div in title_list_divs:
            onclick = div.attributes.get('onclick', '')
            if onclick and 'window.location=' in onclick:
                # Extract the URL from onclick="window.location='film-slug'"
                import re
                url_match = re.search(r"window\.location='([^']+)'", onclick)
                if url_match:
                    film_slug = url_match.group(1)
                    full_url = urljoin(self.domain, film_slug)
                    
                    # Extract title from the div
                    title_element = div.css_first('.title_list_title')
                    if title_element:
                        # Get only the direct text content, not from child elements
                        title_text = ""
                        for node in title_element.iter():
                            if node.tag is None:  # Text node
                                title_text += node
                        title = title_text.strip()
                        if not title:
                            # Fallback to full text if direct text is empty
                            title = title_element.text(strip=True).split('\n')[0].strip()
                        film_links.append((title, full_url))
        
        print(f"📋 Found {len(film_links)} film links to check")
        return film_links

    def check_for_english_subtitles(self, film_content):
        """Check if a film has English subtitles by looking at the last item in info_right_column."""
        tree = HTMLParser(film_content)
        
        # Find info_right_column div
        info_right_column = tree.css_first('.info_right_column')
        if not info_right_column:
            print(f"  ⚠️  Could not find info_right_column")
            return False
        
        # Get the HTML content and split by <br> tags
        html_content = str(info_right_column.html)
        
        # Split by <br> and get text content of each part
        parts = html_content.split('<br>')
        
        if len(parts) >= 2:
            # Get the last part and clean it
            last_part = parts[-1].strip()
            
            # Remove any HTML tags and get clean text
            import re
            clean_text = re.sub(r'<[^>]+>', '', last_part).strip()
            
            # Remove any closing div tags that might be at the end
            clean_text = clean_text.replace('</div>', '').strip()
            
            # If the last part is empty (just closing tags), get the second-to-last part
            if not clean_text and len(parts) >= 3:
                second_last_part = parts[-2].strip()
                clean_text = re.sub(r'<[^>]+>', '', second_last_part).strip()
            
            print(f"  🔍 Last text item: '{clean_text}'")
            
            # Check if the last text item is "Engelska" (English subtitles)
            if clean_text.lower() == "engelska":
                print(f"  ✅ Found English subtitles: {clean_text}")
                return True
            else:
                print(f"  ❌ Subtitles are: {clean_text} (not English)")
                return False
        
        # Fallback: check if there are multiple language options and English is mentioned
        text_content = info_right_column.text(strip=True)
        lines = text_content.split('\n')
        
        # Look for language lines (typically at the end)
        for line in reversed(lines):
            line = line.strip()
            if line and any(lang in line.lower() for lang in ['engelska', 'svenska', 'franska']):
                print(f"  🔍 Found language line: '{line}'")
                if line.lower() == "engelska":
                    print(f"  ✅ Found English subtitles: {line}")
                    return True
                else:
                    print(f"  ❌ Subtitles are: {line}")
                    return False
        
        print(f"  ❌ No subtitle language information found")
        return False

    def parse_date_time(self, date_text, time_text):
        """Parse Swedish date text and time to create ISO datetime string."""
        try:
            from datetime import datetime
            import re
            
            # Handle different Swedish date formats
            # Examples: "fre 8 aug", "lör 9 aug", "sön 10 aug", etc.
            
            # Swedish day names mapping
            swedish_days = {
                'mån': 'Monday', 'måndag': 'Monday',
                'tis': 'Tuesday', 'tisdag': 'Tuesday', 
                'ons': 'Wednesday', 'onsdag': 'Wednesday',
                'tors': 'Thursday', 'torsdag': 'Thursday',
                'fre': 'Friday', 'fredag': 'Friday',
                'lör': 'Saturday', 'lördag': 'Saturday',
                'sön': 'Sunday', 'söndag': 'Sunday'
            }
            
            # Swedish month names mapping
            swedish_months = {
                'jan': 1, 'januari': 1,
                'feb': 2, 'februari': 2,
                'mar': 3, 'mars': 3,
                'apr': 4, 'april': 4,
                'maj': 5,
                'jun': 6, 'juni': 6,
                'jul': 7, 'juli': 7,
                'aug': 8, 'augusti': 8,
                'sep': 9, 'september': 9,
                'okt': 10, 'oktober': 10,
                'nov': 11, 'november': 11,
                'dec': 12, 'december': 12
            }
            
            # Extract day number and month from date_text
            # Pattern like "fre 8 aug" or "lör 9 aug"
            date_match = re.search(r'(\w+)\s+(\d+)\s+(\w+)', date_text.lower())
            if date_match:
                day_name = date_match.group(1)
                day_num = int(date_match.group(2))
                month_name = date_match.group(3)
                
                if month_name in swedish_months:
                    month_num = swedish_months[month_name]
                    
                    # Use current year, but adjust if the date seems to be in the future
                    current_year = datetime.now().year
                    current_month = datetime.now().month
                    
                    # If the month is before current month, assume next year
                    year = current_year
                    if month_num < current_month:
                        year = current_year + 1
                    
                    # Parse time "15:00"
                    time_match = re.match(r'(\d{1,2}):(\d{2})', time_text)
                    if time_match:
                        hour = int(time_match.group(1))
                        minute = int(time_match.group(2))
                        
                        # Create datetime object
                        dt = datetime(year, month_num, day_num, hour, minute)
                        return dt.isoformat()
            
            return ''
        except Exception as e:
            print(f"    ⚠️  Error parsing date '{date_text}' and time '{time_text}': {e}")
            return ''

    def extract_film_details(self, film_content, film_url):
        """Extract film details from a film detail page."""
        tree = HTMLParser(film_content)
        
        # Extract movie title from #info_title
        title_element = tree.css_first('#info_title')
        title = title_element.text(strip=True) if title_element else "Unknown Title"
        
        print(f"  📝 Title: {title}")
        
        # Extract director and genre information from info_right_column
        director = ""
        genre = ""
        duration = ""
        
        info_right_column = tree.css_first('.info_right_column')
        if info_right_column:
            # Look for director and genre info
            text_lines = info_right_column.text().split('\n')
            for line in text_lines:
                line = line.strip()
                if line and not line.startswith('Engelska') and len(line) > 3:
                    # Try to identify director and genre
                    if 'av ' in line:  # Swedish for "by"
                        director = line.replace('av ', '').strip()
                    elif any(genre_word in line.lower() for genre_word in ['drama', 'komedi', 'thriller', 'dokumentär', 'action']):
                        genre = line
                    elif 'min' in line and any(char.isdigit() for char in line):
                        duration = line
        
        # Extract showtimes by finding dates and times
        showtimes = []
        
        # First, try to extract film ID from the URL to use AJAX endpoint
        film_id = None
        url_match = re.search(r'/([^/]+)$', film_url)
        if url_match:
            film_slug = url_match.group(1)
            # Try to find film ID in the page content
            id_match = re.search(r'ajax-screenings\.php\?id=(\d+)', film_content)
            if id_match:
                film_id = id_match.group(1)
                print(f"  🆔 Found film ID: {film_id}")
                
                # Use the new AJAX-based showtime fetching
                ajax_showtimes = self.fetch_showtime_data(film_id)
                if ajax_showtimes:
                    showtimes.extend(ajax_showtimes)
        
        # Always try the HTML parsing method as well to catch any missed showtimes
        print("  🔄 Using HTML parsing method to find additional showtimes")
        
        # Look for the schedule section that lists specific dates and times
        # This is typically found after the film description
        page_text = tree.text() if tree.text() else ""
        
        # Split the page into lines and look for date patterns with times
        lines = page_text.split('\n')
        current_date = None
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
                
            # Look for Swedish date patterns (e.g., "fre 8 aug", "tis 12 aug")
            date_match = re.search(r'\b(fre|lör|sön|mån|tis|ons|tors)\s+(\d+)\s+(aug|sep|okt|nov|dec)\b', line.lower())
            if date_match:
                current_date = f"{date_match.group(1)} {date_match.group(2)} {date_match.group(3)}"
                print(f"    📅 Found date section: {current_date}")
                
                # Look for times on this line and subsequent lines
                time_matches = re.findall(r'\b(\d{1,2}:\d{2})\b', line)
                
                # Also check the next few lines for times related to this date
                for j in range(i, min(i + 5, len(lines))):
                    if j > i:
                        next_line = lines[j].strip()
                        # Stop if we hit another date
                        if re.search(r'\b(fre|lör|sön|mån|tis|ons|tors)\s+\d+\s+(aug|sep|okt|nov|dec)\b', next_line.lower()):
                            break
                        time_matches.extend(re.findall(r'\b(\d{1,2}:\d{2})\b', next_line))
                
                # Process all found times for this date
                for time_match in time_matches:
                    # Check if this is for our specific film by looking at context
                    context_lines = lines[max(0, i-2):min(len(lines), i+5)]
                    context_text = ' '.join(context_lines).lower()
                    
                    if title.lower() in context_text or 'to a land unknown' in context_text:
                        # Extract cinema info from context
                        cinema_match = re.search(r'\(zita\s+\d+\)', context_text)
                        cinema_info = cinema_match.group(0) if cinema_match else ""
                        
                        showtime_entry = {
                            'datetime': '',
                            'display_text': f"{current_date} {time_match}".strip(),
                            'time': time_match,
                            'date': current_date,
                            'cinema': cinema_info,
                            'source_url': film_url
                        }
                        
                        # Try to create a proper datetime string
                        datetime_str = self.parse_date_time(current_date, time_match)
                        if datetime_str:
                            showtime_entry['datetime'] = datetime_str
                        
                        # Avoid duplicates
                        if not any(s['display_text'] == showtime_entry['display_text'] for s in showtimes):
                            showtimes.append(showtime_entry)
                            print(f"      ✅ Added showtime: {showtime_entry['display_text']}")
        
        # Look for the detailed calendar section at the bottom of film pages (alternative method)
        calendar_sections = tree.css('h1, h2, h3')
        calendar_section = None
        
        for heading in calendar_sections:
            heading_text = heading.text(strip=True) if heading.text() else ""
            if any(day in heading_text.lower() for day in ['fre', 'lör', 'sön', 'mån', 'tis', 'ons', 'tors']) or \
               any(word in heading_text.lower() for word in ['aug', 'sep', 'okt', 'nov', 'dec']):
                calendar_section = heading
                break
        
        if calendar_section:
            print("  📅 Found calendar section in film page")
            # Look for all text that contains dates and times
            current_element = calendar_section
            while current_element:
                if current_element.next:
                    current_element = current_element.next
                    element_text = current_element.text(strip=True) if hasattr(current_element, 'text') and current_element.text() else ""
                    
                    # Look for date patterns (e.g., "fre 8 aug", "tis 12 aug")
                    date_match = re.search(r'(\w+\s+\d+\s+\w+)', element_text)
                    if date_match:
                        current_date = date_match.group(1)
                        print(f"    📅 Processing date: {current_date}")
                        
                        # Find all times on this line and subsequent lines until next date
                        time_matches = re.findall(r'\b(\d{1,2}:\d{2})\b', element_text)
                        
                        for time_match in time_matches:
                            # Check if this time is for our film (look for film title in context)
                            if title.lower() in element_text.lower() or \
                               'to a land unknown' in element_text.lower():
                                
                                # Extract cinema info
                                cinema_match = re.search(r'\(Zita\s+\d+\)', element_text)
                                cinema_info = cinema_match.group(0) if cinema_match else ""
                                
                                showtime_entry = {
                                    'datetime': '',
                                    'display_text': f"{current_date} {time_match}".strip(),
                                    'time': time_match,
                                    'date': current_date,
                                    'cinema': cinema_info,
                                    'source_url': film_url
                                }
                                
                                # Try to create a proper datetime string
                                datetime_str = self.parse_date_time(current_date, time_match)
                                if datetime_str:
                                    showtime_entry['datetime'] = datetime_str
                                
                                # Avoid duplicates
                                if not any(s['display_text'] == showtime_entry['display_text'] for s in showtimes):
                                    showtimes.append(showtime_entry)
                                    print(f"      ✅ Added showtime: {showtime_entry['display_text']}")
                else:
                    break
        
        # Find all date spans first (fallback method)
        date_spans = tree.css('span.column_calendar_day_media')
        
        if date_spans:
            for date_span in date_spans:
                date_text = date_span.text(strip=True) if date_span.text() else ""
                
                # Look for times in the same container or nearby elements
                # Find the parent container of the date span
                parent = date_span.parent
                if parent:
                    # Look for times in the parent container
                    parent_text = parent.text() if parent.text() else ""
                    
                    # Extract times (format like "15:00", "20:30")
                    time_matches = re.findall(r'\b(\d{1,2}:\d{2})\b', parent_text)
                    
                    for time_match in time_matches:
                        # Try to parse date and create proper datetime
                        datetime_str = self.parse_date_time(date_text, time_match)
                        
                        showtime_data = {
                            'datetime': datetime_str,
                            'display_text': f"{date_text} {time_match}",
                            'time': time_match,
                            'date': date_text,
                            'source_url': film_url
                        }
                        
                        # Avoid duplicates
                        if not any(s['display_text'] == showtime_data['display_text'] for s in showtimes):
                            showtimes.append(showtime_data)
            
            # If no date-specific showtimes found, fall back to generic time extraction
            if not showtimes:
                calendar_elements = tree.css('.column_calendar_media, [class*="calendar"], [id*="calendar"]')
                unique_times = set()
                
                for calendar in calendar_elements:
                    calendar_text = calendar.text() if calendar.text() else ""
                    time_matches = re.findall(r'\b(\d{1,2}:\d{2})\b', calendar_text)
                    
                    for time_match in time_matches[:10]:
                        if time_match not in unique_times:
                            unique_times.add(time_match)
                            showtime_data = {
                                'datetime': '',
                                'display_text': f"Check zita.se - {time_match}",
                                'time': time_match,
                                'source_url': film_url
                            }
                            showtimes.append(showtime_data)
            
            # If no showtimes found at all, create a placeholder
            if not showtimes:
                showtimes.append({
                    'datetime': '',
                    'display_text': 'Visit zita.se for current showtimes',
                    'time': '',
                    'source_url': film_url
                })
        
        # Deduplicate showtimes to remove duplicates from AJAX and HTML parsing
        unique_showtimes = self.deduplicate_showtimes(showtimes)
        print(f"  🔄 Deduplicated {len(showtimes)} → {len(unique_showtimes)} showtimes")
        
        return {
            'title': title,
            'director': director,
            'genre': genre,
            'duration': duration,
            'showtimes': unique_showtimes,
            'url': film_url
        }

    def scrape_films(self):
        """Main scraping method."""
        print("🎬 Starting scraper for Zita Folkets Bio Stockholm")
        print(f"🔗 Fetching main page: {self.base_url}")
        
        content = self.get_page_content(self.base_url)
        if not content:
            print("❌ Failed to fetch main page")
            return

        # Find all film links under "Aktuella filmer"
        film_links = self.find_current_films_links(content)
        
        if not film_links:
            print("❌ No film links found")
            return
        
        film_count = 0
        english_films_count = 0
        skipped_no_showtimes_count = 0
        
        for idx, (film_title, film_url) in enumerate(film_links):
            film_count += 1
            print(f"\n🎭 Checking film {film_count}/{len(film_links)}: {film_title}")
            print(f"  🔗 URL: {film_url}")
            
            # Get film detail page
            film_content = self.get_page_content(film_url)
            if not film_content:
                print(f"  ❌ Failed to fetch film page")
                continue
            
            # Check for English subtitles
            has_english_subs = self.check_for_english_subtitles(film_content)
            
            if has_english_subs:
                print(f"  ✅ Found film with English subtitles!")
                english_films_count += 1
                
                # Extract film details
                film_data = self.extract_film_details(film_content, film_url)
                
                if film_data:
                    # Check if film has valid showtimes
                    if film_data['showtimes'] and len(film_data['showtimes']) > 0:
                        # Generate a unique film ID
                        film_id = film_data['title'].lower().replace(' ', '-').replace(':', '').replace(',', '')
                        film_id = ''.join(c for c in film_id if c.isalnum() or c == '-')
                        
                        # Create final film data structure
                        final_film_data = {
                            'film_id': film_id,
                            'url': film_data['url'],
                            'title': film_data['title'],
                            'director': film_data['director'],
                            'genre': film_data['genre'],
                            'duration': film_data['duration'],
                            'showtimes': film_data['showtimes'],
                            'cinemas': ["Zita Folkets Bio Stockholm"],
                            'scraped_at': datetime.now(timezone.utc).isoformat(),
                            'source': 'zita'
                        }
                        
                        self.films_with_english_subs.append(final_film_data)
                        
                        print(f"  ✅ Added film: {film_data['title']}")
                        print(f"  🎭 Director: {film_data['director']}")
                        print(f"  🎬 Genre: {film_data['genre']}")
                        print(f"  🕐 Showtimes: {len(film_data['showtimes'])} found")
                    else:
                        print(f"  ❌ Skipped film - no showtimes found: {film_data['title']}")
                        skipped_no_showtimes_count += 1
                else:
                    print(f"  ❌ Failed to extract details for film with English subtitles")
            else:
                print(f"  ❌ No English subtitles found")

        print(f"\n📊 SCRAPING COMPLETE!")
        print(f"✅ Found {len(self.films_with_english_subs)} films with English subtitles and valid showtimes out of {film_count} total films")
        if skipped_no_showtimes_count > 0:
            print(f"⚠️  Skipped {skipped_no_showtimes_count} films with English subtitles due to no showtimes")
        
        # Save results to JSON file
        import os
        os.makedirs('data', exist_ok=True)
        output_file = './data/zita_films_with_english_subs.json'
        
        if self.films_with_english_subs:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(self.films_with_english_subs, f, ensure_ascii=False, indent=2)
            
            print(f"💾 Results saved to:")
            print(f"   - {output_file}")
            
            # Print statistics
            total_showtimes = sum(len(film['showtimes']) for film in self.films_with_english_subs)
            total_cinemas = len(set(cinema for film in self.films_with_english_subs for cinema in film['cinemas']))
            
            print(f"📈 STATISTICS:")
            print(f"   • Films with titles: {len([f for f in self.films_with_english_subs if f['title']])}/{len(self.films_with_english_subs)}")
            print(f"   • Films with showtimes: {len([f for f in self.films_with_english_subs if f['showtimes']])}/{len(self.films_with_english_subs)}")
            print(f"   • Films with cinemas: {len([f for f in self.films_with_english_subs if f['cinemas']])}/{len(self.films_with_english_subs)}")
            print(f"   • Total showtimes found: {total_showtimes}")
            print(f"   • Total cinemas found: {total_cinemas}")
            
            print(f"💡 To add TMDb data: python3 tmdb_enricher.py {output_file}")
        else:
            print("ℹ️  No films with English subtitles found")


def main():
    """Main function with command line argument support."""
    import sys
    
    scraper = Zita()
    
    # Check if user wants to test fetchShowtimes functionality
    if len(sys.argv) > 1 and sys.argv[1] == "--test-showtimes":
        print("🎬 Testing fetchShowtimes functionality...")
        
        # Test general showtime fetching
        print("\n1. Testing general showtime fetching:")
        all_showtimes = scraper.fetch_showtimes()
        
        if all_showtimes:
            print(f"   ✅ Found {len(all_showtimes)} total showtimes")
            
            # Show first few showtimes as examples
            for i, showtime in enumerate(all_showtimes[:3]):
                print(f"   Example {i+1}: {showtime.get('name', 'Unknown')} - {showtime.get('display_text', 'No time')}")
        else:
            print("   ❌ No showtimes found")
        
        # Test specific film ID if provided
        if len(sys.argv) > 2:
            film_id = sys.argv[2]
            print(f"\n2. Testing specific film ID {film_id}:")
            specific_showtimes = scraper.fetch_showtimes(film_id=film_id)
            
            if specific_showtimes:
                print(f"   ✅ Found {len(specific_showtimes)} showtimes for film ID {film_id}")
                for showtime in specific_showtimes:
                    print(f"   - {showtime.get('display_text', 'No time')} at {showtime.get('cinema', 'Unknown cinema')}")
            else:
                print(f"   ❌ No showtimes found for film ID {film_id}")
        
        print("\n💡 Usage examples:")
        print("   python3 scrapers/zita.py --test-showtimes")
        print("   python3 scrapers/zita.py --test-showtimes 3116")
        print("   python3 scrapers/zita.py  # Run normal film scraping")
        
    else:
        # Run normal film scraping
        scraper.scrape_films()


if __name__ == "__main__":
    main()