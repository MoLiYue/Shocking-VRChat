<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api, apiPost } from '@/api'

interface Rule {
  name: string
  channel: 'a' | 'b' | 'both'
  limit_value: number
  condition: {
    param: string
    operator: string
    value: number
  }
  enabled: boolean
}

const rules = ref<Rule[]>([])
const effective = ref<{ A: number; B: number }>({ A: 0, B: 0 })
const msg = ref('')
const msgType = ref<'ok' | 'err'>('ok')

const operators = ['==', '!=', '>', '<', '>=', '<=']

async function load() {
  const data = await api('/api/v1/overlimit_rules')
  rules.value = data.rules || []
  effective.value = data.effective || { A: 0, B: 0 }
}

function addRule() {
  rules.value.push({
    name: `规则 ${rules.value.length + 1}`,
    channel: 'both',
    limit_value: 30,
    condition: {
      param: '/avatar/parameters/',
      operator: '==',
      value: 1,
    },
    enabled: true,
  })
}

async function save() {
  const data = await apiPost('/api/v1/overlimit_rules', { rules: rules.value })
  if (data.success) {
    msg.value = '✓ 已保存并生效'
    msgType.value = 'ok'
    rules.value = data.rules
  } else {
    msg.value = '保存失败'
    msgType.value = 'err'
  }
  setTimeout(() => msg.value = '', 3000)
}

async function removeRule(index: number) {
  rules.value.splice(index, 1)
  await save()
}

function moveUp(index: number) {
  if (index <= 0) return
  const tmp = rules.value[index]
  rules.value[index] = rules.value[index - 1]
  rules.value[index - 1] = tmp
}

function moveDown(index: number) {
  if (index >= rules.value.length - 1) return
  const tmp = rules.value[index]
  rules.value[index] = rules.value[index + 1]
  rules.value[index + 1] = tmp
}

onMounted(load)
</script>

<template>
  <div>
    <h1 class="gradient-text" style="font-size:var(--text-2xl);margin-bottom:var(--sp-2)">超限规则</h1>
    <p class="page-desc">定义多层级超限规则。当 OSC 参数满足条件时，对应通道的强度上限临时提升到规则设定的值。多条规则同时满足时取最大值。</p>

    <div class="status-bar">
      <span class="status-label">当前生效超限:</span>
      <span class="status-chip" :class="{ active: effective.A > 0 }">A: {{ effective.A > 0 ? effective.A : '—' }}</span>
      <span class="status-chip" :class="{ active: effective.B > 0 }">B: {{ effective.B > 0 ? effective.B : '—' }}</span>
      <button class="btn btn-ghost btn-sm" @click="load" title="刷新状态">↻</button>
    </div>

    <div class="rules-list">
      <div v-for="(rule, i) in rules" :key="i" class="rule-card card" :class="{ disabled: !rule.enabled }">
        <div class="rule-header">
          <input type="text" v-model="rule.name" class="rule-name" placeholder="规则名称">
          <label class="toggle">
            <input type="checkbox" v-model="rule.enabled">
            <span class="toggle-label">{{ rule.enabled ? '启用' : '禁用' }}</span>
          </label>
          <div class="rule-actions">
            <button class="btn-icon" @click="moveUp(i)" :disabled="i === 0" title="上移">↑</button>
            <button class="btn-icon" @click="moveDown(i)" :disabled="i === rules.length - 1" title="下移">↓</button>
            <button class="btn-icon danger" @click="removeRule(i)" title="删除">✕</button>
          </div>
        </div>

        <div class="rule-body">
          <div class="condition-row">
            <span class="cond-label">当</span>
            <input type="text" v-model="rule.condition.param" class="cond-param" placeholder="/avatar/parameters/...">
            <select v-model="rule.condition.operator" class="cond-op">
              <option v-for="op in operators" :key="op" :value="op">{{ op }}</option>
            </select>
            <input type="number" v-model.number="rule.condition.value" class="cond-value" step="0.01">
          </div>
          <div class="effect-row">
            <span class="cond-label">则</span>
            <select v-model="rule.channel" class="effect-channel">
              <option value="a">通道 A</option>
              <option value="b">通道 B</option>
              <option value="both">双通道</option>
            </select>
            <span class="effect-text">上限提升到</span>
            <input type="number" v-model.number="rule.limit_value" min="0" max="200" class="effect-value">
          </div>
        </div>
      </div>

      <div v-if="rules.length === 0" class="empty-state">
        <p>暂无超限规则。点击下方按钮添加第一条规则。</p>
      </div>
    </div>

    <div class="save-bar">
      <button class="btn btn-primary" @click="addRule">＋ 添加规则</button>
      <button class="btn btn-primary" @click="save">💾 保存全部</button>
      <button class="btn btn-ghost" @click="load">↺ 重新加载</button>
      <span class="msg" :class="{ ok: msgType === 'ok', err: msgType === 'err' }">{{ msg }}</span>
    </div>

    <div class="info-card card">
      <h3>使用说明</h3>
      <ul>
        <li><strong>条件</strong>：指定一个 OSC 参数路径和比较条件（如 <code>/avatar/parameters/pcs/smash-intense == 1</code>）</li>
        <li><strong>效果</strong>：条件满足时，对应通道的强度上限<em>临时变为</em>规则中的值（绝对值，非增量）</li>
        <li><strong>多规则</strong>：同时满足多条规则时，取所有匹配规则中的最大 limit_value</li>
        <li><strong>优先级</strong>：规则顺序不影响结果（始终取最大值），但影响可读性</li>
        <li><strong>恢复</strong>：当条件不再满足时，自动恢复到基础强度上限</li>
      </ul>
      <h3 style="margin-top:var(--sp-3)">示例</h3>
      <ul>
        <li><code>/avatar/parameters/pcs/smash-intense == 1</code> → 激烈碰撞时允许上限到 60</li>
        <li><code>/avatar/parameters/pcs/contact/enterPass >= 0.9</code> → 深入时允许上限到 80</li>
        <li><code>/avatar/parameters/Shock/OverrideMax == 1</code> → 手动触发满功率</li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.page-desc { color: var(--text-muted); font-size: var(--text-sm); margin-bottom: var(--sp-4); }
.status-bar { display: flex; align-items: center; gap: var(--sp-3); margin-bottom: var(--sp-4); padding: var(--sp-3) var(--sp-4); background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius-lg); }
.status-label { font-size: var(--text-sm); color: var(--text-muted); }
.status-chip { font-size: var(--text-sm); padding: var(--sp-1) var(--sp-3); border-radius: var(--radius-full); background: var(--bg-tertiary); color: var(--text-muted); font-variant-numeric: tabular-nums; }
.status-chip.active { background: rgba(139,92,246,0.15); color: var(--accent); border: 1px solid rgba(139,92,246,0.3); }
.btn-sm { padding: var(--sp-1) var(--sp-2); font-size: var(--text-sm); }
.rules-list { display: flex; flex-direction: column; gap: var(--sp-3); margin-bottom: var(--sp-4); }
.rule-card { padding: var(--sp-4); transition: opacity 0.2s; }
.rule-card.disabled { opacity: 0.5; }
.rule-header { display: flex; align-items: center; gap: var(--sp-3); margin-bottom: var(--sp-3); }
.rule-name { flex: 1; font-weight: 600; font-size: var(--text-sm); }
.toggle { display: flex; align-items: center; gap: var(--sp-2); font-size: var(--text-xs); color: var(--text-muted); cursor: pointer; white-space: nowrap; }
.toggle input[type="checkbox"] { accent-color: var(--accent); }
.toggle-label { user-select: none; }
.rule-actions { display: flex; gap: var(--sp-1); }
.btn-icon { background: transparent; border: 1px solid var(--border); border-radius: var(--radius-sm); width: 28px; height: 28px; display: flex; align-items: center; justify-content: center; cursor: pointer; color: var(--text-muted); font-size: var(--text-sm); transition: all 0.15s; }
.btn-icon:hover { border-color: var(--border-hover); color: var(--text); }
.btn-icon:disabled { opacity: 0.3; cursor: not-allowed; }
.btn-icon.danger:hover { border-color: var(--danger); color: var(--danger); }
.rule-body { display: flex; flex-direction: column; gap: var(--sp-2); }
.condition-row, .effect-row { display: flex; align-items: center; gap: var(--sp-2); flex-wrap: wrap; }
.cond-label { font-size: var(--text-sm); color: var(--accent); font-weight: 600; min-width: 24px; }
.cond-param { flex: 1; min-width: 200px; font-size: var(--text-sm); }
.cond-op { width: 64px; text-align: center; font-size: var(--text-sm); }
.cond-value { width: 80px; text-align: center; font-size: var(--text-sm); }
.effect-channel { width: 100px; font-size: var(--text-sm); }
.effect-text { font-size: var(--text-sm); color: var(--text-secondary); }
.effect-value { width: 80px; text-align: center; font-size: var(--text-sm); font-weight: 600; }
.empty-state { text-align: center; padding: var(--sp-6); color: var(--text-muted); font-size: var(--text-sm); }
.save-bar { display: flex; align-items: center; gap: var(--sp-3); margin-bottom: var(--sp-5); padding: var(--sp-4); background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius-lg); }
.msg { font-size: var(--text-sm); color: var(--text-muted); }
.msg.ok { color: var(--success); }
.msg.err { color: var(--danger); }
.info-card { font-size: var(--text-sm); color: var(--text-secondary); }
.info-card h3 { font-size: var(--text-base); margin-bottom: var(--sp-2); color: var(--text); }
.info-card ul { padding-left: var(--sp-4); }
.info-card li { margin-bottom: var(--sp-2); line-height: 1.6; }
.info-card code { background: var(--bg-tertiary); padding: 2px 6px; border-radius: var(--radius-sm); font-size: var(--text-xs); }
.info-card em { color: var(--accent); font-style: normal; font-weight: 500; }
</style>
