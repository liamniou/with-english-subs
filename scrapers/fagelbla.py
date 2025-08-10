#!/usr/bin/env python3
"""
Bio Fågel Blå Scraper
Scrapes film data from Bio Fågel Blå Stockholm's program page
https://biofagelbla.se/program/

This scraper finds films with English subtitles and extracts:
- Film titles
- Screening times and dates
- Director and duration information
- Cinema details

Structure:
- Films are grouped by date in sections with data-date-range attributes
- Each film is in an <article> element
- English subtitles are indicated by "Text: Engelska" span
- Movie titles are in h3 elements with time elements for showtimes
- Date headers are in h3 elements like "Måndag, 11th Augusti"
"""

import httpx
import json
import os
from datetime import datetime, timezone
from selectolax.parser import HTMLParser
from urllib.parse import urljoin, urlparse, parse_qs


class FagelBla:
    def __init__(self, base_url="https://biofagelbla.se/program/"):
        self.base_url = base_url
        self.domain = "https://biofagelbla.se"
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

    def check_for_english_subtitles(self, article_element):
        """Check if an article contains English subtitles."""
        # Look for "Text: Engelska" in span elements
        subtitle_spans = article_element.css('span')
        for span in subtitle_spans:
            span_text = span.text(strip=True) if span.text() else ""
            if "Text: Engelska" in span_text:
                print(f"  ✅ Found English subtitles: {span_text}")
                return True
        return False

    def extract_film_details(self, article_element, current_date_section):
        """Extract film details from an article element."""
        try:
            # Extract movie title and time from h3 element
            title_element = article_element.css_first('h3.text-sm.font-bold.uppercase.font-heading')
            if not title_element:
                print(f"  ⚠️  Could not find title element")
                return None

            # Movie title is the text content, but we need to exclude the time element
            time_element = title_element.css_first('time')
            if time_element:
                # Get title by removing the time element text
                full_text = title_element.text(strip=True)
                time_text = time_element.text(strip=True)
                title = full_text.replace(time_text, "").strip()
                
                # Extract time and datetime attribute
                showtime_text = time_text
                datetime_attr = time_element.attributes.get('datetime', '')
            else:
                title = title_element.text(strip=True)
                showtime_text = ''
                datetime_attr = ''

            if not title:
                print(f"  ⚠️  Could not extract title")
                return None

            print(f"  📝 Title: {title}")
            print(f"  🕐 Time: {showtime_text}")

            # Extract additional film info (director, duration, language)
            director = ""
            duration = ""
            language = ""
            
            info_spans = article_element.css('span.leading-none')
            for span in info_spans:
                span_text = span.text(strip=True) if span.text() else ""
                if "mins" in span_text:
                    duration = span_text
                elif "Språk:" in span_text:
                    language = span_text.replace("Språk:", "").strip()
                elif len(span_text) > 3 and not any(keyword in span_text.lower() 
                                                   for keyword in ['text:', 'språk:', 'mins', 'h ']):
                    # Likely the director name
                    if not director:
                        director = span_text

            # Extract ticket URL and showtime ID
            ticket_link = article_element.css_first('a.anchor-link')
            ticket_url = ""
            showtime_id = ""
            
            if ticket_link:
                href = ticket_link.attributes.get('href', '')
                if href:
                    ticket_url = urljoin(self.domain, href)
            
            # Look for showtime ID in various possible locations
            # Debug: Print all attributes to help identify showtime ID patterns
            print(f"  🔍 Article attributes: {article_element.attributes}")
            if time_element:
                print(f"  🔍 Time element attributes: {time_element.attributes}")
            if ticket_link:
                print(f"  🔍 Ticket link attributes: {ticket_link.attributes}")
            
            # Check for data attributes that might contain showtime ID
            showtime_id_sources = [
                article_element.attributes.get('data-showtime-id'),
                article_element.attributes.get('data-showtime'),
                article_element.attributes.get('data-id'),
                article_element.attributes.get('id'),
            ]
            
            # Also check time element for showtime ID
            if time_element:
                showtime_id_sources.extend([
                    time_element.attributes.get('data-showtime-id'),
                    time_element.attributes.get('data-showtime'),
                    time_element.attributes.get('data-id'),
                    time_element.attributes.get('id'),
                ])
            
            # Also check the ticket link for showtime ID
            if ticket_link:
                showtime_id_sources.extend([
                    ticket_link.attributes.get('data-showtime-id'),
                    ticket_link.attributes.get('data-showtime'),
                    ticket_link.attributes.get('data-id'),
                    ticket_link.attributes.get('id'),
                ])
                
                # Also check if the href itself contains showtime info
                href = ticket_link.attributes.get('href', '')
                if '?showtime=' in href or '&showtime=' in href:
                    # Extract showtime ID from URL
                    parsed_url = urlparse(href)
                    query_params = parse_qs(parsed_url.query)
                    if 'showtime' in query_params:
                        showtime_id_sources.append(query_params['showtime'][0])
                        print(f"  🎯 Found showtime in URL: {query_params['showtime'][0]}")
                        
            # Look for showtime ID in any script tags or form inputs
            script_tags = article_element.css('script')
            for script in script_tags:
                script_content = script.text() if script.text() else ""
                if 'showtime' in script_content.lower():
                    print(f"  📜 Script content with showtime: {script_content[:200]}...")
                    
            # Look for hidden inputs that might contain showtime ID
            inputs = article_element.css('input[type="hidden"]')
            for inp in inputs:
                inp_name = inp.attributes.get('name', '').lower()
                inp_value = inp.attributes.get('value', '')
                if 'showtime' in inp_name or 'id' in inp_name:
                    showtime_id_sources.append(inp_value)
                    print(f"  📝 Hidden input {inp_name}: {inp_value}")
            
            # Find the first non-empty showtime ID
            for sid in showtime_id_sources:
                if sid and sid.strip():
                    showtime_id = sid.strip()
                    break
            
            # Construct showtime-specific URL if we have the necessary components
            if ticket_url and showtime_id:
                # Parse the ticket URL to get the movie path
                parsed_url = urlparse(ticket_url)
                if parsed_url.path and not parsed_url.query:
                    # Construct the showtime URL: movie_url?showtime=ID
                    ticket_url = f"{ticket_url}?showtime={showtime_id}"
                    print(f"  🎫 Showtime URL: {ticket_url}")
                elif showtime_id:
                    print(f"  🆔 Found showtime ID: {showtime_id}")
            elif showtime_id:
                print(f"  🆔 Found showtime ID: {showtime_id} (no base URL)")
            
            if ticket_url:
                print(f"  🔗 Ticket URL: {ticket_url}")

            # Create showtime data
            showtimes = []
            if showtime_text and datetime_attr:
                # Parse the datetime attribute to get proper ISO format
                showtime_data = {
                    'datetime': datetime_attr,
                    'display_text': f"{current_date_section} {showtime_text}",
                    'time': showtime_text,
                    'date_section': current_date_section,
                    'ticket_url': ticket_url,
                    'showtime_id': showtime_id
                }
                showtimes.append(showtime_data)
            elif showtime_text:
                # Fallback if no datetime attribute
                showtime_data = {
                    'datetime': '',
                    'display_text': f"{current_date_section} {showtime_text}",
                    'time': showtime_text,
                    'date_section': current_date_section,
                    'ticket_url': ticket_url,
                    'showtime_id': showtime_id
                }
                showtimes.append(showtime_data)

            # Create film data
            film_data = {
                'title': title,
                'director': director,
                'duration': duration,
                'language': language,
                'showtimes': showtimes,
                'ticket_url': ticket_url,
                'date_section': current_date_section
            }

            return film_data

        except Exception as e:
            print(f"  ❌ Error extracting film details: {e}")
            return None

    def scrape_films(self):
        """Main scraping method."""
        print("🎬 Starting scraper for Bio Fågel Blå Stockholm")
        print(f"🔗 Fetching main page: {self.base_url}")
        
        content = self.get_page_content(self.base_url)
        if not content:
            print("❌ Failed to fetch main page")
            return

        tree = HTMLParser(content)
        
        # Find all date sections
        date_sections = tree.css('section[data-date-range]')
        
        print(f"📋 Found {len(date_sections)} date sections to check")
        
        film_count = 0
        english_films_count = 0
        
        for section_idx, section in enumerate(date_sections):
            # Extract date from the section header
            date_header = section.css_first('h3.block.mb-6')
            if date_header:
                current_date_section = date_header.text(strip=True)
                print(f"\n📅 Processing section {section_idx + 1}/{len(date_sections)}: {current_date_section}")
            else:
                current_date_section = f"Date section {section_idx + 1}"
                print(f"\n📅 Processing section {section_idx + 1}/{len(date_sections)}: {current_date_section}")
            
            # Find all articles (films) in this date section
            articles = section.css('article')
            
            for article_idx, article in enumerate(articles):
                film_count += 1
                
                # Check for English subtitles
                has_english_subs = self.check_for_english_subtitles(article)
                
                if has_english_subs:
                    print(f"  ✅ Found film with English subtitles!")
                    english_films_count += 1
                    
                    # Extract film details
                    film_data = self.extract_film_details(article, current_date_section)
                    
                    if film_data:
                        # Generate a unique film ID
                        film_id = film_data['title'].lower().replace(' ', '-').replace(':', '').replace(',', '')
                        film_id = ''.join(c for c in film_id if c.isalnum() or c == '-')
                        
                        # Create final film data structure
                        final_film_data = {
                            'film_id': film_id,
                            'url': self.base_url,  # Main program page
                            'title': film_data['title'],
                            'director': film_data['director'],
                            'duration': film_data['duration'],
                            'language': film_data['language'],
                            'showtimes': film_data['showtimes'],
                            'cinemas': ["Bio Fågel Blå Stockholm"],
                            'scraped_at': datetime.now(timezone.utc).isoformat(),
                            'source': 'fagelbla'
                        }
                        
                        self.films_with_english_subs.append(final_film_data)
                        
                        print(f"  ✅ Added film: {film_data['title']}")
                    else:
                        print(f"  ❌ Failed to extract details for film with English subtitles")
                else:
                    # Find title for logging
                    title_element = article.css_first('h3.text-sm.font-bold.uppercase.font-heading')
                    if title_element:
                        time_element = title_element.css_first('time')
                        if time_element:
                            full_text = title_element.text(strip=True)
                            time_text = time_element.text(strip=True)
                            title = full_text.replace(time_text, "").strip()
                        else:
                            title = title_element.text(strip=True)
                        print(f"  ❌ No English subtitles for: {title}")
                    else:
                        print(f"  ❌ No English subtitles found (could not extract title)")

        print(f"\n📊 SCRAPING COMPLETE!")
        print(f"✅ Found {english_films_count} films with English subtitles out of {film_count} total films")
        
        # Save results to JSON file
        import os
        os.makedirs('data', exist_ok=True)
        output_file = './data/fagelbla_films_with_english_subs.json'
        
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


if __name__ == "__main__":
    scraper = FagelBla()
    scraper.scrape_films()