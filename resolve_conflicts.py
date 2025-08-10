#!/usr/bin/env python3
"""
Script to resolve merge conflicts in JSON files by choosing HEAD version for timestamps
and newer TMDB data, while preserving valid JSON structure.
"""

import re
import sys

def resolve_conflicts_in_file(filepath):
    """Resolve merge conflicts in a single file."""
    print(f"Processing {filepath}...")
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Count conflicts before
    conflicts_before = len(re.findall(r'<<<<<<< HEAD', content))
    print(f"  Found {conflicts_before} conflicts")
    
    # Pattern to match entire conflict blocks
    conflict_pattern = r'<<<<<<< HEAD\n(.*?)\n=======\n(.*?)\n>>>>>>> e04a22f \(Fix generation\)'
    
    def resolve_conflict(match):
        head_content = match.group(1)
        branch_content = match.group(2)
        
        # For scraped_at timestamps, always choose HEAD (newer)
        if '"scraped_at"' in head_content and '"scraped_at"' in branch_content:
            return head_content
        
        # For TMDB rating/vote_count conflicts, choose HEAD (more recent data)
        if ('"rating"' in head_content or '"vote_count"' in head_content) and \
           ('"rating"' in branch_content or '"vote_count"' in branch_content):
            return head_content
            
        # For showtime conflicts, choose HEAD
        if '"datetime"' in head_content and '"datetime"' in branch_content:
            return head_content
            
        # For structural conflicts (like missing commas/brackets), analyze more carefully
        if head_content.strip() == '' and branch_content.strip().startswith('}'):
            # This is likely the zita file end conflict - choose branch content
            return branch_content
        elif '=' in head_content and '}' in branch_content:
            # This is likely the zita file end conflict - choose branch content  
            return branch_content
            
        # Default to HEAD version
        return head_content
    
    # Resolve all conflicts
    resolved_content = re.sub(conflict_pattern, resolve_conflict, content, flags=re.DOTALL)
    
    # Count conflicts after
    conflicts_after = len(re.findall(r'<<<<<<< HEAD', resolved_content))
    print(f"  Resolved {conflicts_before - conflicts_after} conflicts, {conflicts_after} remaining")
    
    # Write back the resolved content
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(resolved_content)
    
    return conflicts_after == 0

def main():
    files_to_process = [
        '/Users/stanislau.liamniou/git/films-with-english-subs/data/biorio_films_with_english_subs.json',
        '/Users/stanislau.liamniou/git/films-with-english-subs/data/cinemateket_films_with_english_subs.json', 
        '/Users/stanislau.liamniou/git/films-with-english-subs/data/fagelbla_films_with_english_subs.json',
        '/Users/stanislau.liamniou/git/films-with-english-subs/data/zita_films_with_english_subs.json'
    ]
    
    all_resolved = True
    for filepath in files_to_process:
        try:
            resolved = resolve_conflicts_in_file(filepath)
            if not resolved:
                all_resolved = False
        except Exception as e:
            print(f"Error processing {filepath}: {e}")
            all_resolved = False
    
    if all_resolved:
        print("All JSON conflicts resolved successfully!")
    else:
        print("Some conflicts remain - manual intervention needed")
    
    return all_resolved

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)