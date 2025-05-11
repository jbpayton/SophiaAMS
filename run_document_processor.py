#!/usr/bin/env python3
"""
SophiaAMS Document Processor Runner

Process documents from URLs, files, or text with improved content filtering.
"""

import argparse
import logging
import os
import time
import sys
import json
from datetime import datetime
from typing import Dict, List

from DocumentProcessor import WebPageSource, DocumentProcessor
from utils import setup_logging
try:
    from AssociativeSemanticMemory import AssociativeSemanticMemory
    from VectorKnowledgeGraph import VectorKnowledgeGraph
    MEMORY_AVAILABLE = True
except ImportError:
    MEMORY_AVAILABLE = False

def process_url(url: str, options: Dict) -> Dict:
    """Process a single URL and return results."""
    logger = logging.getLogger('run_document_processor')
    logger.info(f"Processing URL: {url}")
    start_time = time.time()
    
    try:
        # Initialize WebPageSource with config
        source = WebPageSource(url, 
                              chunk_size=options.get('chunk_size', 1024),
                              overlap=options.get('overlap', 128))
        
        # If ingest option is enabled, use DocumentProcessor
        if options.get('ingest', False) and MEMORY_AVAILABLE:
            # Initialize semantic memory
            logger.info("Initializing semantic memory...")
            kgraph = VectorKnowledgeGraph(path=options.get('knowledge_base', "knowledge_graph"))
            memory = AssociativeSemanticMemory(kgraph)
            processor = DocumentProcessor(memory)
            
            # Process document
            logger.info("Processing and ingesting document...")
            result = processor.process_document(source)
            
            # Add processing time
            result['processing_time'] = time.time() - start_time
            return result
        else:
            # Just fetch and process without ingesting
            logger.info("Fetching and filtering content...")
            content = source.fetch_content()
            
            # Calculate stats
            total_chunks = len(content.get('raw_chunks', []))
            kept_chunks = len(content.get('chunks', []))
            
            # Show content statistics
            logger.info(f"URL: {url}")
            logger.info(f"Title: {content.get('title', 'Unknown')}")
            logger.info(f"Extracted text: {len(content.get('text', ''))} characters")
            logger.info(f"Total chunks: {total_chunks}")
            logger.info(f"Kept chunks: {kept_chunks}")
            logger.info(f"Discard ratio: {(total_chunks - kept_chunks) / total_chunks:.1%}")
            
            if options.get('verbose', False):
                # Detailed statistics about filtering
                if 'classification_info' in content:
                    discard_reasons = {}
                    for _, info in content['classification_info'].items():
                        if info['decision'] == 'DISCARD':
                            reason = info['reason']
                            discard_reasons[reason] = discard_reasons.get(reason, 0) + 1
                    
                    logger.info("Discard reasons:")
                    for reason, count in discard_reasons.items():
                        logger.info(f"  - {reason}: {count} chunks")
            
            # Show log file
            if 'chunk_log' in content:
                logger.info(f"Chunk log saved to: {content['chunk_log']}")
                
                # Open log file if requested
                if options.get('open_log', False):
                    logger.info("Opening chunk log file...")
                    try:
                        if sys.platform == 'win32':
                            os.startfile(content['chunk_log'])
                        elif sys.platform == 'darwin':  # macOS
                            os.system(f'open "{content["chunk_log"]}"')
                        else:  # Linux
                            os.system(f'xdg-open "{content["chunk_log"]}"')
                    except Exception as e:
                        logger.error(f"Could not open chunk log: {str(e)}")
            
            # Construct result
            result = {
                'success': True,
                'title': content.get('title', ''),
                'url': url,
                'total_chunks': total_chunks,
                'kept_chunks': kept_chunks,
                'discard_ratio': (total_chunks - kept_chunks) / total_chunks if total_chunks > 0 else 0,
                'chunk_log': content.get('chunk_log', ''),
                'processing_time': time.time() - start_time
            }
            
            return result
            
    except Exception as e:
        logger.error(f"Error processing {url}: {str(e)}")
        logger.debug("Error details:", exc_info=True)
        return {
            'success': False,
            'url': url,
            'error': str(e),
            'processing_time': time.time() - start_time
        }

def main():
    parser = argparse.ArgumentParser(description="Process documents with SophiaAMS")
    
    # Input sources
    parser.add_argument("urls", nargs="*", help="URLs to process")
    parser.add_argument("--file", "-f", help="File containing URLs to process (one per line)")
    
    # Output settings
    parser.add_argument("--output", "-o", help="Save results to JSON file")
    parser.add_argument("--debug", "-d", action="store_true", help="Enable debug logging")
    parser.add_argument("--open-log", action="store_true", help="Open chunk logs automatically")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed information")
    
    # Ingestion options
    parser.add_argument("--ingest", "-i", action="store_true", 
                      help="Ingest content into knowledge graph (requires AssociativeSemanticMemory)")
    parser.add_argument("--knowledge-base", "-k", default="knowledge_graph",
                      help="Path to knowledge graph directory")
    
    # Chunking settings
    parser.add_argument("--chunk-size", type=int, default=1024,
                      help="Token size for chunking (default: 1024)")
    parser.add_argument("--overlap", type=int, default=128,
                      help="Token overlap between chunks (default: 128)")
    
    args = parser.parse_args()
    
    # Set up logging
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = f"document_processor_{timestamp}.log"
    setup_logging(debug_mode=args.debug, log_file=log_file)
    logger = logging.getLogger('run_document_processor')
    
    # Collect URLs from arguments and/or file
    urls = []
    if args.urls:
        urls.extend(args.urls)
    
    if args.file:
        try:
            with open(args.file, 'r', encoding='utf-8') as f:
                file_urls = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]
                urls.extend(file_urls)
        except Exception as e:
            logger.error(f"Error reading URL file: {str(e)}")
    
    if not urls:
        logger.error("No URLs provided. Use positional arguments or --file option.")
        parser.print_help()
        return
    
    # Prepare options dict
    options = {
        'ingest': args.ingest,
        'knowledge_base': args.knowledge_base,
        'chunk_size': args.chunk_size,
        'overlap': args.overlap,
        'open_log': args.open_log,
        'verbose': args.verbose
    }
    
    # Process URLs
    results = []
    start_time = time.time()
    
    for i, url in enumerate(urls, 1):
        logger.info(f"Processing {i}/{len(urls)}: {url}")
        result = process_url(url, options)
        results.append(result)
        
        # Log progress
        success = result.get('success', False)
        if success:
            logger.info(f"Successfully processed {url} in {result.get('processing_time', 0):.2f}s")
        else:
            logger.error(f"Failed to process {url}: {result.get('error', 'Unknown error')}")
        
        # Print separator between URLs
        if i < len(urls):
            logger.info("-" * 40)
    
    # Log summary
    total_time = time.time() - start_time
    successful = sum(1 for r in results if r.get('success', False))
    logger.info("=" * 40)
    logger.info(f"Processing complete: {successful}/{len(urls)} URLs successful")
    logger.info(f"Total processing time: {total_time:.2f}s")
    logger.info(f"Log file: {log_file}")
    
    # Save results if requested
    if args.output:
        output_file = args.output
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
        logger.info(f"Results saved to {output_file}")

if __name__ == "__main__":
    main() 