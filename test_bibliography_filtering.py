#!/usr/bin/env python3
"""
Bibliography Filtering Test

This script tests the improved bibliography and reference filtering on various
academic or reference-heavy web pages.
"""

import argparse
import logging
import time
import json
import sys
from datetime import datetime
import os

from DocumentProcessor import WebPageSource
from utils import setup_logging

# Test URLs with different types of bibliographies and reference sections
TEST_URLS = [
    # Academic papers with formal citations
    "https://en.wikipedia.org/wiki/Bibliography",
    
    # Articles with many external links
    "https://en.wikipedia.org/wiki/List_of_programming_languages",
    
    # Pages with mixtures of content and references
    "https://en.wikipedia.org/wiki/Machine_learning",
    
    # Very citation-heavy page 
    "https://en.wikipedia.org/wiki/Citation"
]

# File to store the latest chunk log filename
LATEST_CHUNK_LOG_FILE = "latest_chunk_log.txt"

def process_url_and_report(url, verbose=False):
    """Process a URL and report on how well bibliography sections were filtered."""
    print(f"\nProcessing: {url}")
    start_time = time.time()
    
    try:
        # Initialize and process with WebPageSource
        source = WebPageSource(url)
        content = source.fetch_content()
        
        if not content.get('chunks') and not content.get('chunk_log'): # Check if either chunks or log exists
            print(f"  Error: Failed to extract chunks or create log")
            return None
        
        # Extract key metrics
        raw_chunks_count = len(content.get('classification_info', {})) # Use classification_info for total count
        kept_chunks = content.get('chunks', [])
        
        # Calculate performance metrics
        total_chunks = raw_chunks_count
        kept_count = len(kept_chunks)
        discard_count = total_chunks - kept_count
        discard_ratio = discard_count / total_chunks if total_chunks > 0 else 0
        
        # Get discard reasons
        discard_reasons = {}
        if 'classification_info' in content:
            for idx, info in content['classification_info'].items():
                if info['decision'] == 'DISCARD':
                    reason = info['reason']
                    discard_reasons[reason] = discard_reasons.get(reason, 0) + 1
        
        # Print results
        print(f"  Title: {content.get('title', 'Unknown')}")
        print(f"  Processing time: {time.time() - start_time:.2f} seconds")
        print(f"  Total chunks: {total_chunks}")
        print(f"  Kept chunks: {kept_count} ({kept_count/total_chunks*100:.1f}%)")
        print(f"  Discarded chunks: {discard_count} ({discard_ratio*100:.1f}%)")
        
        if discard_reasons:
            print("\n  Discard reasons:")
            for reason, count in discard_reasons.items():
                print(f"    - {reason}: {count} chunks")
        
        # Show chunk log location and save it to a file
        chunk_log = content.get('chunk_log')
        if chunk_log:
            print(f"\n  Chunk log: {chunk_log}")
            with open(LATEST_CHUNK_LOG_FILE, 'w') as f_out:
                f_out.write(chunk_log)
        
        return {
            'url': url,
            'title': content.get('title', 'Unknown'),
            'total_chunks': total_chunks,
            'kept_chunks': kept_count,
            'discard_ratio': discard_ratio,
            'discard_reasons': discard_reasons,
            'chunk_log': chunk_log
        }
    
    except Exception as e:
        print(f"  Error: {str(e)}")
        return None

def main():
    parser = argparse.ArgumentParser(description="Test bibliography and reference filtering")
    parser.add_argument("--url", help="Process a single URL instead of test set")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show more detailed output")
    parser.add_argument("--all", action="store_true", help="Run all test URLs")
    
    args = parser.parse_args()
    
    # Set up logging
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = f"bibliography_test_{timestamp}.log"
    # Ensure log file is distinct from main document processor log
    # if 'run_document_processor' in logging.root.manager.loggerDict:
    #     del logging.root.manager.loggerDict['run_document_processor'] 
    setup_logging(debug_mode=args.verbose, log_file=log_file)
    
    results = []
    
    if args.url:
        # Process single URL
        result = process_url_and_report(args.url, args.verbose)
        if result:
            results.append(result)
    elif args.all:
        # Process all test URLs
        for url in TEST_URLS:
            result = process_url_and_report(url, args.verbose)
            if result:
                results.append(result)
    else:
        # Process just one test URL as a sample
        url = TEST_URLS[0]
        print(f"Testing with one sample URL: {url}")
        print("(Use --all to test all URLs or --url to specify a custom URL)")
        result = process_url_and_report(url, args.verbose)
        if result:
            results.append(result)
    
    # Save results
    if results:
        output_file = f"bibliography_filtering_results_{timestamp}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to {output_file}")

if __name__ == "__main__":
    main() 