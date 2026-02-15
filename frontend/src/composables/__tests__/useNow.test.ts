import { describe, it, expect, vi, afterEach } from 'vitest'
import { effectScope, ref } from 'vue'
import { useNow } from '../useNow'

describe('useNow', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('returns a ref with the current date', () => {
    const scope = effectScope()
    scope.run(() => {
      const now = useNow(30000)
      expect(now.value).toBeInstanceOf(Date)
    })
    scope.stop()
  })

  it('updates the ref on the interval', () => {
    vi.useFakeTimers()
    const scope = effectScope()
    scope.run(() => {
      const now = useNow(1000)
      const initial = now.value.getTime()

      vi.advanceTimersByTime(1000)
      expect(now.value.getTime()).toBeGreaterThan(initial)
    })
    scope.stop()
  })

  it('cleans up the interval on scope dispose', () => {
    vi.useFakeTimers()
    const clearSpy = vi.spyOn(globalThis, 'clearInterval')
    const scope = effectScope()
    scope.run(() => {
      useNow(1000)
    })
    scope.stop()
    expect(clearSpy).toHaveBeenCalled()
    clearSpy.mockRestore()
  })

  it('does not start the interval when enabled is false', () => {
    vi.useFakeTimers()
    const scope = effectScope()
    scope.run(() => {
      const enabled = ref(false)
      const now = useNow(1000, enabled)
      const initial = now.value.getTime()

      vi.advanceTimersByTime(3000)
      expect(now.value.getTime()).toBe(initial)
    })
    scope.stop()
  })

  it('starts the interval when enabled changes from false to true', () => {
    vi.useFakeTimers()
    const scope = effectScope()
    scope.run(() => {
      const enabled = ref(false)
      const now = useNow(1000, enabled)
      const initial = now.value.getTime()

      vi.advanceTimersByTime(2000)
      expect(now.value.getTime()).toBe(initial)

      enabled.value = true
      vi.advanceTimersByTime(1000)
      expect(now.value.getTime()).toBeGreaterThan(initial)
    })
    scope.stop()
  })

  it('stops the interval when enabled changes from true to false', () => {
    vi.useFakeTimers()
    const scope = effectScope()
    scope.run(() => {
      const enabled = ref(true)
      const now = useNow(1000, enabled)

      vi.advanceTimersByTime(1000)
      const afterFirstTick = now.value.getTime()

      enabled.value = false
      vi.advanceTimersByTime(3000)
      expect(now.value.getTime()).toBe(afterFirstTick)
    })
    scope.stop()
  })
})
