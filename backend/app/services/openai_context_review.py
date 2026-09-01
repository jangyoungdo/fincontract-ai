"""Optional OpenAI context review that can only add validated review candidates."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.config import get_settings
from app.llm.provider import CONTEXT_REVIEW_PROMPT_VERSION, ProviderError

FORBIDDEN_CONCLUSIONS = ("위법하다", "적법하다", "무효이다", "반드시 승소")


class OpenAIContextReviewer:
    """Batch masked clauses and reject outputs that cannot be grounded exactly."""

    def __init__(self, provider: Any, rules: Any) -> None:
        self.provider = provider
        self.rules = rules
        self.settings = get_settings()
        self.rule_by_id = {rule["id"]: rule for rule in rules.ruleset["rules"]}

    @property
    def enabled(self) -> bool:
        return bool(
            self.settings.openai_context_review_enabled
            and self.provider.name == "openai"
            and hasattr(self.provider, "review_context")
        )

    @property
    def version_metadata(self) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        return {
            "provider": "openai",
            "model": self.settings.openai_balanced_model,
            "prompt_version": CONTEXT_REVIEW_PROMPT_VERSION,
            "max_calls": self.settings.openai_context_max_calls,
            "max_chars_per_call": self.settings.openai_context_max_chars_per_call,
        }

    def review(
        self,
        clauses: list[Any],
        excluded: set[tuple[str, str]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], set[str]]:
        """Return candidates, non-content usage metadata, and stable warnings."""
        if not self.enabled or not clauses:
            return [], [], set()
        batches, truncated = self._batches(clauses)
        warnings = {"OPENAI_CONTEXT_REVIEW_TRUNCATED"} if truncated else set()
        accepted: list[dict[str, Any]] = []
        usage: list[dict[str, Any]] = []
        seen = set(excluded)
        per_section: defaultdict[str, int] = defaultdict(int)
        clause_by_id = {clause.section_id: clause for clause in clauses}

        for sequence, batch in enumerate(batches, start=1):
            sections = [
                {"section_id": clause.section_id, "label": clause.label, "text": clause.text}
                for clause in batch
            ]
            try:
                output = self.provider.review_context(
                    sections,
                    self._taxonomy(),
                    self.settings.openai_balanced_model,
                    max_tokens=2200,
                )
            except ProviderError as exc:
                warnings.add(exc.code)
                warnings.add("OPENAI_CONTEXT_REVIEW_FAILED")
                continue
            metadata = self.provider.last_call_metadata()
            usage.append({"role": "context_reviewer", "sequence": sequence, **metadata})
            for raw in output.get("candidates", []):
                section_id = raw.get("section_id")
                rule_id = raw.get("rule_id")
                clause = clause_by_id.get(section_id)
                rule = self.rule_by_id.get(rule_id)
                if clause is None or rule is None:
                    warnings.add("OPENAI_CONTEXT_OUTPUT_REJECTED")
                    continue
                category = rule["category"]
                pair = (section_id, category)
                quote = str(raw.get("evidence_quote", ""))
                combined = " ".join(
                    [
                        str(raw.get("rationale", "")),
                        str(raw.get("review_question", "")),
                        *[str(item) for item in raw.get("counter_considerations", [])],
                    ]
                )
                if (
                    pair in seen
                    or not quote
                    or quote not in clause.text
                    or any(term in combined for term in FORBIDDEN_CONCLUSIONS)
                    or per_section[section_id]
                    >= self.settings.openai_context_max_candidates_per_section
                ):
                    warnings.add("OPENAI_CONTEXT_OUTPUT_REJECTED")
                    continue
                seen.add(pair)
                per_section[section_id] += 1
                accepted.append(
                    {
                        "candidate_id": f"candidate:{section_id}:openai:{rule_id}",
                        "category": category,
                        "name": rule["name"],
                        "rule_id": rule_id,
                        "status": "semantic_review_candidate",
                        "review_method": "openai_context",
                        "confidence": raw["confidence"],
                        "model_id": metadata.get("model", self.settings.openai_balanced_model),
                        "model_revision": "api-managed",
                        "matched_prototype_ids": [],
                        "review_questions": [raw["review_question"]],
                        "rationale": raw["rationale"],
                        "counter_considerations": list(raw.get("counter_considerations", [])),
                        "evidence_quote": quote,
                        "section_id": section_id,
                        "api_response_id": metadata.get("response_id"),
                    }
                )
        return accepted, usage, warnings

    def _batches(self, clauses: list[Any]) -> tuple[list[list[Any]], bool]:
        limit = max(1, self.settings.openai_context_max_chars_per_call)
        call_limit = max(0, self.settings.openai_context_max_calls)
        batches: list[list[Any]] = []
        current: list[Any] = []
        current_chars = 0
        truncated = False
        for clause in clauses:
            size = len(clause.text)
            if size > limit:
                truncated = True
                continue
            if current and current_chars + size > limit:
                batches.append(current)
                current = []
                current_chars = 0
            current.append(clause)
            current_chars += size
        if current:
            batches.append(current)
        if len(batches) > call_limit:
            batches = batches[:call_limit]
            truncated = True
        return batches, truncated

    def _taxonomy(self) -> list[dict[str, Any]]:
        taxonomy = []
        for rule in self.rule_by_id.values():
            explanation = rule.get("explanation", {})
            taxonomy.append(
                {
                    "rule_id": rule["id"],
                    "name": rule["name"],
                    "category": rule["category"],
                    "description": explanation.get("why_flagged", ""),
                    "review_points": explanation.get("review_points", []),
                    "example_terms": rule.get("candidate_terms", [])[:6],
                }
            )
        return taxonomy
