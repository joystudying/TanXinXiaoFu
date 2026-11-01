// 导入向导的交互：步骤切换、填写方式、字数统计、脱敏处理与下一步门槛。
// 仅控制页面状态，不连接模型或后端。包在 IIFE 里，避免与 shared.js 的全局变量冲突。
;(() => {
  const panels = [...document.querySelectorAll('.wizard-panel')]
  const steps = [...document.querySelectorAll('.wizard-steps li')]
  const source = document.querySelector('[data-source]')
  const counter = document.querySelector('[data-counter]')
  const consent = document.querySelector('[data-consent]')
  const nextButton = document.querySelector('[data-step="1"] [data-next]')
  const gateNote = document.querySelector('[data-gate-note]')
  const detectItems = [...document.querySelectorAll('[data-detect-item]')]
  const detectPanel = document.querySelector('[data-detect]')
  const detectTitle = document.querySelector('[data-detect-title]')
  const detectNote = document.querySelector('[data-detect-note]')

  let currentStep = 1

  function showStep(step) {
    currentStep = step
    panels.forEach((panel) => {
      panel.hidden = Number(panel.dataset.step) !== step
    })
    steps.forEach((item, index) => {
      const value = index + 1
      if (value === step) item.setAttribute('aria-current', 'step')
      else item.removeAttribute('aria-current')
      item.classList.toggle('is-done', value < step)
    })
    const heading = panels[step - 1]?.querySelector('h2')
    if (heading) {
      heading.setAttribute('tabindex', '-1')
      heading.focus({ preventScroll: true })
    }
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    window.scrollTo({ top: 0, behavior: reduce ? 'auto' : 'smooth' })
  }

  function updateGate() {
    if (!nextButton) return
    const unresolved = detectItems.filter((item) => !item.classList.contains('is-resolved')).length
    const ready = Boolean(consent?.checked) && unresolved === 0
    nextButton.disabled = !ready
    if (detectPanel && detectTitle && detectNote) {
      const done = unresolved === 0
      detectPanel.classList.toggle('is-done', done)
      detectTitle.textContent = done ? '个人信息已处理' : `发现 ${unresolved} 处需要处理的个人信息`
      detectNote.textContent = done
        ? '已替换为化名，学号与手机号不会保存。'
        : '替换或删除后才能继续，系统不会保存这些内容。'
    }
    if (!gateNote) return
    if (ready) gateNote.textContent = '可以继续'
    else if (!consent?.checked && unresolved > 0)
      gateNote.textContent = `确认授权并处理 ${unresolved} 处信息后可继续`
    else if (!consent?.checked) gateNote.textContent = '请先确认已获得授权'
    else gateNote.textContent = `还有 ${unresolved} 处信息需要处理`
  }

  consent?.addEventListener('change', updateGate)

  detectItems.forEach((item) => {
    item.querySelector('[data-resolve]')?.addEventListener('click', (event) => {
      const button = event.currentTarget
      item.classList.add('is-resolved')
      button.textContent = '已处理'
      button.disabled = true
      updateGate()
    })
  })

  document.querySelectorAll('[data-mode]').forEach((tab) => {
    tab.addEventListener('click', () => {
      const mode = tab.dataset.mode
      document
        .querySelectorAll('[data-mode]')
        .forEach((item) => item.setAttribute('aria-selected', String(item === tab)))
      document.querySelectorAll('[data-panel]').forEach((panel) => {
        panel.hidden = panel.dataset.panel !== mode
      })
    })
  })

  function updateCounter() {
    if (!source || !counter) return
    const length = source.value.trim().length
    counter.textContent = `${length} / 4000`
    counter.classList.toggle('over', length > 4000)
  }
  source?.addEventListener('input', updateCounter)
  updateCounter()

  document
    .querySelector('[data-step="1"] [data-next]')
    ?.addEventListener('click', () => showStep(2))
  document
    .querySelector('[data-step="2"] [data-next]')
    ?.addEventListener('click', generateCase)
  document
    .querySelector('[data-back]')
    ?.addEventListener('click', () => showStep(Math.max(1, currentStep - 1)))

  // ---------- 生成案例：把第一步的表单 POST 到后端，写入知识库并进入检索索引 ----------
  const API_BASE = location.protocol === 'https:' ? '' : 'http://127.0.0.1:8000'
  const CATEGORY_KEYS = {
    学业困难: 'academic',
    情绪困扰: 'emotion',
    人际关系: 'relationship',
    家庭困境: 'family',
    就业迷茫: 'career',
    危机识别与联动: 'risk',
  }
  const notice = document.querySelector('[data-preview-notice]')

  function fieldVal(id) {
    return document.getElementById(id)?.value?.trim() || ''
  }
  function collectForm() {
    const issue = fieldVal('f-issue')
    const signal = fieldVal('f-signal')
    const family = fieldVal('f-family')
    const other = fieldVal('f-other')
    return {
      category: CATEGORY_KEYS[issue] || 'emotion',
      name: fieldVal('f-nickname') || '小陈',
      grade_major: `${fieldVal('f-grade')} · ${fieldVal('f-major')}`,
      tagline: signal || '最近遇到一些事',
      quote: '',
      public_background: fieldVal('f-detail'),
      goals: fieldVal('f-goals').split(/\n+/).map((s) => s.trim()).filter(Boolean),
      training_focus: signal,
      duration: '5–8分钟',
      tags: [],
      // 家庭情况 / 其他信息按「私有层」存，仅服务端进 system prompt
      hidden_background: [family, other].filter(Boolean).join('；'),
      speech_style: '',
      branches: [],
      opening: signal ? `${signal}，老师。` : '',
    }
  }

  async function generateCase() {
    const btn = document.querySelector('[data-step="2"] [data-next]')
    if (btn) btn.disabled = true
    if (notice) notice.hidden = true
    try {
      const res = await fetch(API_BASE + '/cases', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(collectForm()),
      })
      if (!res.ok) {
        let detail = ''
        try {
          detail = (await res.json()).detail || ''
        } catch (_) {}
        throw new Error(detail || 'HTTP ' + res.status)
      }
      const c = await res.json()

      const card = document.querySelector('[data-step="3"] .result-card')
      const nameEl = card?.querySelector('h3')
      const metaEl = card?.querySelector('.result-meta')
      if (nameEl) nameEl.textContent = c.name
      if (metaEl) metaEl.textContent = `${c.grade_major} · 导入案例`
      const startLink = document.querySelector('[data-step="3"] a[href="conversation.html"]')
      const detailLink = document.querySelector('[data-step="3"] a[href="case-imported.html"]')
      if (startLink) startLink.href = 'conversation.html?case=' + encodeURIComponent(c.id)
      if (detailLink) detailLink.href = 'details.html?case=' + encodeURIComponent(c.id)

      showStep(3)
    } catch (err) {
      if (notice) {
        notice.textContent = '生成案例失败：' + err.message
        notice.hidden = false
      }
    } finally {
      if (btn) btn.disabled = false
    }
  }

  updateGate()
})()
