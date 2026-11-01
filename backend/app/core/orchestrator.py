"""对话编排：一轮对练的完整闭环 ASR -> LLM -> TTS。

- 文字模式：text 直接进 LLM
- 语音模式：audio 先过 ASR 得到 text，再进 LLM
之后统一：LLM 产出学生回复 -> TTS 合成语音 -> 返回 {文字 + 音频 + 情绪}。
"""
import base64
from dataclasses import dataclass, field

from ..providers.base import ASRProvider, LLMProvider, TTSProvider
from .role import RoleConfig, build_system_prompt


@dataclass
class SessionState:
    session_id: str
    role: RoleConfig
    messages: list[dict] = field(default_factory=list)


class Orchestrator:
    def __init__(self, llm: LLMProvider, asr: ASRProvider, tts: TTSProvider):
        self.llm = llm
        self.asr = asr
        self.tts = tts

    def new_session(self, session_id: str, role: RoleConfig) -> SessionState:
        return SessionState(
            session_id=session_id,
            role=role,
            messages=[{"role": "system", "content": build_system_prompt(role)}],
        )

    async def handle_turn(
        self,
        state: SessionState,
        *,
        text: str | None = None,
        audio: bytes | None = None,
        audio_format: str = "pcm16",
    ) -> dict:
        """处理一轮，返回 {input_text, text, emotion, audio_b64, audio_format, note}。

        input_text 是老师这一侧的文字（文字模式即入参，语音模式即 ASR 转写结果），
        供上层落库复盘；text 仍是学生的回复。
        """
        if text is None and audio is not None:
            text = await self.asr.transcribe(audio, audio_format)
            if not text.strip():
                return {
                    "text": "",
                    "emotion": None,
                    "audio_b64": None,
                    "audio_format": None,
                    "note": "语音未识别到内容（可能 ASR 未接入或音频为空）",
                }

        if not text or not text.strip():
            return {
                "text": "",
                "emotion": None,
                "audio_b64": None,
                "audio_format": None,
                "note": "空输入",
            }

        state.messages.append({"role": "user", "content": text})
        result = await self.llm.chat(state.messages)
        reply = result.text.strip()
        if reply:
            state.messages.append({"role": "assistant", "content": reply})

        tts = await self.tts.synthesize(reply) if reply else None
        return {
            "input_text": text,
            "text": reply,
            "emotion": result.emotion,
            "audio_b64": base64.b64encode(tts.audio).decode() if tts and tts.audio else None,
            "audio_format": tts.format if tts else None,
            "note": None,
        }
