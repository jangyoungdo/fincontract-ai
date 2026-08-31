import sys
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.prototype import PrototypePipeline  # noqa: E402
from app.prototype.pii import mask_pii  # noqa: E402


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
        self.assertEqual("failed", result["findings"][0]["verification"]["status"])
        self.assertEqual(
            "UNVERIFIED_EVIDENCE",
            result["findings"][0]["verification"]["issues"][0]["code"],
        )

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

    def test_arm_a_has_no_llm_usage(self) -> None:
        result = self.pipeline.analyze(
            "본 계약에 관한 소송은 은행 본점 소재지 법원을 전속적 관할법원으로 한다.", "A"
        )
        self.assertEqual([], result["usage"]["calls"])
        self.assertIsNone(result["findings"][0]["assessment"])

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

    def test_masking_detects_common_identifiers(self) -> None:
        masked = mask_pii("test@example.com, 010-1234-5678, 900101-1234567")
        self.assertTrue(masked.passed)
        self.assertEqual(3, masked.replacement_count)


if __name__ == "__main__":
    unittest.main()
