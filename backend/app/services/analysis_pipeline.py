from __future__ import annotations

from app.prototype import PrototypePipeline
from app.prototype.pii import mask_pii

from .clause_segmenter import segment_clauses
from .retrieval import HybridRetriever


class DocumentAnalysisPipeline:
    def __init__(self) -> None:
        self.prototype = PrototypePipeline()
        self.retriever = HybridRetriever()

    def run(self, text: str, experiment_arm: str) -> dict:
        clauses = segment_clauses(text)
        results = []
        for clause in clauses:
            masking = mask_pii(clause.text)
            evidence = self._retrieve_evidence(masking.masked_text) if masking.passed else []
            results.append(
                self.prototype.analyze(
                    clause.text,
                    experiment_arm,
                    retrieved_evidence=evidence,
                )
            )
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
        dispositions = {result.get("disposition") for result in results}
        if "needs_review" in dispositions:
            disposition = "needs_review"
        elif not findings:
            disposition = "no_signal"
        else:
            disposition = "ready_for_review"
        return {
            "status": "completed",
            "disposition": disposition,
            "clause_count": len(clauses),
            "findings": findings,
            "warnings": sorted(warnings),
            "usage": {"calls": usage_calls},
            "experiment": {
                "arm": experiment_arm,
                "provider": "none" if experiment_arm == "A" else self.prototype.provider.name,
            },
        }

    def _retrieve_evidence(self, masked_clause: str) -> list[dict]:
        try:
            return self.retriever.search(masked_clause, top_k=3)
        except Exception:
            # Retrieval is a grounding aid, never a reason to expose an internal failure
            # or fabricate a legal source. The caller reports its absence explicitly.
            return []
