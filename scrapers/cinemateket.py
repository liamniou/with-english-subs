#!/usr/bin/env python3
"""
Cinemateket Stockholm web scraper to find films with English subtitles.
"""

import httpx
from selectolax.parser import HTMLParser
import time
import json
import os
from urllib.parse import urljoin, urlparse, parse_qs, quote
from datetime import datetime

class Cinemateket:
    def __init__(self, base_url=None, page=100):
        """Initialize the Cinemateket scraper."""
        if base_url is None:
            self.base_url = f"https://www.filminstitutet.se/sv/se-och-samtala-om-film/cinemateket-stockholm/program/?eventtype=&listtype=text&page={page}"
        else:
            self.base_url = base_url
        
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        self.films_with_english_subs = []
    
    def get_page_content(self, url):
        """Fetch page content with error handling."""
        try:
            with httpx.Client(timeout=15.0) as client:
                response = client.get(url, headers=self.headers)
                response.raise_for_status()
                return response.text
        except httpx.RequestError as e:
            print(f"Error fetching {url}: {e}")
            return None

    def find_article_links(self, html_content):
        """Find all article links from the main page."""
        tree = HTMLParser(html_content)
        article_divs = tree.css('div.article-tickets.article__border')
        
        links = []
        for div in article_divs:
            link_elements = div.css('a')
            for link in link_elements:
                href = link.attributes.get('href')
                if href:
                    full_url = urljoin(self.base_url, href)
                    # Only include links containing filminstitutet.se
                    if 'filminstitutet.se' in full_url:
                        links.append(full_url)
        
        return links

    def check_for_english_text(self, html_content):
        """Check if the film page contains 'engelsk text'."""
        tree = HTMLParser(html_content)
        editorial_divs = tree.css('div.article__editorial-content')
        
        for div in editorial_divs:
            text = div.text()
            if text and 'engelsk text' in text.lower():
                return True
        
        return False

    def extract_film_details(self, html_content):
        """Extract film details from individual film page."""
        tree = HTMLParser(html_content)
        
        # Extract description/title
        description = ""
        description_elements = tree.css('#maincontent > div.js-article.article.article--cinemateket > article > div > div.article__main-paragraph > p:nth-child(1)')
        if description_elements:
            description = description_elements[0].text().strip()
        
        # Extract showtimes
        showtimes = []
        showtime_elements = tree.css('#maincontent > div.js-article.article.article--cinemateket > article > div > div.article-tickets-container.margin-xs-v-3.margin-md-v-4 > div > div > time')
        for time_elem in showtime_elements:
            datetime_attr = time_elem.attributes.get('datetime', '')
            time_text = time_elem.text().strip()
            if time_text:
                showtimes.append({
                    'datetime': datetime_attr,
                    'display_text': time_text
                })
        
        # Extract cinema information
        cinemas = []
        cinema_elements = tree.css('#maincontent > div.js-article.article.article--cinemateket > article > div > div.article-tickets-container.margin-xs-v-3.margin-md-v-4 > div > a.article-tickets__meta-item.margin-xs-b-1 > span')
        for cinema_elem in cinema_elements:
            cinema_text = cinema_elem.text().strip()
            if cinema_text:
                cinemas.append(cinema_text)
        
        return description, showtimes, cinemas

    def get_film_data(self, film_url):
        """Get comprehensive film data from individual film page."""
        print(f"  📋 Getting data for film: {film_url.split('=')[-2] if '=' in film_url else 'unknown'}")
        
        # Get film page content
        film_content = self.get_page_content(film_url)
        if not film_content:
            print(f"  ❌ Failed to fetch film page")
            return None
        
        # Extract details
        title, showtimes, cinemas = self.extract_film_details(film_content)
        
        if title:
            print(f"  📝 Title: {title}")
        
        if showtimes:
            print(f"  🗓️  Showtimes: {len(showtimes)} found")
            for showtime in showtimes[:3]:  # Show first 3 showtimes
                print(f"    - {showtime.get('display_text')}")
            if len(showtimes) > 3:
                print(f"    ... and {len(showtimes) - 3} more")
        
        if cinemas:
            print(f"  🎭 Cinemas: {', '.join(cinemas)}")
        
        # Parse film ID from URL
        parsed_url = urlparse(film_url)
        query_params = parse_qs(parsed_url.query)
        film_id = query_params.get('filmId', ['unknown'])[0]
        
        # Create film data dictionary
        film_data = {
            'film_id': film_id,
            'url': film_url,
            'original_details': film_content,
            'title': title,
            'showtimes': showtimes,
            'cinemas': cinemas,
            'scraped_at': datetime.now().isoformat()
        }
        
        return film_data

    def scrape_films(self):
        """Main scraping method to find films with English subtitles."""
        print(f"🎬 Starting scraper for Cinemateket Stockholm")
        print(f"🔗 Fetching main page: {self.base_url}")
        
        # Get the main page content
        main_content = self.get_page_content(self.base_url)
        if not main_content:
            print("❌ Failed to fetch main page")
            return
        
        # Find all article links
        print("🔍 Finding article links...")
        article_links = self.find_article_links(main_content)
        print(f"📋 Found {len(article_links)} article links to check")
        
        films_with_english_subs = []
        
        # Check each link for English subtitles
        for i, link in enumerate(article_links, 1):
            print(f"🎭 Checking film {i}/{len(article_links)}: {link.split('=')[-2] if '=' in link else 'unknown'}")
            
            # Get the film page content
            film_content = self.get_page_content(link)
            if not film_content:
                print(f"  ⚠️  Failed to fetch film page")
                continue
            
            # Check for English subtitles
            has_english_subs = self.check_for_english_text(film_content)
            
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
            time.sleep(0.2)
        
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
        json_filename = "./data/cinemateket_films_with_english_subs.json"
        with open(json_filename, 'w', encoding='utf-8') as f:
            json.dump(films, f, indent=2, ensure_ascii=False)
        
        # Count films with different data types
        films_with_titles = sum(1 for f in films if f.get('title'))
        films_with_showtimes = sum(1 for f in films if f.get('showtimes'))
        films_with_cinemas = sum(1 for f in films if f.get('cinemas'))
        total_showtimes = sum(len(f.get('showtimes', [])) for f in films)
        total_cinemas = sum(len(f.get('cinemas', [])) for f in films)
        
        summary_content = f"""FILMS WITH ENGLISH SUBTITLES - SUMMARY
{'='*50}
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Total films found: {len(films)}

STATISTICS:
• Films with titles: {films_with_titles}/{len(films)}
• Films with showtimes: {films_with_showtimes}/{len(films)}
• Films with cinemas: {films_with_cinemas}/{len(films)}
• Total showtimes found: {total_showtimes}
• Total cinemas found: {total_cinemas}

NOTE: Use tmdb_enricher.py to add TMDb data to the JSON file
"""
        
        # Save summary file
        summary_filename = "./films_with_english_subs_summary.txt"
        with open(summary_filename, 'w', encoding='utf-8') as f:
            f.write(summary_content)
        
        # Save simple list file
        list_content = f"""FILMS WITH ENGLISH SUBTITLES - LIST
{'='*40}
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

"""
        
        for i, film in enumerate(films, 1):
            title = film.get('title', 'No title')
            film_id = film.get('film_id', 'Unknown ID')
            showtimes_count = len(film.get('showtimes', []))
            cinemas = ', '.join(film.get('cinemas', []))
            
            list_content += f"{i}. {title}\n"
            list_content += f"   ID: {film_id}\n"
            list_content += f"   Showtimes: {showtimes_count}\n"
            if cinemas:
                list_content += f"   Cinemas: {cinemas}\n"
            list_content += f"   URL: {film.get('url', 'No URL')}\n\n"
        
        list_filename = "./films_with_english_subs_list.txt"
        with open(list_filename, 'w', encoding='utf-8') as f:
            f.write(list_content)
        
        print(f"💾 Results saved to:")
        print(f"   - {json_filename}")
        print(f"   - {summary_filename}")
        print(f"   - {list_filename}")
        
        print(f"📈 STATISTICS:")
        print(f"   • Films with titles: {films_with_titles}/{len(films)}")
        print(f"   • Films with showtimes: {films_with_showtimes}/{len(films)}")
        print(f"   • Films with cinemas: {films_with_cinemas}/{len(films)}")
        print(f"   • Total showtimes found: {total_showtimes}")
        print(f"   • Total cinemas found: {total_cinemas}")
        print(f"\n💡 To add TMDb data: python3 tmdb_enricher.py {json_filename}")


if __name__ == "__main__":
    scraper = Cinemateket()
    scraper.scrape_films()