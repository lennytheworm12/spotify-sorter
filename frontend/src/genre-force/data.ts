import { safeUrl } from '../song-space/data'
import type { SongSpaceLayout } from '../song-space/types'
import type { AudioPair, Concept, GenreSong, Settings } from './scoring'
export interface ForcePacket {
  schemaVersion: 'genre-force-explorer-v1'
  songs: GenreSong[]
  pairs: AudioPair[]
  concepts: Record<string, Concept>
  neighborhoodLabels: Record<string, string>
  defaults: Settings
  audioIdentity: string
  provenance: Record<string, unknown>
  baseLayout: SongSpaceLayout
  coordinateOrigin: string
}
export function parseForcePacket(raw: unknown): ForcePacket {
  if (!raw || typeof raw !== 'object') throw Error('Invalid genre explorer data')
  const p = raw as ForcePacket
  if (
    p.schemaVersion !== 'genre-force-explorer-v1' ||
    !Array.isArray(p.songs) ||
    p.songs.length !== 100 ||
    !Array.isArray(p.pairs) ||
    p.pairs.length !== 4950
  )
    throw Error('The complete frozen 100 and all 4,950 pairs are required')
  const ids = new Set(p.songs.map((s) => s.id))
  if (ids.size !== 100) throw Error('Duplicate song identities')
  const validVector = (v: unknown) =>
    v &&
    typeof v === 'object' &&
    !Array.isArray(v) &&
    Object.values(v).every((x) => typeof x === 'number' && Number.isFinite(x) && x >= 0 && x <= 1)
  for (const s of p.songs) {
    if (
      typeof s.title !== 'string' ||
      !Array.isArray(s.artists) ||
      !s.artists.every((x) => typeof x === 'string') ||
      !validVector(s.canonical) ||
      !Array.isArray(s.specificStyleIds) ||
      s.specificStyleIds.some((k) => !s.canonical[k] || p.concepts[k]?.kind !== 'style') ||
      !validVector(s.neighborhoods) ||
      !Array.isArray(s.excluded) ||
      !Array.isArray(s.warnings) ||
      !Array.isArray(s.traces) ||
      !Number.isFinite(s.durationSeconds)
    )
      throw Error('Invalid song profile')
    safeUrl(s.audioUrl)
    if (Object.keys(s.canonical).some((k) => !p.concepts[k]))
      throw Error('Unknown canonical concept')
  }
  for (const [id, c] of Object.entries(p.concepts))
    if (c.id !== id || !validVector(c.neighborhoods)) throw Error('Invalid concept registry')
  const keys = new Set<string>()
  for (const pair of p.pairs) {
    const key = JSON.stringify([pair.a, pair.b].sort())
    if (
      !ids.has(pair.a) ||
      !ids.has(pair.b) ||
      pair.a === pair.b ||
      keys.has(key) ||
      !Number.isFinite(pair.audio)
    )
      throw Error('Invalid exhaustive audio evidence')
    keys.add(key)
  }
  if (
    !p.baseLayout ||
    p.baseLayout.songs.length !== 100 ||
    new Set(p.baseLayout.songs.map((s) => s.id)).size !== 100 ||
    p.baseLayout.songs.some((s) => !ids.has(s.id) || !Number.isFinite(s.x) || !Number.isFinite(s.y))
  )
    throw Error('Missing baseline coordinates')
  if (
    p.defaults.alpha !== 0 ||
    p.defaults.beta !== 0.05 ||
    p.defaults.eta !== 0.25 ||
    p.defaults.genreMode !== 'canonical_plus_residual' ||
    p.defaults.forceMode !== 'pull_only'
  )
    throw Error('Unexpected frozen development defaults')
  return p
}
export async function loadForcePacket(signal: AbortSignal) {
  const r = await fetch('/__song-space/genre/data', { signal })
  if (!r.ok)
    throw Error(
      'Genre explorer data is unavailable. Start the local server with GENRE_FORCE_DATA_DIR pointing to the prepared run.',
    )
  return parseForcePacket(await r.json())
}
