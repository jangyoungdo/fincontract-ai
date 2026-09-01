from __future__ import annotations

from app.config import get_settings
from app.prototype import PrototypePipeline
from app.prototype.pii import mask_pii, mask_pii_pages

from .candidate_finder import CandidateFinder
from .clause_segmenter import segment_clauses
from .deterministic_summary import enrich_summaries
from .openai_context_review import OpenAIContextReviewer
from .retrieval import HybridRetriever


class DocumentAnalysisPipeline:
    """Run one production pipeline; rules-only exists solely for offline evaluation."""
    def __init__(self) -> None:
        self.prototype = PrototypePipeline()
        self.retriever = HybridRetriever()
        self.candidates = CandidateFinder(self.prototype.rules)
        self.context_reviewer = OpenAIContextReviewer(
            self.prototype.provider, self.prototype.rules
        )

    def run(
        self,
        text: str,
        experiment_arm: str | None = None,
        *,
        evaluation_mode: str = "full",
        pages: tuple[str, ...] | None = None,
        source_extension: str | None = None,
    ) -> dict:
        """Analyze a document. Legacy A/D input is accepted but does not select product behavior."""
        if evaluation_mode not in {"full", "rules_only"}:
            raise ValueError("evaluation_mode must be full or rules_only")
        settings = get_settings()
        if pages:
            document_masking, masked_pages = mask_pii_pages(pages)
        else:
            document_masking = mask_pii(text)
            masked_pages = (document_masking.masked_text,)
        page_ranges = self._page_ranges(masked_pages)
        if not document_masking.passed:
            return {
                "status": "completed",
                "disposition": "needs_review",
                "clause_count": 0,
                "findings": [],
                "warnings": ["개인정보 마스킹 검증에 실패해 분석을 중단했습니다."],
                "document": {
                    "pii_types": document_masking.detected_types,
                    "pii_replacement_count": document_masking.replacement_count,
                    "page_count": len(masked_pages),
                    "source_type": (source_extension or "").lstrip(".") or "text",
                },
                "usage": {"calls": []},
                "experiment": {"arm": experiment_arm, "provider": "none"},
            }

        # Segment the already-masked document so all downstream offsets point to
        # the same privacy-safe text returned by the source viewer.
        sections = segment_clauses(document_masking.masked_text)
        clauses = [section for section in sections if section.analyzable]
        results = []
        context_call_reserve = (
            min(settings.openai_context_max_calls, settings.llm_max_calls_per_analysis)
            if evaluation_mode == "full" and self.context_reviewer.enabled
            else 0
        )
        remaining_provider_calls = settings.llm_max_calls_per_analysis - context_call_reserve
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
                absolute_match = clause.char_start + finding["source"]["match_span"][0]
                absolute_match_end = clause.char_start + finding["source"]["match_span"][1]
                finding["source"]["page_number"] = self._page_for_offset(
                    absolute_match, page_ranges
                )
                if source_extension == ".pdf":
                    finding["source"]["_preview_targets"] = self._preview_targets(
                        clause.text,
                        clause.char_start,
                        absolute_match,
                        absolute_match_end,
                        page_ranges,
                    )
                finding["source"]["preview_status"] = "text_only"
                finding["source"]["preview_ids"] = []
                findings.append(finding)
            if evaluation_mode == "full" and settings.semantic_model_enabled:
                matched_categories = {
                    item["rule_signal"]["category"] for item in result.get("findings", [])
                }
                for candidate, evidence_text, subclause_label in self._semantic_candidates(
                    clause, matched_categories
                ):
                    segment_start = clause.text.find(evidence_text)
                    absolute_start = clause.char_start + max(0, segment_start)
                    candidate_findings.append(
                        {
                            **candidate,
                            "candidate_id": f"candidate:{clause.section_id}:{candidate['category']}",
                            "source": {
                                "masked_text": evidence_text,
                                "match_span": [0, len(evidence_text)],
                                "page_number": self._page_for_offset(absolute_start, page_ranges),
                                **(
                                    {
                                        "_preview_targets": self._preview_targets(
                                            evidence_text,
                                            absolute_start,
                                            absolute_start,
                                            absolute_start + len(evidence_text),
                                            page_ranges,
                                        )
                                    }
                                    if source_extension == ".pdf"
                                    else {}
                                ),
                                "preview_status": "text_only",
                                "preview_ids": [],
                            },
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
        if evaluation_mode == "full" and self.context_reviewer.enabled:
            excluded = {
                (item["clause"]["section_id"], item["rule_signal"]["category"])
                for item in findings
            }
            excluded.update(
                (item["clause"]["section_id"], item["category"])
                for item in candidate_findings
            )
            context_candidates, context_usage, context_warnings = self.context_reviewer.review(
                clauses, excluded
            )
            clause_by_id = {clause.section_id: clause for clause in clauses}
            for candidate in context_candidates:
                clause = clause_by_id[candidate.pop("section_id")]
                evidence_text = candidate.pop("evidence_quote")
                relative_start = clause.text.find(evidence_text)
                absolute_start = clause.char_start + relative_start
                subclause = clause.subclause_for_offset(relative_start)
                candidate_findings.append(
                    {
                        **candidate,
                        "source": {
                            "masked_text": evidence_text,
                            "match_span": [0, len(evidence_text)],
                            "page_number": self._page_for_offset(absolute_start, page_ranges),
                            **(
                                {
                                    "_preview_targets": self._preview_targets(
                                        evidence_text,
                                        absolute_start,
                                        absolute_start,
                                        absolute_start + len(evidence_text),
                                        page_ranges,
                                    )
                                }
                                if source_extension == ".pdf"
                                else {}
                            ),
                            "preview_status": "text_only",
                            "preview_ids": [],
                        },
                        "clause": {
                            "number": clause.number,
                            "label": clause.label,
                            "section_type": clause.section_type,
                            "section_id": clause.section_id,
                            "analyzable": clause.analyzable,
                            "char_start": clause.char_start,
                            "char_end": clause.char_end,
                            "subclause_label": subclause.label if subclause else None,
                        },
                    }
                )
            usage_calls.extend(context_usage)
            warnings.update(context_warnings)
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
        return enrich_summaries({
            "status": "completed",
            "disposition": disposition,
            "clause_count": len(clauses),
            "findings": findings,
            "candidate_findings": candidate_findings,
            "warnings": sorted(warnings),
            "document": {
                "pii_types": document_masking.detected_types,
                "pii_replacement_count": document_masking.replacement_count,
                "page_count": len(masked_pages),
                "source_type": (source_extension or "").lstrip(".") or "text",
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
                "openai_context": (
                    self.context_reviewer.version_metadata
                    if evaluation_mode == "full"
                    else None
                ),
            },
        })

    @staticmethod
    def _page_ranges(pages: tuple[str, ...]) -> tuple[tuple[int, int, int], ...]:
        """Return one-based page ranges in the same newline-joined masked string."""
        ranges: list[tuple[int, int, int]] = []
        cursor = 0
        for number, page in enumerate(pages, start=1):
            ranges.append((cursor, cursor + len(page), number))
            cursor += len(page) + 1
        return tuple(ranges)

    @staticmethod
    def _page_for_offset(offset: int, ranges: tuple[tuple[int, int, int], ...]) -> int | None:
        for start, end, number in ranges:
            if start <= offset <= end:
                return number
        return ranges[-1][2] if ranges and offset > ranges[-1][1] else None

    @staticmethod
    def _preview_targets(
        source_text: str,
        source_start: int,
        match_start: int,
        match_end: int,
        ranges: tuple[tuple[int, int, int], ...],
    ) -> list[dict]:
        """Describe at most two page-local fragments for a cross-page match."""
        targets: list[dict] = []
        for page_start, page_end, page_number in ranges:
            start = max(match_start, page_start)
            end = min(match_end, page_end)
            if start >= end:
                continue
            local_start = max(0, start - source_start)
            local_end = min(len(source_text), end - source_start)
            fragment = source_text[local_start:local_end].strip()
            if fragment:
                targets.append({"page_number": page_number, "text": fragment})
            if len(targets) == 2:
                break
        return targets

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
