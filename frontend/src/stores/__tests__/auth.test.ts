import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
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

describe('auth store — refresh token state', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('stores refresh token when provided to setToken', () => {
    const store = useAuthStore()
    store.setToken(fakeJwt({ sub: 'u1', exp: Math.floor(Date.now() / 1000) + 600 }), 'id_tok', 'rt_123')
    expect(store.refreshToken).toBe('rt_123')
  })

  it('sets refreshToken to null when not provided', () => {
    const store = useAuthStore()
    store.setToken(fakeJwt({ sub: 'u1' }), 'id_tok')
    expect(store.refreshToken).toBeNull()
  })

  it('clearToken clears refreshToken', () => {
    const store = useAuthStore()
    store.setToken(fakeJwt({ sub: 'u1', exp: Math.floor(Date.now() / 1000) + 600 }), 'id_tok', 'rt_123')
    store.clearToken()
    expect(store.refreshToken).toBeNull()
    expect(store.token).toBeNull()
    expect(store.idToken).toBeNull()
  })
})

describe('auth store — refresh timer', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('schedules refresh 30s before token expiry', () => {
    const store = useAuthStore()
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ access_token: 'new' }), { status: 200 }))

    const expIn300s = Math.floor(Date.now() / 1000) + 300
    store.setToken(fakeJwt({ sub: 'u1', exp: expIn300s }), undefined, 'rt_123')

    // Advance to 269 seconds — should NOT have fired
    vi.advanceTimersByTime(269_000)
    expect(fetchSpy).not.toHaveBeenCalled()

    // Advance 1 more second to hit 270s (300 - 30) — should fire
    vi.advanceTimersByTime(1_000)
    expect(fetchSpy).toHaveBeenCalledWith('/auth/refresh', expect.objectContaining({
      method: 'POST',
    }))
  })

  it('does not schedule refresh when no refresh token', () => {
    const store = useAuthStore()
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}', { status: 200 }))

    const expIn300s = Math.floor(Date.now() / 1000) + 300
    store.setToken(fakeJwt({ sub: 'u1', exp: expIn300s }))

    vi.advanceTimersByTime(300_000)
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('cancels timer on clearToken', () => {
    const store = useAuthStore()
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}', { status: 200 }))

    const expIn300s = Math.floor(Date.now() / 1000) + 300
    store.setToken(fakeJwt({ sub: 'u1', exp: expIn300s }), undefined, 'rt_123')

    store.clearToken()

    vi.advanceTimersByTime(300_000)
    expect(fetchSpy).not.toHaveBeenCalled()
  })
})
