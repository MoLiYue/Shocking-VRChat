<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { apiPost } from '@/api'

const router = useRouter()

const step = ref(0)
const totalSteps = 4
const modeA = ref('distance')
const modeB = ref('distance')
const paramsA = ref<string[]>(['/avatar/parameters/pcs/contact/enterPass'])
const paramsB = ref<string[]>(['/avatar/parameters/pcs/contact/enterPass'])
const customA = ref('')
const customB = ref('')
const strengthA = ref(100)
const strengthB = ref(100)
const oscPort = ref(9001)
const oscHost = ref('127.0.0.1')
const done = ref(false)
const saving = ref(false)
const errMsg = ref('')

const MODES = [
  { value: 'distance', label: '强度曲线模式', desc: '参数值通过曲线映射到输出强度' },
  { value: 'shock', label: '电击模式', desc: '超过阈值触发固定时长电击' },
  { value: 'touch', label: '触摸模式', desc: '对触摸速度/变化率做响应' },
  { value: 'combo', label: '组合模式', desc: '短触 = 电击，持续 = 柔和抚摸' },
  { value: 'boost', label: '强度增减模式', desc: '按住 +N，松开恢复' },
]

const COMMON_PARAMS = [
  { path: '/avatar/parameters/pcs/contact/enterPass', desc: 'PCS 入口（最常用）' },
  { path: '/avatar/parameters/pcs/contact/proximityA', desc: 'PCS 接近A' },
  { path: '/avatar/parameters/pcs/contact/proximityB', desc: 'PCS 接近B' },
  { path: '/avatar/parameters/pcs/sps/pussy', desc: 'PCS 指定部位' },
  { path: '/avatar/parameters/pcs/sps/ass', desc: 'PCS 指定部位' },
  { path: '/avatar/parameters/pcs/sps/boobs', desc: 'PCS 指定部位' },
  { path: '/avatar/parameters/pcs/sps/mouth', desc: 'PCS 指定部位' },
  { path: '/avatar/parameters/pcs/smash-intensity', desc: 'PCS smash 强度' },
  { path: '/avatar/parameters/lms-penis-proximityA*', desc: 'LMS 1.2' },
  { path: '/avatar/parameters/lms/contact/proximity', desc: 'LMS 1.3' },
]

function toggleParam(list: string[], path: string) {
  const idx = list.indexOf(path)
  if (idx >= 0) list.splice(idx, 1)
  else list.push(path)
}

function addCustom(list: string[], inputRef: { value: string }) {
  const v = inputRef.value.trim()
  if (v && v.startsWith('/') && !list.includes(v)) { list.push(v); inputRef.value = '' }
}

async function save() {
  saving.value = true; errMsg.value = ''
  try {
    const data = await apiPost('/api/v1/setup', {
      channel_a: { mode: modeA.value, strength_limit: strengthA.value, avatar_params: paramsA.value },
      channel_b: { mode: modeB.value, strength_limit: strengthB.value, avatar_params: paramsB.value },
      osc: { listen_port: oscPort.value, listen_host: oscHost.value },
    })
    if (data.success) { done.value = true; setTimeout(() => router.push('/dashboard'), 2500) }
    else errMsg.value = data.message || '保存失败'
  } catch (e: any) { errMsg.value = e.message }
  finally { saving.value = false }
}
</script>

<template>
  <div class="wizard-page" v-if="!done">
    <div class="wizard-card">
      <div class="wizard-header">
        <span class="wizard-logo">⚡</span>
        <h1 class="gradient-text">Shocking VRChat</h1>
        <p class="wizard-sub">首次配置向导</p>
      </div>

      <!-- Progress -->
      <div class="progress">
        <div class="progress-dot" v-for="i in totalSteps" :key="i" :class="{ active: step === i-1, done: step > i-1 }"></div>
      </div>

      <!-- Step 0: Mode -->
      <div v-if="step === 0" class="step">
        <h2>选择工作模式</h2>
        <div class="mode-section">
          <label>通道 A</label>
          <div class="mode-grid">
            <div v-for="m in MODES" :key="m.value" class="mode-option" :class="{selected: modeA === m.value}" @click="modeA = m.value">
              <div class="mode-name">{{ m.label }}</div>
              <div class="mode-desc">{{ m.desc }}</div>
            </div>
          </div>
        </div>
        <div class="mode-section">
          <label>通道 B</label>
          <div class="mode-grid">
            <div v-for="m in MODES" :key="m.value" class="mode-option" :class="{selected: modeB === m.value}" @click="modeB = m.value">
              <div class="mode-name">{{ m.label }}</div>
              <div class="mode-desc">{{ m.desc }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Step 1: Params -->
      <div v-if="step === 1" class="step">
        <h2>选择 OSC 参数</h2>
        <div class="param-tabs">
          <span class="param-tab-label">通道 A</span>
        </div>
        <div class="param-list">
          <div v-for="p in COMMON_PARAMS" :key="p.path" class="param-item" :class="{checked: paramsA.includes(p.path)}" @click="toggleParam(paramsA, p.path)">
            <span class="check">{{ paramsA.includes(p.path) ? '✓' : '' }}</span>
            <span class="param-path">{{ p.path }}</span>
            <span class="param-desc">{{ p.desc }}</span>
          </div>
        </div>
        <div class="custom-add">
          <input v-model="customA" placeholder="/avatar/parameters/..." @keyup.enter="addCustom(paramsA, { value: customA }); customA = ''">
          <button class="btn btn-ghost" @click="addCustom(paramsA, { value: customA }); customA = ''">添加</button>
        </div>

        <div class="param-tabs" style="margin-top:var(--sp-5)">
          <span class="param-tab-label">通道 B</span>
        </div>
        <div class="param-list">
          <div v-for="p in COMMON_PARAMS" :key="p.path" class="param-item" :class="{checked: paramsB.includes(p.path)}" @click="toggleParam(paramsB, p.path)">
            <span class="check">{{ paramsB.includes(p.path) ? '✓' : '' }}</span>
            <span class="param-path">{{ p.path }}</span>
            <span class="param-desc">{{ p.desc }}</span>
          </div>
        </div>
        <div class="custom-add">
          <input v-model="customB" placeholder="/avatar/parameters/..." @keyup.enter="addCustom(paramsB, { value: customB }); customB = ''">
          <button class="btn btn-ghost" @click="addCustom(paramsB, { value: customB }); customB = ''">添加</button>
        </div>
      </div>

      <!-- Step 2: Strength -->
      <div v-if="step === 2" class="step">
        <h2>强度限制</h2>
        <div class="field">
          <label>通道 A 上限: <strong>{{ strengthA }}</strong></label>
          <input type="range" v-model.number="strengthA" min="0" max="200">
          <p class="hint">取该值与 APP 内设置的较小值</p>
        </div>
        <div class="field">
          <label>通道 B 上限: <strong>{{ strengthB }}</strong></label>
          <input type="range" v-model.number="strengthB" min="0" max="200">
        </div>
      </div>

      <!-- Step 3: OSC -->
      <div v-if="step === 3" class="step">
        <h2>OSC 端口</h2>
        <div class="field">
          <label>监听端口</label>
          <input type="number" v-model.number="oscPort" min="1024" max="65535">
          <p class="hint">VRChat 默认 9001。有面捕冲突时修改，并配合 osc-repeater。</p>
        </div>
        <div class="field">
          <label>监听地址</label>
          <input type="text" v-model="oscHost">
          <p class="hint">同一台电脑保持 127.0.0.1，VRChat 在其他设备改为 0.0.0.0</p>
        </div>
      </div>

      <!-- Nav -->
      <div class="wizard-nav">
        <button class="btn btn-ghost" v-if="step > 0" @click="step--">← 上一步</button>
        <div class="spacer"></div>
        <button class="btn btn-primary" v-if="step < totalSteps - 1" @click="step++">下一步 →</button>
        <button class="btn btn-primary" v-if="step === totalSteps - 1" :disabled="saving" @click="save">
          {{ saving ? '保存中...' : '✓ 保存并启动' }}
        </button>
      </div>
      <div v-if="errMsg" class="err">{{ errMsg }}</div>
    </div>
  </div>

  <!-- Done -->
  <div class="wizard-page" v-else>
    <div class="wizard-card done-card">
      <div class="done-icon">✓</div>
      <h2 class="gradient-text">配置完成！</h2>
      <p>正在跳转到 Dashboard...</p>
    </div>
  </div>
</template>

<style scoped>
.wizard-page { display: flex; align-items: center; justify-content: center; min-height: 80vh; }
.wizard-card {
  width: 100%; max-width: 580px;
  background: var(--bg-card);
  backdrop-filter: var(--blur);
  border: 1px solid var(--border);
  border-radius: var(--radius-xl);
  padding: var(--sp-8);
}
.wizard-header { text-align: center; margin-bottom: var(--sp-5); }
.wizard-logo { font-size: 2em; filter: drop-shadow(0 0 10px rgba(139,92,246,0.5)); }
.wizard-header h1 { font-size: var(--text-2xl); margin-top: var(--sp-2); }
.wizard-sub { color: var(--text-muted); font-size: var(--text-sm); margin-top: var(--sp-1); }

.progress { display: flex; justify-content: center; gap: var(--sp-2); margin-bottom: var(--sp-6); }
.progress-dot { width: 10px; height: 10px; border-radius: 50%; background: var(--border); transition: all var(--transition); }
.progress-dot.active { background: var(--accent); box-shadow: 0 0 10px rgba(139,92,246,0.5); transform: scale(1.2); }
.progress-dot.done { background: var(--success); }

.step h2 { font-size: var(--text-xl); margin-bottom: var(--sp-4); }

/* Mode selection */
.mode-section { margin-bottom: var(--sp-4); }
.mode-section > label { display: block; font-size: var(--text-sm); color: var(--text-secondary); margin-bottom: var(--sp-2); font-weight: 600; }
.mode-grid { display: flex; flex-direction: column; gap: var(--sp-2); }
.mode-option {
  padding: var(--sp-3) var(--sp-4);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--transition);
}
.mode-option:hover { border-color: var(--border-hover); }
.mode-option.selected { border-color: var(--accent); background: rgba(139,92,246,0.08); box-shadow: var(--glow-sm); }
.mode-name { font-size: var(--text-sm); font-weight: 600; }
.mode-desc { font-size: var(--text-xs); color: var(--text-muted); margin-top: 2px; }

/* Params */
.param-tab-label { font-size: var(--text-sm); font-weight: 600; color: var(--text-secondary); }
.param-list { max-height: 200px; overflow-y: auto; border: 1px solid var(--border); border-radius: var(--radius-md); margin-top: var(--sp-2); }
.param-item {
  display: flex; align-items: center; gap: var(--sp-2);
  padding: var(--sp-2) var(--sp-3);
  cursor: pointer;
  font-size: var(--text-xs);
  transition: background var(--transition);
}
.param-item:hover { background: rgba(139,92,246,0.04); }
.param-item.checked { background: rgba(139,92,246,0.08); }
.check { width: 16px; color: var(--accent); font-weight: 700; }
.param-path { font-family: var(--font-mono); color: var(--text-secondary); flex: 1; }
.param-desc { color: var(--text-muted); }
.custom-add { display: flex; gap: var(--sp-2); margin-top: var(--sp-2); }
.custom-add input { flex: 1; font-family: var(--font-mono); font-size: var(--text-xs); }

/* Fields */
.field { margin-bottom: var(--sp-5); }
.field label { display: block; font-size: var(--text-sm); color: var(--text-secondary); margin-bottom: var(--sp-2); }
.field input { width: 100%; }
.hint { font-size: var(--text-xs); color: var(--text-muted); margin-top: var(--sp-2); }

/* Nav */
.wizard-nav { display: flex; align-items: center; margin-top: var(--sp-6); }
.spacer { flex: 1; }
.err { color: var(--danger); font-size: var(--text-sm); margin-top: var(--sp-3); text-align: center; }

/* Done */
.done-card { text-align: center; padding: var(--sp-12) var(--sp-8); }
.done-icon { font-size: 3em; color: var(--success); margin-bottom: var(--sp-3); }
.done-card h2 { font-size: var(--text-2xl); margin-bottom: var(--sp-2); }
.done-card p { color: var(--text-muted); }
</style>
