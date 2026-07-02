<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { api, apiPost } from '@/api'

const channel = ref<'A' | 'B'>('A')
const strength = ref(50)
const waveScale = ref(1.0)
const duration = ref(1.0)
const preset = ref('')
const presets = ref<string[]>([])
const sending = ref(false)
const msg = ref('')

async function loadPresets() {
  const data = await api('/api/v1/wave_presets')
  presets.value = data.presets || []
  if (presets.value.length > 0 && !preset.value) {
    preset.value = presets.value[0]
  }
}

async function sendTest() {
  sending.value = true
  msg.value = ''
  try {
    const data = await apiPost('/api/v1/wave_test', {
      channel: channel.value,
      strength: strength.value,
      wave_scale: waveScale.value,
      preset: preset.value || null,
      duration_s: duration.value,
    })
    if (data.result === 'OK') {
      msg.value = `✓ 已发送 (强度=${data.strength}, 缩放=${data.wave_scale}, ${data.waves_sent}帧)`
    } else {
      msg.value = '发送失败'
    }
  } catch (e: any) {
    msg.value = `错误: ${e.message}`
  }
  sending.value = false
  setTimeout(() => msg.value = '', 5000)
}

const effectiveOutput = computed(() => {
  // Each wave op has max strength 100 (0x64), scaled by wave_scale, then multiplied by device strength
  // So effective = strength * wave_scale
  return Math.round(strength.value * waveScale.value)
})

const equivalentAt100 = computed(() => {
  // What wave_scale would give same output at strength 100
  return Math.min(1.0, strength.value * waveScale.value / 100).toFixed(2)
})

onMounted(loadPresets)
</script>

<template>
  <div>
    <h1 class="gradient-text" style="font-size:var(--text-2xl);margin-bottom:var(--sp-2)">波形测试</h1>
    <p class="page-desc">手动发送测试脉冲到设备，调整强度和波形缩放观察体感差异。用于校准 wave_scale 使不同强度下体感一致。</p>

    <div class="test-grid">
      <section class="card">
        <h2>参数设置</h2>

        <div class="field">
          <label>通道</label>
          <div class="channel-tabs">
            <button :class="{ active: channel === 'A' }" @click="channel = 'A'">A</button>
            <button :class="{ active: channel === 'B' }" @click="channel = 'B'">B</button>
          </div>
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
          <label>持续时间 <span class="val">{{ duration.toFixed(1) }}s</span></label>
          <input type="range" v-model.number="duration" min="0.1" max="5" step="0.1">
        </div>

        <div class="field">
          <label>波形预设</label>
          <select v-model="preset">
            <option value="">默认电击波</option>
            <option v-for="p in presets" :key="p" :value="p">{{ p.replace('pulse-', '').replace(/-\d+$/, '') }}</option>
          </select>
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
            <li>先用 <code>强度=100, 缩放=1.0</code> 记住体感</li>
            <li>把强度调到你的目标值（如 200）</li>
            <li>调低缩放直到体感一致</li>
            <li>记下此缩放值 → 填入配置的 <code>wave_scale</code></li>
          </ol>
        </div>

        <div class="send-area">
          <button class="btn btn-primary btn-lg" @click="sendTest" :disabled="sending">
            {{ sending ? '发送中...' : '⚡ 发送测试脉冲' }}
          </button>
          <span class="msg" v-if="msg">{{ msg }}</span>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.page-desc { color: var(--text-muted); font-size: var(--text-sm); margin-bottom: var(--sp-5); }
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
.equiv-table { margin-bottom: var(--sp-4); }
.equiv-row { display: flex; justify-content: space-between; align-items: center; padding: var(--sp-2) var(--sp-3); border-radius: var(--radius-sm); font-size: var(--text-sm); }
.equiv-row.highlight { background: rgba(139,92,246,0.08); border: 1px solid rgba(139,92,246,0.2); }
.equiv-label { color: var(--text-muted); }
.equiv-formula { color: var(--text-secondary); font-variant-numeric: tabular-nums; }
.equiv-value { color: var(--accent); font-weight: 700; font-size: var(--text-base); font-variant-numeric: tabular-nums; }
.calc-tip { padding: var(--sp-3); background: var(--bg-tertiary); border-radius: var(--radius-md); margin-bottom: var(--sp-4); font-size: var(--text-sm); color: var(--text-secondary); }
.calc-tip p { margin-bottom: var(--sp-2); }
.calc-tip ol { padding-left: var(--sp-4); }
.calc-tip li { margin-bottom: var(--sp-1); line-height: 1.5; }
.calc-tip code { background: var(--bg-card); padding: 1px 5px; border-radius: var(--radius-sm); font-size: var(--text-xs); }
.send-area { display: flex; align-items: center; gap: var(--sp-3); flex-wrap: wrap; }
.btn-lg { padding: var(--sp-3) var(--sp-6); font-size: var(--text-base); }
.msg { font-size: var(--text-sm); color: var(--success); }
@media (max-width: 768px) { .test-grid { grid-template-columns: 1fr; } }
</style>
