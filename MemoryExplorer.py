class MemoryExplorer:
    """Light-weight analytics helper for VectorKnowledgeGraph.

    This helper purposefully sits *outside* the normal ingest / retrieval
    flow exposed by ``AssociativeSemanticMemory`` so we can run exploratory
    queries ("what do you know about …?", clustering, degrees, centrality)
    without bloating the core classes.
    """

    def __init__(self, kgraph):
        from VectorKnowledgeGraph import VectorKnowledgeGraph  # local import to avoid circular
        if not isinstance(kgraph, VectorKnowledgeGraph):
            raise TypeError("MemoryExplorer expects a VectorKnowledgeGraph instance")
        self.kgraph = kgraph
        # re-use the same embedding model so we do not allocate twice
        self._embed = self.kgraph.embedding_model.encode

    # ---------------------------------------------------------------------
    # Simple degree-based ranking
    # ---------------------------------------------------------------------
    def top_entities(self, k: int = 25):
        """Return the *k* most connected entities (subject or object).

        Connectivity is measured as the number of triples an entity
        participates in (in- or out-degree).
        """
        triples = self.kgraph.get_all_triples()
        if not triples:
            return []

        from collections import Counter

        counts = Counter()
        for t in triples:
            subj = t.get("subject") or t.get("subj")
            obj = t.get("object")
            if subj:
                counts[subj] += 1
            if obj:
                counts[obj] += 1

        return counts.most_common(k)

    # ------------------------------------------------------------------
    # Clustering similar triples for a natural-language query
    # ------------------------------------------------------------------
    def cluster_for_query(
        self,
        text: str,
        n_clusters: int = 5,
        per_cluster: int = 3,
        search_limit: int = 75,
    ):
        """Cluster triples that are semantically related to *text*.

        1. Retrieve up to *search_limit* triples using the graph's built-in
           semantic search.
        2. Embed the full triple content and run k-means clustering (fallback
           to <= n_clusters if not enough samples).
        3. Return a list of clusters, each with up to *per_cluster* sample
           triples (highest confidence first).
        """
        # Step 1 – gather candidate triples
        candidates = self.kgraph.find_triples_by_text_similarity(
            query_text=text,
            return_metadata=True,
            limit=search_limit,
            similarity_threshold=0.2,
        )
        if not candidates:
            return []

        # Build embeddings for clustering
        contents = [f"Subject: {s} | Rel: {r} | Obj: {o}" for (s, r, o), _ in candidates]
        vectors = self._embed(contents)

        # -------- Density-based clustering (no preset k) --------
        try:
            import hdbscan  # type: ignore

            # min_cluster_size heuristically set to 2% of samples but at least 2
            min_cs = max(2, max(1, len(vectors) // 50))
            clusterer = hdbscan.HDBSCAN(min_cluster_size=min_cs, metric="euclidean")
            labels = clusterer.fit_predict(vectors)
        except Exception:
            # Fallback to sklearn's DBSCAN if hdbscan missing
            try:
                from sklearn.cluster import DBSCAN

                clusterer = DBSCAN(eps=0.8, min_samples=2, metric="euclidean")
                labels = clusterer.fit_predict(vectors)
            except Exception as e:
                import logging

                logging.warning(
                    f"Density clustering unavailable ({e}); placing everything in one cluster"
                )
                labels = [0] * len(vectors)

        # Remap noise label (-1) to its own bucket id so user can still inspect
        unique_labels = sorted(set(labels))
        if unique_labels and unique_labels[0] == -1:
            # shift all non-noise labels by 1 so noise becomes 0
            labels = [lbl + 1 for lbl in labels]

        # Bucket triples per cluster label
        buckets: dict[int, list] = {}
        for (triple, meta), lbl in zip(candidates, labels):
            buckets.setdefault(int(lbl), []).append((triple, meta))

        # Within each cluster sort by confidence and sample
        clustered = []
        for cid, items in buckets.items():
            items.sort(key=lambda x: x[1].get("confidence", 0), reverse=True)
            sample = items[:per_cluster]
            clustered.append(
                {
                    "cluster_id": cid,
                    "size": len(items),
                    "samples": sample,
                }
            )

        # Sort clusters by size descending
        clustered.sort(key=lambda c: c["size"], reverse=True)
        return clustered

    # ------------------------------------------------------------------
    # Convenience pretty-printer (optional)
    # ------------------------------------------------------------------
    def describe_clusters(self, clusters):
        """Return a human-readable multiline string for *clusters*."""
        lines = []
        for cl in clusters:
            lines.append(f"Cluster {cl['cluster_id']} (size {cl['size']}):")
            for (t, _meta) in cl["samples"]:
                lines.append(f"  – {t[0]} {t[1]} {t[2]}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Global clustering over the entire graph
    # ------------------------------------------------------------------
    def cluster_all_triples(
        self,
        n_clusters: int = 8,
        per_cluster: int = 5,
        sample_limit: int = 500,
    ):
        """Cluster *all* (or up to *sample_limit*) triples in the graph.

        This answers the question "What do we know about, in aggregate?"
        without requiring a user query.
        """
        triples_meta = self.kgraph.get_all_triples()
        if not triples_meta:
            return []

        # Limit for performance
        triples_meta = triples_meta[:sample_limit]

        triples = []
        for item in triples_meta:
            # item might be dict or tuple; normalise
            if isinstance(item, dict):
                triple = (
                    item.get("subject", ""),
                    item.get("predicate", item.get("relationship", "")),
                    item.get("object", ""),
                )
                meta = item.get("metadata", {})
            else:
                triple = tuple(item)
                meta = {}
            triples.append((triple, meta))

        contents = [f"{s} {r} {o}" for (s, r, o), _ in triples]
        vectors = self._embed(contents)

        # Density-based clustering to avoid choosing k
        try:
            import hdbscan  # type: ignore

            min_cs = max(2, max(1, len(vectors) // 50))
            clusterer = hdbscan.HDBSCAN(min_cluster_size=min_cs, metric="euclidean")
            labels = clusterer.fit_predict(vectors)
        except Exception:
            try:
                from sklearn.cluster import DBSCAN

                clusterer = DBSCAN(eps=0.8, min_samples=2, metric="euclidean")
                labels = clusterer.fit_predict(vectors)
            except Exception as e:
                import logging

                logging.warning(
                    f"Density clustering unavailable ({e}); all triples grouped together"
                )
                labels = [0] * len(vectors)

        # Remap noise label (-1)
        if -1 in labels:
            labels = [lbl + 1 if lbl != -1 else 0 for lbl in labels]

        buckets: dict[int, list] = {}
        for (triple, meta), lbl in zip(triples, labels):
            buckets.setdefault(int(lbl), []).append((triple, meta))

        clustered = []
        for cid, items in buckets.items():
            # we don't have confidence; keep insertion order
            sample = items[:per_cluster]
            clustered.append({"cluster_id": cid, "size": len(items), "samples": sample})

        clustered.sort(key=lambda c: c["size"], reverse=True)
        return clustered

    # ------------------------------------------------------------------
    # High-level "What do we know about?" overview
    # ------------------------------------------------------------------
    def knowledge_overview(
        self,
        top_k_topics: int = 10,
        per_topic_samples: int = 4,
        top_central_entities: int = 10,
        per_entity_samples: int = 4,
    ):
        """Return a structured snapshot of the most prominent themes/entities.

        * Topics: derived from triple metadata["topics"]. We count occurrences
          and surface the *top_k_topics* with sample triples.
        * Central entities: computed from a quick degree-centrality on the
          subject→object graph. We surface *top_central_entities* nodes with
          example triples.
        """
        triples_raw = self.kgraph.get_all_triples()
        if not triples_raw:
            return {"topics": [], "entities": []}

        # ---------------- Topic aggregation ----------------
        from collections import Counter, defaultdict

        topic_counter: Counter[str] = Counter()
        topic_buckets: defaultdict[str, list] = defaultdict(list)

        cleaned = []
        for item in triples_raw:
            if isinstance(item, dict):
                triple = (
                    item.get("subject"),
                    item.get("predicate", item.get("relationship")),
                    item.get("object"),
                )
                meta = item.get("metadata", {})
            else:
                triple = tuple(item)
                meta = {}
            cleaned.append((triple, meta))

            # Count topics
            topics = meta.get("topics", []) if isinstance(meta, dict) else []
            for t in topics:
                if t:
                    topic_counter[t] += 1
                    topic_buckets[t].append((triple, meta))

        top_topics = [t for t, _ in topic_counter.most_common(top_k_topics)]
        topic_clusters = []
        for t in top_topics:
            samples = topic_buckets[t][:per_topic_samples]
            topic_clusters.append(
                {"topic": t, "size": len(topic_buckets[t]), "samples": samples}
            )

        # ---------------- Entity centrality ----------------
        import networkx as nx

        G = nx.DiGraph()
        for (s, _r, o), _m in cleaned:
            if s and o:
                G.add_edge(s, o)
        centrality = nx.degree_centrality(G)
        top_entities = sorted(centrality.items(), key=lambda kv: kv[1], reverse=True)[:top_central_entities]

        entity_clusters = []
        for ent, cent in top_entities:
            ent_samples = []
            for (tri, meta) in cleaned:
                if ent in tri and len(ent_samples) < per_entity_samples:
                    ent_samples.append((tri, meta))
            entity_clusters.append(
                {
                    "entity": ent,
                    "centrality": cent,
                    "samples": ent_samples,
                }
            )

        return {"topics": topic_clusters, "entities": entity_clusters}

    def knowledge_tree_text(
        self,
        max_topics: int = 10,
        per_topic_samples: int = 4,
        llm_summary: bool = False,
        topic_summary: bool = False,
    ) -> str:
        """Return a text representation (ASCII tree) of top topics & facts.

        If *llm_summary* is True and an LLM key is available, append a prose
        summary generated by the model.
        """
        overview = self.knowledge_overview(
            top_k_topics=max_topics, per_topic_samples=per_topic_samples
        )
        lines = []
        for top in overview["topics"]:
            topic_header = f"- {top['topic']}  (n={top['size']})"
            lines.append(topic_header)

            bullet_lines = []
            for (t, _meta) in top["samples"]:
                subj, rel, obj = t
                bullet_lines.append(f"    • {subj} {rel} {obj}")
            lines.extend(bullet_lines)

            # Optional per-topic summary
            if topic_summary and llm_summary:
                summary_text = self._summarize_bullets(top['topic'], bullet_lines)
                if summary_text:
                    lines.append(f"    ↳ {summary_text}")

        tree_text = "\n".join(lines)

        if llm_summary:
            try:
                from openai import OpenAI
                import os

                client = OpenAI(
                    base_url=os.getenv("LLM_API_BASE"), api_key=os.getenv("LLM_API_KEY")
                )
                prompt = (
                    "Below is a bullet list of facts grouped by topics that come from an internal knowledge graph. "
                    "Produce a concise narrative paragraph summarising the main areas of knowledge without repeating the bullets verbatim.\n\n"
                    "BULLETS:\n" + tree_text + "\n\nSUMMARY:"  # noqa
                )
                resp = client.chat.completions.create(
                    model=os.getenv("SUMMARIZATION_MODEL", "gemma-3-4b-it-qat"),
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=512,
                    temperature=0.7,
                )
                summary = resp.choices[0].message.content or ""
                tree_text += "\n\n---\nSUMMARY:\n" + summary.strip()
            except Exception as e:
                import logging

                logging.warning(f"LLM summary unavailable: {e}")

        return tree_text

    # ---------------- internal helper ----------------
    def _summarize_bullets(self, topic: str, bullet_lines: list[str]) -> str | None:
        """Use LLM to summarize bullet lines into one sentence."""
        if not bullet_lines:
            return None

        import os
        from openai import OpenAI

        try:
            client = OpenAI(base_url=os.getenv("LLM_API_BASE"), api_key=os.getenv("LLM_API_KEY"))
            bullets = "\n".join(bullet_lines)
            prompt = (
                f"Summarize the following facts about '{topic}' in one concise sentence.\nFACTS:\n{bullets}\nSUMMARY:"  # noqa
            )
            resp = client.chat.completions.create(
                model=os.getenv("SUMMARIZATION_MODEL", "gemma-3-4b-it-qat"),
                messages=[{"role": "user", "content": prompt}],
                max_tokens=60,
                temperature=0.5,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            import logging

            logging.debug(f"Topic summary LLM call failed: {e}")
            return None

    def topics_with_summaries(
        self,
        top_k_topics: int = 10,
        per_topic_samples: int = 4,
        use_llm: bool = True,
    ) -> str:
        """Return a bullet list of *Topic: summary* pairs.

        If *use_llm* is False or the LLM call fails, falls back to a naive
        bullet concatenation of sample facts.
        """
        overview = self.knowledge_overview(top_k_topics=top_k_topics, per_topic_samples=per_topic_samples)
        lines: list[str] = []
        for top in overview["topics"]:
            bullet_lines = []
            for (t, _m) in top["samples"]:
                subj, rel, obj = t
                bullet_lines.append(f"{subj} {rel} {obj}")

            summary = None
            if use_llm:
                summary = self._summarize_bullets(top["topic"], ["• " + b for b in bullet_lines])
            if not summary:
                # simple fallback: join first bullets
                summary = "; ".join(bullet_lines[:2]) + (" …" if len(bullet_lines) > 2 else "")

            lines.append(f"- {top['topic']}: {summary}")

        return "\n".join(lines)

    def grouped_topic_summaries(
        self,
        top_k_topics: int = 20,
        per_topic_samples: int = 4,
        similarity_threshold: float = 0.8,
        use_llm: bool = True,
        concise: bool = True,
    ) -> str:
        """Return grouped topic summaries based on semantic similarity of topic labels.

        Topics whose label embeddings have cosine similarity >= *similarity_threshold*
        are merged under the same group.  The first topic discovered becomes the
        group header.  Summaries of member topics are concatenated.
        """
        overview = self.knowledge_overview(top_k_topics=top_k_topics, per_topic_samples=per_topic_samples)
        if not overview["topics"]:
            return "(no topics)"

        # Prepare embeddings of topic labels
        topics = [t["topic"] for t in overview["topics"]]
        vectors = self._embed(topics)

        from numpy import dot
        from numpy.linalg import norm

        def cos_sim(a, b):
            return float(dot(a, b) / (norm(a) * norm(b) + 1e-12))

        groups: list[dict] = []  # each dict: {"label": str, "members": [idx]}

        for idx, (topic, vec) in enumerate(zip(topics, vectors)):
            placed = False
            for g in groups:
                ref_vec = g["centroid"]
                if cos_sim(vec, ref_vec) >= similarity_threshold:
                    g["members"].append(idx)
                    # update centroid simple average
                    g["centroid"] = (ref_vec * len(g["members"][:-1]) + vec) / len(g["members"])
                    placed = True
                    break
            if not placed:
                groups.append({"label": topic, "centroid": vec, "members": [idx]})

        # Build summaries
        lines: list[str] = []
        for g in groups:
            member_entries = [overview["topics"][mi] for mi in g["members"]]

            # Aggregate bullet facts from all members
            agg_bullets = []
            for entry in member_entries:
                agg_bullets.extend(
                    [f"{s} {r} {o}" for (s, r, o), _m in entry["samples"]]
                )

            # Derive group summary
            group_summary = None
            if use_llm:
                group_summary = self._summarize_bullets(g["label"], ["• " + b for b in agg_bullets])
            if not group_summary:
                group_summary = "; ".join(agg_bullets[:3]) + (" …" if len(agg_bullets) > 3 else "")

            if concise:
                lines.append(f"* {g['label']}: {group_summary}")
            else:
                lines.append(f"* {g['label']}")
                for entry in member_entries:
                    # Build / fetch individual summary
                    bullet_lines = [
                        f"{s} {r} {o}" for (s, r, o), _m in entry["samples"]
                    ]
                    indiv_summary = None
                    if use_llm:
                        indiv_summary = self._summarize_bullets(entry["topic"], ["• " + b for b in bullet_lines])
                    if not indiv_summary:
                        indiv_summary = "; ".join(bullet_lines[:2]) + (" …" if len(bullet_lines) > 2 else "")
                    lines.append(f"    - {entry['topic']}: {indiv_summary}")

        return "\n".join(lines).strip() 