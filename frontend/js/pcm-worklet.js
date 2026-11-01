/**
 * 采集线程：把麦克风音频降采样成 16kHz / 单声道 / 16bit PCM，
 * 按固定时长切帧（默认 40ms）回传主线程，同时算一个能量值供本地打断判断。
 *
 * 所有主流实时语音服务（豆包 / 阿里 / OpenAI）上传格式都是 PCM16 16k 单声道，
 * 所以这一层与厂商无关。
 */
class PcmCapture extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const opt = options?.processorOptions || {};
    this.targetRate = opt.targetRate || 16000;
    this.frameMs = opt.frameMs || 40;
    this.frameSamples = Math.round((this.targetRate * this.frameMs) / 1000);

    this.step = sampleRate / this.targetRate; // 降采样步长
    this.cursor = 0;
    this.prev = 0;
    this.frame = new Int16Array(this.frameSamples);
    this.filled = 0;
  }

  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (!channel) return true;

    for (let i = 0; i < channel.length; i += 1) {
      // 线性插值降采样：cursor 每步跨 3 个原始样本（48k → 16k）
      while (this.cursor <= 1) {
        const sample = this.prev + (channel[i] - this.prev) * this.cursor;
        const clipped = Math.max(-1, Math.min(1, sample));
        this.frame[this.filled] = clipped < 0 ? clipped * 0x8000 : clipped * 0x7fff;
        this.filled += 1;

        if (this.filled >= this.frameSamples) {
          let sum = 0;
          for (let k = 0; k < this.frame.length; k += 1) {
            const v = this.frame[k] / 0x8000;
            sum += v * v;
          }
          const level = Math.sqrt(sum / this.frame.length);
          const out = this.frame.buffer.slice(0);
          this.port.postMessage({ buffer: out, level }, [out]);
          this.frame = new Int16Array(this.frameSamples);
          this.filled = 0;
        }
        this.cursor += this.step;
      }
      this.cursor -= 1;
      this.prev = channel[i];
    }
    return true;
  }
}

registerProcessor('pcm-capture', PcmCapture);
