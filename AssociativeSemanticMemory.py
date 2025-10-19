import time
from typing import Dict, List, Tuple, Optional, Any
from VectorKnowledgeGraph import VectorKnowledgeGraph
from triple_extraction import extract_triples_from_string
from ContextSummarizers import ContextSummarizers
import os
import shutil
import atexit
from openai import OpenAI
import logging
from datetime import datetime
from utils import setup_logging

class AssociativeSemanticMemory:
    def __init__(self, kgraph: VectorKnowledgeGraph):
        """
        Initialize the associative semantic memory system.
        
        Args:
            kgraph: VectorKnowledgeGraph instance for storing triples
        """
        self.kgraph = kgraph
        self.summarizer = ContextSummarizers()  # No longer passing kgraph
        logging.debug("Initialized AssociativeSemanticMemory")

    def close(self):
        """Close the knowledge graph connection and release resources."""
        logging.debug("Closing AssociativeSemanticMemory")
        if hasattr(self, 'kgraph') and self.kgraph:
            try:
                # Close the Qdrant client if it exists
                if hasattr(self.kgraph, 'qdrant_client'):
                    self.kgraph.qdrant_client.close()
                    logging.debug("Closed Qdrant client")
            except Exception as e:
                logging.error(f"Could not close Qdrant client: {e}")

    def ingest_text(self, text: str, source: str = "unknown", timestamp: Optional[float] = None,
                   speaker: Optional[str] = None, episode_id: Optional[str] = None) -> Dict:
        """
        Process text by generating summary and extracting triples.
        Topics are now an integral part of each triple.

        Args:
            text: Input text to process
            source: Source identifier for the text
            timestamp: Optional timestamp for when the information was received
            speaker: Optional identifier for who generated this text
            episode_id: Optional episode identifier for episodic memory linking

        Returns:
            dict: Results including summary and triples (with embedded topics)
        """
        logging.info(f"Processing text from source: {source}")
        logging.debug(f"Text length: {len(text)} characters")
        
        # Detect if this is a conversation based on source or content
        is_conversation = (
            "conversation" in source.lower()
        )
        
        # Generate summary
        logging.debug("Generating summary")
        summary = self.summarizer.generate_summary(text)
        logging.debug(f"Generated summary of length: {len(summary)} characters")
        
        # Extract triples from original text
        logging.debug("Extracting triples from original text")
        original_triples_extraction = extract_triples_from_string( # Renamed variable
            text, 
            source=source, 
            timestamp=timestamp, 
            speaker=speaker,
            is_conversation=is_conversation
            # No include_topics
        )
        logging.info(f"Extracted {len(original_triples_extraction.get('triples', []))} triples from original text")
        
        # Extract triples from summary
        logging.debug("Extracting triples from summary")
        summary_triples_extraction = extract_triples_from_string( # Renamed variable
            summary, 
            source=f"{source}_summary", 
            timestamp=timestamp, 
            speaker=speaker,
            is_conversation=is_conversation
            # No include_topics
        )
        logging.info(f"Extracted {len(summary_triples_extraction.get('triples', []))} triples from summary")
        
        # Prepare triples and metadata for storage
        all_triples: List[Tuple[str, str, str]] = []
        metadata_list: List[Dict] = []
        
        # Process original triples
        logging.debug("Processing original triples")
        for triple_data in original_triples_extraction.get("triples", []):
            try:
                subject = triple_data["subject"]
                relationship = triple_data["verb"]
                obj = triple_data["object"]
                all_triples.append((subject, relationship, obj))
                
                triple_speaker = triple_data.get("speaker", original_triples_extraction.get("speaker", speaker))
                
                metadata = {
                    "source": source,
                    "timestamp": original_triples_extraction.get("timestamp"), # Use timestamp from extraction result
                    "is_from_summary": False,
                    "source_text": triple_data.get("source_text", ""),
                    "speaker": triple_speaker,
                    "topics": triple_data.get("topics", []), # Get topics from the triple itself
                    "episode_id": episode_id
                }
                metadata_list.append(metadata)
            except Exception as e:
                logging.error(f"Error processing triple: {e}")
                logging.debug(f"Triple data: {triple_data}")
                continue
        
        # Process summary triples
        logging.debug("Processing summary triples")
        for triple_data in summary_triples_extraction.get("triples", []):
            try:
                subject = triple_data["subject"]
                relationship = triple_data["verb"]
                obj = triple_data["object"]
                all_triples.append((subject, relationship, obj))
                
                triple_speaker = triple_data.get("speaker", summary_triples_extraction.get("speaker", speaker))
                
                metadata = {
                    "source": f"{source}_summary",
                    "timestamp": summary_triples_extraction.get("timestamp"), # Use timestamp from extraction result
                    "is_from_summary": True,
                    "source_text": triple_data.get("source_text", ""),
                    "speaker": triple_speaker,
                    "topics": triple_data.get("topics", []), # Get topics from the triple itself
                    "episode_id": episode_id
                }
                metadata_list.append(metadata)
            except Exception as e:
                logging.error(f"Error processing summary triple: {e}")
                logging.debug(f"Triple data: {triple_data}")
                continue
        
        # Removed call to self._add_topic_triples as topics are now embedded
        
        # Add all triples to knowledge graph
        if all_triples:
            logging.debug(f"Adding {len(all_triples)} triples to knowledge graph")
            self.kgraph.add_triples(all_triples, metadata_list)
            logging.info(f"Successfully added {len(all_triples)} triples to knowledge graph")
        
        # Return results
        result = {
            "summary": summary,
            "original_triples": original_triples_extraction.get("triples", []), # Return the list of triples
            "summary_triples": summary_triples_extraction.get("triples", [])  # Return the list of triples
        }
        # Removed separate 'topics' key from result
        return result

    def _extract_candidate_topics(self, text: str, max_topics: int = 5) -> List[str]:
        """Very lightweight topic extraction: keep meaningful non-stopwords longer than 3 chars."""
        stopwords = {
            'the', 'and', 'for', 'with', 'that', 'this', 'about', 'what', 'where', 'when',
            'how', 'why', 'who', 'are', 'is', 'was', 'were', 'does', 'did', 'do',
        }
        tokens = [t.strip(".,!?()'\" ").lower() for t in text.split()]
        candidates = [t for t in tokens if len(t) > 3 and t not in stopwords]
        return list(dict.fromkeys(candidates))[:max_topics]

    def query_related_information(
        self,
        text: str,
        entity_name: Optional[str] = None,
        speaker: Optional[str] = None,
        limit: int = 20,  # Increased from 10
        min_confidence: Optional[float] = 0.5,  # Lowered from 0.6 to get more results
        include_summary_triples: bool = True,
        hop_depth: int = 1,  # Changed from 0 to enable graph traversal
        return_summary: bool = True,
        include_triples: bool = True
    ) -> Any:
        """
        Enhanced retrieval that blends vector similarity, topic similarity and optional hop expansion.
        Results are filtered and sorted by confidence.
        """
        logging.info(f"[ASM] Querying related information for: '{text}'")

        # ---------------- High-recall channels ----------------
        combined: Dict[Tuple[str, str, str], Dict] = {}
        subject_counts: Dict[str, int] = {}

        def _add_results(results, max_per_subject: int = 6):
            """Add results with optional subject diversification to prevent saturation."""
            for triple, meta in results:
                key = tuple(triple)
                conf = meta.get('confidence', 0.0)
                subject = triple[0]
                
                # Check if we've already hit the limit for this subject
                current_count = subject_counts.get(subject, 0)
                if current_count >= max_per_subject:
                    continue
                    
                # Add or update if higher confidence
                if key not in combined or conf > combined[key]['confidence']:
                    # If this is a new addition, increment subject count
                    if key not in combined:
                        subject_counts[subject] = current_count + 1
                    combined[key] = meta

        # 1. Full-text vector similarity
        try:
            vec_results = self.kgraph.find_triples_by_text_similarity(
                query_text=text,
                return_metadata=True,
                similarity_threshold=0.3,  # Raised from 0.2 to reduce false matches
                limit=max(50, limit*5)
            )
        except Exception as e:
            logging.error(f"Error during text similarity search: {e}")
            vec_results = []
        _add_results(vec_results)

        # 2. Topic vector similarity
        topics = self._extract_candidate_topics(text)
        if topics:
            try:
                topic_results = self.kgraph.find_triples_by_vectorized_topics(
                    query_topics=topics,
                    return_metadata=True,
                    similarity_threshold=0.3,  # Raised from 0.2 to reduce false matches
                    limit=max(50, limit*5)
                )
                # Give a small boost to mark topic-channel origin
                for _, meta in topic_results:
                    meta['confidence'] = meta.get('confidence', 0.0) * 1.05
            except Exception as e:
                logging.error(f"Error during topic similarity search: {e}")
                topic_results = []
            _add_results(topic_results)

        # ---------------- Predicate boost ----------------
        query_lc = text.lower()
        for triple_key, meta in combined.items():
            rel = (triple_key[1] or '').lower()
            if rel and rel in query_lc:
                meta['confidence'] = meta.get('confidence', 0.0) * 1.15

        # ---------------- Hop expansion ----------------
        if hop_depth and hop_depth > 0:
            # pick top 3 seeds above 0.65
            seeds = sorted(combined.items(), key=lambda kv: kv[1].get('confidence', 0.0), reverse=True)[:3]
            for (subj, rel, obj), meta in seeds:
                if meta.get('confidence', 0.0) < 0.65:
                    continue
                try:
                    hop_triples = self.kgraph.build_graph_from_subject_relationship(
                        (obj, rel), similarity_threshold=0.8, max_results=10, return_metadata=True
                    )
                    for hop_triple, hop_meta in hop_triples:
                        hop_meta = dict(hop_meta)
                        hop_meta['confidence'] = meta.get('confidence', 0.0) * 0.6  # decay
                        hop_meta['is_hop'] = True
                        _add_results([(hop_triple, hop_meta)])
                except Exception as e:
                    logging.debug(f"Hop expansion failed for {obj}: {e}")

        # ---------------- Combine & sort ----------------
        results_list = [(list(k), v) for k, v in combined.items()]

        # Filter summary triples if needed
        if not include_summary_triples:
            results_list = [r for r in results_list if not r[1].get('is_from_summary', False)]

        # Entity / speaker filters
        filtered = []
        for triple, meta in results_list:
            if entity_name:
                ent = meta.get('entity', '')
                if ent and ent != entity_name:
                    continue
            if speaker:
                spk = meta.get('speaker', '')
                if spk and spk != speaker:
                    continue
            filtered.append((tuple(triple), meta))

        # Sort by confidence descending
        filtered.sort(key=lambda x: x[1].get('confidence', 0.0), reverse=True)

        # Elastic cut-off - guarantee at least some results even if below threshold
        guarantee_k = max(3, min(limit // 2, 10))  # Guarantee 3-10 results depending on limit
        if min_confidence is not None and min_confidence >= 0:
            above = [r for r in filtered if r[1].get('confidence', 0.0) >= min_confidence]
            if len(above) >= guarantee_k:
                filtered = above
            # If we have very few above threshold, include some below to reach guarantee_k
            elif len(above) > 0:
                below = [r for r in filtered if r[1].get('confidence', 0.0) < min_confidence]
                filtered = above + below[:max(0, guarantee_k - len(above))]
        filtered = filtered[:limit] if limit else filtered

        logging.info(f"[ASM] Returning {len(filtered)} triples (limit={limit}) after blending & filtering")

        if not return_summary:
            # Preserve previous behaviour – just a list of triples
            return filtered

        # Build summary and structured result
        try:
            summary_text = self.summarize_results(text, filtered)
        except Exception as e:
            logging.error(f"Summary generation failed: {e}")
            summary_text = "Summary unavailable due to error."

        result_dict = {
            "summary": summary_text,
            "triple_count": len(filtered)
        }
        if include_triples:
            result_dict["triples"] = filtered

        return result_dict

    def _get_entity_references(self, entity: str) -> List[str]:
        """
        Get all entity references for a given entity.
        
        Args:
            entity: The entity to find references for
            
        Returns:
            List of referenced entities
        """
        references = []
        
        # Find direct references (entity "refers_to" X)
        direct_refs = self.kgraph.build_graph_from_subject_relationship(
            (entity, "refers_to"),
            similarity_threshold=0.8,
            return_metadata=False
        )
        
        # Extract objects from direct references
        for triple in direct_refs:
            if len(triple) >= 3:  # Ensure it's a valid triple
                s, r, o = triple
                if s.lower() == entity.lower() and r.lower() == "refers_to":
                    references.append(o)
        
        # Find reverse references (X "is_referenced_by" entity)
        reverse_refs = self.kgraph.build_graph_from_subject_relationship(
            (entity, "is_referenced_by"),
            similarity_threshold=0.8,
            return_metadata=False
        )
        
        # Extract subjects from reverse references
        for triple in reverse_refs:
            if len(triple) >= 3:  # Ensure it's a valid triple
                s, r, o = triple
                if o.lower() == entity.lower() and r.lower() == "is_referenced_by":
                    references.append(s)
        
        return list(set(references))  # Remove duplicates

    def summarize_results(self, input_text: str, results: List[Tuple]) -> str:
        """
        Summarize the retrieved information into a coherent paragraph, guided by the original input text.
        
        Args:
            input_text: The original text that prompted the search. Can be a question or a statement.
            results: List of (triple, metadata) tuples from query_related_information
            
        Returns:
            str: A natural language summary of the retrieved information
        """
        logging.info(f"Summarizing results for input: '{input_text}'")
        if not results:
            logging.warning("No results to summarize")
            return "No relevant information found."
            
        # Extract all unique information
        logging.debug("Extracting unique information from results")
        unique_info = set()
        for triple, metadata in results:
            # Get the triple components
            subject, relationship, obj = triple
            
            # Build a detailed description with confidence
            confidence = metadata.get('confidence', 0.0)
            desc = f"Fact: {subject} {relationship} {obj} (Confidence: {confidence:.2f})"
            
            unique_info.add(desc)
        
        logging.debug(f"Extracted {len(unique_info)} unique pieces of information")
        
        # Create a prompt for the LLM to format this into a paragraph
        prompt = f"""Synthesize a concise, relevant paragraph in response to the following input text, using only the provided facts.
The facts are sorted by relevance. Prioritize the most relevant ones to form a coherent response that directly addresses the input text.
If one fact clearly and directly answers the input text, **include that fact verbatim** in the response before adding any supporting context.

**Input Text:**
{input_text}

**Facts:**
{chr(10).join(unique_info)}

**Response:**"""
        
        # Call the LLM to format the information
        logging.debug("Calling LLM to generate summary")
        client = OpenAI(
            base_url=os.getenv('LLM_API_BASE'),
            api_key=os.getenv('LLM_API_KEY'),
        )
        
        summary_max_tokens = int(os.getenv('SUMMARY_MAX_TOKENS', '1024'))
        response = client.chat.completions.create(
            model=os.getenv('SUMMARIZATION_MODEL', 'gemma-3-4b-it-qat'),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=summary_max_tokens
        )
        
        logging.info("Successfully generated summary")
        content = response.choices[0].message.content
        return content if content is not None else "Unable to generate summary."

    def query_procedure(
        self,
        goal: str,
        include_alternatives: bool = True,
        include_examples: bool = True,
        include_dependencies: bool = True,
        limit: int = 20
    ) -> Dict:
        """
        Query for procedural knowledge to accomplish a goal.

        Args:
            goal: The task/goal to accomplish (e.g., "send POST request")
            include_alternatives: Whether to include alternative methods
            include_examples: Whether to include example_usage triples
            include_dependencies: Whether to follow requires/requires_prior chains
            limit: Maximum number of primary results

        Returns:
            Dict with procedures, alternatives, dependencies, and examples
        """
        logging.info(f"[ASM] Querying procedures for goal: '{goal}'")

        # Define procedural predicates with priority weights
        procedural_predicates = {
            "accomplished_by": 2.0,      # Highest priority - direct methods
            "is_method_for": 1.8,         # Methods for purposes
            "alternatively_by": 1.5,      # Alternatives
            "requires": 1.3,              # Dependencies
            "requires_prior": 1.3,        # Sequencing
            "enables": 1.2,               # Capabilities
            "example_usage": 1.5,         # Examples
            "has_step": 1.4,              # Procedural steps
            "followed_by": 1.2            # Sequential steps
        }

        # Step 1: Search for procedures related to the goal
        combined: Dict[Tuple[str, str, str], Dict] = {}

        # Vector similarity search
        try:
            vec_results = self.kgraph.find_triples_by_text_similarity(
                query_text=goal,
                return_metadata=True,
                similarity_threshold=0.3,
                limit=max(50, limit * 3)
            )
        except Exception as e:
            logging.error(f"Error during text similarity search: {e}")
            vec_results = []

        # Filter for procedural triples and boost by predicate
        for triple, meta in vec_results:
            key = tuple(triple)
            verb = (triple[1] or '').lower()

            # Check if it's a procedural triple
            topics = meta.get('topics', [])
            is_procedural = "procedure" in topics or verb in procedural_predicates

            if is_procedural:
                # Apply predicate boost
                boost = procedural_predicates.get(verb, 1.0)
                meta['confidence'] = meta.get('confidence', 0.0) * boost
                meta['is_procedural'] = True
                combined[key] = meta

        # Step 2: Topic-based search for procedural topics
        topics = ["procedure", "method", "how-to", "usage", "implementation"]
        topics.extend(self._extract_candidate_topics(goal, max_topics=3))

        try:
            topic_results = self.kgraph.find_triples_by_vectorized_topics(
                query_topics=topics,
                return_metadata=True,
                similarity_threshold=0.3,
                limit=max(50, limit * 3)
            )

            for triple, meta in topic_results:
                key = tuple(triple)
                verb = (triple[1] or '').lower()

                # Filter for procedural
                topic_list = meta.get('topics', [])
                if "procedure" in topic_list or verb in procedural_predicates:
                    boost = procedural_predicates.get(verb, 1.0)
                    meta['confidence'] = meta.get('confidence', 0.0) * boost * 1.05
                    meta['is_procedural'] = True

                    if key not in combined or meta['confidence'] > combined[key].get('confidence', 0):
                        combined[key] = meta

        except Exception as e:
            logging.error(f"Error during topic similarity search: {e}")

        # Step 3: Organize by predicate type
        methods = []
        alternatives = []
        dependencies = []
        examples = []
        steps = []

        for triple_key, meta in combined.items():
            verb = triple_key[1].lower() if triple_key[1] else ""
            triple_with_meta = (list(triple_key), meta)

            if verb == "accomplished_by" or verb == "is_method_for":
                methods.append(triple_with_meta)
            elif verb == "alternatively_by":
                alternatives.append(triple_with_meta)
            elif verb in ["requires", "requires_prior"]:
                dependencies.append(triple_with_meta)
            elif verb == "example_usage":
                examples.append(triple_with_meta)
            elif verb in ["has_step", "followed_by"]:
                steps.append(triple_with_meta)
            else:
                methods.append(triple_with_meta)  # Default to methods

        # Sort each category by confidence
        methods.sort(key=lambda x: x[1].get('confidence', 0.0), reverse=True)
        alternatives.sort(key=lambda x: x[1].get('confidence', 0.0), reverse=True)
        dependencies.sort(key=lambda x: x[1].get('confidence', 0.0), reverse=True)
        examples.sort(key=lambda x: x[1].get('confidence', 0.0), reverse=True)
        steps.sort(key=lambda x: x[1].get('confidence', 0.0), reverse=True)

        # Step 4: Follow dependency chains if requested
        if include_dependencies and (methods or alternatives):
            # For top methods, find their dependencies
            for method_triple, _ in methods[:3]:  # Top 3 methods
                method_obj = method_triple[2]  # The method itself

                try:
                    # Find what this method requires
                    dep_results = self.kgraph.build_graph_from_subject_relationship(
                        (method_obj, "requires"),
                        similarity_threshold=0.7,
                        max_results=10,
                        return_metadata=True
                    )

                    for dep_triple, dep_meta in dep_results:
                        dep_key = tuple(dep_triple)
                        if dep_key not in combined:
                            dep_meta['confidence'] = dep_meta.get('confidence', 0.0) * 0.8
                            dependencies.append((list(dep_triple), dep_meta))

                except Exception as e:
                    logging.debug(f"Dependency search failed for {method_obj}: {e}")

        # Step 5: Build structured result
        result = {
            "goal": goal,
            "methods": methods[:limit] if methods else [],
            "alternatives": alternatives[:limit] if include_alternatives and alternatives else [],
            "dependencies": dependencies[:limit] if include_dependencies and dependencies else [],
            "examples": examples[:limit] if include_examples and examples else [],
            "steps": steps[:limit] if steps else [],
            "total_found": len(methods) + len(alternatives) + len(dependencies) + len(examples) + len(steps)
        }

        logging.info(f"[ASM] Found procedures: {len(methods)} methods, {len(alternatives)} alternatives, "
                    f"{len(dependencies)} dependencies, {len(examples)} examples")

        return result

    def query_recent_memories(self, hours: float = 24, limit: int = 100) -> List[Tuple]:
        """
        Query memories from the last N hours with full metadata.

        Args:
            hours: Number of hours to look back
            limit: Maximum number of results

        Returns:
            List of (triple, metadata) tuples from the time range
        """
        logging.info(f"[ASM] Querying memories from last {hours} hours")
        results = self.kgraph.query_recent(hours=hours, limit=limit, return_metadata=True)
        logging.info(f"[ASM] Found {len(results)} recent memories")
        return results

    def query_memories_by_time_range(self, start_time: float, end_time: float, limit: int = 100) -> List[Tuple]:
        """
        Query memories within a specific time range.

        Args:
            start_time: Unix timestamp for range start
            end_time: Unix timestamp for range end
            limit: Maximum number of results

        Returns:
            List of (triple, metadata) tuples from the time range
        """
        logging.info(f"[ASM] Querying memories between {datetime.fromtimestamp(start_time)} and {datetime.fromtimestamp(end_time)}")
        results = self.kgraph.query_by_time_range(start_time=start_time, end_time=end_time, limit=limit, return_metadata=True)
        logging.info(f"[ASM] Found {len(results)} memories in time range")
        return results

    def query_episodic_context(self, episode_id: str, limit: int = 1000) -> Dict[str, Any]:
        """
        Retrieve all semantic memories linked to a specific episode.

        Args:
            episode_id: The episode identifier
            limit: Maximum number of triples to retrieve

        Returns:
            Dict with episode_id, triples, and summary
        """
        logging.info(f"[ASM] Retrieving episodic context for episode: {episode_id}")
        results = self.kgraph.query_by_episode(episode_id=episode_id, limit=limit, return_metadata=True)

        result_dict = {
            "episode_id": episode_id,
            "triple_count": len(results),
            "triples": results
        }

        logging.info(f"[ASM] Found {len(results)} triples for episode {episode_id}")
        return result_dict

    def get_explorer(self):
        """Return a MemoryExplorer bound to the current knowledge graph."""
        from MemoryExplorer import MemoryExplorer  # local import to avoid circular dependency
        return MemoryExplorer(self.kgraph)

def cleanup_test_directory():
    """Clean up the test directory, ensuring all resources are released first."""
    try:
        # Remove the test directory
        if os.path.exists("Test_AssociativeMemory"):
            # First try to remove the SQLite file directly
            sqlite_path = os.path.join("Test_AssociativeMemory", "qdrant_data", "collection", "knowledge_graph", "storage.sqlite")
            if os.path.exists(sqlite_path):
                try:
                    # Wait a moment to ensure all connections are closed
                    time.sleep(1)
                    os.remove(sqlite_path)
                except PermissionError:
                    print("Warning: Could not remove SQLite file, it may be in use")
                except Exception as e:
                    print(f"Warning: Error removing SQLite file: {e}")
            
            # Then try to remove the directory
            try:
                # Wait a moment to ensure all connections are closed
                time.sleep(1)
                shutil.rmtree("Test_AssociativeMemory")
            except PermissionError:
                print("Warning: Could not remove test directory, some files may be in use")
            except Exception as e:
                print(f"Warning: Error removing test directory: {e}")
    except Exception as e:
        print(f"Warning: Could not clean up test directory: {e}")

if __name__ == "__main__":
    # Set up debug logging for testing
    log_file = f"test-output/associative_memory_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    setup_logging(debug_mode=True, log_file=log_file)
    logging.info("Starting AssociativeSemanticMemory test run")
    
    # Test the associative semantic memory
    logging.info("Testing AssociativeSemanticMemory...")
    
    # Create a test knowledge graph
    kgraph = VectorKnowledgeGraph(path="Test_AssociativeMemory")
    
    # Register cleanup function
    atexit.register(cleanup_test_directory)
    
    try:
        # Initialize memory system
        memory = AssociativeSemanticMemory(kgraph)
        
        # Test text
        test_text = """
        Hatsune Miku (初音ミク), codenamed CV01, was the first Japanese VOCALOID to be both developed and distributed by Crypton Future 
        Media, Inc.. She was initially released in August 2007 for the VOCALOID2 engine and was the first member of the Character Vocal 
        Series. She was the seventh VOCALOID overall, as well as the second VOCALOID2 vocal released to be released for the engine. Her 
        voice is provided by the Japanese voice actress Saki Fujita (藤田咲, Fujita Saki)
        """
        
        # Process text through memory system
        logging.info("Processing test text...")
        result = memory.ingest_text(test_text, source="VOCALOID Wiki")
        
        # Print summary
        logging.info("Generated Summary:")
        logging.info(result["summary"])
        
        # Test natural language queries
        logging.info("Testing natural language queries...")
        
        # Test 1: Simple statement
        logging.info("Query 1: 'I like Hatsune Miku'")
        related = memory.query_related_information("I like Hatsune Miku")
        logging.info("Related information:")
        for triple, metadata in related:
            logging.info(f"Triple: {triple}")
            logging.info(f"Source: {metadata['source']}")
            logging.info(f"From summary: {metadata['is_from_summary']}")
            if 'query_context' in metadata:
                logging.info(f"Query context: {metadata['query_context']}")
            logging.info("---")
        
        # Print summary of results
        logging.info("Summary of retrieved information:")
        logging.info(memory.summarize_results("I like Hatsune Miku", related))
        
        # Test 2: Question format
        logging.info("Query 2: 'Tell me about Miku's voice'")
        related = memory.query_related_information("Tell me about Miku's voice")
        logging.info("Related information:")
        for triple, metadata in related:
            logging.info(f"Triple: {triple}")
            logging.info(f"Source: {metadata['source']}")
            logging.info(f"From summary: {metadata['is_from_summary']}")
            if 'query_context' in metadata:
                logging.info(f"Query context: {metadata['query_context']}")
            logging.info("---")
        
        # Print summary of results
        logging.info("Summary of retrieved information:")
        logging.info(memory.summarize_results("Tell me about Miku's voice", related))
        
        # Test 3: Excluding summary triples
        logging.info("Query 3: 'Who developed Miku?' (excluding summary triples)")
        related_no_summary = memory.query_related_information("Who developed Miku?", include_summary_triples=False)
        logging.info("Related information (original only):")
        for triple, metadata in related_no_summary:
            logging.info(f"Triple: {triple}")
            logging.info(f"Source: {metadata['source']}")
            if 'query_context' in metadata:
                logging.info(f"Query context: {metadata['query_context']}")
            logging.info("---")
        
        # Print summary of results
        logging.info("Summary of retrieved information:")
        logging.info(memory.summarize_results("Who developed Miku?", related_no_summary))
    
    finally:
        # Close the memory system and knowledge graph connection
        if 'memory' in locals():
            try:
                memory.close()
            except Exception as e:
                logging.error(f"Error closing memory system: {e}")
        # Ensure cleanup happens
        cleanup_test_directory()
        logging.info("Test run completed")