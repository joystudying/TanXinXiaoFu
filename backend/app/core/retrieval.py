"""案例混合检索：把 cases 表索引进 Qdrant（dense + sparse），关键词 + 语义融合。

- 关键词侧：jieba 分词 + BM25 稀疏向量（见 bm25.py）
- 语义侧：BGE 稠密向量（fastembed）
- 融合：Qdrant hybrid search + RRF

检索是同步/CPU 密集操作，统一用 asyncio.to_thread 丢线程池，避免阻塞事件循环；
单用户场景用一把 asyncio.Lock 串行化，避免 fastembed / Qdrant 本地模式的并发问题。
"""
import asyncio
import uuid

from ..config import get_settings
from ..providers.embedder_fastembed import FastEmbedDenseEmbedder
from ..providers.vectorstore_qdrant import QdrantVectorStore
from ..repo import case_to_dict, list_cases
from .bm25 import ChineseBM25
from .cases import category_label, public_summary

COLLECTION = "cases"

_lock = asyncio.Lock()
_embedder: FastEmbedDenseEmbedder | None = None
_store: QdrantVectorStore | None = None
_bm25 = ChineseBM25()
_cases: dict[str, dict] = {}   # case_id -> 完整 case dict（含私有层，仅服务端内存）
_texts: dict[str, str] = {}    # case_id -> 检索文本


def _embedder_() -> FastEmbedDenseEmbedder:
    global _embedder
    if _embedder is None:
        _embedder = FastEmbedDenseEmbedder(get_settings().embedding_model)
    return _embedder


def _store_() -> QdrantVectorStore:
    global _store
    if _store is None:
        _store = QdrantVectorStore(get_settings().qdrant_path)
    return _store


def _point_id(case_id: str) -> str:
    """Qdrant 点 ID 只接受 int / UUID；用确定性 UUID 映射案例字符串 ID。"""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, case_id))


def searchable_text(c: dict) -> str:
    """案例 -> 检索文本：分类中文名 + 公开字段 + 标签。"""
    parts = [
        category_label(c.get("category", "")),
        c.get("name", ""),
        c.get("grade_major", ""),
        c.get("tagline", ""),
        c.get("quote", ""),
        c.get("public_background", ""),
        c.get("training_focus", ""),
        " ".join(c.get("tags") or []),
    ]
    return " ".join(p for p in parts if p).strip()


async def reindex_all() -> None:
    """重建索引：读全部案例 -> 算 BM25 语料 -> 编码 dense/sparse -> 重写 Qdrant。"""
    async with _lock:
        cases = [case_to_dict(c) for c in await list_cases()]
        texts = {c["id"]: searchable_text(c) for c in cases}
        _cases.clear()
        _cases.update({c["id"]: c for c in cases})
        _texts.clear()
        _texts.update(texts)

        ids = list(texts.keys())
        docs = list(texts.values())

        embedder = _embedder_()
        store = _store_()

        _bm25.build_vocab(docs)
        dense = await asyncio.to_thread(embedder.embed, docs)
        dim = len(dense[0]) if dense else embedder.dim()

        store.recreate(COLLECTION, dim)
        points = [
            {
                "id": _point_id(ids[i]),
                "dense": dense[i],
                "sparse": _bm25.encode_doc(docs[i]),
                "payload": {"case_id": ids[i]},
            }
            for i in range(len(ids))
        ]
        await asyncio.to_thread(store.upsert, COLLECTION, points)


async def search(q: str, limit: int = 10) -> list[dict]:
    """混合检索，返回 [{...public_summary, score, matched_by}]，按相关度降序。"""
    q = (q or "").strip()
    if not q:
        return []

    if not _cases:
        await reindex_all()
    if not _cases:
        return []

    async with _lock:
        embedder = _embedder_()
        store = _store_()
        dense = (await asyncio.to_thread(embedder.embed, [q]))[0]
        sparse = _bm25.encode_query(q)
        query_terms = _bm25.matched_terms(q)
        hits = await asyncio.to_thread(
            store.hybrid_search, COLLECTION, dense, sparse, limit
        )
        cases = dict(_cases)
        texts = dict(_texts)

    results = []
    for h in hits:
        case_id = (h.get("payload") or {}).get("case_id") or h["id"]
        c = cases.get(case_id)
        if c is None:
            continue
        text = texts.get(case_id, "")
        matched_by = "keyword" if any(t in text for t in query_terms) else "semantic"
        item = public_summary(c)
        item["score"] = round(float(h["score"]), 4)
        item["matched_by"] = matched_by
        results.append(item)
    return results
