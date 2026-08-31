import sys
import unittest
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.llm import ModelRouter, RoutingContext  # noqa: E402


MODELS = {
    "ANTHROPIC_FAST_MODEL": "fast-test-model",
    "ANTHROPIC_BALANCED_MODEL": "balanced-test-model",
    "ANTHROPIC_DEEP_MODEL": "deep-test-model",
}


class ModelRoutingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.router = ModelRouter(environment=MODELS)

    def test_cheap_model_handles_planning_and_first_verification(self) -> None:
        self.assertEqual("fast", self.router.route(RoutingContext(role="planner")).tier)
        self.assertEqual("fast", self.router.route(RoutingContext(role="verifier")).tier)

    def test_analysis_defaults_to_balanced(self) -> None:
        route = self.router.route(RoutingContext(role="analyst", risk_level="medium"))
        self.assertEqual("balanced", route.tier)
        self.assertEqual(1600, route.max_output_tokens)

    def test_deep_model_requires_both_high_risk_and_conflict(self) -> None:
        high_only = self.router.route(RoutingContext(role="analyst", risk_level="high"))
        escalated = self.router.route(
            RoutingContext(role="analyst", risk_level="high", conflicting_evidence=True)
        )
        self.assertEqual("balanced", high_only.tier)
        self.assertEqual("deep", escalated.tier)

    def test_failed_verification_escalates_once(self) -> None:
        route = self.router.route(RoutingContext(role="verifier", failed_attempts=1))
        self.assertEqual("balanced", route.tier)

    def test_input_budget_is_enforced_before_api_call(self) -> None:
        with self.assertRaises(ValueError):
            self.router.route(RoutingContext(role="planner", estimated_input_tokens=3001))

    def test_adjudicator_requires_explicit_escalation_conditions(self) -> None:
        with self.assertRaises(ValueError):
            self.router.route(RoutingContext(role="adjudicator", risk_level="high"))

    def test_deep_daily_limit_fails_to_human_review(self) -> None:
        with self.assertRaises(RuntimeError):
            self.router.route(
                RoutingContext(
                    role="analyst",
                    risk_level="high",
                    conflicting_evidence=True,
                    deep_requests_today=20,
                )
            )

    def test_missing_model_configuration_fails_closed(self) -> None:
        with self.assertRaises(RuntimeError):
            ModelRouter(environment={}).route(RoutingContext(role="planner"))


if __name__ == "__main__":
    unittest.main()
