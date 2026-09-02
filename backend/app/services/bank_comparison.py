"""Rule-based qualitative comparison of an analyzed document against peer banks.

Reuses the same deterministic RuleEngine used for the primary analysis, run
against a verified peer-bank corpus (Chroma collection "bank_products"), so no
new pattern-matching logic or legal conclusions are introduced here.
"""

from __future__ import annotations

from typing import Any

from app.rules.rule_engine import RuleEngine
from app.vectorstore.client import get_chroma_client

MIN_PEER_BANKS = 2
COLLECTION_NAME = "bank_products"


def has_peer_corpus_data() -> bool:
    """Return whether the peer bank corpus collection has any ingested data."""
    client = get_chroma_client()
    collection = client.get_or_create_collection(COLLECTION_NAME)
    return collection.count() > 0


def compare_to_peers(
    findings: list[dict[str, Any]], product_type: str, bank_name: str | None
) -> dict[str, Any]:
    """Compare rule signals already present in `findings` to peer clauses."""
    client = get_chroma_client()
    collection = client.get_or_create_collection(COLLECTION_NAME)
    peers = collection.get(where={"product_type": product_type}, include=["documents", "metadatas"])

    by_bank: dict[str, list[str]] = {}
    manifest_versions: set[str] = set()
    for peer_text, metadata in zip(peers["documents"], peers["metadatas"]):
        peer_bank = metadata.get("bank_name")
        if not peer_bank or peer_bank == bank_name:
            continue
        by_bank.setdefault(peer_bank, []).append(peer_text)
        version = metadata.get("manifest_version")
        if version:
            manifest_versions.add(version)

    peer_bank_count = len(by_bank)
    corpus_version = ",".join(sorted(manifest_versions)) or "not_available"

    if peer_bank_count < MIN_PEER_BANKS:
        return {
            "comparison_status": "insufficient_peer_data",
            "product_type": product_type,
            "bank_name": bank_name,
            "peer_bank_count": peer_bank_count,
            "corpus_version": corpus_version,
            "generated_note": "동종 상품을 등록한 은행이 아직 충분하지 않아 비교를 제공하지 않습니다.",
            "pros": [],
            "cons": [],
            "neutral": [],
        }

    our_matched_rule_ids = {
        finding["rule_signal"]["rule_id"]
        for finding in findings
        if finding.get("rule_signal", {}).get("rule_id")
    }

    engine = RuleEngine()
    pros: list[dict[str, Any]] = []
    cons: list[dict[str, Any]] = []
    neutral: list[dict[str, Any]] = []

    for rule in engine.ruleset["rules"]:
        rule_id = rule["id"]
        rule_name = rule["name"]
        flagged_banks = {
            peer_bank
            for peer_bank, texts in by_bank.items()
            if any(engine.screen(text, rule_ids=[rule_id]) for text in texts)
        }
        peer_match_rate = round(len(flagged_banks) / peer_bank_count, 4)
        our_signal = rule_id in our_matched_rule_ids
        item = {
            "rule_id": rule_id,
            "rule_name": rule_name,
            "our_signal": our_signal,
            "peer_match_rate": peer_match_rate,
            "peer_bank_count": peer_bank_count,
            "explanation": "",
        }

        if our_signal and peer_match_rate < 0.5:
            item["explanation"] = (
                f"'{rule_name}' 관련 조항이 동종 은행 {peer_bank_count}곳 중 {len(flagged_banks)}곳에만 있습니다. "
                "본 상품에는 이 조항이 있어 상대적으로 불리할 수 있습니다."
            )
            cons.append(item)
        elif not our_signal and peer_match_rate >= 0.5:
            item["explanation"] = (
                f"'{rule_name}' 관련 조항이 동종 은행 {peer_bank_count}곳 중 {len(flagged_banks)}곳에 있습니다. "
                "본 상품에는 이 조항이 없어 상대적으로 유리할 수 있습니다."
            )
            pros.append(item)
        else:
            item["explanation"] = f"'{rule_name}' 관련 조항 여부가 동종 상품과 비슷한 수준입니다."
            neutral.append(item)

    pros.sort(key=lambda entry: entry["peer_match_rate"], reverse=True)
    cons.sort(key=lambda entry: entry["peer_match_rate"])

    return {
        "comparison_status": "ready",
        "product_type": product_type,
        "bank_name": bank_name,
        "peer_bank_count": peer_bank_count,
        "corpus_version": corpus_version,
        "generated_note": "규칙 기반 정성 비교이며 법률 자문이 아닙니다.",
        "pros": pros,
        "cons": cons,
        "neutral": neutral,
    }
