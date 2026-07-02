<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, nextTick, watch } from 'vue'
import { api, apiPost } from '@/api'

const channel = ref<'A' | 'B'>('A')
const strength = ref(50)
const waveScale = ref(1.0)
const preset = ref('')
const presets = ref<string[]>([])
const playing = ref(false)
const msg = ref('')

// Waveform display
const canvasRef = ref<HTMLCanvasElement | null>(null)
const waveData = ref<number[]>([])
let pollTimer: ReturnType<typeof setInterval> | null = null
let updateTimer: ReturnType<typeof setTimeout> | null = null

async function loadPresets() {
  const data = await api('/api/v1/wave_presets')
  presets.value = data.presets || []
}

async function loadStatus() {
  try {
    const data = await api('/api/v1/wave_test/status')
    playing.value = data.active
    if (data.active) {
      channel.value = data.channel
      strength.value = data.strength
      waveScale.value = data.wave_scale
      preset.value = data.preset || ''
    }
  } catch {}
}

async function start() {
  msg.value = ''
  try {
    const data = await apiPost('/api/v1/wave_test/start', {
      channel: channel.value,
      strength: strength.value,
      wave_scale: waveScale.value,
      preset: preset.value || null,
    })
    if (data.result === 'OK') {
      playing.value = true
      startPolling()
    } else {
      msg.value = data.error || '启动失败'
    }
  } catch (e: any) {
    msg.value = e.message || '请求失败'
  }
}

async function stop() {
  try {
    const data = await apiPost('/api/v1/wave_test/stop', {})
    if (data.result === 'OK') {
      playing.value = false
      stopPolling()
    }
  } catch {}
  msg.value = ''
}

async function updateParams() {
  if (!playing.value) return
  try {
    await apiPost('/api/v1/wave_test/update', {
      strength: strength.value,
      wave_scale: waveScale.value,
      preset: preset.value || null,
    })
  } catch {}
}

function onParamChange() {
  if (!playing.value) return
  if (updateTimer) clearTimeout(updateTimer)
  updateTimer = setTimeout(updateParams, 50)
}

// Real-time waveform polling
function startPolling() {
  if (pollTimer) return
  pollTimer = setInterval(async () => {
    try {
      const data = await api('/api/v1/wave_history')
      const ch = channel.value
      waveData.value = data[ch] || []
      drawWave()
    } catch {}
  }, 100)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function drawWave() {
  const canvas = canvasRef.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  const dpr = window.devicePixelRatio || 1
  const rect = canvas.getBoundingClientRect()
  canvas.width = rect.width * dpr
  canvas.height = rect.height * dpr
  ctx.scale(dpr, dpr)
  const w = rect.width
  const h = rect.height

  // Clear
  ctx.fillStyle = 'rgba(15, 15, 30, 0.95)'
  ctx.fillRect(0, 0, w, h)

  // Grid
  ctx.strokeStyle = 'rgba(139,92,246,0.1)'
  ctx.lineWidth = 1
  for (let y = 0; y <= 100; y += 25) {
    const py = h - (y / 100) * h
    ctx.beginPath()
    ctx.moveTo(0, py)
    ctx.lineTo(w, py)
    ctx.stroke()
  }

  // Bar chart - fixed bar width, right-aligned (new data on right, scrolls left)
  const data = waveData.value
  if (!data.length) return
  const barW = 3  // fixed pixel width per sample
  const maxBars = Math.floor(w / barW)
  const bars = data.slice(-maxBars)  // take latest N samples

  // Draw from right: bars[bars.length-1] is rightmost (newest)
  const offsetX = w - bars.length * barW

  ctx.fillStyle = 'rgba(139,92,246,0.85)'
  for (let i = 0; i < bars.length; i++) {
    const v = Math.max(0, Math.min(100, bars[i]))
    if (v <= 0) continue
    const barH = (v / 100) * (h - 4)
    const x = offsetX + i * barW
    const y = h - barH
    ctx.fillRect(x, y, barW, barH)
  }

  // Labels
  ctx.fillStyle = 'rgba(255,255,255,0.4)'
  ctx.font = '10px Inter, sans-serif'
  ctx.fillText('100%', 2, 12)
  ctx.fillText('0%', 2, h - 2)
}

const effectiveOutput = computed(() => Math.round(strength.value * waveScale.value))
const equivalentAt100 = computed(() => Math.min(1.0, strength.value * waveScale.value / 100).toFixed(2))

watch([strength, waveScale, preset], onParamChange)

onMounted(async () => {
  await loadPresets()
  await loadStatus()
  if (playing.value) {
    startPolling()
  }
  await nextTick()
  drawWave()
})

onUnmounted(() => {
  stopPolling()
  if (updateTimer) clearTimeout(updateTimer)
})
</script>

<template>
  <div>
    <h1 class="gradient-text" style="font-size:var(--text-2xl);margin-bottom:var(--sp-2)">波形测试</h1>
    <p class="page-desc">持续循环播放波形到设备，实时调节强度和缩放观察体感差异。</p>

    <div class="wave-display">
      <div class="wave-header">
        <span class="wave-title">实时波形 · 通道 {{ channel }}</span>
        <span class="wave-status" :class="{ active: playing }">{{ playing ? '▶ 播放中' : '⏹ 停止' }}</span>
      </div>
      <canvas ref="canvasRef" class="wave-canvas"></canvas>
    </div>

    <div class="test-grid">
      <section class="card">
        <h2>参数设置</h2>

        <div class="field">
          <label>通道</label>
          <div class="channel-tabs">
            <button :class="{ active: channel === 'A' }" @click="channel = 'A'" :disabled="playing">A</button>
            <button :class="{ active: channel === 'B' }" @click="channel = 'B'" :disabled="playing">B</button>
          </div>
          <p class="hint" v-if="playing">播放中不可切换通道，请先停止</p>
        </div>

        <div class="field">
          <label>强度 <span class="val">{{ strength }}</span></label>
          <input type="range" v-model.number="strength" min="0" max="200" step="1">
          <p class="hint">设备实际输出强度 (0–200)</p>
        </div>

        <div class="field">
          <label>波形缩放 (wave_scale) <span class="val">{{ waveScale.toFixed(2) }}</span></label>
          <input type="range" v-model.number="waveScale" min="0" max="1" step="0.01">
          <p class="hint">0 = 静音, 1 = 波形原始强度</p>
        </div>

        <div class="field">
          <label>波形预设</label>
          <select v-model="preset">
            <option value="">默认电击波</option>
            <option v-for="p in presets" :key="p" :value="p">{{ p.replace(/^pulse-/, '').replace(/-\d+$/, '') }}</option>
          </select>
        </div>

        <div class="control-bar">
          <button v-if="!playing" class="btn btn-primary btn-lg" @click="start">▶ 开始播放</button>
          <button v-else class="btn btn-danger btn-lg" @click="stop">⏹ 停止</button>
          <span class="msg" v-if="msg">{{ msg }}</span>
        </div>
      </section>

      <section class="card">
        <h2>等效分析</h2>
        <div class="equiv-table">
          <div class="equiv-row">
            <span class="equiv-label">当前设置</span>
            <span class="equiv-formula">强度 {{ strength }} × 缩放 {{ waveScale.toFixed(2) }}</span>
          </div>
          <div class="equiv-row highlight">
            <span class="equiv-label">等效输出</span>
            <span class="equiv-value">≈ {{ effectiveOutput }}</span>
          </div>
          <div class="equiv-row">
            <span class="equiv-label">等效于 强度100 × 缩放</span>
            <span class="equiv-value">{{ equivalentAt100 }}</span>
          </div>
        </div>

        <div class="calc-tip">
          <p>💡 <strong>校准方法：</strong></p>
          <ol>
            <li>开始播放，感受 <code>强度=100, 缩放=1.0</code> 的体感</li>
            <li>拖动强度到你的目标值（如 200）</li>
            <li>实时调低缩放直到体感一致</li>
            <li>记下此缩放值 → 填入配置的 <code>wave_scale</code></li>
          </ol>
          <p style="margin-top:var(--sp-2)">播放期间所有参数实时生效，无需停止重开。</p>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.page-desc { color: var(--text-muted); font-size: var(--text-sm); margin-bottom: var(--sp-4); }
.wave-display { margin-bottom: var(--sp-4); background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius-lg); overflow: hidden; }
.wave-header { display: flex; justify-content: space-between; align-items: center; padding: var(--sp-3) var(--sp-4); border-bottom: 1px solid var(--border); }
.wave-title { font-size: var(--text-sm); color: var(--text-secondary); font-weight: 500; }
.wave-status { font-size: var(--text-xs); padding: var(--sp-1) var(--sp-2); border-radius: var(--radius-full); background: var(--bg-tertiary); color: var(--text-muted); }
.wave-status.active { background: rgba(139,92,246,0.15); color: var(--accent); }
.wave-canvas { width: 100%; height: 150px; display: block; }
.test-grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--sp-4); }
.field { margin-bottom: var(--sp-4); }
.field:last-child { margin-bottom: 0; }
.field label { display: block; font-size: var(--text-sm); color: var(--text-secondary); margin-bottom: var(--sp-2); font-weight: 500; }
.field input[type="range"] { width: 100%; accent-color: var(--accent); }
.field select { width: 100%; }
.val { color: var(--accent); font-variant-numeric: tabular-nums; font-weight: 600; }
.hint { font-size: var(--text-xs); color: var(--text-muted); margin-top: var(--sp-1); }
.channel-tabs { display: flex; gap: var(--sp-2); }
.channel-tabs button { padding: var(--sp-2) var(--sp-5); border: 1px solid var(--border); border-radius: var(--radius-full); background: transparent; color: var(--text-muted); cursor: pointer; font-size: var(--text-sm); font-weight: 500; transition: all 0.15s; }
.channel-tabs button.active { border-color: var(--accent); color: var(--accent); background: rgba(139,92,246,0.08); }
.channel-tabs button:disabled { opacity: 0.5; cursor: not-allowed; }
.control-bar { display: flex; align-items: center; gap: var(--sp-3); margin-top: var(--sp-4); }
.btn-lg { padding: var(--sp-3) var(--sp-6); font-size: var(--text-base); }
.btn-danger { background: var(--danger); border-color: var(--danger); color: white; }
.btn-danger:hover { opacity: 0.9; }
.msg { font-size: var(--text-sm); color: var(--warning); }
.equiv-table { margin-bottom: var(--sp-4); }
.equiv-row { display: flex; justify-content: space-between; align-items: center; padding: var(--sp-2) var(--sp-3); border-radius: var(--radius-sm); font-size: var(--text-sm); }
.equiv-row.highlight { background: rgba(139,92,246,0.08); border: 1px solid rgba(139,92,246,0.2); }
.equiv-label { color: var(--text-muted); }
.equiv-formula { color: var(--text-secondary); font-variant-numeric: tabular-nums; }
.equiv-value { color: var(--accent); font-weight: 700; font-size: var(--text-base); font-variant-numeric: tabular-nums; }
.calc-tip { padding: var(--sp-3); background: var(--bg-tertiary); border-radius: var(--radius-md); font-size: var(--text-sm); color: var(--text-secondary); }
.calc-tip p { margin-bottom: var(--sp-2); }
.calc-tip ol { padding-left: var(--sp-4); }
.calc-tip li { margin-bottom: var(--sp-1); line-height: 1.5; }
.calc-tip code { background: var(--bg-card); padding: 1px 5px; border-radius: var(--radius-sm); font-size: var(--text-xs); }
@media (max-width: 768px) { .test-grid { grid-template-columns: 1fr; } }
</style>
