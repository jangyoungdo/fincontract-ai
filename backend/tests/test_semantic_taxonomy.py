import json

from app.services.candidate_finder import TAXONOMY_PATH


def test_semantic_taxonomy_covers_all_nineteen_rules_with_hard_negatives() -> None:
    profiles = json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))["profiles"]
    assert len(profiles) == 19
    assert len({item["rule_id"] for item in profiles}) == 19
    assert all(item["positive_prototypes"] and item["hard_negatives"] for item in profiles)
