from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Clause:
    """A source-aligned clause segment used to map findings back to the document."""
    number: int
    text: str
    char_start: int
    char_end: int


CLAUSE_HEADING = re.compile(r"(?m)(?=^\s*(?:제\s*\d+\s*조|\d+[.)])\s*)")


def segment_clauses(text: str) -> list[Clause]:
    """Split common Korean article headings while retaining absolute character spans."""
    starts = [match.start() for match in CLAUSE_HEADING.finditer(text)]
    if not starts:
        return [Clause(1, text, 0, len(text))]
    if starts[0] != 0 and text[: starts[0]].strip():
        starts.insert(0, 0)
    starts.append(len(text))
    clauses = []
    for index, (start, end) in enumerate(zip(starts, starts[1:]), start=1):
        clause_text = text[start:end].strip()
        if clause_text:
            actual_start = text.find(clause_text, start, end)
            clauses.append(Clause(index, clause_text, actual_start, actual_start + len(clause_text)))
    return clauses
