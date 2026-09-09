import type { DatasetSource, SongSpaceDataset, SongSpaceProvider } from './types'

const MAX_SONGS = 20_000
export const MAX_FILE_BYTES = 25 * 1024 * 1024
function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value))
    throw new Error('Expected a song-space object.')
  return value as Record<string, unknown>
}
function text(value: unknown, field: string): string {
  if (typeof value !== 'string' || !value.trim() || value.length > 2000)
    throw new Error(`Invalid ${field}.`)
  return value
}
function finite(value: unknown, field: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) throw new Error(`Invalid ${field}.`)
  return value
}
export function safeUrl(value: unknown): string {
  const url = text(value, 'URL')
  const parsed = new URL(url, 'http://local.invalid')
  if (
    !['http:', 'https:'].includes(parsed.protocol) ||
    parsed.username ||
    parsed.password ||
    url.startsWith('//')
  )
    throw new Error('Unsupported source URL.')
  return url
}
export function parseDataset(value: unknown): SongSpaceDataset {
  const data = object(value)
  if (data.schemaVersion !== 'song-space-v1')
    throw new Error('This file is not a song-space-v1 map. Export a song-space snapshot first.')
  const scorer = object(data.scorer)
  if (!Array.isArray(scorer.scoreRange) || scorer.scoreRange.length !== 2)
    throw new Error('A score range is required.')
  const range: [number, number] = [
    finite(scorer.scoreRange[0], 'score minimum'),
    finite(scorer.scoreRange[1], 'score maximum'),
  ]
  if (range[0] >= range[1] || typeof scorer.higherIsCloser !== 'boolean')
    throw new Error('Invalid score scale.')
  if (
    !Array.isArray(data.songs) ||
    data.songs.length > MAX_SONGS ||
    !Array.isArray(data.links) ||
    data.links.length > 500_000
  )
    throw new Error('Map is too large or has no song/link arrays.')
  const ids = new Set<string>()
  const songs = data.songs.map((raw) => {
    const song = object(raw),
      id = text(song.id, 'song ID')
    if (ids.has(id)) throw new Error(`Duplicate song ID: ${id}`)
    ids.add(id)
    if (!Array.isArray(song.artists) || !song.artists.length)
      throw new Error(`Missing artists for ${id}.`)
    const position =
      song.x !== undefined || song.y !== undefined
        ? { x: finite(song.x, 'x'), y: finite(song.y, 'y') }
        : {}
    const duration =
      song.durationMs === undefined ? {} : { durationMs: finite(song.durationMs, 'duration') }
    if (duration.durationMs !== undefined && duration.durationMs < 0)
      throw new Error('Negative song duration.')
    return {
      id,
      title: text(song.title, 'title'),
      artists: song.artists.map((a) => text(a, 'artist')),
      ...position,
      ...duration,
      ...(song.album === undefined ? {} : { album: text(song.album, 'album') }),
      ...(song.audioUrl === undefined ? {} : { audioUrl: safeUrl(song.audioUrl) }),
      ...(song.community === undefined ? {} : { community: text(song.community, 'community') }),
    }
  })
  const k = finite(data.neighborhoodSize, 'neighborhood size')
  if (!Number.isInteger(k) || k < 1 || k > 100)
    throw new Error('Neighborhood size must be between 1 and 100.')
  const pairs = new Set<string>()
  const ranks = new Map<string, Set<number>>()
  const rank = (value: unknown, id: string): number | null => {
    if (value === null) return null
    const n = finite(value, 'neighbor rank')
    if (!Number.isInteger(n) || n < 1 || n > k)
      throw new Error('Neighbor rank outside snapshot limits.')
    const used = ranks.get(id) ?? new Set<number>()
    if (used.has(n)) throw new Error('Duplicate neighbor rank.')
    used.add(n)
    ranks.set(id, used)
    return n
  }
  const links = data.links.map((raw) => {
    const link = object(raw),
      source = text(link.source, 'source'),
      target = text(link.target, 'target')
    if (!ids.has(source) || !ids.has(target) || source === target)
      throw new Error('A connection references a missing song or itself.')
    const key = JSON.stringify([source, target].sort())
    if (pairs.has(key)) throw new Error('Duplicate similarity connection.')
    pairs.add(key)
    const score = finite(link.score, 'similarity score')
    if (score < range[0] || score > range[1])
      throw new Error('Similarity score outside the declared range.')
    const sourceRank = rank(link.sourceRank, source),
      targetRank = rank(link.targetRank, target)
    if (sourceRank === null && targetRank === null)
      throw new Error('A connection must belong to at least one neighbor list.')
    return { source, target, score, sourceRank, targetRank }
  })
  const communities =
    data.communities === undefined
      ? undefined
      : (Array.isArray(data.communities) ? data.communities : []).map((raw) => {
          const c = object(raw)
          return {
            id: text(c.id, 'community ID'),
            label: text(c.label, 'community label'),
          }
        })
  if (data.communities !== undefined && !Array.isArray(data.communities))
    throw new Error('Invalid communities.')
  if (communities && new Set(communities.map((c) => c.id)).size !== communities.length)
    throw new Error('Duplicate community.')
  if (
    songs.some((s) => s.community !== undefined) &&
    (!communities || songs.some((s) => !communities.some((c) => c.id === s.community)))
  )
    throw new Error('Provide complete community assignments or omit them.')
  return {
    schemaVersion: 'song-space-v1',
    id: text(data.id, 'dataset ID'),
    name: text(data.name, 'dataset name'),
    description: text(data.description, 'description'),
    scorer: {
      id: text(scorer.id, 'scorer ID'),
      label: text(scorer.label, 'scorer label'),
      description: text(scorer.description, 'scorer description'),
      scoreRange: range,
      higherIsCloser: scorer.higherIsCloser,
    },
    neighborhoodSize: k,
    songs,
    links,
    ...(communities ? { communities } : {}),
  }
}
async function fetchJson(url: string, signal: AbortSignal): Promise<unknown> {
  const response = await fetch(safeUrl(url), {
    signal,
    credentials: 'include',
  })
  if (!response.ok)
    throw new Error(
      `The map source could not be reached (${response.status}). Retry or open a local map file.`,
    )
  try {
    return await response.json()
  } catch {
    throw new Error(
      'The map source did not return JSON. Check its address or open a local map file.',
    )
  }
}
export function httpProvider(catalogUrl: string): SongSpaceProvider {
  return {
    async catalog(signal) {
      const value = await fetchJson(catalogUrl, signal)
      if (!Array.isArray(value)) throw new Error('Invalid map catalog.')
      const sources: DatasetSource[] = value.map((raw) => {
        const row = object(raw)
        return {
          id: text(row.id, 'source ID'),
          label: text(row.label, 'source label'),
          url: safeUrl(row.url),
        }
      })
      if (new Set(sources.map((s) => s.id)).size !== sources.length)
        throw new Error('Duplicate map source.')
      return sources
    },
    async load(source, signal) {
      return parseDataset(await fetchJson(source.url, signal))
    },
  }
}

const providerIds = new WeakMap<SongSpaceProvider, number>()
let nextProviderId = 0
export function providerKey(provider: SongSpaceProvider): number {
  if (!providerIds.has(provider)) providerIds.set(provider, ++nextProviderId)
  return providerIds.get(provider)!
}
