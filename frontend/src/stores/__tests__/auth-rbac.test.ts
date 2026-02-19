import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAuthStore } from '../auth'

function fakeJwt(payload: Record<string, unknown>): string {
  const header = btoa(JSON.stringify({ alg: 'RS256', typ: 'JWT' }))
  const body = btoa(JSON.stringify(payload))
  return `${header}.${body}.fake-signature`
}

describe('auth store — isEditor and isViewer', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('isEditor is true when roles include editor', () => {
    const store = useAuthStore()
    store.setToken(fakeJwt({
      sub: 'user-1',
      resource_access: { 'errand': { roles: ['editor'] } },
    }))
    expect(store.isEditor).toBe(true)
    expect(store.isViewer).toBe(false)
  })

  it('isEditor is true when roles include admin', () => {
    const store = useAuthStore()
    store.setToken(fakeJwt({
      sub: 'user-1',
      resource_access: { 'errand': { roles: ['admin'] } },
    }))
    expect(store.isEditor).toBe(true)
    expect(store.isViewer).toBe(false)
  })

  it('isEditor is true when roles include both editor and admin', () => {
    const store = useAuthStore()
    store.setToken(fakeJwt({
      sub: 'user-1',
      resource_access: { 'errand': { roles: ['editor', 'admin'] } },
    }))
    expect(store.isEditor).toBe(true)
    expect(store.isViewer).toBe(false)
  })

  it('isViewer is true when authenticated but no editor or admin role', () => {
    const store = useAuthStore()
    store.setToken(fakeJwt({
      sub: 'user-1',
      resource_access: { 'errand': { roles: ['viewer'] } },
    }))
    expect(store.isEditor).toBe(false)
    expect(store.isViewer).toBe(true)
  })

  it('isViewer is false when not authenticated', () => {
    const store = useAuthStore()
    expect(store.isViewer).toBe(false)
    expect(store.isEditor).toBe(false)
  })

  it('isEditor is false when no roles', () => {
    const store = useAuthStore()
    store.setToken(fakeJwt({ sub: 'user-1' }))
    expect(store.isEditor).toBe(false)
    expect(store.isViewer).toBe(true)
  })
})
