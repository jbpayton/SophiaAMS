"""
Test script for DocumentProcessor functionality.
Extracted from DocumentProcessor.py for better code organization.
"""

import time
import logging
import os
import sys
import shutil
from datetime import datetime

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from DocumentProcessor import DocumentProcessor, WebPageSource
from AssociativeSemanticMemory import AssociativeSemanticMemory
from VectorKnowledgeGraph import VectorKnowledgeGraph
from utils import setup_logging


def run_document_processor_test():
    """Run comprehensive tests for the document processor."""
    # Set up debug logging for testing
    log_file = f"test-output/document_processor_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    setup_logging(debug_mode=True, log_file=log_file)
    logging.info("Starting document processor test run")
    
    # Example test pages
    test_urls = [
        "https://en.wikipedia.org/wiki/Vocaloid",
        "https://vocaloid.fandom.com/wiki/Kasane_Teto",
        "https://blazblue.fandom.com/wiki/Ragna_the_Bloodedge",
        "https://blazblue.fandom.com/wiki/Centralfiction",
        "https://blazblue.fandom.com/wiki/Rachel_Alucard",
        "https://vocaloid.fandom.com/wiki/Hatsune_Miku"
    ]
    
    # Initialize the semantic memory
    logging.info("Initializing semantic memory")
    kgraph = VectorKnowledgeGraph(path="test-output/Test_DocumentProcessing")
    memory = AssociativeSemanticMemory(kgraph)
    processor = DocumentProcessor(memory)
    
    try:
        # Process each page
        total_start = time.time()
        total_processed = 0
        total_failed = 0
        chunk_logs = []
        
        for i, url in enumerate(test_urls, 1):
            logging.info(f"\nProcessing URL {i}/{len(test_urls)}: {url}")
            url_start = time.time()
            
            try:
                source = WebPageSource(url)
                result = processor.process_document(source)
                
                if result['success']:
                    total_processed += result['processed_chunks']
                    if result.get('failed_chunks', 0) > 0:
                        total_failed += result['failed_chunks']
                    
                    logging.info(f"Successfully processed {result['processed_chunks']} chunks")
                    logging.info(f"Found {len(result['images'])} images")
                    logging.info(f"Processing time: {result.get('processing_time', 0):.2f}s")
                    
                    # Track chunk log files
                    if 'chunk_log' in result:
                        chunk_logs.append(result['chunk_log'])
                        logging.info(f"Chunk details saved to: {result['chunk_log']}")
                    
                    # Test querying the processed content
                    _test_queries(memory, logging)
                else:
                    total_failed += 1
                    logging.error(f"Failed to process document: {result.get('error', 'Unknown error')}")
                    if 'metadata' in result and 'error' in result['metadata']:
                        logging.error(f"Error details: {result['metadata']['error']}")
            
            except Exception as e:
                total_failed += 1
                logging.error(f"Error processing URL {url}: {str(e)}")
                logging.debug("Error details:", exc_info=True)
                continue
            
            url_time = time.time() - url_start
            logging.info(f"\nCompleted processing URL {i}/{len(test_urls)} in {url_time:.2f}s")
            
            # Calculate averages and remaining time safely
            elapsed = time.time() - total_start
            if i > 0:  # Prevent division by zero
                progress = i / len(test_urls) * 100
                avg_time = elapsed / i
                remaining = (len(test_urls) - i) * avg_time
            else:
                progress = 0
                avg_time = 0
                remaining = 0
            logging.info(f"Overall progress: {progress:.1f}%")
            logging.info(f"Average time per URL: {avg_time:.2f}s")
            logging.info(f"Estimated time remaining: {remaining:.2f}s")
    
    finally:
        # Clean up and summary
        _cleanup_and_summary(total_start, test_urls, total_processed, total_failed, chunk_logs, processor, memory)


def _test_queries(memory, logging):
    """Test querying the processed content."""
    logging.info("\nTesting queries...")
    queries = [
        "Who is Ragna the Bloodedge?",
        "What is BlazBlue: Centralfiction?",
        "Tell me about Rachel Alucard",
        "What is Vocaloid?",
        "Who is Kasane Teto?",
        "Tell me about Hatsune Miku"
    ]
    
    for query in queries:
        try:
            query_start = time.time()
            logging.info(f"\nQuery: {query}")
            result = memory.query_related_information(text=query)
            related = result.get('triples', [])
            logging.info(f"Found {result.get('triple_count', len(related))} related triples in {time.time() - query_start:.2f}s")
            
            # Print a summary of the results
            if related:
                summary_start = time.time()
                logging.info("\nSummary:")
                try:
                    summary = result.get('summary', '') or memory.summarize_results(query, related)
                    logging.info(summary)
                    logging.info(f"Summary generation time: {time.time() - summary_start:.2f}s")
                    # Verify topics in related triples
                    for rel_triple, rel_metadata in related:
                        assert "topics" in rel_metadata, f"Topics field missing in related triple metadata: {rel_metadata}"
                        assert isinstance(rel_metadata['topics'], list), f"Topics field is not a list in related triple: {rel_metadata['topics']}"
                except Exception as e:
                    logging.error(f"Error generating summary: {str(e)}")
                    logging.info("Attempting to summarize with fewer triples...")
                    
                    # Try with just the first 5 triples if there are too many
                    if len(related) > 8:
                        try:
                            limited_summary = memory.summarize_results(query, related[:8])
                            logging.info("Limited summary (first 8 triples only):")
                            logging.info(limited_summary)
                            logging.info(f"Limited summary generation time: {time.time() - summary_start:.2f}s")
                        except Exception as e2:
                            logging.error(f"Error generating limited summary: {str(e2)}")
                
                # Log the retrieved triples
                _log_retrieved_triples(related, logging)
            else:
                logging.warning(f"No relevant information found for query: '{query}'")
        except Exception as e:
            logging.error(f"Error processing query '{query}': {str(e)}")
            logging.debug("Query error details:", exc_info=True)
            continue


def _log_retrieved_triples(related, logging):
    """Log details of retrieved triples."""
    logging.info("\nRetrieved Triples:")
    for i, triple in enumerate(related[:10]):  # Show first 10 triples
        try:
            # Try to access as a dictionary
            if isinstance(triple, dict):
                logging.info(f"{i+1}. Subject: {triple.get('subject', 'N/A')}")
                logging.info(f"   Predicate: {triple.get('predicate', 'N/A')}")
                logging.info(f"   Object: {triple.get('object', 'N/A')}")
                logging.info(f"   Confidence: {triple.get('confidence', 'N/A')}")
                logging.info(f"   Source: {triple.get('source', 'N/A')}")
            # Try to access as a tuple
            elif isinstance(triple, tuple):
                # Handle (triple, metadata) structure
                if len(triple) == 2 and isinstance(triple[0], (list, tuple)):
                    subj, pred, obj = triple[0]
                    meta = triple[1]
                    conf = meta.get('confidence', 'N/A') if isinstance(meta, dict) else 'N/A'
                    logging.info(f"{i+1}. Subject: {subj}")
                    logging.info(f"   Predicate: {pred}")
                    logging.info(f"   Object: {obj}")
                    logging.info(f"   Confidence: {conf}")
                else:
                    logging.info(f"{i+1}. Subject: {triple[0] if len(triple) > 0 else 'N/A'}")
                    logging.info(f"   Predicate: {triple[1] if len(triple) > 1 else 'N/A'}")
                    logging.info(f"   Object: {triple[2] if len(triple) > 2 else 'N/A'}")
            else:
                logging.info(f"{i+1}. Triple format unknown: {type(triple)}")
                logging.info(f"   Contents: {triple}")
        except Exception as e:
            logging.error(f"Error displaying triple {i+1}: {str(e)}")
    
    if len(related) > 10:
        logging.info(f"... and {len(related) - 10} more triples")


def _cleanup_and_summary(total_start, test_urls, total_processed, total_failed, chunk_logs, processor, memory):
    """Clean up resources and print test summary."""
    total_time = time.time() - total_start
    logging.info("\nTest run summary:")
    logging.info(f"Total URLs processed: {len(test_urls)}")
    logging.info(f"Total chunks processed: {total_processed}")
    logging.info(f"Total failures: {total_failed}")
    logging.info(f"Total processing time: {total_time:.2f}s")
    logging.info(f"Average time per URL: {total_time/len(test_urls):.2f}s")
    
    # List all generated chunk logs
    if chunk_logs:
        logging.info("\nGenerated chunk logs:")
        for log_file in chunk_logs:
            logging.info(f"- {log_file}")
    
    # Export all triples to JSON
    export_file = f"triples_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    export_result = processor.export_all_triples_to_json(export_file)
    if export_result['success']:
        logging.info(f"Successfully exported {export_result['triple_count']} triples to {export_file}")
    else:
        logging.error(f"Failed to export triples: {export_result.get('error', 'Unknown error')}")
    
    logging.info("Cleaning up resources")
    memory.close()
    # Use same directory path that was used to create the graph
    graph_dir = "test-output/Test_DocumentProcessing"
    if os.path.exists(graph_dir):
        shutil.rmtree(graph_dir)
    logging.info("Test run completed")


if __name__ == "__main__":
    run_document_processor_test()
