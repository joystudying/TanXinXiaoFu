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
    ?.addEventListener('click', () => showStep(3))
  document
    .querySelector('[data-back]')
    ?.addEventListener('click', () => showStep(Math.max(1, currentStep - 1)))

  updateGate()
})()
