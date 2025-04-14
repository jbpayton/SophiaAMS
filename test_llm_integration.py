import os
from dotenv import load_dotenv
from openai import OpenAI
from VectorKnowledgeGraph import VectorKnowledgeGraph
from LLMTripleExtractor import LLMTripleExtractor
import time

def test_llm_integration():
    # Load environment variables
    load_dotenv()

    # Initialize the LLM client
    client = OpenAI(
        api_key=os.getenv('LOCAL_TEXTGEN_API_KEY'),
        base_url=os.getenv('LOCAL_TEXTGEN_API_BASE')
    )

    # Create the triple extractor
    triple_extractor = LLMTripleExtractor(client)

    # Create the knowledge graph
    kgraph = VectorKnowledgeGraph(path="Test_LLM_GraphStoreMemory")

    # Example text to process
    text = """Rachel is a young vampire girl with pale skin, long blond hair tied into two pigtails with black 
    ribbons, and red eyes. She wears Gothic Lolita fashion with a frilly black gown and jacket, red ribbon bow tie, 
    a red bat symbol design cross from the front to the back on her dress, another red cross on her shawl and bottom 
    half, black pointy heel boots with a red cross, and a red ribbon on her right ankle."""

    # Extract triples using the triple extractor
    triples, metadata = triple_extractor.extract_triples(text)
    
    # Add metadata to each triple
    metadata_list = []
    for triple in triples:
        meta = {
            "reference": "https://example.com/rachel",
            "timestamp": time.time()
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
    kgraph.visualize_graph_from_nouns([query], similarity_threshold=0.7, depth=1)

    # Clean up test data
    if os.path.exists("Test_LLM_GraphStoreMemory"):
        import shutil
        shutil.rmtree("Test_LLM_GraphStoreMemory")

if __name__ == "__main__":
    test_llm_integration() 