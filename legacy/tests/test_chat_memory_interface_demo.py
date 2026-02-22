#!/usr/bin/env python3
"""
Demo version of ChatMemoryInterface graded test with fast bootstrap.
Uses pre-defined test data instead of full document processing for speed.
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

from AssociativeSemanticMemory import AssociativeSemanticMemory
from VectorKnowledgeGraph import VectorKnowledgeGraph
from ChatMemoryInterface import ChatMemoryInterface
from utils import setup_logging

# Load environment variables
load_dotenv()

# Test directory for the knowledge graph
TEST_DIR = "test-output/Test_ChatMemoryInterface_Demo"

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
        """Grade how well the LLM response utilizes the provided memory context."""
        grading_prompt = f"""
Grade this AI response based on how well it uses provided memory context.

USER QUERY: {user_query}

MEMORY CONTEXT PROVIDED:
{memory_context}

AI RESPONSE:
{llm_response}

EXPECTED TOPICS: {', '.join(expected_topics)}

Grade 0-10 on these criteria:
1. CONTEXT_USAGE: How well did the AI use the provided memory?
2. ACCURACY: How accurate is the information?
3. COMPLETENESS: How completely does it address the query?
4. EXPECTED_COVERAGE: How well does it cover expected topics?

Return JSON with this structure:
{{
    "context_usage": {{"score": 0-10, "explanation": "brief explanation"}},
    "accuracy": {{"score": 0-10, "explanation": "brief explanation"}},
    "completeness": {{"score": 0-10, "explanation": "brief explanation"}},
    "expected_coverage": {{"score": 0-10, "explanation": "brief explanation"}},
    "overall_score": 0-10,
    "overall_grade": "A/B/C/D/F",
    "memory_context_used": true/false,
    "key_strengths": ["strength1"],
    "key_weaknesses": ["weakness1"]
}}
"""

        try:
            response = self.client.chat.completions.create(
                model=os.getenv('EXTRACTION_MODEL', 'gemma-3-4b-it-qat'),
                messages=[{"role": "user", "content": grading_prompt}],
                temperature=0.1,
                max_tokens=800
            )
            
            content = response.choices[0].message.content.strip()
            
            # Handle markdown code blocks
            if content.startswith('```json') and content.endswith('```'):
                content = content[7:-3].strip()
            elif content.startswith('```') and content.endswith('```'):
                content = content[3:-3].strip()
                
            grading_result = json.loads(content)
            
            # Calculate overall score if not provided
            if 'overall_score' not in grading_result:
                scores = [
                    grading_result.get('context_usage', {}).get('score', 0),
                    grading_result.get('accuracy', {}).get('score', 0),
                    grading_result.get('completeness', {}).get('score', 0),
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
                "context_usage": {"score": 0, "explanation": "Grading failed"}
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
    
    def simulate_response(self, user_query: str, session_id: str) -> Dict[str, Any]:
        """Simulate an LLM response using memory context."""
        # Get memory context
        memory_result = self.chat_interface.search_with_context(
            query=user_query,
            session_id=session_id,
            limit=8
        )
        
        memory_data = memory_result.get('results', {})
        memory_triples = memory_data.get('triples', [])
        memory_summary = memory_data.get('summary', '')
        
        # Format memory context for the LLM
        memory_context = self._format_memory_context(memory_triples, memory_summary)
        
        # Create the conversation with memory context framed for natural conversation
        system_prompt = """You are Sophia, an AI assistant with knowledge and memories from previous conversations and research. When relevant information comes to mind from your memory, naturally incorporate it into the conversation as you would recall things in a normal discussion. Don't explicitly mention "memory context" or "knowledge base" - just speak naturally as if you remember or know these things."""
        
        messages = [{"role": "system", "content": system_prompt}]
        
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
                max_tokens=400
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
            for i, (triple, metadata) in enumerate(triples[:6], 1):
                confidence = metadata.get('confidence', 0)
                subject, predicate, obj = triple
                context_parts.append(f"{i}. {subject} {predicate} {obj} (confidence: {confidence:.2f})")
        
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

def quick_bootstrap(memory: AssociativeSemanticMemory) -> Dict[str, Any]:
    """Quickly bootstrap with sample Vocaloid and BlazBlue data."""
    logger = logging.getLogger('bootstrap')
    logger.info("Quick bootstrapping with sample data...")
    
    # Sample triples for Vocaloid knowledge
    vocaloid_triples = [
        ("Vocaloid", "is", "voice synthesis software"),
        ("Vocaloid", "developed_by", "Yamaha Corporation"),
        ("Hatsune Miku", "is", "Vocaloid character"),
        ("Hatsune Miku", "has_code_name", "CV01"),
        ("Hatsune Miku", "voice_provided_by", "Saki Fujita"),
        ("Hatsune Miku", "has_hair_color", "turquoise"),
        ("Hatsune Miku", "released_in", "2007"),
        ("Kasane Teto", "is", "UTAU character"),
        ("Kasane Teto", "has_hair_style", "drill hair"),
        ("Kasane Teto", "created_as", "April Fools joke"),
        ("UTAU", "is", "freeware voice synthesis"),
        ("UTAU", "alternative_to", "Vocaloid")
    ]
    
    # Sample triples for BlazBlue knowledge  
    blazblue_triples = [
        ("BlazBlue", "is", "fighting game series"),
        ("BlazBlue", "developed_by", "Arc System Works"),
        ("Ragna the Bloodedge", "is", "BlazBlue protagonist"),
        ("Ragna the Bloodedge", "has", "Azure Grimoire"),
        ("Ragna the Bloodedge", "seeks", "revenge against brother"),
        ("BlazBlue: Centralfiction", "is", "fourth BlazBlue game"),
        ("BlazBlue: Centralfiction", "released_in", "2015"),
        ("Rachel Alucard", "is", "BlazBlue character"),
        ("Rachel Alucard", "is", "vampire noble"),
        ("Rachel Alucard", "has", "red eyes"),
        ("Rachel Alucard", "role_is", "observer"),
        ("Arc System Works", "specializes_in", "2D fighting games")
    ]
    
    # Add all triples to memory
    start_time = time.time()
    total_added = 0
    
    all_triples = vocaloid_triples + blazblue_triples
    
    try:
        # Create metadata for all triples
        metadata_list = []
        for _ in all_triples:
            metadata_list.append({
                'source': 'quick_bootstrap',
                'confidence': 0.9,
                'timestamp': time.time(),
                'topics': ['demo', 'sample_data']
            })
        
        # Add all triples at once using the correct method
        memory.kgraph.add_triples(all_triples, metadata_list)
        total_added = len(all_triples)
        logger.info(f"Successfully added {total_added} triples to knowledge graph")
        
    except Exception as e:
        logger.error(f"Failed to add triples: {e}")
    
    processing_time = time.time() - start_time
    
    result = {
        'method': 'quick_bootstrap',
        'total_triples_added': total_added,
        'processing_time': processing_time,
        'topics_covered': ['Vocaloid', 'UTAU', 'BlazBlue', 'fighting games']
    }
    
    logger.info(f"Quick bootstrap complete: {result}")
    return result

def run_demo_scenarios(chat_interface: ChatMemoryInterface, 
                      simulator: ConversationSimulator,
                      grader: ConversationGrader) -> Tuple[List[Dict], List[Dict]]:
    """Run simplified demo scenarios."""
    logger = logging.getLogger('scenarios')
    
    scenarios = [
        {
            "name": "Vocaloid Conversation",
            "session_id": "demo_vocaloid",
            "queries": [
                {
                    "query": "I've been hearing about this thing called Vocaloid lately. Do you know anything about it?",
                    "expected_topics": ["voice synthesis", "software", "Yamaha"]
                },
                {
                    "query": "That's interesting! I keep seeing this character with turquoise hair everywhere. I think her name is Hatsune Miku?",
                    "expected_topics": ["Hatsune Miku", "CV01", "Saki Fujita", "turquoise"]
                }
            ]
        },
        {
            "name": "BlazBlue Discussion",
            "session_id": "demo_blazblue", 
            "queries": [
                {
                    "query": "I'm getting into fighting games and someone mentioned this character called Ragna the Bloodedge. Have you heard of him?",
                    "expected_topics": ["Ragna", "protagonist", "Azure Grimoire", "revenge"]
                },
                {
                    "query": "Cool! What about BlazBlue: Centralfiction? Is that worth playing?",
                    "expected_topics": ["Centralfiction", "fourth", "fighting game", "2015"]
                }
            ]
        }
    ]
    
    all_results = []
    scenario_summaries = []
    
    for scenario in scenarios:
        print(f"\n{'='*50}")
        print(f"🎭 SCENARIO: {scenario['name']}")
        print(f"{'='*50}")
        
        scenario_results = []
        total_score = 0
        
        for query_data in scenario['queries']:
            query = query_data['query']
            expected_topics = query_data['expected_topics']
            session_id = scenario['session_id']
            
            print(f"\n🔍 Query: {query}")
            print(f"📝 Expected topics: {expected_topics}")
            
            # Simulate the response
            response_data = simulator.simulate_response(query, session_id)
            
            # Show memory context that was injected
            memory_context = response_data.get('memory_context_formatted', '')
            if memory_context:
                print(f"\n💭 MEMORY CONTEXT INJECTED:")
                print("─" * 40)
                print(memory_context)
                print("─" * 40)
            else:
                print(f"💭 No memory context found")
            
            # Show the LLM response
            llm_response = response_data.get('llm_response', '')
            print(f"\n🤖 LLM RESPONSE:")
            print("─" * 40)
            print(llm_response)
            print("─" * 40)
            
            # Grade the response
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
            print(f"   Memory Results: {response_data.get('memory_result_count', 0)} triples")
            
            if grading_result.get('key_strengths'):
                print(f"   ✅ Strengths: {', '.join(grading_result['key_strengths'])}")
            if grading_result.get('key_weaknesses'):
                print(f"   ❌ Weaknesses: {', '.join(grading_result['key_weaknesses'])}")
            
            # Store results
            query_result = {
                'query': query,
                'expected_topics': expected_topics,
                'response_data': response_data,
                'grading': grading_result,
                'scenario_name': scenario['name']
            }
            
            scenario_results.append(query_result)
            all_results.append(query_result)
            total_score += overall_score
        
        # Scenario summary
        avg_score = total_score / len(scenario['queries'])
        scenario_summary = {
            'scenario_name': scenario['name'],
            'query_count': len(scenario['queries']),
            'average_score': avg_score,
            'total_score': total_score
        }
        scenario_summaries.append(scenario_summary)
        
        print(f"\n📈 SCENARIO SUMMARY:")
        print(f"   Average Score: {avg_score:.1f}/10")
        emoji = "🏆" if avg_score >= 8 else "👍" if avg_score >= 6 else "⚠️"
        print(f"   {emoji} Performance: {'Excellent' if avg_score >= 8 else 'Good' if avg_score >= 6 else 'Needs Improvement'}")
    
    return all_results, scenario_summaries

def cleanup_test_directory():
    """Clean up the test directory."""
    try:
        if os.path.exists(TEST_DIR):
            time.sleep(1)
            shutil.rmtree(TEST_DIR)
            print(f"✅ Cleaned up: {TEST_DIR}")
    except Exception as e:
        print(f"⚠️ Cleanup warning: {e}")

def main():
    """Main demo function."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = f"test-output/chat_memory_demo_{timestamp}.log"
    setup_logging(debug_mode=True, log_file=log_file)
    logger = logging.getLogger('main')
    
    print("🚀 ChatMemoryInterface Demo Test")
    print("="*50)
    
    try:
        # Initialize system
        print("📚 Initializing system...")
        kgraph = VectorKnowledgeGraph(path=TEST_DIR)
        memory = AssociativeSemanticMemory(kgraph)
        chat_interface = ChatMemoryInterface(memory)
        
        simulator = ConversationSimulator(chat_interface)
        grader = ConversationGrader()
        
        # Quick bootstrap
        print("\n⚡ Quick bootstrap with sample data...")
        bootstrap_info = quick_bootstrap(memory)
        print(f"✅ Added {bootstrap_info['total_triples_added']} sample triples in {bootstrap_info['processing_time']:.2f}s")
        
        # Run demo scenarios
        print(f"\n🎭 Running conversation scenarios...")
        results, summaries = run_demo_scenarios(chat_interface, simulator, grader)
        
        # Final summary
        print(f"\n{'='*50}")
        print(f"🎯 FINAL DEMO RESULTS")
        print(f"{'='*50}")
        
        overall_avg = sum(s['average_score'] for s in summaries) / len(summaries) if summaries else 0
        total_queries = sum(s['query_count'] for s in summaries)
        
        print(f"📊 Overall Statistics:")
        print(f"   Total Scenarios: {len(summaries)}")
        print(f"   Total Queries: {total_queries}")
        print(f"   Overall Average Score: {overall_avg:.1f}/10")
        
        print(f"\n📈 By Scenario:")
        for summary in summaries:
            emoji = "🏆" if summary['average_score'] >= 8 else "👍" if summary['average_score'] >= 6 else "⚠️"
            print(f"   {emoji} {summary['scenario_name']}: {summary['average_score']:.1f}/10")
        
        # Close connections
        memory.close()
        chat_interface.close()
        
        print(f"\n✅ Demo completed successfully!")
        
    except Exception as e:
        logger.error(f"Demo failed: {e}", exc_info=True)
        print(f"❌ Demo failed: {e}")
    
    finally:
        print(f"\n🧹 Cleaning up...")
        cleanup_test_directory()
        print(f"📋 Demo log: {log_file}")

if __name__ == "__main__":
    main()