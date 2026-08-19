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
    onSettled: () => {
      void queryClient.invalidateQueries()
    },
  })

  return {
    user: userQuery.data ?? null,
    isChecking: userQuery.isPending,
    authError: userQuery.isError,
    retryAuth: () => userQuery.refetch(),
    logout: () => logoutMutation.mutateAsync(),
  }
}
