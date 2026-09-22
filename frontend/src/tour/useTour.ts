import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'

/** A single coachmark step. */
export interface TourStep {
  /** data-tour attribute value to locate the anchor element. */
  target: string
  /** Route to navigate to before locating the anchor (optional). */
  route?: string
  /** i18n key or literal title. */
  title: string
  /** i18n key or literal body text. */
  body: string
}

/** Rect of the currently highlighted element (viewport coordinates). */
export interface TargetRect {
  top: number
  left: number
  width: number
  height: number
}

const STORAGE_KEY = 'tour_done'
const POLL_INTERVAL_MS = 50
const POLL_TIMEOUT_MS = 1500

// Module-level singleton state so any component can drive/observe the tour.
const active = ref(false)
const index = ref(0)
const steps = ref<TourStep[]>([])
const targetRect = ref<TargetRect | null>(null)

export function useTour() {
  const router = useRouter()

  const currentStep = computed<TourStep | null>(() => steps.value[index.value] ?? null)
  const total = computed(() => steps.value.length)
  const stepNumber = computed(() => index.value + 1)
  const isFirst = computed(() => index.value === 0)
  const isLast = computed(() => index.value >= steps.value.length - 1)

  /** Wait until an element matching the selector is in the DOM, or timeout. */
  function waitForElement(selector: string): Promise<HTMLElement | null> {
    return new Promise((resolve) => {
      const existing = document.querySelector<HTMLElement>(selector)
      if (existing) {
        resolve(existing)
        return
      }
      const start = performance.now()
      const timer = window.setInterval(() => {
        const el = document.querySelector<HTMLElement>(selector)
        if (el) {
          window.clearInterval(timer)
          resolve(el)
        } else if (performance.now() - start >= POLL_TIMEOUT_MS) {
          window.clearInterval(timer)
          resolve(null)
        }
      }, POLL_INTERVAL_MS)
    })
  }

  /** Resolve the current step: navigate, locate the anchor, compute its rect. */
  async function resolveStep() {
    const step = currentStep.value
    if (!step) return
    if (step.route && router.currentRoute.value.path !== step.route) {
      await router.push(step.route)
    }
    // Let the router-view render the new page before querying the DOM.
    await new Promise<void>((r) => requestAnimationFrame(() => r()))
    const el = await waitForElement(`[data-tour="${step.target}"]`)
    if (el) {
      const rect = el.getBoundingClientRect()
      targetRect.value = {
        top: rect.top,
        left: rect.left,
        width: rect.width,
        height: rect.height,
      }
    } else {
      // Anchor missing/unrendered: don't block, just center the bubble.
      targetRect.value = null
    }
  }

  /** Recompute the current target rect (e.g. on window resize). */
  function recompute() {
    const step = currentStep.value
    if (!step) return
    const el = document.querySelector<HTMLElement>(`[data-tour="${step.target}"]`)
    if (el) {
      const rect = el.getBoundingClientRect()
      targetRect.value = {
        top: rect.top,
        left: rect.left,
        width: rect.width,
        height: rect.height,
      }
    } else {
      targetRect.value = null
    }
  }

  async function next() {
    if (isLast.value) {
      finish()
      return
    }
    index.value += 1
    await resolveStep()
  }

  async function prev() {
    if (isFirst.value) return
    index.value -= 1
    await resolveStep()
  }

  function skip() {
    finish()
  }

  function finish() {
    active.value = false
    targetRect.value = null
    try {
      localStorage.setItem(STORAGE_KEY, '1')
    } catch {
      // ignore storage errors (private mode etc.)
    }
  }

  function hasCompleted(): boolean {
    try {
      return localStorage.getItem(STORAGE_KEY) === '1'
    } catch {
      return false
    }
  }

  /** Start the tour with the given steps if it has never been completed. */
  async function start(tourSteps: TourStep[]) {
    if (hasCompleted()) return
    await run(tourSteps)
  }

  /** Force-start the tour regardless of completion state. */
  async function restart(tourSteps: TourStep[]) {
    await run(tourSteps)
  }

  async function run(tourSteps: TourStep[]) {
    steps.value = tourSteps
    index.value = 0
    active.value = true
    await resolveStep()
  }

  return {
    active,
    index,
    steps,
    targetRect,
    currentStep,
    total,
    stepNumber,
    isFirst,
    isLast,
    next,
    prev,
    skip,
    finish,
    recompute,
    start,
    restart,
    hasCompleted,
  }
}
