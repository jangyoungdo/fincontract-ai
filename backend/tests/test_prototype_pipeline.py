import sys
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.prototype import PrototypePipeline  # noqa: E402
from app.prototype.pii import mask_pii  # noqa: E402
from app.services.deterministic_summary import finding_summary  # noqa: E402
from app.services.revision_guidance import GUIDANCE, GUIDANCE_VERSION  # noqa: E402


class PrototypePipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.pipeline = PrototypePipeline()

    def test_arm_d_runs_rules_mock_analysis_and_verification(self) -> None:
        result = self.pipeline.analyze(
            "은행은 필요하다고 인정하는 경우 서비스 내용을 일방적으로 변경할 수 있다.", "D"
        )
        self.assertEqual("completed", result["status"])
        self.assertEqual("needs_review", result["disposition"])
        self.assertEqual("mock", result["experiment"]["provider"])
        self.assertEqual("assessment-v1", result["usage"]["calls"][0]["prompt_version"])
        self.assertTrue(result["usage"]["calls"][0]["synthetic"])
        self.assertEqual("failed", result["findings"][0]["verification"]["status"])
        self.assertEqual(
            "UNVERIFIED_EVIDENCE",
            result["findings"][0]["verification"]["issues"][0]["code"],
        )
        explanation = result["findings"][0]["explanation"]
        self.assertTrue(explanation["why_flagged"])
        self.assertTrue(explanation["possible_impact"])
        self.assertTrue(explanation["review_points"])
        self.assertEqual("revision-guidance-v0.1.0", explanation["guidance_version"])
        self.assertEqual(2, len(explanation["revision_points"]))
        self.assertTrue(explanation["example_clause"])
        self.assertIn("검토용", explanation["disclaimer"])
        self.assertNotIn("explanation", result["findings"][0]["rule_signal"])

    def test_all_rules_have_versioned_drafting_guidance(self) -> None:
        self.assertEqual(19, len(GUIDANCE))
        self.assertEqual("revision-guidance-v0.1.0", GUIDANCE_VERSION)
        forbidden = ("위법하다", "적법하다", "무효이다", "반드시 승소")
        for rule in self.pipeline.rules.ruleset["rules"]:
            with self.subTest(rule_id=rule["id"]):
                point_one, point_two, example_clause = GUIDANCE[rule["id"]]
                self.assertTrue(point_one)
                self.assertTrue(point_two)
                self.assertTrue(example_clause)
                self.assertFalse(any(term in example_clause for term in forbidden))

    def test_arm_d_passes_only_with_retrieved_verified_evidence(self) -> None:
        evidence = [
            {
                "evidence_id": "verified:1",
                "title": "검증 근거",
                "authority": "synthetic-test-authority",
                "source_url": "https://example.invalid/verified",
                "quoted_excerpt": "일방 변경 검토 근거",
                "status": "verified",
                "manifest_version": "test-v1",
            }
        ]
        result = self.pipeline.analyze(
            "은행은 필요하다고 인정하는 경우 서비스 내용을 일방적으로 변경할 수 있다.",
            "D",
            retrieved_evidence=evidence,
        )
        self.assertEqual("ready_for_review", result["disposition"])
        self.assertEqual("passed", result["findings"][0]["verification"]["status"])
        self.assertEqual("verified:1", result["findings"][0]["assessment"]["cited_evidence_ids"][0])

    def test_legacy_source_verified_status_is_normalized_during_reindex_transition(self) -> None:
        assessment = {"cited_evidence_ids": ["legacy:1"], "summary": "검토 보조"}
        evidence = [{"evidence_id": "legacy:1", "status": "source_verified"}]
        self.assertEqual("passed", self.pipeline._verify(assessment, evidence, True)["status"])

    def test_arm_a_has_no_llm_usage(self) -> None:
        result = self.pipeline.analyze(
            "본 계약에 관한 소송은 은행 본점 소재지 법원을 전속적 관할법원으로 한다.", "A"
        )
        self.assertEqual([], result["usage"]["calls"])
        self.assertIsNone(result["findings"][0]["assessment"])

    def test_provider_budget_preserves_rule_findings_and_marks_enrichment_skipped(self) -> None:
        result = self.pipeline.analyze(
            "은행은 필요하다고 인정하는 경우 서비스 내용을 일방적으로 변경할 수 있다.",
            "D",
            max_provider_calls=0,
        )
        self.assertEqual("completed", result["status"])
        self.assertEqual("needs_review", result["disposition"])
        self.assertEqual(1, len(result["findings"]))
        self.assertIsNone(result["findings"][0]["assessment"])
        self.assertEqual("not_run", result["findings"][0]["verification"]["status"])
        self.assertIn("LLM_BUDGET_SKIPPED", result["warnings"])

    def test_pii_is_not_present_in_result(self) -> None:
        email = "customer@example.com"
        result = self.pipeline.analyze(
            f"연락처는 {email}이다. 은행은 필요하다고 인정하는 경우 서비스 내용을 일방적으로 변경할 수 있다."
        )
        self.assertNotIn(email, str(result))
        self.assertIn("[EMAIL_1]", result["document"]["masked_text"])

    def test_no_signal_completes_safely(self) -> None:
        result = self.pipeline.analyze("고객은 약정한 날에 원금을 상환한다.")
        self.assertEqual("no_signal", result["disposition"])

    def test_match_span_points_to_masked_source(self) -> None:
        text = "\n  은행은 필요하다고 인정하는 경우 서비스 내용을 일방적으로 변경할 수 있다."
        result = self.pipeline.analyze(text, "A")
        finding = result["findings"][0]
        start, end = finding["rule_signal"]["match_span"]
        self.assertEqual(finding["rule_signal"]["matched_excerpt"], text[start:end].replace("\n", " "))

    def test_source_span_and_elements_explain_the_complete_risk_structure(self) -> None:
        text = "고객은 은행의 승인을 받지 않으면 계약을 해지할 수 없다."
        result = self.pipeline.analyze(text, "A")
        finding = next(
            item
            for item in result["findings"]
            if item["rule_signal"]["rule_id"] == "R18_CUSTOMER_RIGHTS_RESTRICTION"
        )
        signal = finding["rule_signal"]
        self.assertEqual(
            ["제한되는 권리", "제한 방식", "영향받는 주체"],
            [element["label"] for element in signal["matched_elements"]],
        )
        self.assertEqual(
            ["해지", "할 수 없", "고객"],
            [element["excerpt"] for element in signal["matched_elements"]],
        )
        source_start, source_end = finding["source"]["match_span"]
        source_excerpt = text[source_start:source_end]
        self.assertIn("고객", source_excerpt)
        self.assertIn("해지", source_excerpt)
        self.assertIn("할 수 없", source_excerpt)
        self.assertNotIn("‘해지’ 문구에서", finding_summary(finding))
        self.assertIn("고객의 해지권", finding["explanation"]["revision_points"][0])
        self.assertIn("해지권을 행사할 수 있습니다", finding["explanation"]["example_clause"])

    def test_masking_detects_common_identifiers(self) -> None:
        masked = mask_pii("test@example.com, 010-1234-5678, 900101-1234567")
        self.assertTrue(masked.passed)
        self.assertEqual(3, masked.replacement_count)

    def test_masking_detects_labeled_korean_name_and_address(self) -> None:
        masked = mask_pii("성명: 홍길동\n주소: 서울특별시 종로구 세종대로 1\n대출금 1억원")
        self.assertTrue(masked.passed)
        self.assertEqual(["name", "address"], masked.detected_types)
        self.assertIn("성명: [NAME_1]", masked.masked_text)
        self.assertIn("주소: [ADDRESS_1]", masked.masked_text)
        self.assertNotIn("홍길동", masked.masked_text)
        self.assertNotIn("세종대로", masked.masked_text)

    def test_masking_detects_contextual_identity_and_extended_identifiers(self) -> None:
        source = (
            "계약자는 홍길동이고 주소는 서울특별시 종로구 세종대로 1. "
            "여권 M12345678, 운전면허 11-22-123456-78, 사업자 123-45-67890"
        )
        masked = mask_pii(source)
        self.assertTrue(masked.passed)
        self.assertEqual(
            {"name", "address", "passport", "driver_license", "business_registration"},
            set(masked.detected_types),
        )
        for sensitive in ("홍길동", "세종대로", "M12345678", "11-22-123456-78", "123-45-67890"):
            self.assertNotIn(sensitive, masked.masked_text)

    def test_masking_does_not_treat_legal_venue_as_personal_address(self) -> None:
        text = "은행 본점 소재지 법원을 전속적 관할법원으로 한다."
        self.assertEqual(text, mask_pii(text).masked_text)


if __name__ == "__main__":
    unittest.main()
