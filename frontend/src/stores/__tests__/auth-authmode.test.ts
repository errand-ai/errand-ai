import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAuthStore } from '../auth'

function fakeJwt(payload: Record<string, unknown>): string {
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))
  const body = btoa(JSON.stringify(payload))
  return `${header}.${body}.fake-signature`
}

describe('auth store — authMode state management', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('authMode defaults to null', () => {
    const store = useAuthStore()
    expect(store.authMode).toBeNull()
  })

  it('setAuthMode sets the mode to local', () => {
    const store = useAuthStore()
    store.setAuthMode('local')
    expect(store.authMode).toBe('local')
  })

  it('setAuthMode sets the mode to sso', () => {
    const store = useAuthStore()
    store.setAuthMode('sso')
    expect(store.authMode).toBe('sso')
  })

  it('setAuthMode sets the mode to setup', () => {
    const store = useAuthStore()
    store.setAuthMode('setup')
    expect(store.authMode).toBe('setup')
  })

  it('authMode is reactive and updates correctly', () => {
    const store = useAuthStore()
    expect(store.authMode).toBeNull()
    store.setAuthMode('local')
    expect(store.authMode).toBe('local')
    store.setAuthMode('sso')
    expect(store.authMode).toBe('sso')
  })

  it('extracts roles from _roles claim for local auth tokens', () => {
    const store = useAuthStore()
    store.setToken(fakeJwt({
      sub: 'admin',
      _roles: ['admin'],
      iss: 'errand-local',
    }))
    expect(store.roles).toEqual(['admin'])
    expect(store.isAdmin).toBe(true)
  })

  it('prefers _roles claim over resource_access when present', () => {
    const store = useAuthStore()
    store.setToken(fakeJwt({
      sub: 'admin',
      _roles: ['admin'],
      resource_access: { errand: { roles: ['viewer'] } },
    }))
    expect(store.roles).toEqual(['admin'])
  })

  it('falls back to resource_access when _roles is not present', () => {
    const store = useAuthStore()
    store.setToken(fakeJwt({
      sub: 'user-1',
      resource_access: { errand: { roles: ['editor'] } },
    }))
    expect(store.roles).toEqual(['editor'])
  })
})
