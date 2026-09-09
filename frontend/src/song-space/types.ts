/** A representation-neutral snapshot. Scores/ranks are supplied, never inferred by the UI. */
export interface Song {
  id: string
  title: string
  artists: string[]
  album?: string
  durationMs?: number
  audioUrl?: string
  community?: string
  x?: number
  y?: number
}

export interface SimilarityLink {
  source: string
  target: string
  score: number
  sourceRank: number | null
  targetRank: number | null
}

export interface SongSpaceDataset {
  schemaVersion: 'song-space-v1'
  id: string
  name: string
  description: string
  scorer: {
    id: string
    label: string
    description: string
    scoreRange: [number, number]
    higherIsCloser: boolean
  }
  neighborhoodSize: number
  songs: Song[]
  links: SimilarityLink[]
  communities?: { id: string; label: string }[]
}

export interface DatasetSource {
  id: string
  label: string
  url: string
}
export interface SongSpaceProvider {
  catalog(signal: AbortSignal): Promise<DatasetSource[]>
  load(source: DatasetSource, signal: AbortSignal): Promise<SongSpaceDataset>
}

export interface Community {
  id: string
  label: string
  color: string
  members: string[]
  x: number
  y: number
}
export interface PlacedSong extends Song {
  x: number
  y: number
  community: string
  color: string
  degree: number
}
export interface PlacedLink extends SimilarityLink {
  id: string
  bridge: boolean
  sharedNeighbors: number
  weight: number
}
export interface SongSpaceLayout {
  songs: PlacedSong[]
  links: PlacedLink[]
  communities: Community[]
  contours: number[][][][][]
  elapsedMs: number
}
