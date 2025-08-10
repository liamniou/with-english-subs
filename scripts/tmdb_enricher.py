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
    
    def _extract_year_from_film(self, film: Dict[str, Any]) -> Optional[str]:
        """Extract year from film data if available.
        
        Args:
            film: Film data dictionary
            
        Returns:
            Year as string or None if not found
        """
        import re
        
        # Check for explicit year field
        if 'year' in film and film['year']:
            return str(film['year'])
        
        # Try to extract year from title (look for 4-digit years)
        title = film.get('title', '')
        year_match = re.search(r'\b(19|20)\d{2}\b', title)
        if year_match:
            return year_match.group(0)
        
        # Try to extract from genre/description fields that might contain year
        for field in ['genre', 'description', 'details']:
            if field in film and film[field]:
                year_match = re.search(r'\b(19|20)\d{2}\b', str(film[field]))
                if year_match:
                    return year_match.group(0)
        
        return None
    
    def search_tmdb_movie(self, title: str, director: str = None, year: str = None) -> Optional[Dict[str, Any]]:
        """Search for a movie on TMDb using title and optionally year, then filter by director.
        
        Args:
            title: Movie title to search for
            director: Movie director name (optional, used for better matching)
            year: Release year (optional, helps narrow results)
            
        Returns:
            Movie data from TMDb API or None if not found
        """
        if not self.api_key:
            return None
            
        try:
            # Step 1: Search for movie by title (and year if available)
            search_params = {
                "api_key": self.api_key,
                "query": title,
                "language": "en-US"
            }
            
            if year:
                search_params["year"] = year
                print(f"  🔍 Searching TMDb: '{title}' ({year})")
            else:
                print(f"  🔍 Searching TMDb: '{title}'")
                
            with httpx.Client() as client:
                response = client.get(
                    f"{self.base_url}/search/movie",
                    params=search_params,
                    timeout=10.0
                )
                response.raise_for_status()
                data = response.json()
                
                if not data.get('results'):
                    print(f"  ❌ No TMDb results found for '{title}'")
                    return None
                
                results = data['results']
                print(f"  📋 Found {len(results)} potential matches")
                
                # Step 2: If we have multiple results and a director, try director filmography search
                if len(results) > 1 and director and director.strip():
                    print(f"  🔄 Multiple results found, searching director's filmography...")
                    
                    # Search for director and look through their filmography
                    director_data = self.search_tmdb_director(director)
                    if director_data:
                        director_id = director_data.get('id')
                        if director_id:
                            filmography_match = self.search_in_director_filmography(director_id, title, year)
                            if filmography_match:
                                return filmography_match
                            else:
                                print(f"  🔄 No filmography match, falling back to credits-based search")
                    
                    # Fallback: use original credits-based method
                    print(f"  🎭 Filtering by director credits: '{director}'")
                    best_match = self._find_best_match_by_director(results, director)
                    if best_match:
                        return best_match
                    else:
                        print(f"  ⚠️  No director match found, using first result")
                        return results[0]
                        
                elif director and director.strip():
                    # Single result but we have director - still validate with credits
                    print(f"  🎭 Validating single result with director: '{director}'")
                    best_match = self._find_best_match_by_director(results, director)
                    if best_match:
                        return best_match
                    else:
                        print(f"  ⚠️  Director validation failed, using result anyway")
                        return results[0]
                else:
                    # No director to match against, return first result
                    return results[0]
                    
        except Exception as e:
            print(f"  ❌ TMDb search error for '{title}': {e}")
            
        return None

    def search_tmdb_director(self, director_name: str) -> Optional[Dict[str, Any]]:
        """Search for a director by name on TMDb.
        
        Args:
            director_name: Director name to search for
            
        Returns:
            Director data from TMDb API or None if not found
        """
        if not self.api_key or not director_name:
            return None
            
        try:
            search_params = {
                "api_key": self.api_key,
                "query": director_name,
                "language": "en-US"
            }
            
            print(f"  🎭 Searching for director: '{director_name}'")
            
            with httpx.Client() as client:
                response = client.get(
                    f"{self.base_url}/search/person",
                    params=search_params,
                    timeout=10.0
                )
                response.raise_for_status()
                data = response.json()
                
                if not data.get('results'):
                    print(f"  ❌ No director found for '{director_name}'")
                    return None
                
                # Look for directors (not actors)
                directors = [person for person in data['results'] 
                           if person.get('known_for_department') == 'Directing']
                
                if not directors:
                    # Fallback: use first person if no explicit directors found
                    directors = data['results']
                
                if directors:
                    director = directors[0]
                    print(f"  ✅ Found director: {director.get('name')} (ID: {director.get('id')})")
                    return director
                else:
                    print(f"  ❌ No suitable director found for '{director_name}'")
                    return None
                    
        except Exception as e:
            print(f"  ❌ Error searching for director '{director_name}': {e}")
            
        return None

    def search_in_director_filmography(self, director_id: int, movie_title: str, year: str = None) -> Optional[Dict[str, Any]]:
        """Search for a movie in director's filmography.
        
        Args:
            director_id: TMDb director ID
            movie_title: Movie title to search for
            year: Optional year to help with matching
            
        Returns:
            Movie data from director's filmography or None if not found
        """
        if not self.api_key or not director_id:
            return None
            
        try:
            with httpx.Client() as client:
                response = client.get(
                    f"{self.base_url}/person/{director_id}/movie_credits",
                    params={"api_key": self.api_key},
                    timeout=10.0
                )
                response.raise_for_status()
                data = response.json()
                
                crew_movies = data.get('crew', [])
                # Filter for movies where this person was director
                directed_movies = [movie for movie in crew_movies 
                                 if movie.get('job') == 'Director']
                
                print(f"  🎬 Found {len(directed_movies)} movies directed by this person")
                
                if not directed_movies:
                    return None
                
                # Clean the search title for comparison
                clean_search_title = self.clean_title_for_search(movie_title).lower()
                
                # Look for exact or close matches
                best_match = None
                best_score = 0
                
                for movie in directed_movies:
                    tmdb_title = movie.get('title', '').lower()
                    original_title = movie.get('original_title', '').lower()
                    
                    # Calculate match score
                    score = 0
                    
                    # Exact title match gets highest score
                    if clean_search_title == tmdb_title or clean_search_title == original_title:
                        score = 100
                    # Partial match
                    elif (clean_search_title in tmdb_title or tmdb_title in clean_search_title or
                          clean_search_title in original_title or original_title in clean_search_title):
                        score = 50
                    # Word overlap
                    else:
                        search_words = set(clean_search_title.split())
                        title_words = set(tmdb_title.split())
                        original_words = set(original_title.split())
                        
                        title_overlap = len(search_words & title_words) / max(len(search_words), 1)
                        original_overlap = len(search_words & original_words) / max(len(search_words), 1)
                        max_overlap = max(title_overlap, original_overlap)
                        
                        if max_overlap > 0.5:  # At least 50% word overlap
                            score = int(max_overlap * 30)
                    
                    # Year bonus
                    if year and movie.get('release_date'):
                        movie_year = movie['release_date'][:4]
                        if movie_year == year:
                            score += 20
                    
                    if score > best_score and score >= 30:  # Minimum threshold
                        best_score = score
                        best_match = movie
                        
                if best_match:
                    print(f"  ✅ Found match in filmography: '{best_match.get('title')}' (score: {best_score})")
                    return best_match
                else:
                    print(f"  ❌ No matching movie found in director's filmography")
                    return None
                    
        except Exception as e:
            print(f"  ❌ Error searching director's filmography: {e}")
            
        return None
    
    def _find_best_match_by_director(self, results: List[Dict[str, Any]], director: str) -> Optional[Dict[str, Any]]:
        """Find the best movie match based on director information.
        
        Args:
            results: List of TMDb search results
            director: Director name to match against
            
        Returns:
            Best matching movie or None
        """
        if not director:
            return None
            
        director_lower = director.lower().strip()
        
        for movie in results:
            movie_id = movie.get('id')
            if not movie_id:
                continue
                
            try:
                # Get movie credits to check director
                with httpx.Client() as client:
                    credits_response = client.get(
                        f"{self.base_url}/movie/{movie_id}/credits",
                        params={"api_key": self.api_key},
                        timeout=10.0
                    )
                    credits_response.raise_for_status()
                    credits_data = credits_response.json()
                    
                    # Check if any director matches
                    crew = credits_data.get('crew', [])
                    for person in crew:
                        if person.get('job') == 'Director':
                            tmdb_director = person.get('name', '').lower().strip()
                            
                            # Check for exact match or partial match
                            if (director_lower in tmdb_director or 
                                tmdb_director in director_lower or
                                director_lower.split()[-1] in tmdb_director):  # Last name match
                                print(f"  ✅ Matched director: '{director}' ≈ '{person.get('name')}'")
                                return movie
                                
            except Exception as e:
                print(f"  ⚠️  Error checking director for movie ID {movie_id}: {e}")
                continue
        
        print(f"  ⚠️  No director match found for '{director}', using first result")
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
                
            director = film.get('director', '')
            clean_title = self.clean_title_for_search(title)
            
            # Try to extract year from title or other fields
            year = self._extract_year_from_film(film)
            
            # Search for the movie, including director and year if available
            search_result = self.search_tmdb_movie(clean_title, director, year)
            
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