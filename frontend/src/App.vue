<script setup lang="ts">
import { useRouter } from 'vue-router'
const router = useRouter()

const navItems = [
  { path: '/dashboard', label: 'Dashboard', icon: '⚡' },
  { path: '/curve', label: '强度曲线', icon: '📈' },
  { path: '/combo', label: 'Combo', icon: '🔀' },
  { path: '/params', label: '参数映射', icon: '🗂' },
  { path: '/recorder', label: '录制回放', icon: '🎙' },
]
</script>

<template>
  <div class="app-shell">
    <nav class="sidebar">
      <div class="logo">⚡ Shocking VRChat</div>
      <router-link
        v-for="item in navItems"
        :key="item.path"
        :to="item.path"
        class="nav-item"
        active-class="active"
      >
        <span class="nav-icon">{{ item.icon }}</span>
        <span class="nav-label">{{ item.label }}</span>
      </router-link>
    </nav>
    <main class="main-content">
      <router-view />
    </main>
  </div>
</template>

<style scoped>
.app-shell {
  display: flex;
  min-height: 100vh;
}
.sidebar {
  width: 200px;
  background: var(--panel);
  border-right: 1px solid var(--line);
  padding: 16px 0;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}
.logo {
  padding: 12px 16px 24px;
  font-size: 1em;
  font-weight: 700;
  color: var(--text);
}
.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  color: var(--muted);
  text-decoration: none;
  font-size: 0.9em;
  border-left: 3px solid transparent;
  transition: background 0.15s, color 0.15s;
}
.nav-item:hover {
  background: rgba(255,255,255,0.03);
  color: var(--text);
  text-decoration: none;
}
.nav-item.active {
  color: var(--blue);
  border-left-color: var(--blue);
  background: rgba(99,179,255,0.05);
}
.nav-icon { font-size: 1.1em; }
.main-content {
  flex: 1;
  padding: 24px;
  overflow-y: auto;
}

@media (max-width: 768px) {
  .app-shell { flex-direction: column; }
  .sidebar {
    width: 100%;
    flex-direction: row;
    overflow-x: auto;
    padding: 0;
    border-right: none;
    border-bottom: 1px solid var(--line);
  }
  .logo { display: none; }
  .nav-item { border-left: none; border-bottom: 3px solid transparent; padding: 12px 14px; }
  .nav-item.active { border-bottom-color: var(--blue); border-left-color: transparent; }
  .nav-label { display: none; }
}
</style>
