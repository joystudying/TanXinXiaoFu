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
// 打断判定要迟钝一点：喇叭的声音会串进麦克风，阈值太低会把学生自己的话掐断。
// 实测正常说话 RMS 约 0.05~0.30，房间噪声 0.005~0.03。
const INTERRUPT_LEVEL = 0.18;  // 连续超过这个能量才算"老师真的开口"
const INTERRUPT_FRAMES = 6;    // 约 80ms，避免咳嗽、键盘声误触
const GUARD_MS = 400;          // 开始播放后这段时间内不判打断（躲开起播的爆音）

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
  let muted = false;              // 播放期间上行静音，防止回声被模型当成插话
  let gateOpen = true;            // 按住说话模式下，只有按着才为 true
  // 流式结果会一个字一个字地来，必须攒成一句再交给界面，
  // 否则每来一个增量就往对话框塞一条，轮次会一路涨到上百。
  let asrBuf = '';
  let chatBuf = '';

  function mergeText(prev, next) {
    if (!next) return prev;
    if (!prev) return next;
    if (next.startsWith(prev)) return next;      // 累积式下发
    if (prev.startsWith(next)) return prev;      // 重复下发
    return prev + next;                          // 增量式下发
  }
  let playingSince = 0;
  let hotFrames = 0;

  // 诊断计数：出问题时能一眼看出是被本地掐了还是没收到
  const stats = { chunks: 0, bytes: 0, flushed: 0, flushesByBarge: 0, mutes: 0, sent: 0 };
  window.__rt = stats;

  function setMuted(next) {
    if (muted === next) return;
    muted = next;
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: next ? 'mute' : 'unmute' }));
      stats.mutes += 1;
    }
  }

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
    stats.chunks += 1;
    stats.bytes += buffer.byteLength;
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
    if (sources.size === 1) playingSince = performance.now();
    src.onended = () => {
      sources.delete(src);
      if (sources.size === 0) {
        // 尾音也会被麦克风收进去，延迟一点再放开
        setTimeout(() => { if (sources.size === 0) setMuted(false); }, 250);
      }
    };
    onStatus?.('speaking', '学生在说…');
  }

  /** 打断播放（用户开口时本地立刻静音，不等服务端） */
  function flushPlayback() {
    stats.flushed += 1;
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
      if (msg.event === 451) {                     // 老师这句的识别增量
        const t = p.text || (p.extra && p.extra.origin_text);
        if (t) asrBuf = mergeText(asrBuf, t);
      } else if (msg.event === 459) {              // 老师说完 → 出一整句
        if (asrBuf.trim()) onTeacherText?.(asrBuf.trim());
        asrBuf = '';
        onStatus?.('listening', '听着，你继续说');
      } else if (msg.event === 550) {              // 学生的回答增量
        const t = p.text || p.content;
        if (t) chatBuf = mergeText(chatBuf, t);
      } else if (msg.event === 559) {              // 学生说完 → 出一整句
        if (chatBuf.trim()) onStudentText?.(chatBuf.trim());
        chatBuf = '';
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
        if (muted || !gateOpen) return;    // 播放期间静音 / 没按住就不发
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(buf);
          stats.sent += 1;
        }
      },
      onLevel: (level) => {
        if (sources.size === 0) { hotFrames = 0; return; }
        if (performance.now() - playingSince < GUARD_MS) return;   // 起播保护

        if (level > INTERRUPT_LEVEL) {
          hotFrames += 1;
          if (hotFrames >= INTERRUPT_FRAMES) {
            stats.flushesByBarge += 1;
            flushPlayback();
            // 告诉服务端：别再推刚才那段音频了，否则本地停了它还会接着播
            if (ws.readyState === WebSocket.OPEN) {
              ws.send(JSON.stringify({ type: 'cancel' }));
              stats.cancels = (stats.cancels || 0) + 1;
            }
            onStatus?.('listening', '你打断了他');
          }
        } else {
          hotFrames = 0;
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
    /** 按住说话：true=正在按住（允许上传），false=松开（停止上传） */
    setTransmitting(on) {
      gateOpen = Boolean(on);
      if (!on) setMuted(true);
      else setMuted(false);
    },
    stats,
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
