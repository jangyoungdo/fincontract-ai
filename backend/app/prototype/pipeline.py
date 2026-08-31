"""A deterministic, offline-first vertical AI prototype pipeline."""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

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
        self.router = ModelRouter(environment=MOCK_MODELS)
        self.provider = get_provider()

    def analyze(self, text: str, experiment_arm: str = "D") -> Dict[str, Any]:
        if experiment_arm not in {"A", "D"}:
            raise ValueError("Prototype supports experiment arms A and D")
        if not text.strip():
            raise ValueError("Document text is required")
        if len(text) > 20_000:
            raise ValueError("Prototype input exceeds 20,000 characters")

        started = time.perf_counter()
        created_at = datetime.now(timezone.utc).isoformat()
        analysis_id = str(uuid.uuid4())
        masking = mask_pii(text)
        if not masking.passed:
            return self._safe_failure(analysis_id, created_at, "PII_MASKING_FAILED")

        masked_text = masking.masked_text
        rule_matches = self.rules.screen(masked_text)
        usage: List[Dict[str, Any]] = []
        findings = []

        for index, match in enumerate(rule_matches, start=1):
            signal = match.to_dict()
            evidence = [
                {
                    "evidence_id": f"candidate:{match.rule_id}:{basis_index}",
                    "title": basis,
                    "status": "candidate_unverified",
                    "authority": "국가법령정보센터 확인 필요",
                }
                for basis_index, basis in enumerate(match.legal_basis_candidates, start=1)
            ]
            assessment: Optional[Dict[str, Any]] = None
            verification = {"status": "not_run", "issues": [], "attempts": 0}

            if experiment_arm == "D":
                route = self.router.route(
                    RoutingContext(
                        role="analyst",
                        risk_level="medium",
                        estimated_input_tokens=max(1, len(masked_text) // 3),
                    )
                )
                assessment = self.provider.assess(signal, evidence, route.model)
                usage.append(self._usage(route, index, max(1, len(masked_text) // 3)))
                verification = self._verify(assessment, evidence)
                verifier_route = self.router.route(RoutingContext(role="verifier"))
                usage.append(self._usage(verifier_route, index, max(1, len(str(assessment)) // 3)))

            findings.append(
                {
                    "finding_id": f"finding-{index}",
                    "source": {
                        "masked_text": masked_text,
                        "match_span": signal["match_span"],
                    },
                    "rule_signal": signal,
                    "evidence": evidence,
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
            disposition = "needs_review"

        return {
            "analysis_id": analysis_id,
            "api_version": "prototype-1",
            "status": "completed",
            "disposition": disposition,
            "experiment": {
                "arm": experiment_arm,
                "provider": self.provider.name if experiment_arm == "D" else "none",
                "synthetic_agent_output": experiment_arm == "D" and self.provider.name == "fake",
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
                "corpus": "not_connected",
            },
            "findings": findings,
            "usage": {
                "calls": usage,
                "total_estimated_input_tokens": sum(call["estimated_input_tokens"] for call in usage),
                "total_max_output_tokens": sum(call["max_output_tokens"] for call in usage),
            },
            "warnings": [
                "법적 근거는 검증 전 후보이며 원문·시행일 확인이 필요합니다.",
                "mock 에이전트 결과는 실제 LLM 품질 평가에 사용할 수 없습니다.",
                "이 결과는 법률 판단이 아닌 검토 보조 자료입니다.",
            ],
            "created_at": created_at,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        }

    @staticmethod
    def _verify(assessment: Dict[str, Any], evidence: List[Dict[str, Any]]) -> Dict[str, Any]:
        allowed_ids = {item["evidence_id"] for item in evidence}
        cited_ids = set(assessment.get("cited_evidence_ids", []))
        issues = []
        if not cited_ids or not cited_ids.issubset(allowed_ids):
            issues.append({"code": "INVALID_EVIDENCE_ID", "message": "허용되지 않은 근거 ID"})
        combined = " ".join(str(value) for value in assessment.values())
        if any(term in combined for term in FORBIDDEN_CONCLUSIONS):
            issues.append({"code": "LEGAL_CONCLUSION", "message": "확정적 법률 표현"})
        return {"status": "failed" if issues else "passed", "issues": issues, "attempts": 1}

    @staticmethod
    def _usage(route: Any, sequence: int, estimated_input_tokens: int) -> Dict[str, Any]:
        data = asdict(route)
        data.update({"sequence": sequence, "estimated_input_tokens": estimated_input_tokens, "provider": "mock"})
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
