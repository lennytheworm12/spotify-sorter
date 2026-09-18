import { useEffect } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchCurrentUser, logoutRequest, NetworkError } from '../api/client'

export function useAuth() {
  const queryClient = useQueryClient()
  const userQuery = useQuery({
    queryKey: ['me'],
    queryFn: fetchCurrentUser,
    staleTime: Infinity,
    // Retry only transport-level failures (offline / backend unreachable) a
    // bounded number of times with short delays. HTTP failures such as 401 are
    // never retried, and a network outage is never treated as OAuth failure.
    retry: (failureCount, error) => error instanceof NetworkError && failureCount < 2,
    retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 4000),
  })

  // Refetch the session when the browser reports connectivity is back instead
  // of forcing the user to press Retry.
  useEffect(() => {
    function handleOnline() {
      if (!userQuery.data) {
        void userQuery.refetch()
      }
    }
    window.addEventListener('online', handleOnline)
    return () => window.removeEventListener('online', handleOnline)
  }, [userQuery])

  const logoutMutation = useMutation({
    mutationFn: logoutRequest,
    onSuccess: () => {
      // Drop account-scoped cache so a different Spotify account can never see
      // the previous user's playlists or undo history. Removing ['me'] also
      // flips the shell back to the logged-out connect screen. On failure the
      // authenticated state stays untouched so the error can be shown.
      queryClient.removeQueries({ queryKey: ['me'] })
      queryClient.removeQueries({ queryKey: ['playlists'] })
      queryClient.removeQueries({ queryKey: ['latest-sort-action'] })
    },
  })

  return {
    user: userQuery.data ?? null,
    isChecking: userQuery.isPending,
    authError: userQuery.error ?? null,
    retryAuth: () => userQuery.refetch(),
    isLoggingOut: logoutMutation.isPending,
    logout: () => logoutMutation.mutateAsync(),
  }
}
