<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api, apiPost } from '@/api'

const limitA = ref(5)
const limitB = ref(5)
const overlimitA = ref(20)
const overlimitB = ref(20)
const msg = ref('')
const msgType = ref<'ok' | 'err'>('ok')

let saveTimer: ReturnType<typeof setTimeout> | null = null

async function load() {
  const data = await api('/api/v1/strength_limit')
  limitA.value = data.channel_a ?? 5
  limitB.value = data.channel_b ?? 5
  overlimitA.value = data.overlimit_a ?? 20
  overlimitB.value = data.overlimit_b ?? 20
}

async function save() {
  const data = await apiPost('/api/v1/strength_limit', {
    channel_a: limitA.value,
    channel_b: limitB.value,
    overlimit_a: overlimitA.value,
    overlimit_b: overlimitB.value,
  })
  if (data.success) {
    msg.value = '✓ 已保存'
    msgType.value = 'ok'
  } else {
    msg.value = '✗ 保存失败'
    msgType.value = 'err'
  }
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => msg.value = '', 2000)
}

function schedSave() {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(save, 300)
}

function clamp(val: number) { return Math.max(0, Math.min(200, val)) }

function onInput() {
  limitA.value = clamp(limitA.value)
  limitB.value = clamp(limitB.value)
  overlimitA.value = clamp(overlimitA.value)
  overlimitB.value = clamp(overlimitB.value)
  schedSave()
}

function adj(target: 'limitA' | 'limitB' | 'overlimitA' | 'overlimitB', delta: number) {
  if (target === 'limitA') limitA.value = clamp(limitA.value + delta)
  else if (target === 'limitB') limitB.value = clamp(limitB.value + delta)
  else if (target === 'overlimitA') overlimitA.value = clamp(overlimitA.value + delta)
  else if (target === 'overlimitB') overlimitB.value = clamp(overlimitB.value + delta)
  schedSave()
}

onMounted(load)
</script>

<template>
  <div>
    <h1 class="gradient-text" style="font-size:var(--text-2xl);margin-bottom:var(--sp-2)">强度设置</h1>
    <p class="page-desc">设置郊狼输出的最大强度。调节后自动保存并实时生效。</p>

    <div class="recommend-banner">
      <span class="recommend-icon">💡</span>
      <span>推荐将强度设置为 <strong>200</strong>（设备允许的最大值），然后通过郊狼 APP 内的被控设置调节实际体验上限。初始默认值为 <strong>5</strong>，请根据自身承受能力逐步提高。</span>
    </div>

    <div class="limit-grid">
      <section class="card">
        <h2>通道 A</h2>
        <div class="field">
          <label>强度 (0–200)</label>
          <div class="slider-row">
            <input type="range" v-model.number="limitA" min="0" max="200" step="1" @input="onInput">
          </div>
          <div class="value-row">
            <button class="adj-btn" @click="adj('limitA', -1)">−</button>
            <input type="number" v-model.number="limitA" min="0" max="200" class="num-input" @input="onInput">
            <button class="adj-btn" @click="adj('limitA', 1)">+</button>
          </div>
          <div class="bar-wrap">
            <div class="bar-fill" :style="{ width: (limitA / 200 * 100) + '%' }"></div>
          </div>
        </div>
        <div class="field" style="margin-top:var(--sp-4)">
          <label>超限额度 (0–200)</label>
          <div class="slider-row">
            <input type="range" v-model.number="overlimitA" min="0" max="200" step="1" @input="onInput">
          </div>
          <div class="value-row">
            <button class="adj-btn" @click="adj('overlimitA', -1)">−</button>
            <input type="number" v-model.number="overlimitA" min="0" max="200" class="num-input" @input="onInput">
            <button class="adj-btn" @click="adj('overlimitA', 1)">+</button>
          </div>
          <p class="hint">超限规则触发时，最大值可提升到: <strong>{{ overlimitA }}</strong></p>
        </div>
      </section>

      <section class="card">
        <h2>通道 B</h2>
        <div class="field">
          <label>强度 (0–200)</label>
          <div class="slider-row">
            <input type="range" v-model.number="limitB" min="0" max="200" step="1" @input="onInput">
          </div>
          <div class="value-row">
            <button class="adj-btn" @click="adj('limitB', -1)">−</button>
            <input type="number" v-model.number="limitB" min="0" max="200" class="num-input" @input="onInput">
            <button class="adj-btn" @click="adj('limitB', 1)">+</button>
          </div>
          <div class="bar-wrap">
            <div class="bar-fill" :style="{ width: (limitB / 200 * 100) + '%' }"></div>
          </div>
        </div>
        <div class="field" style="margin-top:var(--sp-4)">
          <label>超限额度 (0–200)</label>
          <div class="slider-row">
            <input type="range" v-model.number="overlimitB" min="0" max="200" step="1" @input="onInput">
          </div>
          <div class="value-row">
            <button class="adj-btn" @click="adj('overlimitB', -1)">−</button>
            <input type="number" v-model.number="overlimitB" min="0" max="200" class="num-input" @input="onInput">
            <button class="adj-btn" @click="adj('overlimitB', 1)">+</button>
          </div>
          <p class="hint">超限规则触发时，最大值可提升到: <strong>{{ overlimitB }}</strong></p>
        </div>
      </section>
    </div>

    <div class="status-bar" v-if="msg">
      <span class="msg" :class="{ ok: msgType === 'ok', err: msgType === 'err' }">{{ msg }}</span>
    </div>

    <div class="info-card card">
      <h3>工作原理</h3>
      <ul>
        <li>实际输出强度 = <code>min(本页设置的上限, 郊狼APP被控设置的上限)</code></li>
        <li>程序根据 OSC 参数在 0 ~ 上限 之间线性输出波形强度</li>
        <li>如果郊狼 APP 内设置的上限低于此值，以 APP 设置为准</li>
        <li>修改后立即生效，无需重启程序或重新连接设备</li>
      </ul>
      <h3 style="margin-top:var(--sp-4)">超限规则</h3>
      <ul>
        <li>在 <router-link to="/overlimit-rules">超限规则</router-link> 页面中配置条件规则</li>
        <li>当 OSC 参数满足规则条件时，对应通道的强度临时提升到规则设定的值</li>
        <li>本页的"超限额度"作为默认回退值（当旧的单参数触发超限时使用）</li>
        <li>推荐使用超限规则页面进行更灵活的多层级配置</li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.page-desc { color: var(--text-muted); font-size: var(--text-sm); margin-bottom: var(--sp-4); }
.recommend-banner { display: flex; align-items: flex-start; gap: var(--sp-3); padding: var(--sp-4); margin-bottom: var(--sp-5); background: rgba(139,92,246,0.08); border: 1px solid rgba(139,92,246,0.25); border-radius: var(--radius-lg); font-size: var(--text-sm); color: var(--text-secondary); line-height: 1.6; }
.recommend-icon { font-size: 1.3em; flex-shrink: 0; }
.recommend-banner strong { color: var(--accent); }
.limit-grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--sp-4); margin-bottom: var(--sp-4); }
.field { margin-bottom: 0; }
.field label { display: block; font-size: var(--text-sm); color: var(--text-secondary); margin-bottom: var(--sp-2); font-weight: 500; }
.slider-row { display: flex; align-items: center; gap: var(--sp-2); }
.slider-row input[type="range"] { flex: 1; accent-color: var(--accent); }
.value-row { display: flex; align-items: center; justify-content: center; gap: var(--sp-2); margin-top: var(--sp-2); }
.adj-btn {
  width: 32px; height: 32px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg-elevated);
  color: var(--text-secondary);
  font-size: var(--text-lg);
  font-weight: 600;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: all var(--transition);
  user-select: none;
}
.adj-btn:hover { border-color: var(--accent); color: var(--accent); background: rgba(139,92,246,0.08); }
.adj-btn:active { transform: scale(0.92); }
.num-input { width: 64px; text-align: center; font-variant-numeric: tabular-nums; font-size: var(--text-base); font-weight: 600; }
.bar-wrap { margin-top: var(--sp-2); height: 6px; background: var(--bg-tertiary); border-radius: 3px; overflow: hidden; }
.bar-fill { height: 100%; background: linear-gradient(90deg, var(--accent), var(--accent-hover)); border-radius: 3px; transition: width 0.15s ease; }
.hint { font-size: var(--text-xs); color: var(--text-muted); margin-top: var(--sp-2); }
.hint strong { color: var(--accent); }
.status-bar { margin-bottom: var(--sp-4); padding: var(--sp-2) var(--sp-4); background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius-md); text-align: center; }
.msg { font-size: var(--text-sm); color: var(--text-muted); transition: color 0.2s; }
.msg.ok { color: var(--success); }
.msg.err { color: var(--danger); }
.info-card { font-size: var(--text-sm); color: var(--text-secondary); }
.info-card h3 { font-size: var(--text-base); margin-bottom: var(--sp-2); color: var(--text); }
.info-card ul { padding-left: var(--sp-4); }
.info-card li { margin-bottom: var(--sp-2); line-height: 1.6; }
.info-card code { background: var(--bg-tertiary); padding: 2px 6px; border-radius: var(--radius-sm); font-size: var(--text-xs); }
@media (max-width: 768px) { .limit-grid { grid-template-columns: 1fr; } }
</style>
