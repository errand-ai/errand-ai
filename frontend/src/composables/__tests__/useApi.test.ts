import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAuthStore } from '../../stores/auth'
import { fetchTasks } from '../useApi'

// Helper: create a fake JWT with given payload
function fakeJwt(payload: Record<string, unknown>): string {
  const header = btoa(JSON.stringify({ alg: 'RS256', typ: 'JWT' }))
  const body = btoa(JSON.stringify(payload))
  return `${header}.${body}.fake-signature`
}

describe('useApi — 401 retry with refresh', () => {
  let originalLocation: Location

  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
    // Mock window.location to prevent actual navigation
    originalLocation = window.location
    Object.defineProperty(window, 'location', {
      writable: true,
      value: { ...originalLocation, href: 'http://localhost/' },
    })
  })

  afterEach(() => {
    Object.defineProperty(window, 'location', {
      writable: true,
      value: originalLocation,
    })
  })

  it('retries after successful refresh on 401', async () => {
    const auth = useAuthStore()
    const newToken = fakeJwt({ sub: 'u1', exp: Math.floor(Date.now() / 1000) + 600 })

    auth.setToken(fakeJwt({ sub: 'u1', exp: Math.floor(Date.now() / 1000) - 10 }), undefined, 'rt_123')

    let callCount = 0
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: string | URL | Request) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url
      if (url === '/auth/refresh') {
        return new Response(JSON.stringify({
          access_token: newToken,
          refresh_token: 'rt_new',
        }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      }
      callCount++
      if (callCount === 1) {
        return new Response('Unauthorized', { status: 401 })
      }
      // Second call (retry) succeeds
      return new Response(JSON.stringify([]), { status: 200, headers: { 'Content-Type': 'application/json' } })
    })

    const result = await fetchTasks()
    expect(result).toEqual([])
    expect(auth.token).toBe(newToken)
    expect(auth.refreshToken).toBe('rt_new')
  })

  it('redirects to login when refresh fails on 401', async () => {
    const auth = useAuthStore()
    auth.setToken(fakeJwt({ sub: 'u1', exp: Math.floor(Date.now() / 1000) - 10 }), undefined, 'rt_expired')

    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: string | URL | Request) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url
      if (url === '/auth/refresh') {
        return new Response('Unauthorized', { status: 401 })
      }
      return new Response('Unauthorized', { status: 401 })
    })

    await expect(fetchTasks()).rejects.toThrow('Unauthorized')
    expect(auth.token).toBeNull()
    expect(window.location.href).toBe('/login')
  })

  it('redirects to login on 401 when no refresh token available', async () => {
    const auth = useAuthStore()
    auth.setToken(fakeJwt({ sub: 'u1', exp: Math.floor(Date.now() / 1000) - 10 }))

    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('Unauthorized', { status: 401 })
    )

    await expect(fetchTasks()).rejects.toThrow('Unauthorized')
    expect(auth.token).toBeNull()
    expect(window.location.href).toBe('/login')
  })

  it('redirects to backend /auth/login on 401 in SSO mode (no refresh token)', async () => {
    const auth = useAuthStore()
    auth.setAuthMode('sso')
    auth.setToken(fakeJwt({ sub: 'u1', exp: Math.floor(Date.now() / 1000) - 10 }))

    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('Unauthorized', { status: 401 })
    )

    await expect(fetchTasks()).rejects.toThrow('Unauthorized')
    expect(auth.token).toBeNull()
    expect(window.location.href).toBe('/auth/login')
  })

  it('redirects to backend /auth/login on 401 in SSO mode when refresh fails', async () => {
    const auth = useAuthStore()
    auth.setAuthMode('sso')
    auth.setToken(fakeJwt({ sub: 'u1', exp: Math.floor(Date.now() / 1000) - 10 }), undefined, 'rt_expired')

    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: string | URL | Request) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url
      if (url === '/auth/refresh') {
        return new Response('Unauthorized', { status: 401 })
      }
      return new Response('Unauthorized', { status: 401 })
    })

    await expect(fetchTasks()).rejects.toThrow('Unauthorized')
    expect(auth.token).toBeNull()
    expect(window.location.href).toBe('/auth/login')
  })
})
