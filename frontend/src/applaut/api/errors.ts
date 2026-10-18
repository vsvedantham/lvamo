/** An API error as a sentence safe to render. FastAPI sends `detail` as a
 * string, or (for validation errors) a list of objects, which React can't
 * render as text: putting that list in JSX blanks the whole page. */
export function apiErrorMessage(err: unknown, fallback: string): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail.length) {
    return detail.map((d: any) => {
      const field = Array.isArray(d?.loc) ? String(d.loc[d.loc.length - 1]).replace(/_/g, ' ') : ''
      const msg = String(d?.msg ?? 'invalid value').replace(/^Value error, /, '')
      return field && field !== 'body' ? `${field}: ${msg}` : msg
    }).join(' · ')
  }
  return fallback
}
