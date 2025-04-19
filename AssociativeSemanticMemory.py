import time
from typing import Dict, List, Tuple, Optional
from VectorKnowledgeGraph import VectorKnowledgeGraph
from triple_extraction import extract_triples_from_string
from ContextSummarizers import ContextSummarizers
import os
import shutil
import atexit
from openai import OpenAI

class AssociativeSemanticMemory:
    def __init__(self, kgraph: VectorKnowledgeGraph):
        """
        Initialize the associative semantic memory system.
        
        Args:
            kgraph: VectorKnowledgeGraph instance for storing triples
        """
        self.kgraph = kgraph
        self.summarizer = ContextSummarizers()  # No longer passing kgraph

    def close(self):
        """Close the knowledge graph connection and release resources."""
        if hasattr(self, 'kgraph') and self.kgraph:
            try:
                # Close the Qdrant client if it exists
                if hasattr(self.kgraph, 'qdrant_client'):
                    self.kgraph.qdrant_client.close()
            except Exception as e:
                print(f"Warning: Could not close Qdrant client: {e}")

    def ingest_text(self, text: str, source: str = "unknown", timestamp: Optional[float] = None) -> Dict:
        """
        Process text through the associative semantic memory system:
        1. Generate summary
        2. Extract triples from original text
        3. Extract triples from summary
        4. Store all triples in knowledge graph with metadata
        
        Args:
            text: Input text to process
            source: Source of the information
            timestamp: Optional timestamp for when the information was received
            
        Returns:
            dict: Results including summary and triples
        """
        # Generate summary
        summary = self.summarizer.generate_summary(text)
        
        # Extract triples from original text
        original_triples = extract_triples_from_string(text, source=source, timestamp=timestamp)
        
        # Extract triples from summary
        summary_triples = extract_triples_from_string(summary, source=f"{source}_summary", timestamp=timestamp)
        
        # Prepare triples and metadata for storage
        all_triples: List[Tuple[str, str, str]] = []
        metadata_list: List[Dict] = []
        
        # Process original triples
        for triple_data in original_triples.get("triples", []):
            try:
                subject = triple_data["subject"]["text"]
                relationship = triple_data["verb"]["text"]
                obj = triple_data["object"]["text"]
                all_triples.append((subject, relationship, obj))
                
                metadata = {
                    "source": source,
                    "timestamp": original_triples["timestamp"],
                    "is_from_summary": False,
                    "subject_properties": triple_data["subject"].get("properties", {}),
                    "verb_properties": triple_data["verb"].get("properties", {}),
                    "object_properties": triple_data["object"].get("properties", {}),
                    "source_text": triple_data.get("source_text", "")
                }
                metadata_list.append(metadata)
            except Exception as e:
                print(f"Error processing triple: {e}")
                print(f"Triple data: {triple_data}")
                continue
        
        # Process summary triples
        for triple_data in summary_triples.get("triples", []):
            try:
                subject = triple_data["subject"]["text"]
                relationship = triple_data["verb"]["text"]
                obj = triple_data["object"]["text"]
                all_triples.append((subject, relationship, obj))
                
                metadata = {
                    "source": f"{source}_summary",
                    "timestamp": summary_triples["timestamp"],
                    "is_from_summary": True,
                    "subject_properties": triple_data["subject"].get("properties", {}),
                    "verb_properties": triple_data["verb"].get("properties", {}),
                    "object_properties": triple_data["object"].get("properties", {}),
                    "source_text": triple_data.get("source_text", "")
                }
                metadata_list.append(metadata)
            except Exception as e:
                print(f"Error processing summary triple: {e}")
                print(f"Triple data: {triple_data}")
                continue
        
        # Add all triples to knowledge graph
        if all_triples:
            self.kgraph.add_triples(all_triples, metadata_list)
        
        # Return results
        return {
            "summary": summary,
            "original_triples": original_triples,
            "summary_triples": summary_triples
        }

    def query_related_information(self, text: str, include_summary_triples: bool = True) -> List:
        """
        Query the knowledge graph for information related to the input text.
        Searches for connections through both subject and object endpoints of the query triples.
        
        Args:
            text: Text to find related information for
            include_summary_triples: Whether to include triples from summaries
            
        Returns:
            list: Related triples and their metadata, ordered by vector similarity
        """
        # Extract triples from query text
        query_result = extract_triples_from_string(text, is_query=True)
        query_triples = query_result["query_triples"]
        
        # Collect related information
        related_triples = []
        
        for triple_data in query_triples:
            try:
                # Get query components
                subject = triple_data["subject"]["text"]
                obj = triple_data["object"]["text"]
                
                # Search for connections through subject endpoint
                subject_results = self.kgraph.build_graph_from_noun(
                    subject,
                    similarity_threshold=0.7,
                    return_metadata=True
                )
                
                # Search for connections through object endpoint
                object_results = self.kgraph.build_graph_from_noun(
                    obj,
                    similarity_threshold=0.7,
                    return_metadata=True
                )
                
                # Combine results
                results = subject_results + object_results
                
                # Filter out summary triples if needed
                if not include_summary_triples:
                    results = [(t, m) for t, m in results if not m.get("is_from_summary", False)]
                
                # Add query context
                for triple, metadata in results:
                    metadata["query_context"] = {
                        "original_query": text,
                        "query_subject": subject,
                        "query_object": obj,
                        "connected_through": "subject" if subject.lower() in str(triple).lower() else "object"
                    }
                    related_triples.append((triple, metadata))
            
            except Exception as e:
                print(f"Error processing query triple: {e}")
                print(f"Query triple data: {triple_data}")
                continue
        
        return related_triples

    def summarize_results(self, results: List[Tuple]) -> str:
        """
        Summarize the retrieved information into a coherent paragraph.
        
        Args:
            results: List of (triple, metadata) tuples from query_related_information
            
        Returns:
            str: A natural language summary of the retrieved information
        """
        if not results:
            return "No relevant information found."
            
        # Extract all unique information
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
        
        # Create a prompt for the LLM to format this into a paragraph
        prompt = f"""Please combine the following pieces of information into a coherent paragraph.
The information should flow naturally and maintain all the important details.

Information to combine:
{chr(10).join(unique_info)}

Please write a paragraph that incorporates all this information in a natural way:"""
        
        # Call the LLM to format the information
        client = OpenAI(
            base_url=os.getenv('LLM_API_BASE'),
            api_key=os.getenv('LLM_API_KEY'),
        )
        
        response = client.chat.completions.create(
            model=os.getenv('SUMMARIZATION_MODEL', 'gemma-3-4b-it-qat'),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        
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
    # Test the associative semantic memory
    print("Testing AssociativeSemanticMemory...")
    
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
        print("\nProcessing text...")
        result = memory.ingest_text(test_text, source="VOCALOID Wiki")
        
        # Print summary
        print("\nGenerated Summary:")
        print(result["summary"])
        
        # Test natural language queries
        print("\nTesting natural language queries...")
        
        # Test 1: Simple statement
        print("\nQuery 1: 'I like Hatsune Miku'")
        related = memory.query_related_information("I like Hatsune Miku")
        print("\nRelated information:")
        for triple, metadata in related:
            print(f"\nTriple: {triple}")
            print(f"Source: {metadata['source']}")
            print(f"From summary: {metadata['is_from_summary']}")
            print("\nProperties:")
            print(f"Subject properties: {metadata.get('subject_properties', {})}")
            print(f"Verb properties: {metadata.get('verb_properties', {})}")
            print(f"Object properties: {metadata.get('object_properties', {})}")
            if 'query_context' in metadata:
                print(f"\nQuery context: {metadata['query_context']}")
            print("---")
        
        # Print summary of results
        print("\nSummary of retrieved information:")
        print(memory.summarize_results(related))
        
        # Test 2: Question format
        print("\nQuery 2: 'Tell me about Miku's voice'")
        related = memory.query_related_information("Tell me about Miku's voice")
        print("\nRelated information:")
        for triple, metadata in related:
            print(f"\nTriple: {triple}")
            print(f"Source: {metadata['source']}")
            print(f"From summary: {metadata['is_from_summary']}")
            print("\nProperties:")
            print(f"Subject properties: {metadata.get('subject_properties', {})}")
            print(f"Verb properties: {metadata.get('verb_properties', {})}")
            print(f"Object properties: {metadata.get('object_properties', {})}")
            if 'query_context' in metadata:
                print(f"\nQuery context: {metadata['query_context']}")
            print("---")
        
        # Print summary of results
        print("\nSummary of retrieved information:")
        print(memory.summarize_results(related))
        
        # Test 3: Excluding summary triples
        print("\nQuery 3: 'Who developed Miku?' (excluding summary triples)")
        related_no_summary = memory.query_related_information("Who developed Miku?", include_summary_triples=False)
        print("\nRelated information (original only):")
        for triple, metadata in related_no_summary:
            print(f"\nTriple: {triple}")
            print(f"Source: {metadata['source']}")
            print("\nProperties:")
            print(f"Subject properties: {metadata.get('subject_properties', {})}")
            print(f"Verb properties: {metadata.get('verb_properties', {})}")
            print(f"Object properties: {metadata.get('object_properties', {})}")
            if 'query_context' in metadata:
                print(f"\nQuery context: {metadata['query_context']}")
            print("---")
        
        # Print summary of results
        print("\nSummary of retrieved information:")
        print(memory.summarize_results(related_no_summary))
    
    finally:
        # Close the memory system and knowledge graph connection
        if 'memory' in locals():
            try:
                memory.close()
            except Exception as e:
                print(f"Warning: Error closing memory system: {e}")
        # Ensure cleanup happens
        cleanup_test_directory() 