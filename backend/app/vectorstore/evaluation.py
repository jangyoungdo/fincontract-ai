from __future__ import annotations

from app.services.retrieval import HybridRetriever


def evaluate(cases: list[dict], top_k: int, embedding_provider: str | None = None) -> dict:
    """Calculate hit rate and reciprocal rank from expected evidence identifiers."""
    retriever = HybridRetriever(embedding_provider)
    hits = 0
    reciprocal_rank = 0.0
    details = []
    for case in cases:
        results = retriever.search(case["query"], top_k=top_k)
        ranked_ids = [result["evidence_id"] for result in results]
        expected = set(case["expected_evidence_ids"])
        rank = next((index for index, item in enumerate(ranked_ids, 1) if item in expected), None)
        hits += int(rank is not None)
        reciprocal_rank += 1.0 / rank if rank else 0.0
        details.append({"case_id": case["case_id"], "rank": rank, "top_ids": ranked_ids})
    count = len(cases)
    return {
        "case_count": count,
        f"hit@{top_k}": round(hits / count, 6) if count else 0.0,
        "mrr": round(reciprocal_rank / count, 6) if count else 0.0,
        "details": details,
    }
