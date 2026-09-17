"""Embedding 抽象：本地哈希向量（离线可用）+ OpenAI 兼容 Embedding API。"""
from __future__ import annotations

import hashlib
import re

import httpx
import numpy as np

from app.config import Settings


class LocalHashEmbedder:
    """字符 n-gram 哈希嵌入：零依赖、离线可用，适合演示与小规模语料检索。"""

    name = "local"

    def __init__(self, dim: int = 512):
        self.dim = dim

    def _tokenize(self, text: str) -> list[str]:
        text = text.lower()
        tokens = re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]", text)
        # 中文补充 bigram，增强语义区分度
        cjk = re.findall(r"[\u4e00-\u9fff]+", text)
        for seg in cjk:
            tokens += [seg[i : i + 2] for i in range(len(seg) - 1)]
        return tokens

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, text in enumerate(texts):
            for tok in self._tokenize(text):
                h = int(hashlib.md5(tok.encode("utf-8")).hexdigest()[:8], 16)
                out[i, h % self.dim] += 1.0
            norm = np.linalg.norm(out[i])
            if norm > 0:
                out[i] /= norm
        return out


class OpenAIEmbedder:
    name = "openai_compatible"

    def __init__(self, settings: Settings):
        self.base_url = settings.embedding_base_url.rstrip("/")
        self.api_key = settings.embedding_api_key
        self.model = settings.embedding_model

    def embed(self, texts: list[str]) -> np.ndarray:
        with httpx.Client(timeout=60) as client:
            resp = client.post(
                f"{self.base_url}/embeddings",
                json={"model": self.model, "input": texts},
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            resp.raise_for_status()
            data = resp.json()["data"]
        vecs = [d["embedding"] for d in data]
        return np.array(vecs, dtype=np.float32)


_EMBEDDER = None


def get_embedder(settings: Settings):
    global _EMBEDDER
    if _EMBEDDER is None:
        if settings.embedding_provider == "openai_compatible" and settings.embedding_api_key:
            _EMBEDDER = OpenAIEmbedder(settings)
        else:
            _EMBEDDER = LocalHashEmbedder(settings.embedding_dim)
    return _EMBEDDER


def reset_embedder() -> None:
    global _EMBEDDER
    _EMBEDDER = None
