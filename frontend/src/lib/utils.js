/**
 * Format an ISO timestamp as a relative time string.
 * e.g., "2 minutes ago", "1 hour ago", "3 days ago"
 */
export function timeAgo(isoString) {
  if (!isoString) return '—'
  const now = new Date()
  const then = new Date(isoString)
  const diffMs = now - then
  const diffMin = Math.floor(diffMs / 60000)

  if (diffMin < 1) return 'just now'
  if (diffMin < 60) return `${diffMin}m ago`
  const diffHr = Math.floor(diffMin / 60)
  if (diffHr < 24) return `${diffHr}h ago`
  const diffDay = Math.floor(diffHr / 24)
  return `${diffDay}d ago`
}

/**
 * Format a date string (YYYY-MM-DD) as "Feb 5" style.
 */
export function formatShortDate(dateStr) {
  if (!dateStr) return '—'
  const d = new Date(dateStr + 'T00:00:00')
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}
