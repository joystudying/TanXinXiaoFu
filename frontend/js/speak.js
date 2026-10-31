/**
 * 朗读封装（M3.2 重写：让声音不那么机械）
 *
 * 三个改动：
 *  1. 挑更好的音色——优先 Edge/Chrome 的神经网络音色（名字里带 Natural / Online），
 *     其次按角色性别挑（小陈是男生，优先云希/云健这类男声），最后才退回任意中文音色；
 *  2. 把「……」当成真实的停顿，而不是念出来——每处停顿插 300~420ms 静默；
 *  3. 每个句子给一点轻微的语速/音高抖动（±3%），避免整段一个调子读下来。
 */

const NEURAL = /Natural|Online|Neural|Plus/i;
const MALE = /Yunxi|Yunjian|Yunyang|Yunfeng|Yunye|Kangkang|云希|云健|云扬|云枫/i;
const FEMALE = /Xiaoxiao|Xiaoyi|Xiaohan|Xiaomo|Xiaorui|Huihui|Yaoyao|晓晓|晓伊|晓涵|晓墨/i;
const KNOWN_GOOD = /Xiaoxiao|Yunxi|Yunjian|Tingting|Meijia|Google 普通话/i;

let voices = [];
let ready = null;
let picked = null;

function loadVoices() {
  if (ready) return ready;
  ready = new Promise((resolve) => {
    const read = () => {
      voices = window.speechSynthesis.getVoices() || [];
      if (voices.length) resolve(voices);
    };
    read();
    window.speechSynthesis.addEventListener('voiceschanged', read, { once: true });
    setTimeout(() => resolve(voices), 2000);
  });
  return ready;
}

export function isSupported() {
  return 'speechSynthesis' in window;
}

function score(v, prefer) {
  if (!/^zh/i.test(v.lang || '')) return -1;
  let s = 10;
  if (NEURAL.test(v.name)) s += 100;
  if (KNOWN_GOOD.test(v.name)) s += 20;
  if (prefer === 'male') {
    if (MALE.test(v.name)) s += 40;
    if (FEMALE.test(v.name)) s -= 30;
  } else if (prefer === 'female') {
    if (FEMALE.test(v.name)) s += 40;
  }
  return s;
}

/** 选一个中文音色；prefer = 'male' | 'female' | undefined */
export async function pickVoice(prefer) {
  const list = await loadVoices();
  if (!list.length) return null;
  const ranked = [...list].sort((a, b) => score(b, prefer) - score(a, prefer));
  const best = ranked.find((v) => score(v, prefer) > 0) || null;
  picked = best;
  return best;
}

/** 给界面显示：当前用的是哪个音色，以及是不是神经网络音色 */
export function describeVoice() {
  if (!picked) return { name: '', neural: false };
  return { name: picked.name, neural: NEURAL.test(picked.name) };
}

export async function listChineseVoices() {
  const list = await loadVoices();
  return list.filter((v) => /^zh/i.test(v.lang || ''))
    .map((v) => ({ name: v.name, lang: v.lang, neural: NEURAL.test(v.name) }));
}

/**
 * 把文本切成「说话片段」和「停顿片段」。
 * 「……」这类省略号不念出来，转成一个自然的换气停顿。
 */
export function planUtterances(text) {
  const plan = [];
  const parts = String(text || '').split(/(……+|…+|\.{3,})/);
  for (const part of parts) {
    if (!part) continue;
    if (/^(……+|…+|\.{3,})$/.test(part)) {
      plan.push({ pause: part.length >= 4 ? 420 : 300 });
      continue;
    }
    const sentences = part.match(/[^。！？；!?;]+[。！？；!?;]?/g) || [];
    for (const s of sentences) {
      const t = s.trim();
      if (t) plan.push({ speak: t });
    }
  }
  return plan;
}

function speakOnce(text, voice, prefer) {
  return new Promise((resolve) => {
    const u = new SpeechSynthesisUtterance(text);
    u.lang = 'zh-CN';
    if (voice) u.voice = voice;
    // 每个句子给一点抖动，避免整段一个语调
    u.rate = 0.98 + Math.random() * 0.08;
    u.pitch = (prefer === 'male' ? 0.95 : 1.02) + (Math.random() * 0.06 - 0.03);
    u.volume = 1.0;
    u.onend = () => resolve(true);
    u.onerror = () => resolve(false);
    window.speechSynthesis.speak(u);
  });
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

let cancelled = false;

/**
 * 朗读一段文字。
 * 返回 true = 正常读完；false = 被打断或失败。
 */
export async function speak(text, { voicePrefer = 'male', onStart, onEnd, onError } = {}) {
  if (!isSupported()) {
    onError?.('tts_failed');
    return false;
  }
  window.speechSynthesis.cancel();
  cancelled = false;

  const voice = await pickVoice(voicePrefer);
  const plan = planUtterances(text);
  if (!plan.length) {
    onEnd?.();
    return true;
  }

  let started = false;
  for (const step of plan) {
    if (cancelled) break;
    if (step.pause) {
      await sleep(step.pause);
      continue;
    }
    if (!started) {
      started = true;
      onStart?.();
    }
    const ok = await speakOnce(step.speak, voice, voicePrefer);
    if (!ok) {
      if (!cancelled) onError?.('tts_failed');
      break;
    }
    await sleep(60);            // 句子之间留一点点缝，听起来有呼吸
  }
  onEnd?.();
  return !cancelled;
}

export function stopSpeaking() {
  cancelled = true;
  try { window.speechSynthesis.cancel(); } catch (e) { /* 忽略 */ }
}

export function isSpeaking() {
  return window.speechSynthesis.speaking;
}
