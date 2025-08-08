#!/usr/bin/env python3
"""
Static HTML Generator - Creates self-contained HTML files for film listings.

This script combines HTML, CSS, JavaScript, and JSON data into a single
static HTML file that can be opened directly in any browser without a server.
"""

import json
import os
import argparse
import re
from pathlib import Path
from typing import Optional

class StaticHTMLGenerator:
    """Generates static HTML files by embedding CSS, JS, and JSON data."""
    
    def __init__(self):
        self.base_dir = Path.cwd()
        
    def read_file(self, file_path: str) -> str:
        """Read file content with error handling.
        
        Args:
            file_path: Path to file to read
            
        Returns:
            File content as string
            
        Raises:
            FileNotFoundError: If file doesn't exist
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            raise FileNotFoundError(f"Required file not found: {file_path}")
        except Exception as e:
            raise Exception(f"Error reading {file_path}: {e}")
    
    def load_json_data(self, json_path: str) -> str:
        """Load and validate JSON data, with automatic merging of multiple sources.
        
        Args:
            json_path: Path to primary JSON file
            
        Returns:
            JSON content as string (merged if multiple sources exist)
            
        Raises:
            FileNotFoundError: If no JSON files exist
            ValueError: If JSON is invalid
        """
        # Define all possible data sources
        possible_sources = [
            json_path,  # Primary file specified
            "data/cinemateket_films_with_english_subs.json",
            "data/biorio_films_with_english_subs.json",
            "data/fagelbla_films_with_english_subs.json",
            "data/zita_films_with_english_subs.json",
            "data/films_with_english_subs.json",
            "data/films_with_english_subs_enriched.json"
        ]
        
        merged_films = []
        loaded_sources = []
        
        print("🔍 Looking for film data sources...")
        
        for source_file in possible_sources:
            if os.path.exists(source_file):
                try:
                    with open(source_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        
                    # Add source information to each film
                    for film in data:
                        if 'data_source' not in film:
                            if 'cinemateket' in source_file.lower():
                                film['data_source'] = 'Cinemateket'
                            elif 'biorio' in source_file.lower():
                                film['data_source'] = 'Bio Rio'
                            elif 'fagelbla' in source_file.lower():
                                film['data_source'] = 'Bio Fågel Blå'
                            elif 'zita' in source_file.lower():
                                film['data_source'] = 'Zita Folkets Bio'
                            else:
                                film['data_source'] = 'Cinema'
                        film['source_file'] = source_file
                    
                    merged_films.extend(data)
                    loaded_sources.append(f"{source_file} ({len(data)} films)")
                    print(f"  ✅ Loaded {len(data)} films from {source_file}")
                    
                except json.JSONDecodeError as e:
                    print(f"  ⚠️  Invalid JSON in {source_file}: {e}")
                except Exception as e:
                    print(f"  ⚠️  Error reading {source_file}: {e}")
        
        if not merged_films:
            raise FileNotFoundError(f"No valid JSON data files found. Checked: {', '.join(possible_sources)}")
        
        # Merge films with same TMDB ID (movies showing at multiple cinemas)
        unique_films = self._merge_multi_cinema_films(merged_films)
        
        print(f"📊 Merged {len(merged_films)} total films → {len(unique_films)} unique films")
        print(f"📁 Sources loaded: {', '.join(loaded_sources)}")
        
        return json.dumps(unique_films, ensure_ascii=False)
    
    def _merge_multi_cinema_films(self, films):
        """Merge films showing at multiple cinemas based on TMDB ID or title+year fallback."""
        film_map = {}
        merged_count = 0
        
        for film in films:
            # Primary key: TMDB ID if available
            tmdb_id = film.get('tmdb', {}).get('id')
            
            # Fallback key: title + year
            title = film.get('title', '').lower().strip()
            year = ''
            if film.get('tmdb', {}).get('release_date'):
                try:
                    year = str(film['tmdb']['release_date'][:4])
                except:
                    pass
            title_year_key = f"{title}_{year}"
            
            # Use TMDB ID as primary key, title+year as fallback
            key = f"tmdb_{tmdb_id}" if tmdb_id else f"title_{title_year_key}"
            
            if key in film_map:
                # Merge with existing film
                existing_film = film_map[key]
                merged_count += 1
                
                # Merge cinemas
                existing_cinemas = existing_film.get('cinemas', [])
                new_cinemas = film.get('cinemas', [])
                existing_film['cinemas'] = existing_cinemas + new_cinemas
                
                # Merge showtimes with cinema source information
                existing_showtimes = existing_film.get('showtimes', [])
                new_showtimes = []
                for showtime in film.get('showtimes', []):
                    new_showtime = {**showtime}
                    new_showtime['source_cinema'] = film.get('data_source', '')
                    new_showtime['source_cinemas'] = film.get('cinemas', [])
                    if film.get('url'):
                        new_showtime['source_url'] = film['url']
                    new_showtimes.append(new_showtime)
                
                existing_film['showtimes'] = existing_showtimes + new_showtimes
                
                # Merge data sources
                existing_sources = existing_film.get('data_sources', [existing_film.get('data_source')])
                if film.get('data_source') and film['data_source'] not in existing_sources:
                    existing_sources.append(film['data_source'])
                existing_film['data_sources'] = [s for s in existing_sources if s]  # Remove None values
                
                # Merge URLs
                existing_urls = existing_film.get('urls', [existing_film.get('url')])
                if film.get('url') and film['url'] not in existing_urls:
                    existing_urls.append(film['url'])
                existing_film['urls'] = [u for u in existing_urls if u]  # Remove None values
                
                # Keep the best available TMDB data (prefer more complete data)
                if film.get('tmdb'):
                    if not existing_film.get('tmdb'):
                        existing_film['tmdb'] = film['tmdb']
                    else:
                        # Merge TMDB data, preferring non-empty values
                        for key, value in film['tmdb'].items():
                            if value and (key not in existing_film['tmdb'] or not existing_film['tmdb'][key]):
                                existing_film['tmdb'][key] = value
                
                print(f"  🎭 Merged multi-cinema film: {film.get('title', 'Unknown')} (now at {len(existing_film['data_sources'])} cinemas)")
                
            else:
                # Add new film with proper structure for potential future merging
                new_film = {**film}
                new_film['data_sources'] = [film.get('data_source')] if film.get('data_source') else []
                new_film['urls'] = [film.get('url')] if film.get('url') else []
                
                # Add cinema source info to showtimes
                if new_film.get('showtimes'):
                    for showtime in new_film['showtimes']:
                        showtime['source_cinema'] = film.get('data_source', '')
                        showtime['source_cinemas'] = film.get('cinemas', [])
                        if film.get('url'):
                            showtime['source_url'] = film['url']
                
                film_map[key] = new_film
        
        unique_films = list(film_map.values())
        multi_cinema_count = len([f for f in unique_films if len(f.get('data_sources', [])) > 1])
        
        print(f"  🎬 Processed {len(films)} films into {len(unique_films)} unique films")
        print(f"  🎭 Found {multi_cinema_count} films showing at multiple cinemas")
        print(f"  🔄 Merged {merged_count} duplicate entries")
        
        return unique_films
    
    def embed_css(self, html_content: str, css_content: str) -> str:
        """Embed CSS content into HTML.
        
        Args:
            html_content: Original HTML content
            css_content: CSS content to embed
            
        Returns:
            HTML with embedded CSS
        """
        css_link_pattern = '<link rel="stylesheet" href="assets/styles.css">'
        css_embed = f'<style>\n{css_content}\n</style>'
        
        # Remove any existing embedded CSS styles first
        html_content = re.sub(r'<style>.*?</style>', '', html_content, flags=re.DOTALL)
        # Clean up any duplicate style tags
        html_content = re.sub(r'(<style[^>]*>.*?</style>\s*)+', '', html_content, flags=re.DOTALL)
        
        if css_link_pattern in html_content:
            return html_content.replace(css_link_pattern, css_embed)
        else:
            # Insert before closing </head> tag
            return html_content.replace('</head>', f'    {css_embed}\n</head>')
    
    def embed_javascript(self, html_content: str, js_content: str) -> str:
        """Embed JavaScript content into HTML.
        
        Args:
            html_content: Original HTML content
            js_content: JavaScript content to embed
            
        Returns:
            HTML with embedded JavaScript
        """
        js_link_pattern = '<script src="assets/script.js"></script>'
        js_embed = f'<script>\n{js_content}\n</script>'
        
        # Remove any existing embedded JavaScript (but keep JSON data scripts)
        # More precise pattern to avoid removing scripts with attributes
        html_content = re.sub(r'<script>\s*\n.*?</script>', '', html_content, flags=re.DOTALL)
        # Clean up any duplicate script tags (but preserve JSON data scripts)
        html_content = re.sub(r'(<script>(?!.*type="application/json").*?</script>\s*)+', '', html_content, flags=re.DOTALL)
        
        if js_link_pattern in html_content:
            return html_content.replace(js_link_pattern, js_embed)
        else:
            # Insert before closing </body> tag
            return html_content.replace('</body>', f'    {js_embed}\n</body>')
    
    def embed_json_data(self, html_content: str, json_content: str) -> str:
        """Embed JSON data into HTML.
        
        Args:
            html_content: Original HTML content
            json_content: JSON content to embed
            
        Returns:
            HTML with embedded JSON data
        """
        # Remove any existing JSON data scripts first
        html_content = re.sub(r'<script id="films-data" type="application/json">.*?</script>', '', html_content, flags=re.DOTALL)
        # Also clean up any leftover duplicate patterns
        html_content = re.sub(r'(<script id="films-data"[^>]*>.*?</script>\s*)+', '', html_content, flags=re.DOTALL)
        
        # Create JSON data script element
        json_script = f'<script id="films-data" type="application/json">{json_content}</script>'
        
        # Insert before the main JavaScript (or before </body>)
        if '<script>' in html_content:
            # Insert before the first script tag
            return html_content.replace('<script>', f'    {json_script}\n    <script>')
        else:
            # Insert before closing </body> tag
            return html_content.replace('</body>', f'    {json_script}\n</body>')
    
    def modify_javascript_for_embedded_data(self, js_content: str) -> str:
        """Modify JavaScript to use embedded JSON data instead of fetch.
        
        Args:
            js_content: Original JavaScript content
            
        Returns:
            Modified JavaScript content
        """
        # Complete replacement including initialization calls
        fetch_replacement = '''// Load films from embedded JSON data
async function loadFilms() {
    try {
        // Get embedded JSON data
        const filmsDataElement = document.getElementById('films-data');
        allFilms = JSON.parse(filmsDataElement.textContent);
        
        filteredFilms = [...allFilms];
        
        console.log(`🎉 Successfully loaded ${allFilms.length} films from embedded data`);
        
        // Extract unique cinemas and genres
        allFilms.forEach(film => {
            film.cinemas?.forEach(cinema => {
                if (typeof cinema === 'string') {
                    cinemas.add(cinema);
                } else if (cinema?.name) {
                    cinemas.add(cinema.name);
                }
            });
            film.tmdb?.genres?.forEach(genre => genres.add(genre));
        });
        
        loading.style.display = 'none';
        
        // Initialize display after loading data
        setupEventListeners();
        displayFilms(allFilms);
        updateStats();
        populateFilters();
    } catch (error) {
        console.error('Error loading films:', error);
        loading.innerHTML = `
            <i class="fas fa-exclamation-triangle"></i>
            <span>Error loading films. Please try again later.</span>
        `;
    }
}'''
        
        # Find the start and end of the loadFilms function using regex
        
        # Use a more robust approach to find and replace the entire function
        # Pattern to match the comment and function start
        start_pattern = r'(// Load films from JSON file\s*\n)?async function loadFilms\(\)\s*\{'
        
        # Find function start and end manually with proper brace counting
        lines = js_content.split('\n')
        result_lines = []
        in_load_films = False
        in_dom_ready = False
        brace_count = 0
        skip_comment = False
        
        for i, line in enumerate(lines):
            # Check for the comment line before the function
            if '// Load films from JSON file' in line:
                skip_comment = True
                continue
            
            # Check for DOMContentLoaded event listener and replace it
            if 'document.addEventListener(\'DOMContentLoaded\', async () => {' in line:
                in_dom_ready = True
                brace_count = line.count('{') - line.count('}')
                # Replace with simplified version
                result_lines.append('// Initialize the app')
                result_lines.append('document.addEventListener(\'DOMContentLoaded\', () => {')
                result_lines.append('    loadFilms();')
                result_lines.append('});')
                continue
            
            if in_dom_ready:
                # Count braces to find the end of the event listener
                brace_count += line.count('{') - line.count('}')
                if brace_count <= 0:
                    # End of event listener found
                    in_dom_ready = False
                    # Don't add this line as it's the closing brace
                    continue
                else:
                    # Skip lines inside the event listener
                    continue
            
            # Check for function start
            if 'async function loadFilms()' in line:
                in_load_films = True
                brace_count = line.count('{') - line.count('}')
                # Add our replacement function
                result_lines.append(fetch_replacement)
                continue
            
            if in_load_films:
                # Count braces to find the end of the function
                brace_count += line.count('{') - line.count('}')
                if brace_count <= 0:
                    # End of function found
                    in_load_films = False
                    # Don't add this line as it's the closing brace
                    continue
                else:
                    # Skip lines inside the function
                    continue
            else:
                # Add lines outside the function (unless it's the skipped comment)
                if not (skip_comment and line.strip() == ''):
                    result_lines.append(line)
                skip_comment = False
        
        return '\n'.join(result_lines)
    
    def generate_static_html(self, 
                           html_file: str = "templates/index_template.html",
                           css_file: str = "assets/styles.css", 
                           js_file: str = "assets/script.js",
                           json_file: str = "data/films_with_english_subs.json",
                           output_file: str = "films_static.html") -> None:
        """Generate a static HTML file with all assets embedded.
        
        Args:
            html_file: Base HTML template file
            css_file: CSS file to embed
            js_file: JavaScript file to embed
            json_file: JSON data file to embed
            output_file: Output static HTML file
        """
        print(f"🔧 Generating static HTML file: {output_file}")
        print(f"📄 Base template: {html_file}")
        print(f"🎨 CSS file: {css_file}")
        print(f"📜 JavaScript file: {js_file}")
        print(f"📊 JSON data file: {json_file}")
        
        try:
            # Read all source files
            print("📖 Reading source files...")
            html_content = self.read_file(html_file)
            css_content = self.read_file(css_file)
            js_content = self.read_file(js_file)
            json_content = self.load_json_data(json_file)
            
            # Modify JavaScript to use embedded data
            print("🔄 Modifying JavaScript for embedded data...")
            modified_js = self.modify_javascript_for_embedded_data(js_content)
            
            # Embed all content
            print("🔗 Embedding CSS...")
            static_html = self.embed_css(html_content, css_content)
            
            print("📊 Embedding JSON data...")
            static_html = self.embed_json_data(static_html, json_content)
            
            print("📜 Embedding JavaScript...")
            static_html = self.embed_javascript(static_html, modified_js)
            
            # Write output file
            print(f"💾 Writing static file: {output_file}")
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(static_html)
            
            # Get file size for user info
            file_size = os.path.getsize(output_file)
            size_mb = file_size / (1024 * 1024)
            
            print(f"\n✅ Static HTML file generated: {output_file}")
            print(f"📁 This file contains all necessary code and data embedded within it")
            print(f"🌐 You can now open {output_file} directly in any web browser without a server")
            print(f"📏 File size: {size_mb:.1f} MB")
            
        except Exception as e:
            print(f"❌ Error generating static HTML: {e}")
            raise


    def check_multi_source_setup(self) -> bool:
        """Check that all required files exist for multi-source website."""
        print("🔍 Checking multi-source website setup...")
        
        required_files = [
                        "templates/index_template.html",
            "assets/styles.css",
            "assets/script.js"
        ]
        
        json_files = [
            "data/cinemateket_films_with_english_subs.json",
            "data/biorio_films_with_english_subs.json"
        ]
        
        # Check required files
        missing_files = []
        for file in required_files:
            if not os.path.exists(file):
                missing_files.append(file)
        
        if missing_files:
            print(f"❌ Missing required files: {', '.join(missing_files)}")
            return False
        
        # Check JSON files (at least one should exist)
        existing_json = []
        for file in json_files:
            if os.path.exists(file):
                existing_json.append(file)
        
        if not existing_json:
            print(f"❌ No JSON data files found. Expected one of: {', '.join(json_files)}")
            return False
        
        print("✅ All required files found:")
        for file in required_files:
            print(f"   • {file}")
        
        print("📊 Available data sources:")
        for file in existing_json:
            try:
                with open(file, 'r') as f:
                    data = json.load(f)
                    print(f"   • {file} ({len(data)} films)")
            except Exception as e:
                print(f"   ⚠️  {file} (error reading: {e})")
        
        print(f"\n🌐 Website ready! Open index.html in your browser")
        print(f"💡 Or run: python3 -m http.server 8000")
        
        return True


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate static HTML files with embedded assets",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                                    # Use default files
  %(prog)s --json films_updated.json         # Use different JSON file
  %(prog)s --output my_static_page.html      # Custom output name
  %(prog)s --html template.html --css main.css --js app.js --json data.json
  
Default Files:
  HTML Template:  templates/index_template.html
  CSS Styles:     assets/styles.css
  JavaScript:     assets/script.js
  JSON Data:      data/films_with_english_subs.json
  Output:         films_static.html
        """
    )
    
    parser.add_argument(
        '--html',
        default='templates/index_template.html',
        help='HTML template file (default: templates/index_template.html)'
    )
    
    parser.add_argument(
        '--css',
        default='assets/styles.css',
        help='CSS file to embed (default: assets/styles.css)'
    )
    
    parser.add_argument(
        '--js',
        default='assets/script.js',
        help='JavaScript file to embed (default: assets/script.js)'
    )
    
    parser.add_argument(
        '--json',
        default='data/films_with_english_subs.json',
        help='JSON data file to embed (default: data/films_with_english_subs.json)'
    )
    
    parser.add_argument(
        '-o', '--output',
        default='films_static.html',
        help='Output static HTML file (default: films_static.html)'
    )
    
    parser.add_argument(
        '--check-files',
        action='store_true',
        help='Check if all required files exist without generating'
    )
    
    parser.add_argument(
        '--multi-source',
        action='store_true',
        help='Check multi-source website setup (loads from multiple JSON files)'
    )
    
    args = parser.parse_args()
    
    generator = StaticHTMLGenerator()
    
    if args.check_files:
        print("🔍 Checking required files...")
        files_to_check = [args.html, args.css, args.js, args.json]
        missing_files = []
        
        for file_path in files_to_check:
            if os.path.exists(file_path):
                print(f"  ✅ {file_path}")
            else:
                print(f"  ❌ {file_path}")
                missing_files.append(file_path)
        
        if missing_files:
            print(f"\n❌ Missing files: {', '.join(missing_files)}")
            exit(1)
        else:
            print("\n✅ All required files found!")
            exit(0)
    
    if args.multi_source:
        # Check multi-source setup instead of generating embedded version
        success = generator.check_multi_source_setup()
        exit(0 if success else 1)
    
    try:
        generator.generate_static_html(
            html_file=args.html,
            css_file=args.css,
            js_file=args.js,
            json_file=args.json,
            output_file=args.output
        )
    except Exception as e:
        print(f"\n❌ Failed to generate static HTML: {e}")
        exit(1)


if __name__ == '__main__':
    main()