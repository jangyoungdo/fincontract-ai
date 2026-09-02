"""A deterministic, offline-first vertical AI prototype pipeline."""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.config import get_settings
from app.llm import ModelRouter, RoutingContext, get_provider
from app.rules import RuleEngine

from .pii import mask_pii

MOCK_MODELS = {
    "ANTHROPIC_FAST_MODEL": "mock-fast",
    "ANTHROPIC_BALANCED_MODEL": "mock-balanced",
    "ANTHROPIC_DEEP_MODEL": "mock-deep",
}

FORBIDDEN_CONCLUSIONS = ("위법하다", "적법하다", "무효이다", "반드시 승소")


class PrototypePipeline:
    """Run arm A or a deterministic mock of arm D using one external schema."""

    def __init__(self) -> None:
        self.rules = RuleEngine()
        self.provider = get_provider()
        settings = get_settings()
        routing_models = (
            MOCK_MODELS
            if self.provider.name == "mock"
            else {
                "ANTHROPIC_FAST_MODEL": settings.openai_fast_model,
                "ANTHROPIC_BALANCED_MODEL": settings.openai_balanced_model,
                "ANTHROPIC_DEEP_MODEL": settings.openai_deep_model,
            }
            if self.provider.name == "openai"
            else {
                "ANTHROPIC_FAST_MODEL": settings.anthropic_fast_model,
                "ANTHROPIC_BALANCED_MODEL": settings.anthropic_balanced_model,
                "ANTHROPIC_DEEP_MODEL": settings.anthropic_deep_model,
            }
        )
        self.router = ModelRouter(environment=routing_models)

    def analyze(
        self,
        text: str,
        experiment_arm: str = "D",
        retrieved_evidence: Optional[List[Dict[str, Any]]] = None,
        max_provider_calls: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Run masking, rule screening, optional assessment, and citation verification."""
        if experiment_arm not in {"A", "D"}:
            raise ValueError("Prototype supports experiment arms A and D")
        if not text.strip():
            raise ValueError("Document text is required")
        if len(text) > 20_000:
            raise ValueError("Prototype input exceeds 20,000 characters")

        started = time.perf_counter()
        created_at = datetime.now(timezone.utc).isoformat()
        analysis_id = str(uuid.uuid4())
        # This is the outbound privacy gate: no rule, retrieval, or provider step
        # receives the clause until supported identifiers have been removed.
        masking = mask_pii(text)
        if not masking.passed:
            return self._safe_failure(analysis_id, created_at, "PII_MASKING_FAILED")

        masked_text = masking.masked_text
        rule_matches = self.rules.screen(masked_text)
        usage: List[Dict[str, Any]] = []
        findings = []
        runtime_warnings: set[str] = set()

        for index, match in enumerate(rule_matches, start=1):
            signal = match.to_dict()
            # Explanations are deterministic rule metadata and remain useful even
            # when the optional model provider is disabled or fails verification.
            explanation = signal.pop("explanation")
            candidate_evidence = [
                {
                    "evidence_id": f"candidate:{match.rule_id}:{basis_index}",
                    "title": basis,
                    "status": "candidate_unverified",
                    "authority": "국가법령정보센터 확인 필요",
                }
                for basis_index, basis in enumerate(match.legal_basis_candidates, start=1)
            ]
            evidence = list(retrieved_evidence or candidate_evidence)
            assessment: Optional[Dict[str, Any]] = None
            verification = {"status": "not_run", "issues": [], "attempts": 0}

            call_allowed = max_provider_calls is None or len(usage) < max_provider_calls
            if experiment_arm == "D" and call_allowed:
                # The provider sees the rule signal and retrieved evidence only;
                # raw document bytes and unmasked text never cross this boundary.
                route = self.router.route(
                    RoutingContext(
                        role="analyst",
                        risk_level="medium",
                        estimated_input_tokens=max(1, len(masked_text) // 3),
                    )
                )
                try:
                    assessment = self.provider.assess(
                        signal, evidence, route.model, max_tokens=route.max_output_tokens
                    )
                    usage.append(self._usage(route, index, max(1, len(masked_text) // 3), self.provider.last_call_metadata()))
                    verification = self._verify(assessment, evidence, require_verified_evidence=True)
                except Exception:
                    runtime_warnings.add("LLM_ENRICHMENT_FAILED")
                    verification = {"status": "not_run", "issues": [{"code": "LLM_ENRICHMENT_FAILED", "message": "설명 보강을 실행하지 못했습니다."}], "attempts": 0}
            elif experiment_arm == "D":
                runtime_warnings.add("LLM_BUDGET_SKIPPED")
                verification = {"status": "not_run", "issues": [{"code": "LLM_BUDGET_SKIPPED", "message": "호출 예산으로 설명 보강을 생략했습니다."}], "attempts": 0}

            findings.append(
                {
                    "finding_id": f"finding-{index}",
                    "source": {
                        "masked_text": masked_text,
                        "match_span": signal["match_span"],
                    },
                    "rule_signal": signal,
                    "explanation": explanation,
                    "evidence": evidence,
                    "legal_basis_candidates": candidate_evidence,
                    "grounding": {
                        "status": "grounded" if retrieved_evidence else "unavailable",
                        "retrieved_count": len(retrieved_evidence or []),
                        "corpus_version": self._corpus_version(retrieved_evidence or []),
                    },
                    "assessment": assessment,
                    "verification": verification,
                    "review_status": "unreviewed",
                }
            )

        verified = all(item["verification"]["status"] == "passed" for item in findings)
        if not findings:
            disposition = "no_signal"
        elif experiment_arm == "A" or verified:
            disposition = "ready_for_review"
        else:
            # Verification failures are never silently downgraded to a usable result.
            disposition = "needs_review"

        if experiment_arm == "D" and self.provider.name == "mock":
            runtime_warnings.add(
                "mock 에이전트 결과는 실제 LLM 품질 평가에 사용할 수 없습니다."
            )

        return {
            "analysis_id": analysis_id,
            "api_version": "analysis-2",
            "status": "completed",
            "disposition": disposition,
            "experiment": {
                "arm": experiment_arm,
                "provider": self.provider.name if experiment_arm == "D" else "none",
                "synthetic_agent_output": experiment_arm == "D" and self.provider.name == "mock",
            },
            "document": {
                "contract_type": "loan_terms",
                "source_retained": False,
                "masked_text": masked_text,
                "text_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "pii_types": masking.detected_types,
                "pii_replacement_count": masking.replacement_count,
            },
            "versions": {
                "ruleset": self.rules.version,
                "routing_policy": self.router.policy["policy_version"],
                "corpus": self._corpus_version(retrieved_evidence or []),
            },
            "findings": findings,
            "usage": {
                "calls": usage,
                "total_estimated_input_tokens": sum(call["estimated_input_tokens"] for call in usage),
                "total_max_output_tokens": sum(call["max_output_tokens"] for call in usage),
            },
            "warnings": sorted(runtime_warnings),
            "created_at": created_at,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        }

    @staticmethod
    def _verify(
        assessment: Dict[str, Any],
        evidence: List[Dict[str, Any]],
        require_verified_evidence: bool = False,
    ) -> Dict[str, Any]:
        allowed_ids = {item["evidence_id"] for item in evidence}
        cited_ids = set(assessment.get("cited_evidence_ids", []))
        issues = []
        if not cited_ids or not cited_ids.issubset(allowed_ids):
            issues.append({"code": "INVALID_EVIDENCE_ID", "message": "허용되지 않은 근거 ID"})
        if require_verified_evidence:
            cited = [item for item in evidence if item["evidence_id"] in cited_ids]
            if any(PrototypePipeline._evidence_status(item) != "verified" for item in cited):
                issues.append(
                    {"code": "UNVERIFIED_EVIDENCE", "message": "검증되지 않은 검색 근거 인용"}
                )
        combined = " ".join(str(value) for value in assessment.values())
        if any(term in combined for term in FORBIDDEN_CONCLUSIONS):
            issues.append({"code": "LEGAL_CONCLUSION", "message": "확정적 법률 표현"})
        return {"status": "failed" if issues else "passed", "issues": issues, "attempts": 1}

    @staticmethod
    def _evidence_status(item: Dict[str, Any]) -> str:
        status = str(item.get("status") or item.get("review_status") or "unverified")
        return "verified" if status in {"verified", "source_verified"} else status

    @staticmethod
    def _corpus_version(evidence: List[Dict[str, Any]]) -> str:
        versions = sorted({item.get("manifest_version", "unknown") for item in evidence})
        return ",".join(versions) if versions else "not_available"

    @staticmethod
    def _usage(
        route: Any,
        sequence: int,
        estimated_input_tokens: int,
        provider_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        data = asdict(route)
        data.update({"sequence": sequence, "estimated_input_tokens": estimated_input_tokens})
        data.update(provider_metadata or {})
        return data

    @staticmethod
    def _safe_failure(analysis_id: str, created_at: str, code: str) -> Dict[str, Any]:
        return {
            "analysis_id": analysis_id,
            "api_version": "prototype-1",
            "status": "failed",
            "disposition": "needs_review",
            "failure": {"code": code, "retryable": False, "safe_message": "안전 검사를 통과하지 못했습니다."},
            "created_at": created_at,
        }
