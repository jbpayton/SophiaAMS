"""
Backward Compatibility Tests for Procedural Knowledge System

Ensures that adding procedural knowledge support doesn't break:
1. Normal factual extraction
2. Conversation extraction
3. Query extraction
4. Standard triple retrieval
5. Existing memory functionality
"""

import sys
import time
import os
import shutil
from triple_extraction import extract_triples_from_string
from AssociativeSemanticMemory import AssociativeSemanticMemory
from VectorKnowledgeGraph import VectorKnowledgeGraph
from ConversationProcessor import ConversationProcessor


def print_test(name):
    """Print test name"""
    print(f"\n{'='*70}")
    print(f"TEST: {name}")
    print('='*70)


def print_result(passed, message=""):
    """Print test result"""
    if passed:
        print(f"[PASS] {message}")
    else:
        print(f"[FAIL] {message}")
    return passed


def test_factual_extraction():
    """Test 1: Normal factual text extraction (encyclopedia-style)"""
    print_test("Factual Text Extraction (Baseline)")

    text = """
    Hatsune Miku is a virtual singer developed by Crypton Future Media.
    She was released in August 2007 for the VOCALOID2 engine.
    Her voice is provided by the Japanese voice actress Saki Fujita.
    """

    print(f"Input: {text.strip()}\n")

    result = extract_triples_from_string(text, source="test_factual")
    triples = result['triples']

    print(f"Extracted {len(triples)} triples:")
    for t in triples[:5]:
        verb = t.get('verb', '')
        topics = t.get('topics', [])
        print(f"  - ({t['subject']}, {verb}, {t['object']})")
        print(f"    Topics: {topics}")

    # Should extract factual triples
    has_triples = len(triples) > 0

    # Should NOT have procedural predicates
    procedural_predicates = ['accomplished_by', 'requires', 'alternatively_by',
                            'example_usage', 'has_step', 'followed_by']
    predicates = [t['verb'].lower() for t in triples]
    has_procedural = any(p in procedural_predicates for p in predicates)

    # Should NOT be marked as procedure
    has_procedure_topic = any('procedure' in t.get('topics', []) for t in triples)

    # Should use standard verbs
    standard_verbs = ['is', 'was', 'has', 'developed', 'created', 'provided', 'released']
    has_standard = any(any(sv in v for sv in standard_verbs) for v in predicates)

    result1 = print_result(has_triples, f"Extracted triples: {len(triples)}")
    result2 = print_result(not has_procedural, f"No procedural predicates: {not has_procedural}")
    result3 = print_result(not has_procedure_topic, f"Not marked as procedure: {not has_procedure_topic}")
    result4 = print_result(has_standard, f"Uses standard verbs: {has_standard}")

    return result1 and result2 and result3 and result4


def test_conversation_extraction():
    """Test 2: Conversation extraction (personal facts)"""
    print_test("Conversation Extraction")

    text = """SPEAKER:Alex|I love sushi and work at Google. I'm interested in AI.
SPEAKER:Sophia|That's great! I can help you learn more about AI."""

    print(f"Input:\n{text}\n")

    result = extract_triples_from_string(
        text,
        source="test_conversation",
        is_conversation=True
    )
    triples = result['triples']

    print(f"Extracted {len(triples)} triples:")
    for t in triples:
        speaker = t.get('speaker', 'N/A')
        print(f"  - ({t['subject']}, {t['verb']}, {t['object']}) [Speaker: {speaker}]")

    # Should extract personal facts
    has_triples = len(triples) > 0

    # Should have speaker attribution
    has_speakers = any('speaker' in t for t in triples)

    # Should extract personal facts (love, work_at, interested_in)
    personal_verbs = ['love', 'work', 'interested']
    predicates = [t['verb'].lower() for t in triples]
    has_personal = any(any(pv in pred for pv in personal_verbs) for pred in predicates)

    # Should NOT treat as procedural (no "to X, use Y" pattern)
    procedural_predicates = ['accomplished_by', 'requires', 'alternatively_by']
    has_procedural = any(p in procedural_predicates for p in predicates)

    result1 = print_result(has_triples, f"Extracted triples: {len(triples)}")
    result2 = print_result(has_speakers, f"Has speaker attribution: {has_speakers}")
    result3 = print_result(has_personal, f"Extracted personal facts: {predicates}")
    result4 = print_result(not has_procedural, f"Not marked as procedural: {not has_procedural}")

    return result1 and result2 and result3 and result4


def test_query_extraction():
    """Test 3: Query extraction (user questions)"""
    print_test("Query Extraction")

    query = "What do you know about my favorite food?"

    print(f"Query: {query}\n")

    result = extract_triples_from_string(
        query,
        source="test_query",
        is_query=True
    )

    # Query extraction returns different format
    query_triples = result.get('query_triples', [])

    print(f"Extracted {len(query_triples)} query triples:")
    for t in query_triples:
        print(f"  - ({t['subject']}, {t['verb']}, {t['object']})")

    # Should extract query intent
    has_triples = len(query_triples) > 0

    # Should NOT be procedural
    predicates = [t['verb'].lower() for t in query_triples]
    procedural_predicates = ['accomplished_by', 'requires', 'alternatively_by']
    has_procedural = any(p in procedural_predicates for p in predicates)

    result1 = print_result(has_triples, f"Extracted query triples: {len(query_triples)}")
    result2 = print_result(not has_procedural, f"Not marked as procedural: {not has_procedural}")

    return result1 and result2


def test_mixed_content():
    """Test 4: Mixed factual and procedural content"""
    print_test("Mixed Content Handling")

    text = """
    Python is a programming language. It was created by Guido van Rossum.
    To install Python packages, use pip install package_name.
    Python is popular for data science and web development.
    """

    print(f"Input: {text.strip()}\n")

    result = extract_triples_from_string(text, source="test_mixed")
    triples = result['triples']

    print(f"Extracted {len(triples)} triples:")
    for t in triples:
        verb = t['verb']
        is_proc = 'procedure' in t.get('topics', [])
        marker = "[PROCEDURAL]" if is_proc else "[FACTUAL]"
        print(f"  {marker} ({t['subject']}, {verb}, {t['object']})")

    # Should extract both types
    has_triples = len(triples) > 0

    # Should have some procedural (pip install instruction)
    procedural_count = sum(1 for t in triples if 'procedure' in t.get('topics', []))
    has_procedural = procedural_count > 0

    # Should have some factual (Python is a language)
    factual_count = sum(1 for t in triples if 'procedure' not in t.get('topics', []))
    has_factual = factual_count > 0

    result1 = print_result(has_triples, f"Extracted triples: {len(triples)}")
    result2 = print_result(has_procedural, f"Has procedural triples: {procedural_count}")
    result3 = print_result(has_factual, f"Has factual triples: {factual_count}")

    return result1 and result2 and result3


def test_standard_memory_operations():
    """Test 5: Standard memory ingest and query"""
    print_test("Standard Memory Operations (End-to-End)")

    test_db = "Test_BackwardCompat"
    if os.path.exists(test_db):
        shutil.rmtree(test_db)

    try:
        kgraph = VectorKnowledgeGraph(path=test_db)
        memory = AssociativeSemanticMemory(kgraph)

        # Ingest factual knowledge
        factual_text = """
        The Eiffel Tower is located in Paris, France.
        It was built in 1889 for the World's Fair.
        The tower is 330 meters tall.
        """

        print("Ingesting factual knowledge...")
        result = memory.ingest_text(factual_text, source="eiffel_facts")
        print(f"  Ingested {len(result['original_triples'])} triples\n")

        time.sleep(1)  # Allow indexing

        # Query factual knowledge
        print("Querying: 'Eiffel Tower location'")
        query_result = memory.query_related_information(
            "Eiffel Tower location",
            limit=5
        )

        triples_found = len(query_result.get('related_triples', []))
        print(f"  Found {triples_found} related triples\n")

        if triples_found > 0:
            print("  Sample results:")
            for triple, meta in query_result['related_triples'][:3]:
                print(f"    - {triple}")

        # Should find related triples
        found_triples = triples_found > 0

        # Should have summary
        has_summary = bool(query_result.get('summary'))

        # Should NOT include procedural triples (none were ingested)
        procedural_predicates = ['accomplished_by', 'requires']
        has_procedural = any(
            any(p in str(t).lower() for p in procedural_predicates)
            for t in query_result.get('related_triples', [])
        )

        memory.close()
        time.sleep(1)

        result1 = print_result(found_triples, f"Found related triples: {triples_found}")
        result2 = print_result(has_summary, "Generated summary")
        result3 = print_result(not has_procedural, "No procedural contamination")

        return result1 and result2 and result3

    finally:
        if os.path.exists(test_db):
            shutil.rmtree(test_db)


def test_conversation_processor():
    """Test 6: ConversationProcessor still works"""
    print_test("ConversationProcessor Compatibility")

    test_db = "Test_ConvProcessor"
    if os.path.exists(test_db):
        shutil.rmtree(test_db)

    try:
        kgraph = VectorKnowledgeGraph(path=test_db)
        memory = AssociativeSemanticMemory(kgraph)
        processor = ConversationProcessor(memory)

        messages = [
            {"role": "user", "content": "My name is Alice and I love photography"},
            {"role": "assistant", "content": "Nice to meet you Alice! Photography is a wonderful hobby."},
            {"role": "user", "content": "I work as a software engineer at TechCorp"},
        ]

        print("Processing conversation...")
        result = processor.process_conversation(messages, entity_name="Assistant")

        success = result.get('success', False)
        processed = result.get('processed_messages', 0)

        print(f"  Success: {success}")
        print(f"  Processed messages: {processed}\n")

        time.sleep(1)

        # Query for extracted facts
        print("Querying: 'Alice work'")
        query_result = memory.query_related_information("Alice work", limit=5)
        found = len(query_result.get('related_triples', []))
        print(f"  Found {found} related triples")

        memory.close()
        time.sleep(1)

        result1 = print_result(success, "Conversation processed successfully")
        result2 = print_result(processed == 3, f"Processed all messages: {processed}")
        result3 = print_result(found > 0, f"Can query extracted facts: {found}")

        return result1 and result2 and result3

    finally:
        if os.path.exists(test_db):
            shutil.rmtree(test_db)


def test_factual_vs_procedural_isolation():
    """Test 7: Factual and procedural knowledge don't interfere"""
    print_test("Factual vs Procedural Isolation")

    test_db = "Test_Isolation"
    if os.path.exists(test_db):
        shutil.rmtree(test_db)

    try:
        kgraph = VectorKnowledgeGraph(path=test_db)
        memory = AssociativeSemanticMemory(kgraph)

        # Ingest factual knowledge
        factual = "Python is a programming language created in 1991."
        memory.ingest_text(factual, source="fact")

        # Ingest procedural knowledge
        procedural = "To install Python packages, use pip install package_name."
        memory.ingest_text(procedural, source="procedure")

        time.sleep(1)

        # Query factual - should get factual
        print("Query 1: 'Python programming language'")
        fact_result = memory.query_related_information("Python programming language", limit=5)
        fact_triples = fact_result.get('related_triples', [])
        print(f"  Found {len(fact_triples)} triples")

        # Query procedural - should get procedural
        print("\nQuery 2: 'install Python packages'")
        if hasattr(memory, 'query_procedure'):
            proc_result = memory.query_procedure("install Python packages", limit=5)
            proc_count = proc_result.get('total_found', 0)
            print(f"  Found {proc_count} procedural triples")
        else:
            proc_count = 0
            print("  [query_procedure not available, using standard query]")
            proc_result = memory.query_related_information("install Python packages", limit=5)
            proc_count = len(proc_result.get('related_triples', []))
            print(f"  Found {proc_count} triples")

        memory.close()
        time.sleep(1)

        result1 = print_result(len(fact_triples) > 0, f"Factual query works: {len(fact_triples)}")
        result2 = print_result(proc_count > 0, f"Procedural query works: {proc_count}")

        return result1 and result2

    finally:
        if os.path.exists(test_db):
            shutil.rmtree(test_db)


def test_topic_extraction():
    """Test 8: Topic extraction still works correctly"""
    print_test("Topic Extraction")

    text = """
    Machine learning is a subset of artificial intelligence.
    It uses algorithms to learn patterns from data.
    Common applications include image recognition and natural language processing.
    """

    print(f"Input: {text.strip()}\n")

    result = extract_triples_from_string(text, source="test_topics")
    triples = result['triples']

    print(f"Extracted {len(triples)} triples:")
    all_topics = set()
    for t in triples[:5]:
        topics = t.get('topics', [])
        all_topics.update(topics)
        print(f"  - ({t['subject']}, {t['verb']}, {t['object']})")
        print(f"    Topics: {topics}")

    # Should have topics
    has_topics = len(all_topics) > 0

    # Topics should be relevant (AI, ML, technology-related)
    relevant_keywords = ['learning', 'intelligence', 'ai', 'ml', 'technology',
                        'algorithm', 'data', 'application']
    has_relevant = any(
        any(kw in topic.lower() for kw in relevant_keywords)
        for topic in all_topics
    )

    # Should NOT have 'procedure' topic (this is factual text)
    has_procedure = 'procedure' in all_topics

    result1 = print_result(has_topics, f"Has topics: {len(all_topics)}")
    result2 = print_result(has_relevant, f"Topics are relevant: {all_topics}")
    result3 = print_result(not has_procedure, f"No procedure topic: {not has_procedure}")

    return result1 and result2 and result3


def main():
    """Run all backward compatibility tests"""
    print("\n" + "="*70)
    print("BACKWARD COMPATIBILITY TEST SUITE")
    print("Ensuring procedural knowledge doesn't break existing functionality")
    print("="*70)

    tests = [
        ("Factual Extraction", test_factual_extraction),
        ("Conversation Extraction", test_conversation_extraction),
        ("Query Extraction", test_query_extraction),
        ("Mixed Content", test_mixed_content),
        ("Standard Memory Ops", test_standard_memory_operations),
        ("ConversationProcessor", test_conversation_processor),
        ("Factual/Procedural Isolation", test_factual_vs_procedural_isolation),
        ("Topic Extraction", test_topic_extraction),
    ]

    results = []
    start_time = time.time()

    for name, test_func in tests:
        try:
            passed = test_func()
            results.append((name, passed))
        except Exception as e:
            print(f"\n[ERROR] in {name}: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))

    end_time = time.time()

    # Print summary
    print("\n" + "="*70)
    print("BACKWARD COMPATIBILITY TEST SUMMARY")
    print("="*70)

    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)

    for name, passed in results:
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{status} - {name}")

    print("\n" + "-"*70)
    print(f"Total: {passed_count}/{total_count} tests passed")
    print(f"Pass Rate: {(passed_count/total_count*100):.1f}%")
    print(f"Time: {end_time - start_time:.2f}s")
    print("-"*70)

    if passed_count == total_count:
        print("\n*** ALL BACKWARD COMPATIBILITY TESTS PASSED! ***")
        print("Procedural knowledge system is fully compatible with existing functionality.")
        return 0
    else:
        print(f"\n*** {total_count - passed_count} test(s) failed ***")
        print("Review failures above to identify compatibility issues.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
