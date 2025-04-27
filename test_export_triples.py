import json
import logging
import os
import shutil
from datetime import datetime

from AssociativeSemanticMemory import AssociativeSemanticMemory
from DocumentProcessor import DocumentProcessor, WebPageSource
from VectorKnowledgeGraph import VectorKnowledgeGraph
from utils import setup_logging

if __name__ == "__main__":
    # Set up debug logging for testing
    log_file = f"export_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    setup_logging(debug_mode=True, log_file=log_file)
    logging.info("Starting test of triples export functionality")
    
    # Initialize the components
    kgraph = VectorKnowledgeGraph(path="Test_ExportTriples")
    memory = AssociativeSemanticMemory(kgraph)
    processor = DocumentProcessor(memory)
    
    try:
        # Add some test triples
        test_triples = [
            ("Sophia", "is", "an intelligent agent"),
            ("Sophia", "processes", "documents"),
            ("Documents", "contain", "information"),
            ("Information", "is stored in", "semantic memory"),
            ("Semantic memory", "consists of", "triples")
        ]
        
        # Add metadata
        test_metadata = [
            {"source": "test", "timestamp": datetime.now().timestamp(), "confidence": 0.9},
            {"source": "test", "timestamp": datetime.now().timestamp(), "confidence": 0.9},
            {"source": "test", "timestamp": datetime.now().timestamp(), "confidence": 0.9},
            {"source": "test", "timestamp": datetime.now().timestamp(), "confidence": 0.9},
            {"source": "test", "timestamp": datetime.now().timestamp(), "confidence": 0.9}
        ]
        
        # Add triples to the knowledge graph
        logging.info("Adding test triples to knowledge graph")
        kgraph.add_triples(test_triples, test_metadata)
        
        # Test getting all triples
        logging.info("Testing get_all_triples method")
        all_triples = kgraph.get_all_triples()
        logging.info(f"Retrieved {len(all_triples)} triples")
        for triple in all_triples:
            logging.info(f"Subject: {triple['subject']}, Predicate: {triple['predicate']}, Object: {triple['object']}")
        
        # Test export functionality
        export_file = f"test_triples_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        logging.info(f"Testing export_all_triples_to_json to {export_file}")
        export_result = processor.export_all_triples_to_json(export_file)
        
        if export_result['success']:
            logging.info(f"Successfully exported {export_result['triple_count']} triples to {export_file}")
            
            # Verify the exported file
            with open(export_file, 'r', encoding='utf-8') as f:
                exported_data = json.load(f)
                logging.info(f"Exported data contains {len(exported_data['triples'])} triples")
                
                # Display some sample data
                logging.info("Sample of exported data:")
                for i, triple in enumerate(exported_data['triples'][:3]):
                    logging.info(f"Triple {i+1}: {triple}")
                
        else:
            logging.error(f"Failed to export triples: {export_result.get('error', 'Unknown error')}")
    
    finally:
        # Clean up
        logging.info("Test completed, cleaning up resources")
        memory.close()
        if os.path.exists("Test_ExportTriples"):
            shutil.rmtree("Test_ExportTriples")
        logging.info("Export test completed") 