import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAuthStore } from '../auth'

// Helper: create a fake JWT with given payload (no signature needed — store only decodes payload)
function fakeJwt(payload: Record<string, unknown>): string {
  const header = btoa(JSON.stringify({ alg: 'RS256', typ: 'JWT' }))
  const body = btoa(JSON.stringify(payload))
  return `${header}.${body}.fake-signature`
}

describe('auth store — roles and isAdmin', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('returns roles from token with resource_access claim', () => {
    const store = useAuthStore()
    store.setToken(fakeJwt({
      sub: 'user-1',
      resource_access: { 'content-manager': { roles: ['user', 'admin'] } },
    }))
    expect(store.roles).toEqual(['user', 'admin'])
  })

  it('returns empty roles when token has no resource_access claim', () => {
    const store = useAuthStore()
    store.setToken(fakeJwt({ sub: 'user-1' }))
    expect(store.roles).toEqual([])
  })

  it('returns empty roles when token has no content-manager client', () => {
    const store = useAuthStore()
    store.setToken(fakeJwt({
      sub: 'user-1',
      resource_access: { 'other-client': { roles: ['viewer'] } },
    }))
    expect(store.roles).toEqual([])
  })

  it('returns empty roles when no token is set', () => {
    const store = useAuthStore()
    expect(store.roles).toEqual([])
  })

  it('isAdmin is true when roles include admin', () => {
    const store = useAuthStore()
    store.setToken(fakeJwt({
      sub: 'user-1',
      resource_access: { 'content-manager': { roles: ['user', 'admin'] } },
    }))
    expect(store.isAdmin).toBe(true)
  })

  it('isAdmin is false when roles do not include admin', () => {
    const store = useAuthStore()
    store.setToken(fakeJwt({
      sub: 'user-1',
      resource_access: { 'content-manager': { roles: ['user'] } },
    }))
    expect(store.isAdmin).toBe(false)
  })

  it('isAdmin is false when no token', () => {
    const store = useAuthStore()
    expect(store.isAdmin).toBe(false)
  })
})
