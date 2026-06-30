<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api, apiPost } from '@/api'

const activeChannel = ref<'a' | 'b'>('a')
const points = ref<{x: number; y: number}[]>([])
const msg = ref('')

const PRESETS = {
  relu: [{x:0,y:0},{x:0.1,y:0},{x:1,y:1}],
  linear: [{x:0,y:0},{x:1,y:1}],
  quadratic: [{x:0,y:0},{x:0.25,y:0.0625},{x:0.5,y:0.25},{x:0.75,y:0.5625},{x:1,y:1}],
  scurve: [{x:0,y:0},{x:0.25,y:0.06},{x:0.5,y:0.5},{x:0.75,y:0.94},{x:1,y:1}],
  step: [{x:0,y:0},{x:0.29,y:0},{x:0.3,y:0.5},{x:0.69,y:0.5},{x:0.7,y:1},{x:1,y:1}],
}

async function loadCurve() {
  const data = await api(`/api/v1/curve/${activeChannel.value}`)
  points.value = data.points || PRESETS.relu
  msg.value = ''
}

async function saveCurve() {
  const data = await apiPost(`/api/v1/curve/${activeChannel.value}`, { points: points.value })
  if (data.success) msg.value = '已保存'
  else msg.value = '保存失败'
}

function applyPreset(name: keyof typeof PRESETS) {
  points.value = JSON.parse(JSON.stringify(PRESETS[name]))
}

function switchChannel(ch: 'a' | 'b') {
  activeChannel.value = ch
  loadCurve()
}

onMounted(loadCurve)
</script>

<template>
  <div>
    <h1>📈 强度曲线编辑器</h1>
    <p style="color:var(--muted);margin:8px 0 16px;font-size:0.85em">适用于强度曲线模式 (distance) · 点击 Canvas 添加控制点 · 拖拽移动 · 右键删除</p>

    <div class="tabs">
      <button :class="{active: activeChannel === 'a'}" @click="switchChannel('a')">Channel A</button>
      <button :class="{active: activeChannel === 'b'}" @click="switchChannel('b')">Channel B</button>
    </div>

    <div class="card" style="margin-bottom:16px">
      <h2>控制点 ({{ points.length }})</h2>
      <div class="point-list">
        <div v-for="(p, i) in points" :key="i" class="point-item">
          <span class="idx">{{ i }}</span>
          <span class="coord">({{ p.x.toFixed(3) }}, {{ p.y.toFixed(3) }})</span>
          <button class="btn-del" @click="points.splice(i, 1)">✕</button>
        </div>
      </div>
    </div>

    <div class="card" style="margin-bottom:16px">
      <h2>预设曲线</h2>
      <div class="preset-btns">
        <button v-for="(_, name) in PRESETS" :key="name" @click="applyPreset(name as any)">{{ name }}</button>
      </div>
    </div>

    <div class="actions">
      <button class="btn btn-green" @click="saveCurve()">保存</button>
      <button class="btn btn-gray" @click="loadCurve()">重新加载</button>
      <button class="btn btn-red" @click="applyPreset('relu')">重置为 ReLU</button>
    </div>
    <div v-if="msg" class="msg">{{ msg }}</div>
  </div>
</template>

<style scoped>
.tabs { display: flex; gap: 8px; margin-bottom: 16px; }
.tabs button { padding: 8px 20px; border: 1px solid var(--line); border-radius: 8px; background: var(--panel); color: var(--muted); cursor: pointer; }
.tabs button.active { border-color: var(--blue); color: var(--blue); }
.point-list { max-height: 200px; overflow-y: auto; }
.point-item { display: flex; align-items: center; gap: 8px; padding: 4px 0; font-size: 0.82em; font-family: monospace; }
.idx { color: #555; width: 20px; }
.coord { color: #bfccec; }
.btn-del { border: none; background: #3a2020; color: #ff8b8b; border-radius: 4px; padding: 2px 6px; cursor: pointer; }
.preset-btns { display: flex; flex-wrap: wrap; gap: 6px; }
.preset-btns button { padding: 6px 12px; border: 1px solid var(--line); border-radius: 6px; background: #0f1a2e; color: var(--muted); cursor: pointer; }
.preset-btns button:hover { border-color: var(--blue); color: var(--blue); }
.actions { display: flex; gap: 8px; }
.msg { margin-top: 8px; font-size: 0.85em; color: var(--green); }
</style>
