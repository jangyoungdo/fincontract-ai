from app.services.bank_comparison import compare_to_peers, has_peer_corpus_data
from app.vectorstore.client import ensure_collections, get_chroma_client
from app.vectorstore.embedding import embed

PRO_TEXT = "은행이 필요하다고 인정하는 경우 서비스 내용을 일방적으로 변경할 수 있다."
CON_TEXT = "소송은 은행 본점 소재지 관할 법원에서만 진행한다."


def _seed_peer(collection_id_prefix: str, product_type: str, entries: list[tuple[str, str]]) -> None:
    """Upsert (bank_name, clause_text) peer chunks into the bank_products collection."""
    ensure_collections()
    collection = get_chroma_client().get_collection("bank_products")
    ids = [f"{collection_id_prefix}:{index}" for index in range(len(entries))]
    documents = [text for _bank, text in entries]
    metadatas = [
        {"bank_name": bank, "product_type": product_type, "manifest_version": "test-bank-corpus-v0"}
        for bank, _text in entries
    ]
    collection.upsert(
        ids=ids,
        documents=documents,
        embeddings=[embed(text) for text in documents],
        metadatas=metadatas,
    )


def test_has_peer_corpus_data_reflects_ingested_state() -> None:
    ensure_collections()
    _seed_peer("presence-check", "presence_check_product", [("은행A", PRO_TEXT)])
    assert has_peer_corpus_data() is True


def test_insufficient_peer_data_when_fewer_than_two_peer_banks() -> None:
    _seed_peer("single-peer", "single_peer_product", [("은행A", PRO_TEXT)])
    result = compare_to_peers([], "single_peer_product", "우리은행")
    assert result["comparison_status"] == "insufficient_peer_data"
    assert result["peer_bank_count"] == 1
    assert result["pros"] == [] and result["cons"] == []


def test_compare_to_peers_classifies_pro_and_con_against_three_peer_banks() -> None:
    _seed_peer(
        "three-peer",
        "three_peer_product",
        [("은행A", PRO_TEXT), ("은행B", PRO_TEXT), ("은행C", CON_TEXT)],
    )
    our_findings = [{"rule_signal": {"rule_id": "R08_EXCLUSIVE_JURISDICTION"}}]

    result = compare_to_peers(our_findings, "three_peer_product", "우리은행")

    assert result["comparison_status"] == "ready"
    assert result["peer_bank_count"] == 3

    pro_ids = {item["rule_id"] for item in result["pros"]}
    con_ids = {item["rule_id"] for item in result["cons"]}
    assert "R04_UNILATERAL_CHANGE" in pro_ids
    assert "R08_EXCLUSIVE_JURISDICTION" in con_ids

    pro_item = next(item for item in result["pros"] if item["rule_id"] == "R04_UNILATERAL_CHANGE")
    con_item = next(item for item in result["cons"] if item["rule_id"] == "R08_EXCLUSIVE_JURISDICTION")
    assert pro_item["our_signal"] is False
    assert abs(pro_item["peer_match_rate"] - 2 / 3) < 1e-3
    assert con_item["our_signal"] is True
    assert abs(con_item["peer_match_rate"] - 1 / 3) < 1e-3


def test_compare_to_peers_excludes_own_bank_from_peer_set() -> None:
    _seed_peer(
        "self-exclusion",
        "self_exclusion_product",
        [("우리은행", PRO_TEXT), ("은행B", PRO_TEXT)],
    )
    result = compare_to_peers([], "self_exclusion_product", "우리은행")
    assert result["comparison_status"] == "insufficient_peer_data"
    assert result["peer_bank_count"] == 1
