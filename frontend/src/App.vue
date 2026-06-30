<script setup lang="ts">
import { ref } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const sidebarOpen = ref(true)

const navItems = [
  { path: '/dashboard', label: 'Dashboard', icon: '⚡' },
  { path: '/params', label: '参数管理', icon: '🎛' },
  { path: '/curve', label: '强度曲线', icon: '📈' },
  { path: '/combo', label: 'Combo', icon: '🔀' },
  { path: '/recorder', label: '录制回放', icon: '🎙' },
  { path: '/settings', label: '设置', icon: '⚙' },
]
</script>

<template>
  <div class="shell">
    <!-- Sidebar -->
    <aside class="sidebar" :class="{ closed: !sidebarOpen }">
      <div class="sidebar-brand">
        <span class="brand-glow">⚡</span>
        <span class="brand-name gradient-text">Shocking</span>
      </div>
      <nav class="nav">
        <router-link
          v-for="item in navItems" :key="item.path"
          :to="item.path"
          class="nav-link"
          active-class="active"
        >
          <span class="nav-ico">{{ item.icon }}</span>
          <span class="nav-txt">{{ item.label }}</span>
        </router-link>
      </nav>
      <button class="toggle-btn" @click="sidebarOpen = !sidebarOpen">
        {{ sidebarOpen ? '‹' : '›' }}
      </button>
    </aside>

    <!-- Main -->
    <main class="main">
      <router-view v-slot="{ Component }">
        <transition name="page" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>
  </div>
</template>

<style scoped>
.shell {
  display: grid;
  grid-template-columns: 200px 1fr;
  min-height: 100vh;
  transition: grid-template-columns 250ms ease;
}
.shell:has(.sidebar.closed) {
  grid-template-columns: 56px 1fr;
}

/* Sidebar */
.sidebar {
  background: rgba(15, 12, 24, 0.95);
  backdrop-filter: blur(20px);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  padding: var(--sp-4) 0;
  position: sticky;
  top: 0;
  height: 100vh;
  overflow: hidden;
  transition: all 250ms ease;
}
.sidebar-brand {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-3) var(--sp-4) var(--sp-6);
}
.brand-glow {
  font-size: 1.4em;
  filter: drop-shadow(0 0 6px rgba(139,92,246,0.5));
}
.brand-name {
  font-size: var(--text-lg);
  font-weight: 800;
  letter-spacing: -0.03em;
}
.sidebar.closed .brand-name { opacity: 0; width: 0; }
.sidebar.closed .nav-txt { opacity: 0; width: 0; }

.nav { flex: 1; padding: 0 var(--sp-2); display: flex; flex-direction: column; gap: 2px; }
.nav-link {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-3) var(--sp-3);
  border-radius: var(--radius-md);
  color: var(--text-muted);
  text-decoration: none;
  font-size: var(--text-sm);
  font-weight: 500;
  transition: all var(--transition);
  position: relative;
  overflow: hidden;
}
.nav-link::before {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: var(--gradient-btn);
  opacity: 0;
  transition: opacity var(--transition);
}
.nav-link:hover {
  color: var(--text);
  text-decoration: none;
}
.nav-link:hover::before { opacity: 0.06; }
.nav-link.active {
  color: var(--text);
  background: rgba(139, 92, 246, 0.12);
  box-shadow: inset 0 0 0 1px rgba(139, 92, 246, 0.2);
}
.nav-link.active::before { opacity: 0.1; }
.nav-ico { font-size: 1.1em; width: 24px; text-align: center; flex-shrink: 0; position: relative; z-index: 1; }
.nav-txt { position: relative; z-index: 1; white-space: nowrap; transition: opacity 200ms; }

.toggle-btn {
  margin: var(--sp-2) var(--sp-3);
  padding: var(--sp-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  font-size: var(--text-base);
  transition: all var(--transition);
}
.toggle-btn:hover { color: var(--text); border-color: var(--border-hover); }

/* Main content */
.main {
  padding: var(--sp-8);
  max-width: 1100px;
  width: 100%;
}

/* Page transitions */
.page-enter-active { transition: opacity 150ms ease, transform 150ms ease; }
.page-leave-active { transition: opacity 100ms ease; }
.page-enter-from { opacity: 0; transform: translateY(8px); }
.page-leave-to { opacity: 0; }

/* Mobile */
@media (max-width: 768px) {
  .shell { grid-template-columns: 1fr; }
  .sidebar {
    position: fixed; left: 0; top: 0; z-index: 100;
    width: 200px;
    transform: translateX(-100%);
    box-shadow: 4px 0 32px rgba(0,0,0,0.7);
  }
  .sidebar:not(.closed) { transform: translateX(0); }
  .main { padding: var(--sp-4); }
}
</style>
