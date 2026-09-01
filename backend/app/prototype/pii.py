"""Conservative PII masking gate for Korean contract text."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Pattern, Tuple


@dataclass(frozen=True)
class MaskingResult:
    """Masked text plus evidence that the outbound PII gate was applied."""
    masked_text: str
    detected_types: List[str]
    replacement_count: int
    passed: bool


# A contract party ("채무자는", "고객은") is not an identity label. Only an
# explicit name field, or a complete identifying predicate, may consume a name.
NAME_LABEL = r"(?:성명|이름|계약자명|채무자명|고객명)\s*[:：]\s*"
IDENTIFYING_PREDICATE = r"(?:계약자|채무자|고객)(?:는|은)\s*"
PATTERNS: List[Tuple[str, Pattern[str]]] = [
    (
        "name",
        re.compile(
            rf"(?P<prefix>{NAME_LABEL})(?P<value>[가-힣]{{2,5}})(?=\s|$|[.,;])"
            rf"|(?P<prefix_context>{IDENTIFYING_PREDICATE})(?P<value_context>(?!(?:은행|회사|법인|사업자|채권자|금융사))[가-힣]{{2,5}})(?=(?:이|입니|이며|이고|씨))"
        ),
    ),
    (
        "address",
        re.compile(
            r"(?P<prefix>(?:주소|거주지|송달주소)\s*(?:[:：]|은|는)\s*)"
            r"(?P<value>[가-힣][^\n;.!?]{4,99})"
        ),
    ),
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("phone", re.compile(r"(?<!\d)(?:01[016789]|0\d{1,2})[- ]?\d{3,4}[- ]?\d{4}(?!\d)")),
    ("resident_id", re.compile(r"(?<!\d)\d{6}[- ]?[1-8]\d{6}(?!\d)")),
    ("passport", re.compile(r"(?<![A-Za-z0-9])[A-Z]{1,2}\d{7,8}(?!\d)")),
    ("driver_license", re.compile(r"(?<!\d)\d{2}[- ]\d{2}[- ]\d{6}[- ]\d{2}(?!\d)")),
    ("business_registration", re.compile(r"(?<!\d)\d{3}[- ]\d{2}[- ]\d{5}(?!\d)")),
    ("card", re.compile(r"(?<!\d)(?:\d{4}[- ]?){3}\d{4}(?!\d)")),
    ("account_candidate", re.compile(r"(?<!\d)\d{2,6}[- ]\d{2,6}[- ]\d{4,8}(?!\d)")),
]


def mask_pii(text: str) -> MaskingResult:
    """Replace supported identifiers and verify none of those patterns remain."""
    masked = text
    counters: Dict[str, int] = {}
    detected: List[str] = []
    replacement_count = 0

    for pii_type, pattern in PATTERNS:
        def replace(match: re.Match[str]) -> str:
            """Preserve contextual labels while replacing only the sensitive value."""
            nonlocal replacement_count
            counters[pii_type] = counters.get(pii_type, 0) + 1
            replacement_count += 1
            prefix = match.groupdict().get("prefix") or match.groupdict().get("prefix_context") or ""
            return f"{prefix}[{pii_type.upper()}_{counters[pii_type]}]"

        masked, count = pattern.subn(replace, masked)
        if count:
            detected.append(pii_type)

    passed = not any(pattern.search(masked) for _, pattern in PATTERNS)
    return MaskingResult(masked, detected, replacement_count, passed)
