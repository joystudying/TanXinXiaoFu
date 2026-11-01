"""中文 BM25 稀疏向量：jieba 分词 + 稳定哈希到固定维度 + 语料 IDF。

为什么自建：fastembed 的 BM25 分词只支持英文等西文（supported_languages 无中文），
Qdrant 本地模式又不支持 full-text 索引（需要 server）。这里用 jieba 把关键词也变成
稀疏向量，和稠密向量一起在 Qdrant 里做 hybrid + RRF，等价于「关键词 + 语义」混合检索。

BM25 拆成「文档向量 × 查询向量」的内积（标准稀疏检索做法）：
  文档侧 = tf * (k1+1) / (tf + k1*(1 - b + b*dl/avgdl))   —— 饱和 + 长度归一化，不含 IDF
  查询侧 = idf * (k1+1)                                      —— 词重要性
  内积  = Σ idf * tf*(k1+1)/(tf + k1*(1-b+b*dl/avgdl))     = BM25 分数
"""
import hashlib
import math

import jieba

# 稀疏向量哈希空间维度（约 104 万）。语料几千词时碰撞概率可忽略。
SPARSE_DIM = 1 << 20

# 高频无信息词，直接过滤（jieba 之外再加一道保险）
_STOPWORDS = {
    "的", "了", "是", "在", "和", "与", "就", "都", "也", "很", "又", "还",
    "把", "被", "这", "那", "有", "没", "不", "我", "你", "他", "她", "它",
    "我们", "你们", "他们", "一个", "一些", "这个", "那个", "什么", "怎么",
}


def tokenize(text: str) -> list[str]:
    """中文分词：只保留有意义的词（去空格/标点/停用词）。"""
    tokens = []
    for w in jieba.cut(text or ""):
        w = w.strip()
        if w and w not in _STOPWORDS and not all(ch.isspace() or ch in "，。、；：？！“”‘’（）()[]{}·…—-" for ch in w):
            tokens.append(w)
    return tokens


def _hash_token(token: str) -> int:
    """稳定哈希（跨进程一致，不能用 Python 内置 hash）。"""
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") % SPARSE_DIM


class ChineseBM25:
    def __init__(self, k1: float = 1.2, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self._df: dict[str, int] = {}
        self._n_docs = 0
        self._avgdl = 1.0

    def build_vocab(self, docs: list[str]) -> None:
        """用整批语料统计 df / avgdl，供编码时的 IDF 与长度归一化使用。"""
        df: dict[str, int] = {}
        total_len = 0
        for text in docs:
            tokens = tokenize(text)
            total_len += len(tokens)
            for term in set(tokens):
                df[term] = df.get(term, 0) + 1
        self._n_docs = len(docs)
        self._df = df
        self._avgdl = total_len / self._n_docs if self._n_docs else 1.0

    def _idf(self, term: str) -> float:
        df = self._df.get(term, 0)
        n = self._n_docs
        return math.log((n - df + 0.5) / (df + 0.5) + 1.0) + 1e-6

    def encode_doc(self, text: str) -> dict[int, float]:
        """文档 -> 稀疏向量（BM25 饱和 + 长度归一化，不含 IDF）。"""
        tokens = tokenize(text)
        tf: dict[str, int] = {}
        for t in tokens:
            tf[t] = tf.get(t, 0) + 1
        dl = len(tokens)
        norm = self.k1 * (1 - self.b + self.b * dl / self._avgdl)
        vec: dict[int, float] = {}
        for term, cnt in tf.items():
            w = cnt * (self.k1 + 1) / (cnt + norm)
            idx = _hash_token(term)
            vec[idx] = vec.get(idx, 0.0) + w
        return vec

    def encode_query(self, text: str) -> dict[int, float]:
        """查询 -> 稀疏向量（IDF * (k1+1)），与文档向量内积即 BM25 分数。"""
        vec: dict[int, float] = {}
        for term in tokenize(text):
            idx = _hash_token(term)
            w = self._idf(term) * (self.k1 + 1)
            vec[idx] = max(vec.get(idx, 0.0), w)
        return vec

    def matched_terms(self, text: str) -> set[str]:
        """返回文本中的关键词（供「关键词命中」判定/展示）。"""
        return set(tokenize(text))
