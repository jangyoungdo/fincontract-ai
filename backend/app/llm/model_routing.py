"""Deterministic model and token-budget routing for experiment reproducibility."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_POLICY_PATH = Path(__file__).with_name("model_routing_v0_1.json")


@dataclass(frozen=True)
class RoutingContext:
    """Inputs used to make a deterministic model-tier decision."""
    role: str
    risk_level: str = "medium"
    failed_attempts: int = 0
    conflicting_evidence: bool = False
    estimated_input_tokens: int = 0
    deep_requests_today: int = 0


@dataclass(frozen=True)
class ModelRoute:
    """Resolved model choice and the budgets enforced for one LLM call."""
    policy_version: str
    role: str
    tier: str
    model: str
    max_input_tokens: int
    max_output_tokens: int
    max_turns: int
    reason: str


class ModelRouter:
    """Resolve versioned role policies without letting callers choose arbitrary models."""
    def __init__(
        self,
        policy_path: Path = DEFAULT_POLICY_PATH,
        environment: Optional[Dict[str, str]] = None,
    ) -> None:
        with policy_path.open(encoding="utf-8") as policy_file:
            self.policy: Dict[str, Any] = json.load(policy_file)
        self.environment = environment if environment is not None else os.environ

    def route(self, context: RoutingContext) -> ModelRoute:
        """Validate routing constraints and return the allowed model and budgets."""
        if context.role not in self.policy["roles"]:
            raise ValueError(f"Unknown LLM role: {context.role}")
        if context.risk_level not in {"low", "medium", "high"}:
            raise ValueError(f"Unknown risk level: {context.risk_level}")
        if min(context.failed_attempts, context.estimated_input_tokens, context.deep_requests_today) < 0:
            raise ValueError("Routing counters and token estimates cannot be negative")
        if context.role == "adjudicator" and not (
            context.risk_level == "high" and context.conflicting_evidence
        ):
            raise ValueError("Adjudicator requires high risk and conflicting evidence")

        role_policy = self.policy["roles"][context.role]
        tier = role_policy["default_tier"]
        reason = "role default"

        verifier_threshold = self.policy["escalation"]["verifier_to_balanced_after_failed_attempts"]
        if context.role == "verifier" and context.failed_attempts >= verifier_threshold:
            tier = "balanced"
            reason = "verification retry escalation"

        if (
            context.role == "analyst"
            and context.risk_level == "high"
            and context.conflicting_evidence
        ):
            tier = "deep"
            reason = "high-risk analysis with conflicting evidence"

        deep_limit = int(self.policy["escalation"]["deep_daily_request_limit"])
        if tier == "deep" and context.deep_requests_today >= deep_limit:
            raise RuntimeError("Deep-model daily limit reached; human review required")

        max_input_tokens = int(role_policy["max_input_tokens"])
        if context.estimated_input_tokens > max_input_tokens:
            raise ValueError(
                f"Input budget exceeded for {context.role}: "
                f"{context.estimated_input_tokens} > {max_input_tokens}"
            )

        tier_policy = self.policy["model_tiers"][tier]
        model_env = tier_policy["model_env"]
        model = self.environment.get(model_env)
        if not model:
            raise RuntimeError(f"Required model setting is missing: {model_env}")

        return ModelRoute(
            policy_version=self.policy["policy_version"],
            role=context.role,
            tier=tier,
            model=model,
            max_input_tokens=max_input_tokens,
            max_output_tokens=int(tier_policy["default_max_output_tokens"]),
            max_turns=int(role_policy["max_turns"]),
            reason=reason,
        )
