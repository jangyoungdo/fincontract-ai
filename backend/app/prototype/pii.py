"""Conservative PII masking gate for the text-only prototype."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Pattern, Tuple


@dataclass(frozen=True)
class MaskingResult:
    masked_text: str
    detected_types: List[str]
    replacement_count: int
    passed: bool


PATTERNS: List[Tuple[str, Pattern[str]]] = [
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("phone", re.compile(r"(?<!\d)(?:01[016789]|0\d{1,2})[- ]?\d{3,4}[- ]?\d{4}(?!\d)")),
    ("resident_id", re.compile(r"(?<!\d)\d{6}[- ]?[1-8]\d{6}(?!\d)")),
    ("card", re.compile(r"(?<!\d)(?:\d{4}[- ]?){3}\d{4}(?!\d)")),
    ("account_candidate", re.compile(r"(?<!\d)\d{2,6}[- ]\d{2,6}[- ]\d{2,8}(?!\d)")),
]


def mask_pii(text: str) -> MaskingResult:
    masked = text
    counters: Dict[str, int] = {}
    detected: List[str] = []
    replacement_count = 0

    for pii_type, pattern in PATTERNS:
        def replace(_: re.Match[str]) -> str:
            nonlocal replacement_count
            counters[pii_type] = counters.get(pii_type, 0) + 1
            replacement_count += 1
            return f"[{pii_type.upper()}_{counters[pii_type]}]"

        masked, count = pattern.subn(replace, masked)
        if count:
            detected.append(pii_type)

    passed = not any(pattern.search(masked) for _, pattern in PATTERNS)
    return MaskingResult(masked, detected, replacement_count, passed)
