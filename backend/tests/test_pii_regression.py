import json
from pathlib import Path

from app.prototype.pii import mask_pii

FIXTURE = Path(__file__).parent / "fixtures" / "pii_regression_v0_1.jsonl"


def test_pii_regression_cases_mask_expected_values_without_known_false_positives() -> None:
    for line in FIXTURE.read_text(encoding="utf-8").splitlines():
        case = json.loads(line)
        result = mask_pii(case["text"])
        assert result.passed, case["case_id"]
        assert set(result.detected_types) == set(case["expected_types"]), case["case_id"]
        for sensitive in case["forbidden"]:
            assert sensitive not in result.masked_text, case["case_id"]
        if not case["expected_types"]:
            assert result.masked_text == case["text"], case["case_id"]
