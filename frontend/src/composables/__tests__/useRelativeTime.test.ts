import { describe, it, expect } from 'vitest'
import { formatRelativeTime } from '../useRelativeTime'

describe('formatRelativeTime', () => {
  const now = new Date('2025-06-15T12:00:00Z')

  it('returns empty string for invalid date', () => {
    expect(formatRelativeTime('not-a-date', now)).toBe('')
  })

  it('returns "in Xm" for minutes in the future', () => {
    const future = new Date(now.getTime() + 15 * 60000).toISOString()
    expect(formatRelativeTime(future, now)).toBe('in 15m')
  })

  it('returns "in Xh" for hours in the future', () => {
    const future = new Date(now.getTime() + 3 * 3600000).toISOString()
    expect(formatRelativeTime(future, now)).toBe('in 3h')
  })

  it('returns "Xm ago" for minutes in the past', () => {
    const past = new Date(now.getTime() - 10 * 60000).toISOString()
    expect(formatRelativeTime(past, now)).toBe('10m ago')
  })

  it('returns "Xh ago" for hours in the past', () => {
    const past = new Date(now.getTime() - 2 * 3600000).toISOString()
    expect(formatRelativeTime(past, now)).toBe('2h ago')
  })

  it('returns different results with different now values', () => {
    const target = new Date('2025-06-15T12:30:00Z').toISOString()
    const early = new Date('2025-06-15T12:00:00Z')
    const late = new Date('2025-06-15T12:25:00Z')

    expect(formatRelativeTime(target, early)).toBe('in 30m')
    expect(formatRelativeTime(target, late)).toBe('in 5m')
  })

  it('defaults now to current time when not provided', () => {
    // Future date far enough to reliably be "in Xh" regardless of when test runs
    const future = new Date(Date.now() + 5 * 3600000).toISOString()
    const result = formatRelativeTime(future)
    expect(result).toBe('in 5h')
  })
})
