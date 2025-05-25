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
                   speaker: Optional[str] = None) -> Dict:
        """
        Process text by generating summary and extracting triples.
        
        Args:
            text: Input text to process
            source: Source identifier for the text
            timestamp: Optional timestamp for when the information was received
            speaker: Optional identifier for who generated this text
            
        Returns:
            dict: Results including summary and triples
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
        original_triples = extract_triples_from_string(
            text, 
            source=source, 
            timestamp=timestamp, 
            speaker=speaker,
            is_conversation=is_conversation
        )
        logging.info(f"Extracted {len(original_triples.get('triples', []))} triples from original text")
        
        # Extract triples from summary
        logging.debug("Extracting triples from summary")
        summary_triples = extract_triples_from_string(
            summary, 
            source=f"{source}_summary", 
            timestamp=timestamp, 
            speaker=speaker,
            is_conversation=is_conversation
        )
        logging.info(f"Extracted {len(summary_triples.get('triples', []))} triples from summary")
        
        # Prepare triples and metadata for storage
        all_triples: List[Tuple[str, str, str]] = []
        metadata_list: List[Dict] = []
        
        # Process original triples
        logging.debug("Processing original triples")
        for triple_data in original_triples.get("triples", []):
            try:
                subject = triple_data["subject"]
                relationship = triple_data["verb"]
                obj = triple_data["object"]
                all_triples.append((subject, relationship, obj))
                
                # Get speaker from the triple if available, otherwise use the global speaker
                triple_speaker = triple_data.get("speaker", original_triples.get("speaker", speaker))
                
                metadata = {
                    "source": source,
                    "timestamp": original_triples["timestamp"],
                    "is_from_summary": False,
                    "subject_properties": {},  # Simplified: no longer using complex modifiers
                    "verb_properties": {},     # Simplified: no longer using complex modifiers
                    "object_properties": {},   # Simplified: no longer using complex modifiers
                    "source_text": triple_data.get("source_text", ""),
                    "speaker": triple_speaker  # Use the extracted speaker
                }
                metadata_list.append(metadata)
            except Exception as e:
                logging.error(f"Error processing triple: {e}")
                logging.debug(f"Triple data: {triple_data}")
                continue
        
        # Process summary triples
        logging.debug("Processing summary triples")
        for triple_data in summary_triples.get("triples", []):
            try:
                subject = triple_data["subject"]
                relationship = triple_data["verb"]
                obj = triple_data["object"]
                all_triples.append((subject, relationship, obj))
                
                # Get speaker from the triple if available, otherwise use the global speaker
                triple_speaker = triple_data.get("speaker", summary_triples.get("speaker", speaker))
                
                metadata = {
                    "source": f"{source}_summary",
                    "timestamp": summary_triples["timestamp"],
                    "is_from_summary": True,
                    "subject_properties": {},  # Simplified: no longer using complex modifiers
                    "verb_properties": {},     # Simplified: no longer using complex modifiers
                    "object_properties": {},   # Simplified: no longer using complex modifiers
                    "source_text": triple_data.get("source_text", ""),
                    "speaker": triple_speaker  # Use the extracted speaker
                }
                metadata_list.append(metadata)
            except Exception as e:
                logging.error(f"Error processing summary triple: {e}")
                logging.debug(f"Triple data: {triple_data}")
                continue
        
        # Add all triples to knowledge graph
        if all_triples:
            logging.debug(f"Adding {len(all_triples)} triples to knowledge graph")
            self.kgraph.add_triples(all_triples, metadata_list)
            logging.info(f"Successfully added {len(all_triples)} triples to knowledge graph")
        
        # Return results
        return {
            "summary": summary,
            "original_triples": original_triples,
            "summary_triples": summary_triples
        }

    def query_related_information(self, text: str, include_summary_triples: bool = True, 
                                 follow_references: bool = True) -> List:
        """
        Query the knowledge graph for information related to the input text.
        Searches for connections through both subject and object endpoints of the query triples.
        
        Args:
            text: Text to find related information for
            include_summary_triples: Whether to include triples from summaries
            follow_references: Whether to follow entity reference links
            
        Returns:
            list: Related triples and their metadata, ordered by vector similarity
        """
        logging.info(f"Querying related information for: {text}")
        logging.debug(f"Include summary triples: {include_summary_triples}")
        logging.debug(f"Follow references: {follow_references}")
        
        # Extract triples from query text
        logging.debug("Extracting triples from query text")
        query_result = extract_triples_from_string(text, is_query=True)
        query_triples = query_result["query_triples"]
        logging.info(f"Extracted {len(query_triples)} query triples")
        
        # Collect related information
        related_triples = []
        
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
                all_subjects = [subject] + subject_references
                all_objects = [obj] + object_references
                
                subject_results = []
                object_results = []
                
                # Search for all subjects
                for subj in all_subjects:
                    logging.debug(f"Searching for connections through subject: {subj}")
                    # Search for connections through subject endpoint
                    results = self.kgraph.build_graph_from_noun(
                        subj,
                        similarity_threshold=0.7,
                        return_metadata=True
                    )
                    subject_results.extend(results)
                    logging.info(f"Found {len(results)} connections through subject '{subj}'")
                
                # Search for all objects
                for obj_item in all_objects:
                    logging.debug(f"Searching for connections through object: {obj_item}")
                    # Search for connections through object endpoint
                    results = self.kgraph.build_graph_from_noun(
                        obj_item,
                        similarity_threshold=0.7,
                        return_metadata=True
                    )
                    object_results.extend(results)
                    logging.info(f"Found {len(results)} connections through object '{obj_item}'")
                
                # Combine results
                results = subject_results + object_results
                
                # Filter out summary triples if needed
                if not include_summary_triples:
                    results = [(t, m) for t, m in results if not m.get("is_from_summary", False)]
                    logging.debug("Filtered out summary triples")
                
                # Add query context
                for triple, metadata in results:
                    metadata["query_context"] = {
                        "original_query": text,
                        "query_subject": subject,
                        "query_object": obj,
                        "connected_through": "subject" if any(s.lower() in str(triple).lower() for s in all_subjects) else "object"
                    }
                    
                # Add to overall results
                related_triples.extend(results)
                
            except Exception as e:
                logging.error(f"Error processing query triple: {e}")
                logging.debug(f"Triple data: {triple_data}")
                continue
        
        # Remove duplicates while preserving order
        seen = set()
        unique_related_triples = []
        for t, m in related_triples:
            triple_str = str(t)
            if triple_str not in seen:
                seen.add(triple_str)
                unique_related_triples.append((t, m))
        
        logging.info(f"Found {len(unique_related_triples)} related triples")
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
        for s, r, o in direct_refs:
            if s.lower() == entity.lower() and r.lower() == "refers_to":
                references.append(o)
        
        # Find reverse references (X "is_referenced_by" entity)
        reverse_refs = self.kgraph.build_graph_from_subject_relationship(
            (entity, "is_referenced_by"),
            similarity_threshold=0.8,
            return_metadata=False
        )
        
        # Extract subjects from reverse references
        for s, r, o in reverse_refs:
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
            
            # Get properties
            subject_props = metadata.get('subject_properties', {})
            verb_props = metadata.get('verb_properties', {})
            object_props = metadata.get('object_properties', {})
            
            # Build a detailed description
            desc = f"{subject}"
            if subject_props:
                desc += f" ({', '.join(f'{k}: {v}' for k, v in subject_props.items())})"
            
            desc += f" {relationship}"
            if verb_props:
                desc += f" ({', '.join(f'{k}: {v}' for k, v in verb_props.items())})"
            
            desc += f" {obj}"
            if object_props:
                desc += f" ({', '.join(f'{k}: {v}' for k, v in object_props.items())})"
            
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
        return response.choices[0].message.content

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
    log_file = f"associative_memory_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
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
            logging.info("Properties:")
            logging.info(f"Subject properties: {metadata.get('subject_properties', {})}")
            logging.info(f"Verb properties: {metadata.get('verb_properties', {})}")
            logging.info(f"Object properties: {metadata.get('object_properties', {})}")
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
            logging.info("Properties:")
            logging.info(f"Subject properties: {metadata.get('subject_properties', {})}")
            logging.info(f"Verb properties: {metadata.get('verb_properties', {})}")
            logging.info(f"Object properties: {metadata.get('object_properties', {})}")
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
            logging.info("Properties:")
            logging.info(f"Subject properties: {metadata.get('subject_properties', {})}")
            logging.info(f"Verb properties: {metadata.get('verb_properties', {})}")
            logging.info(f"Object properties: {metadata.get('object_properties', {})}")
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