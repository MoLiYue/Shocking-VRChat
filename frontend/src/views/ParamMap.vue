<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api, apiPost } from '@/api'

interface Param {
  path: string
  mode: string
  enabled: boolean
}

const MODES = [
  { value: 'distance', label: '强度曲线' },
  { value: 'shock', label: '电击' },
  { value: 'touch', label: '触摸' },
  { value: 'combo', label: '组合' },
  { value: 'boost', label: '强度增减' },
]

const activeChannel = ref<'a' | 'b'>('a')
const params = ref<Param[]>([])
const defaultMode = ref('distance')
const strengthLimit = ref(100)
const newPath = ref('')
const newMode = ref('distance')
const editIndex = ref<number | null>(null)
const editPath = ref('')
const editMode = ref('')
const msg = ref('')
const msgErr = ref(false)
const dirty = ref(false)

async function loadChannel() {
  const data = await api(`/api/v1/params/${activeChannel.value}`)
  params.value = (data.params || []).map((p: any) => ({
    path: typeof p === 'string' ? p : p.path,
    mode: typeof p === 'string' ? data.default_mode : (p.mode || data.default_mode),
    enabled: typeof p === 'string' ? true : (p.enabled !== false),
  }))
  defaultMode.value = data.default_mode || 'distance'
  strengthLimit.value = data.strength_limit || 100
  dirty.value = false
  editIndex.value = null
  msg.value = ''
}

function switchChannel(ch: 'a' | 'b') {
  if (dirty.value && !confirm('有未保存的更改，是否切换？')) return
  activeChannel.value = ch
  loadChannel()
}

function addParam() {
  const path = newPath.value.trim()
  if (!path) return
  if (!path.startsWith('/')) { showMsg('路径必须以 / 开头', true); return }
  params.value.push({ path, mode: newMode.value, enabled: true })
  newPath.value = ''
  dirty.value = true
}

function removeParam(index: number) {
  params.value.splice(index, 1)
  dirty.value = true
  if (editIndex.value === index) editIndex.value = null
}

function startEdit(index: number) {
  editIndex.value = index
  editPath.value = params.value[index].path
  editMode.value = params.value[index].mode
}

function confirmEdit() {
  if (editIndex.value === null) return
  const path = editPath.value.trim()
  if (!path || !path.startsWith('/')) { showMsg('路径必须以 / 开头', true); return }
  params.value[editIndex.value] = { path, mode: editMode.value, enabled: params.value[editIndex.value].enabled }
  editIndex.value = null
  dirty.value = true
}

function cancelEdit() { editIndex.value = null }

async function save() {
  const data = await apiPost(`/api/v1/params/${activeChannel.value}`, {
    params: params.value,
    default_mode: defaultMode.value,
    strength_limit: strengthLimit.value,
  })
  if (data.success) {
    showMsg('已保存（参数变更需重启程序生效）', false)
    dirty.value = false
  } else {
    showMsg(data.message || '保存失败', true)
  }
}

function showMsg(text: string, err: boolean) {
  msg.value = text; msgErr.value = err
  setTimeout(() => msg.value = '', 5000)
}

function modeLabel(mode: string) { return MODES.find(m => m.value === mode)?.label || mode }

onMounted(loadChannel)
</script>

<template>
  <div>
    <h1>🗂 参数管理</h1>
    <p class="subtitle">管理 OSC 监听参数，配置每个参数的工作模式</p>

    <div class="tabs">
      <button :class="{active: activeChannel === 'a'}" @click="switchChannel('a')">Channel A</button>
      <button :class="{active: activeChannel === 'b'}" @click="switchChannel('b')">Channel B</button>
      <span v-if="dirty" class="dirty-badge">● 未保存</span>
    </div>

    <!-- Channel settings -->
    <div class="card settings-row">
      <div class="setting">
        <label>默认模式</label>
        <select v-model="defaultMode" @change="dirty = true">
          <option v-for="m in MODES" :key="m.value" :value="m.value">{{ m.label }}</option>
        </select>
      </div>
      <div class="setting">
        <label>强度上限</label>
        <input type="number" v-model.number="strengthLimit" min="0" max="200" @change="dirty = true">
      </div>
    </div>

    <!-- Param list -->
    <div class="card">
      <h2>参数列表 ({{ params.filter(p => p.enabled).length }}/{{ params.length }} 启用)</h2>
      <table>
        <thead>
          <tr><th style="width:40px">启用</th><th>OSC 参数路径</th><th>模式</th><th style="width:100px">操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="(p, i) in params" :key="i" :class="{'editing': editIndex === i, 'disabled-row': !p.enabled}">
            <template v-if="editIndex === i">
              <td><input type="checkbox" v-model="p.enabled" @change="dirty = true"></td>
              <td><input v-model="editPath" class="edit-input" placeholder="/avatar/parameters/..."></td>
              <td><select v-model="editMode" class="edit-select"><option v-for="m in MODES" :key="m.value" :value="m.value">{{ m.label }}</option></select></td>
              <td class="actions"><button class="act-btn save" @click="confirmEdit">✓</button><button class="act-btn cancel" @click="cancelEdit">✕</button></td>
            </template>
            <template v-else>
              <td><input type="checkbox" v-model="p.enabled" @change="dirty = true"></td>
              <td class="path" :class="{'path-disabled': !p.enabled}">{{ p.path }}</td>
              <td><span class="mode-badge" :class="[('mode-' + p.mode), {'badge-disabled': !p.enabled}]">{{ modeLabel(p.mode) }}</span></td>
              <td class="actions"><button class="act-btn edit" @click="startEdit(i)">✎</button><button class="act-btn del" @click="removeParam(i)">🗑</button></td>
            </template>
          </tr>
          <tr v-if="!params.length"><td colspan="4" class="empty">暂无参数，请在下方添加</td></tr>
        </tbody>
      </table>
    </div>

    <!-- Add new param -->
    <div class="card add-row">
      <h2>添加参数</h2>
      <div class="add-form">
        <input v-model="newPath" placeholder="/avatar/parameters/pcs/contact/enterPass" class="add-input" @keyup.enter="addParam">
        <select v-model="newMode" class="add-select">
          <option v-for="m in MODES" :key="m.value" :value="m.value">{{ m.label }}</option>
        </select>
        <button class="btn btn-green" @click="addParam">+ 添加</button>
      </div>
      <p class="hint">支持通配符 *，如 /avatar/parameters/Shock/*</p>
    </div>

    <!-- Save -->
    <div class="save-bar">
      <button class="btn btn-green" :disabled="!dirty" @click="save">💾 保存配置</button>
      <button class="btn btn-gray" @click="loadChannel">↺ 撤销更改</button>
      <span :class="['msg', msgErr ? 'err' : '']">{{ msg }}</span>
    </div>
  </div>
</template>

<style scoped>
.subtitle { color: var(--text-muted); font-size: var(--text-sm); margin: var(--sp-1) 0 var(--sp-5); }
.tabs { display: flex; gap: var(--sp-2); margin-bottom: var(--sp-4); align-items: center; }
.tabs button { padding: var(--sp-2) var(--sp-5); border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--surface); color: var(--text-secondary); cursor: pointer; font-size: var(--text-sm); transition: all var(--transition); }
.tabs button.active { border-color: var(--accent); color: var(--accent-hover); background: rgba(99,102,241,0.08); }
.dirty-badge { color: var(--warning); font-size: var(--text-xs); margin-left: var(--sp-3); }
.settings-row { display: flex; gap: var(--sp-5); margin-bottom: var(--sp-4); }
.setting { flex: 1; }
.setting label { display: block; font-size: var(--text-xs); color: var(--text-muted); margin-bottom: var(--sp-1); }
.setting select, .setting input { width: 100%; }
table { width: 100%; border-collapse: collapse; }
th { text-align: left; font-size: var(--text-xs); color: var(--text-muted); padding: var(--sp-2) var(--sp-3); border-bottom: 1px solid var(--border-subtle); }
td { padding: var(--sp-3); font-size: var(--text-sm); border-bottom: 1px solid var(--border-subtle); vertical-align: middle; }
.path { font-family: var(--font-mono); color: var(--text-secondary); word-break: break-all; }
.mode-badge { display: inline-block; padding: 2px 10px; border-radius: 99px; font-size: var(--text-xs); font-weight: 600; }
.mode-distance { background: var(--info-surface); color: var(--info); }
.mode-shock { background: var(--danger-surface); color: var(--danger); }
.mode-touch { background: var(--success-surface); color: var(--success); }
.mode-combo { background: var(--warning-surface); color: var(--warning); }
.mode-boost { background: rgba(167,139,250,0.1); color: var(--purple); }
.actions { display: flex; gap: var(--sp-1); }
.act-btn { border: none; border-radius: var(--radius-sm); padding: var(--sp-1) var(--sp-2); cursor: pointer; font-size: var(--text-sm); background: transparent; color: var(--text-muted); transition: color var(--transition); }
.act-btn:hover { color: var(--text); }
.act-btn.del:hover { color: var(--danger); }
.act-btn.save { color: var(--success); }
.act-btn.cancel { color: var(--danger); }
.editing { background: rgba(99,102,241,0.04); }
.disabled-row { opacity: 0.5; }
.path-disabled { text-decoration: line-through; }
.badge-disabled { opacity: 0.4; }
.edit-input, .edit-select { padding: var(--sp-2); border: 1px solid var(--accent); border-radius: var(--radius-sm); background: var(--bg-elevated); color: var(--text); font-family: var(--font-mono); font-size: var(--text-sm); width: 100%; }
.add-row { margin-top: var(--sp-4); }
.add-form { display: flex; gap: var(--sp-2); align-items: center; }
.add-input { flex: 1; padding: var(--sp-2) var(--sp-3); border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--bg-elevated); color: var(--text); font-family: var(--font-mono); font-size: var(--text-sm); }
.add-select { width: 120px; }
.hint { font-size: var(--text-xs); color: var(--text-muted); margin-top: var(--sp-2); }
.save-bar { display: flex; align-items: center; gap: var(--sp-3); margin-top: var(--sp-4); padding: var(--sp-3) var(--sp-4); background: var(--surface); border-radius: var(--radius-md); border: 1px solid var(--border-subtle); }
.msg { font-size: var(--text-sm); color: var(--success); }
.msg.err { color: var(--danger); }
.empty { color: var(--text-muted); text-align: center; padding: var(--sp-5); }
</style>
