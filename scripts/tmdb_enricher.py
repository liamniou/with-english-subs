#!/usr/bin/env python3
"""
TMDb Enricher - Add movie data from The Movie Database API to film listings.

This script reads a JSON file containing film data and enriches it with information
from The Movie Database (TMDb) API, including ratings, genres, and additional metadata.
"""

import json
import os
import re
import argparse
from typing import Dict, List, Optional, Any
import httpx
from dotenv import load_dotenv

class TMDbEnricher:
    """Enriches film data with information from The Movie Database API."""
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize the TMDb enricher.
        
        Args:
            api_key: TMDb API key. If not provided, will try to load from environment.
        """
        load_dotenv()
        self.api_key = api_key or os.getenv('TMDB_API_KEY')
        self.base_url = "https://api.themoviedb.org/3"
        
        if not self.api_key:
            print("⚠️  Warning: No TMDb API key found. Set TMDB_API_KEY environment variable.")
            print("   TMDb enrichment will be skipped.")
        
    def clean_title_for_search(self, title: str) -> str:
        """Clean film title for better TMDb search results.
        
        Args:
            title: Original film title
            
        Returns:
            Cleaned title suitable for TMDb search
        """
        # Remove "Originaltitel:" prefix
        cleaned = re.sub(r'^Originaltitel:\s*', '', title, flags=re.IGNORECASE)
        
        # Remove content in parentheses (like year, country)
        cleaned = re.sub(r'\([^)]*\)', '', cleaned)
        
        # Remove extra whitespace
        cleaned = ' '.join(cleaned.split())
        
        return cleaned.strip()
    
    def search_tmdb_movie(self, title: str) -> Optional[Dict[str, Any]]:
        """Search for a movie on TMDb.
        
        Args:
            title: Movie title to search for
            
        Returns:
            Movie data from TMDb API or None if not found
        """
        if not self.api_key:
            return None
            
        try:
            with httpx.Client() as client:
                response = client.get(
                    f"{self.base_url}/search/movie",
                    params={
                        "api_key": self.api_key,
                        "query": title,
                        "language": "en-US"
                    },
                    timeout=10.0
                )
                response.raise_for_status()
                data = response.json()
                
                if data.get('results'):
                    return data['results'][0]  # Return first result
                    
        except Exception as e:
            print(f"  ❌ TMDb search error for '{title}': {e}")
            
        return None
    
    def get_tmdb_movie_details(self, movie_id: int) -> Optional[Dict[str, Any]]:
        """Get detailed movie information from TMDb.
        
        Args:
            movie_id: TMDb movie ID
            
        Returns:
            Detailed movie data or None if error
        """
        if not self.api_key:
            return None
            
        try:
            with httpx.Client() as client:
                response = client.get(
                    f"{self.base_url}/movie/{movie_id}",
                    params={
                        "api_key": self.api_key,
                        "language": "en-US"
                    },
                    timeout=10.0
                )
                response.raise_for_status()
                return response.json()
                
        except Exception as e:
            print(f"  ❌ TMDb details error for movie {movie_id}: {e}")
            
        return None
    
    def enrich_film(self, film: Dict[str, Any], force_refresh: bool = False) -> Dict[str, Any]:
        """Enrich a single film with TMDb data.
        
        Args:
            film: Film data dictionary
            force_refresh: If True, refresh TMDb data even if it already exists
            
        Returns:
            Film data enriched with TMDb information
        """
        if not self.api_key:
            return film
            
        # Skip if already has TMDb data and not forcing refresh
        if film.get('tmdb') and not force_refresh:
            print(f"  ℹ️  Already has TMDb data, skipping")
            return film
        elif film.get('tmdb') and force_refresh:
            print(f"  🔄 Refreshing existing TMDb data")
            
        # Check if manual TMDb ID is provided
        manual_tmdb_id = film.get('manual_tmdb')
        if manual_tmdb_id:
            print(f"  🎯 Using manual TMDb ID: {manual_tmdb_id}")
            # Get detailed information directly with the manual ID
            details = self.get_tmdb_movie_details(manual_tmdb_id)
            if details:
                print(f"  ✅ Found TMDb match: {details.get('title', 'Unknown')}")
            else:
                print(f"  ❌ Manual TMDb ID {manual_tmdb_id} not found")
                return film
        else:
            # Use automatic search
            title = film.get('title', '')
            if not title:
                print(f"  ⚠️  No title found, skipping TMDb enrichment")
                return film
                
            print(f"  🎬 Searching TMDb for: {self.clean_title_for_search(title)}")
            
            # Search for the movie
            search_result = self.search_tmdb_movie(self.clean_title_for_search(title))
            
            if not search_result:
                print(f"  🔍 No TMDb results found for: {self.clean_title_for_search(title)}")
                return film
                
            print(f"  ✅ Found TMDb match: {search_result.get('title', 'Unknown')}")
            
            # Get detailed information
            details = self.get_tmdb_movie_details(search_result['id'])
        
        if details:
            # Construct full poster and backdrop URLs
            poster_path = details.get('poster_path')
            backdrop_path = details.get('backdrop_path')
            poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None
            backdrop_url = f"https://image.tmdb.org/t/p/w1280{backdrop_path}" if backdrop_path else None
            
            # Add TMDb data to film
            film['tmdb'] = {
                'id': details.get('id'),
                'title': details.get('title'),
                'overview': details.get('overview'),
                'release_date': details.get('release_date'),
                'rating': details.get('vote_average'),
                'vote_count': details.get('vote_count'),
                'genres': [genre['name'] for genre in details.get('genres', [])],
                'poster_path': details.get('poster_path'),
                'poster_url': poster_url,
                'backdrop_path': details.get('backdrop_path'),
                'backdrop_url': backdrop_url,
                'imdb_id': details.get('imdb_id'),
                'runtime': details.get('runtime'),
                'budget': details.get('budget'),
                'revenue': details.get('revenue')
            }
            
            # Display enrichment info
            if film['tmdb'].get('rating'):
                print(f"  ⭐ TMDb Rating: {film['tmdb']['rating']}/10")
            if film['tmdb'].get('genres'):
                print(f"  🎭 Genres: {', '.join(film['tmdb']['genres'])}")
        
        return film
    
    def enrich_films_file(self, input_file: str, output_file: Optional[str] = None, force_refresh: bool = False) -> None:
        """Enrich films in a JSON file with TMDb data.
        
        Args:
            input_file: Path to input JSON file
            output_file: Path to output JSON file. If None, overwrites input file.
            force_refresh: If True, refresh all TMDb data even if it already exists.
        """
        if not os.path.exists(input_file):
            print(f"❌ Error: Input file '{input_file}' not found")
            return
            
        # Load existing data
        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                films = json.load(f)
        except Exception as e:
            print(f"❌ Error reading '{input_file}': {e}")
            return
            
        if not isinstance(films, list):
            print(f"❌ Error: Expected JSON array in '{input_file}'")
            return
            
        print(f"🎬 Starting TMDb enrichment for {len(films)} films...")
        print(f"📖 Reading from: {input_file}")
        
        if force_refresh:
            print(f"🔄 Force refresh mode: Will update all TMDb data")
        
        if not self.api_key:
            print("⚠️  No TMDb API key found - skipping enrichment")
            return
            
        # Enrich each film
        enriched_count = 0
        refreshed_count = 0
        for i, film in enumerate(films, 1):
            film_id = film.get('film_id', f'film_{i}')
            print(f"🎭 Processing film {i}/{len(films)}: {film_id}")
            
            original_tmdb = film.get('tmdb') is not None
            enriched_film = self.enrich_film(film, force_refresh=force_refresh)
            
            if enriched_film.get('tmdb'):
                if not original_tmdb:
                    enriched_count += 1
                elif force_refresh and original_tmdb:
                    refreshed_count += 1
                
        # Save results
        output_path = output_file or input_file
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(films, f, indent=2, ensure_ascii=False)
            print(f"💾 Results saved to: {output_path}")
        except Exception as e:
            print(f"❌ Error writing to '{output_path}': {e}")
            return
            
        # Statistics
        total_with_tmdb = sum(1 for film in films if film.get('tmdb'))
        print(f"\n📈 TMDb Enrichment Complete!")
        print(f"   • Films processed: {len(films)}")
        print(f"   • New TMDb data added: {enriched_count}")
        if force_refresh and refreshed_count > 0:
            print(f"   • TMDb data refreshed: {refreshed_count}")
        print(f"   • Total with TMDb data: {total_with_tmdb}/{len(films)}")
        
        if self.api_key:
            print(f"   • TMDb API: ✅ Enabled")
        else:
            print(f"   • TMDb API: ❌ Disabled (no API key)")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Enrich film data with TMDb information",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s films.json                    # Refresh all TMDb data (default)
  %(prog)s films.json -o enriched.json   # Save to new file
  %(prog)s films.json --skip-existing    # Only add TMDb data to films without it
  %(prog)s films.json --api-key KEY      # Use specific API key
  
Manual TMDb IDs:
  Add "manual_tmdb": 123456 to any film in the JSON to specify exact TMDb ID.
  The enricher will use manual IDs instead of searching automatically.
  
Environment Variables:
  TMDB_API_KEY    TMDb API key (get from https://www.themoviedb.org/settings/api)
        """
    )
    
    parser.add_argument(
        'input_file',
        help='Input JSON file containing film data'
    )
    
    parser.add_argument(
        '-o', '--output',
        help='Output file path (default: overwrite input file)'
    )
    
    parser.add_argument(
        '--api-key',
        help='TMDb API key (overrides TMDB_API_KEY environment variable)'
    )
    
    parser.add_argument(
        '--force-refresh',
        action='store_true',
        default=True,
        help='Force refresh all TMDb data, even if it already exists (default: True)'
    )
    
    parser.add_argument(
        '--skip-existing',
        action='store_true',
        help='Skip films that already have TMDb data (opposite of --force-refresh)'
    )
    
    args = parser.parse_args()
    
    # Handle conflicting options
    if args.skip_existing:
        force_refresh = False
    else:
        force_refresh = args.force_refresh
    
    # Create enricher and process files
    enricher = TMDbEnricher(api_key=args.api_key)
    enricher.enrich_films_file(args.input_file, args.output, force_refresh=force_refresh)


if __name__ == '__main__':
    main()