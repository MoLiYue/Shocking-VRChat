<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api, apiPost } from '@/api'

const ch = ref<'a' | 'b'>('a')
const freqMs = ref(10)
const wavePreset = ref('')
const waveScale = ref(1.0)
const textureFloor = ref(0)
const windowOps = ref(4)
const sampleStep = ref(1.0)
const advanceSamples = ref(4.0)
const envelopeCurve = ref('smoothstep')
const triggerBottom = ref(0)
const triggerTop = ref(0.8)
const presets = ref<string[]>([])
const msg = ref('')

async function loadPresets() {
  const data = await api('/api/v1/wave_presets')
  presets.value = data.presets || []
}

async function load() {
  const data = await api(`/api/v1/mode_config/${ch.value}/distance`)
  const cfg = data.config || {}
  freqMs.value = cfg.freq_ms ?? 10
  wavePreset.value = cfg.wave_preset || ''
  waveScale.value = cfg.wave_scale ?? 1.0
  textureFloor.value = cfg.texture_floor ?? 0
  windowOps.value = cfg.wave_window_ops ?? 4
  sampleStep.value = cfg.wave_sample_step ?? 1.0
  advanceSamples.value = cfg.wave_advance_samples ?? 4.0
  envelopeCurve.value = cfg.wave_envelope_curve || 'smoothstep'
  triggerBottom.value = data.trigger_range?.bottom ?? 0
  triggerTop.value = data.trigger_range?.top ?? 0.8
}

async function save() {
  const data = await apiPost(`/api/v1/mode_config/${ch.value}/distance`, {
    freq_ms: freqMs.value,
    wave_preset: wavePreset.value || null,
    wave_scale: waveScale.value,
    texture_floor: textureFloor.value,
    wave_window_ops: windowOps.value,
    wave_sample_step: sampleStep.value,
    wave_advance_samples: advanceSamples.value,
    wave_envelope_curve: envelopeCurve.value,
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
    <h1 class="gradient-text" style="font-size:var(--text-2xl);margin-bottom:var(--sp-2)">📏 距离模式</h1>
    <p class="page-desc">根据与触发区域中心的距离线性控制波形强度。越接近中心越强。</p>

    <div class="ch-tabs">
      <button :class="{ active: ch === 'a' }" @click="switchCh('a')">通道 A</button>
      <button :class="{ active: ch === 'b' }" @click="switchCh('b')">通道 B</button>
    </div>

    <div class="grid">
      <section class="card">
        <h2>波形参数</h2>
        <div class="field">
          <label>波形预设</label>
          <select v-model="wavePreset">
            <option value="">默认（实时生成）</option>
            <option v-for="p in presets" :key="p" :value="p">{{ p }}</option>
          </select>
          <p class="hint">选择预设波形纹理。不选则按频率实时生成。</p>
        </div>
        <div class="field">
          <label>波形强度: {{ (waveScale * 100).toFixed(0) }}%</label>
          <input type="range" v-model.number="waveScale" min="0" max="1" step="0.05">
        </div>
        <div class="field">
          <label>纹理底噪 (texture_floor): {{ (textureFloor * 100).toFixed(0) }}%</label>
          <input type="range" v-model.number="textureFloor" min="0" max="0.5" step="0.01">
          <p class="hint">波形低谷的最小强度，0 表示允许完全静默。</p>
        </div>
        <div class="field">
          <label>实时频率间隔: {{ freqMs }}ms</label>
          <input type="range" v-model.number="freqMs" min="10" max="240" step="5">
          <p class="hint">无预设时使用的固定脉冲间隔。</p>
        </div>
      </section>

      <section class="card">
        <h2>触发阈值</h2>
        <div class="field">
          <label>下界 (bottom): {{ triggerBottom.toFixed(2) }}</label>
          <input type="range" v-model.number="triggerBottom" min="0" max="0.9" step="0.01">
          <p class="hint">OSC 值低于此值视为 0%（不输出）。</p>
        </div>
        <div class="field">
          <label>上界 (top): {{ triggerTop.toFixed(2) }}</label>
          <input type="range" v-model.number="triggerTop" min="0.1" max="1" step="0.01">
          <p class="hint">OSC 值达到此值视为 100%（最大强度）。</p>
        </div>
        <div class="visual">
          <div class="bar">
            <div class="fill" :style="{ left: (triggerBottom*100)+'%', width: ((triggerTop-triggerBottom)*100)+'%' }"></div>
            <span class="mark" :style="{ left: (triggerBottom*100)+'%' }">{{ triggerBottom.toFixed(2) }}</span>
            <span class="mark" :style="{ left: (triggerTop*100)+'%' }">{{ triggerTop.toFixed(2) }}</span>
          </div>
        </div>
      </section>

      <section class="card">
        <h2>高级：波形窗口</h2>
        <div class="field">
          <label>窗口大小: {{ windowOps }} ops</label>
          <input type="range" v-model.number="windowOps" min="1" max="16" step="1">
          <p class="hint">每次发送的波形 op 数量（1 op = 100ms）。</p>
        </div>
        <div class="field">
          <label>采样步进: {{ sampleStep.toFixed(2) }}</label>
          <input type="range" v-model.number="sampleStep" min="0.25" max="4" step="0.25">
          <p class="hint">播放速度倍率。大于 1 加速、小于 1 减慢。</p>
        </div>
        <div class="field">
          <label>窗口推进: {{ advanceSamples.toFixed(1) }}</label>
          <input type="range" v-model.number="advanceSamples" min="1" max="16" step="0.5">
          <p class="hint">每次推进多少采样点。</p>
        </div>
        <div class="field">
          <label>包络曲线</label>
          <select v-model="envelopeCurve">
            <option value="smoothstep">smoothstep（平滑）</option>
            <option value="linear">linear（线性）</option>
            <option value="ease_in">ease_in（渐入）</option>
            <option value="ease_out">ease_out（渐出）</option>
          </select>
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
