import time
from typing import Dict, List, Tuple, Optional, Any
from VectorKnowledgeGraph import VectorKnowledgeGraph
from triple_extraction import extract_triples_from_string
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
        Process text by extracting triples directly from the original text.
        No intermediate summarization — triples are grounded in actual source text,
        which avoids hallucinated facts from small summarization models.

        Args:
            text: Input text to process
            source: Source identifier for the text
            timestamp: Optional timestamp for when the information was received
            speaker: Optional identifier for who generated this text
            episode_id: Optional episode identifier for episodic memory linking

        Returns:
            dict: Results including extracted triples (with embedded topics)
        """
        logging.info(f"Processing text from source: {source}")
        logging.debug(f"Text length: {len(text)} characters")

        # Detect if this is a conversation based on source or content
        is_conversation = (
            "conversation" in source.lower()
        )

        # Extract triples directly from original text (no summarization step)
        logging.debug("Extracting triples from original text")
        triples_extraction = extract_triples_from_string(
            text,
            source=source,
            timestamp=timestamp,
            speaker=speaker,
            is_conversation=is_conversation
        )
        logging.info(f"Extracted {len(triples_extraction.get('triples', []))} triples from text")

        # Prepare triples and metadata for storage
        all_triples: List[Tuple[str, str, str]] = []
        metadata_list: List[Dict] = []

        for triple_data in triples_extraction.get("triples", []):
            try:
                subject = triple_data["subject"]
                relationship = triple_data["verb"]
                obj = triple_data["object"]
                all_triples.append((subject, relationship, obj))

                triple_speaker = triple_data.get("speaker", triples_extraction.get("speaker", speaker))

                metadata = {
                    "source": source,
                    "timestamp": triples_extraction.get("timestamp"),
                    "is_from_summary": False,
                    "source_text": triple_data.get("source_text", ""),
                    "speaker": triple_speaker,
                    "topics": triple_data.get("topics", []),
                    "episode_id": episode_id
                }
                metadata_list.append(metadata)
            except Exception as e:
                logging.error(f"Error processing triple: {e}")
                logging.debug(f"Triple data: {triple_data}")
                continue

        # Add all triples to knowledge graph
        if all_triples:
            logging.debug(f"Adding {len(all_triples)} triples to knowledge graph")
            self.kgraph.add_triples(all_triples, metadata_list)
            logging.info(f"Successfully added {len(all_triples)} triples to knowledge graph")

        return {
            "triples": triples_extraction.get("triples", []),
        }

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

    # ============================================================================
    # GOAL MANAGEMENT SYSTEM
    # ============================================================================

    def create_goal(
        self,
        owner: str,
        description: str,
        priority: int = 3,
        parent_goal: Optional[str] = None,
        target_date: Optional[float] = None,
        source: str = "sophia_autonomous",
        episode_id: Optional[str] = None,
        topics: Optional[List[str]] = None,
        goal_type: str = "standard",
        is_forever_goal: bool = False,
        depends_on: Optional[List[str]] = None
    ) -> str:
        """
        Create a new goal in the knowledge graph.

        Args:
            owner: Who owns this goal (e.g., "Sophia", "Joey")
            description: Natural language description of the goal
            priority: Priority level (1=lowest, 5=highest)
            parent_goal: Description of parent goal if this is a subgoal
            target_date: Optional Unix timestamp for target completion
            source: Source of the goal ("sophia_autonomous", "user_suggested", etc.)
            episode_id: Optional episode ID if created during conversation
            topics: Optional list of topics for the goal
            goal_type: Type of goal ("standard", "instrumental", "derived")
            is_forever_goal: Whether this is an ongoing/instrumental goal (never completes)
            depends_on: Optional list of goal descriptions this goal depends on

        Returns:
            goal_id: Unique identifier for the goal (same as description for now)
        """
        logging.info(f"[GOAL] Creating goal for {owner}: '{description}' (type={goal_type}, forever={is_forever_goal})")

        current_time = time.time()

        # Build goal metadata
        goal_metadata = {
            "goal_status": "ongoing" if is_forever_goal else "pending",
            "priority": max(1, min(5, priority)),  # Clamp to 1-5
            "created_timestamp": current_time,
            "status_updated_timestamp": current_time,
            "completion_timestamp": None,
            "target_date": target_date,
            "source": source,
            "episode_id": episode_id,
            "blocker_reason": None,
            "completion_notes": None,
            "parent_goal_id": parent_goal,
            "goal_type": goal_type,
            "is_forever_goal": is_forever_goal,
            "topics": topics or ["goal", "planning"]
        }

        # Create the main goal triple
        goal_triple = (owner, "has_goal", description)
        self.kgraph.add_triples([goal_triple], [goal_metadata])

        # If there's a parent goal, create the subgoal relationship
        if parent_goal:
            subgoal_metadata = {
                "source": source,
                "timestamp": current_time,
                "topics": ["goal", "hierarchy"]
            }
            subgoal_triple = (description, "subgoal_of", parent_goal)
            self.kgraph.add_triples([subgoal_triple], [subgoal_metadata])
            logging.info(f"[GOAL] Linked '{description}' as subgoal of '{parent_goal}'")

        # Create dependency relationships
        if depends_on:
            dependency_triples = []
            dependency_metadata = []
            for dependency in depends_on:
                dep_triple = (description, "depends_on", dependency)
                dep_metadata = {
                    "source": source,
                    "timestamp": current_time,
                    "topics": ["goal", "dependency"]
                }
                dependency_triples.append(dep_triple)
                dependency_metadata.append(dep_metadata)

            if dependency_triples:
                self.kgraph.add_triples(dependency_triples, dependency_metadata)
                logging.info(f"[GOAL] Created {len(dependency_triples)} dependency relationships for '{description}'")

        # If this is a derived goal, link it to instrumental parent
        if goal_type == "derived" and parent_goal:
            derived_metadata = {
                "source": source,
                "timestamp": current_time,
                "topics": ["goal", "derived"]
            }
            derived_triple = (description, "derived_from", parent_goal)
            self.kgraph.add_triples([derived_triple], [derived_metadata])
            logging.info(f"[GOAL] Linked '{description}' as derived from '{parent_goal}'")

        logging.info(f"[GOAL] Created goal: '{description}' (priority={priority}, status={'ongoing' if is_forever_goal else 'pending'})")
        return description  # Use description as goal_id

    def update_goal(
        self,
        goal_description: str,
        status: Optional[str] = None,
        priority: Optional[int] = None,
        blocker_reason: Optional[str] = None,
        completion_notes: Optional[str] = None
    ) -> bool:
        """
        Update a goal's status or metadata with dependency checking.

        Args:
            goal_description: Description of the goal to update
            status: New status (pending, in_progress, completed, blocked, cancelled, ongoing)
            priority: New priority level (1-5)
            blocker_reason: Reason if status is blocked
            completion_notes: Notes when completing the goal

        Returns:
            True if successful, False if goal not found or blocked by dependencies
        """
        logging.info(f"[GOAL] Updating goal: '{goal_description}'")

        # Get current goal metadata first
        goal_result = self.kgraph.query_goal_by_description(goal_description, return_metadata=True)
        if not goal_result:
            logging.warning(f"[GOAL] Goal not found: '{goal_description}'")
            return False

        _, current_metadata = goal_result
        is_forever_goal = current_metadata.get('is_forever_goal', False)

        # Build update metadata
        updates = {}
        current_time = time.time()

        if status:
            # Prevent completing forever goals
            if is_forever_goal and status == "completed":
                logging.warning(f"[GOAL] Cannot complete forever goal: '{goal_description}'")
                updates['goal_status'] = "ongoing"
                updates['blocker_reason'] = "This is an instrumental/forever goal - it cannot be completed"
            else:
                # Check dependencies if trying to complete
                if status == "completed":
                    unmet_deps = self._check_unmet_dependencies(goal_description)
                    if unmet_deps:
                        logging.warning(f"[GOAL] Cannot complete goal due to unmet dependencies: {unmet_deps}")
                        updates['goal_status'] = "blocked"
                        updates['blocker_reason'] = f"Blocked by pending dependencies: {', '.join(unmet_deps)}"
                    else:
                        # Check for incomplete sub-goals
                        subgoals = self.get_subgoals(goal_description)
                        incomplete = [t[2] for t, m in subgoals
                                      if m.get('goal_status', 'pending') not in ('completed', 'cancelled')]
                        if incomplete:
                            logging.warning(f"[GOAL] Cannot complete goal -{len(incomplete)} incomplete sub-goals")
                            updates['goal_status'] = "blocked"
                            updates['blocker_reason'] = f"Has {len(incomplete)} incomplete sub-goal(s): {', '.join(incomplete[:3])}"
                    if updates.get('goal_status') != 'blocked':
                        updates['goal_status'] = status
                        updates['completion_timestamp'] = current_time
                else:
                    updates['goal_status'] = status
                    if status == "completed":
                        updates['completion_timestamp'] = current_time

            updates['status_updated_timestamp'] = current_time
            # When resetting to pending, clear stale progress data
            if updates.get('goal_status') == 'pending':
                updates['journal_entries'] = []
                updates['completion_notes'] = None
                updates['completion_timestamp'] = None
            logging.info(f"[GOAL] Setting status to: {updates.get('goal_status', status)}")

        if priority is not None:
            updates['priority'] = max(1, min(5, priority))

        if blocker_reason and 'blocker_reason' not in updates:  # Don't override dependency blocker
            updates['blocker_reason'] = blocker_reason

        if completion_notes:
            updates['completion_notes'] = completion_notes

        # Update using VectorKnowledgeGraph method
        success = self.kgraph.update_goal_metadata(goal_description, updates)

        if success:
            logging.info(f"[GOAL] Successfully updated goal: '{goal_description}'")
        else:
            logging.warning(f"[GOAL] Failed to update goal: '{goal_description}'")

        return success

    def _check_unmet_dependencies(self, goal_description: str) -> List[str]:
        """
        Check if a goal has any unmet dependencies.

        Args:
            goal_description: Description of the goal to check

        Returns:
            List of descriptions of unmet dependency goals
        """
        # Find all dependencies for this goal
        try:
            dependency_triples = self.kgraph.build_graph_from_subject_relationship(
                (goal_description, "depends_on"),
                similarity_threshold=0.9,
                max_results=50,
                return_metadata=True
            )

            unmet_dependencies = []
            for triple, _ in dependency_triples:
                dependency_desc = triple[2]  # The object is the dependency goal description

                # Check status of dependency
                dep_result = self.kgraph.query_goal_by_description(dependency_desc, return_metadata=True)
                if dep_result:
                    _, dep_metadata = dep_result
                    dep_status = dep_metadata.get('goal_status', 'pending')

                    # Dependency is only met if completed or cancelled
                    if dep_status not in ['completed', 'cancelled']:
                        unmet_dependencies.append(dependency_desc)
                        logging.debug(f"[GOAL] Unmet dependency: '{dependency_desc}' (status={dep_status})")

            return unmet_dependencies

        except Exception as e:
            logging.error(f"[GOAL] Error checking dependencies: {e}")
            return []

    def query_goals(
        self,
        status: Optional[str] = None,
        min_priority: int = 1,
        max_priority: int = 5,
        owner: Optional[str] = None,
        active_only: bool = False,
        limit: int = 100
    ) -> List[Tuple]:
        """
        Query goals with various filters.

        Args:
            status: Filter by specific status
            min_priority: Minimum priority level
            max_priority: Maximum priority level
            owner: Filter by goal owner
            active_only: Only return pending/in_progress goals
            limit: Maximum number of results

        Returns:
            List of (triple, metadata) tuples for matching goals
        """
        logging.info(f"[GOAL] Querying goals (status={status}, active_only={active_only})")

        if active_only:
            results = self.kgraph.query_active_goals(limit=limit, return_metadata=True)
        elif status:
            results = self.kgraph.query_goals_by_status(status, limit=limit, return_metadata=True)
        else:
            # Query by priority range
            results = self.kgraph.query_goals_by_priority(
                min_priority=min_priority,
                max_priority=max_priority,
                limit=limit,
                return_metadata=True
            )

        # Filter by owner if specified
        if owner and results:
            results = [(t, m) for t, m in results if t[0].lower() == owner.lower()]

        # Filter to only has_goal predicates
        results = [(t, m) for t, m in results if t[1] == "has_goal"]

        logging.info(f"[GOAL] Found {len(results)} matching goals")
        return results

    def get_subgoals(self, parent_description: str, owner: str = None) -> List[Tuple]:
        """
        Get all sub-goals of a given parent goal.

        Args:
            parent_description: Description of the parent goal
            owner: Optional owner filter

        Returns:
            List of (triple, metadata) tuples for sub-goals
        """
        all_goals = self.query_goals(owner=owner, limit=100)
        return [(t, m) for t, m in all_goals
                if m.get("parent_goal_id") == parent_description]

    def get_goal_progress(self, owner: Optional[str] = None) -> Dict[str, Any]:
        """
        Get statistics on goal completion and progress.

        Args:
            owner: Optional owner to filter by

        Returns:
            Dictionary with goal statistics
        """
        logging.info(f"[GOAL] Calculating goal progress for owner: {owner or 'all'}")

        # Query all goals
        all_goals = self.query_goals(owner=owner, min_priority=1, max_priority=5, limit=1000)

        stats = {
            "total_goals": len(all_goals),
            "by_status": {
                "pending": 0,
                "in_progress": 0,
                "completed": 0,
                "blocked": 0,
                "cancelled": 0
            },
            "by_priority": {
                1: 0,
                2: 0,
                3: 0,
                4: 0,
                5: 0
            },
            "completion_rate": 0.0,
            "active_count": 0,
            "recent_completions": []
        }

        for triple, metadata in all_goals:
            status = metadata.get('goal_status', 'pending')
            priority = metadata.get('priority', 3)

            stats['by_status'][status] = stats['by_status'].get(status, 0) + 1
            stats['by_priority'][priority] = stats['by_priority'].get(priority, 0) + 1

            if status in ["pending", "in_progress"]:
                stats['active_count'] += 1

            if status == "completed":
                completion_time = metadata.get('completion_timestamp')
                if completion_time:
                    stats['recent_completions'].append({
                        "description": triple[2],
                        "completed_at": completion_time
                    })

        # Calculate completion rate
        if stats['total_goals'] > 0:
            stats['completion_rate'] = stats['by_status']['completed'] / stats['total_goals']

        # Sort recent completions by time (most recent first)
        stats['recent_completions'].sort(key=lambda x: x['completed_at'], reverse=True)
        stats['recent_completions'] = stats['recent_completions'][:10]  # Keep top 10

        logging.info(f"[GOAL] Progress: {stats['by_status']['completed']}/{stats['total_goals']} completed ({stats['completion_rate']*100:.1f}%)")
        return stats

    def suggest_next_goal(self, owner: str = "Sophia") -> Optional[Dict[str, Any]]:
        """
        Suggest the next goal to work on based on priority, dependencies, goal type, and status.
        Derived goals from instrumental/forever goals are prioritized.

        Args:
            owner: Goal owner to suggest for

        Returns:
            Dictionary with suggested goal and reasoning, or None
        """
        logging.info(f"[GOAL] Suggesting next goal for {owner}")

        # Get in_progress goals first — these should be continued before starting new ones
        in_progress_goals = self.query_goals(owner=owner, status="in_progress", limit=100)
        # Then get pending goals
        pending_goals = self.query_goals(owner=owner, status="pending", limit=100)

        # Combine: in_progress first, then pending
        all_actionable = in_progress_goals + pending_goals

        if not all_actionable:
            logging.info("[GOAL] No pending or in-progress goals found")
            return None

        # Score each goal based on priority, dependencies, and type
        scored_goals = []

        for triple, metadata in all_actionable:
            goal_desc = triple[2]
            priority = metadata.get('priority', 3)
            target_date = metadata.get('target_date')
            goal_type = metadata.get('goal_type', 'standard')

            # Check if this goal has unmet dependencies
            unmet_deps = self._check_unmet_dependencies(goal_desc)
            if unmet_deps:
                # Skip goals with unmet dependencies
                logging.debug(f"[GOAL] Skipping '{goal_desc}' - unmet dependencies: {unmet_deps}")
                continue

            # Base score is priority
            score = priority * 10

            # Boost in-progress goals — continue what you've started
            if metadata.get('goal_status') == 'in_progress':
                score += 30

            # Boost derived goals (from instrumental parents)
            if goal_type == "derived":
                score += 20
                logging.debug(f"[GOAL] Boosting derived goal '{goal_desc}' (+20)")

            # Boost if target date is soon
            if target_date:
                days_until = (target_date - time.time()) / (24 * 3600)
                if days_until < 7:  # Less than a week away
                    score += 15
                elif days_until < 30:  # Less than a month away
                    score += 5

            # Penalize parent goals that have active sub-goals
            subgoals = self.get_subgoals(goal_desc, owner=owner)
            active_subgoals = [s for s in subgoals
                               if s[1].get('goal_status', 'pending') not in ('completed', 'cancelled')]
            if active_subgoals:
                score -= 50
                logging.debug(f"[GOAL] Penalizing parent '{goal_desc}' (-50, has {len(active_subgoals)} active sub-goals)")

            # Boost sub-goals of high-priority parents
            parent_id = metadata.get('parent_goal_id')
            if parent_id:
                parent_result = self.kgraph.query_goal_by_description(parent_id, return_metadata=True)
                if parent_result:
                    _, parent_meta = parent_result
                    parent_priority = parent_meta.get('priority', 3)
                    if parent_priority >= 4:
                        score += 15
                        logging.debug(f"[GOAL] Boosting sub-goal '{goal_desc}' (+15, parent priority {parent_priority})")

            scored_goals.append({
                "goal": goal_desc,
                "score": score,
                "priority": priority,
                "goal_type": goal_type,
                "metadata": metadata,
                "triple": triple
            })

        # Sort by score descending
        scored_goals.sort(key=lambda x: x['score'], reverse=True)

        if scored_goals:
            top_goal = scored_goals[0]

            # Build reasoning message
            reasoning_parts = [f"Priority {top_goal['priority']}/5"]
            if top_goal['goal_type'] == "derived":
                reasoning_parts.append("derived from instrumental goal")
            reasoning = ", ".join(reasoning_parts) + " - dependencies met"

            logging.info(f"[GOAL] Suggested goal: '{top_goal['goal']}' (score={top_goal['score']})")

            return {
                "goal_description": top_goal['goal'],
                "priority": top_goal['priority'],
                "score": top_goal['score'],
                "goal_type": top_goal['goal_type'],
                "reasoning": reasoning,
                "metadata": top_goal['metadata']
            }

        return None

    def get_active_goals_for_prompt(self, owner: str = "Sophia", limit: int = 10) -> str:
        """
        Get a formatted string of active goals suitable for including in the agent prompt.
        Returns instrumental/forever goals and high-priority active goals.

        Args:
            owner: Goal owner to get goals for
            limit: Maximum number of goals to return

        Returns:
            Formatted string of goals for prompt inclusion
        """
        logging.info(f"[GOAL] Getting active goals for prompt (owner={owner})")

        # Get instrumental/forever goals
        instrumental_goals = self.kgraph.query_instrumental_goals(limit=50, return_metadata=True)
        # Filter by owner and has_goal predicate
        instrumental_goals = [(t, m) for t, m in instrumental_goals if t[0].lower() == owner.lower() and t[1] == "has_goal"]

        # Get high-priority active goals (priority 4-5)
        high_priority_goals = self.kgraph.query_high_priority_goals(min_priority=4, limit=50, return_metadata=True)
        # Filter by owner and has_goal predicate
        high_priority_goals = [(t, m) for t, m in high_priority_goals if t[0].lower() == owner.lower() and t[1] == "has_goal"]

        # Combine and deduplicate
        all_goals = {}
        for triple, metadata in instrumental_goals:
            goal_desc = triple[2]
            all_goals[goal_desc] = {
                "description": goal_desc,
                "priority": metadata.get('priority', 3),
                "status": metadata.get('goal_status', 'pending'),
                "type": metadata.get('goal_type', 'standard'),
                "is_forever": metadata.get('is_forever_goal', False)
            }

        for triple, metadata in high_priority_goals:
            goal_desc = triple[2]
            if goal_desc not in all_goals:  # Don't duplicate
                all_goals[goal_desc] = {
                    "description": goal_desc,
                    "priority": metadata.get('priority', 3),
                    "status": metadata.get('goal_status', 'pending'),
                    "type": metadata.get('goal_type', 'standard'),
                    "is_forever": metadata.get('is_forever_goal', False)
                }

        # Sort by priority descending, then by type (instrumental first)
        sorted_goals = sorted(
            all_goals.values(),
            key=lambda g: (g['priority'], 1 if g['is_forever'] else 0),
            reverse=True
        )[:limit]

        if not sorted_goals:
            logging.info("[GOAL] No active goals found for prompt")
            return ""

        # Format goals as bullet list
        goal_lines = []
        for goal in sorted_goals:
            type_label = ""
            if goal['is_forever']:
                type_label = " [INSTRUMENTAL/ONGOING]"
            elif goal['type'] == "derived":
                type_label = " [DERIVED]"

            status_label = goal['status'].upper() if goal['status'] != "pending" else ""
            priority_stars = "★" * goal['priority']

            goal_lines.append(
                f"- [{priority_stars}] {goal['description']}{type_label} {f'({status_label})' if status_label else ''}".strip()
            )

        formatted_goals = "\n".join(goal_lines)
        logging.info(f"[GOAL] Returning {len(sorted_goals)} goals for prompt")
        return formatted_goals

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