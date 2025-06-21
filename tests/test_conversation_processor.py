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
import sys
import time
import json
import atexit
import shutil
from datetime import datetime
from typing import Dict, List

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ConversationProcessor import ConversationProcessor
from AssociativeSemanticMemory import AssociativeSemanticMemory
from VectorKnowledgeGraph import VectorKnowledgeGraph
from utils import setup_logging

# Setup logging
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
log_file = f"test-output/conversation_processor_test_{timestamp}.log"
setup_logging(debug_mode=True, log_file=log_file)
logger = logging.getLogger('test_conversation_processor')

# Test directory for the knowledge graph
TEST_DIR = "test-output/Test_ConversationMemory"

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

def calculate_answer_score(expected_concepts: List[List[str]], actual_summary: str, query: str) -> Dict:
    """
    Calculate a score based on finding concepts in the summary.
    `expected_concepts` is a list of lists, where each inner list contains aliases for one concept.
    e.g., [["6 months", "six months"]]
    A concept is considered "found" if any of its aliases appear in the summary.
    """
    if not actual_summary:
        return {
            'score': 0.0,
            'found_keywords': [],
            'missing_keywords': [c[0] for c in expected_concepts],
            'total_expected': len(expected_concepts),
            'details': 'No summary provided'
        }
    
    summary_lower = actual_summary.lower()
    found_concepts_count = 0
    found_keywords = []
    missing_concepts = []

    if not expected_concepts:
        return {
            'score': 1.0, 'found_keywords': [], 'missing_keywords': [], 'total_expected': 0, 'details': 'No concepts expected'
        }

    for concept_aliases in expected_concepts:
        is_concept_found = False
        # Find the first alias that matches
        for alias in concept_aliases:
            if alias.lower() in summary_lower:
                is_concept_found = True
                found_keywords.append(alias)  # Log which alias was found
                break  # Move to the next concept
        
        if is_concept_found:
            found_concepts_count += 1
        else:
            # If no alias was found, the concept is missing
            missing_concepts.append(concept_aliases[0])  # Report the primary alias as missing
            
    total_concepts = len(expected_concepts)
    score = found_concepts_count / total_concepts if total_concepts > 0 else 1.0
    
    return {
        'score': score,
        'found_keywords': found_keywords,
        'missing_keywords': missing_concepts,
        'total_expected': total_concepts,
        'details': f'Found {found_concepts_count}/{total_concepts} expected concepts'
    }

def run_scored_memory_test(processor, queries_with_expected):
    """
    Run memory queries with scoring and return comprehensive results.
    """
    results = []
    total_score = 0.0
    total_reciprocal_rank = 0.0
    
    logger.info("=" * 60)
    logger.info("RUNNING SCORED MEMORY TEST")
    logger.info("=" * 60)
    
    for i, (query, expected_concepts) in enumerate(queries_with_expected, 1):
        print(f"🔍 Query {i}/{len(queries_with_expected)}: '{query}'")
        print(f"   🎯 Looking for: {expected_concepts}")
        
        logger.info(f"\nQuery {i}/#{len(queries_with_expected)}: '{query}'")
        logger.info(f"Expected concepts: {expected_concepts}")
        
        # Query the memory
        print("   ⏳ Searching memory...")
        query_result = processor.query_conversation_memory(
            query=query,
            entity_name="Sophia",
            limit=5,
            min_confidence=0.6
        )
        
        summary = query_result.get('summary', 'No summary provided.')
        retrieved_triples = query_result.get('triples', [])

        # NEW: determine ranking position of first relevant triple (for MRR)
        def _alias_rank(expected, triples_sorted):
            # Flatten aliases list
            aliases = [a for sub in expected for a in sub]
            for idx, (triple_tuple, _meta) in enumerate(triples_sorted):
                triple_text = " ".join(triple_tuple).lower()
                if any(alias.lower() in triple_text for alias in aliases):
                    return idx + 1  # 1-indexed rank
            return None

        # Sort triples by confidence for ranking calculations (use full list, not truncated)
        sorted_triples_full = sorted(retrieved_triples, key=lambda x: x[1].get('confidence', 0.0), reverse=True)
        rank_pos = _alias_rank(expected_concepts, sorted_triples_full)
        reciprocal_rank = 1 / rank_pos if rank_pos else 0

        # Calculate score
        score_info = calculate_answer_score(expected_concepts, summary, query)
        score_info['rank'] = rank_pos
        score_info['reciprocal_rank'] = reciprocal_rank
        
        # Show immediate feedback
        print(f"   📝 Summary: {summary}")
        if retrieved_triples:
            print(f"   🧠 Retrieved {len(retrieved_triples)} triples:")
            # Sort by confidence if available (reuse sorted_triples_full)
            sorted_triples = sorted_triples_full
            for i, (triple, metadata) in enumerate(sorted_triples[:3]): # Show top 3
                confidence_score = metadata.get('confidence')
                confidence_str = f"{confidence_score:.2f}" if isinstance(confidence_score, float) else "N/A"
                print(f"      {i+1}. {triple} (Confidence: {confidence_str}, Speaker: {metadata.get('speaker', 'N/A')})")
            if len(retrieved_triples) > 3:
                print("      ...")
        else:
            print("   🧠 No triples retrieved.")

        if score_info['score'] == 1.0:
            print(f"   ✅ Perfect score! Found all concepts: {score_info['found_keywords']}")
        elif score_info['score'] > 0.5:
            print(f"   ⚠️  Partial score ({score_info['score']:.2f}): Found {score_info['found_keywords']}")
            if score_info['missing_keywords']:
                print(f"   ❌ Missing: {score_info['missing_keywords']}")
        else:
            print(f"   ❌ Low score ({score_info['score']:.2f}): Only found {score_info['found_keywords']}")
            print(f"   🔍 Missing: {score_info['missing_keywords']}")
        
        print(f"   📊 Found {query_result.get('triple_count', 0)} related memories")
        print("")
        
        # Log results
        logger.info(f"Found {query_result.get('triple_count', 0)} related memories")
        logger.info(f"Summary: {summary}")
        logger.info(f"Score: {score_info['score']:.2f} ({score_info['details']})")
        
        if retrieved_triples:
            logger.info("Retrieved triples:")
            for triple, metadata in retrieved_triples:
                confidence_score = metadata.get('confidence')
                confidence_str = f"{confidence_score:.2f}" if isinstance(confidence_score, float) else "N/A"
                logger.info(f"  - {triple} (Confidence: {confidence_str}, Speaker: {metadata.get('speaker', 'N/A')})")
        
        if score_info['found_keywords']:
            logger.info(f"✓ Found concepts: {score_info['found_keywords']}")
        if score_info['missing_keywords']:
            logger.info(f"✗ Missing concepts: {score_info['missing_keywords']}")
        
        # Store results
        result_data = {
            'query': query,
            'expected_concepts': expected_concepts,
            'triple_count': query_result.get('triple_count', 0),
            'summary': summary,
            'retrieved_triples': retrieved_triples,
            'score_info': score_info,
        }
        results.append(result_data)
        total_score += score_info['score']
        # Accumulate reciprocal ranks for overall MRR
        total_reciprocal_rank += reciprocal_rank
        
        logger.info("-" * 50)
    
    # Calculate overall statistics
    average_score = total_score / len(queries_with_expected) if queries_with_expected else 0.0
    perfect_scores = sum(1 for r in results if r['score_info']['score'] == 1.0)
    zero_scores = sum(1 for r in results if r['score_info']['score'] == 0.0)
    
    print("📈 MEMORY TEST RESULTS:")
    print(f"   🎯 Total queries: {len(queries_with_expected)}")
    print(f"   ⭐ Average score: {average_score:.3f} ({average_score*100:.1f}%)")
    print(f"   🏆 Perfect scores: {perfect_scores}")
    print(f"   💔 Zero scores: {zero_scores}")
    print(f"   📊 Partial scores: {len(queries_with_expected) - perfect_scores - zero_scores}")
    
    logger.info("\n" + "=" * 60)
    logger.info("MEMORY TEST RESULTS SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Total queries: {len(queries_with_expected)}")
    logger.info(f"Average score: {average_score:.3f} ({average_score*100:.1f}%)")
    logger.info(f"Perfect scores (1.0): {perfect_scores}")
    logger.info(f"Zero scores (0.0): {zero_scores}")
    logger.info(f"Partial scores: {len(queries_with_expected) - perfect_scores - zero_scores}")
    
    # Grade assignment
    if average_score >= 0.9:
        grade = "A"
        grade_emoji = "🏆"
    elif average_score >= 0.8:
        grade = "B"
        grade_emoji = "🥈"
    elif average_score >= 0.7:
        grade = "C"
        grade_emoji = "🥉"
    elif average_score >= 0.6:
        grade = "D"
        grade_emoji = "📚"
    else:
        grade = "F"
        grade_emoji = "❌"
    
    print(f"   {grade_emoji} Overall Grade: {grade}")
    logger.info(f"Overall Grade: {grade}")
    logger.info("=" * 60)
    
    average_mrr = total_reciprocal_rank / len(queries_with_expected) if queries_with_expected else 0.0
    logger.info(f"Mean Reciprocal Rank (MRR): {average_mrr:.3f}")
    
    return {
        'results': results,
        'total_score': total_score,
        'average_score': average_score,
        'average_mrr': average_mrr,
        'perfect_scores': perfect_scores,
        'zero_scores': zero_scores,
        'grade': grade,
        'query_count': len(queries_with_expected)
    }

def export_test_results(results, filename):
    """Export test results to a JSON file."""
    logger.info(f"Exporting test results to {filename}...")
    
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
        logger.info(f"Successfully exported test results to {filename}")
        return True
    except Exception as e:
        logger.error(f"Error exporting test results: {e}")
        return False

def analyze_extracted_triples(export_file):
    """
    Analyze the exported triples to identify patterns and improvement areas.
    """
    print("🔬 ANALYZING EXTRACTED TRIPLES")
    print("=" * 60)
    
    logger.info("=" * 60)
    logger.info("ANALYZING EXTRACTED TRIPLES")
    logger.info("=" * 60)
    
    try:
        print("📖 Loading extracted triples...")
        with open(export_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(f"✅ Loaded {len(data)} triples for analysis")
    except Exception as e:
        print(f"❌ Could not load {export_file}: {e}")
        logger.error(f"Could not load {export_file}: {e}")
        return {}
    
    print("🔍 Analyzing triple patterns...")
    
    # Analysis metrics
    total_triples = len(data)
    original_triples = [t for t in data if not t['metadata'].get('is_from_summary', False)]
    summary_triples = [t for t in data if t['metadata'].get('is_from_summary', False)]
    
    print("👥 Analyzing speaker attribution...")
    # Speaker attribution analysis
    speaker_counts = {}
    speaker_accuracy = {"correct": 0, "incorrect": 0, "unknown": 0}
    
    for triple in data:
        speaker = triple['metadata'].get('speaker', 'unknown')
        if speaker not in speaker_counts:
            speaker_counts[speaker] = 0
        speaker_counts[speaker] += 1
        
        # Check speaker accuracy based on subject
        subject = triple['triple']['subject'].lower()
        # Ensure topics are present
        assert "topics" in triple['metadata'], f"Topics field missing in triple metadata: {triple['metadata']}"
        assert isinstance(triple['metadata']['topics'], list), f"Topics field is not a list: {triple['metadata']['topics']}"
        
        if speaker == 'Alex' and 'alex' in subject:
            speaker_accuracy['correct'] += 1
        elif speaker == 'Sophia' and 'sophia' in subject:
            speaker_accuracy['correct'] += 1
        elif speaker in ['Alex', 'Sophia'] and (subject == 'alex' or subject == 'sophia'):
            if (speaker == 'Alex' and subject == 'sophia') or (speaker == 'Sophia' and subject == 'alex'):
                speaker_accuracy['incorrect'] += 1
            else:
                speaker_accuracy['correct'] += 1
        else:
            speaker_accuracy['unknown'] += 1
    
    print("📝 Analyzing predicate usage...")
    # Predicate analysis
    predicate_counts = {}
    for triple in data:
        pred = triple['triple']['predicate']
        if pred not in predicate_counts:
            predicate_counts[pred] = 0
        predicate_counts[pred] += 1
    
    print("🎯 Checking specific detail preservation...")
    # Specific detail preservation analysis
    specific_details = {
        'dates': [],
        'names': [],
        'specific_items': [],
        'generic_terms': []
    }
    
    date_patterns = ['September 3', 'December 22', 'last week', 'this morning']
    name_patterns = ['Bob Marley', 'Joni Mitchell', 'Leonard Cohen', 'Chopin', 'Emily Dickinson', 'Virginia Woolf']
    specific_patterns = ['fish tacos', 'watercolor painting', 'coffee table', 'sunset scene', 'folk music', 'reggae']
    
    for triple in data:
        obj = triple['triple']['object']
        
        # Check for specific details
        for pattern in date_patterns:
            if pattern.lower() in obj.lower():
                specific_details['dates'].append(obj)
                break
        else:
            for pattern in name_patterns:
                if pattern.lower() in obj.lower():
                    specific_details['names'].append(obj)
                    break
            else:
                for pattern in specific_patterns:
                    if pattern.lower() in obj.lower():
                        specific_details['specific_items'].append(obj)
                        break
                else:
                    # Check if it's too generic
                    generic_terms = ['music', 'food', 'hobby', 'activity', 'thing', 'person']
                    if obj.lower() in generic_terms:
                        specific_details['generic_terms'].append(obj)
    
    # Log analysis results
    print("\n📊 ANALYSIS RESULTS:")
    print(f"📈 Total triples extracted: {total_triples}")
    print(f"📝 Original triples: {len(original_triples)}")
    print(f"📋 Summary triples: {len(summary_triples)}")
    print("")
    
    print("👥 SPEAKER ATTRIBUTION:")
    for speaker, count in speaker_counts.items():
        print(f"   {speaker}: {count} triples")
    accuracy_total = sum(speaker_accuracy.values())
    if accuracy_total > 0:
        accuracy_pct = (speaker_accuracy['correct'] / accuracy_total) * 100
        print(f"   Accuracy: {speaker_accuracy['correct']}/{accuracy_total} ({accuracy_pct:.1f}%)")
    print("")
    
    print("🔗 TOP PREDICATES:")
    sorted_predicates = sorted(predicate_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    for pred, count in sorted_predicates:
        print(f"   {pred}: {count}")
    print("")
    
    print("🎯 DETAIL PRESERVATION:")
    print(f"📅 Dates preserved: {len(specific_details['dates'])} - {specific_details['dates'][:3]}{'...' if len(specific_details['dates']) > 3 else ''}")
    print(f"👤 Names preserved: {len(specific_details['names'])} - {specific_details['names'][:3]}{'...' if len(specific_details['names']) > 3 else ''}")
    print(f"🎨 Specific items: {len(specific_details['specific_items'])} - {specific_details['specific_items'][:3]}{'...' if len(specific_details['specific_items']) > 3 else ''}")
    print(f"⚠️  Generic terms: {len(specific_details['generic_terms'])} - {specific_details['generic_terms']}")
    print("")
    
    # Calculate detail preservation score
    total_details = len(specific_details['dates']) + len(specific_details['names']) + len(specific_details['specific_items'])
    detail_score = total_details / (total_details + len(specific_details['generic_terms'])) if (total_details + len(specific_details['generic_terms'])) > 0 else 0
    
    if detail_score >= 0.9:
        detail_emoji = "🏆"
    elif detail_score >= 0.7:
        detail_emoji = "👍"
    else:
        detail_emoji = "⚠️"
    
    print(f"{detail_emoji} Detail preservation score: {detail_score:.3f} ({detail_score*100:.1f}%)")
    print("=" * 60)
    
    logger.info(f"Total triples extracted: {total_triples}")
    logger.info(f"Original triples: {len(original_triples)}")
    logger.info(f"Summary triples: {len(summary_triples)}")
    logger.info("")
    
    logger.info("SPEAKER ATTRIBUTION ANALYSIS:")
    for speaker, count in speaker_counts.items():
        logger.info(f"  {speaker}: {count} triples")
    logger.info(f"Speaker accuracy: {speaker_accuracy['correct']} correct, {speaker_accuracy['incorrect']} incorrect, {speaker_accuracy['unknown']} unknown")
    logger.info("")
    
    logger.info("PREDICATE ANALYSIS (Top 10):")
    sorted_predicates = sorted(predicate_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    for pred, count in sorted_predicates:
        logger.info(f"  {pred}: {count}")
    logger.info("")
    
    logger.info("SPECIFIC DETAIL PRESERVATION:")
    logger.info(f"Dates preserved: {len(specific_details['dates'])} - {specific_details['dates'][:5]}...")
    logger.info(f"Names preserved: {len(specific_details['names'])} - {specific_details['names'][:5]}...")
    logger.info(f"Specific items: {len(specific_details['specific_items'])} - {specific_details['specific_items'][:5]}...")
    logger.info(f"Generic terms (should be minimal): {len(specific_details['generic_terms'])} - {specific_details['generic_terms']}")
    logger.info("")
    
    logger.info(f"Detail preservation score: {detail_score:.3f} ({detail_score*100:.1f}%)")
    logger.info("=" * 60)
    
    return {
        'total_triples': total_triples,
        'original_count': len(original_triples),
        'summary_count': len(summary_triples),
        'speaker_counts': speaker_counts,
        'speaker_accuracy': speaker_accuracy,
        'top_predicates': sorted_predicates[:10],
        'detail_preservation': specific_details,
        'detail_score': detail_score
    }

def test_different_conversation_types(processor, kgraph, timestamp):
    """
    Test the system with different types of conversations to identify strengths and weaknesses.
    """
    logger.info("=" * 60)
    logger.info("TESTING DIFFERENT CONVERSATION TYPES")
    logger.info("=" * 60)
    
    test_scenarios = [
        {
            "name": "Emotional Support Conversation",
            "conversation": [
                {"role": "user", "name": "Jordan", "content": "I'm feeling really stressed about my job interview tomorrow at Microsoft."},
                {"role": "assistant", "name": "Sophia", "content": "I understand that feeling, Jordan. I felt similarly nervous before my presentation at Stanford last month. What specific aspect worries you most?"},
                {"role": "user", "name": "Jordan", "content": "I'm worried about the technical questions. I've been studying Python for 6 months but still feel unprepared."},
                {"role": "assistant", "name": "Sophia", "content": "Six months of Python study is actually quite substantial! I remember when I first learned JavaScript - it took me 8 months to feel confident. Have you practiced with any specific frameworks?"}
            ],
            "test_queries": [
                ("Where is Jordan's interview?", [["Microsoft"]]),
                ("What programming language has Jordan been studying?", [["Python"]]),
                ("How long has Jordan been studying?", [["6 months", "six months"]]),
                ("What presentation did Sophia give?", [["Stanford"]]),
                ("What programming language did Sophia learn?", [["JavaScript"]])
            ]
        },
        {
            "name": "Memory Sharing Conversation", 
            "conversation": [
                {"role": "user", "name": "Maya", "content": "I just got back from an amazing trip to Iceland. We saw the Northern Lights near Reykjavik on March 15th!"},
                {"role": "assistant", "name": "Sophia", "content": "That sounds incredible, Maya! I visited Iceland two years ago in February and saw them near Akureyri. The Aurora Borealis is absolutely magical. Did you stay at the Blue Lagoon?"},
                {"role": "user", "name": "Maya", "content": "No, we stayed at Hotel Borg in downtown Reykjavik. But we did visit the Blue Lagoon on our last day. Where did you stay?"},
                {"role": "assistant", "name": "Sophia", "content": "I stayed at a small guesthouse in Akureyri called Northern Comfort Inn. The host served amazing lamb stew every evening. What was your favorite meal there?"}
            ],
            "test_queries": [
                ("Where did Maya see the Northern Lights?", [["Iceland", "Reykjavik"]]),
                ("Where did Maya stay?", [["Hotel Borg"]]),
                ("Where did Sophia visit in Iceland?", [["Akureyri"]]),
                ("What did Sophia eat?", [["lamb stew"]]),
                ("Where did Sophia stay?", [["Northern Comfort Inn"]])
            ]
        }
    ]
    
    scenario_results_summary = []
    
    for scenario in test_scenarios:
        logger.info(f"\nTesting: {scenario['name']}")
        logger.info("-" * 40)
        
        # Process the conversation
        result = processor.process_conversation(
            messages=scenario['conversation'],
            entity_name="TestScenario"
        )
        
        if not result['success']:
            logger.error(f"Failed to process {scenario['name']}: {result.get('error')}")
            continue
            
        # Wait for processing
        time.sleep(1)
        
        # Test queries
        scenario_query_results = []
        scenario_score = 0
        max_score = 0
        
        print(f"\n🔬 Testing Scenario: {scenario['name']}")
        for query, expected_concepts in scenario['test_queries']:
            print(f"  - Query: '{query}'")
            logger.info(f"  Query: {query}")
            logger.info(f"  Expected: {expected_concepts}")
            
            query_result = processor.query_conversation_memory(
                query=query,
                entity_name="TestScenario",
                limit=5,
                min_confidence=0.6
            )
            
            summary = query_result.get('summary', 'No summary provided.')
            retrieved_triples = query_result.get('triples', [])
            
            # Calculate score
            score_info = calculate_answer_score(expected_concepts, summary, query)
            scenario_score += score_info['score']
            max_score += 1
            
            # Store detailed result for export
            result_data = {
                'query': query,
                'expected_concepts': expected_concepts,
                'triple_count': query_result.get('triple_count', 0),
                'summary': summary,
                'retrieved_triples': retrieved_triples,
                'score_info': score_info,
            }
            scenario_query_results.append(result_data)

            print(f"    📝 Summary: {summary}")
            if retrieved_triples:
                print(f"    🧠 Retrieved {len(retrieved_triples)} triples:")
                sorted_triples = sorted(retrieved_triples, key=lambda x: x[1].get('confidence', 0.0), reverse=True)
                for i, (triple, metadata) in enumerate(sorted_triples[:3]): # Show top 3
                    confidence_score = metadata.get('confidence')
                    confidence_str = f"{confidence_score:.2f}" if isinstance(confidence_score, float) else "N/A"
                    print(f"      {i+1}. {triple} (Confidence: {confidence_str})")
                if len(retrieved_triples) > 3:
                    print("      ...")
            else:
                print("    🧠 No triples retrieved.")

            if score_info['score'] == 1.0:
                print(f"    ✅ Perfect score! Found: {score_info['found_keywords']}")
            else:
                print(f"    ⚠️  Score: {score_info['score']:.2f} (Found: {score_info['found_keywords']}, Missing: {score_info['missing_keywords']})")
            print("")

            logger.info(f"  Summary: {summary}")
            if retrieved_triples:
                logger.info("  Retrieved triples:")
                for triple, metadata in retrieved_triples:
                    confidence_score = metadata.get('confidence')
                    confidence_str = f"{confidence_score:.2f}" if isinstance(confidence_score, float) else "N/A"
                    logger.info(f"    - {triple} (Confidence: {confidence_str}, Speaker: {metadata.get('speaker', 'N/A')})")
            
            logger.info(f"  Found concepts: {score_info['found_keywords']}")
            logger.info(f"  Missing concepts: {score_info['missing_keywords']}")
            logger.info(f"  Score: {score_info['score']:.2f}")
            logger.info("")
        
        avg_score = scenario_score / max_score if max_score > 0 else 0
        scenario_results_summary.append({
            'name': scenario['name'],
            'score': avg_score,
            'total_queries': max_score
        })

        logger.info(f"{scenario['name']} Overall Score: {avg_score:.3f} ({avg_score*100:.1f}%)")

        # --- Export results for this specific scenario ---
        scenario_name_slug = scenario['name'].replace(' ', '_').lower()
        
        # Create dictionary for export
        export_data = {
            'scenario_name': scenario['name'],
            'results': scenario_query_results,
            'average_score': avg_score,
            'perfect_scores': sum(1 for r in scenario_query_results if r['score_info']['score'] == 1.0),
            'zero_scores': sum(1 for r in scenario_query_results if r['score_info']['score'] == 0.0),
            'query_count': len(scenario_query_results)
        }
        
        # Export scenario test results
        scenario_results_filename = f"test-output/memory_test_results_{scenario_name_slug}_{timestamp}.json"
        print(f"💾 Exporting scenario results to {scenario_results_filename}...")
        export_test_results(export_data, scenario_results_filename)
        logger.info(f"Exported scenario results to {scenario_results_filename}")

        # Export triples snapshot
        scenario_triples_filename = f"test-output/conversation_triples_{scenario_name_slug}_{timestamp}.json"
        print(f"💾 Exporting triples snapshot to {scenario_triples_filename}...")
        export_triples_to_file(kgraph, scenario_triples_filename)
        logger.info(f"Exported triples snapshot to {scenario_triples_filename}")
        print("-" * 40)
    
    print("\nSCENARIO COMPARISON:")
    logger.info("\nSCENARIO COMPARISON:")
    for result in scenario_results_summary:
        print(f"  {result['name']}: {result['score']:.3f} ({result['score']*100:.1f}%)")
        logger.info(f"  {result['name']}: {result['score']:.3f} ({result['score']*100:.1f}%)")
    
    return scenario_results_summary

# ============================================
# NEW HELPER & WRAPPER FUNCTIONS (REFACTORING)
# ============================================

def initialize_memory():
    """Initializes the VectorKnowledgeGraph, AssociativeSemanticMemory and ConversationProcessor.

    Returns
    -------
    Tuple (kgraph, memory, processor)
    """
    print("📚 Initializing knowledge graph and memory...")
    logger.info("Initializing knowledge graph and memory stack")
    kgraph = VectorKnowledgeGraph(path=TEST_DIR)
    memory = AssociativeSemanticMemory(kgraph)
    processor = ConversationProcessor(memory)
    print("✅ Memory system initialized successfully!")
    return kgraph, memory, processor


def test_bidirectional_memory(processor, kgraph, timestamp):
    """Runs the original two-conversation bidirectional memory test.

    Returns
    -------
    (triple_count, test_results) as produced by the existing helper utilities
    """
    # ----- Conversation #1 (as in the original script) -----
    logger.info("Creating first conversation with personal details for bidirectional memory test")
    first_conversation = [
        {"role": "system", "content": "You are Sophia, a helpful AI assistant who remembers personal details about users."},
        {"role": "user", "name": "Alex", "content": "Hi Sophia, it's Alex again!"},
        {"role": "assistant", "name": "Sophia", "content": "Hello Alex! Great to see you back. I was just listening to some Chopin - his nocturnes always help me focus. How have you been?"},
        {"role": "user", "name": "Alex", "content": "Oh nice! I didn't know you liked classical music. I'm doing well - my birthday is coming up on September 3rd and I'm planning a barbecue."},
        {"role": "assistant", "name": "Sophia", "content": "September 3rd - I'll make sure to remember that! A barbecue sounds lovely. You know, my birthday is actually in December on the 22nd. I always love celebrating near the holidays. What kind of food are you planning for your barbecue?"},
        {"role": "user", "name": "Alex", "content": "That's so cool that we're both celebrating this year! I'm thinking Mexican food - maybe my specialty fish tacos. What's your favorite type of cuisine?"},
        {"role": "assistant", "name": "Sophia", "content": "December birthdays are special! I absolutely love Italian food - especially pasta dishes with fresh tomatoes and garlic. Your fish tacos sound amazing though. Are you planning any music for the barbecue?"},
        {"role": "user", "name": "Alex", "content": "I'm a huge fan of reggae music, especially Bob Marley. I'll probably make a playlist with his songs and similar artists. What about you - besides classical, do you like any other genres?"},
        {"role": "assistant", "name": "Sophia", "content": "Bob Marley is perfect for a barbecue! Besides classical, I really enjoy folk music - particularly Joni Mitchell and Leonard Cohen. There's something about their storytelling that fascinates me. I also have a soft spot for blues when I want something more soulful."},
        {"role": "user", "name": "Alex", "content": "That's such an interesting mix! I should explore more folk music. Do you have any hobbies besides music?"},
        {"role": "assistant", "name": "Sophia", "content": "I love painting watercolors and writing short stories - Emily Dickinson and Virginia Woolf are particular inspirations of mine. I also enjoy rock climbing, especially outdoor routes. There's something therapeutic about the physical challenge. What about you - any hobbies outside of cooking?"},
        {"role": "user", "name": "Alex", "content": "I love surfing and woodworking, especially making furniture. It's amazing how we both appreciate creative and outdoor activities!"}
    ]

    print("\n💬 Processing bidirectional memory conversation (1/2)...")
    result = processor.process_conversation(messages=first_conversation, entity_name="Sophia")
    if not result.get("success", False):
        raise RuntimeError(f"Failed to process first conversation: {result.get('error')}")

    # Wait briefly for vector store persistence
    time.sleep(1)

    # ----- Conversation #2  -----
    logger.info("Creating follow-up conversation to exercise recall")
    second_conversation = [
        {"role": "system", "content": "You are Sophia, a helpful AI assistant who remembers personal details about users."},
        {"role": "user", "name": "Alex", "content": "Hi Sophia! How are you doing today?"},
        {"role": "assistant", "name": "Sophia", "content": "Hello Alex! I'm doing well, thank you. I was just working on a watercolor painting this morning - trying to capture a sunset scene. How are your barbecue preparations going?"},
        {"role": "user", "name": "Alex", "content": "That's great! I forgot you're into painting. The barbecue is coming along well - I'm excited for September 3rd! When did you say your birthday was again?"},
        {"role": "assistant", "name": "Sophia", "content": "My birthday is December 22nd! I'm looking forward to it. Are you still planning to make your fish tacos for the barbecue?"},
        {"role": "user", "name": "Alex", "content": "Yes, definitely! And I've been working on that Bob Marley playlist. Have you been listening to any good folk music lately?"},
        {"role": "assistant", "name": "Sophia", "content": "Oh wonderful! I actually discovered some new Joni Mitchell songs last week that I've been enjoying. Your reggae playlist should be perfect for the barbecue atmosphere. Have you been doing any interesting woodworking projects recently?"},
        {"role": "user", "name": "Alex", "content": "I finished a coffee table last weekend! Speaking of your interests, have you read any good literature lately? I remember you mentioned loving Emily Dickinson."},
        {"role": "assistant", "name": "Sophia", "content": "Yes! I've been revisiting some Virginia Woolf recently - her stream of consciousness style is particularly beautiful this time of year. I think you'd appreciate her nature descriptions given your love for surfing and the outdoors. Maybe we should plan something special for our birthdays since they're both coming up this year!"}
    ]

    print("\n💬 Processing bidirectional memory conversation (2/2)...")
    result2 = processor.process_conversation(messages=second_conversation, entity_name="Sophia")
    if not result2.get("success", False):
        raise RuntimeError(f"Failed to process second conversation: {result2.get('error')}")

    # ---------------- Memory Queries ----------------
    queries_with_expected = [
        ("What is Alex's birthday?", [["September 3", "September 3rd"]]),
        ("What is Sophia's birthday?", [["December 22", "December 22nd"]]),
        ("What type of music does Alex like?", [["reggae", "Bob Marley"]]),
        ("What type of music does Sophia like?", [["classical", "Chopin"], ["folk", "Joni Mitchell", "Leonard Cohen"], ["blues"]]),
        ("What does Alex like to cook?", [["fish tacos", "Mexican food"]]),
        ("What food does Sophia prefer?", [["Italian", "pasta"]]),
        ("What are Alex's hobbies?", [["surfing", "surf"], ["woodworking", "making furniture"]]),
        ("What are Sophia's hobbies?", [["painting", "watercolor", "paints", "painter"], ["writing"], ["rock climbing", "rock climber"]]),
        ("What authors does Sophia read?", [["Emily Dickinson", "Dickinson"], ["Virginia Woolf", "Woolf"]]),
        ("What does Sophia paint?", [["watercolor", "sunset"]]),
        ("When are both Alex and Sophia's birthdays?", [["September 3", "September 3rd"], ["December 22", "December 22nd"]]),
        ("What do Alex and Sophia both enjoy that's creative?", [["woodworking", "making furniture", "woodworker"], ["painting", "writing", "painter", "writer"]]),
    ]

    print("\n🧠 Running bidirectional memory queries...")
    test_results = run_scored_memory_test(processor, queries_with_expected)

    # Export triples for later analysis
    export_file = f"test-output/conversation_triples_{timestamp}.json"
    triple_count = export_triples_to_file(kgraph, export_file)

    # Export test results
    results_file = f"test-output/memory_test_results_{timestamp}.json"
    export_test_results(test_results, results_file)

    return triple_count, test_results


def test_triple_analysis(kgraph, timestamp):
    """Wrapper around analyse_extracted_triples with fresh export from current graph."""
    export_file = f"test-output/conversation_triples_{timestamp}.json"
    if not os.path.exists(export_file):
        # Ensure we at least have a snapshot
        export_triples_to_file(kgraph, export_file)
    return analyze_extracted_triples(export_file)


def test_scenario_variations(processor, kgraph, timestamp):
    """Runs the additional scenario variation tests (emotional support & memory sharing)."""
    return test_different_conversation_types(processor, kgraph, timestamp)

# ============================================
# END NEW FUNCTIONS
# ============================================

def main():
    """Entry-point orchestrating the three organised tests."""
    atexit.register(cleanup_test_directory)

    print("🚀 Starting Conversation Memory Test Suite...")
    print("=" * 60)
    try:
        # --- Setup ---
        kgraph, memory, processor = initialize_memory()

        # --- Test 1: Bidirectional memory ---
        triple_count, test_results = test_bidirectional_memory(processor, kgraph, timestamp)

        # --- Test 2: Triple analysis ---
        analysis_results = test_triple_analysis(kgraph, timestamp)

        # --- Test 3: Scenario variations ---
        scenario_summary = test_scenario_variations(processor, kgraph, timestamp)

        # --- Final summary ---
        print("\n" + "=" * 60)
        print("🎯 FINAL TEST SUITE SUMMARY")
        print("=" * 60)
        print(f"Total triples stored: {triple_count}")
        print(f"Memory test average score: {test_results['average_score']:.3f} ({test_results['average_score']*100:.1f}%)")
        print(f"Memory test MRR: {test_results.get('average_mrr', 0):.3f}")
        print(f"Detail preservation score: {analysis_results.get('detail_score', 0):.3f}")
        print("Scenario Scores:")
        for scenario in scenario_summary:
            print(f"  - {scenario['name']}: {scenario['score']:.3f} ({scenario['score']*100:.1f}%)")
        print("=" * 60)

        # Close memory connections before cleanup
        memory.close()
        logger.info("Memory connections closed")

    except Exception as e:
        print(f"❌ Test suite failed: {e}")
        logger.error("Test suite failed", exc_info=True)
    finally:
        print("🧹 Cleaning up test directory...")
        cleanup_test_directory()
        print("✅ Test suite completed!")

if __name__ == "__main__":
    main()