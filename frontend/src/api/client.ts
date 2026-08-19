import type {
  CurrentUser,
  Playlist,
  SortRequest,
  SortResponse,
} from './types'

const API_BASE = (import.meta.env.VITE_API_URL ?? 'http://localhost:3000').replace(
  /\/+$/,
  '',
)

class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
    this.name = 'ApiError'
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })

  if (response.status === 204) {
    return undefined as T
  }

  let body: unknown = null
  try {
    body = await response.json()
  } catch {
    body = null
  }

  if (!response.ok) {
    const message =
      body && typeof body === 'object' && 'message' in body
        ? String((body as { message: unknown }).message)
        : `Request failed (${response.status})`
    throw new ApiError(message, response.status)
  }

  return body as T
}

export function spotifyLoginUrl(): string {
  return `${API_BASE}/auth/spotify/login`
}

export async function fetchCurrentUser(): Promise<CurrentUser | null> {
  try {
    return await request<CurrentUser>('/auth/me')
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      return null
    }
    throw error
  }
}

export async function logoutRequest(): Promise<void> {
  await request<unknown>('/auth/logout', { method: 'POST' })
}

export async function fetchPlaylists(): Promise<Playlist[]> {
  return request<Playlist[]>('/playlists')
}

export async function runSort(payload: SortRequest): Promise<SortResponse> {
  return request<SortResponse>('/sort', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}
