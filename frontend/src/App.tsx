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

function subscribeRoute(callback: () => void) { window.addEventListener('hashchange', callback); return () => window.removeEventListener('hashchange', callback) }
function App() {
  const route = useSyncExternalStore(subscribeRoute, () => window.location.hash)
  const isOrganizer = route.startsWith('#/organize') || new URLSearchParams(window.location.search).has('auth')
  return (
    <QueryClientProvider client={queryClient}>
      {isOrganizer ? <><a className="organizer-return" href="#/" onClick={() => { if (window.location.search) window.history.replaceState(null, '', window.location.pathname + '#/') }}>← Back to song space</a><AppShell /></> : <SongSpace />}
    </QueryClientProvider>
  )
}

export default App
