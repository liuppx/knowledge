"""Providers for the retrieval eval.

Default is an *offline* deterministic pair so the gate runs in CI with no model
gateway. They are stand-ins, not quality references: the embedding hashes ASCII
words + CJK character bigrams into a fixed-dimension vector, and the reranker
scores the same bag-of-ngrams cosine plus a phrase bonus. What they buy us is a
non-mock signal that differs from the product's lexical scorer, so the three
tiers (lexical / hybrid / hybrid+rerank) actually diverge and the harness,
metrics and degradation paths are exercised end to end.

Set ``KNOWLEDGE_EVAL_PROVIDER=live`` to run the same harness against the real
Router providers (requires ``MODEL_PROVIDER_MODE=openai_compatible`` and a
gateway URL) — that is the run whose numbers count for v1.0 acceptance.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
from collections import Counter

from knowledge.core.settings import get_settings
from knowledge.services.embedding import EmbeddingProvider, build_embedding_provider
from knowledge.services.rerank import RerankProvider, build_rerank_provider

_ASCII_TOKEN = re.compile(r"[A-Za-z0-9_]+")
_CJK_RUN = re.compile(r"[一-鿿]+")


def ngram_features(text: str) -> Counter:
    lower = str(text or "").lower()
    features: Counter = Counter()
    for token in _ASCII_TOKEN.findall(lower):
        features[token] += 1
    for run in _CJK_RUN.findall(lower):
        if len(run) == 1:
            features[run] += 1
        for index in range(len(run) - 1):
            features[run[index : index + 2]] += 1
    return features


def _cosine(left: Counter, right: Counter) -> float:
    if not left or not right:
        return 0.0
    dot = sum(count * right.get(feature, 0) for feature, count in left.items())
    left_norm = math.sqrt(sum(count * count for count in left.values()))
    right_norm = math.sqrt(sum(count * count for count in right.values()))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


class NgramHashEmbeddingProvider(EmbeddingProvider):
    """Feature-hashed bag of (ASCII word | CJK bigram) features, L2-normalised."""

    provider_name = "offline_ngram"

    def __init__(self, dimensions: int = 256) -> None:
        self.dimensions = dimensions

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            vector = [0.0] * self.dimensions
            for feature, count in ngram_features(text).items():
                digest = hashlib.sha1(feature.encode("utf-8")).digest()
                index = int.from_bytes(digest[:4], "big") % self.dimensions
                sign = 1.0 if digest[4] & 1 else -1.0
                vector[index] += sign * count
            norm = math.sqrt(sum(value * value for value in vector)) or 1.0
            vectors.append([value / norm for value in vector])
        return vectors

    def diagnostics(self) -> dict:
        return {"provider_name": self.provider_name, "dimensions": self.dimensions}


class NgramOverlapRerankProvider(RerankProvider):
    """Bag-of-ngrams cosine + exact-phrase bonus; deterministic and offline."""

    provider_name = "offline_ngram"

    def rerank(self, query: str, documents: list[str]) -> list[float]:
        query_features = ngram_features(query)
        query_lower = str(query or "").strip().lower()
        scores: list[float] = []
        for document in documents:
            score = _cosine(query_features, ngram_features(document))
            if query_lower and query_lower in str(document or "").lower():
                score += 0.2
            scores.append(score)
        return scores


def resolve_providers() -> tuple[EmbeddingProvider, RerankProvider, str]:
    """Return (embedding, rerank, label) per KNOWLEDGE_EVAL_PROVIDER (offline|live)."""
    mode = os.environ.get("KNOWLEDGE_EVAL_PROVIDER", "offline").strip().lower()
    if mode == "live":
        settings = get_settings()
        embedding = build_embedding_provider()
        rerank = build_rerank_provider()
        if embedding.provider_name == "mock" or rerank.provider_name == "mock":
            raise RuntimeError(
                "KNOWLEDGE_EVAL_PROVIDER=live needs MODEL_PROVIDER_MODE=openai_compatible "
                "and MODEL_GATEWAY_BASE_URL; the factory fell back to the mock provider"
            )
        label = f"live:{embedding.provider_name} embedding={settings.embedding_model} rerank={settings.rerank_model}"
        return embedding, rerank, label
    if mode != "offline":
        raise RuntimeError(f"unknown KNOWLEDGE_EVAL_PROVIDER={mode!r}; expected offline or live")
    return NgramHashEmbeddingProvider(), NgramOverlapRerankProvider(), "offline_ngram (stand-in, not a quality reference)"
