#!/usr/bin/env python3
"""
Test script for ChatMemoryInterface with graded conversation simulation.

This script:
1. Bootstraps knowledge graph with Vocaloid and BlazBlue information
2. Runs simulated conversations with real LLM responses
3. Grades responses based on memory context utilization
4. Shows injected memory context for transparency
"""

import logging
import os
import sys
import time
import json
import shutil
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Any
from openai import OpenAI
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from DocumentProcessor import DocumentProcessor, WebPageSource
from AssociativeSemanticMemory import AssociativeSemanticMemory
from VectorKnowledgeGraph import VectorKnowledgeGraph
from ChatMemoryInterface import ChatMemoryInterface
from utils import setup_logging

# Load environment variables
load_dotenv()

# Test directory for the knowledge graph
TEST_DIR = "test-output/Test_ChatMemoryInterface"
LOG_FILE = None

class ConversationGrader:
    """Grades LLM responses based on memory context utilization."""
    
    def __init__(self):
        self.client = OpenAI(
            base_url=os.getenv('LLM_API_BASE'),
            api_key=os.getenv('LLM_API_KEY'),
        )
        self.logger = logging.getLogger('ConversationGrader')
    
    def grade_response(self, user_query: str, memory_context: str, 
                      llm_response: str, expected_topics: List[str]) -> Dict[str, Any]:
        """
        Grade how well the LLM response utilizes the provided memory context.
        
        Args:
            user_query: The user's question
            memory_context: Memory information provided to the LLM
            llm_response: The LLM's response
            expected_topics: Topics we expect to see addressed
            
        Returns:
            Dict with grading results and analysis
        """
        grading_prompt = f"""
You are grading an AI assistant's response based on how well it uses provided memory context.

USER QUERY: {user_query}

MEMORY CONTEXT PROVIDED TO AI:
{memory_context}

AI'S RESPONSE:
{llm_response}

EXPECTED TOPICS TO ADDRESS: {', '.join(expected_topics)}

Grade the response on these criteria (0-10 scale each):
1. CONTEXT_USAGE: How well did the AI use the provided memory context?
2. ACCURACY: How accurate is the information in the response?
3. COMPLETENESS: How completely does it address the user's query?
4. COHERENCE: How well organized and coherent is the response?
5. EXPECTED_COVERAGE: How well does it cover the expected topics?

Return ONLY a JSON object with this structure:
{{
    "context_usage": {{
        "score": 0-10,
        "explanation": "brief explanation"
    }},
    "accuracy": {{
        "score": 0-10, 
        "explanation": "brief explanation"
    }},
    "completeness": {{
        "score": 0-10,
        "explanation": "brief explanation" 
    }},
    "coherence": {{
        "score": 0-10,
        "explanation": "brief explanation"
    }},
    "expected_coverage": {{
        "score": 0-10,
        "explanation": "brief explanation"
    }},
    "overall_score": 0-10,
    "overall_grade": "A/B/C/D/F",
    "key_strengths": ["strength1", "strength2"],
    "key_weaknesses": ["weakness1", "weakness2"],
    "memory_context_used": true/false,
    "factual_errors": ["error1", "error2"] or []
}}
"""

        try:
            response = self.client.chat.completions.create(
                model=os.getenv('EXTRACTION_MODEL', 'gemma-3-4b-it-qat'),
                messages=[{"role": "user", "content": grading_prompt}],
                temperature=0.1,
                max_tokens=1000
            )
            
            content = response.choices[0].message.content.strip()
            
            # Handle markdown code blocks
            if content.startswith('```json') and content.endswith('```'):
                json_start = content.find('```json') + 7
                json_end = content.rfind('```')
                content = content[json_start:json_end].strip()
            elif content.startswith('```') and content.endswith('```'):
                json_start = content.find('```') + 3
                json_end = content.rfind('```')
                content = content[json_start:json_end].strip()
                
            grading_result = json.loads(content)
            
            # Calculate overall score if not provided
            if 'overall_score' not in grading_result:
                scores = [
                    grading_result.get('context_usage', {}).get('score', 0),
                    grading_result.get('accuracy', {}).get('score', 0),
                    grading_result.get('completeness', {}).get('score', 0),
                    grading_result.get('coherence', {}).get('score', 0),
                    grading_result.get('expected_coverage', {}).get('score', 0)
                ]
                grading_result['overall_score'] = sum(scores) / len(scores)
            
            # Assign letter grade if not provided
            if 'overall_grade' not in grading_result:
                score = grading_result['overall_score']
                if score >= 9: grading_result['overall_grade'] = 'A'
                elif score >= 8: grading_result['overall_grade'] = 'B'
                elif score >= 7: grading_result['overall_grade'] = 'C'
                elif score >= 6: grading_result['overall_grade'] = 'D'
                else: grading_result['overall_grade'] = 'F'
            
            return grading_result
            
        except Exception as e:
            self.logger.error(f"Grading failed: {e}")
            return {
                "error": str(e),
                "overall_score": 0,
                "overall_grade": "F",
                "context_usage": {"score": 0, "explanation": "Grading failed"},
                "accuracy": {"score": 0, "explanation": "Grading failed"},
                "completeness": {"score": 0, "explanation": "Grading failed"},
                "coherence": {"score": 0, "explanation": "Grading failed"},
                "expected_coverage": {"score": 0, "explanation": "Grading failed"}
            }

class ConversationSimulator:
    """Simulates conversations with real LLM responses using memory context."""
    
    def __init__(self, chat_interface: ChatMemoryInterface):
        self.chat_interface = chat_interface
        self.client = OpenAI(
            base_url=os.getenv('LLM_API_BASE'),
            api_key=os.getenv('LLM_API_KEY'),
        )
        self.logger = logging.getLogger('ConversationSimulator')
    
    def simulate_response(self, user_query: str, session_id: str, 
                         system_prompt: str = None) -> Dict[str, Any]:
        """
        Simulate an LLM response using memory context.
        
        Args:
            user_query: User's question
            session_id: Session ID for memory context
            system_prompt: Optional system prompt override
            
        Returns:
            Dict with response, memory context used, and metadata
        """
        # Get memory context
        memory_result = self.chat_interface.search_with_context(
            query=user_query,
            session_id=session_id,
            limit=12  # Get more context for better responses
        )
        
        memory_data = memory_result.get('results', {})
        memory_triples = memory_data.get('triples', [])
        memory_summary = memory_data.get('summary', '')
        
        # Format memory context for the LLM
        memory_context = self._format_memory_context(memory_triples, memory_summary)
        
        # Default system prompt
        if not system_prompt:
            system_prompt = """You are Sophia, an AI assistant with knowledge and memories from previous conversations and research. When relevant information comes to mind from your memory, naturally incorporate it into the conversation as you would recall things in a normal discussion. Don't explicitly mention "memory context" or "knowledge base" - just speak naturally as if you remember or know these things."""
        
        # Create the conversation with memory context framed for natural conversation
        messages = [
            {"role": "system", "content": system_prompt},
        ]
        
        if memory_context:
            # Frame memory context as natural recollection rather than external knowledge
            contextual_memory = self._frame_as_conversation_memory(memory_context, user_query)
            messages.append({
                "role": "system", 
                "content": f"Some relevant things you remember or know about this topic:\n\n{contextual_memory}\n\nIncorporate this naturally into your response as appropriate, as you would in a normal conversation."
            })
        
        messages.append({"role": "user", "content": user_query})
        
        try:
            response = self.client.chat.completions.create(
                model=os.getenv('EXTRACTION_MODEL', 'gemma-3-4b-it-qat'),
                messages=messages,
                temperature=0.7,
                max_tokens=500
            )
            
            llm_response = response.choices[0].message.content
            
            return {
                'user_query': user_query,
                'llm_response': llm_response,
                'memory_context_raw': memory_triples,
                'memory_context_formatted': memory_context,
                'memory_summary': memory_summary,
                'memory_result_count': len(memory_triples),
                'session_id': session_id,
                'processing_time': memory_result.get('processing_time', 0)
            }
            
        except Exception as e:
            self.logger.error(f"Response simulation failed: {e}")
            return {
                'user_query': user_query,
                'llm_response': f"Error generating response: {e}",
                'memory_context_raw': memory_triples,
                'memory_context_formatted': memory_context,
                'error': str(e)
            }
    
    def _format_memory_context(self, triples: List[Tuple], summary: str) -> str:
        """Format memory triples and summary into readable context."""
        if not triples and not summary:
            return ""
        
        context_parts = []
        
        if summary:
            context_parts.append(f"SUMMARY: {summary}")
            context_parts.append("")
        
        if triples:
            context_parts.append("DETAILED INFORMATION:")
            for i, (triple, metadata) in enumerate(triples[:6], 1):  # Limit to top 6
                confidence = metadata.get('confidence', 0)
                subject, predicate, obj = triple
                context_parts.append(f"{i}. {subject} {predicate} {obj} (confidence: {confidence:.2f})")
                
                # Add source if available
                source = metadata.get('source', '')
                if source:
                    context_parts.append(f"   Source: {source}")
        
        return "\n".join(context_parts)
    
    def _frame_as_conversation_memory(self, memory_context: str, user_query: str) -> str:
        """Frame memory context as natural conversational recollection."""
        if not memory_context:
            return ""
        
        # Extract key information from the structured memory context
        lines = memory_context.split('\n')
        conversational_parts = []
        
        # Process summary into conversational tone
        for line in lines:
            if line.startswith("SUMMARY:"):
                summary_text = line.replace("SUMMARY: ", "").strip()
                if summary_text and summary_text != "No relevant information found.":
                    conversational_parts.append(summary_text)
            elif line.strip() and not line.startswith("DETAILED INFORMATION:") and ". " in line and "confidence:" in line:
                # Convert structured triple info to conversational facts
                # Remove the numbering and confidence scores for more natural flow
                clean_line = line.split(". ", 1)[1] if ". " in line else line
                if "(confidence:" in clean_line:
                    fact = clean_line.split(" (confidence:")[0].strip()
                    conversational_parts.append(fact)
        
        if not conversational_parts:
            return ""
        
        # Simple, consistent framing - no conditional logic
        return "Things that come to mind:\n" + "\n".join(f"- {part}" for part in conversational_parts)

def bootstrap_knowledge_graph(memory: AssociativeSemanticMemory) -> Dict[str, Any]:
    """Bootstrap the knowledge graph with Vocaloid and BlazBlue information."""
    logger = logging.getLogger('bootstrap')
    logger.info("Bootstrapping knowledge graph with test data...")
    
    # URLs to process (same as document processor test)
    bootstrap_urls = [
        "https://en.wikipedia.org/wiki/Vocaloid",
        "https://vocaloid.fandom.com/wiki/Hatsune_Miku", 
        "https://vocaloid.fandom.com/wiki/Kasane_Teto",
        "https://blazblue.fandom.com/wiki/Ragna_the_Bloodedge",
        "https://blazblue.fandom.com/wiki/Centralfiction",
        "https://blazblue.fandom.com/wiki/Rachel_Alucard"
    ]
    
    processor = DocumentProcessor(memory)
    total_processed = 0
    total_failed = 0
    processing_times = []
    
    for i, url in enumerate(bootstrap_urls, 1):
        logger.info(f"Processing URL {i}/{len(bootstrap_urls)}: {url}")
        start_time = time.time()
        
        try:
            source = WebPageSource(url)
            result = processor.process_document(source)
            
            if result['success']:
                total_processed += result['processed_chunks']
                processing_time = time.time() - start_time
                processing_times.append(processing_time)
                logger.info(f"✅ Processed {result['processed_chunks']} chunks in {processing_time:.2f}s")
            else:
                total_failed += 1
                logger.error(f"❌ Failed to process {url}: {result.get('error', 'Unknown error')}")
        
        except Exception as e:
            total_failed += 1
            logger.error(f"❌ Exception processing {url}: {e}")
            continue
    
    bootstrap_result = {
        'urls_processed': len(bootstrap_urls) - total_failed,
        'urls_failed': total_failed,
        'total_chunks': total_processed,
        'avg_processing_time': sum(processing_times) / len(processing_times) if processing_times else 0,
        'total_time': sum(processing_times)
    }
    
    logger.info(f"Bootstrap complete: {bootstrap_result}")
    return bootstrap_result

def run_conversation_scenarios(chat_interface: ChatMemoryInterface, 
                             simulator: ConversationSimulator,
                             grader: ConversationGrader) -> List[Dict[str, Any]]:
    """Run predefined conversation scenarios and grade responses."""
    logger = logging.getLogger('scenarios')
    
    # Define test scenarios with expected topics
    scenarios = [
        {
            "name": "Vocaloid Discovery", 
            "session_id": "vocaloid_session",
            "queries": [
                {
                    "query": "I've been hearing a lot about this Vocaloid thing lately, but I'm not really sure what it is. Can you tell me about it?",
                    "expected_topics": ["voice synthesis", "software", "music", "Japanese", "Crypton"]
                },
                {
                    "query": "That's fascinating! I keep seeing this blue-haired character everywhere online. I think it's Hatsune Miku? What's her story?",
                    "expected_topics": ["Hatsune Miku", "CV01", "Saki Fujita", "turquoise", "popular"]
                },
                {
                    "query": "Someone also mentioned a character called Kasane Teto to me. Have you heard of her?",
                    "expected_topics": ["Kasane Teto", "UTAU", "chimera", "drill hair", "April Fools"]
                }
            ]
        },
        {
            "name": "BlazBlue Discussion",
            "session_id": "blazblue_session", 
            "queries": [
                {
                    "query": "I'm getting into fighting games and my friend mentioned this character Ragna the Bloodedge. Do you know anything about him?",
                    "expected_topics": ["Ragna", "protagonist", "Azure Grimoire", "brother", "rebellion"]
                },
                {
                    "query": "Cool! What about BlazBlue: Centralfiction? Is that a good one to start with?",
                    "expected_topics": ["Centralfiction", "fourth installment", "fighting game", "Arc System Works", "story mode"]
                },
                {
                    "query": "I've heard there's this vampire character in the series too. Rachel something?",
                    "expected_topics": ["Rachel", "vampire", "noble", "observer", "red eyes"]
                }
            ]
        },
        {
            "name": "Casual Chat",
            "session_id": "crossdomain_session",
            "queries": [
                {
                    "query": "This is kind of random, but do you think there are any interesting connections between Vocaloid and fighting games?", 
                    "expected_topics": ["music", "collaboration", "soundtrack", "fan culture"]
                },
                {
                    "query": "I'm really interested in Japanese digital characters and virtual idols. What are some examples you know of?",
                    "expected_topics": ["Vocaloid", "virtual", "digital", "anime", "games"]
                }
            ]
        }
    ]
    
    all_results = []
    scenario_summaries = []
    
    for scenario in scenarios:
        logger.info(f"\n{'='*60}")
        logger.info(f"RUNNING SCENARIO: {scenario['name']}")
        logger.info(f"{'='*60}")
        
        scenario_results = []
        total_score = 0
        query_count = 0
        
        for query_data in scenario['queries']:
            query = query_data['query']
            expected_topics = query_data['expected_topics']
            session_id = scenario['session_id']
            
            logger.info(f"\n🔍 Query: {query}")
            logger.info(f"📝 Expected topics: {expected_topics}")
            
            # Simulate the response
            print(f"\n🤖 Processing query: '{query}'")
            response_data = simulator.simulate_response(query, session_id)
            
            # Show memory context that was injected
            memory_context = response_data.get('memory_context_formatted', '')
            if memory_context:
                print(f"\n💭 MEMORY CONTEXT INJECTED:")
                print("─" * 50)
                print(memory_context)
                print("─" * 50)
            else:
                print(f"\n💭 No memory context available for this query")
            
            # Show the LLM response
            llm_response = response_data.get('llm_response', '')
            print(f"\n🤖 LLM RESPONSE:")
            print("─" * 50)
            print(llm_response)
            print("─" * 50)
            
            # Grade the response
            print(f"\n📊 Grading response...")
            grading_result = grader.grade_response(
                user_query=query,
                memory_context=memory_context,
                llm_response=llm_response,
                expected_topics=expected_topics
            )
            
            # Display grading results
            overall_score = grading_result.get('overall_score', 0)
            overall_grade = grading_result.get('overall_grade', 'F')
            context_usage_score = grading_result.get('context_usage', {}).get('score', 0)
            
            print(f"\n🎯 GRADING RESULTS:")
            print(f"   Overall Score: {overall_score:.1f}/10 (Grade: {overall_grade})")
            print(f"   Context Usage: {context_usage_score}/10")
            print(f"   Memory Results Used: {response_data.get('memory_result_count', 0)} triples")
            
            if 'key_strengths' in grading_result and grading_result['key_strengths']:
                print(f"   ✅ Strengths: {', '.join(grading_result['key_strengths'])}")
            if 'key_weaknesses' in grading_result and grading_result['key_weaknesses']:
                print(f"   ❌ Weaknesses: {', '.join(grading_result['key_weaknesses'])}")
            
            # Combine all data for this query
            query_result = {
                'query': query,
                'expected_topics': expected_topics,
                'response_data': response_data,
                'grading': grading_result,
                'scenario_name': scenario['name'],
                'session_id': session_id
            }
            
            scenario_results.append(query_result)
            all_results.append(query_result)
            
            total_score += overall_score
            query_count += 1
            
            logger.info(f"Query '{query}' completed - Score: {overall_score:.1f}/10")
        
        # Scenario summary
        avg_score = total_score / query_count if query_count > 0 else 0
        scenario_summary = {
            'scenario_name': scenario['name'],
            'query_count': query_count,
            'average_score': avg_score,
            'total_score': total_score,
            'session_id': scenario['session_id']
        }
        scenario_summaries.append(scenario_summary)
        
        print(f"\n📈 SCENARIO '{scenario['name']}' SUMMARY:")
        print(f"   Queries: {query_count}")
        print(f"   Average Score: {avg_score:.1f}/10")
        if avg_score >= 8.5: emoji = "🏆"
        elif avg_score >= 7.0: emoji = "👍"
        elif avg_score >= 5.5: emoji = "⚠️"
        else: emoji = "❌"
        print(f"   {emoji} Performance Level: {_get_performance_level(avg_score)}")
        
        logger.info(f"Scenario '{scenario['name']}' completed - Average score: {avg_score:.1f}/10")
    
    return all_results, scenario_summaries

def _get_performance_level(score: float) -> str:
    """Get performance level description from score."""
    if score >= 8.5: return "Excellent"
    elif score >= 7.0: return "Good" 
    elif score >= 5.5: return "Adequate"
    elif score >= 3.0: return "Poor"
    else: return "Failing"

def export_test_results(results: List[Dict], summaries: List[Dict], 
                       bootstrap_info: Dict, timestamp: str):
    """Export comprehensive test results."""
    logger = logging.getLogger('export')
    
    # Create comprehensive export data
    export_data = {
        'test_metadata': {
            'timestamp': timestamp,
            'test_type': 'ChatMemoryInterface Graded Conversation Test',
            'total_queries': len(results),
            'scenarios': len(summaries)
        },
        'bootstrap_info': bootstrap_info,
        'scenario_summaries': summaries,
        'detailed_results': results,
        'overall_stats': {
            'average_score': sum(r['grading']['overall_score'] for r in results) / len(results) if results else 0,
            'score_distribution': _calculate_score_distribution(results),
            'memory_usage_stats': _calculate_memory_usage_stats(results)
        }
    }
    
    # Export to JSON
    results_file = f"test-output/chat_memory_test_results_{timestamp}.json"
    try:
        os.makedirs(os.path.dirname(results_file), exist_ok=True)
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, default=str)
        logger.info(f"✅ Exported detailed results to {results_file}")
        print(f"📁 Detailed results saved to: {results_file}")
        return True
    except Exception as e:
        logger.error(f"❌ Export failed: {e}")
        return False

def _calculate_score_distribution(results: List[Dict]) -> Dict[str, int]:
    """Calculate distribution of grades."""
    distribution = {'A': 0, 'B': 0, 'C': 0, 'D': 0, 'F': 0}
    for result in results:
        grade = result['grading'].get('overall_grade', 'F')
        if grade in distribution:
            distribution[grade] += 1
    return distribution

def _calculate_memory_usage_stats(results: List[Dict]) -> Dict[str, Any]:
    """Calculate memory usage statistics."""
    memory_counts = [r['response_data'].get('memory_result_count', 0) for r in results]
    context_usage_scores = [r['grading'].get('context_usage', {}).get('score', 0) for r in results]
    
    return {
        'avg_memory_results_per_query': sum(memory_counts) / len(memory_counts) if memory_counts else 0,
        'avg_context_usage_score': sum(context_usage_scores) / len(context_usage_scores) if context_usage_scores else 0,
        'queries_with_memory': len([c for c in memory_counts if c > 0]),
        'queries_without_memory': len([c for c in memory_counts if c == 0])
    }

def cleanup_test_directory():
    """Clean up the test directory."""
    logger = logging.getLogger('cleanup')
    try:
        if os.path.exists(TEST_DIR):
            time.sleep(1)  # Allow connections to close
            shutil.rmtree(TEST_DIR)
            logger.info(f"✅ Cleaned up test directory: {TEST_DIR}")
    except Exception as e:
        logger.warning(f"⚠️ Could not fully clean up test directory: {e}")

def main():
    """Main test orchestration function."""
    global LOG_FILE
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    LOG_FILE = f"test-output/chat_memory_test_{timestamp}.log"
    setup_logging(debug_mode=True, log_file=LOG_FILE)
    logger = logging.getLogger('main')
    
    print("🚀 Starting ChatMemoryInterface Graded Test Suite")
    print("="*70)
    
    try:
        # Initialize system
        logger.info("Initializing test system...")
        print("📚 Initializing knowledge graph and memory systems...")
        kgraph = VectorKnowledgeGraph(path=TEST_DIR)
        memory = AssociativeSemanticMemory(kgraph)
        chat_interface = ChatMemoryInterface(memory)
        
        simulator = ConversationSimulator(chat_interface)
        grader = ConversationGrader()
        
        # Bootstrap with data
        print("\n🔄 Bootstrapping knowledge graph with Vocaloid & BlazBlue data...")
        bootstrap_info = bootstrap_knowledge_graph(memory)
        
        print(f"✅ Bootstrap complete:")
        print(f"   📄 URLs processed: {bootstrap_info['urls_processed']}")
        print(f"   📦 Total chunks: {bootstrap_info['total_chunks']}")
        print(f"   ⏱️  Total time: {bootstrap_info['total_time']:.1f}s")
        
        # Run conversation scenarios
        print(f"\n🎭 Running conversation scenarios...")
        results, summaries = run_conversation_scenarios(chat_interface, simulator, grader)
        
        # Final summary
        print(f"\n{'='*70}")
        print(f"🎯 FINAL TEST RESULTS SUMMARY")
        print(f"{'='*70}")
        
        overall_avg = sum(s['average_score'] for s in summaries) / len(summaries) if summaries else 0
        total_queries = sum(s['query_count'] for s in summaries)
        
        print(f"📊 Overall Statistics:")
        print(f"   Total Scenarios: {len(summaries)}")
        print(f"   Total Queries: {total_queries}")
        print(f"   Overall Average Score: {overall_avg:.1f}/10")
        print(f"   Performance Level: {_get_performance_level(overall_avg)}")
        
        print(f"\n📈 Scenario Breakdown:")
        for summary in summaries:
            emoji = "🏆" if summary['average_score'] >= 8.5 else "👍" if summary['average_score'] >= 7.0 else "⚠️"
            print(f"   {emoji} {summary['scenario_name']}: {summary['average_score']:.1f}/10")
        
        # Export results
        print(f"\n💾 Exporting results...")
        export_success = export_test_results(results, summaries, bootstrap_info, timestamp)
        
        if export_success:
            print(f"✅ Test completed successfully!")
        else:
            print(f"⚠️ Test completed with export issues")
        
        # Close connections
        memory.close()
        chat_interface.close()
        
    except Exception as e:
        logger.error(f"Test suite failed: {e}", exc_info=True)
        print(f"❌ Test suite failed: {e}")
    
    finally:
        print(f"\n🧹 Cleaning up...")
        cleanup_test_directory()
        print(f"📋 Test log saved to: {LOG_FILE}")
        print(f"✨ Test suite completed!")

if __name__ == "__main__":
    main()