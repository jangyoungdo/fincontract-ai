"""Deterministic threshold calibration for the public synthetic semantic dev set."""

from __future__ import annotations


def calibrate_threshold(rows: list[dict], minimum_precision: float = 0.75, fallback: float = 0.72) -> float:
    """Maximize macro-style binary F1 under a precision floor; ties prefer safety."""
    candidates = sorted({float(row["score"]) for row in rows}, reverse=True)
    ranked: list[tuple[float, float]] = []
    for threshold in candidates:
        tp = sum(bool(row["positive"]) and float(row["score"]) >= threshold for row in rows)
        fp = sum(not bool(row["positive"]) and float(row["score"]) >= threshold for row in rows)
        fn = sum(bool(row["positive"]) and float(row["score"]) < threshold for row in rows)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        if precision >= minimum_precision:
            ranked.append((f1, threshold))
    return max(ranked, default=(0.0, fallback))[1]
