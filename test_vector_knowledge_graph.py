import os
from dotenv import load_dotenv
from openai import OpenAI
from VectorKnowledgeGraph import VectorKnowledgeGraph
from LLMTripleExtractor import LLMTripleExtractor

def main():
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
    kgraph = VectorKnowledgeGraph(
        triple_extractor=triple_extractor,
        path="Test_GraphStoreMemory"
    )

    # Example text to process
    text = """Rachel is a young vampire girl with pale skin, long blond hair tied into two pigtails with black 
    ribbons, and red eyes. She wears Gothic Lolita fashion with a frilly black gown and jacket, red ribbon bow tie, 
    a red bat symbol design cross from the front to the back on her dress, another red cross on her shawl and bottom 
    half, black pointy heel boots with a red cross, and a red ribbon on her right ankle."""

    # Process the text
    kgraph.process_text(text, metadata={"reference": "https://example.com/rachel"})

    # Query the graph
    query = "Rachel"
    results = kgraph.build_graph_from_noun(query, similarity_threshold=0.7)
    print(f"Results for query '{query}':")
    for triple in results:
        print(triple)

    # Get a summary
    summary = kgraph.summarize_graph(results)
    print("\nSummary:")
    print(summary)

if __name__ == "__main__":
    main() 