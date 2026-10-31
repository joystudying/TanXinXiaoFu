/**
 * 语音识别封装（设计文档 8.1）
 *
 * 三条必须遵守（来自规范与本机实测）：
 *  1. 重复 start() 抛 InvalidStateError → 状态不是 idle 就不许 start
 *  2. 识别走在线服务 → network / service-not-allowed 必然出现，必须有手输兜底
 *  3. stop() 后不保证立刻 onend → UI 一律以事件为准，不用定时器猜
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

export function createRecognizer({ lang = 'zh-CN', onInterim, onFinal, onError, onEnd } = {}) {
  const Ctor = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Ctor) {
    return { supported: false, start() {}, stop() {}, abort() {}, get state() { return 'idle'; } };
  }

  let state = 'idle';
  const r = new Ctor();
  r.lang = lang;
  r.continuous = false;      // 一轮一句
  r.interimResults = true;   // 临时结果：显示"正在听"，也用于判断是否已经开口
  r.maxAlternatives = 1;

  r.onstart = () => { state = 'listening'; };

  r.onresult = (e) => {
    let interim = '';
    let final = '';
    for (const res of e.results) {
      const text = res[0]?.transcript ?? '';
      if (res.isFinal) final += text;
      else interim += text;
    }
    if (interim.trim()) onInterim?.(interim.trim());
    if (final.trim()) {
      state = 'processing';
      onFinal?.(final.trim());
    }
  };

  r.onerror = (e) => {
    state = 'error';
    onError?.(mapAsrError(e.error));
  };

  r.onend = () => {
    if (state !== 'error') state = 'idle';
    onEnd?.();
  };

  return {
    supported: true,
    get state() { return state; },
    start() {
      if (state === 'listening' || state === 'processing') return;  // 防重复
      try {
        r.start();
      } catch (err) {
        if (String(err?.name) === 'InvalidStateError') return;
        onError?.('asr_start_failed');
      }
    },
    stop() { try { r.stop(); } catch (e) { /* 忽略 */ } },
    abort() { try { r.abort(); } catch (e) { /* 忽略 */ } },
  };
}
