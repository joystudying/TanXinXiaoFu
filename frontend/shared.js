const paths = {
  chat: '<path d="M21 11.5a8.5 8.5 0 0 1-8.5 8.5H4l-2 2v-9.5A8.5 8.5 0 0 1 10.5 4H13a8 8 0 0 1 8 7.5Z"/><path d="M7 11h9M7 15h5"/>',
  book: '<path d="M12 7c-3-2-6-2-10-1v14c4-1 7-1 10 1 3-2 6-2 10-1V6c-4-1-7-1-10 1Z"/><path d="M12 7v14"/>',
  heart:
    '<path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z"/>',
  users:
    '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2m20 0v-2a4 4 0 0 0-3-3.9"/><circle cx="9" cy="7" r="4"/><path d="M16 3.1a4 4 0 0 1 0 7.8"/>',
  home: '<path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1Z"/><path d="M9 21v-9h6v9"/>',
  compass: '<circle cx="12" cy="12" r="10"/><path d="m16 8-3 5-5 3 3-5Z"/>',
  shield: '<path d="m12 3 9 4v5c0 5-4 8-9 10-5-2-9-5-9-10V7Z"/><path d="m8 12 3 3 5-6"/>',
  arrow: '<path d="M4 12h16m-6-6 6 6-6 6"/>',
  back: '<path d="M20 12H4m6-6-6 6 6 6"/>',
  search: '<circle cx="10.5" cy="10.5" r="7.5"/><path d="m16 16 5 5"/>',
  refresh: '<path d="M3 10a9 9 0 0 1 15-6l3 3m0-5v5h-5M21 14A9 9 0 0 1 6 20l-3-3m0 5v-5h5"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  mic: '<rect x="9" y="2" width="6" height="13" rx="3"/><path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3M8 22h8"/>',
  audio: '<path d="M2 10v4m4-8v12m4-15v18m4-14v10m4-12v14m4-9v4"/>',
  volume: '<path d="m11 4-6 5H2v6h3l6 5Zm4 4a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14"/>',
  file: '<path d="M14 2H5a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V9Z"/><path d="M14 2v7h7M7 13h10M7 17h7"/>',
  target:
    '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
  pen: '<path d="m16 3 5 5M4 16 16 4a3 3 0 0 1 4 4L8 20l-5 1Z"/>',
  bulb: '<path d="M9 18h6m-5 4h4M8 14a7 7 0 1 1 8 0c-1 1-1 2-1 4H9c0-2 0-3-1-4Z"/>',
  check: '<path d="m5 12 4 4L20 5"/>',
  down: '<path d="m6 9 6 6 6-6"/>',
  download: '<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>',
  history: '<path d="M3 10a9 9 0 1 1 1 8M3 4v6h6M12 7v5l4 2"/>',
  plus: '<path d="M12 4v16M4 12h16"/>',
  more: '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
  headphones:
    '<path d="M3 14v-3a9 9 0 0 1 18 0v3"/><rect x="2" y="12" width="5" height="9" rx="2"/><rect x="17" y="12" width="5" height="9" rx="2"/>',
}
function icon(name) {
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.file}</svg>`
}

const current = document.body.dataset.page
const favicon = document.createElement('link')
favicon.rel = 'icon'
favicon.href = 'assets/icon.svg'
document.head.append(favicon)
const navigation = [
  ['selection', '场景选择', 'index.html'],
  ['conversation', '谈话训练', 'conversation.html'],
  ['review', '评价与复盘', 'review.html'],
  ['records', '训练记录', 'records.html'],
]
document.querySelector('[data-header]').innerHTML =
  `<div class="header-inner"><a class="brand" href="index.html" aria-label="谈心小辅，返回场景选择"><img class="brand-logo" src="assets/tanxin-logo-jade.png" alt="谈心小辅" width="224" height="75" /><span class="brand-caption">辅导员训练空间</span></a><nav aria-label="主导航">${navigation.map(([key, label, href]) => `<a href="${href}" ${key === current ? 'aria-current="page"' : ''}>${label}</a>`).join('')}</nav><div class="account"><span class="account-avatar">林</span><span>林老师</span></div></div>`
document.querySelector('[data-footer]').innerHTML =
  '<div class="footer-inner"><span>谈心小辅 · 辅导员谈话训练</span><span>谈前准备 · 模拟谈话 · 谈话复盘</span></div>'
function hydrateIcons(root = document) {
  root.querySelectorAll('[data-icon]').forEach((element) => {
    element.innerHTML = icon(element.dataset.icon)
  })
}
hydrateIcons()

const transcriptMessages = document.querySelector('.transcript-messages')
if (transcriptMessages) transcriptMessages.scrollTop = transcriptMessages.scrollHeight

const categoryButtons = [...document.querySelectorAll('[data-category]')]
const categoryTitles = {
  academic: ['学业困难', '了解困难，回应挫败感'],
  emotion: ['情绪困扰', '练习倾听与回应感受'],
  relationship: ['人际关系', '理解分歧，支持表达边界'],
  family: ['家庭困境', '尊重隐私，讨论支持'],
  career: ['就业迷茫', '澄清选择，协商下一步'],
  risk: ['危机识别与联动', '练习风险确认与支持联动'],
}
const caseRows = [...document.querySelectorAll('[data-case-row]')]
const caseSearch = document.querySelector('[data-search-cases]')
const searchEmpty = document.querySelector('[data-search-empty]')

function activeCategory() {
  return (
    document.querySelector('[data-category][aria-pressed="true"]')?.dataset.category ?? 'academic'
  )
}

function applyCaseFilter() {
  const category = activeCategory()
  const query = caseSearch?.value.trim() ?? ''
  let visible = 0
  caseRows.forEach((row) => {
    const matches = row.dataset.category === category && (!query || row.textContent.includes(query))
    row.hidden = !matches
    if (matches) visible += 1
  })
  if (searchEmpty) searchEmpty.hidden = visible > 0
}

categoryButtons.forEach((button) =>
  button.addEventListener('click', () => {
    categoryButtons.forEach((item) => item.setAttribute('aria-pressed', String(item === button)))
    const [title, description] = categoryTitles[button.dataset.category]
    document.querySelector('[data-category-title]').textContent = title
    document.querySelector('[data-category-description]').textContent = description
    if (caseSearch) caseSearch.value = ''
    applyCaseFilter()
  }),
)
caseSearch?.addEventListener('input', applyCaseFilter)
document.querySelector('[data-clear-search]')?.addEventListener('click', () => {
  caseSearch.value = ''
  applyCaseFilter()
  caseSearch.focus()
})
applyCaseFilter()
const filterButtons = [...document.querySelectorAll('[data-filter]')]
filterButtons.forEach((button) =>
  button.addEventListener('click', () => {
    filterButtons.forEach((item) => item.setAttribute('aria-pressed', String(item === button)))
    document.querySelectorAll('[data-record]').forEach((row) => {
      row.hidden = button.dataset.filter !== 'all' && row.dataset.record !== button.dataset.filter
    })
  }),
)
document.querySelector('[data-toggle-transcript]')?.addEventListener('click', (event) => {
  const button = event.currentTarget
  const transcript = document.querySelector('[data-transcript]')
  transcript.hidden = !transcript.hidden
  document
    .querySelector('.conversation-grid')
    .classList.toggle('transcript-closed', transcript.hidden)
  button.setAttribute('aria-expanded', String(!transcript.hidden))
  button.querySelector('span').textContent = transcript.hidden ? '展开记录' : '收起记录'
})
document.querySelectorAll('[data-preview-action]').forEach((button) =>
  button.addEventListener('click', () => {
    const notice = document.querySelector('[data-preview-notice]')
    notice.textContent = `${button.dataset.previewAction}服务暂未连接，请稍后再试。`
    notice.hidden = false
  }),
)
document.querySelector('[data-reset-preview]')?.addEventListener('click', () => {
  document.querySelector('[data-preview-notice]').hidden = true
})
