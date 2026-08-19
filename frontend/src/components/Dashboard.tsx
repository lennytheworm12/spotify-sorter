import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchPlaylists, runSort } from '../api/client'
import type {
  CurrentUser,
  ExcludedPlaylist,
  OutputMode,
  Playlist,
  SortBackup,
  SortRequest,
  SortResultItem,
  SourceType,
} from '../api/types'

function trackCount(playlist: Playlist): number | null {
  const total = playlist.items?.total ?? playlist.tracks?.total
  return typeof total === 'number' ? total : null
}

function isEditable(playlist: Playlist, spotifyId: string): boolean {
  return playlist.collaborative || playlist.owner.id === spotifyId
}

function Avatar({
  user,
}: {
  user: CurrentUser
}) {
  return user.profilePictureUrl ? (
    <img className="header__avatar" src={user.profilePictureUrl} alt="" />
  ) : (
    <span className="header__avatar header__avatar--fallback" aria-hidden="true">
      {(user.displayName ?? user.spotifyId).slice(0, 1).toUpperCase()}
    </span>
  )
}

function DashboardHeader({
  user,
  onLogout,
  logoutError,
}: {
  user: CurrentUser
  onLogout: () => void
  logoutError: string | null
}) {
  return (
    <header className="header">
      <div className="header__inner">
        <p className="header__brand">
          <span className="connect__dot" aria-hidden="true" />
          Spotify Sorter
        </p>
        <div className="header__account">
          <Avatar user={user} />
          <div className="header__meta">
            <span className="header__name">{user.displayName ?? user.spotifyId}</span>
            <span className="header__status">Connected</span>
            {logoutError ? <span className="header__error">{logoutError}</span> : null}
          </div>
          <button className="button button--ghost" type="button" onClick={onLogout}>
            Sign out
          </button>
        </div>
      </div>
    </header>
  )
}

function LoadingList() {
  return (
    <div className="workspace__status" role="status">
      <span className="spinner" aria-hidden="true" />
      <p>Loading your playlists…</p>
    </div>
  )
}

function PlaylistLoadError({
  onRetry,
}: {
  onRetry: () => void
}) {
  return (
    <div className="workspace__status workspace__status--error" role="alert">
      <p>We couldn’t load your playlists. Check that the backend is running, then try again.</p>
      <button className="button button--ghost" type="button" onClick={onRetry}>
        Retry
      </button>
    </div>
  )
}

function SourceFieldset({
  sourceType,
  playlistId,
  playlists,
  createBackup,
  onSourceChange,
  onPlaylistChange,
  onCreateBackupChange,
}: {
  sourceType: SourceType
  playlistId: string
  playlists: Playlist[]
  createBackup: boolean
  onSourceChange: (value: SourceType) => void
  onPlaylistChange: (value: string) => void
  onCreateBackupChange: (checked: boolean) => void
}) {
  return (
    <fieldset className="group">
      <legend>Source</legend>
      <div className="radio-row">
        <label className="radio">
          <input
            type="radio"
            name="source"
            value="liked"
            checked={sourceType === 'liked'}
            onChange={() => onSourceChange('liked')}
          />
          <span className="radio__label">Liked Songs</span>
        </label>
        <label className="radio">
          <input
            type="radio"
            name="source"
            value="playlist"
            checked={sourceType === 'playlist'}
            onChange={() => onSourceChange('playlist')}
          />
          <span className="radio__label">Existing Playlist</span>
        </label>
      </div>

      {sourceType === 'playlist' ? (
        <div className="group__sub">
          <label className="select-label" htmlFor="source-playlist">
            Choose a playlist to organize
          </label>
          <div className="select-wrap">
            <select
              id="source-playlist"
              className="select"
              value={playlistId}
              onChange={(event) => onPlaylistChange(event.target.value)}
            >
              <option value="" disabled>
                Select a playlist…
              </option>
              {playlists.map((playlist) => (
                <option key={playlist.id} value={playlist.id}>
                  {playlist.name}
                  {trackCount(playlist) !== null ? ` · ${trackCount(playlist)} tracks` : ''}
                </option>
              ))}
            </select>
          </div>
          <label className="checkbox checkbox--wide backup-option">
            <input
              type="checkbox"
              name="create-backup"
              checked={createBackup}
              onChange={(event) => onCreateBackupChange(event.target.checked)}
            />
            <span className="checkbox__name">Create a backup copy first</span>
            <span className="checkbox__meta">
              Copies every copyable track into a private playlist before organizing. The source is
              never modified.
            </span>
          </label>
        </div>
      ) : null}
    </fieldset>
  )
}

function OutputFieldset({
  outputMode,
  editablePlaylistIds,
  playlists,
  spotifyId,
  sourcePlaylistId,
  onOutputModeChange,
  onEditableChange,
}: {
  outputMode: OutputMode
  editablePlaylistIds: string[]
  playlists: Playlist[]
  spotifyId: string
  sourcePlaylistId: string | null
  onOutputModeChange: (value: OutputMode) => void
  onEditableChange: (playlistId: string, checked: boolean) => void
}) {
  const unavailable = playlists.filter(
    (playlist) => !isEditable(playlist, spotifyId) && playlist.id !== sourcePlaylistId,
  )

  return (
    <fieldset className="group">
      <legend>Output</legend>
      <div className="radio-row">
        <label className="radio">
          <input
            type="radio"
            name="output"
            value="auto-create"
            checked={outputMode === 'auto-create'}
            onChange={() => onOutputModeChange('auto-create')}
          />
          <span className="radio__label">Create genre playlists automatically</span>
        </label>
        <label className="radio">
          <input
            type="radio"
            name="output"
            value="sort-into-existing"
            checked={outputMode === 'sort-into-existing'}
            onChange={() => onOutputModeChange('sort-into-existing')}
          />
          <span className="radio__label">Sort into my existing playlists</span>
        </label>
      </div>

      {outputMode === 'sort-into-existing' ? (
        <div className="group__sub">
          <p className="group__hint">
            Only playlists you own (or can collaborate on) can receive tracks — the source playlist
            is never a destination. Pick at least one.
          </p>
          <div className="checkbox-list">
            {playlists.map((playlist) => {
              const editable = isEditable(playlist, spotifyId)
              const isSource = sourcePlaylistId === playlist.id
              const blocked = !editable || isSource
              const meta = [
                trackCount(playlist) !== null ? `${trackCount(playlist)} tracks` : '',
                isSource ? 'Source · Never modified' : editable ? '' : 'Not editable',
              ]
                .filter(Boolean)
                .join(' · ')
              return (
                <label
                  key={playlist.id}
                  className={`checkbox${blocked ? ' checkbox--disabled' : ''}${isSource ? ' checkbox--source' : ''}`}
                >
                  <input
                    type="checkbox"
                    disabled={blocked}
                    checked={editablePlaylistIds.includes(playlist.id)}
                    onChange={(event) => onEditableChange(playlist.id, event.target.checked)}
                  />
                  <span className="checkbox__name">{playlist.name}</span>
                  <span className="checkbox__meta">{meta}</span>
                </label>
              )
            })}
          </div>
          {unavailable.length > 0 ? (
            <p className="group__note">
              {unavailable.length} playlist{unavailable.length === 1 ? '' : 's'} hidden from
              selection {unavailable.length === 1 ? 'because' : 'because they’re'} not owned by you
              or collaborative. The source playlist is shown above but never used as a destination.
            </p>
          ) : null}
        </div>
      ) : null}
    </fieldset>
  )
}

function SortWorkspace({
  playlists,
  spotifyId,
  onSortStart,
  onSortSuccess,
}: {
  playlists: Playlist[]
  spotifyId: string
  onSortStart: () => void
  onSortSuccess: (
    results: SortResultItem[],
    excluded?: ExcludedPlaylist[],
    backup?: SortBackup,
  ) => void
}) {
  const [sourceType, setSourceType] = useState<SourceType>('liked')
  const [playlistId, setPlaylistId] = useState('')
  const [createBackup, setCreateBackup] = useState(true)
  const [outputMode, setOutputMode] = useState<OutputMode>('auto-create')
  const [editablePlaylistIds, setEditablePlaylistIds] = useState<string[]>([])
  const [isSorting, setIsSorting] = useState(false)
  const [sortError, setSortError] = useState<string | null>(null)

  const editableIds = useMemo(
    () => playlists.filter((playlist) => isEditable(playlist, spotifyId)).map((playlist) => playlist.id),
    [playlists, spotifyId],
  )

  const destinationIds = useMemo(
    () =>
      outputMode === 'sort-into-existing'
        ? editablePlaylistIds.filter((id) => id !== playlistId && editableIds.includes(id))
        : [],
    [editablePlaylistIds, editableIds, playlistId, outputMode],
  )

  const ready =
    (sourceType === 'liked' || playlistId !== '') &&
    (outputMode === 'auto-create' || destinationIds.length > 0)

  const canSubmit = ready && !isSorting

  function handleSourceChange(value: SourceType) {
    setSourceType(value)
    if (value === 'liked') {
      setPlaylistId('')
    }
    setEditablePlaylistIds((current) => current.filter((id) => id !== playlistId))
  }

  function handlePlaylistChange(value: string) {
    setEditablePlaylistIds((current) =>
      current.filter((id) => id !== playlistId && id !== value),
    )
    setPlaylistId(value)
  }

  function handleEditableChange(playlistIdToToggle: string, checked: boolean) {
    setEditablePlaylistIds((current) =>
      checked
        ? [...current, playlistIdToToggle]
        : current.filter((id) => id !== playlistIdToToggle),
    )
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!ready || isSorting) {
      return
    }
    setIsSorting(true)
    setSortError(null)
    onSortStart()

    const payload: SortRequest = {
      sourceType,
      outputMode,
      ...(sourceType === 'playlist' && playlistId ? { playlistId } : {}),
      ...(sourceType === 'playlist' ? { createBackup } : {}),
      ...(outputMode === 'sort-into-existing'
        ? {
            editablePlaylistIds: destinationIds,
          }
        : {}),
    }

    try {
      const response = await runSort(payload)
      onSortSuccess(response.results, response.excluded, response.backup)
    } catch (error) {
      setSortError(
        error instanceof Error
          ? error.message
          : 'The sort didn’t complete. Check that the backend is running, then try again.',
      )
    } finally {
      setIsSorting(false)
    }
  }

  return (
    <form className="workspace" onSubmit={handleSubmit}>
      <SourceFieldset
        sourceType={sourceType}
        playlistId={playlistId}
        playlists={playlists}
        createBackup={createBackup}
        onSourceChange={(value) => {
          handleSourceChange(value)
        }}
        onPlaylistChange={handlePlaylistChange}
        onCreateBackupChange={setCreateBackup}
      />

      <OutputFieldset
        outputMode={outputMode}
        editablePlaylistIds={editablePlaylistIds}
        playlists={playlists}
        spotifyId={spotifyId}
        sourcePlaylistId={sourceType === 'playlist' ? playlistId || null : null}
        onOutputModeChange={(value) => {
          setOutputMode(value)
          if (value === 'auto-create') {
            setEditablePlaylistIds([])
          }
        }}
        onEditableChange={handleEditableChange}
      />

      {sortError ? (
        <p className="form-error" role="alert">
          {sortError}
        </p>
      ) : null}

      <button className="button button--primary button--organize" type="submit" disabled={!canSubmit}>
        {isSorting ? 'Organizing…' : 'Organize Music'}
      </button>
    </form>
  )
}

function ResultsLedger({
  results,
  excluded,
  backup,
}: {
  results: SortResultItem[] | null
  excluded: ExcludedPlaylist[] | null
  backup: SortBackup | null
}) {
  if (!results) {
    return (
      <section className="ledger" id="results">
        <h2>Results</h2>
        <div className="ledger__empty">
          <p>Your organized buckets will appear here after a run.</p>
        </div>
      </section>
    )
  }

  const successful = results.filter((result) => result.status === 'success')
  const failed = results.filter((result) => result.status === 'failed')
  const tracksAdded = successful.reduce((sum, result) => sum + result.tracksAdded, 0)

  return (
    <section className="ledger ledger--reveal" id="results" aria-live="polite">
      <div className="ledger__heading">
        <h2>Results</h2>
        <p>
          {results.length === 0
            ? 'No tracks to organize'
            : `${successful.length} playlist${successful.length === 1 ? '' : 's'} updated · ${tracksAdded} track${tracksAdded === 1 ? '' : 's'} added`}
        </p>
      </div>

      {backup ? (
        <div className="ledger__backup" role="status">
          <div className="ledger__bucket">
            <span className="ledger__status" aria-hidden="true" />
            Backup created
          </div>
          <div className="ledger__detail">
            <span className="ledger__dest">{backup.playlistName}</span>
            <span className="ledger__count">
              {backup.tracksCopied} track{backup.tracksCopied === 1 ? '' : 's'} copied
            </span>
          </div>
        </div>
      ) : null}

      {results.length === 0 ? (
        <div className="ledger__empty">
          <p>
            Your library is already sorted — there were no tracks to organize in the selected
            source.
          </p>
        </div>
      ) : (
        <ul className="ledger__list">
          {results.map((result) => (
            <li className={`ledger__row ledger__row--${result.status}`} key={result.bucket}>
              <div className="ledger__bucket">
                <span className="ledger__status" aria-hidden="true" />
                {result.bucket}
              </div>
              <div className="ledger__detail">
                {result.status === 'success' ? (
                  <>
                    <span className="ledger__dest">
                      {result.playlistName || 'New playlist'}
                    </span>
                    <span className="ledger__count">
                      {result.tracksAdded} track{result.tracksAdded === 1 ? '' : 's'} added
                    </span>
                  </>
                ) : (
                  <span className="ledger__error">{result.error ?? 'Failed to write tracks'}</span>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      {failed.length > 0 ? (
        <p className="ledger__partial-note">
          {successful.length > 0
            ? 'Some buckets succeeded and some failed — successful results above are saved.'
            : 'No buckets could be written. Check the errors above and try again.'}
        </p>
      ) : null}

      {excluded && excluded.length > 0 ? (
        <div className="ledger__excluded">
          <h3>Excluded playlists</h3>
          <ul>
            {excluded.map((playlist) => (
              <li key={playlist.id}>
                <span>{playlist.name}</span>
                <span>{playlist.reason}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  )
}

export function Dashboard({
  user,
  onLogout,
}: {
  user: CurrentUser
  onLogout: () => void
}) {
  const [logoutError, setLogoutError] = useState<string | null>(null)
  const [results, setResults] = useState<SortResultItem[] | null>(null)
  const [excluded, setExcluded] = useState<ExcludedPlaylist[] | null>(null)
  const [backup, setBackup] = useState<SortBackup | null>(null)

  const playlistsQuery = useQuery({
    queryKey: ['playlists'],
    queryFn: fetchPlaylists,
  })

  useEffect(() => {
    if (results) {
      const resultsSection = document.getElementById('results')
      resultsSection?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [results])

  const playlists = playlistsQuery.data ?? []

  return (
    <div className="app">
      <DashboardHeader
        user={user}
        onLogout={async () => {
          setLogoutError(null)
          try {
            await onLogout()
          } catch {
            setLogoutError('Sign out didn’t complete. Please try again.')
          }
        }}
        logoutError={logoutError}
      />

      <main className="dashboard">
        <div className="dashboard__intro">
          <h1>Organize your library</h1>
          <p>
            Pick a source, choose where tracks go, and we’ll copy tracks into genre buckets. Your
            source playlist is never modified.
          </p>
        </div>

        {playlistsQuery.isPending ? <LoadingList /> : null}
        {playlistsQuery.isError ? (
          <PlaylistLoadError onRetry={() => void playlistsQuery.refetch()} />
        ) : null}

        {playlistsQuery.isSuccess ? (
          <div className="dashboard__grid">
            <SortWorkspace
              playlists={playlists}
              spotifyId={user.spotifyId}
              onSortStart={() => {
                setResults(null)
                setExcluded(null)
                setBackup(null)
              }}
              onSortSuccess={(nextResults, nextExcluded, nextBackup) => {
                setResults(nextResults)
                setExcluded(nextExcluded ?? null)
                setBackup(nextBackup ?? null)
                void playlistsQuery.refetch()
              }}
            />
            <ResultsLedger results={results} excluded={excluded} backup={backup} />
          </div>
        ) : null}
      </main>
    </div>
  )
}
