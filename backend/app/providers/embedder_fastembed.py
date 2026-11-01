"""本地稠密向量：fastembed 跑 BGE 中文模型（onnx 后端，无 torch、离线无密钥）。

维度随模型固定：bge-small-zh-v1.5 = 512，bge-m3 = 1024。
换模型只改 .env 的 EMBEDDING_MODEL，接口不变。
"""
from .base import DenseEmbedder


class FastEmbedDenseEmbedder(DenseEmbedder):
    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5"):
        # 延迟导入：不检索时无需加载 onnxruntime / 下载模型
        from fastembed import TextEmbedding

        self._model_name = model_name
        self._model = TextEmbedding(model_name)
        self._dim = None

    def embed(self, texts: list[str]) -> list[list[float]]:
        texts = [t or "" for t in texts]
        if not texts:
            return []
        vectors = [v.tolist() for v in self._model.embed(texts)]
        if self._dim is None and vectors:
            self._dim = len(vectors[0])
        return vectors

    def dim(self) -> int:
        if self._dim is None:
            self.embed([""])  # 触发一次前向，拿到维度
        return self._dim or 0
