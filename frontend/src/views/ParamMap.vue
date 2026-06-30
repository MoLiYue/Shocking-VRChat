<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api, apiPost } from '@/api'

interface Param {
  path: string
  mode: string
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
  params.value.push({ path, mode: newMode.value })
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
  params.value[editIndex.value] = { path, mode: editMode.value }
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
      <h2>参数列表 ({{ params.length }})</h2>
      <table>
        <thead>
          <tr><th>OSC 参数路径</th><th>模式</th><th style="width:100px">操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="(p, i) in params" :key="i" :class="{'editing': editIndex === i}">
            <template v-if="editIndex === i">
              <td><input v-model="editPath" class="edit-input" placeholder="/avatar/parameters/..."></td>
              <td><select v-model="editMode" class="edit-select"><option v-for="m in MODES" :key="m.value" :value="m.value">{{ m.label }}</option></select></td>
              <td class="actions"><button class="act-btn save" @click="confirmEdit">✓</button><button class="act-btn cancel" @click="cancelEdit">✕</button></td>
            </template>
            <template v-else>
              <td class="path">{{ p.path }}</td>
              <td><span class="mode-badge" :class="'mode-' + p.mode">{{ modeLabel(p.mode) }}</span></td>
              <td class="actions"><button class="act-btn edit" @click="startEdit(i)">✎</button><button class="act-btn del" @click="removeParam(i)">🗑</button></td>
            </template>
          </tr>
          <tr v-if="!params.length"><td colspan="3" class="empty">暂无参数，请在下方添加</td></tr>
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
.subtitle { color: var(--muted); font-size: 0.85em; margin: 4px 0 16px; }
.tabs { display: flex; gap: 8px; margin-bottom: 16px; align-items: center; }
.tabs button { padding: 8px 20px; border: 1px solid var(--line); border-radius: 8px; background: var(--panel); color: var(--muted); cursor: pointer; }
.tabs button.active { border-color: var(--blue); color: var(--blue); }
.dirty-badge { color: var(--amber); font-size: 0.82em; margin-left: 12px; }
.settings-row { display: flex; gap: 20px; margin-bottom: 16px; }
.setting { flex: 1; }
.setting label { display: block; font-size: 0.8em; color: var(--muted); margin-bottom: 4px; }
.setting select, .setting input { width: 100%; padding: 8px; border: 1px solid var(--line); border-radius: 8px; background: var(--panel-2); color: var(--text); }
table { width: 100%; border-collapse: collapse; }
th { text-align: left; font-size: 0.75em; color: #555; padding: 8px; border-bottom: 1px solid #1a2540; }
td { padding: 8px; font-size: 0.85em; border-bottom: 1px solid #111a2e; vertical-align: middle; }
.path { font-family: monospace; color: #bfccec; word-break: break-all; }
.mode-badge { display: inline-block; padding: 3px 10px; border-radius: 12px; font-size: 0.78em; font-weight: 600; }
.mode-distance { background: #1a3a5a; color: var(--blue); }
.mode-shock { background: #3a1a1a; color: #ff8b8b; }
.mode-touch { background: #1a3a2a; color: var(--green); }
.mode-combo { background: #3a2a1a; color: var(--amber); }
.mode-boost { background: #2a1a3a; color: var(--purple); }
.actions { display: flex; gap: 4px; }
.act-btn { border: none; border-radius: 6px; padding: 4px 8px; cursor: pointer; font-size: 0.85em; background: var(--panel-2); color: var(--muted); }
.act-btn:hover { color: var(--text); }
.act-btn.del:hover { color: #ff8b8b; }
.act-btn.save { color: var(--green); }
.act-btn.cancel { color: #ff8b8b; }
.editing { background: rgba(99,179,255,0.05); }
.edit-input, .edit-select { padding: 6px 8px; border: 1px solid var(--blue); border-radius: 6px; background: var(--panel-2); color: var(--text); font-family: monospace; font-size: 0.85em; width: 100%; }
.add-row { margin-top: 16px; }
.add-form { display: flex; gap: 8px; align-items: center; }
.add-input { flex: 1; padding: 9px 12px; border: 1px solid var(--line); border-radius: 8px; background: var(--panel-2); color: var(--text); font-family: monospace; font-size: 0.85em; }
.add-select { width: 120px; padding: 9px; border: 1px solid var(--line); border-radius: 8px; background: var(--panel-2); color: var(--text); }
.hint { font-size: 0.78em; color: #555; margin-top: 6px; }
.save-bar { display: flex; align-items: center; gap: 10px; margin-top: 16px; padding: 12px 16px; background: var(--panel); border-radius: 12px; border: 1px solid var(--line); }
.msg { font-size: 0.85em; color: var(--green); }
.msg.err { color: #ff8b8b; }
.empty { color: #444; text-align: center; padding: 16px; }
.card + .card { margin-top: 16px; }
</style>
