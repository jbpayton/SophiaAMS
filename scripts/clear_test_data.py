#!/usr/bin/env python3
"""
Clear old test data from the knowledge graph.

This script removes triples from test sessions while preserving real data.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from VectorKnowledgeGraph import VectorKnowledgeGraph

def clear_test_data():
    """Clear test data from knowledge graph."""
    kg = VectorKnowledgeGraph()

    # Get all triples
    all_triples = kg.get_all_triples()
    print(f"Total triples before cleaning: {len(all_triples)}")

    # Sources that are test data
    test_sources = [
        "agent_storage",
        "agent_storage_summary",
        "conversation_test_episodic_session",
        "conversation_test_episodic_session_summary",
        "conversation_test_episodic_session_2",
        "conversation_natural_test_session",
        "conversation_natural_test_session_summary",
    ]

    # Find test triples
    test_triples = []
    for triple in all_triples:
        source = triple.get('metadata', {}).get('source', '')
        if any(test_src in source for test_src in test_sources):
            test_triples.append(triple)

    print(f"\nFound {len(test_triples)} test triples to remove:")
    for triple in test_triples[:10]:  # Show first 10
        print(f"  - {triple['subject']} | {triple['predicate']} | {triple['object']}")
        print(f"    Source: {triple['metadata']['source']}")

    if len(test_triples) > 10:
        print(f"  ... and {len(test_triples) - 10} more")

    # Ask for confirmation
    print(f"\n{len(all_triples) - len(test_triples)} triples will be kept (real data)")
    response = input("\nProceed with deletion? (yes/no): ")

    if response.lower() in ['yes', 'y']:
        # Note: VectorKnowledgeGraph doesn't have a delete method currently
        # We'll need to recreate the database
        print("\n⚠️  Warning: VectorKnowledgeGraph doesn't have a delete method yet.")
        print("To clear test data, you need to:")
        print("1. Stop all servers")
        print("2. Delete VectorKnowledgeGraphData/qdrant_data/")
        print("3. Restart servers (database will recreate empty)")
        print("\nOr implement a delete method in VectorKnowledgeGraph.py")
    else:
        print("Cancelled.")

if __name__ == "__main__":
    clear_test_data()
