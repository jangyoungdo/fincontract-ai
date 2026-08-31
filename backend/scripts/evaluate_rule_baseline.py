#!/usr/bin/env python3
"""Evaluate the deterministic baseline against JSONL cases."""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.rules import RuleEngine  # noqa: E402


def ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    engine = RuleEngine()
    counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    cases = []
    dataset_is_synthetic = True
    with args.dataset.open(encoding="utf-8") as dataset_file:
        for line in dataset_file:
            if not line.strip():
                continue
            case = json.loads(line)
            dataset_is_synthetic = dataset_is_synthetic and case.get("synthetic") is True
            expected = set(case["expected_rule_ids"])
            actual = {match.rule_id for match in engine.screen(case["text"])}
            cases.append({"case_id": case["case_id"], "expected": sorted(expected), "actual": sorted(actual)})
            for rule_id in {rule["id"] for rule in engine.ruleset["rules"]}:
                counts[rule_id]["tp" if rule_id in expected and rule_id in actual else
                                "fp" if rule_id not in expected and rule_id in actual else
                                "fn" if rule_id in expected and rule_id not in actual else "tn"] += 1

    metrics = {}
    for rule_id, values in sorted(counts.items()):
        precision = ratio(values["tp"], values["tp"] + values["fp"])
        recall = ratio(values["tp"], values["tp"] + values["fn"])
        metrics[rule_id] = {
            **{key: values[key] for key in ("tp", "fp", "fn", "tn")},
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(ratio(2 * precision * recall, precision + recall), 4),
        }

    result = {
        "experiment": "A-rule-engine",
        "ruleset_version": engine.version,
        "dataset": str(args.dataset),
        "dataset_is_synthetic": dataset_is_synthetic,
        "case_count": len(cases),
        "metrics": metrics,
        "cases": cases,
    }
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
