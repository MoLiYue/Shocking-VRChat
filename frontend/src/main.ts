import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import './assets/global.css'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/dashboard' },
    { path: '/dashboard', component: () => import('./views/Dashboard.vue') },
    { path: '/curve', component: () => import('./views/CurveEditor.vue') },
    { path: '/combo', component: () => import('./views/ComboEditor.vue') },
    { path: '/params', component: () => import('./views/ParamMap.vue') },
    { path: '/recorder', component: () => import('./views/Recorder.vue') },
    { path: '/setup', component: () => import('./views/SetupWizard.vue') },
    { path: '/settings', component: () => import('./views/Settings.vue') },
    { path: '/strength', component: () => import('./views/StrengthLimit.vue') },
    { path: '/overlimit-rules', component: () => import('./views/OverlimitRules.vue') },
    { path: '/wave-test', component: () => import('./views/WaveTest.vue') },
  ],
})

const app = createApp(App)
app.use(router)
app.mount('#app')
