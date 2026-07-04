#!/usr/bin/env python3
"""
Bio Rio Stockholm web scraper to find films with English subtitles.
Scrapes from https://www.biorio.se/aktuellt and follows movie links.
"""

import httpx
from selectolax.parser import HTMLParser
import time
import json
import os
from urllib.parse import urljoin, urlparse
from datetime import datetime
import re


class BioRio:
    def __init__(self, base_url="https://www.biorio.se/sv/filmer"):
        """Initialize the Bio Rio scraper."""
        self.base_url = base_url
        self.domain = "https://www.biorio.se"
        # Additional listing pages to scan (e.g. upcoming films tab)
        self.list_urls = [base_url, base_url + "?tab=upcoming"]
        
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        # Create persistent session for API calls
        self.session = httpx.Client(timeout=15.0, follow_redirects=True, headers=self.headers)
        
        self.films_with_english_subs = []
    
    def get_page_content(self, url):
        """Fetch page content with error handling."""
        try:
            response = self.session.get(url)
            response.raise_for_status()
            return response.text
        except httpx.HTTPStatusError as e:
            print(f"HTTP error fetching {url}: {e.response.status_code} {e.response.reason_phrase}")
            return None
        except httpx.RequestError as e:
            print(f"Error fetching {url}: {e}")
            return None
    
    def find_movie_links(self, html_content):
        """Find all movie links from a listing page that point to /filmer/<slug>."""
        tree = HTMLParser(html_content)

        # The site uses both /filmer/<slug> and /sv/filmer/<slug>
        all_links = tree.css('a[href*="/filmer/"]')

        movie_links = []
        for link in all_links:
            href = link.attributes.get('href')
            if not href:
                continue

            # Make absolute URL
            if href.startswith('/'):
                full_url = self.domain + href
            elif 'biorio.se' in href:
                full_url = href
            else:
                continue

            # Match film detail pages only (skip the listing page itself)
            m = re.search(r'biorio\.se/(?:sv/)?filmer/([^/?#]+)', full_url)
            if not m:
                continue
            slug = m.group(1)
            # Normalize to the /sv/filmer/<slug> form
            normalized = f"{self.domain}/sv/filmer/{slug}"
            movie_links.append(normalized)

        # Remove duplicates while preserving order
        seen = set()
        unique_links = []
        for link in movie_links:
            if link not in seen:
                seen.add(link)
                unique_links.append(link)

        return unique_links

    def parse_credits(self, tree):
        """Parse the .movie-credits-grid into a {label_lower: value} dict."""
        credits = {}
        for item in tree.css('.movie-credits-grid .movie-credit-item'):
            label_el = item.css_first('.movie-credit-label')
            value_el = item.css_first('.movie-credit-value')
            if label_el and value_el:
                credits[label_el.text().strip().lower()] = value_el.text().strip()
        return credits
    
    def check_for_english_subtitles(self, html_content):
        """Check if the film page lists 'Engelska' as Undertext."""
        tree = HTMLParser(html_content)
        credits = self.parse_credits(tree)
        subs = credits.get('undertext', '')
        if subs and 'engelska' in subs.lower():
            print(f"  ✅ Found English subtitles: {subs}")
            return True
        if subs:
            print(f"  ❌ Subtitles: {subs}")
        else:
            print(f"  ❌ No subtitle info found")
        return False
    
    def extract_cinema_id(self, html_content):
        """Extract cinema ID from the page source."""
        import re
        
        # Look for const cinemaId = '...' pattern
        cinema_id_match = re.search(r"const cinemaId = ['\"](\d+)['\"]", html_content)
        if cinema_id_match:
            return cinema_id_match.group(1)
        
        # Alternative pattern: cinemaId: '...'
        cinema_id_match = re.search(r"cinemaId[:\s]*['\"](\d+)['\"]", html_content)
        if cinema_id_match:
            return cinema_id_match.group(1)
        
        return None
    
    def extract_movie_id(self, html_content):
        """Extract movie ID from the page source."""
        from selectolax.parser import HTMLParser

        tree = HTMLParser(html_content)

        # Try to find data-movie-id attribute
        movie_id_elements = tree.css('[data-movie-id]')
        if movie_id_elements:
            movie_id = movie_id_elements[0].attributes.get('data-movie-id')
            if movie_id:
                return movie_id

        # Bio Rio's Next.js payload embeds movieId as JSON; the HTML contains
        # both raw `"movieId":5822` and escaped `\"movieId\":\"5822\"` forms.
        for pattern in (
            r'movieId\\?"\s*:\s*\\?"?(\d+)',
            r"movieId[:\s]*['\"](\d+)['\"]",
        ):
            m = re.search(pattern, html_content)
            if m:
                return m.group(1)

        return None
    
    def fetch_showtimes_from_api(self, cinema_id, movie_id):
        """Fetch showtimes from Bio Rio API."""
        import json
        from datetime import datetime, timedelta
        
        # Use the REAL Bio Rio API endpoint (not Firebase)
        api_url = f"https://api.biorio.se/api/proxy/showtimes/by-movie?movieId={movie_id}"
        
        # No payload needed for GET request
        payload = None
        
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Origin': 'https://www.biorio.se',
            'Referer': 'https://www.biorio.se/'
        }
        
        try:
            print(f"    📡 Making API call to fetch showtimes...")
            response = self.session.get(api_url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                try:
                    api_data = response.json()
                    print(f"    📋 API response type: {type(api_data)}")
                    
                    # Normalize to a list of showtime dicts whether API returned a list or a wrapper dict
                    data_list = None
                    if isinstance(api_data, list):
                        data_list = api_data
                    elif isinstance(api_data, dict):
                        # Common wrapper shape: {'showtimes': [...]}
                        if 'showtimes' in api_data and isinstance(api_data['showtimes'], list):
                            data_list = api_data['showtimes']
                        # Sometimes it's {'data': [...]}
                        elif 'data' in api_data and isinstance(api_data['data'], list):
                            data_list = api_data['data']
                        else:
                            # Try to find any first list value inside the dict
                            for v in api_data.values():
                                if isinstance(v, list):
                                    data_list = v
                                    break
                    
                    if not isinstance(data_list, list):
                        print(f"    ❌ Could not find a showtimes list inside API response. Full response keys: {list(api_data.keys()) if isinstance(api_data, dict) else 'n/a'}")
                        print(f"    📋 Raw response (truncated): {response.text[:500]}...")
                        return []
                    
                    print(f"    📋 Found {len(data_list)} showtimes in API response")
                    
                    movie_showtimes = []
                    print(f"    🔍 Processing showtimes for movie ID: {movie_id}")
                    
                    for showtime in data_list:
                        if isinstance(showtime, dict):
                            formatted_showtime = {
                                'datetime': showtime.get('startTime', ''),
                                'display_text': self.format_api_showtime(showtime),
                                'movie_id': movie_id,
                                'cinema_id': cinema_id,
                                'booking_url': f"https://www.biorio.se/sv/boka/{showtime.get('id', '')}",
                                'api_data': showtime
                            }
                            movie_showtimes.append(formatted_showtime)
                    
                    print(f"    ✅ Successfully processed {len(movie_showtimes)} showtimes")
                    return movie_showtimes
                except Exception as json_error:
                    print(f"    ❌ Error parsing JSON response: {json_error}")
                    print(f"    📋 Raw response: {response.text[:500]}...")
                    return []
            else:
                print(f"    ❌ API request failed with status: {response.status_code}")
                return []
                
        except Exception as e:
            print(f"    ❌ Error fetching showtimes from API: {e}")
            return []
    
    def format_api_showtime(self, showtime_data):
        """Format showtime data from API into display text."""
        try:
            start_time = showtime_data.get('startTime', '')
            if start_time:
                # Parse the datetime and format it nicely
                from datetime import datetime
                dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                return dt.strftime('%A %B %d, %Y at %H:%M')
            else:
                return 'Time TBA'
        except Exception:
            return str(showtime_data.get('startTime', 'Time TBA'))
    

    def extract_film_details(self, html_content, url):
        """Extract film details from individual film page."""
        tree = HTMLParser(html_content)
        credits = self.parse_credits(tree)

        # Extract title from the new movie-title-v2 heading
        title = ""
        for selector in ('h1.movie-title-v2', 'h1', '.movie-titlev2 a', '.movie-title'):
            els = tree.css(selector)
            if els:
                title = els[0].text().strip()
                if title:
                    break

        # If still no title, try to extract from URL
        if not title:
            url_parts = url.rstrip('/').split('/')
            if url_parts:
                title = url_parts[-1].replace('-', ' ').title()

        # Director comes from the credits grid
        director = credits.get('regissör', '')

        # Fetch showtimes via API (cinemaId is not actually required by the API)
        print(f"  🔍 Looking for movie ID and fetching showtimes via API...")
        all_showtimes = []

        cinema_id = self.extract_cinema_id(html_content) or '10'
        movie_id = self.extract_movie_id(html_content)

        if movie_id:
            print(f"  🎬 Found movie ID: {movie_id}")
            api_showtimes = self.fetch_showtimes_from_api(cinema_id, movie_id)
            if api_showtimes:
                all_showtimes = api_showtimes
                print(f"  ✅ Successfully fetched {len(api_showtimes)} showtimes from API")
            else:
                print(f"  ❌ No showtimes returned from API - excluding movie from results")
                return None
        else:
            print(f"  ❌ Could not extract movie ID from page - excluding movie from results")
            return None
        
        # Only proceed if we have actual showtimes
        if not all_showtimes:
            print(f"  ❌ No valid showtimes found - excluding movie from results")
            return None
        
        # Extract cinema information (Bio Rio)
        cinemas = ["Bio Rio Stockholm"]
        
        # Try to extract additional cinema info if available
        cinema_selectors = [
            '.cinema-info',
            '.venue',
            '.location'
        ]
        
        for selector in cinema_selectors:
            cinema_elements = tree.css(selector)
            for elem in cinema_elements:
                cinema_text = elem.text().strip()
                if cinema_text and cinema_text not in cinemas:
                    cinemas.append(cinema_text)
        
        return title, director, all_showtimes, cinemas
    
    def get_film_data(self, film_url):
        """Get comprehensive film data from individual film page."""
        print(f"  📋 Getting data for film: {film_url.split('/')[-1]}")
        
        # Get film page content
        film_content = self.get_page_content(film_url)
        if not film_content:
            print(f"  ❌ Failed to fetch film page")
            return None
        
        # Extract details
        extraction_result = self.extract_film_details(film_content, film_url)
        
        # Check if extraction was successful (returns None if no showtimes)
        if extraction_result is None:
            print(f"  ❌ Film excluded due to missing showtimes or data")
            return None
        
        title, director, showtimes, cinemas = extraction_result
        
        if title:
            print(f"  📝 Title: {title}")
        
        if director:
            print(f"  🎭 Director: {director}")
        
        if showtimes:
            print(f"  🗓️  Showtimes: {len(showtimes)} found")
            for showtime in showtimes[:3]:  # Show first 3 showtimes
                print(f"    - {showtime.get('display_text')}")
            if len(showtimes) > 3:
                print(f"    ... and {len(showtimes) - 3} more")
        
        if cinemas:
            print(f"  🎭 Cinemas: {', '.join(cinemas)}")
        
        # Extract film ID from URL
        parsed_url = urlparse(film_url)
        film_id = parsed_url.path.split('/')[-1] if parsed_url.path else 'unknown'
        
        # Create film data dictionary
        film_data = {
            'film_id': film_id,
            'url': film_url,
            'title': title,
            'director': director,
            'showtimes': showtimes,
            'cinemas': cinemas,
            'scraped_at': datetime.now().isoformat(),
            'source': 'biorio'
        }
        
        return film_data
    
    def scrape_films(self):
        """Main scraping method to find films with English subtitles."""
        print(f"🎬 Starting scraper for Bio Rio Stockholm")
        print(f"🔗 Fetching main page: {self.base_url}")
        
        # Get the listing page content from each tab and merge film links
        movie_links = []
        seen_links = set()
        for list_url in self.list_urls:
            print(f"🔗 Fetching listing: {list_url}")
            main_content = self.get_page_content(list_url)
            if not main_content:
                print(f"❌ Failed to fetch listing page: {list_url}")
                continue
            for link in self.find_movie_links(main_content):
                if link not in seen_links:
                    seen_links.add(link)
                    movie_links.append(link)
        print(f"📋 Found {len(movie_links)} movie links to check")
        
        if not movie_links:
            print("⚠️  No movie links found")
            return
        
        films_with_english_subs = []
        
        # Check each link for English subtitles
        for i, link in enumerate(movie_links, 1):
            print(f"🎭 Checking film {i}/{len(movie_links)}: {link.split('/')[-1]}")
            
            # Get the film page content
            film_content = self.get_page_content(link)
            if not film_content:
                print(f"  ⚠️  Failed to fetch film page")
                continue
            
            # Check for English subtitles
            has_english_subs = self.check_for_english_subtitles(film_content)
            
            if has_english_subs:
                print(f"  ✅ Found film with English subtitles!")
                
                # Get comprehensive film data
                film_data = self.get_film_data(link)
                if film_data:
                    films_with_english_subs.append(film_data)
                
                # Small delay to be respectful
                time.sleep(0.5)
            else:
                print(f"  ❌ No English subtitles found")
            
            # Small delay between requests
            time.sleep(0.3)
        
        print(f"📊 SCRAPING COMPLETE!")
        print(f"✅ Found {len(films_with_english_subs)} films with English subtitles")
        
        # Save results
        self.save_results(films_with_english_subs)
        
        return films_with_english_subs
    
    def save_results(self, films):
        """Save the results to files."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save JSON file
        import os
        os.makedirs('data', exist_ok=True)
        json_filename = "./data/biorio_films_with_english_subs.json"
        with open(json_filename, 'w', encoding='utf-8') as f:
            json.dump(films, f, indent=2, ensure_ascii=False)
        
        # Count films with different data types
        films_with_titles = sum(1 for f in films if f.get('title'))
        films_with_showtimes = sum(1 for f in films if f.get('showtimes'))
        films_with_cinemas = sum(1 for f in films if f.get('cinemas'))
        total_showtimes = sum(len(f.get('showtimes', [])) for f in films)
        total_cinemas = sum(len(f.get('cinemas', [])) for f in films)

        print(f"💾 Results saved to:")
        print(f"   - {json_filename}")
        
        print(f"📈 STATISTICS:")
        print(f"   • Films with titles: {films_with_titles}/{len(films)}")
        print(f"   • Films with showtimes: {films_with_showtimes}/{len(films)}")
        print(f"   • Films with cinemas: {films_with_cinemas}/{len(films)}")
        print(f"   • Total showtimes found: {total_showtimes}")
        print(f"   • Total cinemas found: {total_cinemas}")
        print(f"\n💡 To add TMDb data: python3 tmdb_enricher.py {json_filename}")


if __name__ == "__main__":
    scraper = BioRio()
    scraper.scrape_films()
