// records.js —— 把「训练记录」页接到后端 /sessions 列表接口，展示真实历史会话。
// 数据来自 turns / evaluations 表，不再使用静态演示数据。
// 只在训练记录页生效。
(function () {
  'use strict'
  if (document.body.dataset.page !== 'records') return

  // 本地（file:// 或 http）直接打本机后端；https 走同源代理（备用）。
  const API_BASE = location.protocol === 'https:' ? '' : 'http://127.0.0.1:8000'
  const panel = document.querySelector('.records-panel')
  const footer = document.querySelector('.record-footer')
  // 当前系统学生角色只有一个（后端 DEFAULT_ROLE），等「场景选择」做成后再按会话取真实姓名。
  const STUDENT_NAME = '小悦'

  function escapeHtml(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
  }

  function fmtTime(iso) {
    const d = new Date(iso)
    if (isNaN(d.getTime())) return '—'
    const p = (n) => String(n).padStart(2, '0')
    return (
      p(d.getMonth() + 1) + '月' + p(d.getDate()) + '日 ' + p(d.getHours()) + ':' + p(d.getMinutes())
    )
  }

  function rowHtml(s) {
    const reviewed = !!s.reviewed
    const scenario = s.scenario || '谈心谈话'
    const initial = escapeHtml(scenario.slice(0, 1))
    const turns = s.turn_count + ' 轮'
    const status = reviewed
      ? '<span class="status"><span class="dot"></span>已完成</span>'
      : '<span class="status pending">进行中</span>'
    const timeNote =
      reviewed && s.total_score != null
        ? '<small>' + turns + ' · ' + s.total_score + ' 分</small>'
        : '<small>' + turns + '</small>'
    return (
      '<article class="record-row" data-record="' + (reviewed ? 'finished' : 'active') + '">' +
      '<div class="record-person">' +
      '<span class="record-initial">' + initial + '</span>' +
      '<div><h2>' + escapeHtml(STUDENT_NAME) + '</h2><p>' + escapeHtml(scenario) + '</p></div>' +
      '</div>' +
      '<div class="record-time">' + fmtTime(s.started_at) + timeNote + '</div>' +
      status +
      '<div class="record-actions">' +
      '<a class="button secondary" href="review.html?session=' + encodeURIComponent(s.session_id) + '">查看复盘</a>' +
      '</div>' +
      '</article>'
    )
  }

  function setFooter(text) {
    if (footer) footer.textContent = text
  }

  async function load() {
    if (!panel || !footer) return
    // 先清掉静态演示行，避免加载期间误以为是真实数据
    panel.querySelectorAll('article.record-row').forEach((el) => el.remove())
    setFooter('加载中…')
    try {
      const res = await fetch(API_BASE + '/sessions')
      if (!res.ok) throw new Error('HTTP ' + res.status)
      const data = await res.json()
      const list = Array.isArray(data) ? data : []
      if (!list.length) {
        footer.insertAdjacentHTML(
          'beforebegin',
          '<div style="padding:40px 16px;text-align:center;color:var(--ink);font-size:15px">' +
            '还没有训练记录。先到<a href="conversation.html">谈话训练</a>开始一段对话吧。</div>',
        )
      } else {
        list.forEach((s) => footer.insertAdjacentHTML('beforebegin', rowHtml(s)))
      }
      setFooter('共 ' + list.length + ' 条记录')
    } catch (err) {
      setFooter('加载失败：' + (err && err.message ? err.message : err))
    }
  }

  load()
})()
