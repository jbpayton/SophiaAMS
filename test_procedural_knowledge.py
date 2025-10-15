"""
Test script for the Procedural Knowledge System

This script demonstrates:
1. Teaching procedural knowledge
2. Querying procedures
3. Hierarchical skill composition
"""

from AssociativeSemanticMemory import AssociativeSemanticMemory
from VectorKnowledgeGraph import VectorKnowledgeGraph
import time
import json

def print_section(title):
    print("\n" + "="*80)
    print(f"  {title}")
    print("="*80 + "\n")

def print_procedures(result):
    """Pretty print procedure query results"""
    print(f"Goal: {result['goal']}")
    print(f"Total found: {result['total_found']}")

    if result['methods']:
        print("\n📋 Methods:")
        for triple, meta in result['methods'][:3]:
            print(f"  • {triple[0]} → {triple[2]} (confidence: {meta.get('confidence', 0):.2f})")

    if result['alternatives']:
        print("\n🔄 Alternatives:")
        for triple, meta in result['alternatives'][:3]:
            print(f"  • {triple[2]} (confidence: {meta.get('confidence', 0):.2f})")

    if result['dependencies']:
        print("\n⚙️  Dependencies:")
        for triple, meta in result['dependencies'][:3]:
            print(f"  • Requires: {triple[2]} (confidence: {meta.get('confidence', 0):.2f})")

    if result['examples']:
        print("\n💡 Examples:")
        for triple, meta in result['examples'][:3]:
            print(f"  • {triple[2]}")

def main():
    print_section("Procedural Knowledge System - Test")

    # Create memory system
    print("Initializing memory system...")
    kgraph = VectorKnowledgeGraph(path="Test_ProceduralKnowledge")
    memory = AssociativeSemanticMemory(kgraph)
    print("✓ Memory system ready\n")

    try:
        # Test 1: Teaching basic procedures
        print_section("TEST 1: Teaching Basic Procedures")

        teaching_text = """
        To send a POST request to an API, use requests.post(url, json=data).
        You need to import requests first before you can use it.
        Example: requests.post('http://api.example.com', json={'key': 'value'})

        Alternatively, you can use urllib.request for POST requests, but requests is easier.
        """

        print("Teaching text:")
        print(teaching_text)

        result = memory.ingest_text(teaching_text, source="user_teaching")
        print(f"\n✓ Extracted {len(result['original_triples'])} triples")

        # Show extracted triples
        print("\nExtracted procedural triples:")
        for triple in result['original_triples'][:5]:
            if 'procedure' in triple.get('topics', []):
                print(f"  • ({triple['subject']}, {triple['verb']}, {triple['object']})")

        # Test 2: Query procedures
        print_section("TEST 2: Querying Procedures")

        print("Query: 'send POST request'\n")
        proc_result = memory.query_procedure("send POST request")
        print_procedures(proc_result)

        # Test 3: Hierarchical procedures
        print_section("TEST 3: Hierarchical Procedures")

        hierarchical_text = """
        To deploy an application to production:
        1. First, run all tests to ensure code quality
        2. Then, build a Docker image
        3. Finally, push the image to the registry

        To run tests, use pytest with the tests directory.
        Example: pytest tests/ -v

        To build a Docker image, use docker build with a tag.
        Example: docker build -t myapp:latest .

        To push to registry, use docker push.
        Example: docker push myapp:latest
        """

        print("Teaching hierarchical procedure:")
        print(hierarchical_text)

        result = memory.ingest_text(hierarchical_text, source="deployment_guide")
        print(f"\n✓ Extracted {len(result['original_triples'])} triples")

        # Query the high-level task
        print("\nQuery: 'deploy application'\n")
        deploy_proc = memory.query_procedure("deploy application", limit=30)
        print_procedures(deploy_proc)

        # Query sub-tasks
        print("\n" + "-"*80)
        print("Query: 'run tests'\n")
        test_proc = memory.query_procedure("run tests")
        print_procedures(test_proc)

        # Test 4: Multiple alternatives
        print_section("TEST 4: Multiple Alternatives")

        alternatives_text = """
        To make HTTP requests in Python:

        You can use the requests library (most popular):
        Example: response = requests.get('https://api.example.com')

        Alternatively, use urllib (built-in, no installation needed):
        Example: import urllib.request; response = urllib.request.urlopen('https://api.example.com')

        Another option is httpx for async support:
        Example: async with httpx.AsyncClient() as client: response = await client.get('https://api.example.com')

        The requests library is recommended for most use cases.
        """

        print("Teaching alternatives:")
        print(alternatives_text)

        result = memory.ingest_text(alternatives_text, source="http_methods")
        print(f"\n✓ Extracted {len(result['original_triples'])} triples")

        print("\nQuery: 'make HTTP requests'\n")
        http_proc = memory.query_procedure("make HTTP requests")
        print_procedures(http_proc)

        # Test 5: Direct API usage
        print_section("TEST 5: Direct API Query")

        print("Python API usage example:")
        print("""
from AssociativeSemanticMemory import AssociativeSemanticMemory

result = memory.query_procedure(
    goal="deploy application",
    include_alternatives=True,
    include_examples=True,
    include_dependencies=True
)

# Access structured results:
for method_triple, metadata in result['methods']:
    print(f"Method: {method_triple[2]}")
    print(f"Confidence: {metadata['confidence']}")
        """)

        print("\n✓ All tests completed successfully!")

    finally:
        # Cleanup
        print_section("Cleanup")
        memory.close()

        import shutil
        import os
        if os.path.exists("Test_ProceduralKnowledge"):
            time.sleep(1)
            shutil.rmtree("Test_ProceduralKnowledge")
            print("✓ Test directory cleaned up")

if __name__ == "__main__":
    main()
