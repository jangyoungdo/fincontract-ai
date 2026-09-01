from app.prototype.pii import mask_pii
from app.services.candidate_finder import CandidateFinder
from app.services.clause_segmenter import segment_clauses
from app.services.analysis_pipeline import DocumentAnalysisPipeline


def test_contract_subject_text_is_not_masked_as_a_name() -> None:
    source = "채무자는 대출 실행일로부터 상환하고 통지 수령 여부와 이의 제기 여부를 확인한다."
    result = mask_pii(source)
    assert result.passed
    assert result.replacement_count == 0
    assert result.masked_text == source


def test_explicit_and_complete_identity_contexts_are_masked() -> None:
    result = mask_pii("성명: 홍길동, 계약자는 김철수이다.")
    assert result.passed
    assert "홍길동" not in result.masked_text
    assert "김철수" not in result.masked_text


def test_article_segmenter_preserves_numbered_items_in_one_article() -> None:
    source = "제8조 기한의 이익 상실\n1) 신용상태 악화\n2) 내부지침 위반\n채무자는 즉시 전액 상환한다.\n제9조 다음 조항"
    clauses = segment_clauses(source)
    assert [clause.label for clause in clauses] == ["제8조", "제9조"]
    assert [item.label for item in clauses[0].subclauses] == ["1)", "2)"]
    assert "즉시 전액 상환" in clauses[0].text


def test_candidate_finder_requires_two_taxonomy_terms() -> None:
    assert CandidateFinder().suggest("고객은 수수료를 부담한다.") == []


def test_candidate_finder_returns_a_separate_taxonomy_candidate() -> None:
    candidates = CandidateFinder().suggest("고객의 우대금리를 소급 취소할 수 있습니다.")
    assert candidates[0]["category"] == "retroactive_disadvantage"
    assert candidates[0]["status"] == "deterministic_rule_unmapped_candidate"


def test_pipeline_returns_candidates_separately_and_requires_review(monkeypatch) -> None:
    pipeline = DocumentAnalysisPipeline()
    monkeypatch.setattr(pipeline, "_retrieve_evidence", lambda _: [])
    result = pipeline.run("제1조 고객의 우대금리 혜택을 과거분까지 없앤다.", "A")
    assert result["findings"] == []
    assert result["candidate_findings"][0]["category"] == "retroactive_disadvantage"
    assert result["disposition"] == "needs_review"
