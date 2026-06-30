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
    oscEvents.value = (data.events || []).slice(0, 25)
  } catch {}
}

function barPct(ch: 'A' | 'B') {
  const l = limit.value[ch]
  if (l <= 0) return 0
  return Math.min(strength.value[ch] / l * 100, 100)
}

function shortPath(addr: string) {
  return addr.replace('/avatar/parameters/', '')
}

function timeAgo(ts: number) {
  const d = new Date(ts * 1000)
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

onMounted(() => {
  pollStatus(); pollOsc()
  intervals.push(window.setInterval(pollStatus, 2000))
  intervals.push(window.setInterval(pollOsc, 500))
})
onUnmounted(() => intervals.forEach(clearInterval))
</script>

<template>
  <div class="dashboard">
    <!-- Status cards row -->
    <div class="stats-row">
      <div class="stat-card" :class="connected ? 'stat-success' : 'stat-idle'">
        <div class="stat-icon">{{ connected ? '✓' : '○' }}</div>
        <div class="stat-body">
          <div class="stat-value">{{ connected ? deviceCount : 0 }}</div>
          <div class="stat-label">{{ connected ? '设备已连接' : '等待连接' }}</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon">📡</div>
        <div class="stat-body">
          <div class="stat-value">{{ oscStatus || '-' }}</div>
          <div class="stat-label">OSC 监听</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon">⏱</div>
        <div class="stat-body">
          <div class="stat-value">{{ lastTrigger }}</div>
          <div class="stat-label">最近触发</div>
        </div>
      </div>
    </div>

    <!-- Channels -->
    <div class="channels-row">
      <div class="card channel-card" v-for="ch in (['A', 'B'] as const)" :key="ch">
        <div class="channel-header">
          <span class="channel-name">Channel {{ ch }}</span>
          <span class="channel-value">{{ strength[ch] }} <span class="channel-limit">/ {{ limit[ch] }}</span></span>
        </div>
        <div class="progress-track">
          <div class="progress-fill" :class="'fill-' + ch.toLowerCase()" :style="{width: barPct(ch) + '%'}"></div>
        </div>
      </div>
    </div>

    <!-- OSC Feed -->
    <div class="card">
      <h2>OSC 实时触发</h2>
      <div class="osc-feed">
        <div class="osc-row" v-for="(e, i) in oscEvents" :key="i">
          <span class="osc-badge" :class="'badge-' + e.channel.toLowerCase()">{{ e.channel }}</span>
          <span class="osc-mode">{{ e.mode }}</span>
          <span class="osc-path">{{ shortPath(e.address) }}</span>
          <span class="osc-value">{{ e.value }}</span>
          <span class="osc-time">{{ timeAgo(e.time) }}</span>
        </div>
        <div v-if="!oscEvents.length" class="empty-state">
          <span class="empty-icon">📭</span>
          <span>等待 VRChat OSC 数据...</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dashboard { display: flex; flex-direction: column; gap: var(--sp-5); }

/* Stats row */
.stats-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--sp-4); }
.stat-card {
  display: flex; align-items: center; gap: var(--sp-3);
  padding: var(--sp-4) var(--sp-5);
  background: var(--surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
}
.stat-card.stat-success { border-color: rgba(34,197,94,0.3); }
.stat-card.stat-idle { border-color: var(--border-subtle); }
.stat-icon { font-size: 1.5em; }
.stat-value { font-size: var(--text-lg); font-weight: 600; }
.stat-label { font-size: var(--text-xs); color: var(--text-muted); margin-top: 2px; }

/* Channels */
.channels-row { display: grid; grid-template-columns: 1fr 1fr; gap: var(--sp-4); }
.channel-card { padding: var(--sp-5); }
.channel-header { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: var(--sp-3); }
.channel-name { font-size: var(--text-lg); font-weight: 600; }
.channel-value { font-size: var(--text-xl); font-weight: 700; font-variant-numeric: tabular-nums; }
.channel-limit { font-size: var(--text-sm); color: var(--text-muted); font-weight: 400; }
.progress-track { height: 8px; background: var(--bg); border-radius: 4px; overflow: hidden; }
.progress-fill { height: 100%; border-radius: 4px; transition: width 200ms linear; }
.fill-a { background: linear-gradient(90deg, #22c55e, #4ade80); }
.fill-b { background: linear-gradient(90deg, #3b82f6, #60a5fa); }

/* OSC Feed */
.osc-feed { max-height: 320px; overflow-y: auto; }
.osc-row {
  display: grid;
  grid-template-columns: 32px 64px 1fr 60px 64px;
  gap: var(--sp-2);
  align-items: center;
  padding: var(--sp-2) var(--sp-3);
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
}
.osc-row:nth-child(odd) { background: rgba(255,255,255,0.015); }
.osc-badge {
  display: inline-flex; align-items: center; justify-content: center;
  width: 24px; height: 24px;
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  font-weight: 700;
}
.badge-a { background: var(--success-surface); color: var(--success); }
.badge-b { background: var(--info-surface); color: var(--info); }
.osc-mode { color: var(--warning); font-size: var(--text-xs); }
.osc-path { font-family: var(--font-mono); color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.osc-value { font-family: var(--font-mono); color: var(--danger); text-align: right; font-variant-numeric: tabular-nums; }
.osc-time { color: var(--text-muted); font-size: var(--text-xs); text-align: right; }

.empty-state {
  display: flex; flex-direction: column; align-items: center; gap: var(--sp-2);
  padding: var(--sp-10); color: var(--text-muted);
}
.empty-icon { font-size: 2em; opacity: 0.5; }

@media (max-width: 768px) {
  .stats-row { grid-template-columns: 1fr; }
  .channels-row { grid-template-columns: 1fr; }
  .osc-row { grid-template-columns: 28px 1fr 50px; }
  .osc-mode, .osc-time { display: none; }
}
</style>
