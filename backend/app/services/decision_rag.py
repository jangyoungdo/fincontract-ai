"""Private decision-card RAG used to validate semantic review candidates."""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.rules import RuleEngine
from app.vectorstore.client import get_chroma_client
from app.vectorstore.embedding import tokenize

from .candidate_finder import LocalE5Encoder
from .retrieval import HybridRetriever

LOGGER = logging.getLogger(__name__)
CARDS_PATH = Path(__file__).with_name("decision_cards_v0_1.json")
COLLECTION_NAME = "decision_cards"


class DecisionRAGUnavailable(RuntimeError):
    """Raised when the private decision-card index cannot be used safely."""


@dataclass(frozen=True)
class DecisionAssessment:
    """Internal-only adjudication result; never added to the public analysis payload."""

    status: str
    support_score: float
    exception_score: float
    matched_factor_codes: tuple[str, ...]
    elapsed_ms: float


class DecisionCardRetriever:
    """Index and retrieve synthetic decision cards in a dedicated Chroma collection."""

    def __init__(
        self,
        *,
        encoder: Callable[[list[str]], Sequence[Sequence[float]]] | None = None,
        client: Any | None = None,
        cards_path: Path = CARDS_PATH,
    ) -> None:
        self.settings = get_settings()
        self.cards_path = cards_path
        self.payload = json.loads(cards_path.read_text(encoding="utf-8"))
        self._validate_payload(self.payload)
        self.cards = {card["card_id"]: card for card in self.payload["cards"]}
        self.encoder = encoder or self._production_encoder()
        self.client = client or get_chroma_client()
        self._injected_encoder = encoder is not None
        self._collection = None

    @staticmethod
    def _validate_payload(payload: dict[str, Any]) -> None:
        required = {
            "card_id",
            "rule_id",
            "polarity",
            "title",
            "source_class",
            "review_status",
            "evaluation_split",
            "factor_groups",
            "text",
        }
        cards = payload.get("cards", [])
        ids = [card.get("card_id") for card in cards]
        if not payload.get("version") or not cards or len(ids) != len(set(ids)):
            raise DecisionRAGUnavailable("invalid decision-card corpus header or duplicate IDs")
        for card in cards:
            if required - card.keys() or card["polarity"] not in {
                "risk_pattern",
                "safe_exception",
            }:
                raise DecisionRAGUnavailable("invalid decision-card record")
            if card["review_status"] != "synthetic_verified":
                raise DecisionRAGUnavailable("unverified decision card")

    def _production_encoder(self) -> LocalE5Encoder:
        if not Path(self.settings.semantic_model_path).is_dir():
            raise DecisionRAGUnavailable("local multilingual-E5 model is unavailable")
        return LocalE5Encoder()

    def _encode(self, texts: list[str]) -> Sequence[Sequence[float]]:
        vectors = self.encoder(texts)
        backend = getattr(self.encoder, "backend", "injected")
        if not self._injected_encoder and backend != "multilingual-e5":
            raise DecisionRAGUnavailable("decision RAG does not permit hashing fallback")
        return vectors

    def _ensure_index(self):
        if self._collection is not None:
            return self._collection
        metadata = {
            "hnsw:space": "cosine",
            "cards_version": self.payload["version"],
            "embedding_provider": "multilingual-e5",
            "model_id": getattr(self.encoder, "model_id", "injected-test-encoder"),
            "model_revision": getattr(self.encoder, "model_revision", "test"),
        }
        collection = self.client.get_or_create_collection(COLLECTION_NAME, metadata=metadata)
        current = collection.metadata or {}
        for key in ("cards_version", "embedding_provider", "model_id", "model_revision"):
            if collection.count() and current.get(key) != metadata[key]:
                raise DecisionRAGUnavailable(f"decision-card index metadata mismatch: {key}")

        current_ids = set(collection.get(include=["metadatas"])["ids"])
        expected_ids = set(self.cards)
        stale_ids = sorted(current_ids - expected_ids)
        if stale_ids:
            collection.delete(ids=stale_ids)
        missing_or_changed = []
        shared_ids = sorted(current_ids & expected_ids)
        metadata_by_id: dict[str, dict[str, Any]] = {}
        if shared_ids:
            existing = collection.get(ids=shared_ids, include=["metadatas"])
            metadata_by_id = dict(zip(existing["ids"], existing["metadatas"], strict=True))
        for card_id, card in self.cards.items():
            if metadata_by_id.get(card_id, {}).get("card_version") != self.payload["version"]:
                missing_or_changed.append(card)
        if missing_or_changed:
            texts = [f"passage: {card['text']}" for card in missing_or_changed]
            embeddings = self._encode(texts)
            collection.upsert(
                ids=[card["card_id"] for card in missing_or_changed],
                documents=[card["text"] for card in missing_or_changed],
                embeddings=[list(vector) for vector in embeddings],
                metadatas=[self._metadata(card) for card in missing_or_changed],
            )
        self._collection = collection
        return collection

    def _metadata(self, card: dict[str, Any]) -> dict[str, Any]:
        return {
            "rule_id": card["rule_id"],
            "polarity": card["polarity"],
            "title": card["title"],
            "source_class": card["source_class"],
            "review_status": card["review_status"],
            "evaluation_split": card["evaluation_split"],
            "factor_groups": json.dumps(card["factor_groups"], ensure_ascii=False),
            "card_version": self.payload["version"],
        }

    def search(self, text: str, rule_id: str) -> list[dict[str, Any]]:
        """Return internal scored cards for one candidate rule."""
        collection = self._ensure_index()
        query_vector = self._encode([f"query: {text}"])[0]
        result = collection.query(
            query_embeddings=[list(query_vector)],
            where={"rule_id": rule_id},
            n_results=min(8, max(1, collection.count())),
            include=["documents", "metadatas", "distances"],
        )
        documents = result["documents"][0]
        lexical_scores = HybridRetriever._bm25(tokenize(text), documents)
        hits = []
        for card_id, document, metadata, distance, lexical in zip(
            result["ids"][0],
            documents,
            result["metadatas"][0],
            result["distances"][0],
            lexical_scores,
            strict=True,
        ):
            factor_groups = json.loads(metadata["factor_groups"])
            matched = tuple(
                group["code"]
                for group in factor_groups
                if any(re.search(pattern, text) for pattern in group["patterns"])
            )
            factor_score = len(matched) / len(factor_groups) if factor_groups else 0.0
            vector_score = max(0.0, 1.0 - float(distance))
            score = 0.6 * vector_score + 0.2 * lexical + 0.2 * factor_score
            hits.append(
                {
                    "card_id": card_id,
                    "polarity": metadata["polarity"],
                    "score": round(score, 6),
                    "factor_score": factor_score,
                    "matched_factor_codes": matched,
                    "factor_count": len(factor_groups),
                    "document": document,
                }
            )
        return sorted(hits, key=lambda item: (-item["score"], item["card_id"]))


class DecisionRAGGate:
    """Filter only candidates contradicted by a complete, high-confidence safe exception."""

    def __init__(
        self,
        retriever: DecisionCardRetriever | None = None,
        rules: RuleEngine | None = None,
    ) -> None:
        self.settings = get_settings()
        self.retriever = retriever
        engine = rules or RuleEngine()
        self.rule_by_category = {
            rule["category"]: rule["id"] for rule in engine.ruleset["rules"]
        }

    def assess(self, text: str, rule_id: str) -> DecisionAssessment:
        started = time.perf_counter()
        if self.retriever is None:
            self.retriever = DecisionCardRetriever()
        retriever = self.retriever
        hits = retriever.search(text, rule_id)
        risks = [item for item in hits if item["polarity"] == "risk_pattern"]
        exceptions = [item for item in hits if item["polarity"] == "safe_exception"]
        risk = risks[0] if risks else None
        exception = exceptions[0] if exceptions else None
        risk_score = float(risk["score"]) if risk else 0.0
        exception_score = float(exception["score"]) if exception else 0.0
        status = "insufficient"
        matched = tuple(risk["matched_factor_codes"]) if risk else ()
        if (
            exception
            and exception_score >= self.settings.decision_rag_min_score
            and exception["factor_count"] > 0
            and exception["factor_score"] == 1.0
        ):
            status = "contested"
            matched = tuple(exception["matched_factor_codes"])
        elif (
            risk
            and risk_score >= self.settings.decision_rag_min_score
            and risk_score - exception_score >= self.settings.decision_rag_margin
            and len(risk["matched_factor_codes"]) >= 2
        ):
            status = "supported"
        return DecisionAssessment(
            status=status,
            support_score=risk_score,
            exception_score=exception_score,
            matched_factor_codes=matched,
            elapsed_ms=(time.perf_counter() - started) * 1000,
        )

    def filter_candidates(self, candidates: list[dict[str, Any]]) -> tuple[list[dict], dict[str, int]]:
        """Keep the public candidate schema unchanged and fail open on RAG unavailability."""
        if not self.settings.decision_rag_enabled:
            return candidates, {"supported": 0, "contested": 0, "insufficient": len(candidates)}
        kept = []
        counts = {"supported": 0, "contested": 0, "insufficient": 0}
        for candidate in candidates:
            rule_id = candidate.get("rule_id") or self._rule_id_from_candidate(candidate)
            text = str(candidate.get("source", {}).get("masked_text", ""))
            if not rule_id or not text:
                counts["insufficient"] += 1
                kept.append(candidate)
                continue
            try:
                assessment = self.assess(text, str(rule_id))
            except Exception as exc:  # noqa: BLE001 - private RAG must not break analysis
                LOGGER.warning("decision_rag.unavailable rule_id=%s error=%s", rule_id, type(exc).__name__)
                counts["insufficient"] += 1
                kept.append(candidate)
                continue
            counts[assessment.status] += 1
            LOGGER.info(
                "decision_rag.assessed rule_id=%s status=%s support=%.4f exception=%.4f "
                "card_version=%s elapsed_ms=%.2f",
                rule_id,
                assessment.status,
                assessment.support_score,
                assessment.exception_score,
                getattr(self.retriever, "payload", {}).get("version", "decision-cards-v0.1.0"),
                assessment.elapsed_ms,
            )
            if assessment.status != "contested":
                kept.append(candidate)
        return kept, counts

    def _rule_id_from_candidate(self, candidate: dict[str, Any]) -> str | None:
        candidate_id = str(candidate.get("candidate_id", ""))
        marker = next((part for part in candidate_id.split(":") if part.startswith("R")), "")
        if re.fullmatch(r"R\d{2}_[A-Z0-9_]+", marker):
            return marker
        return self.rule_by_category.get(str(candidate.get("category", "")))
