const OAUTH_URL_PARAMS = ['auth', 'reason']

// Removes OAuth result markers (auth=success / auth=error&reason=...) from the
// address bar without reloading, preserving unrelated query params and the hash.
export function cleanupOAuthUrlParams(): void {
  const url = new URL(window.location.href)
  let changed = false
  for (const key of OAUTH_URL_PARAMS) {
    if (url.searchParams.has(key)) {
      url.searchParams.delete(key)
      changed = true
    }
  }
  if (changed) {
    window.history.replaceState(
      window.history.state,
      '',
      `${url.pathname}${url.search}${url.hash}`,
    )
  }
}
