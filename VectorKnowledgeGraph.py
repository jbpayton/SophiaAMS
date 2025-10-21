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
from typing import List, Tuple, Dict, Any, Optional
import logging
from datetime import datetime
from utils import setup_logging # Added import

# Load environment variables
load_dotenv()

class VectorKnowledgeGraph:
    def __init__(self, embedding_model=None, embedding_dim=None, path="VectorKnowledgeGraphData"):
        """
        Initialize the Vector Knowledge Graph.
        
        Args:
            embedding_model: Optional pre-configured embedding model
            embedding_dim: Optional embedding dimension (integer)
            path: Path to store graph data
        """
        logging.debug(f"Initializing VectorKnowledgeGraph with path: {path}")
        if embedding_model is None:
            logging.debug("Using default embedding model")
            self.embedding_model = SentenceTransformer(os.getenv('EMBEDDING_MODEL', 'sentence-transformers/all-MiniLM-L6-v2'))
            # Suppress progress bars globally for this model
            self.embedding_model._show_progress_bar = False
            # Ensure embedding_dim has a default integer value
            try:
                self.embedding_dim: int = int(os.getenv('EMBEDDING_DIM', 384))
            except ValueError:
                logging.warning("Invalid EMBEDDING_DIM from env, using default 384")
                self.embedding_dim = 384
        else:
            logging.debug("Using provided embedding model")
            self.embedding_model = embedding_model
            if embedding_dim is None:
                logging.warning("embedding_dim not provided with custom model, attempting to infer or defaulting to 384")
                # Attempt to infer, or use a common default if not easily inferable
                if hasattr(self.embedding_model, 'get_sentence_embedding_dimension'):
                    self.embedding_dim = self.embedding_model.get_sentence_embedding_dimension()
                else:
                    self.embedding_dim = 384 # Default if cannot infer
                    logging.warning(f"Could not infer embedding_dim, defaulted to {self.embedding_dim}")
            else:
                self.embedding_dim = embedding_dim

        # Ensure the directory exists
        self.save_path = path
        os.makedirs(path, exist_ok=True)
        logging.debug(f"Created/verified directory: {path}")
        
        # Initialize Qdrant client with local storage
        logging.debug("Initializing Qdrant client")
        self.qdrant_client = QdrantClient(path=os.path.join(path, "qdrant_data"))
        
        # Define collection with named vectors
        self.collection_name = os.getenv('QDRANT_COLLECTION_NAME', 'knowledge_graph')
        logging.debug(f"Using collection name: {self.collection_name}")
        
        # Create collection if it doesn't exist
        collections = self.qdrant_client.get_collections().collections
        collection_names = [collection.name for collection in collections]
        
        if self.collection_name not in collection_names:
            logging.info(f"Creating new collection: {self.collection_name}")
            self.qdrant_client.create_collection(
                collection_name=self.collection_name,
                vectors_config={
                    "subject": VectorParams(size=self.embedding_dim, distance=Distance.COSINE),
                    "relationship": VectorParams(size=self.embedding_dim, distance=Distance.COSINE),
                    "object": VectorParams(size=self.embedding_dim, distance=Distance.COSINE),
                    "topic_vector": VectorParams(size=self.embedding_dim, distance=Distance.COSINE),
                    "triple_content": VectorParams(size=self.embedding_dim, distance=Distance.COSINE)
                }
            )
            logging.info("Collection created successfully")
        else:
            logging.debug("Collection already exists")

    def add_triples(self, triples: List[Tuple[str, str, str]], metadata: Optional[List[Dict[str, Any]]] = None): # metadata can be None
        """
        Add triples to the knowledge graph with their embeddings and metadata.
        
        Args:
            triples: List of (subject, relationship, object) tuples
            metadata: Optional list of metadata dictionaries for each triple
        """
        logging.info(f"Adding {len(triples)} triples to knowledge graph")
        if not triples:
            logging.warning("No triples provided to add_triples method.")
            return
            
        if metadata is None:
            metadata = [{} for _ in triples]
            logging.debug("No metadata provided, using empty metadata")
        elif len(metadata) != len(triples):
            logging.warning("Mismatch between number of triples and metadata entries. Using empty metadata for safety.")
            metadata = [{} for _ in triples] # Fallback to empty if mismatch

        # Generate embeddings for each component
        logging.debug("Generating embeddings for triples")
        subjects, relationships, objects = zip(*triples)
        
        # Convert tuples from zip to lists for SentenceTransformer
        subject_embeddings = self.embedding_model.encode(list(subjects))
        relationship_embeddings = self.embedding_model.encode(list(relationships))
        object_embeddings = self.embedding_model.encode(list(objects))
        
        # Generate embeddings for the entire triple content
        triple_content_strings = [f"Subject: {s}, Relationship: {r}, Object: {o}" for s, r, o in triples]
        triple_content_embeddings = self.embedding_model.encode(triple_content_strings)

        # Generate embeddings for topics
        topic_embeddings = []
        for meta in metadata:
            triple_topics = meta.get("topics", [])
            if triple_topics and isinstance(triple_topics, list) and all(isinstance(t, str) for t in triple_topics):
                concatenated_topics = " ".join(triple_topics)
                topic_embeddings.append(self.embedding_model.encode([concatenated_topics])[0])
            else:
                # Use a zero vector if no topics or invalid format
                topic_embeddings.append(np.zeros(self.embedding_dim))
        
        logging.debug("Embeddings generated successfully")
        
        # Prepare points for Qdrant insertion
        logging.debug("Preparing points for Qdrant insertion")
        points = []
        for i, (triple, s_emb, r_emb, o_emb, t_emb, c_emb, meta) in enumerate(zip(triples, subject_embeddings, relationship_embeddings, object_embeddings, topic_embeddings, triple_content_embeddings, metadata)):
            subject, relationship, obj = triple
            # Ensure unique ID, for example, by using a combination of current time and index, or UUIDs
            # For simplicity, using index i, but this assumes add_triples is called sequentially or IDs are managed externally
            # A more robust ID would be `str(uuid.uuid4())` or a hash of the triple content.
            # Using `self.qdrant_client.count(collection_name=self.collection_name).count + i` could also work if inserts are batched.
            # For now, let's assume `i` is sufficient for this context, but flag for potential improvement.
            # A simple way to get a unique ID for new points is to get the current count of points.
            # However, this is not safe for concurrent additions.
            # Let's use a timestamp + index for a bit more uniqueness in a single run.
            # For production, a robust UUID or content hash is better.
            # Qdrant recommends using your own IDs. If not provided, it generates them.
            # Let's allow Qdrant to generate IDs by not specifying `id` or using `None`.
            # Or, if we need to refer to them, we must generate them.
            # The previous code used `i`. Let's stick to that for now, assuming it's within a single batch context.
            # If `add_triples` is called multiple times, `i` will restart from 0, causing ID collisions.
            # This needs to be addressed. A simple fix is to use a unique identifier.
            # For now, let's use a placeholder for ID generation that needs to be robust.
            # A common pattern is to use a hash of the content or a UUID.
            # Let's use a simple counter based on existing points for this iteration.
            # This is still not perfectly safe for concurrent writes.
            # Qdrant can auto-generate IDs if you don't provide them.
            # Let's try omitting the ID and let Qdrant handle it.
            # Update: Qdrant requires IDs for `PointStruct`.
            # We need a strategy for unique IDs.
            # Simplest for now: use a large random number or hash of content.
            # Let's use a hash of the triple itself for a deterministic ID.
            import hashlib
            triple_string = f"{subject}-{relationship}-{obj}"
            point_id = hashlib.md5(triple_string.encode()).hexdigest()

            points.append(models.PointStruct(
                id=point_id, 
                vector={
                    "subject": s_emb.tolist(),
                    "relationship": r_emb.tolist(),
                    "object": o_emb.tolist(),
                    "topic_vector": t_emb.tolist(),
                    "triple_content": c_emb.tolist()
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
            logging.debug("Inserting points into Qdrant")
            self.qdrant_client.upsert(
                collection_name=self.collection_name,
                points=points
            )
            logging.info(f"Successfully inserted {len(points)} points into Qdrant")
        else:
            logging.warning("No points to insert")

    def build_graph_from_subject_relationship(self, subject_relationship, similarity_threshold=0.8, max_results=20, metadata_query=None,
                                      return_metadata=False):
        logging.debug(f"Building graph from subject-relationship with threshold: {similarity_threshold}")
        # Check if collection is empty
        collection_info = self.qdrant_client.get_collection(self.collection_name)
        if collection_info.points_count == 0:
            logging.warning("Collection is empty")
            return []

        subject, verb = subject_relationship
        logging.debug(f"Generating embeddings for subject: {subject} and verb: {verb}")
        subject_embedding = self.embedding_model.encode([subject])[0]
        verb_embedding = self.embedding_model.encode([verb])[0]
        
        # Search for subject matches
        logging.debug("Searching for subject matches")
        subject_results = self.qdrant_client.search(
            collection_name=self.collection_name,
            query_vector=("subject", subject_embedding.tolist()),
            limit=max_results,
            with_payload=True,
            with_vectors=False
        )
        
        # Search for verb matches
        logging.debug("Searching for verb matches")
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
        logging.debug(f"Found {len(common_triple_ids)} common triples")

        # Collect matching triples
        for hit in subject_results:
            if hit.id in common_triple_ids:
                payload = hit.payload
                if payload:
                    triple = (payload.get("subject"), payload.get("relationship"), payload.get("object"))
                    similarity = hit.score

                    if similarity >= similarity_threshold:
                        collected_triples.append(triple)
                        if return_metadata:
                            collected_metadata.append(payload.get("metadata"))

        logging.info(f"Found {len(collected_triples)} matching triples")
        if return_metadata:
            # Add confidence score to metadata
            for i in range(len(collected_triples)):
                # This confidence is based on the subject match score.
                # A more nuanced approach could average subject and verb scores
                # or use the minimum of the two. Let's use subject score for now.
                subject_hit = next((hit for hit in subject_results if hit.id == common_triple_ids[i]), None)
                if subject_hit:
                    collected_metadata[i]['confidence'] = subject_hit.score
                else:
                    collected_metadata[i]['confidence'] = similarity_threshold # Default
            return list(zip(collected_triples, collected_metadata))
        else:
            return collected_triples

    def query_triples_from_metadata(self, metadata_criteria):
        """
        Query triples based on metadata criteria.
        
        Args:
            metadata_criteria: Dictionary of metadata fields and values to match.
                               Can include fields like 'speaker', 'entity', 'is_from_summary'
        """
        logging.info(f"Querying triples with metadata criteria: {metadata_criteria}")
        # Build filter condition
        filter_conditions = []
        for key, value in metadata_criteria.items():
            # Handle special cases for common fields
            if key in ['speaker', 'entity', 'is_from_summary']:
                filter_conditions.append(
                    models.FieldCondition(
                        key=f"metadata.{key}",
                        match=models.MatchValue(value=value)
                    )
                )
            else:
                # For nested metadata fields
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
        logging.debug("Executing metadata query")
        results = self.qdrant_client.scroll(
            collection_name=self.collection_name,
            scroll_filter=filter_condition,
            with_payload=True,
            limit=1000
        )
        
        # Return triples with complete metadata
        triples_with_metadata = []
        for hit in results[0]: # results[0] contains the list of Hit objects
            payload = hit.payload
            if payload:
                triple = (payload.get("subject"), payload.get("relationship"), payload.get("object"))
                metadata = payload.get("metadata", {})
                triples_with_metadata.append((triple, metadata))
        
        logging.info(f"Found {len(triples_with_metadata)} triples matching metadata criteria")
        return triples_with_metadata

    def get_all_triples(self):
        """
        Retrieve all triples stored in the knowledge graph with their metadata.
        
        Returns:
            List of dictionaries, where each dictionary contains subject, predicate, object and metadata
        """
        logging.info("Retrieving all triples from knowledge graph")
        
        # Check if collection is empty
        collection_info = self.qdrant_client.get_collection(self.collection_name)
        if collection_info.points_count == 0:
            logging.warning("Collection is empty")
            return []
        
        # Use scroll to retrieve all points
        all_points = []
        offset = None
        
        while True:
            # Get a batch of points
            batch, offset = self.qdrant_client.scroll(
                collection_name=self.collection_name,
                scroll_filter=None,  # No filter to get all points
                limit=1000,  # Get 1000 points at a time
                offset=offset,  # Use the offset from the previous iteration
                with_payload=True,
                with_vectors=False
            )
            
            all_points.extend(batch)
            
            # If there are no more points, break the loop
            if len(batch) < 1000 or offset is None:
                break
        
        # Convert points to triple format with metadata
        triples = []
        for point in all_points:
            payload = point.payload
            if payload:
                triple_data = {
                    "subject": payload.get("subject"),
                    "predicate": payload.get("relationship"),
                    "object": payload.get("object")
                }
                
                # Add metadata if available
                if "metadata" in payload:
                    triple_data["metadata"] = payload.get("metadata")
                
                triples.append(triple_data)
        
        logging.info(f"Retrieved {len(triples)} triples from knowledge graph")
        return triples

    def find_triples_by_vectorized_topics(self, query_topics: List[str], return_metadata: bool = True, limit: int = 10, similarity_threshold: float = 0.7) -> List:
        """
        Find triples by vector similarity of their associated topics to the query topics.
        This requires that topics for each triple were embedded and stored during ingestion as 'topic_vector'.

        Args:
            query_topics: A list of topic strings from the query.
            return_metadata: Whether to return metadata along with the triples.
            limit: Maximum number of results to return.
            similarity_threshold: The minimum similarity score for a topic match.

        Returns:
            A list of (triple, metadata) tuples or just triples, matching the criteria.
        """
        logging.info(f"Finding triples by vectorized topics: {query_topics} with threshold: {similarity_threshold}")
        if not query_topics or not all(isinstance(t, str) for t in query_topics):
            logging.warning("query_topics list is empty or contains non-string elements. Returning no results.")
            return []

        collection_info = self.qdrant_client.get_collection(self.collection_name)
        if collection_info.points_count == 0:
            logging.warning(f"Collection '{self.collection_name}' is empty.")
            return []

        # Concatenate query topics and generate embedding
        concatenated_query_topics = " ".join(query_topics)
        if not concatenated_query_topics.strip():
            logging.warning("Concatenated query topics are empty. Returning no results.")
            return []
            
        query_topic_embedding = self.embedding_model.encode([concatenated_query_topics])[0]

        logging.debug(f"Searching with topic vector against collection: {self.collection_name}")
        search_results = self.qdrant_client.search(
            collection_name=self.collection_name,
            query_vector=("topic_vector", query_topic_embedding.tolist()), # Search against 'topic_vector'
            limit=limit,
            score_threshold=similarity_threshold, # Qdrant uses score_threshold for minimum similarity
            with_payload=True,
            with_vectors=False # We don't need the vectors themselves in the result
        )

        found_triples = []
        for hit in search_results:
            payload = hit.payload
            if payload:
                triple = (payload.get("subject"), payload.get("relationship"), payload.get("object"))
                if return_metadata:
                    metadata = payload.get("metadata", {})
                    # Include the similarity score in the metadata for context
                    metadata_with_score = {**metadata, "topic_similarity_score": hit.score}
                    found_triples.append((triple, metadata_with_score))
                else:
                    # If not returning metadata, we might still want to convey the triple itself
                    # or decide how to handle this case. For now, just the triple.
                    found_triples.append(triple)
        
        logging.info(f"Found {len(found_triples)} triples matching vectorized topics with score >= {similarity_threshold}")
        return found_triples

    def find_triples_by_text_similarity(self, query_text: str, return_metadata: bool = True, limit: int = 25, similarity_threshold: float = 0.7) -> List:
        """
        Finds triples by performing a semantic search on the entire content of the triple.

        Args:
            query_text: The text to search for.
            return_metadata: Whether to return metadata.
            limit: The maximum number of results.
            similarity_threshold: The minimum similarity score.

        Returns:
            A list of matching triples.
        """
        logging.info(f"Finding triples by text similarity for: '{query_text}'")
        
        query_embedding = self.embedding_model.encode([query_text])[0]

        search_results = self.qdrant_client.search(
            collection_name=self.collection_name,
            query_vector=("triple_content", query_embedding.tolist()),
            limit=limit,
            score_threshold=similarity_threshold,
            with_payload=True
        )

        found_triples = []
        for hit in search_results:
            payload = hit.payload
            if payload:
                triple = (payload.get("subject"), payload.get("relationship"), payload.get("object"))
                if return_metadata:
                    metadata = payload.get("metadata", {})
                    metadata['confidence'] = hit.score
                    found_triples.append((triple, metadata))
                else:
                    found_triples.append(triple)
        
        logging.info(f"Found {len(found_triples)} triples from text similarity search.")
        return found_triples

    def find_triples_by_topic_tags(self, topics_to_match: List[str], return_metadata: bool = True, limit: int = 1000) -> List:
        """
        Find triples where the 'topics' list in their metadata contains any of the specified topic strings.

        Args:
            topics_to_match: A list of topic strings to search for.
            return_metadata: Whether to return metadata along with the triples.
            limit: Maximum number of results to return.

        Returns:
            A list of (triple, metadata) tuples or just triples, matching the criteria.
        """
        logging.info(f"Finding triples by topic tags: {topics_to_match}")
        if not topics_to_match:
            logging.warning("topics_to_match list is empty. Returning no results.")
            return []

        collection_info = self.qdrant_client.get_collection(self.collection_name)
        if collection_info.points_count == 0:
            logging.warning(f"Collection '{self.collection_name}' is empty.")
            return []

        # Construct the filter for matching any of the topics in the 'metadata.topics' array
        # Ensure that topics_to_match contains only non-empty strings
        valid_topics_to_match = [topic for topic in topics_to_match if topic and isinstance(topic, str)]
        if not valid_topics_to_match:
            logging.warning("All topics in topics_to_match are empty or invalid. Returning no results.")
            return []
            
        topic_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="metadata.topics",  # Assuming topics are stored in metadata.topics
                    match=models.MatchAny(
                        any=valid_topics_to_match
                    )
                )
            ]
        )

        logging.debug(f"Executing scroll query with topic filter: {topic_filter}")
        # Using scroll to get all matching results up to the limit
        results, _ = self.qdrant_client.scroll(
            collection_name=self.collection_name,
            scroll_filter=topic_filter,
            limit=limit,
            with_payload=True,
            with_vectors=False  # Vectors are not needed for this type of query
        )

        found_triples = []
        for hit in results: # Iterate directly over results (list of Record)
            payload = hit.payload
            if payload:
                triple = (payload.get("subject"), payload.get("relationship"), payload.get("object"))
                if return_metadata:
                    metadata = payload.get("metadata", {})
                    found_triples.append((triple, metadata))
                else:
                    found_triples.append(triple)
        
        logging.info(f"Found {len(found_triples)} triples matching topic tags: {valid_topics_to_match}")
        return found_triples

    def compute_entity_similarities(self, entities: List[str], similarity_threshold: float = 0.6) -> List[Tuple[str, str, float]]:
        """
        Compute pairwise semantic similarities between entities based on their embeddings.

        This is the core method that reveals the self-assembling nature of the graph -
        entities can stand in for each other based on embedding similarity, not just explicit links.

        Args:
            entities: List of entity strings to compare
            similarity_threshold: Minimum cosine similarity to include in results

        Returns:
            List of (entity1, entity2, similarity_score) tuples for pairs above threshold
        """
        logging.info(f"Computing semantic similarities between {len(entities)} entities")

        if len(entities) < 2:
            logging.warning("Need at least 2 entities to compute similarities")
            return []

        # Generate embeddings for all entities
        entity_embeddings = self.embedding_model.encode(entities)

        # Compute pairwise cosine similarities
        from numpy import dot
        from numpy.linalg import norm

        def cosine_similarity(a, b):
            return float(dot(a, b) / (norm(a) * norm(b) + 1e-12))

        similarities = []
        for i in range(len(entities)):
            for j in range(i + 1, len(entities)):  # Only upper triangle to avoid duplicates
                sim_score = cosine_similarity(entity_embeddings[i], entity_embeddings[j])

                if sim_score >= similarity_threshold:
                    similarities.append((entities[i], entities[j], sim_score))

        # Sort by similarity descending
        similarities.sort(key=lambda x: x[2], reverse=True)

        logging.info(f"Found {len(similarities)} entity pairs with similarity >= {similarity_threshold}")
        return similarities

    def query_by_time_range(self, start_time: float, end_time: float, limit: int = 100, return_metadata: bool = True) -> List:
        """
        Query triples that were created within a specific time range.

        Args:
            start_time: Unix timestamp for start of range
            end_time: Unix timestamp for end of range
            limit: Maximum number of results
            return_metadata: Whether to return metadata

        Returns:
            List of triples (with metadata if requested) from the time range
        """
        logging.info(f"Querying triples from time range: {datetime.fromtimestamp(start_time)} to {datetime.fromtimestamp(end_time)}")

        collection_info = self.qdrant_client.get_collection(self.collection_name)
        if collection_info.points_count == 0:
            logging.warning(f"Collection '{self.collection_name}' is empty.")
            return []

        # Build filter for timestamp range
        time_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="metadata.timestamp",
                    range=models.Range(
                        gte=start_time,
                        lte=end_time
                    )
                )
            ]
        )

        # Query with filter
        results, _ = self.qdrant_client.scroll(
            collection_name=self.collection_name,
            scroll_filter=time_filter,
            limit=limit,
            with_payload=True,
            with_vectors=False
        )

        found_triples = []
        for hit in results:
            payload = hit.payload
            if payload:
                triple = (payload.get("subject"), payload.get("relationship"), payload.get("object"))
                if return_metadata:
                    metadata = payload.get("metadata", {})
                    found_triples.append((triple, metadata))
                else:
                    found_triples.append(triple)

        logging.info(f"Found {len(found_triples)} triples in time range")
        return found_triples

    def query_recent(self, hours: float = 24, limit: int = 100, return_metadata: bool = True) -> List:
        """
        Query triples from the last N hours.

        Args:
            hours: Number of hours to look back
            limit: Maximum number of results
            return_metadata: Whether to return metadata

        Returns:
            List of recent triples (with metadata if requested)
        """
        end_time = time.time()
        start_time = end_time - (hours * 3600)  # Convert hours to seconds

        logging.info(f"Querying triples from last {hours} hours")
        return self.query_by_time_range(start_time, end_time, limit, return_metadata)

    def query_by_episode(self, episode_id: str, limit: int = 1000, return_metadata: bool = True) -> List:
        """
        Query all triples associated with a specific conversation episode.

        Args:
            episode_id: The episode identifier
            limit: Maximum number of results
            return_metadata: Whether to return metadata

        Returns:
            List of triples from the episode (with metadata if requested)
        """
        logging.info(f"Querying triples for episode: {episode_id}")

        collection_info = self.qdrant_client.get_collection(self.collection_name)
        if collection_info.points_count == 0:
            logging.warning(f"Collection '{self.collection_name}' is empty.")
            return []

        # Build filter for episode_id
        episode_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="metadata.episode_id",
                    match=models.MatchValue(value=episode_id)
                )
            ]
        )

        # Query with filter
        results, _ = self.qdrant_client.scroll(
            collection_name=self.collection_name,
            scroll_filter=episode_filter,
            limit=limit,
            with_payload=True,
            with_vectors=False
        )

        found_triples = []
        for hit in results:
            payload = hit.payload
            if payload:
                triple = (payload.get("subject"), payload.get("relationship"), payload.get("object"))
                if return_metadata:
                    metadata = payload.get("metadata", {})
                    found_triples.append((triple, metadata))
                else:
                    found_triples.append(triple)

        logging.info(f"Found {len(found_triples)} triples for episode {episode_id}")
        return found_triples

    def save(self, path=""):
        """Save is now handled automatically by Qdrant's local storage"""
        logging.debug("Save operation not needed (handled by Qdrant)")
        pass

    def load(self, path="VectorKnowledgeGraphData"):
        """Load is now handled automatically by Qdrant's local storage"""
        logging.debug("Load operation not needed (handled by Qdrant)")
        return True

    def build_graph_from_noun(self, query, similarity_threshold=0.8, depth=0, metadata_query=None,
                              return_metadata=False, confidence_decay=0.8):
        logging.debug(f"Building graph from noun: {query} with depth: {depth}")
        # Check if collection is empty
        collection_info = self.qdrant_client.get_collection(self.collection_name)
        if collection_info.points_count == 0:
            logging.warning("Collection is empty")
            return []

        # Initialize lists to collect results and a set to keep track of visited nodes
        collected_triples = []
        collected_metadata = []
        visited = set()

        def recursive_search(current_point, current_depth, current_confidence):
            if current_depth > depth:
                return

            visited.add(current_point)
            logging.debug(f"Processing node: {current_point} at depth {current_depth} with confidence {current_confidence:.2f}")
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
                if payload:
                    triple = (payload.get("subject"), payload.get("relationship"), payload.get("object"))
                    similarity = hit.score

                    if similarity >= similarity_threshold:
                        # The confidence of this triple is the initial match similarity
                        # times the decay factor for its depth
                        new_confidence = current_confidence * similarity
                        
                        collected_triples.append(triple)
                        if return_metadata:
                            metadata = payload.get("metadata", {})
                            metadata['confidence'] = new_confidence
                            collected_metadata.append(metadata)

                        # Recurse on the object if it hasn't been visited
                        object_val = payload.get("object")
                        if object_val and object_val not in visited:
                            # The confidence for the next level is decayed
                            recursive_search(object_val, current_depth + 1, new_confidence * confidence_decay)

        # Kick off the recursive search from the query point with initial confidence of 1.0
        recursive_search(query, 0, 1.0)
        logging.info(f"Found {len(collected_triples)} triples in graph traversal")

        if return_metadata:
            return list(zip(collected_triples, collected_metadata))
        else:
            return collected_triples

    def visualize_graph_from_nouns(self, queries, similarity_threshold=0.8, depth=0, metadata_query=None):
        logging.info(f"Visualizing graph for queries: {queries}")
        # Check if collection is empty
        collection_info = self.qdrant_client.get_collection(self.collection_name)
        if collection_info.points_count == 0:
            logging.warning("Collection is empty")
            return

        G = nx.DiGraph()
        visited = set()

        def recursive_search(current_point, current_depth):
            if current_depth > depth:
                return

            visited.add(current_point)
            logging.debug(f"Processing node: {current_point} at depth {current_depth}")
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
                if payload:
                    similarity = hit.score

                    if similarity >= similarity_threshold:
                        G.add_edge(payload.get("subject"), payload.get("object"),
                                 weight=similarity,
                                 label=f'Similarity: {similarity:.2f}')

                        object_val = payload.get("object")
                        if object_val and object_val not in visited:
                            recursive_search(object_val, current_depth + 1)

        for query in queries:
            recursive_search(query, 0)

        logging.info(f"Graph contains {len(G.nodes)} nodes and {len(G.edges)} edges")
        logging.debug("Drawing graph visualization")
        pos = nx.spring_layout(G, seed=42)
        nx.draw_networkx_nodes(G, pos, node_size=500)
        nx.draw_networkx_edges(G, pos, width=1.0, alpha=0.5)
        edge_labels = {(node1, node2): data['label'] for node1, node2, data in G.edges(data=True)}
        nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, font_color='red')
        nx.draw_networkx_labels(G, pos, font_size=12)
        plt.show()
        logging.info("Graph visualization completed")

    # ============================================================================
    # GOAL SYSTEM QUERY METHODS
    # ============================================================================

    def query_goals_by_status(self, status: str, limit: int = 100, return_metadata: bool = True) -> List:
        """
        Query goals by their status.

        Args:
            status: Goal status to filter by (pending, in_progress, completed, blocked, cancelled)
            limit: Maximum number of results
            return_metadata: Whether to return metadata

        Returns:
            List of goal triples matching the status
        """
        logging.info(f"Querying goals with status: {status}")

        collection_info = self.qdrant_client.get_collection(self.collection_name)
        if collection_info.points_count == 0:
            logging.warning(f"Collection '{self.collection_name}' is empty.")
            return []

        # Build filter for goal_status in metadata
        status_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="metadata.goal_status",
                    match=models.MatchValue(value=status)
                )
            ]
        )

        # Query with filter
        results, _ = self.qdrant_client.scroll(
            collection_name=self.collection_name,
            scroll_filter=status_filter,
            limit=limit,
            with_payload=True,
            with_vectors=False
        )

        found_triples = []
        for hit in results:
            payload = hit.payload
            if payload:
                triple = (payload.get("subject"), payload.get("relationship"), payload.get("object"))
                if return_metadata:
                    metadata = payload.get("metadata", {})
                    found_triples.append((triple, metadata))
                else:
                    found_triples.append(triple)

        logging.info(f"Found {len(found_triples)} goals with status '{status}'")
        return found_triples

    def query_goals_by_priority(self, min_priority: int = 1, max_priority: int = 5, limit: int = 100, return_metadata: bool = True) -> List:
        """
        Query goals by priority range.

        Args:
            min_priority: Minimum priority (1-5)
            max_priority: Maximum priority (1-5)
            limit: Maximum number of results
            return_metadata: Whether to return metadata

        Returns:
            List of goal triples in the priority range
        """
        logging.info(f"Querying goals with priority {min_priority}-{max_priority}")

        collection_info = self.qdrant_client.get_collection(self.collection_name)
        if collection_info.points_count == 0:
            logging.warning(f"Collection '{self.collection_name}' is empty.")
            return []

        # Build filter for priority range
        priority_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="metadata.priority",
                    range=models.Range(
                        gte=min_priority,
                        lte=max_priority
                    )
                )
            ]
        )

        # Query with filter
        results, _ = self.qdrant_client.scroll(
            collection_name=self.collection_name,
            scroll_filter=priority_filter,
            limit=limit,
            with_payload=True,
            with_vectors=False
        )

        found_triples = []
        for hit in results:
            payload = hit.payload
            if payload:
                triple = (payload.get("subject"), payload.get("relationship"), payload.get("object"))
                if return_metadata:
                    metadata = payload.get("metadata", {})
                    found_triples.append((triple, metadata))
                else:
                    found_triples.append(triple)

        logging.info(f"Found {len(found_triples)} goals in priority range {min_priority}-{max_priority}")
        return found_triples

    def query_active_goals(self, limit: int = 100, return_metadata: bool = True) -> List:
        """
        Query all active goals (pending or in_progress status).

        Args:
            limit: Maximum number of results
            return_metadata: Whether to return metadata

        Returns:
            List of active goal triples
        """
        logging.info(f"Querying active goals")

        collection_info = self.qdrant_client.get_collection(self.collection_name)
        if collection_info.points_count == 0:
            logging.warning(f"Collection '{self.collection_name}' is empty.")
            return []

        # Build filter for active statuses
        active_filter = models.Filter(
            should=[
                models.FieldCondition(
                    key="metadata.goal_status",
                    match=models.MatchValue(value="pending")
                ),
                models.FieldCondition(
                    key="metadata.goal_status",
                    match=models.MatchValue(value="in_progress")
                )
            ]
        )

        # Query with filter
        results, _ = self.qdrant_client.scroll(
            collection_name=self.collection_name,
            scroll_filter=active_filter,
            limit=limit,
            with_payload=True,
            with_vectors=False
        )

        found_triples = []
        for hit in results:
            payload = hit.payload
            if payload:
                triple = (payload.get("subject"), payload.get("relationship"), payload.get("object"))
                if return_metadata:
                    metadata = payload.get("metadata", {})
                    found_triples.append((triple, metadata))
                else:
                    found_triples.append(triple)

        logging.info(f"Found {len(found_triples)} active goals")
        return found_triples

    def query_goal_by_description(self, description: str, similarity_threshold: float = 0.5, return_metadata: bool = True) -> Optional[Tuple]:
        """
        Find a specific goal by its description using semantic search.

        Args:
            description: The goal description to search for
            similarity_threshold: Minimum similarity score
            return_metadata: Whether to return metadata

        Returns:
            Best matching goal triple or None
        """
        logging.info(f"Searching for goal: '{description}'")

        collection_info = self.qdrant_client.get_collection(self.collection_name)
        if collection_info.points_count == 0:
            logging.warning(f"Collection '{self.collection_name}' is empty.")
            return None

        # Generate embedding for description
        description_embedding = self.embedding_model.encode([description])[0]

        # Search for matching goals using object vector (goal description is the object)
        search_results = self.qdrant_client.search(
            collection_name=self.collection_name,
            query_vector=("object", description_embedding.tolist()),
            limit=10,
            score_threshold=similarity_threshold,
            with_payload=True,
            with_vectors=False
        )

        # Filter for has_goal predicates and find best match
        best_match = None
        best_score = 0

        for hit in search_results:
            payload = hit.payload
            if payload and payload.get("relationship") == "has_goal":
                if hit.score > best_score:
                    best_score = hit.score
                    triple = (payload.get("subject"), payload.get("relationship"), payload.get("object"))
                    if return_metadata:
                        metadata = payload.get("metadata", {})
                        metadata['confidence'] = hit.score
                        best_match = (triple, metadata)
                    else:
                        best_match = triple

        if best_match:
            logging.info(f"Found goal matching '{description}' with score {best_score:.3f}")
            return best_match

        logging.info(f"No goal found matching '{description}'")
        return None

    def update_goal_metadata(self, goal_description: str, updated_metadata: Dict[str, Any]) -> bool:
        """
        Update metadata for a goal by finding it via semantic search and updating its payload.

        Args:
            goal_description: Description of the goal to update
            updated_metadata: New metadata values to merge

        Returns:
            True if updated successfully, False otherwise
        """
        logging.info(f"Updating goal metadata for: '{goal_description}'")

        # Find the goal
        goal_result = self.query_goal_by_description(goal_description, similarity_threshold=0.5, return_metadata=True)
        if not goal_result:
            logging.warning(f"Could not find goal: '{goal_description}'")
            return False

        triple, existing_metadata = goal_result

        # Merge metadata
        merged_metadata = {**existing_metadata, **updated_metadata}
        merged_metadata['status_updated_timestamp'] = time.time()

        # Generate the point ID (same as in add_triples)
        import hashlib
        subject, relationship, obj = triple
        triple_string = f"{subject}-{relationship}-{obj}"
        point_id = hashlib.md5(triple_string.encode()).hexdigest()

        # Update the point's payload
        self.qdrant_client.set_payload(
            collection_name=self.collection_name,
            payload={"metadata": merged_metadata},
            points=[point_id]
        )

        logging.info(f"Successfully updated goal: '{goal_description}'")
        return True

def main():
    # Set up debug logging for testing
    log_file = f"vector_knowledge_graph_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    setup_logging(debug_mode=True, log_file=log_file)
    logging.info("Starting VectorKnowledgeGraph test run")
    
    # Test basic triple operations
    logging.info("Testing basic triple operations...")
    
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
        logging.info("Adding test triples to knowledge graph")
        kgraph.add_triples(test_triples, test_metadata)
        
        # Test querying by noun with multiple hops
        logging.info("Testing query by noun 'cat' with depth=2")
        results = kgraph.build_graph_from_noun("cat", similarity_threshold=0.7, depth=2)
        logging.info("Found triples:")
        for triple in results:
            logging.info(triple)
        
        # Test querying by subject-relationship with complex relationships
        logging.info("Testing query by subject-relationship ('cat', 'hunts')")
        results = kgraph.build_graph_from_subject_relationship(("cat", "hunts"), similarity_threshold=0.7)
        logging.info("Found triples:")
        for triple in results:
            logging.info(triple)
        
        # Test metadata query with multiple criteria
        logging.info("Testing metadata query (source='biology_textbook')")
        results = kgraph.query_triples_from_metadata({"source": "biology_textbook"})
        logging.info("Found triples:")
        for triple, metadata in results:
            logging.info(f"{triple} - Metadata: {metadata}")
        
        # Test visualization with multiple starting points
        logging.info("Testing visualization with multiple starting points...")
        kgraph.visualize_graph_from_nouns(["cat", "bird", "dog"], similarity_threshold=0.7, depth=2)
    
    finally:
        logging.info("Test run completed")
        # Clean up test data
        if hasattr(kgraph, 'qdrant_client'):
            kgraph.qdrant_client.close()
        if os.path.exists("Test_GraphStoreMemory"):
            shutil.rmtree("Test_GraphStoreMemory")

if __name__ == "__main__":
    main()




