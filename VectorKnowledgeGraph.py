import json
import re
import shutil
import time
from functools import reduce
import os
from matplotlib import pyplot as plt
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.models import Distance, VectorParams
import networkx as nx
import numpy as np
from sentence_transformers import SentenceTransformer
from typing import List, Tuple, Dict, Any

# Load environment variables
load_dotenv()

class VectorKnowledgeGraph:
    def __init__(self, embedding_model=None, embedding_dim=None, path="VectorKnowledgeGraphData"):
        """
        Initialize the Vector Knowledge Graph.
        
        Args:
            embedding_model: Optional pre-configured embedding model
            embedding_dim: Optional embedding dimension
            path: Path to store graph data
        """
        if embedding_model is None:
            self.embedding_model = SentenceTransformer(os.getenv('EMBEDDING_MODEL', 'sentence-transformers/all-MiniLM-L6-v2'))
            self.embedding_dim = int(os.getenv('EMBEDDING_DIM', 384))
        else:
            self.embedding_model = embedding_model
            self.embedding_dim = embedding_dim

        # Ensure the directory exists
        self.save_path = path
        os.makedirs(path, exist_ok=True)
        
        # Initialize Qdrant client with local storage
        self.qdrant_client = QdrantClient(path=os.path.join(path, "qdrant_data"))
        
        # Define collection with named vectors
        self.collection_name = os.getenv('QDRANT_COLLECTION_NAME', 'knowledge_graph')
        
        # Create collection if it doesn't exist
        collections = self.qdrant_client.get_collections().collections
        collection_names = [collection.name for collection in collections]
        
        if self.collection_name not in collection_names:
            self.qdrant_client.create_collection(
                collection_name=self.collection_name,
                vectors_config={
                    "subject": VectorParams(size=self.embedding_dim, distance=Distance.COSINE),
                    "relationship": VectorParams(size=self.embedding_dim, distance=Distance.COSINE),
                    "object": VectorParams(size=self.embedding_dim, distance=Distance.COSINE)
                }
            )

    def add_triples(self, triples: List[Tuple[str, str, str]], metadata: List[Dict[str, Any]] = None):
        """
        Add triples to the knowledge graph with their embeddings and metadata.
        
        Args:
            triples: List of (subject, relationship, object) tuples
            metadata: Optional list of metadata dictionaries for each triple
        """
        if metadata is None:
            metadata = [{} for _ in triples]

        # Generate embeddings for each component
        subjects, relationships, objects = zip(*triples)
        subject_embeddings = self.embedding_model.encode(subjects)
        relationship_embeddings = self.embedding_model.encode(relationships)
        object_embeddings = self.embedding_model.encode(objects)
        
        # Prepare points for Qdrant insertion
        points = []
        for i, (triple, s_emb, r_emb, o_emb, meta) in enumerate(zip(triples, subject_embeddings, relationship_embeddings, object_embeddings, metadata)):
            subject, relationship, obj = triple
            points.append(models.PointStruct(
                id=i,
                vector={
                    "subject": s_emb.tolist(),
                    "relationship": r_emb.tolist(),
                    "object": o_emb.tolist()
                },
                payload={
                    "subject": subject,
                    "relationship": relationship,
                    "object": obj,
                    "metadata": meta
                }
            ))

        if points:
            # Insert into Qdrant
            self.qdrant_client.upsert(
                collection_name=self.collection_name,
                points=points
            )

    def build_graph_from_subject_relationship(self, subject_relationship, similarity_threshold=0.8, max_results=20, metadata_query=None,
                                      return_metadata=False):
        # Check if collection is empty
        collection_info = self.qdrant_client.get_collection(self.collection_name)
        if collection_info.points_count == 0:
            return []

        subject, verb = subject_relationship
        subject_embedding = self.embedding_model.encode([subject])[0]
        verb_embedding = self.embedding_model.encode([verb])[0]
        
        # Search for subject matches
        subject_results = self.qdrant_client.search(
            collection_name=self.collection_name,
            query_vector=("subject", subject_embedding.tolist()),
            limit=max_results,
            with_payload=True,
            with_vectors=False
        )
        
        # Search for verb matches
        verb_results = self.qdrant_client.search(
            collection_name=self.collection_name,
            query_vector=("relationship", verb_embedding.tolist()),
            limit=max_results,
            with_payload=True,
            with_vectors=False
        )

        collected_triples = []
        collected_metadata = []

        # Find common triples between subject and verb matches
        subject_triple_ids = {hit.id for hit in subject_results}
        verb_triple_ids = {hit.id for hit in verb_results}
        common_triple_ids = subject_triple_ids.intersection(verb_triple_ids)

        # Collect matching triples
        for hit in subject_results:
            if hit.id in common_triple_ids:
                payload = hit.payload
                triple = (payload["subject"], payload["relationship"], payload["object"])
                similarity = hit.score

                if similarity >= similarity_threshold:
                    collected_triples.append(triple)
                    if return_metadata:
                        collected_metadata.append(payload.get("metadata"))

        if return_metadata:
            return list(zip(collected_triples, collected_metadata))
        else:
            return collected_triples

    def query_triples_from_metadata(self, metadata_criteria):
        """
        Query triples based on metadata criteria.
        
        Args:
            metadata_criteria: Dictionary of metadata fields and values to match
        """
        # Build filter condition
        filter_conditions = []
        for key, value in metadata_criteria.items():
            filter_conditions.append(
                models.FieldCondition(
                    key=f"metadata.{key}",
                    match=models.MatchValue(value=value)
                )
            )
        
        filter_condition = models.Filter(
            must=filter_conditions
        )
        
        # Query Qdrant
        results = self.qdrant_client.scroll(
            collection_name=self.collection_name,
            scroll_filter=filter_condition,
            with_payload=True,
            limit=1000
        )
        
        return [(hit.payload["subject"], hit.payload["relationship"], hit.payload["object"]) 
                for hit in results[0]]

    def save(self, path=""):
        """Save is now handled automatically by Qdrant's local storage"""
        pass

    def load(self, path="VectorKnowledgeGraphData"):
        """Load is now handled automatically by Qdrant's local storage"""
        return True

    def build_graph_from_noun(self, query, similarity_threshold=0.8, depth=0, metadata_query=None,
                              return_metadata=False):
        # Check if collection is empty
        collection_info = self.qdrant_client.get_collection(self.collection_name)
        if collection_info.points_count == 0:
            return []

        # Initialize lists to collect results and a set to keep track of visited nodes
        collected_triples = []
        collected_metadata = []
        visited = set()

        def recursive_search(current_point, current_depth):
            if current_depth > depth:
                return

            visited.add(current_point)
            current_point_embedding = self.embedding_model.encode([current_point])[0]

            # Only search for matches where the current point is the subject
            subject_results = self.qdrant_client.search(
                collection_name=self.collection_name,
                query_vector=("subject", current_point_embedding.tolist()),
                limit=100,
                with_payload=True,
                with_vectors=False
            )

            # Process subject matches
            for hit in subject_results:
                payload = hit.payload
                triple = (payload["subject"], payload["relationship"], payload["object"])
                similarity = hit.score

                if similarity >= similarity_threshold:
                    collected_triples.append(triple)
                    if return_metadata:
                        collected_metadata.append(payload.get("metadata"))

                    # Recurse on the object if it hasn't been visited
                    if payload["object"] not in visited:
                        recursive_search(payload["object"], current_depth + 1)

        # Kick off the recursive search from the query point
        recursive_search(query, 0)

        if return_metadata:
            return list(zip(collected_triples, collected_metadata))
        else:
            return list(set(collected_triples))

    def visualize_graph_from_nouns(self, queries, similarity_threshold=0.8, depth=0, metadata_query=None):
        # Check if collection is empty
        collection_info = self.qdrant_client.get_collection(self.collection_name)
        if collection_info.points_count == 0:
            return

        G = nx.DiGraph()
        visited = set()

        def recursive_search(current_point, current_depth):
            if current_depth > depth:
                return

            visited.add(current_point)
            current_point_embedding = self.embedding_model.encode([current_point])[0]

            # Only search for matches where the current point is the subject
            subject_results = self.qdrant_client.search(
                collection_name=self.collection_name,
                query_vector=("subject", current_point_embedding.tolist()),
                limit=100,
                with_payload=True,
                with_vectors=False
            )

            # Process subject matches
            for hit in subject_results:
                payload = hit.payload
                similarity = hit.score

                if similarity >= similarity_threshold:
                    G.add_edge(payload["subject"], payload["object"], 
                             weight=similarity, 
                             label=f'Similarity: {similarity:.2f}')

                    if payload["object"] not in visited:
                        recursive_search(payload["object"], current_depth + 1)

        for query in queries:
            recursive_search(query, 0)

        pos = nx.spring_layout(G, seed=42)
        nx.draw_networkx_nodes(G, pos, node_size=500)
        nx.draw_networkx_edges(G, pos, width=1.0, alpha=0.5)
        edge_labels = {(node1, node2): data['label'] for node1, node2, data in G.edges(data=True)}
        nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, font_color='red')
        nx.draw_networkx_labels(G, pos, font_size=12)
        plt.show()

def main():
    # Test basic triple operations
    print("Testing basic triple operations...")
    
    # Create a test graph
    kgraph = VectorKnowledgeGraph(path="Test_GraphStoreMemory")
    
    try:
        # Test triples - creating a more complex knowledge graph
        test_triples = [
            # Animal characteristics
            ("cat", "has", "whiskers"),
            ("cat", "has", "fur"),
            ("cat", "is", "mammal"),
            ("cat", "eats", "fish"),
            ("cat", "eats", "meat"),
            
            ("dog", "has", "tail"),
            ("dog", "has", "fur"),
            ("dog", "is", "mammal"),
            ("dog", "eats", "meat"),
            ("dog", "eats", "kibble"),
            
            ("bird", "has", "wings"),
            ("bird", "has", "feathers"),
            ("bird", "is", "vertebrate"),
            ("bird", "eats", "seeds"),
            ("bird", "eats", "insects"),
            
            # Food chain relationships
            ("cat", "hunts", "bird"),
            ("cat", "hunts", "mouse"),
            ("dog", "chases", "cat"),
            ("dog", "chases", "bird"),
            
            # Habitat relationships
            ("cat", "lives_in", "house"),
            ("cat", "lives_in", "barn"),
            ("dog", "lives_in", "house"),
            ("dog", "lives_in", "yard"),
            ("bird", "lives_in", "tree"),
            ("bird", "lives_in", "nest"),
            
            # Physical characteristics
            ("whiskers", "help_with", "balance"),
            ("whiskers", "help_with", "navigation"),
            ("wings", "enable", "flight"),
            ("feathers", "provide", "insulation"),
            ("fur", "provides", "warmth"),
            ("tail", "helps_with", "balance")
        ]
        
        # Test metadata - adding more detailed metadata
        test_metadata = [
            {"source": "biology_textbook", "timestamp": time.time(), "confidence": 0.95},
            {"source": "biology_textbook", "timestamp": time.time(), "confidence": 0.95},
            {"source": "biology_textbook", "timestamp": time.time(), "confidence": 0.95},
            {"source": "animal_behavior", "timestamp": time.time(), "confidence": 0.85},
            {"source": "animal_behavior", "timestamp": time.time(), "confidence": 0.85},
            
            {"source": "biology_textbook", "timestamp": time.time(), "confidence": 0.95},
            {"source": "biology_textbook", "timestamp": time.time(), "confidence": 0.95},
            {"source": "biology_textbook", "timestamp": time.time(), "confidence": 0.95},
            {"source": "animal_behavior", "timestamp": time.time(), "confidence": 0.85},
            {"source": "animal_behavior", "timestamp": time.time(), "confidence": 0.85},
            
            {"source": "biology_textbook", "timestamp": time.time(), "confidence": 0.95},
            {"source": "biology_textbook", "timestamp": time.time(), "confidence": 0.95},
            {"source": "biology_textbook", "timestamp": time.time(), "confidence": 0.95},
            {"source": "animal_behavior", "timestamp": time.time(), "confidence": 0.85},
            {"source": "animal_behavior", "timestamp": time.time(), "confidence": 0.85},
            
            {"source": "ecology_study", "timestamp": time.time(), "confidence": 0.80},
            {"source": "ecology_study", "timestamp": time.time(), "confidence": 0.80},
            {"source": "ecology_study", "timestamp": time.time(), "confidence": 0.80},
            {"source": "ecology_study", "timestamp": time.time(), "confidence": 0.80},
            
            {"source": "habitat_research", "timestamp": time.time(), "confidence": 0.90},
            {"source": "habitat_research", "timestamp": time.time(), "confidence": 0.90},
            {"source": "habitat_research", "timestamp": time.time(), "confidence": 0.90},
            {"source": "habitat_research", "timestamp": time.time(), "confidence": 0.90},
            {"source": "habitat_research", "timestamp": time.time(), "confidence": 0.90},
            {"source": "habitat_research", "timestamp": time.time(), "confidence": 0.90},
            
            {"source": "anatomy_study", "timestamp": time.time(), "confidence": 0.95},
            {"source": "anatomy_study", "timestamp": time.time(), "confidence": 0.95},
            {"source": "anatomy_study", "timestamp": time.time(), "confidence": 0.95},
            {"source": "anatomy_study", "timestamp": time.time(), "confidence": 0.95},
            {"source": "anatomy_study", "timestamp": time.time(), "confidence": 0.95},
            {"source": "anatomy_study", "timestamp": time.time(), "confidence": 0.95}
        ]
        
        # Add triples
        kgraph.add_triples(test_triples, test_metadata)
        
        # Test querying by noun with multiple hops
        print("\nTesting query by noun 'cat' with depth=2:")
        results = kgraph.build_graph_from_noun("cat", similarity_threshold=0.7, depth=2)
        print("\nFound triples:")
        for triple in results:
            print(triple)
        
        # Test querying by subject-relationship with complex relationships
        print("\nTesting query by subject-relationship ('cat', 'hunts'):")
        results = kgraph.build_graph_from_subject_relationship(("cat", "hunts"), similarity_threshold=0.7)
        print("\nFound triples:")
        for triple in results:
            print(triple)
        
        # Test metadata query with multiple criteria
        print("\nTesting metadata query (source='biology_textbook'):")
        results = kgraph.query_triples_from_metadata({"source": "biology_textbook"})
        print("\nFound triples:")
        for triple in results:
            print(triple)
        
        # Test visualization with multiple starting points
        print("\nTesting visualization with multiple starting points...")
        kgraph.visualize_graph_from_nouns(["cat", "bird", "dog"], similarity_threshold=0.7, depth=2)
    
    finally:
        # Clean up test data
        if hasattr(kgraph, 'qdrant_client'):
            kgraph.qdrant_client.close()
        if os.path.exists("Test_GraphStoreMemory"):
            shutil.rmtree("Test_GraphStoreMemory")

if __name__ == "__main__":
    main()




