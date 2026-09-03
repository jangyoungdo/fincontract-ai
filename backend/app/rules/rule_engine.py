"""A small, deterministic baseline for clause-level risk-signal screening.

The engine emits review candidates, never a legal conclusion.  The rules file is
JSON-compatible YAML so the baseline runs with Python's standard library while
remaining consumable by a YAML parser when the backend stack is introduced.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_RULESET_PATH = Path(__file__).with_name("rules_v0_1.yaml")

MATCH_ELEMENT_LABELS = {
    "R01_EXCESSIVE_LIQUIDATED_DAMAGES": ("금전 부담", "과도성 표현", "부담 주체·행위"),
    "R02_UNFAIR_TERMINATION": ("종료 행위", "포괄적 판단", "행사 주체"),
    "R03_LIMITATION_OF_LIABILITY": ("책임 배제", "포괄 범위", "면책 주체"),
    "R04_UNILATERAL_CHANGE": ("변경 행위", "변경 권한", "행사 주체", "변경 대상"),
    "R05_ACCELERATION": ("즉시 상환", "발생 조건"),
    "R06_TRANSFER_OF_RIGHTS": ("이전 행위", "동의 배제·이전 대상", "계약 관계"),
    "R07_AUTOMATIC_RENEWAL": ("자동 처리", "갱신 행위", "발생 조건"),
    "R08_EXCLUSIVE_JURISDICTION": ("관할 제한", "지정 기준", "사업자 연계"),
    "R09_EXCESSIVE_FEES_OR_RATE": ("비용 항목", "부과 행위", "부담 주체", "과도성 표현"),
    "R10_TYING_OR_ANCILLARY_TRANSACTION": ("부수 상품", "요구 행위", "강제 조건"),
    "R11_DEEMED_CONSENT": ("동의 간주", "침묵·계속 이용 조건"),
    "R12_RETROACTIVE_DISADVANTAGE": ("소급 적용", "취소 대상"),
    "R13_ADDITIONAL_COLLATERAL_OR_GUARANTEE": ("추가 부담", "요구 행위", "요구 주체"),
    "R14_EVIDENCE_MONOPOLY_AND_OBJECTION_LIMIT": ("일방적 증거", "사업자 기록", "이의 제한"),
    "R15_UNFAIR_COST_SHIFTING": ("전가 비용", "부담 주체", "포괄 전가"),
    "R16_BROAD_DATA_USE_OR_THIRD_PARTY_SHARING": ("이용 정보", "이용·제공 행위", "포괄 범위"),
    "R17_DEEMED_OR_INADEQUATE_NOTICE": ("통지 행위", "도달 간주", "효력 표현"),
    "R18_CUSTOMER_RIGHTS_RESTRICTION": ("제한되는 권리", "제한 방식", "영향받는 주체"),
    "R19_REPRESENTATIVE_OR_GUARANTOR_BURDEN": ("책임 주체", "책임 내용", "포괄 범위"),
}


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
    risk_start: int
    risk_end: int
    matched_elements: list[dict[str, Any]]
    signal_strength: str
    rationale: str
    legal_basis_candidates: list[str]
    explanation: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Convert the immutable match to the API finding schema."""
        return {
            "rule_id": self.rule_id,
            "rule_version": self.rule_version,
            "rule_name": self.rule_name,
            "category": self.category,
            "matched_excerpt": self.matched_excerpt,
            "match_span": [self.match_start, self.match_end],
            "risk_span": [self.risk_start, self.risk_end],
            "matched_elements": self.matched_elements,
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

    def screen(
        self, clause_text: str, rule_ids: Iterable[str] | None = None
    ) -> list[RuleMatch]:
        """Return matching risk signals without making a legal conclusion."""
        normalized = self._normalize(clause_text)
        selected = set(rule_ids) if rule_ids is not None else None
        matches: list[RuleMatch] = []

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
            concrete_matches = [match for match in group_matches if match is not None]
            labels = MATCH_ELEMENT_LABELS.get(rule["id"], ())
            matched_elements = [
                {
                    "label": labels[index] if index < len(labels) else f"판단 표현 {index + 1}",
                    "excerpt": match.group(0),
                    "span": [match.start(), match.end()],
                }
                for index, match in enumerate(concrete_matches)
            ]
            risk_start, risk_end = self._sentence_span(
                normalized,
                min(match.start() for match in concrete_matches),
                max(match.end() for match in concrete_matches),
            )
            matches.append(
                RuleMatch(
                    rule_id=rule["id"],
                    rule_version=self.version,
                    rule_name=rule["name"],
                    category=rule["category"],
                    matched_excerpt=positive.group(0),
                    match_start=positive.start(),
                    match_end=positive.end(),
                    risk_start=risk_start,
                    risk_end=risk_end,
                    matched_elements=matched_elements,
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
    def _sentence_span(text: str, start: int, end: int) -> tuple[int, int]:
        """Expand combined rule elements to their readable sentence boundary."""
        left = max(text.rfind(mark, 0, start) for mark in ".!?") + 1
        while left < start and text[left].isspace():
            left += 1
        right_candidates = [position for mark in ".!?" if (position := text.find(mark, end)) >= 0]
        right = min(right_candidates) + 1 if right_candidates else len(text)
        return left, right

    @staticmethod
    def _normalize(text: str) -> str:
        # Preserve string length so match spans still point to the masked source.
        return re.sub(r"\s", " ", text)

    @staticmethod
    def _first_match(patterns: Iterable[str], text: str) -> re.Match[str] | None:
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
