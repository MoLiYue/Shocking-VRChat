<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api, apiPost } from '@/api'

const oscPort = ref(9001)
const oscHost = ref('127.0.0.1')
const wsPort = ref(28846)
const webPort = ref(8800)
const webHost = ref('127.0.0.1')
const githubMirror = ref('')
const logLevel = ref('INFO')
const msg = ref('')
const msgErr = ref(false)
const importMsg = ref('')
const importErr = ref(false)

async function load() {
  const data = await api('/api/v1/config')
  const adv = data.advanced || {}
  oscPort.value = adv.osc?.listen_port || 9001
  oscHost.value = adv.osc?.listen_host || '127.0.0.1'
  wsPort.value = adv.ws?.listen_port || 28846
  webPort.value = adv.web_server?.listen_port || 8800
  webHost.value = adv.web_server?.listen_host || '127.0.0.1'
  logLevel.value = adv.log_level || 'INFO'
  githubMirror.value = adv.general?.github_mirror || ''
}

async function save() {
  const data = await apiPost('/api/v1/settings', {
    osc: { listen_port: oscPort.value, listen_host: oscHost.value },
    ws: { listen_port: wsPort.value },
    web_server: { listen_port: webPort.value, listen_host: webHost.value },
    log_level: logLevel.value,
    github_mirror: githubMirror.value,
  })
  if (data.success) {
    if (data.restart_needed?.length) {
      msg.value = '已保存，程序正在重启... 请稍候刷新页面。'
      msgErr.value = false
      // If web port changed, redirect to new port after delay
      const newPort = webPort.value
      const currentPort = window.location.port
      if (String(newPort) !== currentPort) {
        setTimeout(() => {
          window.location.href = `http://${window.location.hostname}:${newPort}/settings`
        }, 3000)
      } else {
        setTimeout(() => window.location.reload(), 3000)
      }
    } else {
      msg.value = data.message; msgErr.value = false
    }
  } else { msg.value = data.message || '保存失败'; msgErr.value = true }
  setTimeout(() => msg.value = '', 8000)
}

function exportConfig() {
  window.open('/api/v1/config/export', '_blank')
}

const importFileRef = ref<HTMLInputElement | null>(null)

function triggerImport() {
  importFileRef.value?.click()
}

async function handleImport(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  const form = new FormData()
  form.append('file', file)
  try {
    const res = await fetch('/api/v1/config/import', { method: 'POST', body: form })
    const data = await res.json()
    if (data.success) {
      importMsg.value = '✓ ' + data.message
      importErr.value = false
      setTimeout(() => window.location.reload(), 2000)
    } else {
      importMsg.value = '✗ ' + (data.detail || '导入失败')
      importErr.value = true
    }
  } catch (err) {
    importMsg.value = '✗ 导入失败: ' + err
    importErr.value = true
  }
  if (importFileRef.value) importFileRef.value.value = ''
  setTimeout(() => importMsg.value = '', 8000)
}

onMounted(load)

// --- Update check ---
const updateInfo = ref<any>(null)
const updateChecking = ref(false)
const updateApplying = ref(false)
const updateMsg = ref('')
const updateErr = ref(false)

async function checkUpdate() {
  updateChecking.value = true
  updateMsg.value = ''
  try {
    const data = await api('/api/v1/update/check')
    updateInfo.value = data
    if (data.error) {
      updateMsg.value = '检查失败: ' + data.error
      updateErr.value = true
    }
  } catch (e) {
    updateMsg.value = '检查失败'
    updateErr.value = true
  }
  updateChecking.value = false
}

async function applyUpdate() {
  if (!confirm('确定要更新？程序将下载新版本并自动重启。')) return
  updateApplying.value = true
  updateMsg.value = '正在下载更新...'
  updateErr.value = false
  try {
    const res = await fetch('/api/v1/update/apply', { method: 'POST' })
    const data = await res.json()
    if (data.success) {
      updateMsg.value = '✓ ' + data.message + ' 页面将在几秒后自动刷新...'
      updateErr.value = false
      // Wait and reload
      setTimeout(() => window.location.reload(), 8000)
    } else {
      updateMsg.value = '✗ ' + (data.detail || data.message || '更新失败')
      updateErr.value = true
      updateApplying.value = false
    }
  } catch (e) {
    updateMsg.value = '✗ 更新失败: ' + e
    updateErr.value = true
    updateApplying.value = false
  }
}

onMounted(() => { checkUpdate() })
</script>

<template>
  <div>
    <h1 class="gradient-text" style="font-size:var(--text-2xl);margin-bottom:var(--sp-2)">设置</h1>
    <p class="page-desc">服务端口和日志配置。网络端口变更需重启程序生效。</p>

    <div class="settings-grid">
      <section class="card">
        <h2>OSC 监听</h2>
        <div class="field">
          <label>端口</label>
          <input type="number" v-model.number="oscPort" min="1024" max="65535">
          <p class="hint">VRChat 默认发送到 9001。有面捕冲突时修改。</p>
        </div>
        <div class="field">
          <label>地址</label>
          <input type="text" v-model="oscHost">
          <p class="hint">127.0.0.1 = 仅本机。0.0.0.0 = 接受外部。</p>
        </div>
      </section>

      <section class="card">
        <h2>WebSocket（郊狼连接）</h2>
        <div class="field">
          <label>端口</label>
          <input type="number" v-model.number="wsPort" min="1024" max="65535">
          <p class="hint">郊狼 APP 扫码连接使用此端口。</p>
        </div>
      </section>

      <section class="card">
        <h2>Web 服务器</h2>
        <div class="field">
          <label>端口</label>
          <input type="number" v-model.number="webPort" min="1024" max="65535">
          <p class="hint">当前页面的 HTTP 服务端口。</p>
        </div>
        <div class="field">
          <label>地址</label>
          <input type="text" v-model="webHost">
          <p class="hint">0.0.0.0 可从其他设备打开网页。</p>
        </div>
      </section>

      <section class="card">
        <h2>日志</h2>
        <div class="field">
          <label>日志等级</label>
          <select v-model="logLevel">
            <option value="DEBUG">DEBUG</option>
            <option value="INFO">INFO</option>
            <option value="WARNING">WARNING</option>
            <option value="ERROR">ERROR</option>
          </select>
          <p class="hint">DEBUG 可用于诊断问题，日常使用 INFO 即可。</p>
        </div>
      </section>

      <section class="card">
        <h2>GitHub 加速</h2>
        <div class="field">
          <label>镜像代理</label>
          <input type="text" v-model="githubMirror" placeholder="留空 = 直连 GitHub">
          <p class="hint">中国大陆用户建议填写代理地址加速更新下载。</p>
          <div class="mirror-presets">
            <button class="preset-tag" @click="githubMirror = ''">直连</button>
            <button class="preset-tag" @click="githubMirror = 'https://mirror.ghproxy.com'">ghproxy</button>
            <button class="preset-tag" @click="githubMirror = 'https://ghfast.top'">ghfast</button>
            <button class="preset-tag" @click="githubMirror = 'https://gh-proxy.com'">gh-proxy</button>
          </div>
        </div>
      </section>
    </div>

    <div class="save-bar">
      <button class="btn btn-primary" @click="save">💾 保存设置</button>
      <button class="btn btn-ghost" @click="load">↺ 重新加载</button>
      <span class="msg" :class="{ err: msgErr }">{{ msg }}</span>
    </div>

    <section class="card" style="margin-top:var(--sp-4)">
      <h2>配置导入/导出</h2>
      <p class="hint" style="margin-bottom:var(--sp-3)">导出当前全部配置为 JSON 文件，或从之前导出的文件恢复配置。</p>
      <div class="ie-bar">
        <button class="btn" @click="exportConfig">📤 导出配置</button>
        <button class="btn" @click="triggerImport">📥 导入配置</button>
        <input ref="importFileRef" type="file" accept=".json" hidden @change="handleImport">
        <span class="msg" :class="{ err: importErr }">{{ importMsg }}</span>
      </div>
    </section>

    <section class="card" style="margin-top:var(--sp-4)">
      <h2>软件更新</h2>
      <div class="update-info">
        <div class="update-row">
          <span class="update-label">当前版本:</span>
          <span class="update-value">{{ updateInfo?.current || '...' }}</span>
        </div>
        <div class="update-row">
          <span class="update-label">最新版本:</span>
          <span class="update-value" :class="{ 'has-update': updateInfo?.update_available }">
            {{ updateInfo?.latest || (updateChecking ? '检查中...' : '未知') }}
            <span v-if="updateInfo?.update_available" class="update-badge">有更新</span>
          </span>
        </div>
        <div v-if="updateInfo?.release_name && updateInfo?.update_available" class="update-row">
          <span class="update-label">更新内容:</span>
          <span class="update-value update-notes">{{ updateInfo.release_name }}</span>
        </div>
      </div>
      <div class="ie-bar" style="margin-top:var(--sp-3)">
        <button class="btn" @click="checkUpdate" :disabled="updateChecking">🔄 检查更新</button>
        <button
          v-if="updateInfo?.update_available"
          class="btn btn-primary"
          @click="applyUpdate"
          :disabled="updateApplying"
        >⬇️ {{ updateApplying ? '更新中...' : '下载并更新' }}</button>
        <span class="msg" :class="{ err: updateErr }">{{ updateMsg }}</span>
      </div>
    </section>
  </div>
</template>

<style scoped>
.page-desc { color: var(--text-muted); font-size: var(--text-sm); margin-bottom: var(--sp-6); }
.settings-grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--sp-4); }
.field { margin-bottom: var(--sp-4); }
.field:last-child { margin-bottom: 0; }
.field label { display: block; font-size: var(--text-sm); color: var(--text-secondary); margin-bottom: var(--sp-2); font-weight: 500; }
.field input, .field select { width: 100%; }
.hint { font-size: var(--text-xs); color: var(--text-muted); margin-top: var(--sp-1); }
.save-bar { display: flex; align-items: center; gap: var(--sp-3); margin-top: var(--sp-5); padding: var(--sp-4); background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius-lg); }
.ie-bar { display: flex; align-items: center; gap: var(--sp-3); flex-wrap: wrap; }
.msg { font-size: var(--text-sm); color: var(--success); }
.msg.err { color: var(--danger); }
.update-info { display: flex; flex-direction: column; gap: var(--sp-2); }
.update-row { display: flex; align-items: center; gap: var(--sp-2); font-size: var(--text-sm); }
.update-label { color: var(--text-muted); min-width: 80px; }
.update-value { color: var(--text-secondary); }
.update-value.has-update { color: var(--accent); font-weight: 600; }
.update-badge { display: inline-block; margin-left: var(--sp-2); padding: 1px 8px; border-radius: 99px; background: rgba(139,92,246,0.15); color: var(--accent); font-size: var(--text-xs); font-weight: 600; }
.update-notes { font-size: var(--text-xs); color: var(--text-muted); max-width: 400px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mirror-presets { display: flex; gap: var(--sp-2); margin-top: var(--sp-2); flex-wrap: wrap; }
.preset-tag { padding: 2px 10px; border: 1px solid var(--border); border-radius: 99px; background: transparent; color: var(--text-muted); font-size: var(--text-xs); cursor: pointer; transition: all var(--transition); }
.preset-tag:hover { border-color: var(--accent); color: var(--accent); background: rgba(139,92,246,0.06); }
@media (max-width: 768px) { .settings-grid { grid-template-columns: 1fr; } }
</style>
