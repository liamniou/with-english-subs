#!/usr/bin/env python3
"""
Generic JSON field translator using Google Gemini API.
Translate any specified text fields in JSON files from one language to another.
"""

import json
import os
import sys
import httpx
from datetime import datetime
import argparse


class JSONFieldTranslator:
    def __init__(self, gemini_api_key=None, source_language="Swedish", target_language="English"):
        """Initialize the translator with Gemini API key and language settings."""
        self.gemini_api_key = gemini_api_key or os.getenv('GEMINI_API_KEY')
        if not self.gemini_api_key:
            raise ValueError("Gemini API key is required. Set GEMINI_API_KEY environment variable or pass it as argument.")
        
        self.source_language = source_language
        self.target_language = target_language
    
    def translate_batch(self, texts_to_translate):
        """
        Translate multiple texts using Google Gemini API in a single request.
        
        Args:
            texts_to_translate (list): List of texts to translate
            
        Returns:
            list: List of translated texts in the same order
        """
        if not texts_to_translate:
            return []
            
        # Filter out empty texts but keep track of their positions
        text_map = {}
        valid_texts = []
        for i, text in enumerate(texts_to_translate):
            if text and text.strip():
                text_map[len(valid_texts)] = i
                valid_texts.append(text)
            
        if not valid_texts:
            return texts_to_translate
            
        try:
            # Prepare the API request
            api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={self.gemini_api_key}"
            
            headers = {
                'Content-Type': 'application/json',
            }
            
            # Create numbered list for batch translation
            numbered_texts = []
            for i, text in enumerate(valid_texts, 1):
                numbered_texts.append(f"{i}. {text}")
            
            prompt = f"""Translate these {self.source_language} texts to {self.target_language}. Keep the format and structure exactly the same for each text, only translate the words. If there are dates, times, numbers, or proper names, preserve their format. Be concise and natural.

Maintain the numbered format in your response.

{self.source_language} texts:
{chr(10).join(numbered_texts)}

Return only the {self.target_language} translations in the same numbered format without any explanation."""
            
            payload = {
                "contents": [{
                    "parts": [{
                        "text": prompt
                    }]
                }],
                "generationConfig": {
                    "temperature": 0.1,
                    "maxOutputTokens": 2000,
                    "topP": 0.8
                }
            }
            
            with httpx.Client(timeout=60.0) as client:  # Increased timeout
                response = client.post(api_url, headers=headers, json=payload)
                response.raise_for_status()
                
                result = response.json()
                translated_response = result['candidates'][0]['content']['parts'][0]['text'].strip()
                
                # Parse the numbered response
                translated_texts = self._parse_numbered_response(translated_response, len(valid_texts))
                
                # Reconstruct the full list with original empty texts
                result_texts = texts_to_translate.copy()
                for valid_idx, original_idx in text_map.items():
                    if valid_idx < len(translated_texts):
                        result_texts[original_idx] = translated_texts[valid_idx]
                
                return result_texts
                
        except Exception as e:
            print(f"⚠️  Batch translation failed: {e}")
            print(f"   Falling back to individual translations...")
            # Fallback to individual translations
            return [self.translate_single_text(text) for text in texts_to_translate]
    
    def _parse_numbered_response(self, response, expected_count):
        """Parse numbered response from API."""
        lines = response.split('\n')
        translations = []
        
        for line in lines:
            line = line.strip()
            if line and '. ' in line:
                # Extract text after the number and period
                parts = line.split('. ', 1)
                if len(parts) == 2 and parts[0].isdigit():
                    translation = parts[1].strip('"\'')
                    translations.append(translation)
        
        # If we don't get the expected count, pad with original texts
        while len(translations) < expected_count:
            translations.append("")
            
        return translations[:expected_count]
    
    def translate_single_text(self, text_to_translate):
        """
        Translate single text using Google Gemini API (fallback method).
        
        Args:
            text_to_translate (str): Text to translate
            
        Returns:
            str: Translated text
        """
        if not text_to_translate or not text_to_translate.strip():
            return text_to_translate
            
        try:
            # Prepare the API request
            api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={self.gemini_api_key}"
            
            headers = {
                'Content-Type': 'application/json',
            }
            
            prompt = f"""Translate this {self.source_language} text to {self.target_language}. Keep the format and structure exactly the same, only translate the words. If there are dates, times, numbers, or proper names, preserve their format. Be concise and natural.

{self.source_language} text: "{text_to_translate}"

Return only the {self.target_language} translation without any explanation or quotes."""
            
            payload = {
                "contents": [{
                    "parts": [{
                        "text": prompt
                    }]
                }],
                "generationConfig": {
                    "temperature": 0.1,
                    "maxOutputTokens": 200,
                    "topP": 0.8
                }
            }
            
            with httpx.Client(timeout=30.0) as client:  # Increased timeout
                response = client.post(api_url, headers=headers, json=payload)
                response.raise_for_status()
                
                result = response.json()
                translated_text = result['candidates'][0]['content']['parts'][0]['text'].strip()
                
                # Clean up any quotes that might be added by the API
                translated_text = translated_text.strip('"\'')
                
                return translated_text
                
        except Exception as e:
            print(f"⚠️  Translation failed for '{text_to_translate[:50]}...': {e}")
            return text_to_translate  # Return original text if translation fails
    
    def _translate_nested_field(self, data, field_path, item_index=None, total_items=None):
        """
        Translate a field that may be nested in the data structure.
        
        Args:
            data (dict/list): The data containing the field
            field_path (str): Dot notation path to the field (e.g., 'showtimes.display_text')
            item_index (int): Index of current item being processed
            total_items (int): Total number of items
            
        Returns:
            int: Number of fields translated
        """
        path_parts = field_path.split('.')
        translated_count = 0
        
        def navigate_and_translate(obj, parts, current_path=""):
            nonlocal translated_count
            
            if not parts:
                return 0
                
            current_part = parts[0]
            remaining_parts = parts[1:]
            
            if isinstance(obj, dict):
                if current_part in obj:
                    if not remaining_parts:
                        # This is the final field to translate
                        field_value = obj[current_part]
                        if isinstance(field_value, str) and field_value.strip():
                            # Check if already translated
                            original_key = f"original_{current_part}"
                            if original_key in obj:
                                print(f"   ⏭️  Field '{current_path}.{current_part}' already translated, skipping")
                                return 0
                            
                            print(f"   🔄 Translating '{current_path}.{current_part}': '{field_value[:30]}...'")
                            
                            # Translate the text
                            translated_text = self.translate_text(field_value)
                            
                            # Update with translation
                            obj[original_key] = field_value  # Keep original
                            obj[current_part] = translated_text  # Replace with translation
                            
                            print(f"   ✅ '{field_value[:30]}...' → '{translated_text[:30]}...'")
                            return 1
                    else:
                        # Navigate deeper
                        return navigate_and_translate(obj[current_part], remaining_parts, f"{current_path}.{current_part}" if current_path else current_part)
                        
            elif isinstance(obj, list):
                count = 0
                for i, item in enumerate(obj):
                    count += navigate_and_translate(item, parts, f"{current_path}[{i}]" if current_path else f"[{i}]")
                return count
                
            return 0
        
        return navigate_and_translate(data, path_parts)
    
    def _collect_texts_for_translation(self, data, field_path, text_references):
        """
        Collect all texts that need translation from the specified field path.
        
        Args:
            data (dict/list): The data containing the field
            field_path (str): Dot notation path to the field
            text_references (list): List to append (object, field_key, text) tuples
        """
        path_parts = field_path.split('.')
        
        def navigate_and_collect(obj, parts, current_path=""):
            if not parts:
                return
                
            current_part = parts[0]
            remaining_parts = parts[1:]
            
            if isinstance(obj, dict):
                if current_part in obj:
                    if not remaining_parts:
                        # This is the final field to collect
                        field_value = obj[current_part]
                        if isinstance(field_value, str) and field_value.strip():
                            # Check if already translated
                            original_key = f"original_{current_part}"
                            if original_key not in obj:
                                text_references.append((obj, current_part, field_value))
                    else:
                        # Navigate deeper
                        navigate_and_collect(obj[current_part], remaining_parts, f"{current_path}.{current_part}" if current_path else current_part)
                        
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    navigate_and_collect(item, parts, f"{current_path}[{i}]" if current_path else f"[{i}]")
        
        navigate_and_collect(data, path_parts)
    
    def translate_json_file(self, input_file, output_file=None, field_paths=None, batch_size=50):
        """
        Translate specified field paths in a JSON file using batch processing.
        
        Args:
            input_file (str): Path to input JSON file
            output_file (str): Path to output JSON file (optional)
            field_paths (list): List of dot-notation field paths to translate
            batch_size (int): Number of texts to translate in one API call
        """
        if not os.path.exists(input_file):
            raise FileNotFoundError(f"Input file not found: {input_file}")
        
        # Set default field paths
        if field_paths is None:
            field_paths = ['showtimes.display_text']  # Default for backward compatibility
        
        print(f"🎬 Loading data from: {input_file}")
        print(f"🔧 Field paths to translate: {', '.join(field_paths)}")
        print(f"🌐 Translation: {self.source_language} → {self.target_language}")
        print(f"📦 Batch size: {batch_size}")
        
        # Load the JSON file
        with open(input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Handle both list of objects and single object
        if isinstance(data, list):
            items = data
            total_items = len(items)
            print(f"📋 Found {total_items} items to process")
        else:
            items = [data]
            total_items = 1
            print(f"📋 Found 1 item to process")
        
        # First pass: collect all texts to translate
        print(f"🔍 Collecting texts to translate...")
        text_references = []  # List of (object, field_key, original_text)
        
        for item in items:
            for field_path in field_paths:
                self._collect_texts_for_translation(item, field_path, text_references)
        
        total_texts = len(text_references)
        print(f"📝 Found {total_texts} texts to translate")
        
        if total_texts == 0:
            print(f"⚠️  No texts found to translate")
            return input_file
        
        # Extract just the texts for batch translation
        texts_to_translate = [ref[2] for ref in text_references]
        
        # Translate in batches
        print(f"🚀 Starting batch translation...")
        all_translations = []
        
        for i in range(0, len(texts_to_translate), batch_size):
            batch = texts_to_translate[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (len(texts_to_translate) + batch_size - 1) // batch_size
            
            print(f"   📦 Processing batch {batch_num}/{total_batches} ({len(batch)} texts)...")
            
            batch_translations = self.translate_batch(batch)
            all_translations.extend(batch_translations)
            
            # Small delay between batches to avoid rate limiting
            if i + batch_size < len(texts_to_translate):
                import time
                time.sleep(2)  # Increased delay to 2 seconds
        
        # Apply translations back to the data
        print(f"📝 Applying translations to data...")
        translated_count = 0
        
        for i, (obj, field_key, original_text) in enumerate(text_references):
            if i < len(all_translations):
                translated_text = all_translations[i]
                if translated_text and translated_text != original_text:
                    # Store original and update with translation
                    obj[f"original_{field_key}"] = original_text
                    obj[field_key] = translated_text
                    translated_count += 1
        
        # Determine output file
        if not output_file:
            base_name = os.path.splitext(input_file)[0]
            output_file = f"{base_name}_translated.json"
        
        # Save the translated file
        print(f"💾 Saving translated data to: {output_file}")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"📊 TRANSLATION COMPLETE!")
        print(f"✅ Translated {translated_count} fields")
        
        return output_file


def main():
    parser = argparse.ArgumentParser(
        description='Translate text fields in JSON files using Gemini API',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Field path examples:
  title                    - Translate top-level 'title' field
  showtimes.display_text   - Translate 'display_text' in 'showtimes' array
  meta.description         - Translate nested 'description' in 'meta' object
  items.name               - Translate 'name' field in 'items' array
  
Usage examples:
  python3 translate_json_fields.py data.json
  python3 translate_json_fields.py data.json -f title,description
  python3 translate_json_fields.py data.json -f "showtimes.display_text,cinemas.name"
  python3 translate_json_fields.py data.json --source Swedish --target English
  python3 translate_json_fields.py data.json --fields title -k "your_api_key"
        """
    )
    
    parser.add_argument('input_file', help='Path to input JSON file')
    parser.add_argument('-o', '--output', help='Path to output JSON file (optional)')
    parser.add_argument('-k', '--api-key', help='Gemini API key (or set GEMINI_API_KEY env variable)')
    parser.add_argument('-f', '--fields', 
                       help='Comma-separated list of field paths to translate (default: showtimes.display_text)',
                       default='showtimes.display_text')
    parser.add_argument('--source', 
                       help='Source language (default: Swedish)',
                       default='Swedish')
    parser.add_argument('--target', 
                       help='Target language (default: English)', 
                       default='English')
    parser.add_argument('-b', '--batch-size',
                       type=int,
                       help='Number of texts to translate in one API call (default: 50)',
                       default=50)
    
    args = parser.parse_args()
    
    try:
        # Parse field paths to translate
        field_paths = [field.strip() for field in args.fields.split(',') if field.strip()]
        
        print(f"🎯 Will translate field paths: {', '.join(field_paths)}")
        
        # Initialize translator
        translator = JSONFieldTranslator(
            gemini_api_key=args.api_key,
            source_language=args.source,
            target_language=args.target
        )
        
        # Translate the file
        output_file = translator.translate_json_file(args.input_file, args.output, field_paths, args.batch_size)
        
        print(f"\n🎉 Translation completed successfully!")
        print(f"📁 Translated file: {output_file}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        print(f"💡 This could be due to:")
        print(f"   - Network connectivity issues")
        print(f"   - API rate limiting")
        print(f"   - Invalid API key")
        print(f"   - Malformed JSON data")
        print(f"   - API service temporarily unavailable")
        print(f"🔄 The pipeline will continue with the next scraper...")
        sys.exit(1)


if __name__ == "__main__":
    main()