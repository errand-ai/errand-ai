/**
 * Format an ISO datetime string as a relative time string.
 * Examples: "in 15 minutes", "at 5:00 PM today", "tomorrow at 9:00 AM"
 */
export function formatRelativeTime(isoString: string): string {
  const date = new Date(isoString)
  if (isNaN(date.getTime())) return ''

  const now = new Date()
  const diffMs = date.getTime() - now.getTime()
  const diffMinutes = Math.round(diffMs / 60000)

  if (diffMinutes < 0) {
    // Past time
    const absMins = Math.abs(diffMinutes)
    if (absMins < 60) return `${absMins}m ago`
    if (absMins < 1440) return `${Math.round(absMins / 60)}h ago`
    return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  }

  if (diffMinutes < 60) {
    return `in ${diffMinutes}m`
  }

  if (diffMinutes < 1440) {
    const hours = Math.round(diffMinutes / 60)
    return `in ${hours}h`
  }

  // Check if tomorrow
  const tomorrow = new Date(now)
  tomorrow.setDate(tomorrow.getDate() + 1)
  if (date.toDateString() === tomorrow.toDateString()) {
    return `tomorrow at ${date.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })}`
  }

  // Check if today (shouldn't normally reach here, but just in case)
  if (date.toDateString() === now.toDateString()) {
    return `at ${date.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })}`
  }

  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}
