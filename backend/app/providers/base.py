"""可插拔 Provider 接口。

每个环节（ASR / LLM / TTS）都只面向接口编程，具体厂商在实现类里切换，
对应文档「不依赖某一家模型或特定框架」的 Harness 约束。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMResult:
    text: str
    # 学生情绪标签，后续传给 IndexTTS2 的 8 维情绪向量；当前先留空
    emotion: str | None = None


@dataclass
class TTSResult:
    audio: bytes
    format: str = "mp3"


class ASRProvider(ABC):
    @abstractmethod
    async def transcribe(self, audio: bytes, audio_format: str = "pcm16") -> str:
        """音频 -> 文字。"""


class LLMProvider(ABC):
    @abstractmethod
    async def chat(self, messages: list[dict], **kwargs) -> LLMResult:
        """带上下文的对话 -> 学生回复。"""


class TTSProvider(ABC):
    @abstractmethod
    async def synthesize(self, text: str, **kwargs) -> TTSResult:
        """文字 -> 语音。"""


@dataclass
class EvaluationResult:
    total_score: int
    dimensions: list[dict]  # [{name, score, comment, evidence:[...]}, ...]
    summary: str
    suggestions: str


class EvaluatorProvider(ABC):
    @abstractmethod
    async def evaluate(self, transcript: str, rubric: str, **kwargs) -> EvaluationResult:
        """对话转写 + 评分要点 -> 结构化复盘评价。"""


class DenseEmbedder(ABC):
    """文本 -> 稠密向量（可插拔 embedding，如本地 BGE / 任意 OpenAI 兼容 API）。"""

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """一批文本 -> 一批等长向量。"""

    @abstractmethod
    def dim(self) -> int:
        """向量维度。"""


class VectorStore(ABC):
    """向量库（可插拔，如 Qdrant / Milvus / pgvector），支持 dense+sparse 混合检索。"""

    @abstractmethod
    def recreate(self, collection: str, dim: int) -> None:
        """（重）建集合：稠密向量 + 稀疏向量两个命名向量。"""

    @abstractmethod
    def upsert(self, collection: str, points: list[dict]) -> None:
        """写入/覆盖一批点。point: {id, dense:[...], sparse:{idx:val}, payload:{...}}"""

    @abstractmethod
    def hybrid_search(
        self, collection: str, dense: list[float], sparse: dict, limit: int
    ) -> list[dict]:
        """dense + sparse 双路召回 + RRF 融合，返回 [{id, score}]。"""

    @abstractmethod
    def exists(self, collection: str) -> bool:
        """集合是否存在且非空。"""
