export interface CurrentUser {
  spotifyId: string
  displayName: string | null
  profilePictureUrl: string | null
}

export interface PlaylistOwner {
  id: string
}

export interface Playlist {
  id: string
  name: string
  description: string | null
  collaborative: boolean
  public: boolean | null
  images: Array<{ url: string; height: number | null; width: number | null }>
  owner: PlaylistOwner
  items?: { href: string; total: number }
  tracks?: { href: string; total: number }
}

export type SourceType = 'liked' | 'playlist'
export type OutputMode = 'auto-create' | 'sort-into-existing'
export type ExistingPlaylistWriteMode = 'copy' | 'direct'

export interface SortRequest {
  sourceType: SourceType
  playlistId?: string
  outputMode: OutputMode
  editablePlaylistIds?: string[]
  existingPlaylistWriteMode?: ExistingPlaylistWriteMode
  createBackup?: boolean
  /**
   * Optional user-chosen names for safe copies in sort-into-existing copy
   * mode, keyed by selected original destination playlist IDs. Values are
   * trimmed, nonblank, and at most 100 characters. The backend falls back to
   * "Original — Spotify Sorter Copy" for missing entries.
   */
  safeCopyNames?: Record<string, string>
}

export interface Track {
  id: string
  name: string
  artists: string[]
  albumName: string
  spotifyUrl: string
}

export interface SortResultItem {
  bucket: string
  playlistId: string
  playlistName: string
  tracksAdded: number
  tracks: Track[]
  status: 'success' | 'failed'
  error?: string
}

export interface DestinationCopy {
  sourcePlaylistId: string
  sourcePlaylistName: string
  playlistId: string
  playlistName: string
  tracksCopied: number
  status: 'success' | 'failed'
  error?: string
}

export interface ExcludedPlaylist {
  id: string
  name: string
  reason: string
}

export interface SortBackup {
  playlistId: string
  playlistName: string
  tracksCopied: number
  status: 'success'
}

export type SortActionBucketStatus = 'applied' | 'undone'

export type SortActionTrack = Track

export interface SortActionDestination {
  playlistId: string
  playlistName: string
  baselineUris: string[]
  expectedSnapshotId: string
  bucketOrder: string[]
}

export interface SortActionBucket {
  bucket: string
  playlistId: string
  playlistName: string
  trackUris: string[]
  tracks: SortActionTrack[]
  status: SortActionBucketStatus
}

export interface SortAction {
  id: string
  spotifyId: string
  createdAt: string
  expiresAt: string
  destinations: SortActionDestination[]
  buckets: SortActionBucket[]
}

export interface SortResponse {
  results: SortResultItem[]
  excluded?: ExcludedPlaylist[]
  backup?: SortBackup
  destinationCopies?: DestinationCopy[]
  action?: SortAction
  actionWarning?: string
}

export interface UndoneDestination {
  playlistId: string
  playlistName: string
  undoneBuckets: string[]
  newSnapshotId: string
}

export interface FailedUndoDestination {
  playlistId: string
  playlistName: string
  buckets: string[]
  error: string
}

export interface UndoConflict {
  playlistId: string
  playlistName: string
  expectedSnapshotId: string
  actualSnapshotId: string
  buckets: string[]
}

export interface UndoConflictResponse {
  message: string
  conflicts: UndoConflict[]
}

export interface UndoResponse {
  status: 'complete' | 'partial'
  undoneDestinations: UndoneDestination[]
  failedDestinations?: FailedUndoDestination[]
  action: SortAction
  actionPersistWarning?: string
}
