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

export interface SortRequest {
  sourceType: SourceType
  playlistId?: string
  outputMode: OutputMode
  editablePlaylistIds?: string[]
  createBackup?: boolean
}

export interface SortResultItem {
  bucket: string
  playlistId: string
  playlistName: string
  tracksAdded: number
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

export interface SortResponse {
  results: SortResultItem[]
  excluded?: ExcludedPlaylist[]
  backup?: SortBackup
}
