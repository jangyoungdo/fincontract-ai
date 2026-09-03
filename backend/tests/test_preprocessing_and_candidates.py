from app.prototype.pii import mask_pii, mask_pii_pages
from app.services.analysis_pipeline import DocumentAnalysisPipeline
from app.services.candidate_finder import CandidateFinder
from app.services.clause_segmenter import segment_clauses
from app.services.text_extraction import _remove_repeated_margins


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


def test_page_masking_uses_document_global_replacement_numbers() -> None:
    result, pages = mask_pii_pages(("성명: 홍길동", "성명: 김철수"))
    assert result.replacement_count == 2
    assert "[NAME_1]" in pages[0]
    assert "[NAME_2]" in pages[1]


def test_article_segmenter_preserves_numbered_items_in_one_article() -> None:
    source = "제8조 기한의 이익 상실\n1) 신용상태 악화\n2) 내부지침 위반\n채무자는 즉시 전액 상환한다.\n제9조 다음 조항"
    clauses = segment_clauses(source)
    assert [clause.label for clause in clauses] == ["제8조", "제9조"]
    assert [item.label for item in clauses[0].subclauses] == ["1)", "2)"]
    assert "즉시 전액 상환" in clauses[0].text


def test_candidate_finder_requires_two_taxonomy_terms() -> None:
    assert CandidateFinder().suggest("고객은 수수료를 부담한다.") == []


def test_candidate_finder_returns_a_separate_taxonomy_candidate() -> None:
    class TargetEncoder:
        model_id = "test-e5"
        model_revision = "test-revision"
        backend = "injected"
        def __call__(self, texts: list[str]):
            return [[1.0, 0.0] if "소급" in text or "우대 혜택" in text else [0.0, 1.0] for text in texts]
    finder = CandidateFinder(encoder=TargetEncoder())
    finder.threshold = 0.7
    candidates = finder.suggest("고객의 우대금리를 소급 취소할 수 있습니다.")
    assert candidates[0]["category"] == "retroactive_disadvantage"
    assert candidates[0]["status"] == "semantic_review_candidate"
    assert candidates[0]["model_id"] == "test-e5"


def test_r11_semantic_taxonomy_covers_behavior_silence_and_assignment() -> None:
    class R11Encoder:
        model_id = "test-e5"
        model_revision = "test-revision"
        backend = "injected"

        def __call__(self, texts: list[str]):
            markers = ("계속 상품", "정해진 시간", "지위가 이전", "48시간", "계속 거래", "계속 사용")
            return [[1.0, 0.0] if any(item in text for item in markers) else [0.0, 1.0] for text in texts]

    finder = CandidateFinder(encoder=R11Encoder())
    finder.threshold = 0.7
    finder.margin = 0.04
    samples = (
        "고객이 계속 사용하면 새 조건을 받아들인 것으로 처리한다.",
        "고객이 48시간 동안 응답하지 않으면 변경 조건을 수용한 것으로 확정한다.",
        "지위가 이전된 뒤 계속 거래하면 새 상대방을 승인한 것으로 처리한다.",
    )
    for text in samples:
        candidates = finder.suggest(text)
        assert candidates[0]["category"] == "deemed_consent"


def test_pipeline_returns_candidates_separately_and_requires_review(monkeypatch) -> None:
    pipeline = DocumentAnalysisPipeline()
    monkeypatch.setattr(pipeline, "_retrieve_evidence", lambda _: [])
    monkeypatch.setattr(pipeline.candidates, "suggest", lambda text, excluded: [{
        "candidate_id": "candidate:R12", "category": "retroactive_disadvantage",
        "name": "소급 불이익", "status": "semantic_review_candidate", "confidence": "medium",
        "similarity_score": 0.8, "model_id": "test-e5", "model_revision": "test",
        "matched_prototype_ids": ["R12:p1"], "review_questions": ["소급 적용되는지"],
    }])
    result = pipeline.run("제1조 고객의 우대금리 혜택을 과거분까지 없앤다.", "A")
    assert result["findings"] == []
    assert result["candidate_findings"][0]["category"] == "retroactive_disadvantage"
    assert result["disposition"] == "needs_review"


def test_pipeline_hides_a_candidate_rejected_by_private_rag_without_new_public_fields(
    monkeypatch,
) -> None:
    pipeline = DocumentAnalysisPipeline()
    monkeypatch.setattr(pipeline, "_retrieve_evidence", lambda _: [])
    monkeypatch.setattr(
        pipeline.candidates,
        "suggest",
        lambda text, excluded: [{
            "candidate_id": "candidate:R04_UNILATERAL_CHANGE",
            "category": "unilateral_change",
            "name": "일방 변경",
            "status": "semantic_review_candidate",
            "confidence": "medium",
            "similarity_score": 0.8,
            "model_id": "test-e5",
            "model_revision": "test",
            "matched_prototype_ids": ["R04:p1"],
            "review_questions": ["거절권이 있는지"],
        }],
    )
    monkeypatch.setattr(
        pipeline.decision_gate,
        "filter_candidates",
        lambda candidates: ([], {"supported": 0, "contested": 1, "insufficient": 0}),
    )
    result = pipeline.run("제1조 정상적인 변경 절차를 정한다.")
    assert result["candidate_findings"] == []
    assert result["result_schema_version"] == "3.1"
    assert "decision_rag" not in result


def test_preamble_is_not_analyzed_and_appendices_are_independent_sections() -> None:
    source = "위험유형 시험: 은행이 일방 변경\n제1조 정상 조항\n별지 1 개인정보를 동의 없이 제3자에게 제공한다."
    sections = segment_clauses(source)
    assert sections[0].section_type == "preamble" and sections[0].analyzable is False
    assert sections[1].section_id == "article:1"
    assert sections[2].section_id == "appendix:1"


def test_repeated_page_margins_are_removed_but_unique_content_is_retained() -> None:
    pages = ["공통 계약서\n제1조 첫 내용\n1 / 2", "공통 계약서\n제2조 둘째 내용\n2 / 2"]
    assert _remove_repeated_margins(pages) == ["제1조 첫 내용", "제2조 둘째 내용"]


def test_full_pipeline_preserves_rules_only_findings(monkeypatch) -> None:
    pipeline = DocumentAnalysisPipeline()
    monkeypatch.setattr(pipeline, "_retrieve_evidence", lambda _: [])
    monkeypatch.setattr(pipeline.candidates, "suggest", lambda text, excluded: [])
    text = "제1조 은행은 필요하다고 인정하는 경우 계약 내용을 변경할 수 있다."
    baseline = pipeline.run(text, evaluation_mode="rules_only")
    full = pipeline.run(text, evaluation_mode="full")
    project = lambda result: [(item["finding_id"], item["rule_signal"]) for item in result["findings"]]
    assert project(full) == project(baseline)
    assert full["experiment"]["mode"] == "full"


def test_pipeline_maps_a_rule_match_to_its_pdf_page(monkeypatch) -> None:
    pipeline = DocumentAnalysisPipeline()
    monkeypatch.setattr(pipeline, "_retrieve_evidence", lambda _: [])
    monkeypatch.setattr(pipeline.candidates, "suggest", lambda text, excluded: [])
    pages = (
        "계약서 안내와 표지",
        "제1조 은행은 필요하다고 인정하는 경우 계약 내용을 변경할 수 있다.",
    )
    result = pipeline.run("\n".join(pages), pages=pages, source_extension=".pdf")
    assert result["findings"][0]["source"]["page_number"] == 2
    assert result["document"]["page_count"] == 2


def test_cross_page_preview_targets_are_bounded_to_two_pages() -> None:
    targets = DocumentAnalysisPipeline._preview_targets(
        "abc\nDEF", 0, 2, 6, ((0, 3, 1), (4, 7, 2))
    )
    assert targets == [
        {"page_number": 1, "text": "c"},
        {"page_number": 2, "text": "DE"},
    ]
