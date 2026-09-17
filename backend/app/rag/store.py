"""向量存储：embedding 以 BLOB 存 SQLite，查询时内存矩阵 + 余弦相似度 Top-K。

演示规模（万级分片内）性能足够，接口与 Milvus/Chroma 等专业向量库一致，可平滑替换。
"""
from __future__ import annotations

import threading

import numpy as np
from sqlalchemy.orm import Session

from app.db.models import Chunk


class VectorStore:
    def __init__(self):
        self._cache: dict[str, tuple[np.ndarray, list[dict]]] = {}
        self._lock = threading.Lock()

    def _load_dataset(self, db: Session, dataset_id: str) -> tuple[np.ndarray, list[dict]]:
        with self._lock:
            if dataset_id in self._cache:
                return self._cache[dataset_id]
        rows = (
            db.query(Chunk)
            .filter(Chunk.dataset_id == dataset_id)
            .order_by(Chunk.idx)
            .all()
        )
        if not rows:
            return np.zeros((0, 1), dtype=np.float32), []
        dim = rows[0].dim
        matrix = np.zeros((len(rows), dim), dtype=np.float32)
        metas: list[dict] = []
        for i, r in enumerate(rows):
            matrix[i] = np.frombuffer(r.embedding, dtype=np.float32)[:dim]
            metas.append(
                {
                    "chunk_id": r.id,
                    "document_id": r.document_id,
                    "dataset_id": r.dataset_id,
                    "idx": r.idx,
                    "content": r.content,
                }
            )
        with self._lock:
            self._cache[dataset_id] = (matrix, metas)
        return matrix, metas

    def invalidate(self, dataset_id: str | None = None) -> None:
        with self._lock:
            if dataset_id is None:
                self._cache.clear()
            else:
                self._cache.pop(dataset_id, None)

    def search(
        self,
        db: Session,
        dataset_ids: list[str],
        query_embedding: np.ndarray,
        top_k: int = 4,
    ) -> list[dict]:
        results: list[dict] = []
        q = np.asarray(query_embedding, dtype=np.float32).reshape(-1)
        for ds_id in dataset_ids:
            matrix, metas = self._load_dataset(db, ds_id)
            if matrix.shape[0] == 0:
                continue
            # 余弦相似度（向量均已归一化，点积即相似度）
            scores = matrix @ q
            top_idx = np.argsort(-scores)[:top_k]
            for i in top_idx:
                results.append({**metas[i], "score": round(float(scores[i]), 4)})
        results.sort(key=lambda r: -r["score"])
        return results[:top_k]


vector_store = VectorStore()
