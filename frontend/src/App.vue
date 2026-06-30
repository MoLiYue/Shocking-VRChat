<script setup lang="ts">
import { ref } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const sidebarCollapsed = ref(false)

const navItems = [
  { path: '/dashboard', label: 'Dashboard', icon: '⚡' },
  { path: '/params', label: '参数管理', icon: '🎛' },
  { path: '/curve', label: '强度曲线', icon: '📈' },
  { path: '/combo', label: 'Combo 配置', icon: '🔀' },
  { path: '/recorder', label: '录制回放', icon: '🎙' },
]

function getPageTitle() {
  const item = navItems.find(n => n.path === route.path)
  return item?.label || ''
}
</script>

<template>
  <div class="app-shell" :class="{ collapsed: sidebarCollapsed }">
    <!-- Sidebar -->
    <aside class="sidebar">
      <div class="sidebar-header">
        <span class="brand-icon">⚡</span>
        <span class="brand-text">Shocking VRChat</span>
      </div>

      <nav class="nav-list">
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

      <div class="sidebar-footer">
        <button class="collapse-btn" @click="sidebarCollapsed = !sidebarCollapsed" :title="sidebarCollapsed ? '展开' : '收起'">
          {{ sidebarCollapsed ? '→' : '←' }}
        </button>
      </div>
    </aside>

    <!-- Main -->
    <div class="main-wrapper">
      <!-- Top bar -->
      <header class="topbar">
        <div class="topbar-left">
          <button class="mobile-menu-btn" @click="sidebarCollapsed = !sidebarCollapsed">☰</button>
          <h1 class="topbar-title">{{ getPageTitle() }}</h1>
        </div>
        <div class="topbar-right">
          <slot name="topbar-actions" />
        </div>
      </header>

      <!-- Page content -->
      <main class="page-content">
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </main>
    </div>
  </div>
</template>

<style scoped>
.app-shell {
  display: grid;
  grid-template-columns: 220px 1fr;
  min-height: 100vh;
  transition: grid-template-columns var(--transition);
}
.app-shell.collapsed {
  grid-template-columns: 60px 1fr;
}

/* Sidebar */
.sidebar {
  background: var(--bg-elevated);
  border-right: 1px solid var(--border-subtle);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: sticky;
  top: 0;
  height: 100vh;
}
.sidebar-header {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-5) var(--sp-4);
  border-bottom: 1px solid var(--border-subtle);
  min-height: 60px;
}
.brand-icon { font-size: 1.3em; }
.brand-text {
  font-size: var(--text-sm);
  font-weight: 700;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  transition: opacity var(--transition);
}
.collapsed .brand-text { opacity: 0; width: 0; }

.nav-list {
  flex: 1;
  padding: var(--sp-3) var(--sp-2);
  display: flex;
  flex-direction: column;
  gap: var(--sp-1);
}
.nav-item {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-3) var(--sp-3);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  text-decoration: none;
  font-size: var(--text-sm);
  font-weight: 500;
  transition: all var(--transition);
  white-space: nowrap;
  overflow: hidden;
}
.nav-item:hover {
  background: rgba(255,255,255,0.04);
  color: var(--text);
  text-decoration: none;
}
.nav-item.active {
  background: rgba(99,102,241,0.1);
  color: var(--accent-hover);
}
.nav-icon { font-size: 1.1em; flex-shrink: 0; width: 24px; text-align: center; }
.nav-label { transition: opacity var(--transition); }
.collapsed .nav-label { opacity: 0; }

.sidebar-footer {
  padding: var(--sp-3);
  border-top: 1px solid var(--border-subtle);
}
.collapse-btn {
  width: 100%;
  padding: var(--sp-2);
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  font-size: var(--text-sm);
  transition: color var(--transition);
}
.collapse-btn:hover { color: var(--text); }

/* Main content */
.main-wrapper {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  overflow-x: hidden;
}
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--sp-4) var(--sp-6);
  border-bottom: 1px solid var(--border-subtle);
  background: var(--bg-elevated);
  position: sticky;
  top: 0;
  z-index: 10;
  backdrop-filter: blur(8px);
}
.topbar-left { display: flex; align-items: center; gap: var(--sp-3); }
.topbar-title {
  font-size: var(--text-lg);
  font-weight: 600;
  letter-spacing: -0.01em;
}
.mobile-menu-btn {
  display: none;
  border: none;
  background: none;
  color: var(--text);
  font-size: 1.2em;
  cursor: pointer;
  padding: var(--sp-1);
}
.page-content {
  flex: 1;
  padding: var(--sp-6);
  max-width: 1200px;
  width: 100%;
}

/* Page transitions */
.fade-enter-active, .fade-leave-active {
  transition: opacity 120ms ease;
}
.fade-enter-from, .fade-leave-to {
  opacity: 0;
}

/* Responsive */
@media (max-width: 768px) {
  .app-shell {
    grid-template-columns: 1fr;
  }
  .sidebar {
    position: fixed;
    left: -220px;
    width: 220px;
    z-index: 100;
    transition: left var(--transition);
    box-shadow: 4px 0 24px rgba(0,0,0,0.5);
  }
  .app-shell.collapsed .sidebar { left: -220px; }
  .app-shell:not(.collapsed) .sidebar { left: 0; }
  .mobile-menu-btn { display: block; }
  .sidebar-footer { display: none; }
  .page-content { padding: var(--sp-4); }
}
</style>
