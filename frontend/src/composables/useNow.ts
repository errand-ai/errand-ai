import { ref, watch, onScopeDispose } from 'vue'
import type { Ref } from 'vue'

export function useNow(intervalMs: number, enabled?: Ref<boolean>): Ref<Date> {
  const now = ref(new Date())
  let timer: ReturnType<typeof setInterval> | null = null

  const start = () => {
    if (timer) return
    timer = setInterval(() => { now.value = new Date() }, intervalMs)
  }

  const stop = () => {
    if (timer) { clearInterval(timer); timer = null }
  }

  if (enabled) {
    watch(enabled, (val) => { val ? start() : stop() }, { immediate: true, flush: 'sync' })
  } else {
    start()
  }

  onScopeDispose(stop)
  return now
}
