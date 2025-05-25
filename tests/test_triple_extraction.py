#!/usr/bin/env python3
"""
Test script to verify the improved triple extraction with better verb handling.
"""

import json
import os
import sys

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from triple_extraction import extract_triples_from_string

def test_conversation_extraction():
    """Test conversation extraction with improved prompts."""
    conversation_text = """SPEAKER:Alex|I work at Microsoft and my birthday is September 3rd. I love playing guitar and recently started learning piano.
SPEAKER:Sophia|That's awesome! I'm a software engineer at Google and my birthday is December 22nd. I enjoy watercolor painting and rock climbing."""
    
    print("Testing conversation extraction...")
    print("Input:", conversation_text)
    print("\n" + "="*60 + "\n")
    
    result = extract_triples_from_string(
        conversation_text, 
        source="test_conversation",
        is_conversation=True
    )
    
    print("EXTRACTED TRIPLES:")
    for i, triple in enumerate(result.get("triples", []), 1):
        print(f"{i}. Subject: {triple.get('subject')}")
        print(f"   Verb: {triple.get('verb')}")
        print(f"   Object: {triple.get('object')}")
        print(f"   Speaker: {triple.get('speaker')}")
        print(f"   Source: {triple.get('source_text')}")
        print(f"   Topics: {triple.get('topics')}")
        assert "topics" in triple, "Triple should have a 'topics' field"
        assert isinstance(triple.get("topics"), list), "Topics should be a list"
        print()

def test_document_extraction():
    """Test document extraction with improved prompts."""
    document_text = """The iPhone was developed by Apple Inc. and was first released in June 2007. 
    Steve Jobs served as CEO of Apple during its development. The device revolutionized smartphones."""
    
    print("Testing document extraction...")
    print("Input:", document_text)
    print("\n" + "="*60 + "\n")
    
    result = extract_triples_from_string(
        document_text, 
        source="test_document"
    )
    
    print("EXTRACTED TRIPLES:")
    for i, triple in enumerate(result.get("triples", []), 1):
        print(f"{i}. Subject: {triple.get('subject')}")
        print(f"   Verb: {triple.get('verb')}")
        print(f"   Object: {triple.get('object')}")
        speaker = triple.get('speaker')
        print(f"   Speaker: {speaker if speaker is not None else 'N/A'}")
        print(f"   Source: {triple.get('source_text')}")
        print(f"   Topics: {triple.get('topics')}")
        assert "topics" in triple, "Triple should have a 'topics' field"
        assert isinstance(triple.get("topics"), list), "Topics should be a list"
        print()

if __name__ == "__main__":
    test_conversation_extraction()
    print("\n" + "="*80 + "\n")
    test_document_extraction()
