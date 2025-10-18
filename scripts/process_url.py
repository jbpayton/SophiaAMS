#!/usr/bin/env python3
"""
URL Processing Tool for SophiaAMS

This script extracts, processes, and displays content from a given URL using the DocumentProcessor.
It shows chunking results without needing to ingest the content into a knowledge graph.
"""

import argparse
import logging
import os
import sys
import time
import webbrowser
import subprocess
from datetime import datetime

from DocumentProcessor import WebPageSource
from utils import setup_logging

def process_url(url, debug=False, open_log=False, show_all_chunks=False):
    """Process a URL and display the results."""
    # Set up logging
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = f"url_processor_{timestamp}.log"
    setup_logging(debug_mode=debug, log_file=log_file)
    
    logging.info(f"Processing URL: {url}")
    start_time = time.time()
    
    try:
        # Initialize WebPageSource
        source = WebPageSource(url)
        
        # Fetch content
        logging.info("Fetching and processing content...")
        content = source.fetch_content()
        
        if not content.get('chunks'):
            logging.error("Failed to extract chunks from the page")
            return
        
        # Print results
        total_chunks = len(content.get('raw_chunks', []))
        kept_chunks = len(content.get('chunks', []))
        
        print("\n" + "="*80)
        print(f"URL: {url}")
        print(f"Title: {content.get('title', 'Unknown')}")
        print(f"Processing time: {time.time() - start_time:.2f} seconds")
        print(f"Character count: {len(content.get('text', ''))}")
        print(f"Total chunks: {total_chunks}")
        print(f"Kept chunks: {kept_chunks} ({kept_chunks/total_chunks*100:.1f}%)")
        print(f"Discarded chunks: {total_chunks - kept_chunks}")
        print("="*80)
        
        # Show chunk log location
        chunk_log = content.get('chunk_log')
        if chunk_log:
            print(f"\nDetailed chunk log saved to: {chunk_log}")
            print(f"The log shows each chunk and why it was kept or discarded.")
            
            # Open the log file if requested
            if open_log:
                print("\nOpening chunk log...")
                try:
                    # Try platform-specific methods first
                    if sys.platform == 'win32':
                        os.startfile(chunk_log)
                    elif sys.platform == 'darwin':  # macOS
                        subprocess.call(['open', chunk_log])
                    else:  # Linux and other Unix
                        subprocess.call(['xdg-open', chunk_log])
                except Exception as e:
                    print(f"Could not open log file automatically: {str(e)}")
                    print(f"Please open {chunk_log} manually.")
        
        # Preview chunks
        if show_all_chunks:
            print("\nAll chunks preview:")
            for i, chunk in enumerate(content.get('chunks', [])):
                preview = chunk[:100] + "..." if len(chunk) > 100 else chunk
                print(f"\nChunk {i+1}:")
                print("-"*40)
                print(preview)
                print("-"*40)
        else:
            print("\nFirst 3 chunks preview:")
            for i, chunk in enumerate(content.get('chunks', [])[:3]):
                preview = chunk[:150] + "..." if len(chunk) > 150 else chunk
                print(f"\nChunk {i+1}:")
                print("-"*40)
                print(preview)
                print("-"*40)
        
        return content
        
    except Exception as e:
        logging.error(f"Error processing URL: {str(e)}")
        logging.debug("Error details:", exc_info=True)
        print(f"\nError: {str(e)}")
        return None

def main():
    parser = argparse.ArgumentParser(description="Process a URL with SophiaAMS DocumentProcessor")
    parser.add_argument("url", help="URL to process")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--open-log", action="store_true", help="Automatically open the chunk log file")
    parser.add_argument("--show-all", action="store_true", help="Show all chunks in preview instead of just the first 3")
    
    args = parser.parse_args()
    process_url(args.url, args.debug, args.open_log, args.show_all)

if __name__ == "__main__":
    main() 