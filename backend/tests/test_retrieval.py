from app.services.retrieval import HybridRetriever
from app.vectorstore.client import ensure_collections, get_chroma_client
from app.vectorstore.embedding import embed


def test_hybrid_retrieval_ranks_relevant_synthetic_record() -> None:
    ensure_collections()
    collection = get_chroma_client().get_collection("clause_patterns")
    collection.upsert(
        ids=["test:unilateral", "test:jurisdiction"],
        documents=[
            "사업자가 서비스 내용을 일방적으로 변경하는 조항",
            "사업자 소재지 법원을 전속 관할로 정하는 조항",
        ],
        embeddings=[embed("사업자가 서비스 내용을 일방적으로 변경하는 조항"), embed("사업자 소재지 법원을 전속 관할로 정하는 조항")],
        metadatas=[
            {"title":"일방 변경", "authority":"synthetic", "source_url":"https://example.invalid/a", "review_status":"synthetic", "manifest_version":"test", "authority_weight":0.1},
            {"title":"전속 관할", "authority":"synthetic", "source_url":"https://example.invalid/b", "review_status":"synthetic", "manifest_version":"test", "authority_weight":0.1},
        ],
    )
    results = HybridRetriever().search("서비스를 일방적으로 변경", top_k=2)
    assert results[0]["evidence_id"] == "test:unilateral"
