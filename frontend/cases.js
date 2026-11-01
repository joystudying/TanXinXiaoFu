// cases.js —— 案例库前端数据层：把 /cases、/sessions 接到三个页面。
//   · 场景选择页（index.html）：拉取 GET /cases 渲染 18 个案例，分类筛选 + 搜索。
//   · 案例详情页（details.html）：拉取 GET /cases/{id} 展示公开信息 + 谈前准备。
//   · 谈话页（conversation.html）：拉取案例公开信息填标题 / 徽章 / 头像，并修链接。
// 私有层（隐藏背景 / 表达特点 / 分支 / 开场白）永不进前端，只在服务端进 system prompt。
(function () {
  'use strict'

  const API_BASE = location.protocol === 'https:' ? '' : 'http://127.0.0.1:8000'

  const CATEGORY_LABELS = {
    academic: '学业困难',
    emotion: '情绪困扰',
    relationship: '人际关系',
    family: '家庭困境',
    career: '就业迷茫',
    risk: '危机识别与联动',
  }
  const CATEGORY_TITLES = {
    academic: ['学业困难', '了解困难，回应挫败感'],
    emotion: ['情绪困扰', '练习倾听与回应感受'],
    relationship: ['人际关系', '理解分歧，支持表达边界'],
    family: ['家庭困境', '尊重隐私，讨论支持'],
    career: ['就业迷茫', '澄清选择，协商下一步'],
    risk: ['危机识别与联动', '练习风险确认与支持联动'],
  }

  function escapeHtml(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
  }
  function categoryLabel(key) {
    return CATEGORY_LABELS[key] || key
  }
  function gradeOf(gradeMajor) {
    return String(gradeMajor || '').split('·')[0].trim()
  }
  async function getJSON(path, options) {
    const res = await fetch(API_BASE + path, options)
    if (!res.ok) {
      let detail = ''
      try {
        detail = (await res.json()).detail || ''
      } catch (_) {}
      throw new Error(detail || 'HTTP ' + res.status)
    }
    return res.json()
  }

  // ---------- 场景选择页 ----------
  const caseList = document.querySelector('.case-list')
  if (caseList) initSelection()

  function initialOf(name) {
    return String(name || '').replace(/^小/, '')
  }

  function caseRowHTML(c) {
    const lead = c.avatar
      ? `<img class="case-portrait" src="${escapeHtml(c.avatar)}" alt="${escapeHtml(c.name)}" />`
      : `<span class="case-initial" aria-hidden="true">${escapeHtml(initialOf(c.name))}</span>`
    return (
      `<article class="case-row" data-case-row data-category="${escapeHtml(c.category)}">${lead}` +
      `<div class="case-copy">` +
      `<div class="case-person"><strong>${escapeHtml(c.name)}</strong>${escapeHtml(c.grade_major)}</div>` +
      `<h3>${escapeHtml(c.tagline)}</h3>` +
      `<p>${escapeHtml(c.quote)}</p>` +
      `<div class="case-meta">` +
      `<span data-icon="target"></span><span>${escapeHtml(c.training_focus)}</span>` +
      `<span><span data-icon="clock"></span>${escapeHtml(c.duration)}</span>` +
      `</div></div>` +
      `<div class="case-action"><a class="button" href="details.html?case=${encodeURIComponent(c.id)}">查看案例<span data-icon="arrow"></span></a></div>` +
      `</article>`
    )
  }

  async function initSelection() {
    const empty = document.querySelector('[data-search-empty]')
    const search = document.querySelector('[data-search-cases]')
    const clear = document.querySelector('[data-clear-search]')
    const titleEl = document.querySelector('[data-category-title]')
    const descEl = document.querySelector('[data-category-description]')
    const catButtons = [...document.querySelectorAll('[data-category]')]
    const myBar = document.querySelector('[data-my-case]')

    let cases = []
    try {
      cases = await getJSON('/cases')
    } catch (err) {
      caseList.innerHTML =
        '<div class="empty-state"><span data-icon="search"></span><h3>案例库加载失败</h3>' +
        '<p>' + escapeHtml(err.message) + '</p></div>'
      if (window.hydrateIcons) window.hydrateIcons(caseList)
      return
    }

    caseList.innerHTML = cases.map(caseRowHTML).join('')
    if (window.hydrateIcons) window.hydrateIcons(caseList)

    // 「我的案例」条：指向第一个案例，替换旧的静态示例
    if (myBar && cases.length) {
      const first = cases[0]
      document.querySelector('[data-my-case-name]').textContent = first.name
      document.querySelector('[data-my-case-meta]').textContent =
        `${first.grade_major} · ${categoryLabel(first.category)}`
      document.querySelector('[data-my-case-open]').href =
        `details.html?case=${encodeURIComponent(first.id)}`
      myBar.hidden = false
    }

    function activeCategory() {
      return (
        document.querySelector('[data-category][aria-pressed="true"]')?.dataset.category ??
        'academic'
      )
    }
    function applyFilter() {
      const category = activeCategory()
      const query = search?.value.trim() ?? ''
      let visible = 0
      document.querySelectorAll('[data-case-row]').forEach((row) => {
        const matches =
          row.dataset.category === category && (!query || row.textContent.includes(query))
        row.hidden = !matches
        if (matches) visible += 1
      })
      if (empty) empty.hidden = visible > 0
    }

    catButtons.forEach((btn) =>
      btn.addEventListener('click', () => {
        catButtons.forEach((b) => b.setAttribute('aria-pressed', String(b === btn)))
        const [t, d] = CATEGORY_TITLES[btn.dataset.category]
        titleEl.textContent = t
        descEl.textContent = d
        if (search) search.value = ''
        applyFilter()
      }),
    )
    search?.addEventListener('input', applyFilter)
    clear?.addEventListener('click', () => {
      search.value = ''
      applyFilter()
      search.focus()
    })
    applyFilter()
  }

  // ---------- 案例详情页 ----------
  if (document.querySelector('.detail-layout')) initDetails()

  async function initDetails() {
    const caseId = new URLSearchParams(location.search).get('case')
    const nameEl = document.querySelector('[data-case-name]')
    if (!caseId) {
      if (nameEl) nameEl.textContent = '未指定案例'
      return
    }

    let c
    try {
      c = await getJSON('/cases/' + encodeURIComponent(caseId))
    } catch (err) {
      if (nameEl) nameEl.textContent = '案例加载失败'
      const bg = document.querySelector('[data-case-background]')
      if (bg) bg.textContent = err.message
      return
    }

    nameEl.textContent = c.name
    document.querySelector('[data-case-badge]').textContent = categoryLabel(c.category)
    document.title = `${c.name} · 谈心小辅`

    document.querySelector('[data-profile-photo]').innerHTML = c.avatar
      ? `<img class="profile-photo" src="${escapeHtml(c.avatar)}" alt="${escapeHtml(c.name)}" />`
      : `<div class="profile-photo profile-initial" aria-hidden="true">${escapeHtml(initialOf(c.name))}</div>`
    document.querySelector('[data-profile-name]').textContent = c.name
    document.querySelector('[data-profile-meta]').textContent = c.grade_major
    document.querySelector('[data-profile-quote]').textContent = `“${c.quote}”`
    document.querySelector('[data-profile-duration]').textContent = `建议练习时长：${c.duration}`

    document.querySelector('[data-case-background]').textContent = c.public_background
    document.querySelector('[data-case-goals]').innerHTML = (c.goals || [])
      .map((g, i) => `<li><span class="goal-number">${i + 1}</span>${escapeHtml(g)}</li>`)
      .join('')

    // 谈前准备 → 创建训练会话 → 进入谈话窗口
    const startBtn = document.querySelector('[data-start-session]')
    const startLabel = document.querySelector('[data-start-label]')
    const noticeEl = document.querySelector('[data-session-notice]')
    const noteEl = document.getElementById('preparation')

    startBtn.addEventListener('click', async () => {
      const note = noteEl ? noteEl.value.trim() : ''
      startBtn.disabled = true
      if (startLabel) startLabel.textContent = '正在创建会话…'
      if (noticeEl) noticeEl.hidden = true
      try {
        const s = await getJSON('/sessions', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ case_id: caseId, prep_note: note }),
        })
        location.href =
          `conversation.html?case=${encodeURIComponent(caseId)}` +
          `&session=${encodeURIComponent(s.session_id)}`
      } catch (err) {
        startBtn.disabled = false
        if (startLabel) startLabel.textContent = '进入谈话窗口'
        if (noticeEl) {
          noticeEl.textContent = '创建会话失败：' + err.message
          noticeEl.hidden = false
        }
      }
    })
  }

  // ---------- 谈话页 ----------
  if (document.body.dataset.page === 'conversation') initConversation()

  async function initConversation() {
    const caseId = new URLSearchParams(location.search).get('case')

    const back = document.querySelector('[data-back-link]')
    const prep = document.querySelector('[data-prep-link]')
    if (caseId) {
      const href = `details.html?case=${encodeURIComponent(caseId)}`
      if (back) back.href = href
      if (prep) prep.href = href
    }

    // 有案例就清掉静态演示内容，避免展示错人
    if (caseId) {
      const transcript = document.querySelector('.transcript-messages')
      if (transcript) transcript.innerHTML = ''
      const resp = document.querySelector('.current-response blockquote')
      if (resp) resp.textContent = '“……”'
    }

    if (!caseId) return
    let c
    try {
      c = await getJSON('/cases/' + encodeURIComponent(caseId))
    } catch (_) {
      return
    }

    const titleEl = document.querySelector('[data-voice-title]')
    if (titleEl) titleEl.textContent = `和${c.name}聊聊`
    document.title = `和${c.name}聊聊 · 谈心小辅`

    const badgeEl = document.querySelector('[data-voice-badge]')
    if (badgeEl) {
      badgeEl.textContent = `${c.name} · ${gradeOf(c.grade_major)} · ${categoryLabel(c.category)}`
    }
    const photoEl = document.querySelector('[data-voice-photo]')
    if (photoEl) {
      photoEl.innerHTML = c.avatar
        ? `<img class="presence-photo" src="${escapeHtml(c.avatar)}" alt="${escapeHtml(c.name)}" />`
        : `<div class="presence-photo presence-initial" aria-hidden="true">${escapeHtml(initialOf(c.name))}</div>`
    }
  }
})()
