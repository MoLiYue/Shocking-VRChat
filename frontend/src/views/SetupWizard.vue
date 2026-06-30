<script setup lang="ts">
import { ref } from 'vue'
import { apiPost } from '@/api'

const step = ref(0)
const modeA = ref('distance')
const modeB = ref('distance')
const strengthA = ref(100)
const strengthB = ref(100)
const oscPort = ref(9001)
const oscHost = ref('127.0.0.1')
const done = ref(false)
const msg = ref('')

const MODES = [
  { value: 'distance', label: 'distance - 强度曲线模式' },
  { value: 'shock', label: 'shock - 电击模式' },
  { value: 'touch', label: 'touch - 触摸模式' },
  { value: 'combo', label: 'combo - 组合模式' },
  { value: 'boost', label: 'boost - 强度增减模式' },
]

async function save() {
  const payload = {
    channel_a: { mode: modeA.value, strength_limit: strengthA.value, avatar_params: [] },
    channel_b: { mode: modeB.value, strength_limit: strengthB.value, avatar_params: [] },
    osc: { listen_port: oscPort.value, listen_host: oscHost.value },
  }
  const data = await apiPost('/api/v1/setup', payload)
  if (data.success) { done.value = true; setTimeout(() => window.location.href = '/dashboard', 2000) }
  else msg.value = data.message || '保存失败'
}
</script>

<template>
  <div class="wizard" v-if="!done">
    <h1>⚡ 首次配置向导</h1>

    <!-- Step 0: Mode -->
    <div v-if="step === 0" class="step">
      <h2>选择工作模式</h2>
      <label>通道 A</label>
      <select v-model="modeA"><option v-for="m in MODES" :key="m.value" :value="m.value">{{ m.label }}</option></select>
      <label>通道 B</label>
      <select v-model="modeB"><option v-for="m in MODES" :key="m.value" :value="m.value">{{ m.label }}</option></select>
      <div class="nav"><button class="btn btn-blue" @click="step++">下一步 →</button></div>
    </div>

    <!-- Step 1: Strength -->
    <div v-if="step === 1" class="step">
      <h2>强度限制</h2>
      <label>通道 A 上限: {{ strengthA }}</label>
      <input type="number" v-model.number="strengthA" min="0" max="200">
      <label>通道 B 上限: {{ strengthB }}</label>
      <input type="number" v-model.number="strengthB" min="0" max="200">
      <div class="nav"><button class="btn btn-gray" @click="step--">← 上一步</button><button class="btn btn-blue" @click="step++">下一步 →</button></div>
    </div>

    <!-- Step 2: OSC -->
    <div v-if="step === 2" class="step">
      <h2>OSC 端口</h2>
      <label>监听端口</label>
      <input type="number" v-model.number="oscPort" min="1024" max="65535">
      <label>监听地址</label>
      <input type="text" v-model="oscHost">
      <p class="hint">默认 9001 端口。有面捕冲突时请修改。</p>
      <div class="nav"><button class="btn btn-gray" @click="step--">← 上一步</button><button class="btn btn-green" @click="save">✓ 保存并启动</button></div>
      <div v-if="msg" class="err">{{ msg }}</div>
    </div>
  </div>

  <div v-else class="wizard done">
    <h2>✓ 配置完成！</h2>
    <p>正在跳转到 Dashboard...</p>
  </div>
</template>

<style scoped>
.wizard { max-width: 500px; margin: 60px auto; padding: 32px; background: var(--panel); border-radius: 16px; border: 1px solid var(--line); }
.wizard h1 { text-align: center; margin-bottom: 24px; }
.step h2 { color: var(--blue); margin-bottom: 12px; }
label { display: block; font-size: 0.85em; color: var(--muted); margin: 12px 0 4px; }
select, input { width: 100%; padding: 10px; border: 1px solid var(--line); border-radius: 8px; background: var(--panel-2); color: var(--text); font-size: 0.9em; }
.nav { display: flex; justify-content: space-between; margin-top: 20px; gap: 8px; }
.hint { font-size: 0.8em; color: #555; margin-top: 6px; }
.err { font-size: 0.85em; color: #ff8b8b; margin-top: 8px; }
.done { text-align: center; }
.done h2 { color: var(--green); }
</style>
