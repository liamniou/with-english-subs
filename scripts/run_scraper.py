#!/usr/bin/env python3
"""
Simple script to run the Cinemateket scraper.
"""

from scrapers.cinemateket import Cinemateket

def main():
    print("🎬 Running Cinemateket scraper for films with English subtitles...")
    
    # Initialize scraper (default page 100)
    scraper = Cinemateket()
    
    # Run the scraping process
    films = scraper.scrape_films()
    
    # Save results
    scraper.save_results()
    
    print("\n🎉 Scraping completed successfully!")

if __name__ == "__main__":
    main()