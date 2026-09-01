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

    def test_all_nineteen_rules_have_a_synthetic_positive_case(self) -> None:
        cases = {
            "R01_EXCESSIVE_LIQUIDATED_DAMAGES": "고객은 실제 손해와 관계없이 위약금 전액을 지급한다.",
            "R02_UNFAIR_TERMINATION": "은행은 필요하다고 인정하는 경우 계약을 해지할 수 있다.",
            "R03_LIMITATION_OF_LIABILITY": "은행은 어떠한 책임을 지지 않는다.",
            "R04_UNILATERAL_CHANGE": "은행은 필요하다고 인정하는 경우 서비스 내용을 일방적으로 변경할 수 있다.",
            "R05_ACCELERATION": "은행이 필요하다고 판단하는 경우 기한의 이익을 상실한다.",
            "R06_TRANSFER_OF_RIGHTS": "은행은 고객의 동의 없이 채권을 제3자에게 양도할 수 있다.",
            "R07_AUTOMATIC_RENEWAL": "계약은 만료일에 자동으로 갱신된다.",
            "R08_EXCLUSIVE_JURISDICTION": "소송은 은행 본점 소재지 법원에서만 한다.",
            "R09_EXCESSIVE_FEES_OR_RATE": "채무자는 기간과 관계없이 중도상환수수료 5%를 부담한다.",
            "R10_TYING_OR_ANCILLARY_TRANSACTION": "고객은 신용카드를 반드시 가입하여야 한다.",
            "R11_DEEMED_CONSENT": "고객이 이의를 제기하지 않으면 동의한 것으로 본다.",
            "R12_RETROACTIVE_DISADVANTAGE": "우대금리를 소급 적용하여 모두 취소한다.",
            "R13_ADDITIONAL_COLLATERAL_OR_GUARANTEE": "채권자는 추가 담보를 제출하도록 요구한다.",
            "R14_EVIDENCE_MONOPOLY_AND_OBJECTION_LIMIT": "은행 전산 기록을 최종 증거로 하며 이의를 제기할 수 없다.",
            "R15_UNFAIR_COST_SHIFTING": "채무자는 모든 변호사비용을 전액 부담한다.",
            "R16_BROAD_DATA_USE_OR_THIRD_PARTY_SHARING": "회사는 고객 개인정보를 동의 없이 제3자에게 제공한다.",
            "R17_DEEMED_OR_INADEQUATE_NOTICE": "우편 발송 즉시 통지가 도달한 것으로 본다.",
            "R18_CUSTOMER_RIGHTS_RESTRICTION": "고객은 항변권을 포기하고 이의제기할 수 없다.",
            "R19_REPRESENTATIVE_OR_GUARANTOR_BURDEN": "보증인은 모든 채무를 연대하여 전액 변제한다.",
        }
        self.assertEqual(19, len(self.engine.ruleset["rules"]))
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
        self.assertEqual(19, len(self.engine.ruleset["rules"]))
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

    def test_ordinary_interest_rate_information_is_not_an_excessive_fee_signal(self) -> None:
        text = "최초 적용금리는 연 4.20%이며 시장 상황에 따라 가산금리를 조정할 수 있습니다."
        actual = {match.rule_id for match in self.engine.screen(text)}
        self.assertNotIn("R09_EXCESSIVE_FEES_OR_RATE", actual)


if __name__ == "__main__":
    unittest.main()
