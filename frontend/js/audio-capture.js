/**
 * 麦克风采集封装（真双工底层）
 *
 * 输出：16kHz / 单声道 / 16bit PCM 帧，外加每帧能量值。
 * 这一层不含任何厂商协议——接豆包、阿里、OpenAI 都是这个格式。
 *
 * 同时提供"立刻打断"：本地能量一超阈值就回调，不等服务端往返。
 */

// 相对本模块解析 worklet 路径，无论站点挂在根目录还是子路径都能找到。
const WORKLET_URL = new URL('pcm-worklet.js', import.meta.url).href;

export function audioSupported() {
  return Boolean(navigator.mediaDevices?.getUserMedia) && Boolean(window.AudioContext);
}

export async function createAudioCapture({
  frameMs = 40,
  targetRate = 16000,
  onFrame,        // (Int16Array, ArrayBuffer) => void
  onLevel,        // (number) => void  每帧的 RMS 能量 0~1
  onError,        // (code) => void
} = {}) {
  if (!audioSupported()) {
    onError?.('capture_unsupported');
    return null;
  }

  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        channelCount: 1,
      },
    });
  } catch (e) {
    onError?.('mic_denied');
    return null;
  }

  const ctx = new (window.AudioContext || window.webkitAudioContext)();
  await ctx.audioWorklet.addModule(WORKLET_URL);

  const source = ctx.createMediaStreamSource(stream);
  const node = new AudioWorkletNode(ctx, 'pcm-capture', {
    numberOfInputs: 1,
    numberOfOutputs: 0,
    processorOptions: { targetRate, frameMs },
  });

  node.port.onmessage = (e) => {
    const { buffer, level } = e.data || {};
    if (typeof level === 'number') onLevel?.(level);
    if (buffer) onFrame?.(new Int16Array(buffer), buffer);
  };

  source.connect(node);

  // 播放回声消除后的旁路，防止某些浏览器把 worklet 判定为无声而不驱动
  const silent = ctx.createGain();
  silent.gain.value = 0;
  node.connect(silent);
  silent.connect(ctx.destination);

  return {
    sampleRate: targetRate,
    frameMs,
    async resume() {
      if (ctx.state === 'suspended') await ctx.resume();
    },
    async close() {
      try { node.port.onmessage = null; } catch (e) { /* 忽略 */ }
      try { source.disconnect(); } catch (e) { /* 忽略 */ }
      try { node.disconnect(); } catch (e) { /* 忽略 */ }
      stream.getTracks().forEach((t) => t.stop());
      try { await ctx.close(); } catch (e) { /* 忽略 */ }
    },
    get state() { return ctx.state; },
  };
}
