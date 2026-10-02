"""Hashing embedder.

Hosted embedding APIs make a demo depend on a network and a key. This embedder
is deterministic, 384-dimensional, and L2-normalized so pgvector cosine distance
matches an in-process cosine. It is a lexical hasher, not a semantic model.
The corpus is written so the scripted incidents separate cleanly. See the eval.
"""

import hashlib
import math
import re

DIMENSIONS = 384
MODEL_NAME = "opspilot-hash-v1"
_STOP = {
    "the",
    "a",
    "an",
    "of",
    "to",
    "and",
    "in",
    "on",
    "for",
    "after",
    "with",
    "was",
    "were",
    "is",
    "are",
    "at",
    "by",
    "from",
    "that",
    "this",
    "it",
}


def tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return [token for token in tokens if token not in _STOP and len(token) > 1]


def embed(text: str) -> list[float]:
    vector = [0.0] * DIMENSIONS
    for token in tokenize(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:2], "big") % DIMENSIONS
        sign = 1.0 if digest[2] % 2 == 0 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def cosine(left: list[float], right: list[float]) -> float:
    return float(sum(a * b for a, b in zip(left, right, strict=True)))


def vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in values) + "]"
