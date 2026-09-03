from app.services.deterministic_summary import (
    MAX_SENTENCE_LENGTH,
    document_summary,
    enrich_summaries,
    finding_summary,
)


def finding(name: str, strength: str, source: str = "채권자는 5% 수수료를 부과한다.") -> dict:
    return {
        "finding_id": name,
        "source": {"masked_text": source, "match_span": [0, len(source)]},
        "rule_signal": {
            "rule_name": name,
            "category": name,
            "signal_strength": strength,
        },
    }


def test_finding_summary_uses_document_facts_and_stays_bounded() -> None:
    sentence = finding_summary(finding("과도한 수수료 또는 가산금리", "high"))
    assert "채권자" in sentence
    assert "5%" in sentence
    assert "과도한 수수료 또는 가산금리" in sentence
    assert len(sentence) <= MAX_SENTENCE_LENGTH
    assert all(term not in sentence for term in ("위법", "무효", "불공정 확정"))


def test_finding_summary_falls_back_to_reviewed_rule_explanation() -> None:
    item = finding("조건 변경", "medium", "일반 문장")
    item["source"]["match_span"] = [0, 0]
    item["rule_signal"]["matched_excerpt"] = ""
    item["explanation"] = {"why_flagged": "사업자가 고객 동의 없이 조건을 바꿀 수 있습니다."}
    assert "사업자가 고객 동의 없이 조건을 바꿀 수 있습니다" in finding_summary(item)


def test_document_summary_orders_strength_then_count_then_document_order() -> None:
    findings = [
        finding("중간 선행", "medium"),
        finding("높음", "high"),
        finding("중간 반복", "medium"),
        finding("중간 반복", "medium"),
        finding("낮음", "low"),
    ]
    summary = document_summary(findings, [])
    assert summary["top_categories"] == ["높음", "중간 반복", "중간 선행"]
    assert "외 1개 유형" in summary["headline"]


def test_summary_enrichment_is_deterministic_and_marks_schema_version() -> None:
    result = {"findings": [finding("금리 변경", "medium")], "candidate_findings": []}
    first = enrich_summaries(result)
    second = enrich_summaries(result)
    assert first == second
    assert first["result_schema_version"] == "3.1"
    assert first["findings"][0]["summary_sentence"]


def test_no_signal_summary_preserves_legal_safety_caveat() -> None:
    headline = document_summary([], [])["headline"]
    assert "위험 신호가 확인되지 않았습니다" in headline
    assert "안전성이나 적법성을 보장하지는 않습니다" in headline
