"""Deterministic, extractive summaries for privacy-safe contract review."""

from __future__ import annotations

import re
from collections import Counter

MAX_SENTENCE_LENGTH = 120
FORBIDDEN_CONCLUSIONS = ("위법", "무효", "불공정 확정", "법률 위반")
FACT_PATTERNS = (
    re.compile(r"(?<!\d)\d+(?:\.\d+)?\s*%"),
    re.compile(r"(?<!\d)\d{1,3}(?:,\d{3})*(?:\.\d+)?\s*(?:원|만원|억원)"),
    re.compile(r"(?<!\d)\d+\s*(?:일|개월|년)(?:\s*(?:이내|이상|이하|간))?"),
)
ACTORS = ("채권자", "금융회사", "금융사", "은행", "대주", "채무자", "차주", "고객")
STRENGTH_RANK = {"high": 0, "medium": 1, "low": 2}
MAX_EXCERPT_LENGTH = 64


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _bounded(sentence: str) -> str:
    sentence = _clean(sentence)
    for term in FORBIDDEN_CONCLUSIONS:
        sentence = sentence.replace(term, "추가 검토")
    if len(sentence) <= MAX_SENTENCE_LENGTH:
        return sentence
    return sentence[: MAX_SENTENCE_LENGTH - 2].rstrip(" ,·") + "…"


def _facts(text: str) -> list[str]:
    found: list[tuple[int, str]] = []
    for pattern in FACT_PATTERNS:
        found.extend((match.start(), _clean(match.group())) for match in pattern.finditer(text))
    for actor in ACTORS:
        index = text.find(actor)
        if index >= 0:
            found.append((index, actor))
    unique: list[str] = []
    for _, value in sorted(found):
        if value not in unique:
            unique.append(value)
    return unique[:3]


def _matched_excerpt(finding: dict) -> str:
    source = finding.get("source", {})
    text = str(source.get("masked_text", ""))
    span = source.get("match_span", [0, 0])
    try:
        start, end = int(span[0]), int(span[1])
    except (IndexError, TypeError, ValueError):
        start, end = 0, 0
    excerpt = text[start:end] if 0 <= start < end <= len(text) else ""
    excerpt = _clean(excerpt)
    if not excerpt:
        excerpt = _clean(str(finding.get("rule_signal", {}).get("matched_excerpt", "")))
    if len(excerpt) > MAX_EXCERPT_LENGTH:
        excerpt = excerpt[: MAX_EXCERPT_LENGTH - 1].rstrip(" ,·") + "…"
    return excerpt


def finding_summary(finding: dict) -> str:
    """Combine exact document facts with reviewed rule metadata in one safe sentence."""
    signal = finding.get("rule_signal", {})
    source = finding.get("source", {})
    rule_name = str(signal.get("rule_name") or signal.get("category") or "계약 조건")
    source_text = str(source.get("masked_text", ""))
    facts = _facts(source_text)
    excerpt = _matched_excerpt(finding)
    if excerpt:
        lead = f"‘{excerpt}’ 문구에서 "
    elif facts:
        lead = f"{', '.join(facts)} 조건과 관련해 "
    else:
        fallback = _clean(str(finding.get("explanation", {}).get("why_flagged", "")))
        lead = f"{fallback[:48].rstrip()}와 관련해 " if fallback else ""
    return _bounded(f"{lead}‘{rule_name}’ 위험 신호가 확인되어 고객 영향을 검토해야 합니다.")


def candidate_summary(candidate: dict) -> str:
    """Explain a semantic-only candidate without presenting it as a rule finding."""
    label = str(candidate.get("name") or candidate.get("category") or "계약 조건")
    excerpt = _matched_excerpt(candidate)
    lead = f"‘{excerpt}’ 문구가 " if excerpt else "해당 문구가 "
    relation = (
        "문맥상 해당할 가능성이 있어"
        if candidate.get("review_method") == "openai_context"
        else "의미적으로 유사해"
    )
    return _bounded(f"{lead}‘{label}’ 유형에 {relation} 추가 확인이 필요합니다.")


def document_summary(findings: list[dict], candidates: list[dict]) -> dict:
    """Create one stable headline from the highest-priority distinct rule categories."""
    if not findings and not candidates:
        return {
            "headline": "현재 19개 규칙과 추가 의미 검토에서 위험 신호가 확인되지 않았습니다. 계약의 안전성이나 적법성을 보장하지는 않습니다.",
            "top_categories": [],
        }

    counts = Counter(
        str(item.get("rule_signal", {}).get("rule_name") or item.get("rule_signal", {}).get("category"))
        for item in findings
    )
    first_indexes: dict[str, int] = {}
    strengths: dict[str, int] = {}
    for index, item in enumerate(findings):
        signal = item.get("rule_signal", {})
        name = str(signal.get("rule_name") or signal.get("category"))
        first_indexes.setdefault(name, index)
        strengths[name] = min(
            strengths.get(name, 99), STRENGTH_RANK.get(str(signal.get("signal_strength")), 99)
        )
    ordered = sorted(counts, key=lambda name: (strengths[name], -counts[name], first_indexes[name]))
    top = ordered[:3]
    remaining = max(0, len(ordered) - len(top))
    category_phrase = ", ".join(top) + (f" 외 {remaining}개 유형" if remaining else "")

    parts = []
    if findings:
        parts.append(f"규칙 위험 신호 {len(findings)}건")
    if candidates:
        parts.append(f"추가 검토 후보 {len(candidates)}건")
    lead = f"이 문서에서는 {category_phrase} 관련 " if category_phrase else "이 문서에서는 "
    return {
        "headline": _bounded(f"{lead}{'과 '.join(parts)}이 확인되어 해당 조항을 우선 검토해야 합니다."),
        "top_categories": top,
    }


def enrich_summaries(result: dict) -> dict:
    """Attach stable summaries without changing any rule or semantic finding."""
    findings = result.get("findings", [])
    candidates = result.get("candidate_findings", [])
    for finding in findings:
        finding["summary_sentence"] = finding_summary(finding)
    for candidate in candidates:
        candidate["summary_sentence"] = candidate_summary(candidate)
    result["summary"] = document_summary(findings, candidates)
    result["result_schema_version"] = "3.0"
    return result
