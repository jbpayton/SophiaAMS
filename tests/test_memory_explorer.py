#!/usr/bin/env python3
"""Quick manual test for MemoryExplorer.

Run:  python tests/test_memory_explorer.py

This avoids pytest and behaves like the other demo scripts in the repo.
"""

import numpy as np
import sys
import os
import logging
import time
from datetime import datetime
import argparse

# Add project root to path so we can import local modules when executed directly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from MemoryExplorer import MemoryExplorer
from VectorKnowledgeGraph import VectorKnowledgeGraph
from DocumentProcessor import WebPageSource, DocumentProcessor
from AssociativeSemanticMemory import AssociativeSemanticMemory

# Logging helper
from utils import setup_logging


class DummyEmbedder:
    """Extremely lightweight embedder that maps any sentence to a small vector.

    Each call increments a counter so vectors are distinct enough for clustering.
    """

    def __init__(self):
        self._counter = 0

    def encode(self, sentences):
        if isinstance(sentences, str):
            sentences = [sentences]
        embeds = []
        for _ in sentences:
            embeds.append(np.array([float(self._counter), 0.0, 0.0]))
            self._counter += 1
        return np.vstack(embeds)


class DummyVectorKnowledgeGraph(VectorKnowledgeGraph):
    """Stub graph that fulfils the API without touching Qdrant or HF models."""

    def __init__(self):
        # bypass heavy superclass init
        self.embedding_model = DummyEmbedder()

    _triples = [
        ("Alice", "likes", "Bob"),
        ("Bob", "likes", "Cats"),
        ("Alice", "owns", "Cats"),
        ("Eve", "hates", "Bob"),
        ("Mallory", "knows", "Eve"),
        ("Alice", "likes", "Dogs"),
    ]

    # Minimal implementations of methods used by MemoryExplorer -----------------
    def get_all_triples(self):
        return [{"subject": s, "object": o} for s, _, o in self._triples]

    def find_triples_by_text_similarity(self, query_text, return_metadata=True, limit=75, similarity_threshold=0.2):
        results = []
        for idx, triple in enumerate(self._triples):
            meta = {"confidence": 1.0 - idx * 0.1}
            results.append((triple, meta) if return_metadata else triple)
        return results


WIKI_URLS = [
    # Pop-culture & tech
    "https://en.wikipedia.org/wiki/Vocaloid",
    "https://en.wikipedia.org/wiki/Hatsune_Miku",
    # Science / engineering
    "https://en.wikipedia.org/wiki/CRISPR",
    "https://en.wikipedia.org/wiki/Photosynthesis",
    "https://en.wikipedia.org/wiki/LIGO",
    "https://en.wikipedia.org/wiki/Quantum_computing",
]


def main():
    # ---------------- CLI ----------------
    parser = argparse.ArgumentParser(description="MemoryExplorer demo & analytics")
    parser.add_argument("--path", default="WikiGraph", help="Directory for the Qdrant graph store")
    parser.add_argument("--refresh", action="store_true", help="Force re-ingestion even if the store exists")
    args = parser.parse_args()

    # ----------------------------------------------------
    # Logging setup
    # ----------------------------------------------------
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = f"test-output/memory_explorer_{timestamp}.log"
    os.makedirs("test-output", exist_ok=True)
    setup_logging(debug_mode=False, log_file=log_file)

    logging.info("Starting MemoryExplorer demo script")

    # If environment lacks OpenAI creds etc., fall back to dummy mode
    use_live_ingest = os.getenv("LLM_API_KEY") is not None

    if use_live_ingest:
        print("\n[+] Live ingestion of Wikipedia pages …\n")
        kgraph = VectorKnowledgeGraph(path=args.path)
        memory = AssociativeSemanticMemory(kgraph)
        processor = DocumentProcessor(memory)

        graph_exists = os.path.exists(os.path.join(args.path, "qdrant_data"))

        if not graph_exists or args.refresh:
            action = "Rebuilding" if args.refresh else "Building"
            logging.info(f"{action} knowledge graph at '{args.path}' by ingesting pages …")

            total_start = time.time()
            chunk_logs = []
            for i, url in enumerate(WIKI_URLS, 1):
                logging.info(f"Processing URL {i}/{len(WIKI_URLS)}: {url}")
                url_start = time.time()
                try:
                    res = processor.process_document(WebPageSource(url))
                    if res.get("success"):
                        logging.info(
                            f"  -> processed {res.get('processed_chunks', 0)}/{res.get('total_chunks', 0)} chunks"
                        )
                        if res.get("chunk_log"):
                            chunk_logs.append(res["chunk_log"])
                            logging.info(f"  chunk log: {res['chunk_log']}")
                    else:
                        logging.warning(f"  Processing failed: {res.get('error')}")
                except Exception as e:
                    logging.error(f"Error processing {url}: {e}")
                logging.info(f"   URL done in {time.time() - url_start:.2f}s")

            logging.info(
                f"Finished ingesting {len(WIKI_URLS)} pages in {time.time() - total_start:.2f}s"
            )

            if chunk_logs:
                logging.info("Chunk logs generated:")
                for p in chunk_logs:
                    logging.info(f"  {p}")
        else:
            logging.info(f"Opening existing knowledge graph at '{args.path}' (no ingestion)")

        explorer = memory.get_explorer()
    else:
        print("[!] LLM_API_KEY missing – running in dummy mode")
        graph = DummyVectorKnowledgeGraph()
        explorer = MemoryExplorer(graph)

    # Show what we know (top entities)
    print("\nTop entities:")
    for ent, cnt in explorer.top_entities(15):
        print(f"  {ent}: {cnt}")

    # Cluster the whole graph
    print("\nHigh-level clusters (no query):")
    clusters = explorer.cluster_all_triples(per_cluster=4)
    for cl in clusters:
        print(f"Cluster {cl['cluster_id']} (size {cl['size']}):")
        for (t, _meta) in cl['samples']:
            print(f"  – {t[0]} {t[1]} {t[2]}")

    # Knowledge overview using topics & central entities
    overview = explorer.knowledge_overview()
    print("\nTop topics:")
    for top in overview["topics"]:
        print(f"  Topic '{top['topic']}' ({top['size']} triples)")
        for (t, _meta) in top["samples"]:
            print(f"    – {t[0]} {t[1]} {t[2]}")

    print("\nCentral entities:")
    for ent in overview["entities"]:
        print(f"  {ent['entity']} (centrality {ent['centrality']:.3f})")
        for (t, _meta) in ent["samples"]:
            print(f"    – {t[0]} {t[1]} {t[2]}")

    # Quick sample query clustering (works in dummy mode)
    print("\nClustering query 'Alice likes':")
    clusters = explorer.cluster_for_query("Alice likes", per_cluster=2)
    for cl in clusters:
        print(f"  Query Cluster {cl['cluster_id']} (size {cl['size']}):")
        for (t, _meta) in cl['samples']:
            print(f"    – {t[0]} {t[1]} {t[2]}")

    # Topic summaries
    print("\nTopic summaries:\n")
    print(explorer.topics_with_summaries(use_llm=use_live_ingest))

    # Grouped topic summaries to merge redundancies
    print("\nGrouped topic summaries:\n")
    print(explorer.grouped_topic_summaries(use_llm=use_live_ingest, concise=True))


if __name__ == "__main__":
    main() 