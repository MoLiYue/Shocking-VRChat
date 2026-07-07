<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, watch, nextTick } from 'vue'
import { api, apiPost } from '@/api'
import { Bar } from 'vue-chartjs'
import {
  Chart as ChartJS,
  BarElement,
  CategoryScale,
  LinearScale,
  Tooltip,
  Legend,
} from 'chart.js'

ChartJS.register(BarElement, CategoryScale, LinearScale, Tooltip, Legend)

const channel = ref<'A' | 'B'>('A')
const strength = ref(50)
const waveScale = ref(1.0)
const preset = ref('')
const presets = ref<string[]>([])
const playing = ref(false)
const msg = ref('')

// Waveform data (real-time)
const waveData = ref<number[]>([])
let pollTimer: ReturnType<typeof setInterval> | null = null
let updateTimer: ReturnType<typeof setTimeout> | null = null

// Preset preview
const previewCanvasRef = ref<HTMLCanvasElement | null>(null)
const previewInfo = ref('')
interface SectionData {
  freq_low: number; freq_high: number; freq_mode: number
  duration: number; n_points: number; repeats: number
  points: { strength: number; anchor: boolean }[]
}
const previewSections = ref<SectionData[]>([])
const previewSpeed = ref(1)

// Chart.js config (real-time)
const chartData = computed(() => ({
  labels: waveData.value.map(() => ''),
  datasets: [{
    data: waveData.value,
    backgroundColor: waveData.value.map(v => v > 0 ? 'rgba(139,92,246,0.85)' : 'transparent'),
    borderWidth: 0,
    barPercentage: 1.0,
    categoryPercentage: 1.0,
  }]
}))

const chartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  animation: false as const,
  plugins: {
    legend: { display: false },
    tooltip: {
      callbacks: {
        label: (ctx: any) => `${ctx.raw}%`,
      }
    }
  },
  scales: {
    x: {
      display: false,
      grid: { display: false },
    },
    y: {
      min: 0,
      max: 100,
      grid: {
        color: 'rgba(139,92,246,0.1)',
      },
      ticks: {
        color: 'rgba(255,255,255,0.4)',
        font: { size: 10 },
        callback: (v: any) => v + '%',
        stepSize: 25,
      }
    }
  }
}

async function loadPresets() {
  const data = await api('/api/v1/wave_presets')
  presets.value = data.presets || []
}

async function loadPreview() {
  if (!preset.value) {
    previewSections.value = []
    previewInfo.value = ''
    return
  }
  try {
    const data = await api(`/api/v1/wave_presets/${encodeURIComponent(preset.value)}/preview`)
    previewSections.value = data.sections || []
    previewSpeed.value = data.speed || 1
    const totalPulses = previewSections.value.reduce((sum: number, s: SectionData) => sum + s.n_points * s.repeats, 0)
    previewInfo.value = `${previewSections.value.length} 小节 · ${totalPulses} 脉冲 · ${data.speed || 1}x`
    await nextTick()
    drawPreview()
  } catch {
    previewInfo.value = '加载失败'
  }
}

function drawPreview() {
  const canvas = previewCanvasRef.value
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

  const sections = previewSections.value
  if (!sections.length) return

  // Total pulses across all sections (with repeats)
  const totalPulses = sections.reduce((sum, s) => sum + s.n_points * s.repeats, 0)
  if (totalPulses <= 0) return

  const barW = w / totalPulses
  let x = 0
  const colors = [
    'rgba(139,92,246,', // purple
    'rgba(59,130,246,', // blue
    'rgba(52,211,153,', // green
    'rgba(251,191,36,', // amber
    'rgba(248,113,113,', // red
    'rgba(168,85,247,', // violet
  ]

  for (let si = 0; si < sections.length; si++) {
    const sec = sections[si]
    const baseColor = colors[si % colors.length]

    for (let rep = 0; rep < sec.repeats; rep++) {
      const alpha = rep === 0 ? '0.85)' : '0.45)'
      for (let pi = 0; pi < sec.n_points; pi++) {
        const pt = sec.points[pi]
        const barH = (pt.strength / 100) * (h - 18)

        if (pt.strength > 0) {
          ctx.fillStyle = baseColor + alpha
          ctx.fillRect(x, h - 16 - barH, Math.max(barW - 0.3, 0.5), barH)
        }
        x += barW
      }
    }

    // Section divider
    if (si < sections.length - 1) {
      ctx.strokeStyle = 'rgba(255,255,255,0.2)'
      ctx.lineWidth = 1
      ctx.setLineDash([2, 2])
      ctx.beginPath()
      ctx.moveTo(x, 0)
      ctx.lineTo(x, h - 16)
      ctx.stroke()
      ctx.setLineDash([])
    }
  }

  // Y labels
  ctx.fillStyle = 'rgba(255,255,255,0.35)'
  ctx.font = '9px Inter, sans-serif'
  ctx.fillText('100%', 2, 10)
  ctx.fillText('0%', 2, h - 18)

  // Section labels
  x = 0
  for (let si = 0; si < sections.length; si++) {
    const sec = sections[si]
    const secW = sec.n_points * sec.repeats * barW
    const label = `${sec.n_points}×${sec.repeats}`
    ctx.fillStyle = colors[si % colors.length] + '0.9)'
    ctx.font = '9px Inter, sans-serif'
    const tx = x + secW / 2 - ctx.measureText(label).width / 2
    ctx.fillText(label, Math.max(tx, x + 1), h - 4)
    x += secW
  }

  // Grid
  ctx.strokeStyle = 'rgba(139,92,246,0.06)'
  ctx.lineWidth = 1
  for (let pct = 25; pct <= 75; pct += 25) {
    const py = h - 16 - (pct / 100) * (h - 18)
    ctx.beginPath(); ctx.moveTo(0, py); ctx.lineTo(w, py); ctx.stroke()
  }
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

function startPolling() {
  if (pollTimer) return
  pollTimer = setInterval(async () => {
    try {
      const data = await api('/api/v1/wave_history')
      const ch = channel.value
      waveData.value = data[ch] || []
    } catch {}
  }, 200)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

watch([strength, waveScale], onParamChange)
watch(preset, () => { loadPreview(); onParamChange() })

onMounted(async () => {
  await loadPresets()
  await loadStatus()
  if (playing.value) {
    startPolling()
  }
  if (preset.value) {
    await loadPreview()
  }
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
      <div class="chart-container">
        <Bar :data="chartData" :options="chartOptions" />
      </div>
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
        <h2>预设预览</h2>
        <div class="preview-container" v-if="preset">
          <div class="preview-info">{{ previewInfo }}</div>
          <canvas ref="previewCanvasRef" class="preview-canvas"></canvas>
          <div class="preview-legend">
            <span class="legend-item">每柱=1脉冲</span>
            <span class="legend-item">浅色=循环重复</span>
            <span class="legend-item">虚线=小节分界</span>
          </div>
        </div>
        <div v-else class="empty-preview">选择预设查看波形预览</div>
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
.chart-container { height: 150px; padding: var(--sp-2) var(--sp-3); }
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
.preview-container { display: flex; flex-direction: column; gap: var(--sp-2); }
.preview-info { font-size: var(--text-xs); color: var(--text-secondary); padding: var(--sp-2) var(--sp-3); background: rgba(139,92,246,0.05); border-radius: var(--radius-sm); }
.preview-canvas { width: 100%; height: 150px; border-radius: var(--radius-md); display: block; }
.preview-legend { display: flex; gap: var(--sp-4); font-size: var(--text-xs); color: var(--text-muted); padding-top: var(--sp-1); }
.legend-item { display: flex; align-items: center; gap: var(--sp-1); }
.empty-preview { padding: var(--sp-6); text-align: center; color: var(--text-muted); font-size: var(--text-sm); }
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
