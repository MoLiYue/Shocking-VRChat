<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { api } from '@/api'

const channel = ref<'A' | 'B' | 'all'>('A')
const preset = ref('')
const presets = ref<string[]>([])
const playing = ref(false)
const msg = ref('')

// Waveform display
const canvasRef = ref<HTMLCanvasElement | null>(null)
const waveData = ref<number[]>([])
let pollTimer: ReturnType<typeof setInterval> | null = null
let playTimer: ReturnType<typeof setInterval> | null = null

// Preview
const previewInfo = ref('')
async function loadPresets() {
  const data = await api('/api/v1/wave_presets')
  presets.value = data.presets || []
  if (presets.value.length && !preset.value) {
    preset.value = presets.value[0]
    previewWave()
  }
}

async function previewWave() {
  if (!preset.value) { previewInfo.value = ''; return }
  try {
    const data = await api(`/api/v1/wave_presets/${encodeURIComponent(preset.value)}/preview`)
    previewInfo.value = `${data.ops_count} ops · ${(data.duration_ms / 1000).toFixed(1)}s 周期`
  } catch { previewInfo.value = '加载失败' }
}

function getChannels(): string[] {
  return channel.value === 'all' ? ['A', 'B'] : [channel.value]
}

async function sendWaveOnce() {
  if (!preset.value) return
  // Send 2 seconds of wave (will be called every ~1.5s to overlap and avoid gaps)
  for (const ch of getChannels()) {
    await api(`/api/v1/wave_preset/${ch}/${encodeURIComponent(preset.value)}/2`)
  }
}

async function start() {
  if (!preset.value) {
    msg.value = '请先选择波形预设'
    return
  }
  playing.value = true
  msg.value = ''

  // Send first wave immediately
  await sendWaveOnce()

  // Then send every 1.5s to keep continuous playback (2s waves with 0.5s overlap)
  playTimer = setInterval(async () => {
    if (!playing.value) return
    await sendWaveOnce()
  }, 1500)

  startPolling()
}

function stop() {
  playing.value = false
  msg.value = ''
  if (playTimer) {
    clearInterval(playTimer)
    playTimer = null
  }
  stopPolling()
}

function quickTest() {
  if (!preset.value) { msg.value = '请先选择波形预设'; return }
  for (const ch of getChannels()) {
    api(`/api/v1/wave_preset/${ch}/${encodeURIComponent(preset.value)}/1`)
  }
  msg.value = '已发送 1s 试探'
  setTimeout(() => { if (msg.value === '已发送 1s 试探') msg.value = '' }, 2000)
}

// Real-time waveform polling
function startPolling() {
  if (pollTimer) return
  pollTimer = setInterval(async () => {
    try {
      const data = await api('/api/v1/wave_history')
      const ch = channel.value === 'all' ? 'A' : channel.value
      waveData.value = data[ch] || []
      drawWave()
    } catch {}
  }, 200)
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

  // Wave
  const data = waveData.value
  if (data.length < 2) return
  const step = w / Math.min(data.length, 400)
  const startIdx = Math.max(0, data.length - 400)

  ctx.beginPath()
  ctx.strokeStyle = 'rgba(139,92,246,0.9)'
  ctx.lineWidth = 1.5
  for (let i = 0; i < Math.min(data.length - startIdx, 400); i++) {
    const x = i * step
    const y = h - (data[startIdx + i] / 100) * h
    if (i === 0) ctx.moveTo(x, y)
    else ctx.lineTo(x, y)
  }
  ctx.stroke()

  // Fill under curve
  const lastX = (Math.min(data.length - startIdx, 400) - 1) * step
  ctx.lineTo(lastX, h)
  ctx.lineTo(0, h)
  ctx.closePath()
  ctx.fillStyle = 'rgba(139,92,246,0.08)'
  ctx.fill()

  // Labels
  ctx.fillStyle = 'rgba(255,255,255,0.4)'
  ctx.font = '10px Inter, sans-serif'
  ctx.fillText('100%', 2, 12)
  ctx.fillText('0%', 2, h - 2)
}

watch(preset, previewWave)

onMounted(async () => {
  await loadPresets()
  await nextTick()
  drawWave()
})

onUnmounted(() => {
  stop()
})
</script>

<template>
  <div>
    <h1 class="gradient-text" style="font-size:var(--text-2xl);margin-bottom:var(--sp-2)">波形测试</h1>
    <p class="page-desc">持续循环播放波形到设备，方便体感校准与波形对比。</p>

    <div class="wave-display">
      <div class="wave-header">
        <span class="wave-title">实时波形 · 通道 {{ channel === 'all' ? 'A+B' : channel }}</span>
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
            <button :class="{ active: channel === 'all' }" @click="channel = 'all'" :disabled="playing">全部</button>
          </div>
          <p class="hint" v-if="playing">播放中不可切换通道，请先停止</p>
        </div>

        <div class="field">
          <label>波形预设</label>
          <select v-model="preset" :disabled="playing">
            <option v-for="p in presets" :key="p" :value="p">{{ p.replace(/^pulse-/, '').replace(/-\d+$/, '') }}</option>
          </select>
          <p class="preview-info" v-if="previewInfo">{{ previewInfo }}</p>
        </div>

        <div class="control-bar">
          <button v-if="!playing" class="btn btn-primary btn-lg" @click="start">▶ 开始循环</button>
          <button v-else class="btn btn-danger btn-lg" @click="stop">⏹ 停止</button>
          <button class="btn btn-success" @click="quickTest" :disabled="playing">试一下(1s)</button>
          <span class="msg" v-if="msg">{{ msg }}</span>
        </div>
      </section>

      <section class="card">
        <h2>使用说明</h2>
        <div class="calc-tip">
          <p>💡 <strong>使用方法：</strong></p>
          <ol>
            <li>选择通道和波形预设</li>
            <li>点击 <strong>试一下(1s)</strong> 发送短暂测试波形</li>
            <li>点击 <strong>开始循环</strong> 持续循环发送当前预设</li>
            <li>体验波形效果后，点击 <strong>停止</strong></li>
          </ol>
          <p style="margin-top:var(--sp-3)">📌 <strong>说明：</strong></p>
          <ul>
            <li>循环播放使用与 Dashboard 相同的波形发送接口</li>
            <li>强度受设备端 APP 设定的上限控制</li>
            <li>循环播放时不可切换通道和预设，需先停止</li>
          </ul>
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
.preview-info { font-size: var(--text-xs); color: var(--text-secondary); margin-top: var(--sp-2); padding: var(--sp-2) var(--sp-3); background: rgba(139,92,246,0.05); border-radius: var(--radius-sm); }
.channel-tabs { display: flex; gap: var(--sp-2); }
.channel-tabs button { padding: var(--sp-2) var(--sp-5); border: 1px solid var(--border); border-radius: var(--radius-full); background: transparent; color: var(--text-muted); cursor: pointer; font-size: var(--text-sm); font-weight: 500; transition: all 0.15s; }
.channel-tabs button.active { border-color: var(--accent); color: var(--accent); background: rgba(139,92,246,0.08); }
.channel-tabs button:disabled { opacity: 0.5; cursor: not-allowed; }
.control-bar { display: flex; align-items: center; gap: var(--sp-3); margin-top: var(--sp-4); flex-wrap: wrap; }
.btn-lg { padding: var(--sp-3) var(--sp-6); font-size: var(--text-base); }
.btn-danger { background: var(--danger); border-color: var(--danger); color: white; }
.btn-danger:hover { opacity: 0.9; }
.btn-success { background: var(--success); border-color: var(--success); color: white; }
.btn-success:hover { opacity: 0.9; }
.msg { font-size: var(--text-sm); color: var(--warning); }
.calc-tip { padding: var(--sp-3); background: var(--bg-tertiary); border-radius: var(--radius-md); font-size: var(--text-sm); color: var(--text-secondary); }
.calc-tip p { margin-bottom: var(--sp-2); }
.calc-tip ol, .calc-tip ul { padding-left: var(--sp-4); }
.calc-tip li { margin-bottom: var(--sp-1); line-height: 1.5; }
.calc-tip code { background: var(--bg-card); padding: 1px 5px; border-radius: var(--radius-sm); font-size: var(--text-xs); }
@media (max-width: 768px) { .test-grid { grid-template-columns: 1fr; } }
</style>
