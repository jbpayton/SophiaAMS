"""
Chat-integrated memory interface that wraps existing AssociativeSemanticMemory
functionality with conversation-aware features and enhanced bookkeeping.
"""
import logging
import time
from typing import Dict, List, Tuple, Optional, Any, Union
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from AssociativeSemanticMemory import AssociativeSemanticMemory
from MemoryExplorer import MemoryExplorer
import json

@dataclass
class QuerySession:
    """Represents a conversation session for tracking memory queries."""
    session_id: str
    queries: List[Dict] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    
    def add_query(self, query: str, results_count: int, processing_time: float, 
                  context: Optional[str] = None):
        """Add a query to this session's history."""
        self.queries.append({
            'query': query,
            'timestamp': datetime.now(),
            'results_count': results_count,
            'processing_time': processing_time,
            'context': context
        })
        self.last_activity = datetime.now()

class ChatMemoryInterface:
    """
    Chat-integrated interface for AssociativeSemanticMemory that provides:
    - Session-aware querying with conversation context
    - Thread-following capabilities  
    - Enhanced bookkeeping and usage tracking
    - Self-awareness tools for knowledge inventory
    """
    
    def __init__(self, memory: AssociativeSemanticMemory):
        """
        Initialize with existing AssociativeSemanticMemory instance.
        
        Args:
            memory: Existing AssociativeSemanticMemory instance
        """
        self.memory = memory
        self.explorer = MemoryExplorer(memory.kgraph)
        self.sessions: Dict[str, QuerySession] = {}
        self.logger = logging.getLogger(__name__)
        
        self.logger.info("Initialized ChatMemoryInterface")
    
    def search_with_context(self, query: str, session_id: str, 
                           conversation_context: Optional[str] = None,
                           limit: int = 10, **kwargs) -> Dict[str, Any]:
        """
        Search memory with conversation session context.
        
        Args:
            query: Search query text
            session_id: Unique identifier for conversation session
            conversation_context: Recent conversation context for enhanced search
            limit: Maximum number of results to return
            **kwargs: Additional arguments passed to underlying query method
        
        Returns:
            Dict with search results, metadata, and session tracking info
        """
        start_time = time.time()
        
        # Get or create session
        if session_id not in self.sessions:
            self.sessions[session_id] = QuerySession(session_id)
        session = self.sessions[session_id]
        
        # Enhance query with conversation context if provided
        enhanced_query = query
        if conversation_context:
            enhanced_query = f"Context: {conversation_context[:200]}...\n\nQuery: {query}"
        
        try:
            # Use existing query method with session context
            results = self.memory.query_related_information(
                text=enhanced_query,
                limit=limit,
                return_summary=True,
                **kwargs
            )
            
            processing_time = time.time() - start_time
            results_count = len(results.get('triples', [])) if isinstance(results, dict) else len(results)
            
            # Track this query in session
            session.add_query(
                query=query,
                results_count=results_count,
                processing_time=processing_time,
                context=conversation_context
            )
            
            self.logger.info(f"Session {session_id}: Query processed in {processing_time:.2f}s, {results_count} results")
            
            # Return enhanced results with session metadata
            return {
                'results': results,
                'session_id': session_id,
                'processing_time': processing_time,
                'query_count_in_session': len(session.queries),
                'related_suggestions': self._suggest_related_queries(query, results)
            }
            
        except Exception as e:
            self.logger.error(f"Search failed for session {session_id}: {e}")
            return {
                'results': [],
                'error': str(e),
                'session_id': session_id,
                'processing_time': time.time() - start_time
            }
    
    def follow_thread(self, starting_triple: Union[Tuple, str], session_id: str, 
                     depth: int = 2, max_results: int = 20) -> Dict[str, Any]:
        """
        Follow a thread of related knowledge starting from a specific triple or entity.
        
        Args:
            starting_triple: Triple tuple or entity name to start from
            session_id: Session identifier for tracking
            depth: How many hops to explore
            max_results: Maximum total results to return
        
        Returns:
            Dict with threaded results and exploration path
        """
        start_time = time.time()
        
        try:
            if isinstance(starting_triple, str):
                # If string provided, search for triples containing this entity
                initial_results = self.memory.query_related_information(
                    text=starting_triple,
                    limit=5,
                    hop_depth=0  # Just direct matches first
                )
                
                if isinstance(initial_results, dict):
                    triples = initial_results.get('triples', [])
                else:
                    triples = initial_results
                
                if not triples:
                    return {
                        'thread_results': [],
                        'exploration_path': [],
                        'message': f"No triples found starting from: {starting_triple}"
                    }
                
                # Use first triple as starting point
                starting_triple = tuple(triples[0][0]) if triples else None
            
            if not starting_triple:
                return {'thread_results': [], 'error': 'Invalid starting point'}
            
            # Use memory's hop expansion with gradual depth increase
            thread_results = []
            exploration_path = [starting_triple]
            
            for current_depth in range(1, depth + 1):
                hop_results = self.memory.query_related_information(
                    text=' '.join(starting_triple),  # Convert triple to text query
                    limit=max_results // depth,
                    hop_depth=current_depth,
                    min_confidence=0.3  # Lower threshold for exploration
                )
                
                if isinstance(hop_results, dict):
                    new_triples = hop_results.get('triples', [])
                else:
                    new_triples = hop_results
                
                for triple, metadata in new_triples:
                    if metadata.get('is_hop') and tuple(triple) not in exploration_path:
                        thread_results.append((triple, metadata))
                        exploration_path.append(tuple(triple))
            
            processing_time = time.time() - start_time
            
            # Track in session
            if session_id in self.sessions:
                self.sessions[session_id].add_query(
                    query=f"thread_follow:{starting_triple}",
                    results_count=len(thread_results),
                    processing_time=processing_time,
                    context=f"depth={depth}"
                )
            
            return {
                'thread_results': thread_results,
                'exploration_path': exploration_path,
                'starting_point': starting_triple,
                'depth_explored': depth,
                'processing_time': processing_time
            }
            
        except Exception as e:
            self.logger.error(f"Thread following failed: {e}")
            return {
                'thread_results': [],
                'error': str(e),
                'processing_time': time.time() - start_time
            }
    
    def what_do_i_know_about(self, entity_or_topic: str, session_id: str, 
                            comprehensive: bool = False) -> Dict[str, Any]:
        """
        Generate a comprehensive knowledge summary about a specific entity or topic.
        
        Args:
            entity_or_topic: The subject to analyze
            session_id: Session identifier
            comprehensive: If True, includes deeper analysis and connections
        
        Returns:
            Dict with knowledge summary, related entities, and coverage analysis
        """
        start_time = time.time()
        
        try:
            # Get direct knowledge
            direct_results = self.memory.query_related_information(
                text=entity_or_topic,
                limit=50 if comprehensive else 20,
                return_summary=True,
                hop_depth=1 if comprehensive else 0
            )
            
            # Use MemoryExplorer for deeper analysis
            if comprehensive:
                try:
                    # Get clustering analysis
                    cluster_analysis = self.explorer.cluster_for_query(entity_or_topic)
                    
                    # Get centrality information  
                    entity_centrality = self.explorer.top_entities(limit=20)
                    entity_rank = None
                    for i, (entity, centrality) in enumerate(entity_centrality):
                        if entity.lower() == entity_or_topic.lower():
                            entity_rank = i + 1
                            break
                    
                except Exception as e:
                    self.logger.debug(f"Comprehensive analysis failed: {e}")
                    cluster_analysis = None
                    entity_rank = None
            else:
                cluster_analysis = None
                entity_rank = None
            
            processing_time = time.time() - start_time
            
            # Format results
            knowledge_summary = {
                'entity_or_topic': entity_or_topic,
                'direct_knowledge': direct_results,
                'entity_rank': entity_rank,
                'cluster_analysis': cluster_analysis,
                'knowledge_depth': 'comprehensive' if comprehensive else 'basic',
                'processing_time': processing_time
            }
            
            # Track in session
            if session_id in self.sessions:
                self.sessions[session_id].add_query(
                    query=f"what_do_i_know:{entity_or_topic}",
                    results_count=len(direct_results.get('triples', [])) if isinstance(direct_results, dict) else len(direct_results),
                    processing_time=processing_time,
                    context=f"comprehensive={comprehensive}"
                )
            
            return knowledge_summary
            
        except Exception as e:
            self.logger.error(f"Knowledge analysis failed for '{entity_or_topic}': {e}")
            return {
                'entity_or_topic': entity_or_topic,
                'error': str(e),
                'processing_time': time.time() - start_time
            }
    
    def recent_discoveries(self, session_id: str, timeframe: str = "1d") -> Dict[str, Any]:
        """
        Show recently added knowledge within a timeframe.
        
        Args:
            session_id: Session identifier
            timeframe: Time period (e.g., "1d", "1h", "1w")
        
        Returns:
            Dict with recent knowledge additions
        """
        # Parse timeframe
        timeframe_map = {
            "1h": timedelta(hours=1),
            "1d": timedelta(days=1), 
            "1w": timedelta(weeks=1),
            "1m": timedelta(days=30)
        }
        
        delta = timeframe_map.get(timeframe, timedelta(days=1))
        cutoff_time = datetime.now() - delta
        
        try:
            # Query for recent additions - this would need enhancement to the core system
            # For now, return session-specific recent queries
            if session_id in self.sessions:
                session = self.sessions[session_id]
                recent_queries = [
                    q for q in session.queries 
                    if q['timestamp'] >= cutoff_time
                ]
                
                return {
                    'timeframe': timeframe,
                    'recent_session_queries': recent_queries,
                    'query_count': len(recent_queries),
                    'note': 'Currently showing session queries. Full knowledge recency requires core system enhancement.'
                }
            
            return {
                'timeframe': timeframe,
                'message': f"No active session {session_id} found"
            }
            
        except Exception as e:
            self.logger.error(f"Recent discoveries query failed: {e}")
            return {'error': str(e)}
    
    def suggest_related(self, current_context: str, session_id: str, 
                       limit: int = 5) -> List[str]:
        """
        Suggest related queries or topics based on current conversation context.
        
        Args:
            current_context: Current conversation context
            session_id: Session identifier  
            limit: Maximum suggestions to return
        
        Returns:
            List of suggested follow-up questions or topics
        """
        try:
            # Get related knowledge
            related_results = self.memory.query_related_information(
                text=current_context,
                limit=limit * 2,
                hop_depth=1
            )
            
            suggestions = []
            if isinstance(related_results, dict):
                triples = related_results.get('triples', [])
            else:
                triples = related_results
            
            # Extract unique entities and relationships for suggestions
            entities = set()
            relationships = set()
            
            for triple, metadata in triples:
                entities.add(triple[0])  # subject
                entities.add(triple[2])  # object
                relationships.add(triple[1])  # relationship
            
            # Generate suggestions based on found entities
            for entity in list(entities)[:limit]:
                suggestions.append(f"Tell me more about {entity}")
            
            return suggestions
            
        except Exception as e:
            self.logger.error(f"Suggestion generation failed: {e}")
            return []
    
    def get_session_stats(self, session_id: str) -> Dict[str, Any]:
        """Get statistics and history for a conversation session."""
        if session_id not in self.sessions:
            return {'error': f'Session {session_id} not found'}
        
        session = self.sessions[session_id]
        return {
            'session_id': session_id,
            'created_at': session.created_at.isoformat(),
            'last_activity': session.last_activity.isoformat(),
            'total_queries': len(session.queries),
            'query_history': session.queries[-10:],  # Last 10 queries
            'avg_processing_time': sum(q['processing_time'] for q in session.queries) / len(session.queries) if session.queries else 0
        }
    
    def _suggest_related_queries(self, query: str, results: Any) -> List[str]:
        """Internal method to generate related query suggestions."""
        try:
            suggestions = []
            
            if isinstance(results, dict):
                triples = results.get('triples', [])
            else:
                triples = results if isinstance(results, list) else []
            
            # Extract entities from results for suggestions
            entities = set()
            for triple, metadata in triples[:5]:  # Top 5 results
                if len(entities) < 3:  # Limit suggestions
                    entities.add(triple[0])  # subject
                    entities.add(triple[2])  # object
            
            for entity in list(entities)[:3]:
                suggestions.append(f"What else do you know about {entity}?")
            
            return suggestions
            
        except Exception as e:
            self.logger.debug(f"Suggestion generation failed: {e}")
            return []
    
    def close(self):
        """Clean up resources."""
        self.logger.info("Closing ChatMemoryInterface")
        # Sessions will be garbage collected
        self.sessions.clear()