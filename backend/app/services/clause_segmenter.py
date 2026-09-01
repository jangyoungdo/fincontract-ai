from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Subclause:
    label: str
    char_start: int
    char_end: int


@dataclass(frozen=True)
class Clause:
    """One Korean article, with internal numbering retained for source mapping."""
    number: int
    text: str
    char_start: int
    char_end: int
    subclauses: tuple[Subclause, ...] = ()

    @property
    def label(self) -> str:
        return f"제{self.number}조" if self.number else "전문"

    def subclause_for_offset(self, offset: int) -> Subclause | None:
        absolute = self.char_start + offset
        return next((item for item in self.subclauses if item.char_start <= absolute < item.char_end), None)


ARTICLE_HEADING = re.compile(r"(?m)^\s*제\s*(?P<number>\d+)\s*조")
SUBCLAUSE_HEADING = re.compile(r"(?m)^\s*(?P<label>[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳]|\d+\))")


def _subclauses(text: str, article_start: int) -> tuple[Subclause, ...]:
    starts = [(match.start(), match.group("label")) for match in SUBCLAUSE_HEADING.finditer(text)]
    return tuple(
        Subclause(label, article_start + start, article_start + end)
        for (start, label), (end, _) in zip(starts, starts[1:] + [(len(text), "")])
        if text[start:end].strip()
    )


def segment_clauses(text: str) -> list[Clause]:
    """Split only ``제N조`` headings; numbered items remain article context."""
    headings = list(ARTICLE_HEADING.finditer(text))
    if not headings:
        return [Clause(1, text, 0, len(text), _subclauses(text, 0))]
    clauses: list[Clause] = []
    if text[: headings[0].start()].strip():
        prefix = text[: headings[0].start()]
        clauses.append(Clause(0, prefix, 0, len(prefix), _subclauses(prefix, 0)))
    for index, heading in enumerate(headings):
        start = heading.start()
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        clause_text = text[start:end].strip()
        actual_start = text.find(clause_text, start, end)
        clauses.append(
            Clause(
                int(heading.group("number")),
                clause_text,
                actual_start,
                actual_start + len(clause_text),
                _subclauses(clause_text, actual_start),
            )
        )
    return clauses
