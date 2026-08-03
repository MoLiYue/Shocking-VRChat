<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api, apiPost } from '@/api'
import { useI18n } from '@/i18n'

const { t } = useI18n()

interface Param {
  path: string
  mode: string
  enabled: boolean
}

const MODES = [
  { value: 'distance', label: '距离' },
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
const PARAM_PREFIX = '/avatar/parameters/'
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
  let path = newPath.value.trim()
  if (!path) return
  // Auto-prepend prefix if user didn't include it
  if (!path.startsWith('/')) {
    path = PARAM_PREFIX + path
  } else if (!path.startsWith(PARAM_PREFIX)) {
    // Has a leading / but not the standard prefix - use as-is
  }
  if (params.value.some(p => p.path === path)) { showMsg(t('params.paramExists'), true); return }
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

async function waitForRestart() {
  // Wait for old server to die
  for (let i = 0; i < 20; i++) {
    await new Promise(r => setTimeout(r, 300))
    try { await fetch('/api/v1/status') } catch { break }
  }
  // Wait for new server to come up
  for (let i = 0; i < 30; i++) {
    await new Promise(r => setTimeout(r, 500))
    try {
      const resp = await fetch('/api/v1/status')
      if (resp.ok) return
    } catch {}
  }
}

async function save() {
  const data = await apiPost(`/api/v1/params/${activeChannel.value}`, {
    params: params.value,
    default_mode: defaultMode.value,
    strength_limit: strengthLimit.value,
  })
  if (data.success) {
    showMsg(t('params.savedRestarting'), false)
    dirty.value = false
    // Wait for restart then reload
    await waitForRestart()
    loadChannel()
    showMsg(t('params.applied'), false)
  } else {
    showMsg(data.message || '保存失败', true)
  }
}

function showMsg(text: string, err: boolean) {
  msg.value = text; msgErr.value = err
  setTimeout(() => msg.value = '', 5000)
}

function modeLabel(mode: string) {
  const key = 'params.mode' + mode.charAt(0).toUpperCase() + mode.slice(1)
  const translated = t(key)
  return translated !== key ? translated : mode
}

onMounted(loadChannel)
</script>

<template>
  <div>
    <h1>{{ t('params.title') }}</h1>
    <p class="subtitle">{{ t('params.desc') }}</p>

    <div class="tabs">
      <button :class="{active: activeChannel === 'a'}" @click="switchChannel('a')">{{ t('common.channelA') }}</button>
      <button :class="{active: activeChannel === 'b'}" @click="switchChannel('b')">{{ t('common.channelB') }}</button>
      <span v-if="dirty" class="dirty-badge">● {{ t('common.unsaved') }}</span>
    </div>

    <!-- Channel settings -->
    <div class="card settings-row">
      <div class="setting">
        <label>{{ t('params.defaultMode') }}</label>
        <select v-model="defaultMode" @change="dirty = true">
          <option v-for="m in MODES" :key="m.value" :value="m.value">{{ modeLabel(m.value) }}</option>
        </select>
      </div>
      <div class="setting">
        <label>{{ t('params.strengthLimit') }}</label>
        <input type="number" v-model.number="strengthLimit" min="0" max="200" @change="dirty = true">
      </div>
    </div>

    <!-- Param list -->
    <div class="card">
      <h2>{{ t('params.paramList') }} ({{ params.filter(p => p.enabled).length }}/{{ params.length }} {{ t('params.colEnabled') }})</h2>
      <table>
        <thead>
          <tr><th style="width:40px">{{ t('params.colEnabled') }}</th><th>{{ t('params.colPath') }}</th><th>{{ t('params.colMode') }}</th><th style="width:100px">{{ t('params.colActions') }}</th></tr>
        </thead>
        <tbody>
          <tr v-for="(p, i) in params" :key="i" :class="{'editing': editIndex === i, 'disabled-row': !p.enabled}">
            <template v-if="editIndex === i">
              <td><input type="checkbox" v-model="p.enabled" @change="dirty = true"></td>
              <td><input v-model="editPath" class="edit-input" placeholder="/avatar/parameters/..."></td>
              <td><select v-model="editMode" class="edit-select"><option v-for="m in MODES" :key="m.value" :value="m.value">{{ modeLabel(m.value) }}</option></select></td>
              <td class="actions"><button class="act-btn save" @click="confirmEdit">✓</button><button class="act-btn cancel" @click="cancelEdit">✕</button></td>
            </template>
            <template v-else>
              <td><input type="checkbox" v-model="p.enabled" @change="dirty = true"></td>
              <td class="path" :class="{'path-disabled': !p.enabled}"><span class="path-prefix">{{ p.path.startsWith('/avatar/parameters/') ? '/avatar/parameters/' : '' }}</span>{{ p.path.startsWith('/avatar/parameters/') ? p.path.slice(19) : p.path }}</td>
              <td><span class="mode-badge" :class="[('mode-' + p.mode), {'badge-disabled': !p.enabled}]">{{ modeLabel(p.mode) }}</span></td>
              <td class="actions"><button class="act-btn edit" @click="startEdit(i)">✎</button><button class="act-btn del" @click="removeParam(i)">🗑</button></td>
            </template>
          </tr>
          <tr v-if="!params.length"><td colspan="4" class="empty">{{ t('params.noParams') }}</td></tr>
        </tbody>
      </table>
    </div>

    <!-- Add new param -->
    <div class="card add-row">
      <h2>{{ t('params.addTitle') }}</h2>
      <div class="add-form">
        <span class="prefix-label">/avatar/parameters/</span>
        <input v-model="newPath" placeholder="pcs/contact/enterPass" class="add-input" @keyup.enter="addParam">
        <select v-model="newMode" class="add-select">
          <option v-for="m in MODES" :key="m.value" :value="m.value">{{ modeLabel(m.value) }}</option>
        </select>
        <button class="btn btn-green" @click="addParam">+ 添加</button>
      </div>
      <p class="hint">{{ t('params.addHint') }}</p>
    </div>

    <!-- Save -->
    <div class="save-bar">
      <button class="btn btn-green" :disabled="!dirty" @click="save">{{ t('params.saveConfig') }}</button>
      <button class="btn btn-gray" @click="loadChannel">{{ t('params.undoChanges') }}</button>
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
.path-prefix { color: var(--text-muted); opacity: 0.5; }
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
.prefix-label { font-family: var(--font-mono); font-size: var(--text-xs); color: var(--text-muted); white-space: nowrap; background: var(--bg-tertiary); padding: var(--sp-2) var(--sp-2); border-radius: var(--radius-sm) 0 0 var(--radius-sm); border: 1px solid var(--border); border-right: none; }
.add-input { flex: 1; padding: var(--sp-2) var(--sp-3); border: 1px solid var(--border); border-radius: 0 var(--radius-md) var(--radius-md) 0; background: var(--bg-elevated); color: var(--text); font-family: var(--font-mono); font-size: var(--text-sm); }
.add-select { width: 120px; }
.hint { font-size: var(--text-xs); color: var(--text-muted); margin-top: var(--sp-2); }
.save-bar { display: flex; align-items: center; gap: var(--sp-3); margin-top: var(--sp-4); padding: var(--sp-3) var(--sp-4); background: var(--surface); border-radius: var(--radius-md); border: 1px solid var(--border-subtle); }
.msg { font-size: var(--text-sm); color: var(--success); }
.msg.err { color: var(--danger); }
.empty { color: var(--text-muted); text-align: center; padding: var(--sp-5); }
</style>
