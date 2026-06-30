<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { api, apiPost, apiDelete } from '@/api'

const recActive = ref(false)
const recCount = ref(0)
const recElapsed = ref(0)
const playActive = ref(false)
const playProgress = ref(0)
const playTotal = ref(0)
const playFilename = ref('')
const speed = ref(1.0)
const loop = ref(false)
const recordings = ref<any[]>([])
const msg = ref('')

let timer: number | null = null

async function startRec() {
  const data = await apiPost('/api/v1/recorder/start')
  if (!data.success) msg.value = data.message
}

async function stopRec() {
  const data = await apiPost('/api/v1/recorder/stop')
  if (data.success) { msg.value = `已保存 ${data.filename}`; loadFiles() }
}

async function startPlay(filename: string) {
  await apiPost('/api/v1/playback/start', { filename, speed: speed.value, loop: loop.value })
}

async function stopPlay() {
  await apiPost('/api/v1/playback/stop')
}

async function deleteFile(name: string) {
  if (!confirm(`删除 ${name}？`)) return
  await apiDelete(`/api/v1/recordings/${encodeURIComponent(name)}`)
  loadFiles()
}

async function loadFiles() {
  const data = await api('/api/v1/recordings')
  recordings.value = data.recordings || []
}

async function poll() {
  try {
    const r = await api('/api/v1/recorder/status')
    recActive.value = r.recording
    recCount.value = r.message_count
    recElapsed.value = r.elapsed_ms

    const p = await api('/api/v1/playback/status')
    playActive.value = p.active
    playProgress.value = p.progress
    playTotal.value = p.total
    playFilename.value = p.filename || ''
  } catch {}
}

onMounted(() => { loadFiles(); poll(); timer = window.setInterval(poll, 1000) })
onUnmounted(() => { if (timer) clearInterval(timer) })
</script>

<template>
  <div>
    <h1>🎙 OSC 录制 / 回放</h1>

    <div class="grid">
      <div>
        <!-- Recording -->
        <section class="card">
          <h2>录制</h2>
          <div class="status-badge" :class="recActive ? 'recording' : ''">
            <span class="dot" :class="recActive ? 'dot-rec' : ''"></span>
            {{ recActive ? `录制中 · ${recCount} 条 · ${(recElapsed / 1000).toFixed(1)}s` : '待机' }}
          </div>
          <div class="actions">
            <button class="btn btn-red" :disabled="recActive" @click="startRec">⏺ 开始</button>
            <button class="btn btn-gray" :disabled="!recActive" @click="stopRec">⏹ 停止</button>
          </div>
        </section>

        <!-- Playback -->
        <section class="card">
          <h2>回放控制</h2>
          <div class="status-badge" :class="playActive ? 'playing' : ''">
            <span class="dot" :class="playActive ? 'dot-play' : ''"></span>
            {{ playActive ? `回放中 · ${playFilename}` : '停止' }}
          </div>
          <label>速度: {{ speed.toFixed(2) }}x</label>
          <input type="range" v-model.number="speed" min="0.25" max="3" step="0.25">
          <label><input type="checkbox" v-model="loop"> 循环回放</label>
          <div class="actions">
            <button class="btn btn-gray" :disabled="!playActive" @click="stopPlay">⏹ 停止</button>
          </div>
          <div v-if="playActive" class="progress-bar">
            <div class="fill" :style="{width: (playTotal > 0 ? playProgress / playTotal * 100 : 0) + '%'}"></div>
          </div>
        </section>
      </div>

      <!-- File list -->
      <section class="card">
        <h2>录制文件</h2>
        <div class="file-list">
          <div class="file-item" v-for="f in recordings" :key="f.name">
            <span class="file-name" :title="f.name">{{ f.name }}</span>
            <span class="file-meta">{{ f.message_count }}条 · {{ (f.duration_ms / 1000).toFixed(1) }}s</span>
            <button class="fbtn play" @click="startPlay(f.name)">▶</button>
            <button class="fbtn del" @click="deleteFile(f.name)">✕</button>
          </div>
          <div v-if="!recordings.length" class="empty">无录制文件</div>
        </div>
      </section>
    </div>
    <div v-if="msg" class="msg-toast">{{ msg }}</div>
  </div>
</template>

<style scoped>
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 16px; }
.status-badge { display: inline-flex; align-items: center; gap: 8px; padding: 8px 12px; border-radius: 12px; background: #1a2540; font-size: 0.85em; margin-bottom: 12px; }
.status-badge.recording { background: #3a1a1a; color: #ff8b8b; }
.status-badge.playing { background: #1a3a2a; color: var(--green); }
.dot { width: 8px; height: 8px; border-radius: 50%; background: #444; }
.dot-rec { background: #ff6b6b; animation: pulse 1s infinite; }
.dot-play { background: var(--green); animation: pulse 1.5s infinite; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.5} }
.actions { display: flex; gap: 8px; margin: 8px 0; }
label { display: block; font-size: 0.82em; color: var(--muted); margin: 8px 0 4px; }
input[type="range"] { width: 100%; accent-color: var(--blue); }
.progress-bar { height: 5px; background: #0a1020; border-radius: 4px; margin-top: 8px; overflow: hidden; }
.fill { height: 100%; background: var(--green); transition: width 0.3s; }
.file-list { max-height: 400px; overflow-y: auto; }
.file-item { display: flex; align-items: center; gap: 8px; padding: 8px; border-bottom: 1px solid #111a2e; font-size: 0.85em; }
.file-name { flex: 1; font-family: monospace; color: #bfccec; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.file-meta { color: #555; font-size: 0.8em; }
.fbtn { border: none; border-radius: 6px; padding: 4px 10px; cursor: pointer; color: #fff; font-size: 0.8em; }
.fbtn.play { background: #2fa75b; }
.fbtn.del { background: #8b3a3a; }
.empty { padding: 16px; text-align: center; color: #444; }
.msg-toast { position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%); padding: 10px 20px; background: var(--green); color: #000; border-radius: 8px; font-size: 0.85em; }
.card + .card { margin-top: 16px; }
@media (max-width: 768px) { .grid { grid-template-columns: 1fr; } }
</style>
