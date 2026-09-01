"""Offline-only review candidates for clauses that matched no deterministic rule."""

from __future__ import annotations

from app.rules import RuleEngine


class CandidateFinder:
    """Rank taxonomy candidates without treating similarity as a legal finding."""

    def __init__(self, rules: RuleEngine | None = None) -> None:
        self.rules = rules or RuleEngine()

    def suggest(self, text: str, limit: int = 2) -> list[dict]:
        candidates = []
        for rule in self.rules.ruleset["rules"]:
            profile = set(rule.get("candidate_terms", []))
            overlap = sorted(term for term in profile if term in text)
            # Two independent taxonomy terms prevent generic Korean words from
            # becoming a review candidate. This is deliberately conservative.
            if len(overlap) < 2:
                continue
            score = len(overlap) / len(profile)
            candidates.append(
                {
                    "candidate_id": f"candidate:{rule['id']}",
                    "category": rule["category"],
                    "name": rule["name"],
                    "status": "deterministic_rule_unmapped_candidate",
                    "confidence": "medium" if score >= 0.5 else "low",
                    "matched_terms": overlap,
                    "review_questions": list(rule["explanation"]["review_points"]),
                }
            )
        return sorted(candidates, key=lambda item: (-len(item["matched_terms"]), item["category"]))[:limit]
