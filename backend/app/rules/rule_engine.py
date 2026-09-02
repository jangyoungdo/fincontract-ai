"""A small, deterministic baseline for clause-level risk-signal screening.

The engine emits review candidates, never a legal conclusion.  The rules file is
JSON-compatible YAML so the baseline runs with Python's standard library while
remaining consumable by a YAML parser when the backend stack is introduced.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

DEFAULT_RULESET_PATH = Path(__file__).with_name("rules_v0_1.yaml")


@dataclass(frozen=True)
class RuleMatch:
    """One reproducible review signal with a source span and version metadata."""
    rule_id: str
    rule_version: str
    rule_name: str
    category: str
    matched_excerpt: str
    match_start: int
    match_end: int
    signal_strength: str
    rationale: str
    legal_basis_candidates: List[str]
    explanation: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Convert the immutable match to the API finding schema."""
        return {
            "rule_id": self.rule_id,
            "rule_version": self.rule_version,
            "rule_name": self.rule_name,
            "category": self.category,
            "matched_excerpt": self.matched_excerpt,
            "match_span": [self.match_start, self.match_end],
            "signal_strength": self.signal_strength,
            "rationale": self.rationale,
            "legal_basis_candidates": self.legal_basis_candidates,
            "explanation": self.explanation,
        }


class RuleEngine:
    """Screen masked clauses with versioned deterministic review rules."""
    def __init__(self, ruleset_path: Path = DEFAULT_RULESET_PATH) -> None:
        with ruleset_path.open(encoding="utf-8") as ruleset_file:
            self.ruleset = json.load(ruleset_file)
        self.version = str(self.ruleset["version"])
        self._rules = self.ruleset["rules"]

    def screen(self, clause_text: str, rule_ids: Optional[Iterable[str]] = None) -> List[RuleMatch]:
        """Return matching risk signals without making a legal conclusion."""
        normalized = self._normalize(clause_text)
        selected = set(rule_ids) if rule_ids is not None else None
        matches: List[RuleMatch] = []

        for rule in self._rules:
            if selected is not None and rule["id"] not in selected:
                continue
            required = rule.get("required_pattern_groups")
            group_matches = (
                [self._first_match(group, normalized) for group in required]
                if required
                else [self._first_match(rule["positive_patterns"], normalized)]
            )
            if any(match is None for match in group_matches):
                continue
            positive = next(match for match in group_matches if match is not None)
            if self._has_local_suppression(rule.get("negative_patterns", []), normalized, positive):
                continue
            if self._has_local_group_suppression(
                rule.get("negative_pattern_groups", []), normalized, positive
            ):
                continue

            context_count = sum(term in normalized for term in rule["context_terms"])
            strength = "medium" if context_count >= 2 else "low"
            matches.append(
                RuleMatch(
                    rule_id=rule["id"],
                    rule_version=self.version,
                    rule_name=rule["name"],
                    category=rule["category"],
                    matched_excerpt=positive.group(0),
                    match_start=positive.start(),
                    match_end=positive.end(),
                    signal_strength=strength,
                    rationale=(
                        f"'{rule['name']}' 검토 신호와 문맥어 {context_count}개가 탐지됨. "
                        "위법성 결론이 아니며 예외와 계약 전체 문맥을 검토해야 함."
                    ),
                    legal_basis_candidates=list(rule["legal_basis_candidates"]),
                    explanation=dict(rule["explanation"]),
                )
            )
        return matches

    @staticmethod
    def _normalize(text: str) -> str:
        # Preserve string length so match spans still point to the masked source.
        return re.sub(r"\s", " ", text)

    @staticmethod
    def _first_match(patterns: Iterable[str], text: str) -> Optional[re.Match[str]]:
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match
        return None

    @classmethod
    def _matches_any(cls, patterns: Iterable[str], text: str) -> bool:
        return cls._first_match(patterns, text) is not None

    @classmethod
    def _has_local_suppression(
        cls, patterns: Iterable[str], text: str, anchor: re.Match[str], window: int = 140
    ) -> bool:
        """Do not let a safe exception in another sub-item hide a risk signal."""
        start = max(0, anchor.start() - window)
        end = min(len(text), anchor.end() + window)
        return cls._matches_any(patterns, text[start:end])

    @classmethod
    def _has_local_group_suppression(
        cls,
        pattern_groups: Iterable[Iterable[str]],
        text: str,
        anchor: re.Match[str],
        window: int = 220,
    ) -> bool:
        """Suppress only when every safe-condition group occurs near the risk anchor."""
        groups = list(pattern_groups)
        if not groups:
            return False
        start = max(0, anchor.start() - window)
        end = min(len(text), anchor.end() + window)
        local_context = text[start:end]
        return all(cls._matches_any(group, local_context) for group in groups)
