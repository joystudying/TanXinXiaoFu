// review.js —— 把「评价与复盘」页接到后端复盘接口 /sessions/{id}/review。
// 数据来自评价大模型（五维评分 + 证据 + 总结 + 建议），不再使用静态演示数据。
// 只在复盘页生效。
(function () {
  'use strict'
  if (document.body.dataset.page !== 'review') return

  // 本地（file:// 或 http）直接打本机后端；https 走同源代理（备用）。
  const API_BASE = location.protocol === 'https:' ? '' : 'http://127.0.0.1:8000'
  const root = document.getElementById('report-root')

  const params = new URLSearchParams(location.search)
  let sessionId = params.get('session')
  if (!sessionId) {
    try {
      sessionId = localStorage.getItem('xxt_last_session')
    } catch (_) {}
  }

  // ---------- 雷达图几何（与 review.html 静态稿同一坐标系） ----------
  const CX = 240
  const CY = 180
  const OUTER = [
    { x: 240, y: 68 }, // 共情引导（上）
    { x: 346.5, y: 145.4 }, // 思想引领（右上）
    { x: 305.8, y: 270.6 }, // 问题解决（右下）
    { x: 174.2, y: 270.6 }, // 临场应变（左下）
    { x: 133.5, y: 145.4 }, // 语言表达（左上）
  ]
  const LABELS = [
    { text: '共情引导', x: 240, y: 37 },
    { text: '思想引领', x: 400, y: 144 },
    { text: '问题解决', x: 335, y: 310 },
    { text: '临场应变', x: 145, y: 310 },
    { text: '语言表达', x: 80, y: 144 },
  ]

  function pt(i, frac) {
    const o = OUTER[i]
    return { x: CX + (o.x - CX) * frac, y: CY + (o.y - CY) * frac }
  }
  function ring(frac) {
    return (
      'M' +
      OUTER.map((_, i) => {
        const p = pt(i, frac)
        return p.x.toFixed(1) + ' ' + p.y.toFixed(1)
      }).join(' ') +
      'Z'
    )
  }

  function escapeHtml(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
  }

  function splitItems(text) {
    const byLine = String(text || '')
      .split(/\n+/)
      .map((s) => s.trim())
      .filter(Boolean)
    if (byLine.length > 1) return byLine
    const bySentence = String(text || '')
      .split(/(?<=[。；])\s*/)
      .map((s) => s.trim())
      .filter(Boolean)
    return bySentence.length ? bySentence : text ? [String(text)] : []
  }

  function renderTranscript(turns) {
    if (!Array.isArray(turns) || !turns.length) {
      return '<p class="report-note">暂无对话记录。</p>'
    }
    const rows = turns
      .map((t) => {
        const isTeacher = t.role === 'teacher'
        const cls = isTeacher ? ' class="teacher-turn"' : ''
        return (
          '<div' + cls + '><dt>' + (isTeacher ? '辅导员' : '学生') + '</dt>' +
          '<dd>' + escapeHtml(t.text) + '</dd></div>'
        )
      })
      .join('')
    return '<dl class="dialogue-transcript">' + rows + '</dl>'
  }

  function setMessage(html) {
    root.innerHTML =
      '<div style="padding:48px 16px;text-align:center;color:var(--ink);font-size:15px">' +
      html +
      '</div>'
  }

  // ---------- 渲染 ----------
  function renderRadar(dimensions) {
    const scores = dimensions.map((d) => Number(d.score) || 0)
    const ringPaths = [1, 0.8, 0.6, 0.4].map((f) => ring(f)).join('')
    const spokes = OUTER.map((o) => 'M' + CX + ' ' + CY + 'L' + o.x + ' ' + o.y).join('')
    const poly = (
      'M' +
      scores.map((s, i) => {
        const p = pt(i, Math.max(0, Math.min(20, s)) / 20)
        return p.x.toFixed(1) + ' ' + p.y.toFixed(1)
      }).join(' ') +
      'Z'
    )
    const dots = scores
      .map((s, i) => {
        const p = pt(i, Math.max(0, Math.min(20, s)) / 20)
        return '<circle cx="' + p.x.toFixed(1) + '" cy="' + p.y.toFixed(1) + '" r="4" />'
      })
      .join('')
    const desc = dimensions
      .map((d) => d.name + String(d.score))
      .join('，') + '，各维度满分20。'

    return (
      '<svg class="radar" viewBox="0 0 480 350" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="radar-title radar-desc">' +
      '<title id="radar-title">五维谈话行为雷达图</title>' +
      '<desc id="radar-desc">' + escapeHtml(desc) + '</desc>' +
      '<g fill="none" stroke="#c6d6cb" stroke-width="1">' +
      '<path d="' + ring(1) + '" fill="#f4f8f5" />' +
      '<path d="' + ring(0.8) + '" />' +
      '<path d="' + ring(0.6) + '" />' +
      '<path d="' + ring(0.4) + '" />' +
      '<path d="' + spokes + '" />' +
      '</g>' +
      '<path d="' + poly + '" fill="#296e49" fill-opacity=".2" stroke="#296e49" stroke-width="2.5" />' +
      '<g fill="#296e49" stroke="white" stroke-width="2">' + dots + '</g>' +
      '<g font-family="Microsoft YaHei, sans-serif" font-size="22" fill="#294e38" text-anchor="middle">' +
      LABELS.map((l) => '<text x="' + l.x + '" y="' + l.y + '">' + l.text + '</text>').join('') +
      '</g>' +
      '</svg>'
    )
  }

  // 翻页：一次只显示一页「纸」，用上一页/下一页翻动；打印时全部展开（CSS 处理）。
  function setupPagination() {
    const sheets = Array.from(root.querySelectorAll('.report-pages .report-sheet'))
    const prev = root.querySelector('[data-page-prev]')
    const next = root.querySelector('[data-page-next]')
    const indicator = root.querySelector('[data-page-indicator]')
    if (!sheets.length || !prev || !next || !indicator) return

    let current = 0
    function show(i) {
      current = Math.max(0, Math.min(sheets.length - 1, i))
      sheets.forEach((s, k) => { s.hidden = k !== current })
      prev.disabled = current === 0
      next.disabled = current === sheets.length - 1
      indicator.textContent = '第 ' + (current + 1) + ' / ' + sheets.length + ' 页'
    }

    prev.addEventListener('click', () => {
      show(current - 1)
      window.scrollTo({ top: 0, behavior: 'smooth' })
    })
    next.addEventListener('click', () => {
      show(current + 1)
      window.scrollTo({ top: 0, behavior: 'smooth' })
    })

    // 目录链接跨页跳转：先切到目标所在页，再滚到该节
    const directory = document.querySelector('.review-directory')
    if (directory) {
      directory.addEventListener('click', (e) => {
        const a = e.target.closest('a[href^="#"]')
        if (!a) return
        e.preventDefault()
        const target = document.getElementById(a.getAttribute('href').slice(1))
        if (!target) return
        const sheet = target.closest('.report-sheet')
        const idx = sheet ? sheets.indexOf(sheet) : -1
        if (idx >= 0) show(idx)
        target.scrollIntoView({ behavior: 'smooth', block: 'start' })
      })
    }

    show(0)
  }

  function renderReport(data) {
    const dims = data.dimensions || []
    const total = Number(data.total_score) || 0
    const scores = dims.map((d) => Number(d.score) || 0)
    let top = dims[0]
    let low = dims[0]
    for (const d of dims) {
      if (Number(d.score) > Number(top.score)) top = d
      if (Number(d.score) < Number(low.score)) low = d
    }

    const firstTurn = Array.isArray(data.turns) && data.turns.length ? data.turns[0] : null
    const modeLabel = firstTurn && firstTurn.mode === 'realtime' ? '实时通话'
      : firstTurn && firstTurn.mode === 'pipeline' ? '语音/文字对练' : '—'

    const facts = [
      ['训练场景', data.scenario || '—'],
      ['训练方式', modeLabel],
      ['综合得分', total + ' / 100'],
      ['评价维度', dims.length + ' 维'],
      ['会话编号', sessionId ? sessionId.slice(0, 8) : '—'],
    ]

    const dimensionRows = dims
      .map(
        (d) =>
          '<tr><th scope="row">' + escapeHtml(d.name) + '</th>' +
          '<td class="score">' + Number(d.score) + '</td>' +
          '<td>' + escapeHtml(d.comment) + '</td></tr>',
      )
      .join('')

    const evidenceBlocks = dims
      .map((d) => {
        const quotes = Array.isArray(d.evidence) ? d.evidence.filter(Boolean) : []
        const quoteHtml = quotes.length
          ? '<ul class="rubric-legend">' +
            quotes.map((q) => '<li>“' + escapeHtml(q) + '”</li>').join('') +
            '</ul>'
          : '<p class="report-note">本维度未引用到明确原话依据。</p>'
        return (
          '<section class="report-section">' +
          '<h3 class="subsection-title">' + escapeHtml(d.name) + ' · ' + Number(d.score) + ' 分</h3>' +
          '<p class="report-note">' + escapeHtml(d.comment) + '</p>' +
          '<h4 class="subsection-title">原话依据</h4>' + quoteHtml +
          '</section>'
        )
      })
      .join('')

    const practiceItems = splitItems(data.suggestions)
      .map((s) => '<li>' + escapeHtml(s) + '</li>')
      .join('')

    root.innerHTML =
      '<div class="report-pages">' +
      '<article class="report-sheet" aria-label="第1页：评价总览">' +
      '<header class="sheet-heading"><h2>谈话训练评价报告</h2><span class="sheet-page">01 / 02</span></header>' +
      '<dl class="report-facts">' +
      facts
        .map(
          ([k, v]) => '<div><dt>' + k + '</dt><dd>' + escapeHtml(v) + '</dd></div>',
        )
        .join('') +
      '</dl>' +
      '<section id="review-verdict" class="report-section">' +
      '<h2 class="report-section-title"><span aria-hidden="true">一</span>整体评价</h2>' +
      '<div class="verdict-summary">' +
      '<p class="verdict-lead">本次谈话综合得分 ' + total + ' 分（满分 100）。</p>' +
      '<p>' + escapeHtml(data.summary) + '</p>' +
      '</div>' +
      (top && low
        ? '<dl class="verdict-findings">' +
          '<div><dt>值得保留</dt><dd>「' + escapeHtml(top.name) + '」得分最高（' + Number(top.score) + ' 分）。</dd></div>' +
          '<div><dt>优先调整</dt><dd>「' + escapeHtml(low.name) + '」相对薄弱（' + Number(low.score) + ' 分），是下轮重点。</dd></div>' +
          '<div><dt>下一步</dt><dd>可执行建议见第 2 页「下一轮练习计划」。</dd></div>' +
          '</dl>'
        : '') +
      '</section>' +
      '<section id="review-dimensions" class="report-section">' +
      '<h2 class="report-section-title"><span aria-hidden="true">二</span>五维评价</h2>' +
      '<div class="evaluation-body">' +
      '<figure class="radar-figure">' +
      renderRadar(dims) +
      '<figcaption>本次五维表现</figcaption>' +
      '</figure>' +
      '<div class="table-wrap" tabindex="0" role="region" aria-label="五维评价明细表">' +
      '<table class="report-table dimension-table"><thead><tr><th scope="col">评价维度</th><th scope="col">本次</th><th scope="col">本次点评</th></tr></thead>' +
      '<tbody>' + dimensionRows + '</tbody></table>' +
      '<p class="report-note">依据全国高校辅导员素质能力大赛谈心谈话环节评审表。各维度满分 20，合计 100。</p>' +
      '<ul class="rubric-legend">' +
      '<li><strong>共情引导</strong>尊重接纳学生情绪，换位思考，快速建立信任。</li>' +
      '<li><strong>思想引领</strong>立场鲜明、价值导向正确，自然融入谈话。</li>' +
      '<li><strong>问题解决</strong>研判问题实质，提出可行的思路与办法。</li>' +
      '<li><strong>临场应变</strong>应对情绪变化与突发状况，调整策略和节奏。</li>' +
      '<li><strong>语言表达</strong>表达流畅、条理清晰，有感染力和说服力。</li>' +
      '</ul>' +
      '</div></div></section>' +
      '<footer class="sheet-footer"><span>评价依据：本次对话转写</span><span>第1页 / 共2页</span></footer>' +
      '</article>' +

      '<article class="report-sheet" aria-label="第2页：对话分析与改进">' +
      '<header class="sheet-heading"><h2>对话分析与改进计划</h2><span class="sheet-page">02 / 02</span></header>' +
      '<section id="review-transcript" class="report-section">' +
      '<h2 class="report-section-title"><span aria-hidden="true">三</span>完整对话记录</h2>' +
      '<p class="report-note">本次对话转写（按发言顺序），供对照下方点评定位原话。</p>' +
      renderTranscript(data.turns) +
      '</section>' +
      '<section id="review-evidence" class="report-section">' +
      '<h2 class="report-section-title"><span aria-hidden="true">四</span>五维点评与证据</h2>' +
      evidenceBlocks +
      '</section>' +
      '<section id="review-next" class="report-section">' +
      '<div class="practice-heading">' +
      '<h2 class="report-section-title"><span aria-hidden="true">五</span>下一轮练习计划</h2>' +
      '<a class="button" href="conversation.html"><span data-icon="refresh"></span>再练一次</a>' +
      '</div>' +
      (practiceItems
        ? '<ol class="practice-sequence">' + practiceItems + '</ol>'
        : '<p class="report-note">暂无明确建议。</p>') +
      '</section>' +
      '<footer class="sheet-footer"><span>本报告用于训练复盘，不代替专业判断</span><span>第2页 / 共2页</span></footer>' +
      '</article>' +
      '</div>' +
      '<nav class="report-pagination" aria-label="报告分页">' +
        '<button type="button" class="button outline" data-page-prev disabled>上一页</button>' +
        '<span class="page-indicator" data-page-indicator>第 1 / 2 页</span>' +
        '<button type="button" class="button" data-page-next>下一页</button>' +
      '</nav>'

    setupPagination()

    // 重新水合图标（"再练一次"按钮里的 refresh 图标）
    if (window.hydrateIcons) window.hydrateIcons(root)
  }

  async function load() {
    if (!sessionId) {
      setMessage(
        '还没有可复盘的会话。请先到<a href="conversation.html">谈话训练</a>完成一段对话，再点「结束并查看复盘」。',
      )
      return
    }

    setMessage('<span class="dot" style="display:inline-block;margin-right:8px"></span>正在加载复盘…')

    try {
      let res = await fetch(API_BASE + '/sessions/' + encodeURIComponent(sessionId) + '/review')
      if (res.status === 404) {
        setMessage('该会话还没有复盘，正在生成（评价模型分析中，约需十几秒）…')
        res = await fetch(API_BASE + '/sessions/' + encodeURIComponent(sessionId) + '/review', {
          method: 'POST',
        })
      }
      if (!res.ok) {
        let detail = ''
        try {
          const err = await res.json()
          detail = err.detail || ''
        } catch (_) {}
        setMessage('无法生成复盘：' + escapeHtml(detail || 'HTTP ' + res.status))
        return
      }
      const data = await res.json()
      renderReport(data)
    } catch (err) {
      setMessage('请求后端失败：' + escapeHtml(err && err.message ? err.message : err))
    }
  }

  if (root) load()
})()
