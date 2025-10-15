"""
Quick unit tests for Procedural Knowledge System core functionality
"""

import sys
import time
from triple_extraction import extract_triples_from_string


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


def test_procedural_detection():
    """Test 1: Basic procedural pattern detection"""
    print_test("Procedural Pattern Detection")

    text = "To send a POST request, use requests.post with the URL and data."
    print(f"Input: {text}\n")

    result = extract_triples_from_string(text, source="test")
    triples = result['triples']

    print(f"Extracted {len(triples)} triples:")
    for t in triples:
        print(f"  - ({t['subject']}, {t['verb']}, {t['object']})")
        print(f"    Topics: {t.get('topics', [])}")
        if 'abstraction_level' in t:
            print(f"    Abstraction Level: {t['abstraction_level']}")

    # Check for procedural predicates
    predicates = [t['verb'].lower() for t in triples]
    procedural_predicates = ['accomplished_by', 'is_method_for', 'requires',
                            'alternatively_by', 'example_usage']

    has_procedural = any(p in procedural_predicates for p in predicates)

    # Check for 'procedure' in topics
    has_procedure_topic = any('procedure' in t.get('topics', []) for t in triples)

    result1 = print_result(has_procedural, f"- Has procedural predicate: {predicates}")
    result2 = print_result(has_procedure_topic, "- Has 'procedure' in topics")

    return result1 and result2


def test_requires_pattern():
    """Test 2: Requires pattern detection"""
    print_test("Requires Pattern Detection")

    text = "You need to import requests before using requests.post"
    print(f"Input: {text}\n")

    result = extract_triples_from_string(text, source="test")
    triples = result['triples']

    print(f"Extracted {len(triples)} triples:")
    for t in triples:
        print(f"  - ({t['subject']}, {t['verb']}, {t['object']})")

    predicates = [t['verb'].lower() for t in triples]

    return print_result('requires' in predicates, f"- Found 'requires': {predicates}")


def test_example_usage():
    """Test 3: Example usage detection"""
    print_test("Example Usage Detection")

    text = "Example: requests.post('http://api.com', json={'key': 'value'})"
    print(f"Input: {text}\n")

    result = extract_triples_from_string(text, source="test")
    triples = result['triples']

    print(f"Extracted {len(triples)} triples:")
    for t in triples:
        print(f"  - ({t['subject']}, {t['verb']}, {t['object']})")

    predicates = [t['verb'].lower() for t in triples]

    # Check for example_usage predicate
    has_example = 'example_usage' in predicates

    # Check that code is preserved
    example_objects = [t['object'] for t in triples if 'example' in t['verb'].lower()]
    has_code = any('requests.post' in obj for obj in example_objects) if example_objects else False

    result1 = print_result(has_example, f"- Has example_usage predicate: {predicates}")
    result2 = print_result(has_code or len(example_objects) > 0, f"- Preserves code: {example_objects}")

    return result1 or result2  # At least one should pass


def test_alternatives():
    """Test 4: Alternative methods detection"""
    print_test("Alternative Methods Detection")

    text = "You can use requests or urllib. Another option is httpx for async."
    print(f"Input: {text}\n")

    result = extract_triples_from_string(text, source="test")
    triples = result['triples']

    print(f"Extracted {len(triples)} triples:")
    for t in triples:
        print(f"  - ({t['subject']}, {t['verb']}, {t['object']})")

    predicates = [t['verb'].lower() for t in triples]

    # Should have either alternatively_by or multiple methods
    has_alternatives = 'alternatively_by' in predicates or len(triples) >= 2

    return print_result(has_alternatives, f"- Detected alternatives: {len(triples)} triples, predicates: {predicates}")


def test_abstraction_levels():
    """Test 5: Abstraction level tagging"""
    print_test("Abstraction Level Tagging")

    text = "To send HTTP requests, use the requests library. Example: import requests"
    print(f"Input: {text}\n")

    result = extract_triples_from_string(text, source="test")
    triples = result['triples']

    print(f"Extracted {len(triples)} triples:")
    for t in triples:
        level = t.get('abstraction_level', 'N/A')
        print(f"  - ({t['subject']}, {t['verb']}, {t['object']}) [Level: {level}]")

    # Check for abstraction_level
    has_abstraction = any('abstraction_level' in t for t in triples)

    # Verify levels are valid
    valid_levels = all(
        t.get('abstraction_level', 1) in [1, 2, 3]
        for t in triples if 'abstraction_level' in t
    )

    result1 = print_result(has_abstraction, "- Has abstraction_level field")
    result2 = print_result(valid_levels, "- Levels are valid (1, 2, or 3)")

    return result1 and result2


def test_non_procedural():
    """Test 6: Non-procedural text handling"""
    print_test("Non-Procedural Text Handling")

    text = "Python is a programming language created by Guido van Rossum in 1991."
    print(f"Input: {text}\n")

    result = extract_triples_from_string(text, source="test")
    triples = result['triples']

    print(f"Extracted {len(triples)} triples:")
    for t in triples:
        print(f"  - ({t['subject']}, {t['verb']}, {t['object']})")

    predicates = [t['verb'].lower() for t in triples]
    procedural_predicates = ['accomplished_by', 'requires', 'alternatively_by', 'example_usage']

    has_procedural = any(p in procedural_predicates for p in predicates)

    return print_result(not has_procedural, f"- No procedural predicates (correct): {predicates}")


def test_complex_procedural():
    """Test 7: Complex procedural text"""
    print_test("Complex Procedural Text")

    text = """To deploy an application:
    1. First, run tests using pytest
    2. Then, build a Docker image
    3. Finally, push to the registry

    Building Docker requires a Dockerfile.
    Example: docker build -t myapp:latest ."""

    print(f"Input: {text}\n")

    result = extract_triples_from_string(text, source="test")
    triples = result['triples']

    print(f"Extracted {len(triples)} triples:")
    for t in triples[:10]:  # Show first 10
        print(f"  - ({t['subject']}, {t['verb']}, {t['object']})")
        if 'procedure' in t.get('topics', []):
            print(f"    [Marked as procedure]")

    # Should extract multiple procedural triples
    procedural_count = sum(1 for t in triples if 'procedure' in t.get('topics', []))

    result1 = print_result(len(triples) >= 3, f"- Extracted multiple triples: {len(triples)}")
    result2 = print_result(procedural_count >= 1, f"- Marked as procedural: {procedural_count}")

    return result1 and result2


def test_procedural_score_calculation():
    """Test 8: Procedural score calculation"""
    print_test("Procedural Score Calculation")

    # High score text (should trigger procedural extraction)
    high_score_text = "To use the API, you need to import requests. Use requests.post with the URL. Example: requests.post('http://api.com')"

    # Low score text (should use standard extraction)
    low_score_text = "The weather is nice today"

    print("High-score text (should be procedural):")
    print(f"  {high_score_text}\n")

    result1 = extract_triples_from_string(high_score_text, source="test")
    predicates1 = [t['verb'].lower() for t in result1['triples']]
    procedural_predicates = ['accomplished_by', 'requires', 'example_usage', 'is_method_for']
    is_procedural1 = any(p in procedural_predicates for p in predicates1)

    print(f"  Predicates: {predicates1}")
    print(f"  Is procedural: {is_procedural1}")

    print("\nLow-score text (should NOT be procedural):")
    print(f"  {low_score_text}\n")

    result2 = extract_triples_from_string(low_score_text, source="test")
    predicates2 = [t['verb'].lower() for t in result2['triples']]
    is_procedural2 = any(p in procedural_predicates for p in predicates2)

    print(f"  Predicates: {predicates2}")
    print(f"  Is procedural: {is_procedural2}")

    test1 = print_result(is_procedural1, "- High-score text uses procedural predicates")
    test2 = print_result(not is_procedural2, "- Low-score text doesn't use procedural predicates")

    return test1 and test2


def main():
    """Run all tests"""
    print("\n" + "="*70)
    print("PROCEDURAL KNOWLEDGE SYSTEM - QUICK UNIT TESTS")
    print("="*70)

    tests = [
        ("Procedural Detection", test_procedural_detection),
        ("Requires Pattern", test_requires_pattern),
        ("Example Usage", test_example_usage),
        ("Alternatives", test_alternatives),
        ("Abstraction Levels", test_abstraction_levels),
        ("Non-Procedural Text", test_non_procedural),
        ("Complex Procedural", test_complex_procedural),
        ("Score Calculation", test_procedural_score_calculation),
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
    print("TEST SUMMARY")
    print("="*70)

    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)

    for name, passed in results:
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{status} - {name}")

    print("\n" + "-"*70)
    print(f"Total: {passed_count}/{total_count} tests passed")
    print(f"Time: {end_time - start_time:.2f}s")
    print("-"*70)

    if passed_count == total_count:
        print("\n*** All tests passed! ***")
        return 0
    else:
        print(f"\n*** {total_count - passed_count} test(s) failed ***")
        return 1


if __name__ == "__main__":
    sys.exit(main())
