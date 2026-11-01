/**
 * 谈话页：把设计稿接上真实后端（M3）
 *
 * 设计稿原本是纯静态的，点击只提示"服务暂未连接"。这里保留它的结构与样式，
 * 只把数据源换成 /api/sessions 与 /api/chat。
 */
import { createRecognizer } from './speech.js';
import { speak, stopSpeaking, describeVoice } from './speak.js';
import { createBargeInWatcher, canWatchBargeIn } from './vad.js';
import { probeCapabilities, Tier, tierSummary } from './capabilities.js';
import { startRealtime, realtimeSupported } from './realtime.js';

const CASE_ID = 'c_academic_01';
const LS_SESSION = 'tanxin.session_id';
const LS_CASE = 'tanxin.case_public';

const State = { IDLE: 'idle', LISTENING: 'listening', PROCESSING: 'processing', SPEAKING: 'speaking', ERROR: 'error' };

const $ = (s) => document.querySelector(s);
const ui = {
  title: $('[data-case-title]'),
  badge: $('[data-case-badge]'),
  status: $('[data-status]'),
  messages: $('[data-messages]'),
  round: $('[data-round]'),
  quote: $('[data-current-quote]'),
  quoteBox: $('[data-current-response]'),
  mic: $('#btnMic'),
  micLabel: $('[data-mic-label]'),
  micHint: $('[data-mic-hint]'),
  rt: $('#btnRealtime'),
  rtLabel: $('[data-rt-label]'),
  talk: $('#btnTalk'),
  manual: $('#manualText'),
  send: $('#btnSend'),
  end: $('#btnEnd'),
  notice: $('[data-preview-notice]'),
};

const ERROR_TEXT = {
  mic_denied: '麦克风权限被拒。点地址栏左侧的锁图标允许麦克风，或直接打字。',
  asr_unsupported: '这个浏览器不支持语音识别，请用 Edge / Chrome；现在可以直接打字。',
  asr_network: '识别需要联网，现在连不上。先用打字继续。',
  asr_no_speech: '没听清，再说一次（太吵的话可以打字）。',
  asr_aborted: '这次识别取消了，再来一次。',
  asr_failed: '识别出错了，再说一次或改用打字。',
  tts_failed: '朗读失败，文字已经显示在右边。',
  tts_blocked: '浏览器拦了自动朗读，点一下页面再试。',
  network: '网络断了，检查一下连接。',
  model_timeout: '小辅没来得及回应，再试一次？',
  model_unavailable: '模型暂时不可用，稍等再试。',
  rate_limited: '说话有点频繁，歇一下。',
  session_closed: '这次训练已结束，点「结束并查看复盘」后重新开始。',
  session_not_found: '会话找不到了，回到场景选择重新开始。',
  duplicate_in_flight: '上一条还在处理，等它出结果。',
};

let state = State.IDLE;
let sessionId = null;
let currentKey = null;
let pendingText = '';
let recognizer = null;
let watcher = null;
let watcherReady = false;
let voiceHinted = false;
let voiceDisabled = false;      // 档位判定为纯文字时，禁用语音入口
let capabilityReport = null;
let rtSession = null;          // 正在跑的实时通话

// ---------------- 渲染 ----------------

function setState(next, message = '') {
  state = next;
  const labels = {
    [State.IDLE]: { status: '等待你的回应', mic: '点击开始说话', hint: '点击开始' },
    [State.LISTENING]: { status: '正在听你说…（停顿 1.2 秒会自动结束）', mic: '说完了', hint: '正在录音' },
    [State.PROCESSING]: { status: '小辅在回应…', mic: '小辅在回应…', hint: '请稍等' },
    [State.SPEAKING]: { status: '小辅正在说（开口可打断）', mic: '正在朗读…', hint: '可打断' },
    [State.ERROR]: { status: '出了点问题', mic: '点击重试说话', hint: '看下面的提示' },
  }[next];

  if (ui.status) ui.status.textContent = message || labels.status;
  if (ui.micLabel) ui.micLabel.textContent = labels.mic;
  if (ui.micHint) ui.micHint.textContent = labels.hint;

  const busy = next === State.PROCESSING || next === State.SPEAKING;
  if (ui.mic) {
    ui.mic.disabled = voiceDisabled || !sessionId || busy;
    ui.mic.setAttribute('aria-pressed', String(next === State.LISTENING));
  }
  if (ui.send) ui.send.disabled = !sessionId || busy;
  if (ui.manual) ui.manual.disabled = !sessionId || busy;
  if (ui.end) ui.end.disabled = !sessionId;
}

function renderMessages(turns) {
  if (!ui.messages) return;
  ui.messages.innerHTML = '';
  let teacherRound = 0;
  turns.forEach((t) => {
    if (t.role === 'teacher') teacherRound += 1;
    const article = document.createElement('article');
    article.className = `message ${t.role}`;
    const speaker = document.createElement('span');
    speaker.className = 'speaker';
    speaker.textContent = t.role === 'teacher' ? `辅导员 · 第${teacherRound}轮` : '小陈';
    const p = document.createElement('p');
    p.textContent = t.text;
    article.append(speaker, p);
    ui.messages.appendChild(article);
  });
  ui.messages.scrollTop = ui.messages.scrollHeight;
  if (ui.round) ui.round.textContent = `第 ${teacherRound} 轮`;
}

function appendMessage(role, text, roundNo) {
  if (!ui.messages) return;
  const article = document.createElement('article');
  article.className = `message ${role}`;
  const speaker = document.createElement('span');
  speaker.className = 'speaker';
  speaker.textContent = role === 'teacher' ? `辅导员 · 第${roundNo}轮` : '小陈';
  const p = document.createElement('p');
  p.textContent = text;
  article.append(speaker, p);
  ui.messages.appendChild(article);
  ui.messages.scrollTop = ui.messages.scrollHeight;
}

function showCase(publicInfo) {
  const alias = publicInfo?.alias || '小陈';
  const grade = publicInfo?.grade || '';
  if (ui.title) ui.title.textContent = `和${alias}聊聊`;
  if (ui.badge) {
    ui.badge.textContent = [alias, grade, '学业困难'].filter(Boolean).join(' · ');
  }
}

function showQuote(text) {
  if (!ui.quoteBox) return;
  if (!text) {
    ui.quoteBox.hidden = true;
    return;
  }
  ui.quote.textContent = `“${text}”`;
  ui.quoteBox.hidden = false;
}

function showSetupBanner(html) {
  let el = document.getElementById('setup-banner');
  if (!el) {
    el = document.createElement('div');
    el.id = 'setup-banner';
    el.className = 'setup-banner';
    el.setAttribute('role', 'status');
    document.querySelector('.stage')?.prepend(el);
  }
  el.innerHTML = html;
  el.hidden = false;
}

function notice(msg) {
  if (!ui.notice) return;
  ui.notice.textContent = msg;
  ui.notice.hidden = !msg;
}

// ---------------- 接口 ----------------

async function api(path, options = {}) {
  const res = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...options });
  let body = null;
  try { body = await res.json(); } catch (e) { /* 空响应 */ }
  if (!res.ok) {
    const err = body?.error || {};
    const e = new Error(err.message || `HTTP ${res.status}`);
    e.code = err.code || 'http_error';
    e.retryable = Boolean(err.retryable);
    throw e;
  }
  return body;
}

async function ensureSession() {
  const saved = localStorage.getItem(LS_SESSION);
  if (saved) {
    try {
      const sess = await api(`/api/sessions/${saved}`);
      if (sess.status !== 'ended') {
        sessionId = saved;
        const turns = await api(`/api/sessions/${saved}/turns`);
        renderMessages(turns.turns);
        const last = [...turns.turns].reverse().find((t) => t.role === 'student');
        if (last) showQuote(last.text);
        const cached = localStorage.getItem(LS_CASE);
        if (cached) {
          try { showCase(JSON.parse(cached)); } catch (e) { /* 忽略 */ }
        }
        setState(State.IDLE, turns.turns.length ? '已恢复上次的对话' : '');
        return;
      }
    } catch (e) { /* 掉到下面重建 */ }
    localStorage.removeItem(LS_SESSION);
  }

  const data = await api('/api/sessions', {
    method: 'POST',
    body: JSON.stringify({ case_id: CASE_ID, prep_note: '先问最近状态，不急着给建议' }),
  });
  sessionId = data.session_id;
  localStorage.setItem(LS_SESSION, sessionId);
  localStorage.setItem(LS_CASE, JSON.stringify(data.case.public));
  showCase(data.case.public);
  renderMessages([]);
  setState(State.IDLE, '准备好了，点下面的按钮开始说话');
}

async function sendChat(text, { retry = false } = {}) {
  if (!sessionId) return;
  if (!retry) {
    currentKey = crypto.randomUUID ? crypto.randomUUID() : `k-${Date.now()}`;
    pendingText = text;
  }
  setState(State.PROCESSING);
  notice('');

  const payload = {
    session_id: sessionId,
    text: retry ? pendingText : text,
    idempotency_key: currentKey,
  };

  try {
    const data = await api('/api/chat', { method: 'POST', body: JSON.stringify(payload) });
    const roundNo = Math.ceil(data.turn_no / 2);
    if (!retry) appendMessage('teacher', text, roundNo);
    appendMessage('student', data.reply_text, roundNo);
    if (ui.round) ui.round.textContent = `第 ${roundNo} 轮`;
    showQuote(data.reply_text);
    currentKey = null;
    await speakReply(data.reply_text);
  } catch (err) {
    const msg = ERROR_TEXT[err.code] || err.message || '请求失败';
    setState(State.ERROR, msg);
    notice(err.retryable ? `${msg} 点麦克风旁边的按钮可重试这一句。` : msg);
    if (err.retryable) {
      pendingText = retry ? pendingText : text;
      ui.mic.onclick = () => { ui.mic.onclick = null; sendChat(pendingText, { retry: true }); };
    }
  }
}

// ---------------- 语音 ----------------

async function ensureWatcher() {
  if (watcherReady || !canWatchBargeIn()) return;
  try {
    watcher = await createBargeInWatcher();
    watcherReady = true;
  } catch (e) { watcher = null; }
}

function timeoutAfter(ms, value) {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms));
}

async function speakReply(text) {
  setState(State.SPEAKING);
  await ensureWatcher();
  if (watcher) setTimeout(() => watcher.start(onBargeIn), 300);

  const estimate = Math.max(6000, Math.round(text.length * 320) + 4000);
  const result = await Promise.race([
    speak(text, { voicePrefer: 'male', onError: (code) => notice(ERROR_TEXT[code] || '朗读失败') }),
    timeoutAfter(estimate, '__timeout__'),
  ]);

  if (watcher) watcher.disarm();

  // 第一次朗读后检查音色：不是神经网络音色的话，说明声音会偏机械，给个可操作建议
  if (!voiceHinted) {
    voiceHinted = true;
    const v = describeVoice();
    if (v.name && !v.neural) {
      notice(`当前音色是「${v.name}」（传统合成音）。换成 Microsoft Edge 打开本站可以自动用上神经网络音色，听起来自然很多。`);
    }
  }

  if (result === '__timeout__') {
    stopSpeaking();
    setState(State.IDLE, '文字已经显示；朗读没有出声，可以继续下一句');
    return;
  }
  if (result) setState(State.IDLE);
}

function onBargeIn() {
  if (state !== State.SPEAKING) return;
  stopSpeaking();
  setState(State.IDLE, '被打断，接着说');
  beginTalk();
}

function setupRecognizer() {
  recognizer = createRecognizer({
    onInterim: (t) => { if (ui.status) ui.status.textContent = `正在听：${t}`; },
    onFinal: (text) => { sendChat(text); },
    onError: (code) => {
      setState(State.ERROR, ERROR_TEXT[code] || '识别出错');
      if (code === 'mic_denied' || code === 'asr_network' || code === 'asr_unsupported') {
        ui.manual?.focus();
      }
    },
    onEnd: () => { if (state === State.LISTENING) setState(State.IDLE); },
  });
  if (!recognizer.supported) {
    notice('这个浏览器不支持语音识别，先在下面打字（功能完全一样）。');
  }
}

function beginTalk() {
  if (voiceDisabled) { notice('当前环境已切到文字模式，请直接打字。'); ui.manual?.focus(); return; }
  if (!sessionId) return;
  if (state === State.LISTENING) return;
  if (!recognizer || !recognizer.supported) {
    notice('这个浏览器不支持语音识别，请在下面打字。');
    ui.manual?.focus();
    return;
  }
  recognizer.start();
  setState(State.LISTENING);
}

async function endSession() {
  if (!sessionId) return;
  try {
    await api(`/api/sessions/${sessionId}/end`, {
      method: 'POST', body: JSON.stringify({ reason: '用户结束' }),
    });
  } catch (e) { /* 结束失败也允许离开 */ }
  localStorage.removeItem(LS_SESSION);
  localStorage.removeItem(LS_CASE);
  location.href = 'review.html';
}

// ---------------- 绑定 ----------------

function bind() {
  ui.mic?.addEventListener('click', () => {
    if (state === State.LISTENING) {
      recognizer?.flush();
      return;
    }
    beginTalk();
  });

  ui.send?.addEventListener('click', () => {
    const text = ui.manual.value.trim();
    if (!text) return;
    ui.manual.value = '';
    sendChat(text);
  });

  ui.manual?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      ui.send?.click();
    }
  });

  ui.end?.addEventListener('click', endSession);

  // 按住说话：按下才把麦克风声音发给模型，松开就停。外放环境必须用这个。
  if (ui.talk) {
    const press = (on) => {
      ui.talk.setAttribute('aria-pressed', String(on));
      rtSession?.setTransmitting?.(on);
      setState(on ? State.LISTENING : State.IDLE, on ? '正在说…' : '松开即停');
    };
    ui.talk.addEventListener('pointerdown', (e) => { e.preventDefault(); press(true); });
    ui.talk.addEventListener('pointerup', (e) => { e.preventDefault(); press(false); });
    ui.talk.addEventListener('pointerleave', () => press(false));
    ui.talk.addEventListener('pointercancel', () => press(false));
    window.addEventListener('keydown', (e) => {
      if (e.code === 'Space' && rtSession && !e.repeat) { e.preventDefault(); press(true); }
    });
    window.addEventListener('keyup', (e) => {
      if (e.code === 'Space' && rtSession) { e.preventDefault(); press(false); }
    });
  }

  ui.rt?.addEventListener('click', async () => {
    if (rtSession) {                       // 正在通话 → 结束
      rtSession.stop();
      rtSession = null;
      ui.rt.setAttribute('aria-pressed', 'false');
      if (ui.rtLabel) ui.rtLabel.textContent = '实时通话';
      if (ui.talk) { ui.talk.hidden = true; ui.talk.disabled = true; ui.talk.setAttribute('aria-pressed', 'false'); }
      setState(State.IDLE, '实时通话已结束');
      return;
    }
    if (!realtimeSupported()) {
      notice('这个浏览器不支持实时通话（需要 AudioWorklet + 麦克风）。');
      return;
    }
    notice('');
    ui.rt.setAttribute('aria-pressed', 'true');
    if (ui.rtLabel) ui.rtLabel.textContent = '结束通话';
    try {
      rtSession = await startRealtime({
        onStatus: (state, text) => {
          if (state === 'speaking') setState(State.SPEAKING, text);
          else if (state === 'listening' || state === 'ready') setState(State.LISTENING, text);
          else if (state === 'error') setState(State.ERROR, text);
          else setState(State.IDLE, text);
        },
        onTeacherText: (text) => {
          const t = (text || '').trim();
          if (!t) return;
          const roundNo = document.querySelectorAll('.message.teacher').length + 1;
          appendMessage('teacher', t, roundNo);
          if (ui.round) ui.round.textContent = `第 ${roundNo} 轮`;
        },
        onStudentText: (text) => {
          const t = (text || '').trim();
          if (!t) return;
          const roundNo = Math.max(1, document.querySelectorAll('.message.teacher').length);
          appendMessage('student', t, roundNo);
          if (ui.round) ui.round.textContent = `第 ${roundNo} 轮`;
          showQuote(t);
        },
        onError: (code, message) => notice(`${message || '实时语音出错'}（${code}）`),
      });
      // 启用「按住说话」：外放时用它彻底避免回声
      if (ui.talk) {
        ui.talk.hidden = false;
        ui.talk.disabled = false;
      }
    } catch (e) {
      rtSession = null;
      ui.rt.setAttribute('aria-pressed', 'false');
      if (ui.rtLabel) ui.rtLabel.textContent = '实时通话';
      notice('实时通话启动失败：' + (e?.message || e));
    }
  });

  window.addEventListener('beforeunload', () => {
    recognizer?.abort();
    stopSpeaking();
    watcher?.stop();
  });
}

const GUIDE_URL = 'https://github.com/joystudying/TanXinXiaoFu/blob/integrate/docs/公告_新用户接入指南.md';

async function applyCapabilities() {
  capabilityReport = await probeCapabilities();

  // 没配模型密钥：直接用横幅把话说清楚，并给一个能点的指引
  if (capabilityReport.server && !capabilityReport.server.llm?.ready) {
    showSetupBanner(
      '还没接入 AI：请在项目根目录的 <code>.env</code> 里填 <code>DEEPSEEK_API_KEY</code>，'
      + `然后重启服务。<a href="${GUIDE_URL}" target="_blank" rel="noopener">查看接入指南 →</a>`
    );
  } else if (capabilityReport.server && !capabilityReport.server.realtime?.ready) {
    showSetupBanner(
      '实时语音未开通：填 <code>VOLC_APP_ID</code> 和 <code>VOLC_ACCESS_TOKEN</code> 后重启，'
      + `即可使用「实时通话」。<a href="${GUIDE_URL}" target="_blank" rel="noopener">查看接入指南 →</a>`
    );
  }
  // 纯文字档：直接禁用麦克风，避免用户点了没反应
  if (capabilityReport.tier === Tier.TEXT) {
    voiceDisabled = true;
    if (ui.mic) {
      ui.mic.disabled = true;
      ui.mic.title = '当前环境已切到文字模式';
    }
    notice(`${tierSummary(capabilityReport)}。可以直接在下面打字，功能一样完整。`);
  }
  // 实时通话：服务端配了火山、浏览器也支持，才放出来
  if (ui.rt) {
    const ready = Boolean(capabilityReport.server?.realtime?.ready)
      && realtimeSupported();
    ui.rt.disabled = !ready;
    ui.rt.title = ready ? '端到端模型直接对话，可随时打断' : '服务端未配置实时语音';
  }
  if (capabilityReport.device.weak) {
    notice(`检测到本机配置较低，已选用「${tierSummary(capabilityReport)}」，不会占用本地算力。`);
  }
  return capabilityReport;
}

async function main() {
  setupRecognizer();
  bind();
  setState(State.IDLE, '正在准备训练…');
  await applyCapabilities();
  try {
    await ensureSession();
  } catch (e) {
    setState(State.ERROR, '建会话失败：' + (e.message || e));
    notice('检查后端是否在运行（http://127.0.0.1:8000/api/health）。');
  }
}

main();
