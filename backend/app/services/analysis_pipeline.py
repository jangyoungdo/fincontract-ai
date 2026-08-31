from __future__ import annotations

from app.prototype import PrototypePipeline

from .clause_segmenter import segment_clauses
from .retrieval import HybridRetriever


class DocumentAnalysisPipeline:
    def __init__(self) -> None:
        self.prototype = PrototypePipeline()
        self.retriever = HybridRetriever()

    def run(self, text: str, experiment_arm: str) -> dict:
        clauses = segment_clauses(text)
        results = [self.prototype.analyze(clause.text, experiment_arm) for clause in clauses]
        findings = []
        warnings = set()
        usage_calls = []
        for clause, result in zip(clauses, results):
            for finding in result.get("findings", []):
                # The retriever receives the already-masked clause only.
                retrieved_evidence = self._retrieve_evidence(finding["source"]["masked_text"])
                # Candidate legal-basis labels are not source-grounded.  Keep them
                # visible, but append only corpus records returned for this masked clause.
                finding["evidence"].extend(retrieved_evidence)
                finding["grounding"] = {
                    "status": "grounded" if retrieved_evidence else "unavailable",
                    "retrieved_count": len(retrieved_evidence),
                    "corpus_version": self._corpus_version(retrieved_evidence),
                }
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

    @staticmethod
    def _corpus_version(evidence: list[dict]) -> str:
        versions = sorted({item.get("manifest_version", "unknown") for item in evidence})
        return ",".join(versions) if versions else "not_available"
