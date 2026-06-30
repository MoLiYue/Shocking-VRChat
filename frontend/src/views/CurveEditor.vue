<script setup lang="ts">
import { ref, onMounted, watch, nextTick } from 'vue'
import { api, apiPost } from '@/api'

const activeChannel = ref<'a' | 'b'>('a')
const points = ref<{x: number; y: number}[]>([])
const msg = ref('')
const canvasRef = ref<HTMLCanvasElement | null>(null)
let dragging: number | null = null

const PRESETS: Record<string, {x:number;y:number}[]> = {
  relu: [{x:0,y:0},{x:0.1,y:0},{x:1,y:1}],
  linear: [{x:0,y:0},{x:1,y:1}],
  quadratic: [{x:0,y:0},{x:0.25,y:0.0625},{x:0.5,y:0.25},{x:0.75,y:0.5625},{x:1,y:1}],
  scurve: [{x:0,y:0},{x:0.25,y:0.06},{x:0.5,y:0.5},{x:0.75,y:0.94},{x:1,y:1}],
  step: [{x:0,y:0},{x:0.29,y:0},{x:0.3,y:0.5},{x:0.69,y:0.5},{x:0.7,y:1},{x:1,y:1}],
}

function interpolate(px: number, pts: {x:number;y:number}[]): number {
  if (!pts.length) return 0
  if (px <= pts[0].x) return pts[0].y
  if (px >= pts[pts.length-1].x) return pts[pts.length-1].y
  for (let i = 0; i < pts.length - 1; i++) {
    if (px >= pts[i].x && px <= pts[i+1].x) {
      const t = (px - pts[i].x) / (pts[i+1].x - pts[i].x)
      return pts[i].y + t * (pts[i+1].y - pts[i].y)
    }
  }
  return 0
}

function sortPoints() { points.value.sort((a, b) => a.x - b.x) }

function draw() {
  const canvas = canvasRef.value
  if (!canvas) return
  const ratio = window.devicePixelRatio || 1
  const W = canvas.clientWidth
  const H = canvas.clientHeight
  canvas.width = W * ratio
  canvas.height = H * ratio
  const ctx = canvas.getContext('2d')!
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0)
  ctx.clearRect(0, 0, W, H)

  // Grid
  ctx.strokeStyle = 'rgba(139,92,246,0.06)'
  ctx.lineWidth = 1
  for (let i = 0; i <= 10; i++) {
    const x = (i / 10) * W, y = (i / 10) * H
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke()
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke()
  }

  // Labels
  ctx.fillStyle = 'rgba(139,92,246,0.3)'
  ctx.font = '11px Inter, sans-serif'
  ctx.fillText('0', 4, H - 4)
  ctx.fillText('1', W - 12, H - 4)
  ctx.fillText('1', 4, 14)
  ctx.fillText('参数值 →', W / 2 - 24, H - 4)

  const pts = points.value
  // Curve fill
  ctx.beginPath()
  ctx.moveTo(0, H)
  for (let px = 0; px <= W; px++) {
    const x = px / W
    const y = interpolate(x, pts)
    ctx.lineTo(px, (1 - y) * H)
  }
  ctx.lineTo(W, H)
  ctx.closePath()
  ctx.fillStyle = 'rgba(139,92,246,0.08)'
  ctx.fill()

  // Curve line
  ctx.beginPath()
  for (let px = 0; px <= W; px++) {
    const x = px / W
    const y = interpolate(x, pts)
    if (px === 0) ctx.moveTo(px, (1 - y) * H)
    else ctx.lineTo(px, (1 - y) * H)
  }
  ctx.strokeStyle = '#8b5cf6'
  ctx.lineWidth = 2.5
  ctx.shadowColor = 'rgba(139,92,246,0.4)'
  ctx.shadowBlur = 8
  ctx.stroke()
  ctx.shadowBlur = 0

  // Points
  pts.forEach((p, i) => {
    const cx = p.x * W, cy = (1 - p.y) * H
    ctx.beginPath()
    ctx.arc(cx, cy, 7, 0, Math.PI * 2)
    ctx.fillStyle = dragging === i ? '#fff' : '#a78bfa'
    ctx.fill()
    ctx.strokeStyle = '#13111c'
    ctx.lineWidth = 2
    ctx.stroke()
    // Glow
    ctx.beginPath()
    ctx.arc(cx, cy, 7, 0, Math.PI * 2)
    ctx.strokeStyle = 'rgba(139,92,246,0.4)'
    ctx.lineWidth = 1
    ctx.stroke()
  })
}

function toCoord(e: MouseEvent): [number, number] {
  const canvas = canvasRef.value!
  const r = canvas.getBoundingClientRect()
  const x = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width))
  const y = Math.max(0, Math.min(1, 1 - (e.clientY - r.top) / r.height))
  return [x, y]
}

function findPoint(mx: number, my: number): number {
  const canvas = canvasRef.value!
  const W = canvas.clientWidth, H = canvas.clientHeight
  for (let i = 0; i < points.value.length; i++) {
    const px = points.value[i].x * W, py = (1 - points.value[i].y) * H
    const r = canvas.getBoundingClientRect()
    const cx = mx - r.left, cy = my - r.top
    if (Math.hypot(cx - px, cy - py) < 14) return i
  }
  return -1
}

function onMouseDown(e: MouseEvent) {
  if (e.button === 2) {
    const idx = findPoint(e.clientX, e.clientY)
    if (idx >= 0) { points.value.splice(idx, 1); draw() }
    return
  }
  const idx = findPoint(e.clientX, e.clientY)
  if (idx >= 0) { dragging = idx }
  else {
    const [x, y] = toCoord(e)
    points.value.push({x, y})
    sortPoints()
    dragging = points.value.findIndex(p => Math.abs(p.x - x) < 0.001 && Math.abs(p.y - y) < 0.001)
    draw()
  }
}

function onMouseMove(e: MouseEvent) {
  if (dragging === null) return
  const [x, y] = toCoord(e)
  points.value[dragging] = {x, y}
  sortPoints()
  dragging = points.value.findIndex(p => Math.abs(p.x - x) < 0.001 && Math.abs(p.y - y) < 0.001)
  draw()
}

function onMouseUp() { dragging = null; draw() }

async function loadCurve() {
  const data = await api(`/api/v1/curve/${activeChannel.value}`)
  points.value = data.points || PRESETS.relu
  sortPoints()
  await nextTick()
  draw()
  msg.value = ''
}

async function saveCurve() {
  const data = await apiPost(`/api/v1/curve/${activeChannel.value}`, { points: points.value })
  msg.value = data.success ? '✓ 已保存并生效' : '保存失败'
  setTimeout(() => msg.value = '', 3000)
}

function applyPreset(name: string) {
  points.value = JSON.parse(JSON.stringify(PRESETS[name]))
  sortPoints()
  draw()
}

function switchChannel(ch: 'a' | 'b') { activeChannel.value = ch; loadCurve() }

watch(points, draw, { deep: true })
onMounted(() => {
  loadCurve()
  window.addEventListener('resize', draw)
})
</script>

<template>
  <div>
    <h1 class="gradient-text" style="font-size:var(--text-2xl);margin-bottom:var(--sp-2)">强度曲线编辑器</h1>
    <p class="page-desc">适用于强度曲线模式 · X轴=参数值 · Y轴=输出强度 · 点击添加 · 拖拽移动 · 右键删除</p>

    <div class="tabs">
      <button :class="{active: activeChannel === 'a'}" @click="switchChannel('a')">Channel A</button>
      <button :class="{active: activeChannel === 'b'}" @click="switchChannel('b')">Channel B</button>
    </div>

    <div class="editor-grid">
      <!-- Canvas -->
      <div class="card canvas-card">
        <canvas
          ref="canvasRef"
          class="curve-canvas"
          @mousedown="onMouseDown"
          @mousemove="onMouseMove"
          @mouseup="onMouseUp"
          @mouseleave="onMouseUp"
          @contextmenu.prevent
        ></canvas>
      </div>

      <!-- Controls -->
      <div class="side-panel">
        <div class="card">
          <h2>预设</h2>
          <div class="preset-grid">
            <button v-for="(_, name) in PRESETS" :key="name" class="preset-btn" @click="applyPreset(name)">{{ name }}</button>
          </div>
        </div>
        <div class="card">
          <h2>控制点 ({{ points.length }})</h2>
          <div class="point-list">
            <div v-for="(p, i) in points" :key="i" class="pt-row">
              <span class="pt-idx">{{ i }}</span>
              <span class="pt-coord">({{ p.x.toFixed(3) }}, {{ p.y.toFixed(3) }})</span>
              <button class="pt-del" @click="points.splice(i, 1); draw()">✕</button>
            </div>
          </div>
        </div>
        <div class="actions">
          <button class="btn btn-primary" @click="saveCurve">保存</button>
          <button class="btn btn-ghost" @click="loadCurve">重载</button>
          <button class="btn btn-danger" @click="applyPreset('relu')">重置</button>
        </div>
        <div v-if="msg" class="msg-text">{{ msg }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page-desc { color: var(--text-muted); font-size: var(--text-sm); margin-bottom: var(--sp-5); }
.tabs { display: flex; gap: var(--sp-2); margin-bottom: var(--sp-4); }
.tabs button { padding: var(--sp-2) var(--sp-5); border: 1px solid var(--border); border-radius: var(--radius-full); background: transparent; color: var(--text-muted); cursor: pointer; font-size: var(--text-sm); font-weight: 500; transition: all var(--transition); }
.tabs button.active { border-color: var(--accent); color: var(--accent); background: rgba(139,92,246,0.08); box-shadow: var(--glow-sm); }
.tabs button:hover { border-color: var(--border-hover); color: var(--text); }

.editor-grid { display: grid; grid-template-columns: 1fr 260px; gap: var(--sp-4); }
.canvas-card { padding: var(--sp-4); }
.curve-canvas {
  width: 100%; height: 380px; cursor: crosshair;
  border-radius: var(--radius-lg);
  background: rgba(10, 8, 16, 0.6);
  border: 1px solid var(--border);
}

.side-panel { display: flex; flex-direction: column; gap: var(--sp-4); }
.preset-grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--sp-2); }
.preset-btn {
  padding: var(--sp-2) var(--sp-3);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: var(--text-xs);
  font-weight: 500;
  transition: all var(--transition);
}
.preset-btn:hover { border-color: var(--accent); color: var(--text); background: rgba(139,92,246,0.06); }

.point-list { max-height: 180px; overflow-y: auto; }
.pt-row { display: flex; align-items: center; gap: var(--sp-2); padding: var(--sp-1) 0; font-family: var(--font); font-variant-numeric: tabular-nums; font-size: var(--text-xs); }
.pt-idx { color: var(--text-muted); width: 16px; }
.pt-coord { color: var(--text-secondary); flex: 1; }
.pt-del { border: none; background: transparent; color: var(--text-muted); cursor: pointer; padding: 2px 6px; border-radius: 4px; transition: color var(--transition); }
.pt-del:hover { color: var(--danger); }

.actions { display: flex; gap: var(--sp-2); }
.msg-text { font-size: var(--text-sm); color: var(--success); margin-top: var(--sp-2); }

@media (max-width: 768px) { .editor-grid { grid-template-columns: 1fr; } }
</style>
