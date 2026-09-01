from __future__ import annotations

from app.config import get_settings
from app.prototype import PrototypePipeline
from app.prototype.pii import mask_pii

from .candidate_finder import CandidateFinder
from .clause_segmenter import segment_clauses
from .retrieval import HybridRetriever


class DocumentAnalysisPipeline:
    """Coordinate clause-level masking, retrieval, assessment, and aggregation."""
    def __init__(self) -> None:
        self.prototype = PrototypePipeline()
        self.retriever = HybridRetriever()
        self.candidates = CandidateFinder(self.prototype.rules)

    def run(self, text: str, experiment_arm: str) -> dict:
        """Analyze each clause and preserve the strictest downstream disposition."""
        settings = get_settings()
        document_masking = mask_pii(text)
        if not document_masking.passed:
            return {
                "status": "completed",
                "disposition": "needs_review",
                "clause_count": 0,
                "findings": [],
                "warnings": ["개인정보 마스킹 검증에 실패해 분석을 중단했습니다."],
                "document": {
                    "masked_text": "",
                    "pii_types": document_masking.detected_types,
                    "pii_replacement_count": document_masking.replacement_count,
                },
                "usage": {"calls": []},
                "experiment": {"arm": experiment_arm, "provider": "none"},
            }

        # Segment the already-masked document so all downstream offsets point to
        # the same privacy-safe text returned by the source viewer.
        clauses = segment_clauses(document_masking.masked_text)
        results = []
        remaining_provider_calls = settings.llm_max_calls_per_analysis
        for clause in clauses:
            # Retrieval happens before provider assessment and receives masked text only.
            evidence = self._retrieve_evidence(clause.text)
            result = self.prototype.analyze(
                clause.text,
                experiment_arm,
                retrieved_evidence=evidence,
                max_provider_calls=remaining_provider_calls,
            )
            results.append(result)
            remaining_provider_calls -= len(result.get("usage", {}).get("calls", []))
        findings = []
        candidate_findings = []
        warnings = set()
        usage_calls = []
        for clause, result in zip(clauses, results):
            for finding in result.get("findings", []):
                finding["clause"] = {
                    "number": clause.number,
                    "label": clause.label,
                    "char_start": clause.char_start,
                    "char_end": clause.char_end,
                }
                subclause = clause.subclause_for_offset(finding["source"]["match_span"][0])
                if subclause:
                    finding["clause"]["subclause_label"] = subclause.label
                findings.append(finding)
            if not result.get("findings"):
                for candidate in self.candidates.suggest(clause.text):
                    candidate_findings.append(
                        {
                            **candidate,
                            "source": {"masked_text": clause.text},
                            "clause": {
                                "number": clause.number,
                                "label": clause.label,
                                "char_start": clause.char_start,
                                "char_end": clause.char_end,
                            },
                        }
                    )
            warnings.update(result.get("warnings", []))
            usage_calls.extend(result.get("usage", {}).get("calls", []))
        dispositions = {result.get("disposition") for result in results}
        if "needs_review" in dispositions or candidate_findings:
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
            "candidate_findings": candidate_findings,
            "warnings": sorted(warnings),
            "document": {
                "masked_text": document_masking.masked_text,
                "pii_types": document_masking.detected_types,
                "pii_replacement_count": document_masking.replacement_count,
            },
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
