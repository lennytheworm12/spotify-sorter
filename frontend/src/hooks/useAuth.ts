import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchCurrentUser, logoutRequest } from '../api/client'

export function useAuth() {
  const queryClient = useQueryClient()
  const userQuery = useQuery({
    queryKey: ['me'],
    queryFn: fetchCurrentUser,
    staleTime: Infinity,
    retry: false,
  })

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
