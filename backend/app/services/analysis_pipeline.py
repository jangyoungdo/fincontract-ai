from __future__ import annotations

import logging
import time

from app.config import get_settings
from app.prototype import PrototypePipeline
from app.prototype.pii import mask_pii, mask_pii_pages

from .candidate_finder import CandidateFinder
from .clause_segmenter import segment_clauses
from .decision_rag import DecisionRAGGate
from .deterministic_summary import enrich_summaries
from .openai_context_review import OpenAIContextReviewer
from .openai_summary import OpenAIReviewSummarizer
from .retrieval import HybridRetriever

LOGGER = logging.getLogger(__name__)


class DocumentAnalysisPipeline:
    """Run one production pipeline; rules-only exists solely for offline evaluation."""

    def __init__(self) -> None:
        self.prototype = PrototypePipeline()
        self.retriever = HybridRetriever()
        self.candidates = CandidateFinder(self.prototype.rules)
        self.decision_gate = DecisionRAGGate(rules=self.prototype.rules)
        self.context_reviewer = OpenAIContextReviewer(
            self.prototype.provider, self.prototype.rules
        )
        self.review_summarizer = OpenAIReviewSummarizer(self.prototype.provider)

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
        overall_started = time.perf_counter()
        if evaluation_mode not in {"full", "rules_only"}:
            raise ValueError("evaluation_mode must be full or rules_only")
        settings = get_settings()

        LOGGER.info(
            "analysis.pipeline.start arm=%s mode=%s ext=%s has_pages=%s",
            experiment_arm,
            evaluation_mode,
            source_extension,
            bool(pages),
        )

        stage_started = time.perf_counter()
        if pages:
            document_masking, masked_pages = mask_pii_pages(pages)
        else:
            document_masking = mask_pii(text)
            masked_pages = (document_masking.masked_text,)
        LOGGER.info(
            "analysis.pipeline.masking_done elapsed_ms=%.2f passed=%s page_count=%s",
            (time.perf_counter() - stage_started) * 1000,
            document_masking.passed,
            len(masked_pages),
        )

        stage_started = time.perf_counter()
        page_ranges = self._page_ranges(masked_pages)
        LOGGER.info(
            "analysis.pipeline.page_ranges_done elapsed_ms=%.2f",
            (time.perf_counter() - stage_started) * 1000,
        )

        if not document_masking.passed:
            LOGGER.info(
                "analysis.pipeline.failed_fast elapsed_ms=%.2f",
                (time.perf_counter() - overall_started) * 1000,
            )
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
        stage_started = time.perf_counter()
        sections = segment_clauses(document_masking.masked_text)
        clauses = [section for section in sections if section.analyzable]
        LOGGER.info(
            "analysis.pipeline.segment_done total_sections=%s analyzable=%s elapsed_ms=%.2f",
            len(sections),
            len(clauses),
            (time.perf_counter() - stage_started) * 1000,
        )

        results = []
        stage_started = time.perf_counter()
        for clause in clauses:
            # The baseline scan stays deterministic. OpenAI is reserved for the
            # single document-level context review after all rules have run.
            evidence = self._retrieve_evidence(clause.text)
            result = self.prototype.analyze(
                clause.text,
                "A",
                retrieved_evidence=evidence,
                max_provider_calls=0,
            )
            results.append(result)
        LOGGER.info(
            "analysis.pipeline.rules_scan_done clauses=%s elapsed_ms=%.2f",
            len(clauses),
            (time.perf_counter() - stage_started) * 1000,
        )

        findings = []
        candidate_findings = []
        warnings = set()
        usage_calls = []
        stage_started = time.perf_counter()
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
                    finding["source"]["_generate_pdf_preview"] = True
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
        LOGGER.info(
            "analysis.pipeline.findings_done findings=%s base_candidates=%s elapsed_ms=%.2f",
            len(findings),
            len(candidate_findings),
            (time.perf_counter() - stage_started) * 1000,
        )

        stage_started = time.perf_counter()
        context_candidate_count = 0
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
            context_candidate_count = len(context_candidates)
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
        LOGGER.info(
            "analysis.pipeline.context_review_done enabled=%s elapsed_ms=%.2f context_candidates=%s",
            evaluation_mode == "full" and self.context_reviewer.enabled,
            (time.perf_counter() - stage_started) * 1000,
            context_candidate_count,
        )

        if evaluation_mode == "full" and candidate_findings:
            candidate_findings, decision_counts = self.decision_gate.filter_candidates(
                candidate_findings
            )
            LOGGER.info(
                "analysis.pipeline.decision_rag_done supported=%s contested=%s "
                "insufficient=%s visible_candidates=%s",
                decision_counts["supported"],
                decision_counts["contested"],
                decision_counts["insufficient"],
                len(candidate_findings),
            )

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

        result = enrich_summaries(
            {
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
                    "openai_summary": self.review_summarizer.version_metadata,
                },
            }
        )

        stage_started = time.perf_counter()
        summary_usage, summary_warnings = self.review_summarizer.enrich(result)
        result["usage"]["calls"].extend(summary_usage)
        result["warnings"] = sorted({*result["warnings"], *summary_warnings})
        LOGGER.info(
            "analysis.pipeline.summary_done enabled=%s method=%s elapsed_ms=%.2f",
            self.review_summarizer.enabled,
            result.get("summary", {}).get("generation", {}).get("method"),
            (time.perf_counter() - stage_started) * 1000,
        )

        LOGGER.info(
            "analysis.pipeline.done elapsed_ms=%.2f findings=%s candidates=%s",
            (time.perf_counter() - overall_started) * 1000,
            len(result.get("findings", [])),
            len(result.get("candidate_findings", [])),
        )
        return result

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
