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
    """One document section, with internal numbering retained for source mapping."""
    number: int | None
    text: str
    char_start: int
    char_end: int
    section_type: str = "article"
    section_id: str = "article:1"
    analyzable: bool = True
    subclauses: tuple[Subclause, ...] = ()

    @property
    def label(self) -> str:
        if self.section_type == "preamble":
            return "전문"
        if self.section_type == "appendix":
            return f"별지 {self.number}"
        return f"제{self.number}조"

    def subclause_for_offset(self, offset: int) -> Subclause | None:
        absolute = self.char_start + offset
        return next((item for item in self.subclauses if item.char_start <= absolute < item.char_end), None)


SECTION_HEADING = re.compile(
    r"(?m)^\s*(?:(?P<article>제\s*(?P<article_number>\d+)\s*조)|"
    r"(?P<appendix>별\s*지\s*(?:제\s*)?(?P<appendix_number>\d+)\s*호?))"
)
SUBCLAUSE_HEADING = re.compile(r"(?m)^\s*(?P<label>[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳]|\d+\))")


def _subclauses(text: str, article_start: int) -> tuple[Subclause, ...]:
    starts = [(match.start(), match.group("label")) for match in SUBCLAUSE_HEADING.finditer(text)]
    return tuple(
        Subclause(label, article_start + start, article_start + end)
        for (start, label), (end, _) in zip(starts, starts[1:] + [(len(text), "")])
        if text[start:end].strip()
    )


def segment_clauses(text: str) -> list[Clause]:
    """Split articles and appendices while retaining a non-analyzable preamble."""
    headings = list(SECTION_HEADING.finditer(text))
    if not headings:
        return [
            Clause(1, text, 0, len(text), "article", "article:1", True, _subclauses(text, 0))
        ]
    clauses: list[Clause] = []
    if text[: headings[0].start()].strip():
        prefix = text[: headings[0].start()]
        clauses.append(
            Clause(
                0, prefix, 0, len(prefix), "preamble", "preamble", False,
                _subclauses(prefix, 0),
            )
        )
    for index, heading in enumerate(headings):
        start = heading.start()
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        clause_text = text[start:end].strip()
        actual_start = text.find(clause_text, start, end)
        section_type = "article" if heading.group("article") else "appendix"
        number = int(heading.group("article_number") or heading.group("appendix_number"))
        clauses.append(
            Clause(
                number, clause_text, actual_start, actual_start + len(clause_text),
                section_type, f"{section_type}:{number}", True,
                _subclauses(clause_text, actual_start),
            )
        )
    return clauses
