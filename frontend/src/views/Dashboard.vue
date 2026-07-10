<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { api, apiPost, apiDelete, apiPut } from '@/api'
import QrCode from '@/components/QrCode.vue'

// --- State ---
const connected = ref(false)
const deviceCount = ref(0)
const strength = ref({ A: 0, B: 0 })
const limit = ref({ A: 100, B: 100 })
const oscStatus = ref('')
const lastTrigger = ref('-')
const oscEvents = ref<any[]>([])
const waveA = ref<{s: number; f: number}[]>([])
const waveB = ref<{s: number; f: number}[]>([])
const canvasARef = ref<HTMLCanvasElement | null>(null)
const canvasBRef = ref<HTMLCanvasElement | null>(null)
const qrContent = ref('')
const logs = ref<{text: string; level: string}[]>([])

// Control
const ctrlChannel = ref('all')
const ctrlStrength = ref(0)

// Wave test
const wavePresets = ref<string[]>([])
const selectedPreset = ref('')
const waveDuration = ref(3)
const previewSamples = ref<number[]>([])
const previewInfo = ref('')

// Profiles
const profiles = ref<string[]>([])
const profileName = ref('')
const profileMsg = ref('')

let intervals: number[] = []
let dashWs: WebSocket | null = null

// --- WebSocket-based real-time data ---
function connectLiveWs() {
  if (dashWs) return
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
  const wsUrl = `${proto}//${location.host}/ws/live`
  dashWs = new WebSocket(wsUrl)
  dashWs.onopen = () => {
    dashWs!.send(JSON.stringify({ subscribe: ['wave_A', 'wave_B', 'osc', 'status'] }))
  }
  dashWs.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data)
      if (msg.topic === 'wave_A' && msg.samples) {
        waveA.value.push(...msg.samples)
        if (waveA.value.length > 200) waveA.value = waveA.value.slice(-200)
        drawWave(canvasARef.value, waveA.value)
      } else if (msg.topic === 'wave_B' && msg.samples) {
        waveB.value.push(...msg.samples)
        if (waveB.value.length > 200) waveB.value = waveB.value.slice(-200)
        drawWave(canvasBRef.value, waveB.value)
      } else if (msg.topic === 'osc' && msg.event) {
        oscEvents.value.unshift(msg.event)
        if (oscEvents.value.length > 20) oscEvents.value = oscEvents.value.slice(0, 20)
        lastTrigger.value = '刚刚'
      } else if (msg.topic === 'status') {
        const devices = msg.devices || []
        deviceCount.value = devices.length
        connected.value = devices.length > 0
        if (devices.length > 0) {
          strength.value = devices[0].strength || { A: 0, B: 0 }
          limit.value = {
            A: Math.min(devices[0].strength_max?.A || 0, devices[0].strength_limit?.A || 100),
            B: Math.min(devices[0].strength_max?.B || 0, devices[0].strength_limit?.B || 100),
          }
        }
      }
    } catch {}
  }
  dashWs.onclose = () => {
    dashWs = null
    // Reconnect after 2s
    setTimeout(connectLiveWs, 2000)
  }
  dashWs.onerror = () => { dashWs?.close() }
}

function disconnectLiveWs() {
  if (dashWs) { dashWs.close(); dashWs = null }
}

// --- Polling (fallback for initial load and status heartbeat) ---
async function pollStatus() {
  try {
    const data = await api('/api/v1/status')
    const devices = data.devices || []
    deviceCount.value = devices.length
    connected.value = devices.length > 0
    if (devices.length > 0) {
      const attr = devices[0].attr
      strength.value = attr.strength
      limit.value = {
        A: Math.min(attr.strength_max?.A || 0, attr.strength_limit?.A || 100),
        B: Math.min(attr.strength_max?.B || 0, attr.strength_limit?.B || 100),
      }
    }
    oscStatus.value = data.osc_listening || ''
    if (data.last_osc_time) {
      const ago = Math.round(Date.now() / 1000 - data.last_osc_time)
      lastTrigger.value = ago < 2 ? '刚刚' : `${ago}s 前`
    } else { lastTrigger.value = '无数据' }
  } catch { connected.value = false }
}

function drawWave(canvas: HTMLCanvasElement | null, samples: {s: number; f: number}[]) {
  if (!canvas) return
  const dpr = window.devicePixelRatio || 1
  const W = canvas.clientWidth
  const H = canvas.clientHeight
  if (W < 1 || H < 1) return
  canvas.width = W * dpr
  canvas.height = H * dpr
  const ctx = canvas.getContext('2d')!
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)

  // Clear
  ctx.fillStyle = 'rgba(10, 8, 16, 0.95)'
  ctx.fillRect(0, 0, W, H)

  // Grid
  ctx.strokeStyle = 'rgba(139,92,246,0.08)'
  ctx.lineWidth = 1
  for (let pct = 25; pct <= 75; pct += 25) {
    const py = H - (pct / 100) * H
    ctx.beginPath(); ctx.moveTo(0, py); ctx.lineTo(W, py); ctx.stroke()
  }

  const DISPLAY = 200
  const data = samples.slice(-DISPLAY)
  if (!data.length) return

  const slotW = W / DISPLAY
  const xBase = (DISPLAY - data.length) * slotW

  for (let i = 0; i < data.length; i++) {
    const sample = data[i]
    if (sample.s <= 0) continue

    // Duty cycle: f=10 (densest) → widest, f=240 (sparsest) → narrowest
    const dutyCycle = Math.max(0.05, 1 - (sample.f - 10) / (240 - 10))
    const barW = slotW * dutyCycle
    const barH = (sample.s / 100) * H
    const x = xBase + i * slotW + (slotW - barW) / 2

    // Color: high freq (f=10) = purple, low freq (f=240) = reddish
    const freqT = 1 - (sample.f - 10) / 230
    const r = Math.round(139 + (1 - freqT) * 100)
    const g = Math.round(92 * freqT)
    const b = Math.round(246 * freqT + 100 * (1 - freqT))
    ctx.fillStyle = `rgba(${r},${g},${b},0.85)`
    ctx.fillRect(x, H - barH, Math.max(barW, 0.5), barH)
  }
}

// --- Actions ---
function addLog(msg: string, level = '') {
  logs.value.unshift({ text: `[${new Date().toLocaleTimeString()}] ${msg}`, level })
  if (logs.value.length > 80) logs.value.pop()
}

function getChannels(): string[] {
  return ctrlChannel.value === 'all' ? ['A', 'B'] : [ctrlChannel.value]
}

async function sendStrength() {
  const hex = Math.min(ctrlStrength.value, 100).toString(16).padStart(2, '0').toUpperCase()
  const wave = '0A0A0A0A' + hex + hex + hex + hex
  for (const ch of getChannels()) await api(`/api/v1/sendwave/${ch}/10/${wave}`)
  addLog(`发送固定强度 ${ctrlStrength.value} → ${ctrlChannel.value}`)
}

async function sendShock() {
  const duration = Math.min(ctrlStrength.value / 20 || 1, 5)
  await api(`/api/v1/shock/${ctrlChannel.value}/${duration}`)
  addLog(`Shock ${ctrlChannel.value} ${duration.toFixed(1)}s`)
}

async function sendStop() {
  for (const ch of getChannels()) await api(`/api/v1/sendwave/${ch}/10/0A0A0A0A00000000`)
  addLog('停止输出')
}

// Wave presets
async function loadPresets() {
  const data = await api('/api/v1/wave_presets')
  wavePresets.value = data.presets || []
  if (wavePresets.value.length && !selectedPreset.value) {
    selectedPreset.value = wavePresets.value[0]
    previewWave()
  }
}

async function previewWave() {
  if (!selectedPreset.value) { previewSamples.value = []; previewInfo.value = ''; return }
  try {
    const data = await api(`/api/v1/wave_presets/${encodeURIComponent(selectedPreset.value)}/preview`)
    previewSamples.value = data.strength_samples || []
    previewInfo.value = `${data.ops_count} ops · ${(data.duration_ms / 1000).toFixed(1)}s`
  } catch { previewInfo.value = '加载失败' }
}

async function sendWave() {
  if (!selectedPreset.value) { addLog('请选择预设', 'warn'); return }
  for (const ch of getChannels()) await api(`/api/v1/wave_preset/${ch}/${encodeURIComponent(selectedPreset.value)}/${waveDuration.value}`)
  addLog(`发送 ${selectedPreset.value} → ${ctrlChannel.value} (${waveDuration.value}s)`)
}

async function quickTest() {
  if (!selectedPreset.value) return
  for (const ch of getChannels()) await api(`/api/v1/wave_preset/${ch}/${encodeURIComponent(selectedPreset.value)}/1`)
  addLog(`试一下 ${selectedPreset.value} → ${ctrlChannel.value}`)
}

// Profiles
async function loadProfiles() {
  const data = await api('/api/v1/profiles')
  profiles.value = data.profiles || []
}

async function saveProfile() {
  if (!profileName.value.trim()) return
  const data = await apiPut(`/api/v1/profiles/${encodeURIComponent(profileName.value)}`)
  if (data.success) { profileMsg.value = '已保存'; profileName.value = ''; loadProfiles() }
  else profileMsg.value = data.message || '失败'
  setTimeout(() => profileMsg.value = '', 3000)
}

async function loadProfile(name: string) {
  const data = await apiPost(`/api/v1/profiles/${encodeURIComponent(name)}`)
  if (data.success) addLog(`切换预设: ${name}`)
}

async function deleteProfile(name: string) {
  if (!confirm(`删除 "${name}"？`)) return
  await apiDelete(`/api/v1/profiles/${encodeURIComponent(name)}`)
  loadProfiles()
}

// QR
async function loadQr() {
  try {
    const data = await api('/api/v1/qr_payload')
    qrContent.value = data.content || ''
  } catch {}
}

// Helpers
function barPct(ch: 'A' | 'B') {
  const l = limit.value[ch]
  return l > 0 ? Math.min(strength.value[ch] / l * 100, 100) : 0
}
function shortPath(addr: string) { return addr.replace('/avatar/parameters/', '') }
function timeStr(ts: number) { return new Date(ts * 1000).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'}) }
function presetLabel(name: string) { return name.replace(/^pulse-/, '').replace(/-\d+$/, '') }

onMounted(() => {
  pollStatus(); loadPresets(); loadProfiles(); loadQr()
  connectLiveWs()
  // Reduced polling: only status every 5s as fallback (WS handles real-time)
  intervals.push(window.setInterval(pollStatus, 5000))
})
onUnmounted(() => {
  intervals.forEach(clearInterval)
  disconnectLiveWs()
})
</script>

<template>
  <div class="dashboard">
    <!-- Stats row -->
    <div class="stats-row">
      <div class="stat-card" :class="connected ? 'stat-on' : ''">
        <span class="stat-dot" :class="connected ? 'on' : ''"></span>
        <div>
          <div class="stat-val">{{ connected ? `${deviceCount} 台已连接` : '等待连接' }}</div>
          <div class="stat-sub">郊狼设备</div>
        </div>
      </div>
      <div class="stat-card">
        <span class="stat-icon">📡</span>
        <div><div class="stat-val">{{ oscStatus || '-' }}</div><div class="stat-sub">OSC 监听</div></div>
      </div>
      <div class="stat-card">
        <span class="stat-icon">⏱</span>
        <div><div class="stat-val">{{ lastTrigger }}</div><div class="stat-sub">最近触发</div></div>
      </div>
    </div>

    <div class="grid-2">
      <!-- Left column -->
      <div class="col">
        <!-- Channels -->
        <section class="card">
          <h2>设备状态</h2>
          <div class="ch-row" v-for="ch in (['A', 'B'] as const)" :key="ch">
            <div class="ch-head"><span class="ch-name">{{ ch }}</span><strong>{{ strength[ch] }} / {{ limit[ch] }}</strong></div>
            <div class="bar-track"><div class="bar-fill" :class="'bar-' + ch.toLowerCase()" :style="{width: barPct(ch) + '%'}"></div></div>
          </div>
        </section>

        <!-- OSC Feed -->
        <section class="card">
          <h2>OSC 触发</h2>
          <div class="osc-feed">
            <div class="osc-row" v-for="(e, i) in oscEvents" :key="i">
              <span class="badge" :class="'b-' + e.channel.toLowerCase()">{{ e.channel }}</span>
              <span class="osc-mode">{{ e.mode }}</span>
              <span class="osc-path">{{ shortPath(e.address) }}</span>
              <span class="osc-val">{{ e.value }}</span>
              <span class="osc-time">{{ timeStr(e.time) }}</span>
            </div>
            <div v-if="!oscEvents.length" class="empty">等待数据...</div>
          </div>
        </section>

        <!-- Wave visualization -->
        <section class="card">
          <h2>实时波形</h2>
          <div class="wave-grid">
            <div class="wave-panel">
              <div class="wave-label">A</div>
              <canvas ref="canvasARef" class="wave-canvas"></canvas>
            </div>
            <div class="wave-panel">
              <div class="wave-label">B</div>
              <canvas ref="canvasBRef" class="wave-canvas"></canvas>
            </div>
          </div>
        </section>

        <!-- Logs -->
        <section class="card">
          <h2>日志</h2>
          <div class="log-area">
            <div v-for="(l, i) in logs" :key="i" class="log-line" :class="l.level">{{ l.text }}</div>
            <div v-if="!logs.length" class="empty">暂无日志</div>
          </div>
        </section>
      </div>

      <!-- Right column -->
      <div class="col">
        <!-- QR -->
        <section class="card">
          <h2>连接二维码</h2>
          <QrCode :content="qrContent" :size="240" />
          <div class="qr-text">{{ qrContent }}</div>
        </section>

        <!-- Strength control -->
        <section class="card">
          <h2>强度控制</h2>
          <div class="form-field">
            <label>通道</label>
            <select v-model="ctrlChannel"><option value="A">A</option><option value="B">B</option><option value="all">全部</option></select>
          </div>
          <div class="form-field">
            <label>强度: {{ ctrlStrength }}</label>
            <input type="range" v-model.number="ctrlStrength" min="0" max="100">
          </div>
          <div class="btn-group">
            <button class="btn btn-danger" @click="sendStrength">发送固定强度</button>
            <button class="btn btn-success" @click="sendShock">Shock</button>
            <button class="btn btn-gray" @click="sendStop">停止</button>
          </div>
        </section>

        <!-- Wave test -->
        <section class="card">
          <h2>波形测试</h2>
          <div class="form-field">
            <label>波形预设</label>
            <select v-model="selectedPreset" @change="previewWave">
              <option v-for="p in wavePresets" :key="p" :value="p">{{ presetLabel(p) }}</option>
            </select>
          </div>
          <div class="preview-info" v-if="previewInfo">{{ previewInfo }}</div>
          <div class="form-field">
            <label>持续: {{ waveDuration }}s</label>
            <input type="range" v-model.number="waveDuration" min="1" max="10">
          </div>
          <div class="btn-group">
            <button class="btn btn-primary" @click="sendWave">发送预设</button>
            <button class="btn btn-success" @click="quickTest">试一下(1s)</button>
          </div>
        </section>

        <!-- Profiles -->
        <section class="card">
          <h2>场景预设</h2>
          <div class="profile-list">
            <div class="profile-item" v-for="p in profiles" :key="p">
              <span class="profile-name">{{ p }}</span>
              <button class="btn-sm load" @click="loadProfile(p)">▶</button>
              <button class="btn-sm del" @click="deleteProfile(p)">✕</button>
            </div>
            <div v-if="!profiles.length" class="empty">无预设</div>
          </div>
          <div class="profile-add">
            <input type="text" v-model="profileName" placeholder="新预设名" @keyup.enter="saveProfile">
            <button class="btn btn-primary" @click="saveProfile">保存当前</button>
          </div>
          <div v-if="profileMsg" class="profile-msg">{{ profileMsg }}</div>
        </section>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dashboard { display: flex; flex-direction: column; gap: var(--sp-5); }

.stats-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--sp-4); }
.stat-card {
  display: flex; align-items: center; gap: var(--sp-4);
  padding: var(--sp-5);
  background: var(--bg-card);
  backdrop-filter: var(--blur);
  border: 1px solid var(--border);
  border-radius: var(--radius-xl);
  transition: all var(--transition);
}
.stat-card:hover { border-color: var(--border-hover); box-shadow: var(--glow-sm); }
.stat-card.stat-on { border-color: rgba(52, 211, 153, 0.3); box-shadow: 0 0 20px rgba(52,211,153,0.08); }
.stat-dot { width: 10px; height: 10px; border-radius: 50%; background: var(--text-muted); transition: all var(--transition); }
.stat-dot.on { background: var(--success); box-shadow: 0 0 12px rgba(52,211,153,0.6); animation: pulse 2s infinite; }
@keyframes pulse { 0%,100% { box-shadow: 0 0 12px rgba(52,211,153,0.6); } 50% { box-shadow: 0 0 20px rgba(52,211,153,0.3); } }
.stat-icon { font-size: 1.5em; }
.stat-val { font-size: var(--text-base); font-weight: 600; }
.stat-sub { font-size: var(--text-xs); color: var(--text-muted); margin-top: 2px; }

.grid-2 { display: grid; grid-template-columns: 1.3fr 0.7fr; gap: var(--sp-5); }
.col { display: flex; flex-direction: column; gap: var(--sp-4); }

/* Channels */
.ch-row { margin-bottom: var(--sp-2); }
.ch-row:last-child { margin-bottom: 0; }
.ch-head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: var(--sp-1); font-size: var(--text-sm); }
.ch-name { font-weight: 700; font-size: var(--text-base); background: var(--gradient-text); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.bar-track { height: 5px; background: rgba(139,92,246,0.1); border-radius: var(--radius-full); overflow: hidden; }
.bar-fill { height: 100%; border-radius: var(--radius-full); transition: width 200ms linear; }
.bar-a { background: linear-gradient(90deg, #34d399, #6ee7b7); box-shadow: 0 0 8px rgba(52,211,153,0.3); }
.bar-b { background: linear-gradient(90deg, #60a5fa, #93c5fd); box-shadow: 0 0 8px rgba(96,165,250,0.3); }

/* OSC feed */
.osc-feed { max-height: 220px; overflow-y: auto; }
.osc-row {
  display: flex; gap: var(--sp-2); align-items: center;
  padding: var(--sp-2) var(--sp-3); border-radius: var(--radius-sm);
  font-size: var(--text-xs); font-family: var(--font-mono);
  transition: background var(--transition);
}
.osc-row:hover { background: rgba(139,92,246,0.05); }
.badge { padding: 2px 7px; border-radius: var(--radius-sm); font-weight: 700; font-size: 10px; }
.b-a { background: rgba(52,211,153,0.12); color: var(--success); }
.b-b { background: rgba(96,165,250,0.12); color: var(--info); }
.osc-mode { color: var(--warning); min-width: 48px; }
.osc-path { flex: 1; color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.osc-val { color: var(--accent-2); min-width: 40px; text-align: right; font-variant-numeric: tabular-nums; }
.osc-time { color: var(--text-muted); min-width: 52px; text-align: right; }

/* QR */
.qr-text { margin-top: var(--sp-3); font-size: var(--text-xs); font-family: var(--font); color: var(--text-muted); word-break: break-all; padding: var(--sp-2) var(--sp-3); background: rgba(139,92,246,0.05); border-radius: var(--radius-sm); }

/* Wave */
.wave-grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--sp-3); }
.wave-panel { position: relative; }
.wave-label { position: absolute; top: var(--sp-2); left: var(--sp-3); font-size: var(--text-xs); font-weight: 700; color: var(--text-muted); }
.wave-canvas { width: 100%; height: 120px; border-radius: var(--radius-md); background: rgba(10,8,16,0.5); border: 1px solid var(--border); }

/* Controls */
.form-field { margin-bottom: var(--sp-4); }
.form-field label { display: block; font-size: var(--text-xs); color: var(--text-muted); margin-bottom: var(--sp-2); font-weight: 500; }
.form-field select { width: 100%; }
.btn-group { display: flex; gap: var(--sp-2); flex-wrap: wrap; }

/* Wave preview */
.preview-info { font-size: var(--text-xs); color: var(--text-secondary); margin-bottom: var(--sp-3); padding: var(--sp-2) var(--sp-3); background: rgba(139,92,246,0.05); border-radius: var(--radius-sm); }

/* Profiles */
.profile-list { max-height: 140px; overflow-y: auto; margin-bottom: var(--sp-3); }
.profile-item { display: flex; align-items: center; gap: var(--sp-2); padding: var(--sp-2) var(--sp-3); border-radius: var(--radius-sm); transition: background var(--transition); }
.profile-item:hover { background: rgba(139,92,246,0.05); }
.profile-name { flex: 1; font-size: var(--text-sm); }
.btn-sm { border: none; border-radius: var(--radius-full); padding: 3px 10px; cursor: pointer; font-size: var(--text-xs); color: #fff; transition: all var(--transition); }
.btn-sm:hover { transform: scale(1.05); }
.btn-sm.load { background: var(--success); }
.btn-sm.del { background: rgba(248,113,113,0.7); }
.profile-add { display: flex; gap: var(--sp-2); }
.profile-add input { flex: 1; }
.profile-msg { font-size: var(--text-xs); color: var(--success); margin-top: var(--sp-2); }

/* Logs */
.log-area { max-height: 140px; overflow-y: auto; font-family: var(--font-mono); font-size: var(--text-xs); padding: var(--sp-2); background: rgba(0,0,0,0.2); border-radius: var(--radius-md); }
.log-line { padding: 2px var(--sp-2); color: var(--text-muted); }
.log-line.warn { color: var(--warning); }
.log-line.error { color: var(--danger); }

.empty { padding: var(--sp-6); text-align: center; color: var(--text-muted); font-size: var(--text-sm); }

@media (max-width: 768px) {
  .stats-row { grid-template-columns: 1fr; }
  .grid-2 { grid-template-columns: 1fr; }
}
</style>
