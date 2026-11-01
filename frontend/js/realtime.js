/**
 * 真双工实时语音（原生端到端模型）
 *
 * 链路：麦克风 16k PCM → /ws/voice → 火山端到端模型 → 24k float32 音频 → 播放
 * 中间不经过任何文字模型，学生的话由端到端模型自己组织和发声。
 *
 * 三个要点：
 *  1. 上行必须是 int16 / 16k / 单声道，20ms 一帧（640 字节）
 *  2. 下行是 float32 / 24k / 单声道 —— 直接就是 Web Audio 要的格式，别当 int16 读
 *  3. 服务端输出电平偏低（实测 RMS 约 −39 dBFS），播放要加增益
 */
import { createAudioCapture } from './audio-capture.js';

const GAIN = 3.0;              // ≈ +9.5 dB，把 −39 dBFS 抬到可用音量
const SPEECH_LEVEL = 0.03;     // 本地判断"用户开口"的能量阈值

export function realtimeSupported() {
  return Boolean(
    navigator.mediaDevices?.getUserMedia
    && window.AudioWorkletNode
    && window.WebSocket,
  );
}

/**
 * 开始一次实时通话。
 * 返回 { stop() } —— 调用即结束。
 */
export async function startRealtime({
  onStatus,      // (state, text) => void   state: connecting/ready/listening/speaking/closed/error
  onTeacherText, // (text) => void   老师这句被识别成的文字（流式）
  onStudentText, // (text) => void   学生说的文字
  onError,
} = {}) {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const url = `${proto}://${location.host}/ws/voice`;

  const ws = new WebSocket(url);
  ws.binaryType = 'arraybuffer';

  let playCtx = null;
  let nextTime = 0;
  const sources = new Set();
  let capture = null;
  let stopped = false;

  function ensurePlayCtx() {
    if (!playCtx) {
      playCtx = new (window.AudioContext || window.webkitAudioContext)();
      nextTime = playCtx.currentTime;
    }
    return playCtx;
  }

  /** float32(24k) → 排进播放队列，无缝衔接 */
  function enqueueAudio(buffer) {
    const samples = new Float32Array(buffer);
    if (!samples.length) return;
    const ctx = ensurePlayCtx();
    if (ctx.state === 'suspended') ctx.resume();

    const audioBuf = ctx.createBuffer(1, samples.length, 24000);
    audioBuf.copyToChannel(samples, 0);

    const gain = ctx.createGain();
    gain.gain.value = GAIN;

    const src = ctx.createBufferSource();
    src.buffer = audioBuf;
    src.connect(gain);
    gain.connect(ctx.destination);

    const startAt = Math.max(nextTime, ctx.currentTime + 0.01);
    src.start(startAt);
    nextTime = startAt + audioBuf.duration;

    sources.add(src);
    src.onended = () => sources.delete(src);
    onStatus?.('speaking', '学生在说…');
  }

  /** 打断播放（用户开口时本地立刻静音，不等服务端） */
  function flushPlayback() {
    for (const s of sources) {
      try { s.stop(); } catch (e) { /* 忽略 */ }
    }
    sources.clear();
    nextTime = playCtx ? playCtx.currentTime : 0;
  }

  ws.onopen = async () => {
    onStatus?.('connecting', '正在建立实时语音…');
  };

  ws.onmessage = async (ev) => {
    if (typeof ev.data !== 'string') {
      enqueueAudio(ev.data);          // 二进制 = 学生音频
      return;
    }
    let msg;
    try { msg = JSON.parse(ev.data); } catch (e) { return; }

    if (msg.type === 'ready') {
      onStatus?.('ready', '可以说话了');
      await startCapture();
      return;
    }
    if (msg.type === 'error') {
      onStatus?.('error', msg.message || '实时语音出错');
      onError?.(msg.code, msg.message);
      return;
    }
    if (msg.type === 'event') {
      const p = msg.payload || {};
      if (msg.event === 451) {                     // 老师这句的识别结果
        const t = p.text || (p.extra && p.extra.origin_text);
        if (t) onTeacherText?.(t);
      } else if (msg.event === 550) {              // 学生的话
        const t = p.text || p.content;
        if (t) onStudentText?.(t);
      } else if (msg.event === 459) {              // 老师说完
        onStatus?.('listening', '听着，你继续说');
      }
    }
  };

  ws.onerror = () => {
    onStatus?.('error', '实时语音连接失败');
    onError?.('ws_error', '连接失败');
  };

  ws.onclose = () => {
    if (!stopped) onStatus?.('closed', '实时通话已断开');
    cleanup();
  };

  async function startCapture() {
    // 有些环境里 getUserMedia 会一直挂着（没有麦克风、权限弹窗未处理），
    // 必须有超时，否则界面停在"可以说话了"却永远说不了。
    let timer = null;
    const timeout = new Promise((resolve) => {
      timer = setTimeout(() => resolve(null), 8000);
    });

    capture = await Promise.race([createAudioCapture({
      frameMs: 20,                       // 端到端模型要求 20ms 一帧
      targetRate: 16000,
      onFrame: (_i16, buf) => {
        if (ws.readyState === WebSocket.OPEN) ws.send(buf);
      },
      onLevel: (level) => {
        // 用户一开口就把本地播放掐掉，不等服务端判断
        if (level > SPEECH_LEVEL && sources.size > 0) {
          flushPlayback();
          onStatus?.('listening', '你打断了他');
        }
      },
      onError: (code) => {
        onStatus?.('error', '麦克风不可用');
        onError?.(code, '麦克风不可用');
      },
    }), timeout]);
    clearTimeout(timer);

    if (!capture) {
      onStatus?.('error', '拿不到麦克风（8 秒无响应）');
      onError?.('mic_timeout', '拿不到麦克风。检查是否允许了麦克风权限，或换一台有麦克风的电脑。');
      return;
    }
    await capture.resume();
    onStatus?.('listening', '正在听你说…');
  }

  function cleanup() {
    try { capture?.close(); } catch (e) { /* 忽略 */ }
    capture = null;
    flushPlayback();
    try { playCtx?.close(); } catch (e) { /* 忽略 */ }
    playCtx = null;
  }

  return {
    stop() {
      stopped = true;
      try {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'finish' }));
        }
        ws.close();
      } catch (e) { /* 忽略 */ }
      cleanup();
    },
    flush: flushPlayback,
  };
}
