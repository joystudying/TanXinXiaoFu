/**
 * 语音识别封装（设计文档 8.1）
 *
 * 关键改进（M3.2）：**自己判断"说完了"**。
 * 浏览器在 continuous=false 时，说话中间一停顿就会把这一句判成结束；
 * 改成 continuous=true + 静音计时器：每收到识别结果就把计时器重置，
 * 连续 1.2 秒没有任何新结果才认为这一轮说完了。
 */

export function mapAsrError(code) {
  switch (code) {
    case 'not-allowed':
    case 'service-not-allowed':
      return 'mic_denied';
    case 'network':
      return 'asr_network';
    case 'no-speech':
      return 'asr_no_speech';
    case 'aborted':
      return 'asr_aborted';
    default:
      return 'asr_failed';
  }
}

export function createRecognizer({
  lang = 'zh-CN',
  silenceMs = 1200,      // 停顿多久算说完
  maxUtteranceMs = 60000, // 兜底：一次最多说这么久
  onInterim,
  onFinal,
  onError,
  onEnd,
} = {}) {
  const Ctor = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Ctor) {
    return { supported: false, start() {}, stop() {}, abort() {}, flush() {}, get state() { return 'idle'; } };
  }

  let state = 'idle';
  let finalText = '';
  let interimText = '';
  let silenceTimer = null;
  let hardTimer = null;
  let finishing = false;

  const r = new Ctor();
  r.lang = lang;
  r.continuous = true;        // 不在停顿处自动断开
  r.interimResults = true;
  r.maxAlternatives = 1;

  function clearTimers() {
    if (silenceTimer) { clearTimeout(silenceTimer); silenceTimer = null; }
    if (hardTimer) { clearTimeout(hardTimer); hardTimer = null; }
  }

  function resetSilenceTimer() {
    if (silenceTimer) clearTimeout(silenceTimer);
    silenceTimer = setTimeout(() => finish('silence'), silenceMs);
  }

  function collected() {
    return (finalText + interimText).trim();
  }

  function finish(reason) {
    if (finishing) return;
    const text = collected();
    finishing = true;
    clearTimers();
    try { r.stop(); } catch (e) { /* 忽略 */ }
    if (reason === 'manual' || reason === 'silence') {
      if (text) {
        state = 'processing';
        finalText = '';
        interimText = '';
        onFinal?.(text);
      }
    }
  }

  r.onstart = () => {
    state = 'listening';
    finishing = false;
    finalText = '';
    interimText = '';
    resetSilenceTimer();
    hardTimer = setTimeout(() => finish('timeout'), maxUtteranceMs);
  };

  r.onresult = (e) => {
    let finals = '';
    let interims = '';
    for (let i = 0; i < e.results.length; i += 1) {
      const res = e.results[i];
      const text = res[0]?.transcript ?? '';
      if (res.isFinal) finals += text;
      else interims += text;
    }
    finalText = finals;
    interimText = interims;

    const shown = collected();
    if (shown) {
      onInterim?.(shown);
      resetSilenceTimer();          // 只要还在出字，就认为人还在说
    }
  };

  r.onerror = (e) => {
    state = 'error';
    clearTimers();
    onError?.(mapAsrError(e.error));
  };

  r.onend = () => {
    clearTimers();
    const rest = collected();
    if (rest && !finishing) {       // 浏览器自己断开了，把已收到的交出去
      finalText = '';
      interimText = '';
      onFinal?.(rest);
    }
    if (state !== 'error') state = 'idle';
    finishing = false;
    onEnd?.();
  };

  return {
    supported: true,
    get state() { return state; },
    get pendingText() { return collected(); },
    start() {
      if (state === 'listening' || state === 'processing') return;
      finishing = false;
      try {
        r.start();
      } catch (err) {
        if (String(err?.name) === 'InvalidStateError') return;
        onError?.('asr_start_failed');
      }
    },
    /** 用户主动点「说完了」：立刻收尾 */
    flush() { finish('manual'); },
    stop() { finish('manual'); },
    abort() {
      clearTimers();
      finalText = '';
      interimText = '';
      try { r.abort(); } catch (e) { /* 忽略 */ }
    },
  };
}
