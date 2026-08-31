from __future__ import annotations

from app.prototype import PrototypePipeline

from .clause_segmenter import segment_clauses


class DocumentAnalysisPipeline:
    def __init__(self) -> None:
        self.prototype = PrototypePipeline()

    def run(self, text: str, experiment_arm: str) -> dict:
        clauses = segment_clauses(text)
        results = [self.prototype.analyze(clause.text, experiment_arm) for clause in clauses]
        findings = []
        warnings = set()
        usage_calls = []
        for clause, result in zip(clauses, results):
            for finding in result.get("findings", []):
                finding["clause"] = {
                    "number": clause.number,
                    "char_start": clause.char_start,
                    "char_end": clause.char_end,
                }
                findings.append(finding)
            warnings.update(result.get("warnings", []))
            usage_calls.extend(result.get("usage", {}).get("calls", []))
        disposition = "no_signal" if not findings else "ready_for_review"
        return {
            "status": "completed",
            "disposition": disposition,
            "clause_count": len(clauses),
            "findings": findings,
            "warnings": sorted(warnings),
            "usage": {"calls": usage_calls},
            "experiment": {"arm": experiment_arm, "provider": "mock" if experiment_arm == "D" else "none"},
        }
