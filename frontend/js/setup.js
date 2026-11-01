/**
 * 「接入 AI」页面：读取状态、保存配置、测试连通。
 * 密钥只提交不显示；页面上永远只看到"已配置 / 未配置"。
 */
const $ = (s) => document.querySelector(s);

const ui = {
  llmStatus: $('#llmStatus'),
  rtStatus: $('#rtStatus'),
  voiceStatus: $('#voiceStatus'),
  deepseekKey: $('#deepseekKey'),
  modelBase: $('#modelBase'),
  modelName: $('#modelName'),
  volcAppId: $('#volcAppId'),
  volcToken: $('#volcToken'),
  ttsProvider: $('#ttsProvider'),
  ttsVoice: $('#ttsVoice'),
  asrProvider: $('#asrProvider'),
  save: $('#btnSave'),
  test: $('#btnTest'),
  msg: $('#setupMsg'),
};

function setMsg(text, kind = '') {
  if (!ui.msg) return;
  ui.msg.textContent = text || '';
  ui.msg.dataset.kind = kind;
}

function badge(el, ok, okText, badText) {
  if (!el) return;
  el.textContent = ok ? okText : badText;
  el.dataset.ok = String(Boolean(ok));
}

async function api(path, options = {}) {
  const res = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...options });
  let body = null;
  try { body = await res.json(); } catch (e) { /* 忽略 */ }
  if (!res.ok) {
    const err = body?.error || {};
    throw new Error(err.message || `HTTP ${res.status}`);
  }
  return body;
}

function render(state) {
  const s = state;
  badge(ui.llmStatus, s.llm?.ready, '已接入', '未接入');
  badge(ui.rtStatus, s.realtime?.ready, '已开通', '未开通');
  badge(ui.voiceStatus, s.tts?.provider === 'edge', '免费音色', '不发声');

  if (ui.modelBase && !ui.modelBase.value) ui.modelBase.value = s.llm?.base_url || '';
  if (ui.modelName && !ui.modelName.value) ui.modelName.value = s.llm?.model || '';
  if (ui.volcAppId && !ui.volcAppId.value) ui.volcAppId.value = '';
  if (ui.ttsVoice && !ui.ttsVoice.value) ui.ttsVoice.value = s.tts?.voice || '';
  if (ui.ttsProvider) ui.ttsProvider.value = s.tts?.provider || 'edge';
  if (ui.asrProvider) ui.asrProvider.value = s.asr?.provider || 'stub';

  // 已配置时给个占位提示，避免用户以为要先清空
  if (ui.deepseekKey) {
    ui.deepseekKey.placeholder = s.llm?.key_set ? '已配置（留空表示不修改）' : 'sk-… 粘贴进来';
  }
  if (ui.volcToken) {
    ui.volcToken.placeholder = s.realtime?.token_set ? '已配置（留空表示不修改）' : '粘贴 Access Token';
  }
}

async function load() {
  try {
    render(await api('/api/settings'));
  } catch (e) {
    setMsg('读取配置失败：' + e.message, 'error');
  }
}

async function save() {
  const payload = {
    deepseek_api_key: ui.deepseekKey?.value.trim() || undefined,
    model_base_url: ui.modelBase?.value.trim() || undefined,
    model_name: ui.modelName?.value.trim() || undefined,
    volc_app_id: ui.volcAppId?.value.trim() || undefined,
    volc_access_token: ui.volcToken?.value.trim() || undefined,
    tts_provider: ui.ttsProvider?.value || undefined,
    tts_voice: ui.ttsVoice?.value.trim() || undefined,
    asr_provider: ui.asrProvider?.value || undefined,
  };
  // 去掉 undefined，空字符串不覆盖原值
  const body = Object.fromEntries(Object.entries(payload).filter(([, v]) => v));

  if (!Object.keys(body).length) {
    setMsg('没有需要保存的改动', 'warn');
    return;
  }

  ui.save.disabled = true;
  setMsg('保存中…');
  try {
    const res = await api('/api/settings', { method: 'POST', body: JSON.stringify(body) });
    render(res.state);
    ui.deepseekKey.value = '';
    ui.volcToken.value = '';
    setMsg(`已保存：${res.saved.join('、')}。立即生效。`, 'ok');
  } catch (e) {
    setMsg('保存失败：' + e.message, 'error');
  } finally {
    ui.save.disabled = false;
  }
}

async function test() {
  ui.test.disabled = true;
  setMsg('测试中…');
  try {
    const caps = await api('/api/capabilities');
    const health = await api('/api/health');
    const parts = [
      health.ok ? '服务正常' : '服务异常',
      caps.llm?.ready ? '模型已接入' : '模型未接入',
      caps.realtime?.ready ? '实时语音已开通' : '实时语音未开通',
    ];
    setMsg(parts.join(' · '), caps.llm?.ready ? 'ok' : 'warn');
  } catch (e) {
    setMsg('测试失败：' + e.message, 'error');
  } finally {
    ui.test.disabled = false;
  }
}

ui.save?.addEventListener('click', save);
ui.test?.addEventListener('click', test);
load();
