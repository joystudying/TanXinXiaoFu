/**
 * 状态机与接口调用（设计文档 8.4 / 8.5 / 8.6 / 11.x）
 *
 * 状态：idle | listening | processing | speaking | error
 * 幂等键：新一轮换、重试同一轮复用
 */
import { createRecognizer } from './speech.js';
import { speak, stopSpeaking } from './speak.js';
import { createBargeInWatcher, canWatchBargeIn } from './vad.js';

const State = {
  IDLE: 'idle',
  LISTENING: 'listening',
  PROCESSING: 'processing',
  SPEAKING: 'speaking',
  ERROR: 'error',
};

const $ = (sel) => document.querySelector(sel);
const CASE_ID = 'c_academic_01';
const LS_SESSION = 'tanxin.session_id';
const LS_CASE = 'tanxin.case_public';

/** 错误码 → 用户能看懂的下一步（设计文档 6.8 / 12） */
const ERROR_TEXT = {
  mic_denied: '麦克风权限被拒。点地址栏左侧的锁图标 → 允许麦克风；也可以直接打字。',
  asr_unsupported: '这个浏览器不支持语音识别，请用 Edge 或 Chrome；现在可以直接打字。',
  asr_network: '识别服务连不上（需要联网）。先用打字继续。',
  asr_no_speech: '没听清，再说一次（环境太吵的话可以打字）。',
  asr_aborted: '这次识别被取消了，再来一次。',
  asr_failed: '识别出错了，再说一次或改用打字。',
  tts_failed: '朗读失败，文字已经显示出来了，可以点重读。',
  tts_blocked: '浏览器拦截了自动朗读，点一下页面再试。',
  network: '网络好像断了，检查一下连接再试。',
  model_timeout: '小辅没来得及回应，要不要再试一次？',
  model_unavailable: '模型暂时不可用，稍等再试。',
  rate_limited: '说话有点频繁，歇一下再说。',
  session_closed: '这次训练已经结束了，想再练要新建一次。',
  session_not_found: '会话找不到了，重新开始一次训练。',
  duplicate_in_flight: '上一条还在处理，等它出结果。',
};

const ui = {
  caseBox: $('#caseBox'),
  caseMeta: $('#caseMeta'),
  turns: $('#turns'),
  status: $('#status'),
  hint: $('#hint'),
  btnStart: $('#btnStart'),
  btnTalk: $('#btnTalk'),
  btnEnd: $('#btnEnd'),
  btnRetry: $('#btnRetry'),
  manual: $('#manualText'),
  btnSend: $('#btnSend'),
};

let state = State.IDLE;
let sessionId = null;
let currentKey = null;
let pendingText = '';
let recognizer = null;
let watcher = null;
let watcherReady = false;

// ---------------- 渲染 ----------------

function setState(next, note = '') {
  state = next;
  document.body.dataset.state = next;

  if (ui.btnTalk) {
    ui.btnTalk.disabled = !sessionId || next === State.PROCESSING || next === State.SPEAKING;
    ui.btnTalk.textContent = next === State.LISTENING ? '说完' : '开始说话';
  }
  if (ui.btnSend) ui.btnSend.disabled = !sessionId || next === State.PROCESSING;
  if (ui.btnEnd) ui.btnEnd.disabled = !sessionId || next === State.SPEAKING;

  const label = {
    [State.IDLE]: '准备好了，点「开始说话」',
    [State.LISTENING]: '正在听你说…',
    [State.PROCESSING]: '小辅在回应…',
    [State.SPEAKING]: '小辅正在说（开口可以打断）',
    [State.ERROR]: '出错了',
  }[next] || '';

  if (ui.status) {
    ui.status.textContent = note || label;
    ui.status.dataset.state = next;
  }
}

function renderTurn(role, text, turnNo) {
  const wrap = document.createElement('div');
  wrap.className = `turn ${role}`;
  if (turnNo != null) wrap.dataset.turnNo = String(turnNo);

  const who = document.createElement('span');
  who.className = 'who';
  who.textContent = role === 'teacher' ? '老师' : '小辅';

  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  bubble.textContent = text;

  wrap.append(who, bubble);
  ui.turns.appendChild(wrap);
  ui.turns.scrollTop = ui.turns.scrollHeight;
  return wrap;
}

function clearTurns() {
  ui.turns.innerHTML = '';
}

function showCase(publicInfo) {
  ui.caseBox.hidden = false;
  const rows = [
    ['称呼', publicInfo.alias],
    ['年级专业', `${publicInfo.grade || ''}${publicInfo.major || ''}`],
    ['已知情况', publicInfo.concern],
    ['线索来源', publicInfo.origin],
    ['训练目标', publicInfo.goal],
  ];
  ui.caseMeta.innerHTML = rows
    .filter(([, v]) => v)
    .map(([k, v]) => `<dt>${k}</dt><dd>${escapeHtml(v)}</dd>`)
    .join('');
}

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

function setHint(msg) {
  if (ui.hint) ui.hint.textContent = msg || '';
}

function newKey() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID();
  return 'k-' + Date.now() + '-' + Math.random().toString(16).slice(2, 10);
}

// ---------------- 接口 ----------------

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  let body = null;
  try {
    body = await res.json();
  } catch (e) { /* 可能是空响应 */ }
  if (!res.ok) {
    const err = body?.error || {};
    const e = new Error(err.message || `HTTP ${res.status}`);
    e.code = err.code || 'http_error';
    e.retryable = Boolean(err.retryable);
    throw e;
  }
  return body;
}

async function startTraining() {
  setHint('');
  ui.btnStart.disabled = true;
  try {
    const data = await api('/api/sessions', {
      method: 'POST',
      body: JSON.stringify({ case_id: CASE_ID, prep_note: '先问最近状态，不急着给建议' }),
    });
    sessionId = data.session_id;
    localStorage.setItem(LS_SESSION, sessionId);
    localStorage.setItem(LS_CASE, JSON.stringify(data.case.public));
    showCase(data.case.public);
    clearTurns();
    currentKey = null;
    setState(State.IDLE);
    setHint('先说一句开放的问题试试，比如「最近怎么样？」');
    ui.manual.focus();
  } catch (e) {
    setState(State.ERROR, ERROR_TEXT[e.code] || '建会话失败：' + e.message);
  } finally {
    ui.btnStart.disabled = false;
  }
}

async function restoreSession() {
  const sid = localStorage.getItem(LS_SESSION);
  if (!sid) return false;
  try {
    const sess = await api(`/api/sessions/${sid}`);
    if (sess.status === 'ended') {
      localStorage.removeItem(LS_SESSION);
      return false;
    }
    sessionId = sid;
    const turns = await api(`/api/sessions/${sid}/turns`);
    clearTurns();
    turns.turns.forEach((t) => renderTurn(t.role, t.text, t.turn_no));
    const cached = localStorage.getItem(LS_CASE);
    if (cached) {
      try { showCase(JSON.parse(cached)); } catch (e) { /* 存坏了就跳过 */ }
    }
    setState(State.IDLE, '已恢复上次的对话');
    return true;
  } catch (e) {
    localStorage.removeItem(LS_SESSION);
    return false;
  }
}


async function endSession() {
  if (!sessionId) return;
  try {
    await api(`/api/sessions/${sessionId}/end`, {
      method: 'POST',
      body: JSON.stringify({ reason: '用户结束' }),
    });
  } catch (e) { /* 结束失败也让前端回到初始态 */ }
  localStorage.removeItem(LS_SESSION);
  localStorage.removeItem(LS_CASE);
  sessionId = null;
  clearTurns();
  ui.caseBox.hidden = true;
  ui.caseMeta.innerHTML = '';
  setHint('本次训练已结束。想再练一次？点「开始训练」会新建一条记录，旧的不会被覆盖。');
  setState(State.IDLE);
}

async function sendChat(text, { retry = false } = {}) {
  if (!sessionId) return;
  if (!retry) {
    currentKey = newKey();          // 新一轮 → 新 key
    pendingText = text;
  } else if (!pendingText) {
    return;
  }

  ui.btnRetry.hidden = true;
  setState(State.PROCESSING);

  const payload = retry
    ? { session_id: sessionId, text: pendingText, idempotency_key: currentKey }
    : { session_id: sessionId, text, idempotency_key: currentKey };

  try {
    const data = await api('/api/chat', { method: 'POST', body: JSON.stringify(payload) });

    if (!retry) renderTurn('teacher', text, data.turn_no - 1);
    const studentEl = renderTurn('student', data.reply_text, data.turn_no);
    if (data.cached) studentEl.dataset.cached = '1';

    currentKey = null;
    pendingText = data.reply_text;
    await speakReply(data.reply_text);
  } catch (err) {
    const msg = ERROR_TEXT[err.code] || err.message || '请求失败';
    setState(State.ERROR, msg);
    if (err.retryable) ui.btnRetry.hidden = false;
    setHint(err.code === 'rate_limited' || err.code === 'duplicate_in_flight'
      ? '等一两秒再点重试。'
      : '');
  }
}

// ---------------- 朗读 + 打断 ----------------

async function ensureWatcher() {
  if (watcherReady || !canWatchBargeIn()) return;
  try {
    watcher = await createBargeInWatcher();
    watcherReady = true;
  } catch (e) {
    watcher = null;                 // 拿不到麦克风就放弃打断功能，不影响主流程
  }
}



function onBargeIn() {
  if (state !== State.SPEAKING) return;
  stopSpeaking();
  setState(State.IDLE, '被打断，接着说');
  beginTalk();
}

function timeoutAfter(ms, value) {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms));
}

async function speakReply(text) {
  setState(State.SPEAKING);
  await ensureWatcher();

  if (watcher) {
    // 朗读开始 300ms 后再开，否则会被自己的扬声器触发
    setTimeout(() => {
      watcher.start(() => onBargeIn());
    }, 300);
  }

  // 看门狗：某些环境（无可用音色、被浏览器策略拦截）speak() 既不报错也不结束，
  // 会让状态永久停在 speaking、按钮全禁用。按字数估一个上限，超时强制回 idle。
  const estimateMs = Math.max(6000, Math.round(text.length * 320) + 4000);

  const result = await Promise.race([
    speak(text, {
      onError: (code) => {
        setHint(ERROR_TEXT[code] || '朗读失败，可以点重读。');
      },
    }),
    timeoutAfter(estimateMs, '__timeout__'),
  ]);

  if (watcher) watcher.disarm();

  if (result === '__timeout__') {
    stopSpeaking();
    setHint('朗读好像没出声（可能是浏览器没有可用音色）。文字已经在上面了，可以继续说下一句。');
    setState(State.IDLE);
    return;
  }
  if (result) setState(State.IDLE);
}

// ---------------- 说话 ----------------

function beginTalk() {
  if (!sessionId) {
    setHint('先点「开始训练」。');
    return;
  }
  if (state === State.LISTENING) return;

  if (!recognizer || !recognizer.supported) {
    setHint('这个浏览器不支持语音识别（建议 Edge / Chrome）。可以直接在下面打字。');
    ui.manual.focus();
    return;
  }
  recognizer.start();
  setState(State.LISTENING);
  setHint('说完可以点「说完」，也可以直接停下等它自己结束。');
}

function setupRecognizer() {
  recognizer = createRecognizer({
    onInterim: (t) => {
      if (ui.status) ui.status.textContent = `正在听：${t}`;
    },
    onFinal: (text) => {
      setHint('');
      sendChat(text);
    },
    onError: (code) => {
      setState(State.ERROR, ERROR_TEXT[code] || '识别出错');
      if (code === 'mic_denied' || code === 'asr_network' || code === 'asr_unsupported') {
        ui.manual.focus();
      }
    },
    onEnd: () => {
      if (state === State.LISTENING) setState(State.IDLE);
    },
  });

  if (!recognizer.supported) {
    setHint('这个浏览器不支持语音识别，先在下面打字练习（功能完全一样）。');
  }
}

// ---------------- 事件绑定 ----------------

function bind() {
  ui.btnStart?.addEventListener('click', startTraining);
  ui.btnEnd?.addEventListener('click', endSession);

  ui.btnTalk?.addEventListener('click', () => {
    if (state === State.LISTENING) {
      recognizer?.stop();
      return;
    }
    beginTalk();
  });

  ui.btnSend?.addEventListener('click', () => {
    const text = ui.manual.value.trim();
    if (!text) return;
    if (state === State.PROCESSING || state === State.SPEAKING) {
      setHint('等这一轮结束再发下一句。');
      return;
    }
    ui.manual.value = '';
    sendChat(text);
  });

  ui.manual?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      ui.btnSend?.click();
    }
  });

  ui.btnRetry?.addEventListener('click', () => sendChat(pendingText, { retry: true }));

  window.addEventListener('beforeunload', () => {
    recognizer?.abort();
    stopSpeaking();
    watcher?.stop();
  });

  window.addEventListener('resize', () => {
    ui.turns.scrollTop = ui.turns.scrollHeight;
  });
}

async function main() {
  setupRecognizer();
  bind();
  setState(State.IDLE);
  const restored = await restoreSession();
  if (!restored) {
    setState(State.IDLE, '点「开始训练」进入案例');
    setHint('这是演练，学生是虚拟的；你说的话会被记录，用于复盘。');
  }
}

main();
