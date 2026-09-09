import { useEffect, useSyncExternalStore } from 'react'
import { SongSpace } from './song-space/SongSpace'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useAuth } from './hooks/useAuth'
import { cleanupOAuthUrlParams } from './utils/oauthCleanup'
import { userFacingErrorMessage } from './api/client'
import { ConnectScreen } from './components/ConnectScreen'
import { Dashboard } from './components/Dashboard'
import './App.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      staleTime: 30_000,
    },
  },
})

function AppShell() {
  const { user, isChecking, authError, retryAuth, logout, isLoggingOut } = useAuth()

  useEffect(() => {
    if (isChecking) {
      return
    }
    if (user) {
      cleanupOAuthUrlParams()
      return
    }
    const params = new URLSearchParams(window.location.search)
    if (params.get('auth') !== 'error') {
      cleanupOAuthUrlParams()
    }
  }, [isChecking, user])

  if (isChecking) {
    return (
      <div className="checking" role="status" aria-live="polite">
        <span className="spinner" aria-hidden="true" />
        <p>Checking your Spotify connection…</p>
      </div>
    )
  }

  if (!user) {
    return (
      <ConnectScreen
        connectionError={
          authError
            ? userFacingErrorMessage(
                authError,
                'We couldn’t reach the organizer service. Your saved Spotify session is unchanged; check the backend and retry.',
              )
            : null
        }
        onRetry={() => void retryAuth()}
      />
    )
  }

  return <Dashboard user={user} onLogout={logout} isSigningOut={isLoggingOut} />
}

function subscribeRoute(callback: () => void) {
  window.addEventListener('hashchange', callback)
  window.addEventListener('popstate', callback)
  return () => {
    window.removeEventListener('hashchange', callback)
    window.removeEventListener('popstate', callback)
  }
}
function App() {
  const location = new URL(useSyncExternalStore(subscribeRoute, () => window.location.href))
  const isOrganizer = location.hash.startsWith('#/organize') || location.searchParams.has('auth')
  return (
    <QueryClientProvider client={queryClient}>
      {isOrganizer ? (
        <>
          <a
            className="organizer-return"
            href="#/"
            onClick={(event) => {
              event.preventDefault()
              const destination = new URL(window.location.href)
              destination.searchParams.delete('auth')
              destination.searchParams.delete('reason')
              destination.hash = '/'
              window.history.pushState(null, '', destination)
              window.dispatchEvent(new PopStateEvent('popstate'))
            }}
          >
            ← Back to song space
          </a>
          <AppShell />
        </>
      ) : (
        <SongSpace />
      )}
    </QueryClientProvider>
  )
}

export default App
