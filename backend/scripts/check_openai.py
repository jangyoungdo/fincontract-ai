"""Make one bounded OpenAI call using synthetic, privacy-safe assessment data."""

from __future__ import annotations

import json

from app.config import get_settings
from app.llm import get_provider
from app.llm.provider import ProviderError
from app.prototype.pipeline import PrototypePipeline


def main() -> None:
    settings = get_settings()
    provider = get_provider()
    if provider.name != "openai":
        raise SystemExit(
            "Set LLM_PROVIDER=openai, ALLOW_EXTERNAL_LLM=true, and OPENAI_API_KEY first"
        )
    evidence = [
        {
            "evidence_id": "verified:synthetic-1",
            "title": "합성 검증 근거",
            "status": "verified",
            "authority": "synthetic-test-only",
        }
    ]
    try:
        result = provider.assess(
            {
                "rule_id": "R04_UNILATERAL_CHANGE",
                "category": "일방적 계약 변경",
                "rationale": "사업자가 조건을 변경할 수 있다는 합성 위험 신호입니다.",
                "matched_excerpt": "[COMPANY_1]은 조건을 변경할 수 있습니다.",
            },
            evidence,
            settings.openai_balanced_model,
            max_tokens=600,
        )
    except ProviderError as exc:
        print(
            json.dumps(
                {
                    "provider": provider.name,
                    "model": settings.openai_balanced_model,
                    "status": "failed",
                    "error_code": exc.code,
                    "retryable": exc.retryable,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        raise SystemExit(1) from None
    verification = PrototypePipeline._verify(result, evidence, require_verified_evidence=True)
    print(
        json.dumps(
            {
                "provider": provider.name,
                **provider.last_call_metadata(),
                "schema_valid": True,
                "verification_status": verification["status"],
                "cited_evidence_count": len(result["cited_evidence_ids"]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
