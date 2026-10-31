"""独立 FunASR 识别服务（自部署、免费）。

用法（建议用 Python 3.10/3.11 的独立环境，因为 FunASR 对 3.12+ 支持滞后）：
    pip install funasr fastapi uvicorn
    python services/funasr_server.py

主后端通过 FUNASR_SERVICE_URL=http://127.0.0.1:8001/transcribe 调用这里。
首次运行会自动下载 paraformer-zh 模型（约 1GB），之后离线可用。

注意：入参约定为 PCM16 / 16kHz / 单声道音频（前端录音器已按此规格输出）。
"""
import base64
import tempfile
import wave

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="FunASR 识别服务")

_model = None


class TranscribeItem(BaseModel):
    audio_b64: str
    format: str = "pcm16"


@app.on_event("startup")
def _load_model() -> None:
    global _model
    from funasr import AutoModel

    # 标点模型 ct-punc 首次下载易超时，暂不启用（不影响识别，仅不加标点）
    _model = AutoModel(model="paraformer-zh", vad_model="fsmn-vad", disable_update=True)


def _pcm16_to_wav(audio: bytes) -> str:
    """把 PCM16 16k 单声道转成临时 wav 文件供 FunASR 读取。"""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        path = f.name
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(audio)
    return path


@app.post("/transcribe")
def transcribe(item: TranscribeItem) -> dict:
    if _model is None:
        return {"text": "", "error": "model not loaded"}
    audio = base64.b64decode(item.audio_b64)
    wav_path = _pcm16_to_wav(audio)
    try:
        result = _model.generate(input=wav_path)
        text = result[0]["text"] if result else ""
        return {"text": text}
    finally:
        import os

        os.remove(wav_path)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8001)
