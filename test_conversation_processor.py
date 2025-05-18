#!/usr/bin/env python3
"""
Test script for ConversationProcessor

This script demonstrates:
1. Initializing memory
2. Processing a conversation with personal details
3. Querying the memory for each line of a follow-up conversation
4. Exporting triples and cleaning up

Usage:
python test_conversation_processor.py
"""

import logging
import os
import time
import json
import atexit
import shutil
from datetime import datetime
from typing import Dict, List

from ConversationProcessor import ConversationProcessor
from AssociativeSemanticMemory import AssociativeSemanticMemory
from VectorKnowledgeGraph import VectorKnowledgeGraph
from utils import setup_logging

# Setup logging
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
log_file = f"conversation_processor_test_{timestamp}.log"
setup_logging(debug_mode=True, log_file=log_file)
logger = logging.getLogger('test_conversation_processor')

# Test directory for the knowledge graph
TEST_DIR = "Test_ConversationMemory"

def cleanup_test_directory():
    """Clean up the test directory, ensuring all resources are released first."""
    try:
        logger.info("Cleaning up test directory...")
        if os.path.exists(TEST_DIR):
            # Wait a moment to ensure all connections are closed
            time.sleep(1)
            # Try to remove SQLite file directly
            sqlite_path = os.path.join(TEST_DIR, "qdrant_data", "collection", "knowledge_graph", "storage.sqlite")
            if os.path.exists(sqlite_path):
                try:
                    os.remove(sqlite_path)
                except Exception as e:
                    logger.warning(f"Could not remove SQLite file: {e}")
            
            # Then try to remove the directory
            try:
                shutil.rmtree(TEST_DIR)
                logger.info(f"Successfully removed {TEST_DIR}")
            except Exception as e:
                logger.warning(f"Could not fully remove test directory: {e}")
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")

def export_triples_to_file(kgraph, filename):
    """Export all triples from the knowledge graph to a JSON file."""
    logger.info(f"Exporting triples to {filename}...")
    
    try:
        # Get all triples with metadata
        triples = kgraph.get_all_triples()
        
        # Format for export
        export_data = []
        for triple in triples:
            export_data.append({
                "triple": {
                    "subject": triple["subject"],
                    "predicate": triple["predicate"],
                    "object": triple["object"]
                },
                "metadata": triple.get("metadata", {})
            })
        
        # Write to file
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2)
        
        logger.info(f"Successfully exported {len(export_data)} triples to {filename}")
        return len(export_data)
    except Exception as e:
        logger.error(f"Error exporting triples: {e}")
        return 0

def main():
    # Register cleanup function
    atexit.register(cleanup_test_directory)
    
    try:
        # Initialize knowledge graph and memory
        logger.info("Initializing knowledge graph and memory...")
        kgraph = VectorKnowledgeGraph(path=TEST_DIR)
        memory = AssociativeSemanticMemory(kgraph)
        processor = ConversationProcessor(memory)
        
        # First conversation with personal details
        logger.info("Creating first conversation with personal details...")
        first_conversation = [
            {"role": "system", "content": "You are Sophia, a helpful AI assistant who remembers personal details about users."},
            {"role": "user", "name": "Alex", "content": "Hi there! My name is Alex. It's nice to meet you."},
            {"role": "assistant", "name": "Sophia", "content": "Hello Alex! It's wonderful to meet you too. How can I help you today?"},
            {"role": "user", "name": "Alex", "content": "I just wanted to chat. My birthday is coming up next week, on April 18th."},
            {"role": "assistant", "name": "Sophia", "content": "That's exciting, Alex! Happy early birthday. How do you plan to celebrate your birthday on April 18th?"},
            {"role": "user", "name": "Alex", "content": "I'm thinking of having a small dinner party with friends. I love Italian food, especially pasta."},
            {"role": "assistant", "name": "Sophia", "content": "A dinner party sounds wonderful! Italian food is a great choice for a celebration. Do you have a favorite pasta dish you'd like to serve?"},
            {"role": "user", "name": "Alex", "content": "I make a pretty good fettuccine alfredo. By the way, what's your favorite type of music?"},
            {"role": "assistant", "name": "Sophia", "content": "Your fettuccine alfredo sounds delicious! As for music, I appreciate all kinds of music, but I particularly enjoy classical compositions for their complexity and emotional depth. I find works by composers like Mozart and Debussy fascinating. What about you, Alex? What kind of music do you enjoy?"},
            {"role": "user", "name": "Alex", "content": "I'm a big fan of indie rock. I've been listening to a lot of Arctic Monkeys lately."},
            {"role": "assistant", "name": "Sophia", "content": "Arctic Monkeys are excellent! They have such a distinctive sound and clever lyrics. Do you have a favorite album or song by them?"}
        ]
        
        # Process the first conversation
        logger.info("Processing first conversation...")
        result = processor.process_conversation(
            messages=first_conversation,
            entity_name="Sophia"
        )
        
        if result['success']:
            logger.info(f"Successfully processed conversation with {result['processed_messages']} messages")
        else:
            logger.error(f"Failed to process conversation: {result.get('error', 'Unknown error')}")
        
        # Wait a moment to let processing complete
        time.sleep(1)
        
        # Follow-up conversation
        logger.info("Creating second conversation that references the first...")
        second_conversation = [
            {"role": "system", "content": "You are Sophia, a helpful AI assistant who remembers personal details about users."},
            {"role": "user", "name": "Alex", "content": "Hi Sophia, it's Alex again!"},
            {"role": "assistant", "name": "Sophia", "content": "Hello Alex! It's great to see you again. How can I help you today?"},
            {"role": "user", "name": "Alex", "content": "Just checking in. My birthday is in a few days!"},
            {"role": "assistant", "name": "Sophia", "content": "Of course! Your birthday is on April 18th, right? Are you still planning that dinner party with Italian food?"},
            {"role": "user", "name": "Alex", "content": "Yes! I've invited a few friends over. I'll be making my specialty."},
            {"role": "assistant", "name": "Sophia", "content": "That sounds wonderful! Your fettuccine alfredo should be a hit with your friends. Will you be playing any Arctic Monkeys during the party? I remember you're a fan of indie rock."},
            {"role": "user", "name": "Alex", "content": "Definitely! I've created a playlist with some of their best songs. What was your favorite type of music again?"},
            {"role": "assistant", "name": "Sophia", "content": "I particularly enjoy classical music, especially compositions by Mozart and Debussy. I appreciate their complexity and emotional depth. But your Arctic Monkeys playlist sounds perfect for a birthday celebration!"}
        ]
        
        # For the second conversation, query memory for each line
        logger.info("Processing second conversation with memory queries for each message...")
        
        # First, process entire conversation to capture it in memory
        result2 = processor.process_conversation(
            messages=second_conversation,
            entity_name="Sophia"
        )
        
        if result2['success']:
            logger.info(f"Successfully processed second conversation with {result2['processed_messages']} messages")
        else:
            logger.error(f"Failed to process second conversation: {result2.get('error', 'Unknown error')}")
        
        # Now go through each user message and query memory
        logger.info("Querying memory for each user message in the second conversation...")
        for i, message in enumerate(second_conversation):
            if message['role'] == 'user':
                query = message['content']
                logger.info(f"User query: '{query}'")
                
                # Query the memory
                query_result = processor.query_conversation_memory(
                    query=query,
                    entity_name="Sophia",
                    limit=5,
                    min_confidence=0.6
                )
                
                # Log the results
                logger.info(f"Found {query_result['triple_count']} related memories")
                if query_result['summary']:
                    logger.info(f"Memory summary: {query_result['summary']}")
                else:
                    logger.info("No memory summary generated")
                
                logger.info("-" * 40)
        
        # Export all triples to a JSON file
        export_file = f"conversation_triples_{timestamp}.json"
        triple_count = export_triples_to_file(kgraph, export_file)
        logger.info(f"Exported {triple_count} triples to {export_file}")
        
        # Close connections and clean up
        logger.info("Closing memory connections...")
        memory.close()
        
    except Exception as e:
        logger.error(f"Test failed with error: {e}", exc_info=True)
    finally:
        # Ensure cleanup happens
        cleanup_test_directory()
        logger.info("Test completed")

if __name__ == "__main__":
    main() 