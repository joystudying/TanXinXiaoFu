"""Qdrant 向量库（本地嵌入式模式）：dense + sparse 两个命名向量 + RRF 混合检索。

本地模式（QdrantClient(path=...)）无需起服务、落盘持久化；sparse 向量是一等公民，
因此关键词（BM25 稀疏向量）和语义（BGE 稠密向量）都能放进同一个 collection 里融合。
"""
from qdrant_client import QdrantClient, models

from .base import VectorStore


class QdrantVectorStore(VectorStore):
    def __init__(self, path: str):
        self._client = QdrantClient(path=path)

    def recreate(self, collection: str, dim: int) -> None:
        if self._client.collection_exists(collection):
            self._client.delete_collection(collection)
        self._client.create_collection(
            collection_name=collection,
            vectors_config={"dense": models.VectorParams(size=dim, distance=models.Distance.COSINE)},
            sparse_vectors_config={"sparse": models.SparseVectorParams()},
        )

    def upsert(self, collection: str, points: list[dict]) -> None:
        if not points:
            return
        self._client.upsert(
            collection_name=collection,
            points=[
                models.PointStruct(
                    id=p["id"],
                    vector={
                        "dense": p["dense"],
                        "sparse": models.SparseVector(
                            indices=list(p["sparse"].keys()),
                            values=list(p["sparse"].values()),
                        ),
                    },
                    payload=p.get("payload", {}),
                )
                for p in points
            ],
        )

    def hybrid_search(
        self, collection: str, dense: list[float], sparse: dict, limit: int
    ) -> list[dict]:
        if not self._client.collection_exists(collection):
            return []
        result = self._client.query_points(
            collection_name=collection,
            prefetch=[
                models.Prefetch(query=dense, using="dense", limit=limit * 3),
                models.Prefetch(
                    query=models.SparseVector(
                        indices=list(sparse.keys()), values=list(sparse.values())
                    ),
                    using="sparse",
                    limit=limit * 3,
                ),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=limit,
        )
        return [
            {"id": str(p.id), "score": float(p.score), "payload": dict(p.payload or {})}
            for p in result.points
        ]

    def exists(self, collection: str) -> bool:
        return self._client.collection_exists(collection)
