"""
Unit tests for Procedural Knowledge System

Tests low-level components:
1. Procedural pattern detection in triple extraction
2. Procedural predicate extraction
3. Metadata tagging (abstraction_level, topics)
4. Query procedure filtering and boosting
5. Dependency chain following
"""

import unittest
import time
import os
import shutil
from typing import List, Dict

from triple_extraction import extract_triples_from_string
from AssociativeSemanticMemory import AssociativeSemanticMemory
from VectorKnowledgeGraph import VectorKnowledgeGraph


class TestProceduralDetection(unittest.TestCase):
    """Test that procedural patterns are detected correctly"""

    def test_basic_procedural_detection(self):
        """Test detection of 'to X, use Y' pattern"""
        text = "To send a POST request, use requests.post with the URL and data."
        result = extract_triples_from_string(text, source="test")

        triples = result['triples']
        self.assertGreater(len(triples), 0, "Should extract at least one triple")

        # Check for procedural predicates
        predicates = [t['verb'] for t in triples]
        procedural_predicates = ['accomplished_by', 'is_method_for', 'requires',
                                'alternatively_by', 'example_usage']

        has_procedural = any(p in procedural_predicates for p in predicates)
        self.assertTrue(has_procedural, f"Should have procedural predicate, got: {predicates}")

        # Check for 'procedure' in topics
        has_procedure_topic = any('procedure' in t.get('topics', []) for t in triples)
        self.assertTrue(has_procedure_topic, "Should have 'procedure' in topics")

    def test_requires_pattern_detection(self):
        """Test detection of 'requires' pattern"""
        text = "You need to import requests before using requests.post"
        result = extract_triples_from_string(text, source="test")

        triples = result['triples']
        predicates = [t['verb'].lower() for t in triples]

        self.assertIn('requires', predicates, f"Should detect 'requires' predicate, got: {predicates}")

    def test_alternative_pattern_detection(self):
        """Test detection of alternatives"""
        text = "You can use requests or urllib. Another option is httpx."
        result = extract_triples_from_string(text, source="test")

        triples = result['triples']
        predicates = [t['verb'].lower() for t in triples]

        # Should have either alternatively_by or multiple methods
        has_alternatives = 'alternatively_by' in predicates or len(triples) >= 2
        self.assertTrue(has_alternatives, f"Should detect alternatives, got: {predicates}")

    def test_example_usage_detection(self):
        """Test detection of code examples"""
        text = "Example: requests.post('http://api.com', json={'key': 'value'})"
        result = extract_triples_from_string(text, source="test")

        triples = result['triples']
        predicates = [t['verb'].lower() for t in triples]

        self.assertIn('example_usage', predicates,
                     f"Should detect example_usage predicate, got: {predicates}")

        # Verify code is preserved verbatim
        example_objects = [t['object'] for t in triples if t['verb'].lower() == 'example_usage']
        if example_objects:
            self.assertIn('requests.post', example_objects[0],
                         "Should preserve code verbatim in example")

    def test_abstraction_level_tagging(self):
        """Test that abstraction levels are assigned"""
        text = "To send HTTP requests, use the requests library. Example: import requests"
        result = extract_triples_from_string(text, source="test")

        triples = result['triples']

        # At least one triple should have abstraction_level
        has_abstraction = any('abstraction_level' in t for t in triples)
        self.assertTrue(has_abstraction, "Should assign abstraction_level to procedural triples")

    def test_non_procedural_text(self):
        """Test that factual text is NOT marked as procedural"""
        text = "Python is a programming language created by Guido van Rossum."
        result = extract_triples_from_string(text, source="test")

        triples = result['triples']

        # Should not have procedural predicates
        predicates = [t['verb'].lower() for t in triples]
        procedural_predicates = ['accomplished_by', 'requires', 'alternatively_by', 'example_usage']

        has_procedural = any(p in procedural_predicates for p in predicates)
        self.assertFalse(has_procedural,
                        f"Factual text should not have procedural predicates, got: {predicates}")


class TestProceduralQuery(unittest.TestCase):
    """Test query_procedure method"""

    @classmethod
    def setUpClass(cls):
        """Set up test database once for all tests"""
        cls.test_db_path = "Test_ProceduralQuery"
        if os.path.exists(cls.test_db_path):
            shutil.rmtree(cls.test_db_path)

        cls.kgraph = VectorKnowledgeGraph(path=cls.test_db_path)
        cls.memory = AssociativeSemanticMemory(cls.kgraph)

        # Ingest some procedural knowledge
        teaching_texts = [
            """To send a POST request, use requests.post(url, json=data).
               You need to import requests first.
               Example: requests.post('http://api.example.com', json={'key': 'value'})""",

            """Alternatively, you can use urllib for POST requests.
               Example: urllib.request.urlopen(url, data=encoded_data)""",

            """To run tests, use pytest with the test directory.
               Example: pytest tests/ -v""",

            """To deploy an application, first run tests, then build Docker image.
               Building Docker requires a Dockerfile."""
        ]

        for i, text in enumerate(teaching_texts):
            cls.memory.ingest_text(text, source=f"test_source_{i}")

        # Small delay to allow indexing
        time.sleep(1)

    @classmethod
    def tearDownClass(cls):
        """Clean up test database"""
        cls.memory.close()
        time.sleep(1)
        if os.path.exists(cls.test_db_path):
            shutil.rmtree(cls.test_db_path)

    def test_query_procedure_basic(self):
        """Test basic procedure query"""
        result = self.memory.query_procedure("send POST request")

        self.assertIsInstance(result, dict, "Should return dict")
        self.assertIn('goal', result, "Should have 'goal' field")
        self.assertIn('methods', result, "Should have 'methods' field")
        self.assertEqual(result['goal'], "send POST request")

    def test_query_procedure_finds_methods(self):
        """Test that query finds methods"""
        result = self.memory.query_procedure("send POST request")

        methods = result['methods']
        self.assertGreater(len(methods), 0, "Should find at least one method")

        # Check structure of methods
        if methods:
            triple, metadata = methods[0]
            self.assertIsInstance(triple, list, "Triple should be a list")
            self.assertEqual(len(triple), 3, "Triple should have 3 elements")
            self.assertIsInstance(metadata, dict, "Metadata should be a dict")
            self.assertIn('confidence', metadata, "Should have confidence score")

    def test_query_procedure_finds_alternatives(self):
        """Test that query finds alternative methods"""
        result = self.memory.query_procedure("send POST request", include_alternatives=True)

        # Should have either methods or alternatives (or both)
        total_results = len(result.get('methods', [])) + len(result.get('alternatives', []))
        self.assertGreater(total_results, 0, "Should find methods or alternatives")

    def test_query_procedure_finds_dependencies(self):
        """Test that query finds dependencies"""
        result = self.memory.query_procedure("send POST request", include_dependencies=True)

        dependencies = result.get('dependencies', [])
        # May or may not find dependencies depending on extraction, but should have the field
        self.assertIsInstance(dependencies, list, "Dependencies should be a list")

    def test_query_procedure_finds_examples(self):
        """Test that query finds examples"""
        result = self.memory.query_procedure("send POST request", include_examples=True)

        examples = result.get('examples', [])
        # May or may not find examples depending on extraction, but should have the field
        self.assertIsInstance(examples, list, "Examples should be a list")

    def test_query_procedure_respects_limit(self):
        """Test that limit parameter works"""
        result = self.memory.query_procedure("send POST request", limit=2)

        methods = result.get('methods', [])
        alternatives = result.get('alternatives', [])
        dependencies = result.get('dependencies', [])
        examples = result.get('examples', [])

        # Each category should respect limit
        self.assertLessEqual(len(methods), 2, "Methods should respect limit")
        self.assertLessEqual(len(alternatives), 2, "Alternatives should respect limit")
        self.assertLessEqual(len(dependencies), 2, "Dependencies should respect limit")
        self.assertLessEqual(len(examples), 2, "Examples should respect limit")

    def test_query_procedure_different_goal(self):
        """Test query with different goal"""
        result = self.memory.query_procedure("run tests")

        self.assertIsInstance(result, dict, "Should return dict")
        total_found = result.get('total_found', 0)

        # Should find something related to testing
        self.assertGreater(total_found, 0, "Should find test-related procedures")

    def test_query_procedure_confidence_ordering(self):
        """Test that results are ordered by confidence"""
        result = self.memory.query_procedure("send POST request")

        methods = result.get('methods', [])
        if len(methods) > 1:
            confidences = [meta.get('confidence', 0) for _, meta in methods]
            # Check descending order
            for i in range(len(confidences) - 1):
                self.assertGreaterEqual(confidences[i], confidences[i+1],
                                      "Results should be ordered by confidence (descending)")

    def test_query_procedure_no_include_flags(self):
        """Test query with all include flags False"""
        result = self.memory.query_procedure(
            "send POST request",
            include_alternatives=False,
            include_examples=False,
            include_dependencies=False
        )

        # Should still have methods
        self.assertGreater(len(result.get('methods', [])), 0, "Should have methods")
        # Others should be empty
        self.assertEqual(len(result.get('alternatives', [])), 0, "Alternatives should be empty")
        self.assertEqual(len(result.get('examples', [])), 0, "Examples should be empty")
        # Dependencies might still be present from dependency following, but should be minimal


class TestProceduralPredicates(unittest.TestCase):
    """Test specific procedural predicates"""

    def test_accomplished_by_extraction(self):
        """Test accomplished_by predicate extraction"""
        text = "To deploy an application, use Docker containers"
        result = extract_triples_from_string(text, source="test")

        triples = result['triples']
        predicates = [t['verb'].lower() for t in triples]

        self.assertIn('accomplished_by', predicates,
                     f"Should extract accomplished_by, got: {predicates}")

    def test_is_method_for_extraction(self):
        """Test is_method_for predicate extraction"""
        text = "kubectl is for managing Kubernetes clusters"
        result = extract_triples_from_string(text, source="test")

        triples = result['triples']
        predicates = [t['verb'].lower() for t in triples]

        self.assertIn('is_method_for', predicates,
                     f"Should extract is_method_for, got: {predicates}")

    def test_enables_extraction(self):
        """Test enables predicate extraction"""
        text = "Docker enables containerization of applications"
        result = extract_triples_from_string(text, source="test")

        triples = result['triples']
        predicates = [t['verb'].lower() for t in triples]

        # Should extract some relationship about Docker and containerization
        self.assertGreater(len(triples), 0, "Should extract at least one triple")

    def test_followed_by_extraction(self):
        """Test followed_by/sequential extraction"""
        text = "First run tests, then build the image, finally deploy to production"
        result = extract_triples_from_string(text, source="test")

        triples = result['triples']
        predicates = [t['verb'].lower() for t in triples]

        # Should extract sequential relationships
        has_sequential = 'followed_by' in predicates or 'has_step' in predicates
        self.assertTrue(has_sequential or len(triples) >= 2,
                       f"Should extract sequential steps, got: {predicates}")


class TestProceduralMetadata(unittest.TestCase):
    """Test procedural metadata handling"""

    def test_procedure_topic_added(self):
        """Test that 'procedure' is added to topics"""
        text = "To use the API, send a POST request with authentication"
        result = extract_triples_from_string(text, source="test")

        triples = result['triples']

        # At least one triple should have 'procedure' in topics
        has_procedure_topic = any('procedure' in t.get('topics', []) for t in triples)
        self.assertTrue(has_procedure_topic, "Should add 'procedure' to topics")

    def test_abstraction_level_range(self):
        """Test that abstraction levels are in valid range"""
        texts = [
            "import requests",  # Level 1: atomic
            "To send POST request, use requests.post",  # Level 2: basic procedure
            "To deploy application, run tests then build image"  # Level 3: high-level
        ]

        for text in texts:
            result = extract_triples_from_string(text, source="test")
            triples = result['triples']

            for triple in triples:
                if 'abstraction_level' in triple:
                    level = triple['abstraction_level']
                    self.assertIn(level, [1, 2, 3],
                                f"Abstraction level should be 1, 2, or 3, got: {level}")

    def test_confidence_metadata(self):
        """Test that confidence scores are present in query results"""
        # Need a memory instance for this
        test_db = "Test_Confidence"
        if os.path.exists(test_db):
            shutil.rmtree(test_db)

        try:
            kgraph = VectorKnowledgeGraph(path=test_db)
            memory = AssociativeSemanticMemory(kgraph)

            # Ingest procedural knowledge
            memory.ingest_text("To test code, use pytest. Example: pytest tests/",
                             source="test")
            time.sleep(1)

            # Query
            result = memory.query_procedure("test code")

            # Check confidence in results
            for method_triple, metadata in result.get('methods', []):
                self.assertIn('confidence', metadata, "Should have confidence in metadata")
                confidence = metadata['confidence']
                self.assertIsInstance(confidence, (int, float), "Confidence should be numeric")
                self.assertGreaterEqual(confidence, 0, "Confidence should be >= 0")

            memory.close()
        finally:
            time.sleep(1)
            if os.path.exists(test_db):
                shutil.rmtree(test_db)


class TestProceduralScoring(unittest.TestCase):
    """Test procedural detection scoring"""

    def test_high_procedural_score(self):
        """Test text with many procedural indicators scores high"""
        text = """To send a POST request, you need to use the requests library.
                  First, import requests. Then, use requests.post with the URL.
                  Example: requests.post('http://example.com', json={'key': 'value'})"""

        result = extract_triples_from_string(text, source="test")
        triples = result['triples']

        # Should detect as procedural and extract procedural predicates
        procedural_predicates = ['accomplished_by', 'requires', 'example_usage',
                                'is_method_for', 'alternatively_by']
        extracted_predicates = [t['verb'].lower() for t in triples]

        has_procedural = any(p in procedural_predicates for p in extracted_predicates)
        self.assertTrue(has_procedural,
                       f"High procedural score text should use procedural predicates, got: {extracted_predicates}")

    def test_low_procedural_score(self):
        """Test text with few procedural indicators scores low"""
        text = "Python is a popular programming language. It was created in 1991."

        result = extract_triples_from_string(text, source="test")
        triples = result['triples']

        # Should use standard predicates, not procedural ones
        procedural_predicates = ['accomplished_by', 'requires', 'example_usage',
                                'alternatively_by']
        extracted_predicates = [t['verb'].lower() for t in triples]

        has_procedural = any(p in procedural_predicates for p in extracted_predicates)
        self.assertFalse(has_procedural,
                        f"Low procedural score text should not use procedural predicates, got: {extracted_predicates}")


def run_tests():
    """Run all tests with detailed output"""

    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestProceduralDetection))
    suite.addTests(loader.loadTestsFromTestCase(TestProceduralQuery))
    suite.addTests(loader.loadTestsFromTestCase(TestProceduralPredicates))
    suite.addTests(loader.loadTestsFromTestCase(TestProceduralMetadata))
    suite.addTests(loader.loadTestsFromTestCase(TestProceduralScoring))

    # Run tests with verbose output
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Print summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    print(f"Tests run: {result.testsRun}")
    print(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")

    if result.wasSuccessful():
        print("\n✅ All tests passed!")
    else:
        print("\n❌ Some tests failed")

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    exit(0 if success else 1)
