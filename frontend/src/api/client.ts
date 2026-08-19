import type {
  CurrentUser,
  Playlist,
  SortAction,
  SortRequest,
  SortResponse,
  UndoResponse,
} from './types'

const API_BASE = (import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:3000').replace(
  /\/+$/,
  '',
)

export class ApiError extends Error {
  status: number
  body: unknown

  constructor(message: string, status: number, body: unknown = null) {
    super(message)
    this.status = status
    this.body = body
    this.name = 'ApiError'
  }
}

export const NETWORK_ERROR_MESSAGE =
  'We couldn’t reach the organizer service. Your saved Spotify session is unchanged; check the backend and retry.'

/**
 * Transport-level failures (offline, DNS, connection refused, CORS) surface
 * from fetch as TypeError. We normalize those into this error so the browser's
 * raw network error text never reaches the UI.
 */
export class NetworkError extends Error {
  constructor(message: string = NETWORK_ERROR_MESSAGE) {
    super(message)
    this.name = 'NetworkError'
  }
}

export function userFacingErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message.trim() ? error.message : fallback
}

function jsonHeaders(init?: RequestInit): HeadersInit | undefined {
  if (init?.body == null) {
    return init?.headers
  }
  const headers = new Headers(init.headers)
  headers.set('Content-Type', 'application/json')
  return headers
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      credentials: 'include',
      ...init,
      headers: jsonHeaders(init),
    })
  } catch (error) {
    if (error instanceof TypeError) {
      throw new NetworkError()
    }
    throw error
  }

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
    throw new ApiError(message, response.status, body)
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

export async function fetchLatestSortAction(): Promise<SortAction | null> {
  const action = await request<SortAction | undefined>('/sort/actions/latest')
  return action ?? null
}

export async function undoSortAction(
  actionId: string,
  bucketNames: string[],
): Promise<UndoResponse> {
  return request<UndoResponse>(
    `/sort/actions/${encodeURIComponent(actionId)}/undo`,
    {
      method: 'POST',
      body: JSON.stringify({ buckets: bucketNames }),
    },
  )
}
