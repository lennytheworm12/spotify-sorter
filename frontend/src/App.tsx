import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useAuth } from './hooks/useAuth'
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
  const { user, isChecking, authError, retryAuth, logout } = useAuth()

  if (isChecking) {
    return (
      <div className="checking" role="status" aria-live="polite">
        <span className="spinner" aria-hidden="true" />
        <p>Checking your Spotify connection…</p>
      </div>
    )
  }

  if (!user) {
    return <ConnectScreen connectionError={authError} onRetry={() => void retryAuth()} />
  }

  return (
    <Dashboard user={user} onLogout={logout} />
  )
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AppShell />
    </QueryClientProvider>
  )
}

export default App
