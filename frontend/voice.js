// voice.js —— 将「谈心小辅」原生 HTML 界面对接到后端语音链路（ASR→LLM→TTS）。
// 协议见 README：WS /ws/chat，收 ready / reply / reset，发 text / audio / reset。
// 只在谈话页生效；其余页面不受影响。
(function () {
  'use strict'
  if (document.body.dataset.page !== 'conversation') return

  // WebSocket 走当前页面同源：Caddy 会把 /ws/chat 转发到 FastAPI；
  // 直接从 file:// 打开时回退到本机后端。
  const _host = location.host || '127.0.0.1:8000'
  const _params = new URLSearchParams(location.search)
  const CASE_ID = _params.get('case') || ''
  const _qs = new URLSearchParams()
  if (CASE_ID) _qs.set('case_id', CASE_ID)
  if (_params.get('session')) _qs.set('session_id', _params.get('session'))
  const _q = _qs.toString()
  const WS_URL = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${_host}/ws/chat${_q ? '?' + _q : ''}`

  // ---------- 录音器：麦克风 -> PCM16 / 16kHz / 单声道（FunASR 所需规格） ----------
  const recorder = {
    ctx: null,
    stream: null,
    node: null,
    chunks: [],
    recording: false,
    async start() {
      this.stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      this.ctx = new (window.AudioContext || window.webkitAudioContext)()
      const source = this.ctx.createMediaStreamSource(this.stream)
      this.node = this.ctx.createScriptProcessor(4096, 1, 1)
      this.chunks = []
      this.node.onaudioprocess = (e) => {
        if (!this.recording) return
        const input = e.inputBuffer.getChannelData(0)
        const down = downsample(input, this.ctx.sampleRate, 16000)
        this.chunks.push(floatTo16PCM(down))
      }
      source.connect(this.node)
      this.node.connect(this.ctx.destination)
      this.recording = true
    },
    stop() {
      if (!this.recording) return null
      this.recording = false
      this.node.disconnect()
      this.stream.getTracks().forEach((t) => t.stop())
      if (this.ctx) this.ctx.close()
      let total = 0
      for (const c of this.chunks) total += c.length
      const merged = new Int16Array(total)
      let offset = 0
      for (const c of this.chunks) {
        merged.set(c, offset)
        offset += c.length
      }
      this.chunks = []
      return merged
    },
  }

  function downsample(input, fromRate, toRate) {
    if (fromRate === toRate) return input
    const ratio = fromRate / toRate
    const len = Math.round(input.length / ratio)
    const out = new Float32Array(len)
    for (let i = 0; i < len; i++) out[i] = input[Math.round(i * ratio)]
    return out
  }

  function floatTo16PCM(f32) {
    const out = new Int16Array(f32.length)
    for (let i = 0; i < f32.length; i++) {
      const s = Math.max(-1, Math.min(1, f32[i]))
      out[i] = s < 0 ? s * 0x8000 : s * 0x7fff
    }
    return out
  }

  function int16ToBase64(int16) {
    const bytes = new Uint8Array(int16.buffer)
    let binary = ''
    const CHUNK = 0x8000
    for (let i = 0; i < bytes.length; i += CHUNK) {
      binary += String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK))
    }
    return btoa(binary)
  }

  function playBase64(b64, format) {
    if (!b64) return
    const mime = format === 'wav' ? 'audio/wav' : 'audio/mpeg'
    const audio = new Audio(`data:${mime};base64,${b64}`)
    audio.play().catch(() => {})
  }

  // 把录音得到的 PCM16 / 16kHz / 单声道包一层 WAV 头再播放（用于回听自己的录音）
  function playPcm16(int16) {
    if (!int16) return
    const sampleRate = 16000
    const buffer = new ArrayBuffer(44 + int16.length * 2)
    const view = new DataView(buffer)
    const writeStr = (offset, str) => {
      for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i))
    }
    writeStr(0, 'RIFF')
    view.setUint32(4, 36 + int16.length * 2, true)
    writeStr(8, 'WAVE')
    writeStr(12, 'fmt ')
    view.setUint32(16, 16, true)
    view.setUint16(20, 1, true)
    view.setUint16(22, 1, true)
    view.setUint32(24, sampleRate, true)
    view.setUint32(28, sampleRate * 2, true)
    view.setUint16(32, 2, true)
    view.setUint16(34, 16, true)
    writeStr(36, 'data')
    view.setUint32(40, int16.length * 2, true)
    let offset = 44
    for (let i = 0; i < int16.length; i++) {
      view.setInt16(offset, int16[i], true)
      offset += 2
    }
    const audio = new Audio(URL.createObjectURL(new Blob([view], { type: 'audio/wav' })))
    audio.play().catch(() => {})
  }

  // ---------- DOM ----------
  const els = {
    status: document.querySelector('.presence-status'),
    response: document.querySelector('.current-response blockquote'),
    transcript: document.querySelector('.transcript-messages'),
    round: document.querySelector('[data-transcript-round]'),
    title: document.querySelector('[data-voice-title]'),
    mic: document.querySelector('[data-voice-mic]'),
    micLabel: document.querySelector('[data-voice-mic-label]'),
    replayStudent: document.querySelector('[data-voice-replay-student]'),
    replayTeacher: document.querySelector('[data-voice-replay-teacher]'),
    input: document.querySelector('[data-voice-text]'),
    send: document.querySelector('[data-voice-send]'),
    notice: document.querySelector('[data-preview-notice]'),
  }

  const state = {
    ws: null,
    connected: false,
    busy: false,
    recording: false,
    studentName: '小陈',
    sessionId: null,
    lastStudentAudio: null,
    lastTeacherPcm: null,
    turn: 0,
  }

  function setStatus(text) {
    if (els.status) els.status.innerHTML = `<span class="dot"></span>${text}`
  }

  function setBusy(busy) {
    state.busy = busy
    if (els.mic) els.mic.disabled = busy
    if (els.send) els.send.disabled = busy
    if (els.input) els.input.disabled = busy
    if (els.micLabel) els.micLabel.textContent = busy ? '正在回应…' : '点击开始说话'
  }

  function appendMessage(role, text) {
    if (!els.transcript) return
    const article = document.createElement('article')
    article.className = 'message ' + (role === 'teacher' ? 'teacher' : 'student')
    const speaker = document.createElement('span')
    speaker.className = 'speaker'
    speaker.textContent = role === 'teacher' ? `辅导员 · 第${state.turn}轮` : state.studentName
    const p = document.createElement('p')
    p.textContent = text
    article.append(speaker, p)
    els.transcript.append(article)
    els.transcript.scrollTop = els.transcript.scrollHeight
  }

  function notice(text) {
    if (!els.notice) return
    els.notice.textContent = text
    els.notice.hidden = false
  }

  function clearNotice() {
    if (els.notice) els.notice.hidden = true
  }

  function persistSession(id) {
    if (!id) return
    state.sessionId = id
    try {
      localStorage.setItem('xxt_last_session', id)
    } catch (_) {}
    const link = document.querySelector('a[href^="review.html"]')
    if (link) link.href = 'review.html?session=' + encodeURIComponent(id)
  }

  // ---------- WebSocket ----------
  function connect() {
    const ws = new WebSocket(WS_URL)
    state.ws = ws
    ws.onopen = () => {
      state.connected = true
      setStatus('已连接 · 等待你的回应')
      clearNotice()
    }
    ws.onmessage = (e) => {
      let data
      try {
        data = JSON.parse(e.data)
      } catch (err) {
        return
      }
      if (data.type === 'ready') {
        persistSession(data.session_id)
        state.studentName = data.student_name || state.studentName
        if (els.title) els.title.textContent = `和${state.studentName}聊聊`
        if (els.transcript) els.transcript.innerHTML = ''
        if (els.response) els.response.textContent = '“……”'
        setStatus('已连接 · 等待你的回应')
      } else if (data.type === 'reset') {
        persistSession(data.session_id)
        state.turn = 0
        if (els.transcript) els.transcript.innerHTML = ''
        if (els.round) els.round.textContent = '第0轮'
        if (els.response) els.response.textContent = '“……”'
      } else if (data.type === 'reply') {
        setBusy(false)
        if (data.text) {
          state.turn += 1
          appendMessage('student', data.text)
          if (els.response) els.response.textContent = `“${data.text}”`
          state.lastStudentAudio = data.audio_b64
          if (els.round) els.round.textContent = `第${state.turn}轮`
          setStatus('等待你的回应')
          playBase64(data.audio_b64, data.audio_format)
        } else if (data.note) {
          notice(data.note)
        }
      }
    }
    ws.onclose = () => {
      state.connected = false
      setStatus('连接断开，正在重连…')
      setTimeout(connect, 1500)
    }
    ws.onerror = () => ws.close()
  }

  function send(obj) {
    if (state.ws && state.ws.readyState === WebSocket.OPEN) state.ws.send(JSON.stringify(obj))
  }

  function sendText() {
    const t = els.input ? els.input.value.trim() : ''
    if (!t || state.busy || !state.connected) return
    state.turn += 1
    appendMessage('teacher', t)
    send({ type: 'text', text: t })
    els.input.value = ''
    setBusy(true)
    setStatus('小陈正在回应…')
  }

  async function toggleRecording() {
    if (state.recording) {
      const pcm = recorder.stop()
      state.recording = false
      if (els.micLabel) els.micLabel.textContent = '点击开始说话'
      if (pcm && pcm.length) {
        state.turn += 1
        state.lastTeacherPcm = pcm
        setBusy(true)
        setStatus('识别中…')
        send({ type: 'audio', audio_b64: int16ToBase64(pcm), audio_format: 'pcm16' })
      }
    } else {
      try {
        await recorder.start()
        state.recording = true
        if (els.micLabel) els.micLabel.textContent = '正在录音，点击停止'
        setStatus('正在录音…')
      } catch (err) {
        notice('无法访问麦克风：' + (err && err.message ? err.message : err))
      }
    }
  }

  // ---------- 绑定 ----------
  if (els.mic) els.mic.addEventListener('click', toggleRecording)
  if (els.send) els.send.addEventListener('click', sendText)
  if (els.input) els.input.addEventListener('keydown', (e) => { if (e.key === 'Enter') sendText() })
  if (els.replayStudent)
    els.replayStudent.addEventListener('click', () => {
      if (!state.lastStudentAudio) return notice('还没有学生语音可以回听。')
      playBase64(state.lastStudentAudio, 'mp3')
    })
  if (els.replayTeacher)
    els.replayTeacher.addEventListener('click', () => {
      if (!state.lastTeacherPcm) return notice('还没有你的录音可以回听。')
      playPcm16(state.lastTeacherPcm)
    })

  // ---------- 实时通话（真双工，可选；走 /ws/voice） ----------
  const rtBtn = document.querySelector('[data-voice-realtime]')
  const rtLabel = document.querySelector('[data-voice-realtime-label]')
  let rtSession = null

  function endRealtime() {
    rtSession = null
    if (rtLabel) rtLabel.textContent = '实时通话'
    if (els.mic) els.mic.disabled = false
    if (els.send) els.send.disabled = false
    if (els.input) els.input.disabled = false
  }

  async function toggleRealtime() {
    if (rtSession) {
      rtSession.stop()
      endRealtime()
      setStatus('等待你的回应')
      return
    }
    let mod
    try {
      mod = await import('./js/realtime.js')
    } catch (e) {
      notice('实时通话模块加载失败：' + (e && e.message ? e.message : e))
      return
    }
    if (!mod.realtimeSupported()) {
      notice('这个浏览器不支持实时通话（需要 AudioWorklet + 麦克风），请用 Edge / Chrome。')
      return
    }
    // 实时模式先关掉回合制输入，避免抢麦克风
    if (els.mic) els.mic.disabled = true
    if (els.send) els.send.disabled = true
    if (els.input) els.input.disabled = true
    if (rtLabel) rtLabel.textContent = '结束通话'
    setStatus('正在建立实时语音…')
    try {
      rtSession = await mod.startRealtime({
        onStatus: (s, text) => {
          if (s === 'speaking') setStatus(text || '学生在说…')
          else if (s === 'listening' || s === 'ready') setStatus(text || '听着，你继续说')
          else if (s === 'error') setStatus(text || '实时语音出错')
          else if (s === 'closed') {
            setStatus('实时通话已断开')
            endRealtime()
          } else setStatus(text || '实时通话')
        },
        onTeacherText: (text) => {
          const t = (text || '').trim()
          if (!t) return
          state.turn += 1
          appendMessage('teacher', t)
          if (els.round) els.round.textContent = `第${state.turn}轮`
        },
        onStudentText: (text) => {
          const t = (text || '').trim()
          if (!t) return
          appendMessage('student', t)
          if (els.response) els.response.textContent = `“${t}”`
        },
        onError: (code, message) => notice(`${message || '实时语音出错'}（${code}）`),
        onSession: (id) => persistSession(id),
        caseId: CASE_ID,
      })
    } catch (e) {
      endRealtime()
      notice('实时通话启动失败：' + (e && e.message ? e.message : e))
    }
  }

  if (rtBtn) rtBtn.addEventListener('click', toggleRealtime)

  connect()
})()
