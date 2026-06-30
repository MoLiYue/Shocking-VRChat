<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api, apiPost } from '@/api'

const oscPort = ref(9001)
const oscHost = ref('127.0.0.1')
const wsPort = ref(28846)
const webPort = ref(8800)
const webHost = ref('127.0.0.1')
const logLevel = ref('INFO')
const msg = ref('')
const msgErr = ref(false)

async function load() {
  const data = await api('/api/v1/config')
  const adv = data.advanced || {}
  oscPort.value = adv.osc?.listen_port || 9001
  oscHost.value = adv.osc?.listen_host || '127.0.0.1'
  wsPort.value = adv.ws?.listen_port || 28846
  webPort.value = adv.web_server?.listen_port || 8800
  webHost.value = adv.web_server?.listen_host || '127.0.0.1'
  logLevel.value = adv.log_level || 'INFO'
}

async function save() {
  const data = await apiPost('/api/v1/settings', {
    osc: { listen_port: oscPort.value, listen_host: oscHost.value },
    ws: { listen_port: wsPort.value },
    web_server: { listen_port: webPort.value, listen_host: webHost.value },
    log_level: logLevel.value,
  })
  if (data.success) { msg.value = data.message; msgErr.value = false }
  else { msg.value = data.message || '保存失败'; msgErr.value = true }
  setTimeout(() => msg.value = '', 5000)
}

onMounted(load)
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
    </div>

    <div class="save-bar">
      <button class="btn btn-primary" @click="save">💾 保存设置</button>
      <button class="btn btn-ghost" @click="load">↺ 重新加载</button>
      <span class="msg" :class="{ err: msgErr }">{{ msg }}</span>
    </div>
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
.msg { font-size: var(--text-sm); color: var(--success); }
.msg.err { color: var(--danger); }
@media (max-width: 768px) { .settings-grid { grid-template-columns: 1fr; } }
</style>
