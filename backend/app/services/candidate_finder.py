"""Offline semantic review candidates, kept separate from deterministic findings."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Sequence
from functools import lru_cache
from pathlib import Path

from app.config import get_settings
from app.rules import RuleEngine

TAXONOMY_PATH = Path(__file__).with_name("semantic_taxonomy_v0_4.json")

Vector = Sequence[float]
Encoder = Callable[[list[str]], Sequence[Vector]]


@lru_cache(maxsize=1)
def _load_sentence_transformer(model_path: str):
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_path, local_files_only=True)


class LocalE5Encoder:
    """Lazy offline multilingual E5 adapter with a deterministic dev fallback."""

    def __init__(self) -> None:
        settings = get_settings()
        self.model_id = settings.semantic_model_id
        self.model_revision = settings.semantic_model_revision
        self.model_path = settings.semantic_model_path
        self.required = settings.semantic_model_required
        self.backend = "multilingual-e5"
        self._model = None

    def __call__(self, texts: list[str]) -> Sequence[Vector]:
        if self._model is None:
            try:
                if not Path(self.model_path).is_dir():
                    raise FileNotFoundError(self.model_path)
                self._model = _load_sentence_transformer(str(self.model_path))
            except (ImportError, FileNotFoundError, OSError) as exc:
                if self.required:
                    raise RuntimeError("SEMANTIC_MODEL_UNAVAILABLE") from exc
                self.backend = "local-hashing-fallback"
                return [self._hash_vector(text) for text in texts]
        return self._model.encode(texts, normalize_embeddings=True).tolist()

    @staticmethod
    def _hash_vector(text: str, dimensions: int = 384) -> list[float]:
        compact = "".join(text.casefold().split())
        vector = [0.0] * dimensions
        for size in (2, 3, 4):
            for index in range(max(0, len(compact) - size + 1)):
                token = compact[index : index + size].encode("utf-8")
                bucket = int.from_bytes(hashlib.sha256(token).digest()[:4], "big") % dimensions
                vector[bucket] += 1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


def _cosine(left: Vector, right: Vector) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


class CandidateFinder:
    """Rank at most two taxonomy candidates without promoting them to findings."""

    def __init__(self, rules: RuleEngine | None = None, encoder: Encoder | None = None) -> None:
        self.rules = rules or RuleEngine()
        self.encoder = encoder or LocalE5Encoder()
        settings = get_settings()
        self.threshold = settings.semantic_candidate_threshold
        self.margin = settings.semantic_candidate_margin
        self._prototypes: list[tuple[dict, str, str]] = []
        self._negative_prototypes: list[tuple[str, str]] = []
        taxonomy = json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))
        profiles = {item["rule_id"]: item for item in taxonomy["profiles"]}
        for rule in self.rules.ruleset["rules"]:
            prototypes = profiles.get(rule["id"], {}).get("positive_prototypes") or rule.get("candidate_terms", [])
            for index, prototype in enumerate(prototypes, start=1):
                self._prototypes.append((rule, f"{rule['id']}:p{index}", str(prototype)))
            negatives = profiles.get(rule["id"], {}).get("hard_negatives", [])
            negatives = [*negatives, "고객은 약정한 날짜에 원금과 이자를 정상적으로 상환한다."]
            self._negative_prototypes.extend((rule["category"], str(item)) for item in negatives)
        self._prototype_vectors: Sequence[Vector] | None = None
        self._negative_vectors: Sequence[Vector] | None = None

    @property
    def metadata(self) -> dict:
        return {
            "model_id": getattr(self.encoder, "model_id", "injected-test-encoder"),
            "model_revision": getattr(self.encoder, "model_revision", "test"),
            "backend": getattr(self.encoder, "backend", "injected"),
            "threshold": self.threshold,
            "margin": self.margin,
        }

    def suggest(self, text: str, excluded_categories: set[str] | None = None, limit: int = 2) -> list[dict]:
        if not text.strip() or not self._prototypes:
            return []
        if self._prototype_vectors is None:
            self._prototype_vectors = self.encoder([f"query: {item[2]}" for item in self._prototypes])
            self._negative_vectors = self.encoder([f"query: {item[1]}" for item in self._negative_prototypes])
        passage_vector = self.encoder([f"passage: {text}"])[0]
        best: dict[str, tuple[float, dict, str]] = {}
        for (rule, prototype_id, _), vector in zip(self._prototypes, self._prototype_vectors, strict=True):
            if rule["category"] in (excluded_categories or set()):
                continue
            score = _cosine(passage_vector, vector)
            if rule["category"] not in best or score > best[rule["category"]][0]:
                best[rule["category"]] = (score, rule, prototype_id)
        ranked = sorted(best.values(), key=lambda item: (-item[0], item[1]["id"]))
        if not ranked or ranked[0][0] < self.threshold:
            return []
        negative_scores: dict[str, float] = {}
        for (category, _), vector in zip(self._negative_prototypes, self._negative_vectors or [], strict=True):
            negative_scores[category] = max(negative_scores.get(category, -1.0), _cosine(passage_vector, vector))
        candidates = []
        for score, rule, prototype_id in ranked:
            if score < self.threshold:
                continue
            score_margin = score - negative_scores.get(rule["category"], 0.0)
            if score_margin < self.margin:
                continue
            candidates.append({
                "candidate_id": f"candidate:{rule['id']}", "category": rule["category"],
                "name": rule["name"], "status": "semantic_review_candidate",
                "confidence": "high" if score >= 0.85 else "medium",
                "similarity_score": round(score, 6), "similarity_margin": round(score_margin, 6),
                "model_id": self.metadata["model_id"],
                "model_revision": self.metadata["model_revision"],
                "matched_prototype_ids": [prototype_id],
                "review_questions": list(rule["explanation"]["review_points"]),
            })
            if len(candidates) >= limit:
                break
        return candidates
