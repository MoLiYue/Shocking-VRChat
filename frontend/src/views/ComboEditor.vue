<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api, apiPost } from '@/api'

const activeChannel = ref<'a' | 'b'>('a')
const switchDuration = ref(0.3)
const shockDuration = ref(2)
const shockPreset = ref('')
const shockScale = ref(1.0)
const touchPreset = ref('')
const touchScale = ref(0.35)
const touchDerivative = ref(1)
const triggerBottom = ref(0)
const triggerTop = ref(1)
const presets = ref<string[]>([])
const msg = ref('')

async function loadPresets() {
  const data = await api('/api/v1/wave_presets')
  presets.value = data.presets || []
}

async function loadCombo() {
  const data = await api(`/api/v1/combo/${activeChannel.value}`)
  switchDuration.value = data.combo?.switch_duration ?? 0.3
  shockDuration.value = data.shock?.duration ?? 2
  shockPreset.value = data.shock?.wave_preset || ''
  shockScale.value = data.shock?.wave_scale ?? 1.0
  touchPreset.value = data.touch?.wave_preset || ''
  touchScale.value = data.touch?.wave_scale ?? 0.35
  touchDerivative.value = data.touch?.n_derivative ?? 1
  triggerBottom.value = data.trigger_range?.bottom ?? 0
  triggerTop.value = data.trigger_range?.top ?? 1
}

async function saveCombo() {
  const data = await apiPost(`/api/v1/combo/${activeChannel.value}`, {
    combo: { switch_duration: switchDuration.value },
    shock: { duration: shockDuration.value, wave_preset: shockPreset.value || null, wave_scale: shockScale.value },
    touch: { wave_preset: touchPreset.value || null, wave_scale: touchScale.value, n_derivative: touchDerivative.value },
    trigger_range: { bottom: triggerBottom.value, top: triggerTop.value },
  })
  msg.value = data.success ? '已保存' : '保存失败'
  setTimeout(() => msg.value = '', 3000)
}

function switchChannel(ch: 'a' | 'b') { activeChannel.value = ch; loadCombo() }

onMounted(() => { loadPresets(); loadCombo() })
</script>

<template>
  <div>
    <h1>⚡ Combo 模式配置</h1>
    <p style="color:var(--muted);margin:8px 0 16px;font-size:0.85em">短触发 → Shock (一激灵) · 持续触摸 → Touch (柔和)</p>

    <div class="tabs">
      <button :class="{active: activeChannel === 'a'}" @click="switchChannel('a')">Channel A</button>
      <button :class="{active: activeChannel === 'b'}" @click="switchChannel('b')">Channel B</button>
    </div>

    <div class="grid">
      <div class="card">
        <h2>组合逻辑</h2>
        <label>切换时长: {{ switchDuration.toFixed(2) }}s</label>
        <input type="range" v-model.number="switchDuration" min="0.1" max="1.5" step="0.05">

        <h2 style="margin-top:16px">Shock 参数</h2>
        <label>持续时长: {{ shockDuration.toFixed(1) }}s</label>
        <input type="range" v-model.number="shockDuration" min="0.5" max="5" step="0.1">
        <label>波形预设</label>
        <select v-model="shockPreset"><option value="">默认</option><option v-for="p in presets" :key="p" :value="p">{{ p }}</option></select>
        <label>波形强度: {{ shockScale.toFixed(2) }}</label>
        <input type="range" v-model.number="shockScale" min="0" max="1" step="0.05">

        <h2 style="margin-top:16px">Touch 参数</h2>
        <label>波形预设</label>
        <select v-model="touchPreset"><option value="">默认</option><option v-for="p in presets" :key="p" :value="p">{{ p }}</option></select>
        <label>波形强度: {{ touchScale.toFixed(2) }}</label>
        <input type="range" v-model.number="touchScale" min="0" max="1" step="0.05">
        <label>导数阶数</label>
        <select v-model.number="touchDerivative">
          <option :value="0">0 - 距离</option>
          <option :value="1">1 - 速度</option>
          <option :value="2">2 - 加速度</option>
          <option :value="3">3 - 急动度</option>
        </select>

        <div class="actions" style="margin-top:16px">
          <button class="btn btn-green" @click="saveCombo">保存</button>
          <button class="btn btn-gray" @click="loadCombo">重载</button>
        </div>
        <div v-if="msg" class="msg">{{ msg }}</div>
      </div>

      <div class="card">
        <h2>行为示意</h2>
        <div class="diagram">
          <div class="phase phase-shock">⚡ Shock<br>一激灵</div>
          <div class="divider">{{ switchDuration.toFixed(2) }}s</div>
          <div class="phase phase-touch">🤚 Touch<br>柔和抚摸</div>
        </div>
        <h2 style="margin-top:16px">Trigger Range</h2>
        <label>下界: {{ triggerBottom.toFixed(2) }}</label>
        <input type="range" v-model.number="triggerBottom" min="0" max="0.5" step="0.01">
        <label>上界: {{ triggerTop.toFixed(2) }}</label>
        <input type="range" v-model.number="triggerTop" min="0.3" max="1" step="0.01">
      </div>
    </div>
  </div>
</template>

<style scoped>
.tabs { display: flex; gap: 8px; margin-bottom: 16px; }
.tabs button { padding: 8px 20px; border: 1px solid var(--line); border-radius: 8px; background: var(--panel); color: var(--muted); cursor: pointer; }
.tabs button.active { border-color: var(--blue); color: var(--blue); }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
label { display: block; font-size: 0.82em; color: var(--muted); margin: 8px 0 4px; }
select, input[type="range"] { width: 100%; }
select { padding: 8px; border: 1px solid var(--line); border-radius: 8px; background: var(--panel-2); color: var(--text); }
input[type="range"] { accent-color: var(--blue); }
.diagram { display: flex; align-items: stretch; height: 100px; gap: 2px; }
.phase { flex: 1; display: flex; align-items: center; justify-content: center; border-radius: 8px; text-align: center; font-size: 0.85em; line-height: 1.4; }
.phase-shock { background: rgba(255,107,107,0.1); border: 1px solid rgba(255,107,107,0.3); color: #ff8b8b; }
.phase-touch { background: rgba(114,224,143,0.1); border: 1px solid rgba(114,224,143,0.3); color: var(--green); flex: 2; }
.divider { display: flex; align-items: center; padding: 0 6px; font-size: 0.7em; color: var(--amber); }
.actions { display: flex; gap: 8px; }
.msg { margin-top: 8px; font-size: 0.85em; color: var(--green); }
@media (max-width: 768px) { .grid { grid-template-columns: 1fr; } }
</style>
