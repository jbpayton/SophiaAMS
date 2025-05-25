import os
import sys
# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from openai import OpenAI
from VectorKnowledgeGraph import VectorKnowledgeGraph
from triple_extraction import extract_triples_from_string
import time

def test_llm_integration():
    # Load environment variables
    load_dotenv()    # Create the knowledge graph
    kgraph = VectorKnowledgeGraph(path="test-output/Test_LLM_GraphStoreMemory")

    # Example text to process
    text = """Rachel is a young vampire girl with pale skin, long blond hair tied into two pigtails with black 
    ribbons, and red eyes. She wears Gothic Lolita fashion with a frilly black gown and jacket, red ribbon bow tie, 
    a red bat symbol design cross from the front to the back on her dress, another red cross on her shawl and bottom 
    half, black pointy heel boots with a red cross, and a red ribbon on her right ankle."""

    # Extract triples using the new extractor
    result = extract_triples_from_string(text)
    
    # Convert the new format to the old format for compatibility
    triples = []
    metadata_list = []
    for triple_data in result["triples"]:
        subject = triple_data["subject"]["text"]
        relationship = triple_data["verb"]["text"]
        obj = triple_data["object"]["text"]
        triples.append((subject, relationship, obj))
        
        # Create metadata from properties
        meta = {
            "reference": "https://example.com/rachel",
            "timestamp": time.time(),
            "source_text": triple_data["source_text"]
        }
        metadata_list.append(meta)

    # Add triples to the knowledge graph
    kgraph.add_triples(triples, metadata_list)

    # Query the graph
    query = "Rachel"
    results = kgraph.build_graph_from_noun(query, similarity_threshold=0.7)
    print(f"Results for query '{query}':")
    for triple in results:
        print(triple)

    # Visualize the graph
    kgraph.visualize_graph_from_nouns([query], similarity_threshold=0.7, depth=1)    # Clean up test data
    if os.path.exists("test-output/Test_LLM_GraphStoreMemory"):
        import shutil
        shutil.rmtree("test-output/Test_LLM_GraphStoreMemory")

if __name__ == "__main__":
    test_llm_integration() 