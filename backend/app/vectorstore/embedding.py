from __future__ import annotations

import hashlib
import math
import re

DIMENSION = 128
TOKEN_PATTERN = re.compile(r"[가-힣A-Za-z0-9]+")


def tokenize(text: str) -> list[str]:
    """Normalize Korean, Latin, and numeric terms for offline retrieval."""
    return [token.lower() for token in TOKEN_PATTERN.findall(text)]


def embed(text: str) -> list[float]:
    """Deterministic offline hashing vector used only by the local prototype."""
    vector = [0.0] * DIMENSION
    for token in tokenize(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % DIMENSION
        vector[index] += -1.0 if digest[4] & 1 else 1.0
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]
