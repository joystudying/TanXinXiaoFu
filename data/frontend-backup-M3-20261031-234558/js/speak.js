/**
 * 朗读封装（设计文档 8.2）
 * 长文本按句切段排队，规避某些浏览器一次 speak() 长文本会中途卡住的问题。
 */

let voices = [];
let ready = null;

function loadVoices() {
  if (ready) return ready;
  ready = new Promise((resolve) => {
    const read = () => {
      voices = window.speechSynthesis.getVoices() || [];
      if (voices.length) resolve(voices);
    };
    read();                                                  // 有的浏览器首次就返回
    window.speechSynthesis.addEventListener('voiceschanged', read, { once: true });
    setTimeout(() => resolve(voices), 2000);                 // 兜底：2 秒还没来就先继续
  });
  return ready;
}

export async function pickChineseVoice(prefer = /Xiaoxiao|Huihui|Yunxi|Natural|Tingting/i) {
  const list = await loadVoices();
  return list.find((v) => /^zh/i.test(v.lang) && prefer.test(v.name))
    || list.find((v) => /^zh/i.test(v.lang))
    || null;
}

export function isSupported() {
  return 'speechSynthesis' in window;
}

/** 超过 80 字就按句切段 */
export function splitSentences(text, maxLen = 80) {
  if (text.length <= maxLen) return [text];
  const parts = text.match(/[^。！？!?\n]+[。！？!?]?/g) || [text];
  const out = [];
  let buf = '';
  for (const p of parts) {
    if ((buf + p).length > maxLen && buf) {
      out.push(buf);
      buf = p;
    } else {
      buf += p;
    }
  }
  if (buf) buf = buf.trim() && buf;
  if (buf) out.push(buf);
  return out.filter(Boolean);
}

let currentResolve = null;
let cancelled = false;

function speakOne(text, voice) {
  return new Promise((resolve) => {
    const u = new SpeechSynthesisUtterance(text);
    u.lang = 'zh-CN';
    if (voice) u.voice = voice;
    u.rate = 1.0;
    u.pitch = 1.0;
    u.volume = 1.0;
    u.onend = () => resolve(true);
    u.onerror = () => resolve(false);
    currentResolve = resolve;
    window.speechSynthesis.speak(u);
  });
}

/**
 * 朗读。返回 true 表示正常读完，false 表示中途被打断或失败。
 */
export async function speak(text, { onStart, onEnd, onError } = {}) {
  if (!isSupported()) {
    onError?.('tts_failed');
    return false;
  }
  window.speechSynthesis.cancel();   // 先清队列，避免叠加
  cancelled = false;

  const voice = await pickChineseVoice();
  const chunks = splitSentences(text);

  let started = false;
  for (const chunk of chunks) {
    if (cancelled) break;
    if (!started) {
      started = true;
      onStart?.();
    }
    const ok = await speakOne(chunk, voice);
    if (!ok) {
      if (!cancelled) onError?.('tts_failed');
      break;
    }
  }
  onEnd?.();
  return !cancelled;
}

export function stopSpeaking() {
  cancelled = true;
  try {
    window.speechSynthesis.cancel();
  } catch (e) { /* 忽略 */ }
}

export function isSpeaking() {
  return window.speechSynthesis.speaking;
}
