/**
 * 开口检测（设计文档 8.3）——用能量判断"用户开口"，比等识别 interim 快 1~2 秒。
 *
 * 调参提示：
 *  - threshold 28 / 三帧触发只是起点，实际要按房间噪音校准；
 *  - 只在朗读期间开启，并且要在朗读开始 300ms 后再开，否则会被自己的扬声器触发。
 */

export async function createBargeInWatcher({
  threshold = 28,
  framesToTrigger = 3,
  pollMs = 60,
} = {}) {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
  });

  const Ctx = window.AudioContext || window.webkitAudioContext;
  const ctx = new Ctx();
  const src = ctx.createMediaStreamSource(stream);
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 512;
  src.connect(analyser);

  const buf = new Uint8Array(analyser.frequencyBinCount);
  let hot = 0;
  let timer = null;
  let onBarge = null;
  let armed = false;

  const tick = () => {
    if (!armed) return;
    analyser.getByteFrequencyData(buf);
    let sum = 0;
    for (let i = 0; i < buf.length; i += 1) sum += buf[i];
    const avg = sum / buf.length;
    hot = avg > threshold ? hot + 1 : Math.max(0, hot - 1);
    if (hot >= framesToTrigger) {
      hot = 0;
      armed = false;                 // 一次朗读只触发一次
      onBarge?.();
    }
  };

  return {
    /** 开始监听；handler 在检测到开口时被调用一次 */
    start(handler) {
      onBarge = handler;
      hot = 0;
      armed = true;
      if (!timer) timer = setInterval(tick, pollMs);
    },
    /** 暂停触发（不在朗读期间就别开） */
    disarm() { armed = false; },
    stop() {
      if (timer) clearInterval(timer);
      timer = null;
      armed = false;
      stream.getTracks().forEach((t) => t.stop());
      ctx.close().catch(() => {});
    },
    get listening() { return timer !== null; },
  };
}

/** 当前环境能否做开口检测 */
export function canWatchBargeIn() {
  return Boolean(navigator.mediaDevices?.getUserMedia)
    && Boolean(window.AudioContext || window.webkitAudioContext);
}
