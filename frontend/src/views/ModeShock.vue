<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api, apiPost } from '@/api'

const ch = ref<'a' | 'b'>('a')
const duration = ref(2)
const wavePreset = ref('')
const waveScale = ref(1.0)
const triggerBottom = ref(0)
const triggerTop = ref(0.8)
const presets = ref<string[]>([])
const msg = ref('')

async function loadPresets() {
  const data = await api('/api/v1/wave_presets')
  presets.value = data.presets || []
}

async function load() {
  const data = await api(`/api/v1/mode_config/${ch.value}/shock`)
  const cfg = data.config || {}
  duration.value = cfg.duration ?? 2
  wavePreset.value = cfg.wave_preset || ''
  waveScale.value = cfg.wave_scale ?? 1.0
  triggerBottom.value = data.trigger_range?.bottom ?? 0
  triggerTop.value = data.trigger_range?.top ?? 0.8
}

async function save() {
  const data = await apiPost(`/api/v1/mode_config/${ch.value}/shock`, {
    duration: duration.value,
    wave_preset: wavePreset.value || null,
    wave_scale: waveScale.value,
    trigger_range: { bottom: triggerBottom.value, top: triggerTop.value },
  })
  msg.value = data.success ? '✓ 已保存' : '✗ 保存失败'
  setTimeout(() => msg.value = '', 3000)
}

function switchCh(c: 'a' | 'b') { ch.value = c; load() }
onMounted(() => { loadPresets(); load() })
</script>

<template>
  <div>
    <h1 class="gradient-text" style="font-size:var(--text-2xl);margin-bottom:var(--sp-2)">⚡ 电击模式</h1>
    <p class="page-desc">触发后电击固定时长。被持续触碰时电到触碰离开后延续该时长。</p>

    <div class="ch-tabs">
      <button :class="{ active: ch === 'a' }" @click="switchCh('a')">通道 A</button>
      <button :class="{ active: ch === 'b' }" @click="switchCh('b')">通道 B</button>
    </div>

    <div class="grid">
      <section class="card">
        <h2>电击参数</h2>
        <div class="field">
          <label>电击时长: {{ duration.toFixed(1) }}s</label>
          <input type="range" v-model.number="duration" min="0.5" max="10" step="0.1">
          <p class="hint">触发后持续输出的秒数。</p>
        </div>
        <div class="field">
          <label>波形预设</label>
          <select v-model="wavePreset">
            <option value="">默认电击波</option>
            <option v-for="p in presets" :key="p" :value="p">{{ p }}</option>
          </select>
        </div>
        <div class="field">
          <label>波形强度: {{ (waveScale * 100).toFixed(0) }}%</label>
          <input type="range" v-model.number="waveScale" min="0" max="1" step="0.05">
          <p class="hint">波形纹理的强度系数，不影响通道设定强度。</p>
        </div>
      </section>

      <section class="card">
        <h2>触发阈值</h2>
        <div class="field">
          <label>下界 (bottom): {{ triggerBottom.toFixed(2) }}</label>
          <input type="range" v-model.number="triggerBottom" min="0" max="0.9" step="0.01">
          <p class="hint">OSC 值超过此值时触发电击。</p>
        </div>
        <div class="field">
          <label>上界 (top): {{ triggerTop.toFixed(2) }}</label>
          <input type="range" v-model.number="triggerTop" min="0.1" max="1" step="0.01">
          <p class="hint">Shock 模式下此值被忽略。</p>
        </div>
        <div class="visual">
          <div class="bar">
            <div class="fill" :style="{ left: (triggerBottom*100)+'%', width: ((triggerTop-triggerBottom)*100)+'%' }"></div>
            <span class="mark" :style="{ left: (triggerBottom*100)+'%' }">{{ triggerBottom.toFixed(2) }}</span>
            <span class="mark" :style="{ left: (triggerTop*100)+'%' }">{{ triggerTop.toFixed(2) }}</span>
          </div>
        </div>
      </section>
    </div>

    <div class="save-bar">
      <button class="btn btn-primary" @click="save">💾 保存</button>
      <button class="btn btn-ghost" @click="load">↺ 重载</button>
      <span class="msg">{{ msg }}</span>
    </div>
  </div>
</template>

<style scoped>
.page-desc { color: var(--text-muted); font-size: var(--text-sm); margin-bottom: var(--sp-4); }
.ch-tabs { display: flex; gap: var(--sp-2); margin-bottom: var(--sp-4); }
.ch-tabs button { padding: var(--sp-2) var(--sp-4); border: 1px solid var(--border); border-radius: var(--radius-md); background: transparent; color: var(--text-muted); cursor: pointer; font-size: var(--text-sm); }
.ch-tabs button.active { border-color: var(--accent); color: var(--accent); background: rgba(139,92,246,0.08); }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--sp-4); }
.field { margin-bottom: var(--sp-4); }
.field label { display: block; font-size: var(--text-sm); color: var(--text-secondary); margin-bottom: var(--sp-1); font-weight: 500; }
.field select, .field input[type="number"] { width: 100%; }
.field input[type="range"] { width: 100%; accent-color: var(--accent); }
.hint { font-size: var(--text-xs); color: var(--text-muted); margin-top: var(--sp-1); }
.visual { margin-top: var(--sp-3); }
.bar { position: relative; height: 8px; background: var(--bg-inset); border-radius: 4px; }
.fill { position: absolute; top: 0; height: 100%; background: var(--accent); border-radius: 4px; opacity: 0.4; }
.mark { position: absolute; top: 14px; font-size: 10px; color: var(--text-muted); transform: translateX(-50%); }
.save-bar { display: flex; align-items: center; gap: var(--sp-3); margin-top: var(--sp-5); padding: var(--sp-4); background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius-lg); }
.msg { font-size: var(--text-sm); color: var(--success); }
@media (max-width: 768px) { .grid { grid-template-columns: 1fr; } }
</style>
