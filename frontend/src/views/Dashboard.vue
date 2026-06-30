<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { api } from '@/api'

interface DeviceAttr {
  strength: { A: number; B: number }
  strength_max: { A: number; B: number }
  strength_limit: { A: number; B: number }
  uuid: string
}

const connected = ref(false)
const deviceCount = ref(0)
const strength = ref({ A: 0, B: 0 })
const limit = ref({ A: 100, B: 100 })
const oscStatus = ref('')
const lastTrigger = ref('-')
const oscEvents = ref<any[]>([])
const waveA = ref<number[]>([])
const waveB = ref<number[]>([])

let intervals: number[] = []

async function pollStatus() {
  try {
    const data = await api('/api/v1/status')
    const devices = data.devices || []
    deviceCount.value = devices.length
    connected.value = devices.length > 0
    if (devices.length > 0) {
      const attr: DeviceAttr = devices[0].attr
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
    } else {
      lastTrigger.value = '无数据'
    }
  } catch { connected.value = false }
}

async function pollOsc() {
  try {
    const data = await api('/api/v1/osc_activity')
    oscEvents.value = (data.events || []).slice(0, 20)
  } catch {}
}

async function pollWave() {
  try {
    const data = await api('/api/v1/wave_history')
    waveA.value = data.A || []
    waveB.value = data.B || []
  } catch {}
}

function barPct(ch: 'A' | 'B') {
  const l = limit.value[ch]
  if (l <= 0) return 0
  return Math.min(strength.value[ch] / l * 100, 100)
}

function shortPath(addr: string) {
  return addr.replace('/avatar/parameters/', '.../')
}

onMounted(() => {
  pollStatus(); pollOsc(); pollWave()
  intervals.push(window.setInterval(pollStatus, 2000))
  intervals.push(window.setInterval(pollOsc, 500))
  intervals.push(window.setInterval(pollWave, 250))
})
onUnmounted(() => intervals.forEach(clearInterval))
</script>

<template>
  <div class="dashboard">
    <div class="dash-header">
      <h1>Dashboard</h1>
      <div class="conn-badge" :class="connected ? 'online' : ''">
        <span class="dot"></span>
        {{ connected ? `已连接 ${deviceCount} 台设备` : '等待郊狼 APP 连接...' }}
      </div>
    </div>

    <!-- Device status -->
    <section class="card">
      <h2>设备状态</h2>
      <div class="status-grid">
        <div class="channel" v-for="ch in (['A', 'B'] as const)" :key="ch">
          <div class="ch-head">
            <span class="ch-label">Channel {{ ch }}</span>
            <strong>{{ strength[ch] }} / {{ limit[ch] }}</strong>
          </div>
          <div class="meter"><div class="meter-fill" :class="'fill-' + ch.toLowerCase()" :style="{width: barPct(ch) + '%'}"></div></div>
        </div>
      </div>
      <div class="status-meta">
        <span>OSC: {{ oscStatus }}</span>
        <span>最近触发: {{ lastTrigger }}</span>
      </div>
    </section>

    <!-- OSC Activity -->
    <section class="card">
      <h2>OSC 触发实况</h2>
      <div class="osc-feed">
        <div class="osc-entry" v-for="(e, i) in oscEvents" :key="i">
          <span class="osc-ch" :class="e.channel === 'A' ? 'ch-a' : 'ch-b'">{{ e.channel }}</span>
          <span class="osc-mode">{{ e.mode }}</span>
          <span class="osc-path" :title="e.address">{{ shortPath(e.address) }}</span>
          <span class="osc-val">{{ e.value }}</span>
        </div>
        <div v-if="!oscEvents.length" class="empty">等待 OSC 数据...</div>
      </div>
    </section>

    <!-- Wave visualization placeholder -->
    <section class="card">
      <h2>实时波形</h2>
      <div class="wave-grid">
        <div class="wave-panel">
          <div class="wave-label">Channel A</div>
          <canvas ref="canvasA" class="wave-canvas"></canvas>
        </div>
        <div class="wave-panel">
          <div class="wave-label">Channel B</div>
          <canvas ref="canvasB" class="wave-canvas"></canvas>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.dashboard { max-width: 1000px; }
.dash-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.dash-header h1 { font-size: 1.6em; }
.conn-badge { display: inline-flex; align-items: center; gap: 8px; padding: 8px 14px; border-radius: 20px; background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); color: var(--muted); font-size: 0.85em; }
.conn-badge .dot { width: 8px; height: 8px; border-radius: 50%; background: #c04e4e; }
.conn-badge.online .dot { background: var(--green); box-shadow: 0 0 10px rgba(114,224,143,0.4); }
.status-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.channel { padding: 14px; border-radius: 12px; background: var(--panel); }
.ch-head { display: flex; justify-content: space-between; margin-bottom: 8px; }
.ch-label { font-size: 1.1em; font-weight: 700; }
.meter { height: 14px; border-radius: 99px; background: #0a1020; overflow: hidden; }
.meter-fill { height: 100%; transition: width 180ms linear; }
.fill-a { background: linear-gradient(90deg, #77e89d, #b0ff91); }
.fill-b { background: linear-gradient(90deg, #66b8ff, #8be8ff); }
.status-meta { display: flex; gap: 20px; margin-top: 10px; font-size: 0.82em; color: var(--muted); }
.osc-feed { max-height: 200px; overflow-y: auto; }
.osc-entry { display: flex; gap: 8px; padding: 4px 8px; font-size: 0.82em; font-family: monospace; align-items: center; }
.osc-entry:nth-child(odd) { background: rgba(255,255,255,0.02); }
.osc-ch { font-weight: 700; min-width: 16px; }
.ch-a { color: var(--green); }
.ch-b { color: var(--blue); }
.osc-mode { color: var(--amber); min-width: 55px; font-size: 0.9em; }
.osc-path { color: #bfccec; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.osc-val { color: var(--accent); min-width: 45px; text-align: right; }
.empty { padding: 16px; text-align: center; color: #444; }
.wave-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.wave-panel { padding: 10px; border-radius: 12px; background: #0c1323; }
.wave-label { font-size: 0.8em; color: var(--muted); margin-bottom: 6px; }
.wave-canvas { width: 100%; height: 120px; border-radius: 8px; background: #080e1a; }
.card + .card { margin-top: 16px; }

@media (max-width: 768px) {
  .status-grid, .wave-grid { grid-template-columns: 1fr; }
  .dash-header { flex-direction: column; align-items: flex-start; gap: 10px; }
}
</style>
