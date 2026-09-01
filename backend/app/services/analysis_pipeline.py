from __future__ import annotations

from app.config import get_settings
from app.prototype import PrototypePipeline
from app.prototype.pii import mask_pii

from .candidate_finder import CandidateFinder
from .clause_segmenter import segment_clauses
from .retrieval import HybridRetriever


class DocumentAnalysisPipeline:
    """Run one production pipeline; rules-only exists solely for offline evaluation."""
    def __init__(self) -> None:
        self.prototype = PrototypePipeline()
        self.retriever = HybridRetriever()
        self.candidates = CandidateFinder(self.prototype.rules)

    def run(self, text: str, experiment_arm: str | None = None, *, evaluation_mode: str = "full") -> dict:
        """Analyze a document. Legacy A/D input is accepted but does not select product behavior."""
        if evaluation_mode not in {"full", "rules_only"}:
            raise ValueError("evaluation_mode must be full or rules_only")
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
        sections = segment_clauses(document_masking.masked_text)
        clauses = [section for section in sections if section.analyzable]
        results = []
        remaining_provider_calls = settings.llm_max_calls_per_analysis
        for clause in clauses:
            # Retrieval happens before provider assessment and receives masked text only.
            evidence = self._retrieve_evidence(clause.text)
            result = self.prototype.analyze(
                clause.text,
                "D" if evaluation_mode == "full" else "A",
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
                finding["finding_id"] = f"finding:{clause.section_id}:{finding['rule_signal']['rule_id']}"
                finding["clause"] = {
                    "number": clause.number,
                    "label": clause.label,
                    "section_type": clause.section_type,
                    "section_id": clause.section_id,
                    "analyzable": clause.analyzable,
                    "char_start": clause.char_start,
                    "char_end": clause.char_end,
                }
                subclause = clause.subclause_for_offset(finding["source"]["match_span"][0])
                if subclause:
                    finding["clause"]["subclause_label"] = subclause.label
                findings.append(finding)
            if evaluation_mode == "full" and settings.semantic_model_enabled:
                matched_categories = {
                    item["rule_signal"]["category"] for item in result.get("findings", [])
                }
                for candidate, evidence_text, subclause_label in self._semantic_candidates(
                    clause, matched_categories
                ):
                    candidate_findings.append(
                        {
                            **candidate,
                            "candidate_id": f"candidate:{clause.section_id}:{candidate['category']}",
                            "source": {"masked_text": evidence_text, "match_span": [0, len(evidence_text)]},
                            "clause": {
                                "number": clause.number,
                                "label": clause.label,
                                "section_type": clause.section_type,
                                "section_id": clause.section_id,
                                "analyzable": clause.analyzable,
                                "char_start": clause.char_start,
                                "char_end": clause.char_end,
                                "subclause_label": subclause_label,
                            },
                        }
                    )
            warnings.update(result.get("warnings", []))
            usage_calls.extend(result.get("usage", {}).get("calls", []))
        dispositions = {result.get("disposition") for result in results}
        if evaluation_mode == "full" and self.candidates.metadata["backend"] != "multilingual-e5":
            warnings.add("SEMANTIC_MODEL_FALLBACK")
        if experiment_arm in {"A", "D"}:
            warnings.add("EXPERIMENT_ARM_DEPRECATED")
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
                "mode": evaluation_mode,
                "legacy_arm_ignored": experiment_arm if experiment_arm in {"A", "D"} else None,
                "provider": self.prototype.provider.name if evaluation_mode == "full" else "none",
            },
            "versions": {
                "ruleset": self.prototype.rules.version,
                "semantic": self.candidates.metadata if evaluation_mode == "full" else None,
            },
        }

    def _semantic_candidates(
        self, clause, excluded_categories: set[str]
    ) -> list[tuple[dict, str, str | None]]:
        """Evaluate whole context and internal items, then retain two unique categories."""
        segments: list[tuple[str, str | None]] = [(clause.text, None)]
        for subclause in clause.subclauses:
            start = subclause.char_start - clause.char_start
            end = subclause.char_end - clause.char_start
            segments.append((clause.text[start:end].strip(), subclause.label))
        best: dict[str, tuple[dict, str, str | None]] = {}
        for segment, label in segments:
            for candidate in self.candidates.suggest(segment, excluded_categories):
                existing = best.get(candidate["category"])
                if (
                    existing is None
                    or candidate["similarity_score"] > existing[0]["similarity_score"]
                ):
                    best[candidate["category"]] = (candidate, segment, label)
        return sorted(best.values(), key=lambda item: -item[0]["similarity_score"])[:2]

    def _retrieve_evidence(self, masked_clause: str) -> list[dict]:
        try:
            return self.retriever.search(masked_clause, top_k=3)
        except Exception:  # noqa: BLE001 - retrieval is optional and fails closed
            # Retrieval is a grounding aid, never a reason to expose an internal failure
            # or fabricate a legal source. The caller reports its absence explicitly.
            return []
