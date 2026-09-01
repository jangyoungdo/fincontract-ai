"""Run one synthetic context-detection call without sending a user document."""

from __future__ import annotations

import json

from app.config import get_settings
from app.llm import get_provider
from app.llm.provider import ProviderError
from app.rules import RuleEngine
from app.services.openai_context_review import OpenAIContextReviewer


class Clause:
    def __init__(self, section_id: str, label: str, text: str) -> None:
        self.section_id = section_id
        self.label = label
        self.text = text


def main() -> None:
    settings = get_settings()
    provider = get_provider()
    if provider.name != "openai":
        raise SystemExit("OpenAI provider is not enabled")
    reviewer = OpenAIContextReviewer(provider, RuleEngine())
    reviewer.settings.openai_context_review_enabled = True
    clauses = [
        Clause(
            "article-7",
            "제7조",
            "고객이 변경 통지 후 서비스를 계속 사용하면 변경 내용에 동의한 것으로 본다.",
        ),
        Clause(
            "article-8",
            "제8조",
            "직원의 잘못이 있더라도 실제 손실과 무관하게 고객은 잔액의 9%를 부담한다.",
        ),
        Clause(
            "article-9",
            "제9조",
            "고객은 약정한 날짜에 원금과 이자를 정상적으로 상환한다.",
        ),
    ]
    try:
        candidates, usage, warnings = reviewer.review(clauses, excluded=set())
    except ProviderError as exc:
        print(json.dumps({"status": "failed", "error_code": exc.code}, indent=2))
        raise SystemExit(1) from None
    print(
        json.dumps(
            {
                "status": "passed",
                "model": settings.openai_balanced_model,
                "candidate_count": len(candidates),
                "candidates": [
                    {
                        "section_id": item["section_id"],
                        "rule_id": item["rule_id"],
                        "evidence_quote": item["evidence_quote"],
                        "confidence": item["confidence"],
                    }
                    for item in candidates
                ],
                "usage": usage,
                "warnings": sorted(warnings),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
