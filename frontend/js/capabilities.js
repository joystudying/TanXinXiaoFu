/**
 * 能力探测与档位选择（弱机 / 弱网降级）。
 *
 * 原则：客户端不跑任何模型，只收音、放音、显示。
 * 重活全在服务端或浏览器自带能力里。所以"电脑性能差"不该影响可用性，
 * 真正决定档位的是：网络质量、浏览器是否支持识别、服务端配了哪些 Provider。
 */

export const Tier = {
  FULL: 'full',     // 服务端识别 + 合成：客户端最省力
  HYBRID: 'hybrid', // 浏览器识别 + 服务端合成
  LITE: 'lite',     // 全用浏览器自带能力
  TEXT: 'text',     // 纯文字，兜底
};

function netQuality() {
  const c = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
  if (!c) return 'unknown';
  if (c.saveData) return 'slow';
  const type = c.effectiveType || 'unknown';
  if (type === 'slow-2g' || type === '2g') return 'slow';
  if (type === '3g') return 'medium';
  return 'fast';
}

function deviceProfile() {
  const cores = navigator.hardwareConcurrency || 2;
  const mem = navigator.deviceMemory || 4; // GB，Chrome 才有
  return {
    cores,
    mem,
    weak: cores <= 4 || mem <= 4,
    // 低端设备上有省电模式时浏览器会降频，靠它做信号之一
    lowPower: Boolean(navigator.getBattery ? false : false),
  };
}

export function browserASRSupported() {
  return Boolean(window.SpeechRecognition || window.webkitSpeechRecognition);
}

export function browserTTSSupported() {
  return 'speechSynthesis' in window;
}

/**
 * 探测并给出一份可用性报告 + 推荐档位。
 * 失败时一律退到 text，绝不因为探测失败让页面不能用。
 */
export async function probeCapabilities({ timeoutMs = 4000 } = {}) {
  const device = deviceProfile();
  const net = netQuality();
  const hasASR = browserASRSupported();
  const hasTTS = browserTTSSupported();

  let server = null;
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    const res = await fetch('/api/capabilities', { signal: controller.signal });
    clearTimeout(timer);
    if (res.ok) server = await res.json();
  } catch (e) {
    server = null;
  }

  const available = (server?.tiers || []).map((t) => t.id);
  let tier = Tier.TEXT;

  if (net === 'slow') {
    tier = Tier.TEXT;                       // 弱网优先保文字，语音一卡体验更差
  } else if (available.includes(Tier.FULL)) {
    tier = Tier.FULL;                       // 服务端全包，客户端最省力
  } else if (available.includes(Tier.HYBRID) && hasASR) {
    tier = Tier.HYBRID;
  } else if (server?.llm?.ready) {
    tier = hasASR || hasTTS ? Tier.LITE : Tier.TEXT;
  }

  // 浏览器连识别都不支持、服务端也没识别 → 只能文字
  if (tier === Tier.LITE && !hasASR) tier = Tier.TEXT;

  return {
    tier,
    device,
    net,
    browser: { asr: hasASR, tts: hasTTS },
    server,
    reason: describe(tier, { net, device, hasASR, available }),
  };
}

function describe(tier, ctx) {
  if (tier === Tier.TEXT && ctx.net === 'slow') return '网络较差，已切到纯文字，避免语音卡顿';
  if (tier === Tier.FULL) return '服务端承担识别与合成，本机负担最小';
  if (tier === Tier.HYBRID) return '用浏览器识别，服务端合成';
  if (tier === Tier.LITE) return '服务端未配语音，使用浏览器自带能力';
  return '仅文字对练';
}

/** 供页面显示的一行说明 */
export function tierSummary(report) {
  const map = {
    [Tier.FULL]: '全服务端语音',
    [Tier.HYBRID]: '浏览器识别 + 服务端合成',
    [Tier.LITE]: '浏览器自带语音',
    [Tier.TEXT]: '纯文字',
  };
  return `${map[report.tier] || '未知'}（${report.reason}）`;
}
