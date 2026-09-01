#!/usr/bin/env python3
"""Make one bounded Claude call using synthetic, privacy-safe assessment data."""

from __future__ import annotations

import json

from app.llm import ModelRouter, RoutingContext, get_provider


def main() -> int:
    """Validate live structured output without printing prompts or response text."""
    provider = get_provider()
    if provider.name != "anthropic":
        raise RuntimeError(
            "Set LLM_PROVIDER=anthropic and explicitly enable the external provider"
        )
    route = ModelRouter().route(
        RoutingContext(role="analyst", risk_level="medium", estimated_input_tokens=200)
    )
    evidence_id = "synthetic-live-check:1"
    result = provider.assess(
        {
            "category": "synthetic_contract_change_signal",
            "rationale": "합성 위험 신호의 근거 적합성을 검토합니다.",
        },
        [
            {
                "evidence_id": evidence_id,
                "title": "합성 검증 근거",
                "status": "verified",
                "authority": "synthetic-test-only",
            }
        ],
        route.model,
        max_tokens=min(route.max_output_tokens, 600),
    )
    if result["cited_evidence_ids"] != [evidence_id]:
        raise RuntimeError("Live response cited an unexpected evidence ID")
    print(
        json.dumps(
            {
                "status": "passed",
                "schema_valid": True,
                "evidence_ids_valid": True,
                "provider": provider.name,
                **provider.last_call_metadata(),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
