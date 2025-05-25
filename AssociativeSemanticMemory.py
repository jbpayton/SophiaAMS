import time
from typing import Dict, List, Tuple, Optional
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
                   speaker: Optional[str] = None) -> Dict: # Removed include_topics
        """
        Process text by generating summary and extracting triples.
        Topics are now an integral part of each triple.
        
        Args:
            text: Input text to process
            source: Source identifier for the text
            timestamp: Optional timestamp for when the information was received
            speaker: Optional identifier for who generated this text
            
        Returns:
            dict: Results including summary and triples (with embedded topics)
        """
        logging.info(f"Processing text from source: {source}")
        logging.debug(f"Text length: {len(text)} characters")
        
        # Detect if this is a conversation based on source or content
        is_conversation = (
            "conversation" in source.lower() or 
            "SPEAKER:" in text or
            speaker is not None
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
                    "topics": triple_data.get("topics", []) # Get topics from the triple itself
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
                    "topics": triple_data.get("topics", []) # Get topics from the triple itself
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

    def query_related_information(self, text: str, include_summary_triples: bool = True, 
                                 follow_references: bool = True) -> List: # Removed include_topics
        """
        Query the knowledge graph for information related to the input text.
        Topics are now integral to triples and queries.
        
        Args:
            text: Text to find related information for
            include_summary_triples: Whether to include triples from summaries
            follow_references: Whether to follow entity reference links
            
        Returns:
            list: Related triples and their metadata, ordered by a relevance score
        """
        logging.info(f"Querying related information for: {text}")
        logging.debug(f"Include summary triples: {include_summary_triples}")
        logging.debug(f"Follow references: {follow_references}")
        
        # Extract triples from query text
        logging.debug("Extracting triples from query text")
        # Call extract_triples_from_string without include_topics
        query_extraction_result = extract_triples_from_string(text, is_query=True)
        query_triples = query_extraction_result.get("query_triples", []) # get query_triples key
        
        # Derive query_topics from the 'topics' field within each query_triple
        query_topics_set = set()
        for qt in query_triples:
            if isinstance(qt, dict):
                topics_list = qt.get("topics")
                if isinstance(topics_list, list):
                    for topic_item in topics_list:
                        if isinstance(topic_item, str):
                            query_topics_set.add(topic_item)
                        # else: consider logging a warning for non-string topic items
                # else: consider logging a warning if 'topics' is not a list or is missing
            # else: consider logging a warning if a query triple item is not a dictionary
        query_topics = list(query_topics_set)
        
        logging.info(f"Extracted {len(query_triples)} query triples")
        logging.info(f"Derived {len(query_topics)} unique query topics from query triples")
        
        # Collect related information
        related_triples = [] # This will store (triple, metadata) tuples
        # topic_related_triples = [] # This will store (triple, metadata) tuples for topic-based matches

        # Search for connections through both subject and object endpoints of the query triples.
        for triple_data in query_triples:
            try:
                # Get query components
                subject = triple_data["subject"]
                obj = triple_data["object"]
                
                # Get references if requested
                subject_references = []
                object_references = []
                
                if follow_references:
                    # Find references for subjects
                    subject_references = self._get_entity_references(subject)
                    logging.debug(f"Found references for subject '{subject}': {subject_references}")
                    
                    # Find references for objects
                    object_references = self._get_entity_references(obj)
                    logging.debug(f"Found references for object '{obj}': {object_references}")
                
                # Combine original and references
                all_subjects = [subject] # + subject_references (if any)
                all_objects = [obj]     # + object_references (if any)
                if follow_references:
                    all_subjects.extend(subject_references)
                    all_objects.extend(object_references)
                
                current_results = []
                for s_item in all_subjects:
                    current_results.extend(self.kgraph.build_graph_from_noun(s_item, similarity_threshold=0.7, return_metadata=True))
                for o_item in all_objects:
                    current_results.extend(self.kgraph.build_graph_from_noun(o_item, similarity_threshold=0.7, return_metadata=True))

                if not include_summary_triples:
                    current_results = [(t, m) for t, m in current_results if not m.get("is_from_summary", False)]
                
                # Add query context
                for t, m in current_results:
                    m["query_context"] = {
                        "original_query": text,
                        "query_subject": subject,
                        "query_object": obj,
                        "query_triple_topics": triple_data.get("topics", []), # Add topics of the query triple
                        "connected_through": "subject" if any(s.lower() in str(t).lower() for s in all_subjects) else "object"
                    }
                related_triples.extend(current_results)
            except Exception as e:
                logging.error(f"Error processing query triple for direct search: {e}")
                continue
        
        # New: Perform vector-based search for query_topics
        topic_vector_search_results = []
        if query_topics:
            logging.debug(f"Performing vector-based topic search for topics: {query_topics}")
            try:
                # This is a placeholder for the new method in VectorKnowledgeGraph
                # It will take the list of query topics, embed them (or a concatenation), 
                # and search against stored topic vectors.
                topic_vector_search_results = self.kgraph.find_triples_by_vectorized_topics(
                    query_topics=query_topics,
                    return_metadata=True,
                    # We might need a similarity threshold here, e.g., similarity_threshold=0.7
                )
                logging.info(f"Found {len(topic_vector_search_results)} triples via vector-based topic search.")

                if not include_summary_triples:
                    topic_vector_search_results = [(t, m) for t, m in topic_vector_search_results
                                               if not m.get("is_from_summary", False)]
                
                # Add context that these were found via a vectorized topic search from the query
                for triple, metadata in topic_vector_search_results:
                    metadata["topic_query_context"] = {
                        "searched_query_topics": query_topics, # The topics used for the vector search
                        "search_type": "vectorized_topic_match" 
                    }
            except AttributeError as e:
                logging.error(f"VectorKnowledgeGraph does not yet have method 'find_triples_by_vectorized_topics': {e}")
            except Exception as e:
                logging.error(f"Error during vectorized topic search: {e}")
        
        all_results = related_triples + topic_vector_search_results
        
        seen = set() # Corrected indentation
        unique_related_triples = []
        for t, m in all_results:
            # Ensure t is converted to a hashable type, e.g., a tuple of strings
            try:
                hashable_t = tuple(map(str, t))
            except TypeError: # If t is not iterable or elements not convertible
                hashable_t = str(t)

            if hashable_t not in seen:
                seen.add(hashable_t)
                unique_related_triples.append((t, m))
        
        # Sort results by relevance
        def get_relevance_score(item):
            _, metadata = item
            score = 0.5  # Base score
            
            if "topic_query_context" in metadata: # Matched via a query topic
                score += 0.3 # Boost for topic match
            if "query_context" in metadata: # Matched via direct query triple S/O
                score += 0.2

            timestamp_val = metadata.get("timestamp", 0)
            if timestamp_val:
                age_days = (time.time() - timestamp_val) / (24 * 3600)
                score += max(0, 0.2 - (age_days * 0.01))
            
            return score
        
        unique_related_triples.sort(key=get_relevance_score, reverse=True)
        
        logging.info(f"Found {len(unique_related_triples)} unique related triples after merging and sorting.")
        return unique_related_triples
        
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

    def summarize_results(self, results: List[Tuple]) -> str:
        """
        Summarize the retrieved information into a coherent paragraph.
        
        Args:
            results: List of (triple, metadata) tuples from query_related_information
            
        Returns:
            str: A natural language summary of the retrieved information
        """
        logging.info("Summarizing results")
        if not results:
            logging.warning("No results to summarize")
            return "No relevant information found."
            
        # Extract all unique information
        logging.debug("Extracting unique information from results")
        unique_info = set()
        for triple, metadata in results:
            # Get the triple components
            subject = triple[0]
            relationship = triple[1]
            obj = triple[2]
            
            # Build a detailed description
            desc = f"{subject}"
            
            desc += f" {relationship}"
            
            desc += f" {obj}"
            
            unique_info.add(desc)
        
        logging.debug(f"Extracted {len(unique_info)} unique pieces of information")
        
        # Create a prompt for the LLM to format this into a paragraph
        prompt = f"""Please combine the following pieces of information into a coherent paragraph.
The information should flow naturally and maintain all the important details.

Information to combine:
{chr(10).join(unique_info)}

Please write a paragraph that incorporates all this information in a natural way:"""
        
        # Call the LLM to format the information
        logging.debug("Calling LLM to generate summary")
        client = OpenAI(
            base_url=os.getenv('LLM_API_BASE'),
            api_key=os.getenv('LLM_API_KEY'),
        )
        
        response = client.chat.completions.create(
            model=os.getenv('SUMMARIZATION_MODEL', 'gemma-3-4b-it-qat'),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        
        logging.info("Successfully generated summary")
        content = response.choices[0].message.content
        return content if content is not None else "Unable to generate summary."

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
        logging.info(memory.summarize_results(related))
        
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
        logging.info(memory.summarize_results(related))
        
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
        logging.info(memory.summarize_results(related_no_summary))
    
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