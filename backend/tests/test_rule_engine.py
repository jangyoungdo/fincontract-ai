import json
import sys
import unittest
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.rules import RuleEngine  # noqa: E402
from app.rules.rule_engine import DEFAULT_RULESET_PATH  # noqa: E402
from app.llm.model_routing import DEFAULT_POLICY_PATH  # noqa: E402


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "loan_terms_synthetic_v0_1.jsonl"


class RuleEngineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = RuleEngine()
        with FIXTURE_PATH.open(encoding="utf-8") as fixture_file:
            cls.cases = [json.loads(line) for line in fixture_file if line.strip()]

    def test_synthetic_gold_cases(self) -> None:
        for case in self.cases:
            with self.subTest(case_id=case["case_id"]):
                actual = {match.rule_id for match in self.engine.screen(case["text"])}
                self.assertEqual(set(case["expected_rule_ids"]), actual)

    def test_every_match_is_explicitly_non_conclusive(self) -> None:
        matches = self.engine.screen(self.cases[0]["text"])
        self.assertTrue(matches)
        self.assertIn("위법성 결론이 아니며", matches[0].rationale)

    def test_unknown_rule_filter_returns_no_matches(self) -> None:
        matches = self.engine.screen(self.cases[0]["text"], rule_ids=["UNKNOWN"])
        self.assertEqual([], matches)

    def test_runtime_package_data_files_are_present(self) -> None:
        self.assertTrue(DEFAULT_RULESET_PATH.is_file())
        self.assertTrue(DEFAULT_POLICY_PATH.is_file())

    def test_all_eight_rules_have_a_synthetic_positive_case(self) -> None:
        cases = {
            "R01_EXCESSIVE_LIQUIDATED_DAMAGES": "고객은 손해의 발생 여부와 관계없이 위약금을 지급한다.",
            "R02_UNFAIR_TERMINATION": "은행은 필요하다고 인정하는 경우 계약을 해지할 수 있다.",
            "R03_LIMITATION_OF_LIABILITY": "은행은 어떠한 책임을 지지 않는다.",
            "R04_UNILATERAL_CHANGE": "은행은 필요하다고 인정하는 경우 서비스 내용을 일방적으로 변경할 수 있다.",
            "R05_ACCELERATION": "은행이 필요하다고 판단하는 경우 기한의 이익을 상실한다.",
            "R06_TRANSFER_OF_RIGHTS": "은행은 고객의 동의 없이 채권을 제3자에게 양도할 수 있다.",
            "R07_AUTOMATIC_RENEWAL": "계약은 만료일에 자동으로 갱신된다.",
            "R08_EXCLUSIVE_JURISDICTION": "소송은 은행 본점 소재지 법원에서만 한다.",
        }
        self.assertEqual(8, len(self.engine.ruleset["rules"]))
        for rule_id, text in cases.items():
            with self.subTest(rule_id=rule_id):
                self.assertIn(rule_id, {match.rule_id for match in self.engine.screen(text)})

    def test_all_rules_have_complete_deterministic_explanations(self) -> None:
        required = {
            "why_flagged",
            "possible_impact",
            "review_points",
            "suggested_revision",
            "disclaimer",
        }
        self.assertEqual(8, len(self.engine.ruleset["rules"]))
        for rule in self.engine.ruleset["rules"]:
            with self.subTest(rule_id=rule["id"]):
                explanation = rule["explanation"]
                self.assertEqual(required, set(explanation))
                self.assertTrue(explanation["review_points"])
                self.assertTrue(all(str(value).strip() for value in explanation.values()))
                self.assertIn("검토용 예시", explanation["disclaimer"])

    def test_suggested_revisions_do_not_make_conclusive_legal_claims(self) -> None:
        forbidden = ("위법하다", "적법하다", "무효이다", "반드시 승소")
        for rule in self.engine.ruleset["rules"]:
            revision = rule["explanation"]["suggested_revision"]
            with self.subTest(rule_id=rule["id"]):
                self.assertFalse(any(term in revision for term in forbidden))


if __name__ == "__main__":
    unittest.main()
