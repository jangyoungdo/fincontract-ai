import json
import sys
import unittest
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.rules import RuleEngine  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
