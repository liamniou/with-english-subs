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
    def __init__(self, base_url="https://www.biorio.se/aktuellt"):
        """Initialize the Bio Rio scraper."""
        self.base_url = base_url
        self.domain = "https://www.biorio.se"
        
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
        except httpx.RequestError as e:
            print(f"Error fetching {url}: {e}")
            return None
    
    def find_movie_links(self, html_content):
        """Find all movie links from the main page that contain biorio.se/movies/."""
        tree = HTMLParser(html_content)
        
        # Look for all links containing /movies/
        all_links = tree.css('a[href*="/movies/"]')
        
        movie_links = []
        for link in all_links:
            href = link.attributes.get('href')
            if href:
                # Make absolute URL
                if href.startswith('/'):
                    full_url = self.domain + href
                elif 'biorio.se' in href:
                    full_url = href
                else:
                    continue
                
                # Only include links containing biorio.se/movies/
                if 'biorio.se' in full_url and '/movies/' in full_url:
                    movie_links.append(full_url)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_links = []
        for link in movie_links:
            if link not in seen:
                seen.add(link)
                unique_links.append(link)
        
        return unique_links
    
    def check_for_english_subtitles(self, html_content):
        """Check if the film page contains 'Engelska' in subtitle section."""
        tree = HTMLParser(html_content)
        
        # Find all divs in the page
        all_divs = tree.css('div')
        
        for i, div in enumerate(all_divs):
            div_text = div.text().strip()
            
            # Check if this div contains exactly "Undertext"
            if div_text and div_text.lower() == 'undertext':
                print(f"  🔍 Found 'Undertext' div")
                
                # Get the next div element
                if i + 1 < len(all_divs):
                    next_div = all_divs[i + 1]
                    next_div_text = next_div.text().strip()
                    
                    print(f"  📋 Next div text: '{next_div_text}'")
                    
                    # Check if the next div contains 'Engelska'
                    if next_div_text and 'engelska' in next_div_text.lower():
                        print(f"  ✅ Found English subtitles: {next_div_text}")
                        return True
                    elif next_div_text and 'svenska' in next_div_text.lower():
                        print(f"  ❌ Found Swedish subtitles: {next_div_text}")
                        # Continue checking other "Undertext" divs
                    else:
                        print(f"  ⚠️  Next div after 'Undertext' contains: '{next_div_text}'")
        
        # Alternative approach: look for "Undertext" in div text (case-insensitive)
        for i, div in enumerate(all_divs):
            div_text = div.text().strip().lower()
            
            # Check if this div contains "undertext" (more flexible matching)
            if 'undertext' in div_text and len(div_text) <= 20:  # Avoid matching large text blocks
                print(f"  🔍 Found div containing 'undertext': '{div.text().strip()}'")
                
                # Get the next div element
                if i + 1 < len(all_divs):
                    next_div = all_divs[i + 1]
                    next_div_text = next_div.text().strip()
                    
                    print(f"  📋 Next div text: '{next_div_text}'")
                    
                    # Check if the next div contains 'Engelska'
                    if next_div_text and 'engelska' in next_div_text.lower():
                        print(f"  ✅ Found English subtitles: {next_div_text}")
                        return True
                    elif next_div_text and 'svenska' in next_div_text.lower():
                        print(f"  ❌ Found Swedish subtitles: {next_div_text}")
                        # Continue checking other potential "Undertext" divs
        
        print(f"  ❌ No English subtitles found")
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
        import re
        from selectolax.parser import HTMLParser
        
        tree = HTMLParser(html_content)
        
        # Try to find data-movie-id attribute
        movie_id_elements = tree.css('[data-movie-id]')
        if movie_id_elements:
            movie_id = movie_id_elements[0].attributes.get('data-movie-id')
            if movie_id:
                return movie_id
        
        # Alternative: look for movie ID in JavaScript
        movie_id_match = re.search(r"movieId[:\s]*['\"](\d+)['\"]", html_content)
        if movie_id_match:
            return movie_id_match.group(1)
        
        # Try to extract from URL patterns
        movie_id_match = re.search(r"/movies/[^/]*\?.*id=(\d+)", html_content)
        if movie_id_match:
            return movie_id_match.group(1)
        
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
                    print(f"    📋 Found {len(api_data)} showtimes in API response" if isinstance(api_data, list) else f"    📋 API response: {api_data}")
                    
                    # The new Bio Rio API returns showtimes directly as a list
                    if isinstance(api_data, list):
                        movie_showtimes = []
                        print(f"    🔍 Processing showtimes for movie ID: {movie_id}")
                        
                        for showtime in api_data:
                            if isinstance(showtime, dict):
                                formatted_showtime = {
                                    'datetime': showtime.get('startTime', ''),
                                    'display_text': self.format_api_showtime(showtime),
                                    'movie_id': movie_id,
                                    'cinema_id': cinema_id,
                                    'booking_url': f"https://biorio.se/showtime/{showtime.get('id', '')}",
                                    'api_data': showtime
                                }
                                movie_showtimes.append(formatted_showtime)
                        
                        print(f"    ✅ Successfully processed {len(movie_showtimes)} showtimes")
                        return movie_showtimes
                    else:
                        print(f"    ❌ Expected list but got: {type(api_data)}")
                        return []
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
        
        # Extract title from the specified selector
        title = ""
        title_selectors = [
            '#w-node-d87164c5-94a7-e9f7-a217-6196d41cc303-f47a8a01 > div.movie-titlev2 > a',
            'div.movie-titlev2 > a',
            '.movie-titlev2 a',
            'h1',
            '.movie-title'
        ]
        
        for selector in title_selectors:
            title_elements = tree.css(selector)
            if title_elements:
                title = title_elements[0].text().strip()
                break
        
        # If still no title, try to extract from URL
        if not title:
            url_parts = url.split('/')
            if url_parts:
                title = url_parts[-1].replace('-', ' ').title()
        
        # Extract director information
        director = ""
        director_selectors = [
            '#w-node-_66399d6d-b16a-02f9-8476-bf3230235a79-f47a8a01',
            '.director',
            '.movie-director'
        ]
        
        for selector in director_selectors:
            director_elements = tree.css(selector)
            if director_elements:
                director = director_elements[0].text().strip()
                break
        
        # Extract cinema ID and fetch showtimes via API
        print(f"  🔍 Looking for cinema ID and fetching showtimes via API...")
        all_showtimes = []
        
        # Extract cinema ID from page source
        cinema_id = self.extract_cinema_id(html_content)
        
        if cinema_id:
            print(f"  🎭 Found cinema ID: {cinema_id}")
            # Extract movie ID for filtering
            movie_id = self.extract_movie_id(html_content)
            
            if movie_id:
                print(f"  🎬 Found movie ID: {movie_id}")
                # Fetch showtimes from the API
                api_showtimes = self.fetch_showtimes_from_api(cinema_id, movie_id)
                
                if api_showtimes:
                    all_showtimes = api_showtimes
                    print(f"  ✅ Successfully fetched {len(api_showtimes)} showtimes from API")
                else:
                    print(f"  ❌ No showtimes returned from API - excluding movie from results")
                    return None  # Don't include movies without showtimes
            else:
                print(f"  ❌ Could not extract movie ID from page - excluding movie from results")
                return None  # Don't include movies without movie ID
        else:
            print(f"  ❌ Could not extract cinema ID from page - excluding movie from results")
            return None  # Don't include movies without cinema ID
        
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
        
        # Get the main page content
        main_content = self.get_page_content(self.base_url)
        if not main_content:
            print("❌ Failed to fetch main page")
            return
        
        # Find all movie links
        print("🔍 Finding movie links...")
        movie_links = self.find_movie_links(main_content)
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