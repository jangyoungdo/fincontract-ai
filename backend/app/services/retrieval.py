from __future__ import annotations

import math
from collections import Counter
from typing import Any

from app.vectorstore.client import COLLECTION_NAMES, get_chroma_client
from app.vectorstore.embedding import provider_name, query_embedding, tokenize


class HybridRetriever:
    """Merge deterministic vector, lexical, and source-authority relevance signals."""

    def __init__(self, embedding_provider: str | None = None) -> None:
        """Pin one provider for both query vectors and indexed collection metadata."""
        self.embedding_provider = provider_name(embedding_provider)

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Search all legal collections and return unique, ranked evidence records."""
        client = get_chroma_client()
        candidates = []
        query_tokens = tokenize(query)
        for collection_name in COLLECTION_NAMES:
            collection = client.get_or_create_collection(collection_name)
            if collection.count() == 0:
                continue
            if (collection.metadata or {}).get("embedding_provider") != self.embedding_provider:
                raise ValueError(
                    f"Collection {collection_name} embedding provider does not match "
                    f"{self.embedding_provider}"
                )
            # Retrieve a wider vector candidate pool before lexical reranking.
            # Limiting this stage to top_k prevents a strong exact-text match from
            # ever reaching BM25 when the semantic model ranks it slightly lower.
            candidate_count = min(max(top_k * 4, 20), collection.count())
            result = collection.query(
                n_results=candidate_count,
                include=["documents", "metadatas", "distances"],
                **query_embedding(query, self.embedding_provider),
            )
            documents = result["documents"][0]
            metadatas = result["metadatas"][0]
            distances = result["distances"][0]
            ids = result["ids"][0]
            lexical_scores = self._bm25(query_tokens, documents)
            for item_id, document, metadata, distance, lexical in zip(
                ids, documents, metadatas, distances, lexical_scores
            ):
                vector_score = max(0.0, 1.0 - float(distance))
                authority_weight = float(metadata.get("authority_weight", 0.5))
                # Fixed weights keep retrieval reproducible across experiment runs.
                score = 0.45 * vector_score + 0.4 * lexical + 0.15 * authority_weight
                candidates.append(
                    {
                        "evidence_id": item_id,
                        "collection": collection_name,
                        "title": metadata["title"],
                        "authority": metadata["authority"],
                        "source_url": metadata["source_url"],
                        "quoted_excerpt": document,
                        "status": metadata["review_status"],
                        "relevance_score": round(score, 6),
                        "manifest_version": metadata["manifest_version"],
                    }
                )
        unique = {item["evidence_id"]: item for item in candidates}
        return sorted(unique.values(), key=lambda item: item["relevance_score"], reverse=True)[:top_k]

    @staticmethod
    def _bm25(query_tokens: list[str], documents: list[str]) -> list[float]:
        tokenized = [tokenize(document) for document in documents]
        if not query_tokens or not tokenized:
            return [0.0] * len(documents)
        average_length = sum(len(tokens) for tokens in tokenized) / len(tokenized) or 1.0
        scores = []
        for tokens in tokenized:
            frequencies = Counter(tokens)
            score = 0.0
            for query_token in set(query_tokens):
                containing = sum(query_token in doc_tokens for doc_tokens in tokenized)
                inverse = math.log(1 + (len(tokenized) - containing + 0.5) / (containing + 0.5))
                frequency = frequencies[query_token]
                denominator = frequency + 1.5 * (1 - 0.75 + 0.75 * len(tokens) / average_length)
                score += inverse * (frequency * 2.5 / denominator if denominator else 0.0)
            scores.append(score)
        maximum = max(scores) or 1.0
        return [score / maximum for score in scores]
