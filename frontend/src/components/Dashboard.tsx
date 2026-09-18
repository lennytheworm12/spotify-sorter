import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ApiError,
  fetchLatestSortAction,
  fetchPlaylists,
  runSort,
  undoSortAction,
  userFacingErrorMessage,
} from '../api/client'
import type {
  CurrentUser,
  DestinationCopy,
  ExcludedPlaylist,
  ExistingPlaylistWriteMode,
  OutputMode,
  Playlist,
  SortBackup,
  SortRequest,
  SortResultItem,
  SortResponse,
  SourceType,
  UndoConflictResponse,
  UndoResponse,
} from '../api/types'
import { UndoPanel } from './UndoPanel'

function defaultCopyName(playlist: Playlist | undefined): string {
  return `${playlist?.name ?? 'Original'} — Spotify Sorter Copy`
}

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
  isSigningOut,
}: {
  user: CurrentUser
  onLogout: () => void
  logoutError: string | null
  isSigningOut: boolean
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
            <span className="header__session">
              Session remembered securely in this browser
            </span>
            {logoutError ? <span className="header__error">{logoutError}</span> : null}
          </div>
          <button
            className="button button--ghost"
            type="button"
            disabled={isSigningOut}
            onClick={onLogout}
          >
            {isSigningOut ? 'Signing out…' : 'Sign out'}
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
  message,
  onRetry,
}: {
  message: string
  onRetry: () => void
}) {
  return (
    <div className="workspace__status workspace__status--error" role="alert">
      <p>
        {message ||
          'We couldn’t load your playlists. Check that the backend is running, then try again.'}
      </p>
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
  spotifyId,
  disabled,
  onSourceChange,
  onPlaylistChange,
  onCreateBackupChange,
}: {
  sourceType: SourceType
  playlistId: string
  playlists: Playlist[]
  createBackup: boolean
  spotifyId: string
  disabled: boolean
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
            disabled={disabled}
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
            disabled={disabled}
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
              disabled={disabled}
              onChange={(event) => onPlaylistChange(event.target.value)}
            >
              <option value="" disabled>
                Select a playlist…
              </option>
              {playlists.map((playlist) => {
                const readable = isEditable(playlist, spotifyId)
                const countLabel =
                  trackCount(playlist) !== null ? ` · ${trackCount(playlist)} tracks` : ''
                return (
                  <option key={playlist.id} value={playlist.id} disabled={!readable}>
                    {playlist.name}
                    {countLabel}
                    {!readable ? ' · Track access unavailable' : ''}
                  </option>
                )
              })}
            </select>
          </div>
          {playlists.some((playlist) => !isEditable(playlist, spotifyId)) ? (
            <p className="group__note">
              Only playlists you own or collaborate on can be read as a source — Spotify hides
              track contents for other playlists, so those are disabled. Liked Songs is always
              available.
            </p>
          ) : null}
          <label className="checkbox checkbox--wide backup-option">
            <input
              type="checkbox"
              name="create-backup"
              checked={createBackup}
              disabled={disabled}
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
  writeMode,
  editablePlaylistIds,
  destinationIds,
  safeCopyNames,
  playlists,
  spotifyId,
  sourcePlaylistId,
  disabled,
  onOutputModeChange,
  onWriteModeChange,
  onEditableChange,
  onSafeCopyNameChange,
}: {
  outputMode: OutputMode
  writeMode: ExistingPlaylistWriteMode
  editablePlaylistIds: string[]
  destinationIds: string[]
  safeCopyNames: Record<string, string>
  playlists: Playlist[]
  spotifyId: string
  sourcePlaylistId: string | null
  disabled: boolean
  onOutputModeChange: (value: OutputMode) => void
  onWriteModeChange: (value: ExistingPlaylistWriteMode) => void
  onEditableChange: (playlistId: string, checked: boolean) => void
  onSafeCopyNameChange: (playlistId: string, value: string) => void
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
            disabled={disabled}
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
            disabled={disabled}
            onChange={() => onOutputModeChange('sort-into-existing')}
          />
          <span className="radio__label">Sort into my existing playlists</span>
        </label>
      </div>

      {outputMode === 'sort-into-existing' ? (
        <div className="group__sub">
          <fieldset className="safety">
            <legend>Destination safety</legend>
            <label className="radio">
              <input
                type="radio"
                name="destination-write-mode"
                value="copy"
                checked={writeMode === 'copy'}
                disabled={disabled}
                onChange={() => onWriteModeChange('copy')}
              />
              <span className="radio__body">
                <span className="radio__label">
                  Create safe copies <span className="pill">Recommended</span>
                </span>
                <span className="radio__meta">
                  Clones each selected playlist and adds tracks to the copies — your originals stay
                  unchanged.
                </span>
              </span>
            </label>
            <label className="radio radio--warning">
              <input
                type="radio"
                name="destination-write-mode"
                value="direct"
                checked={writeMode === 'direct'}
                disabled={disabled}
                onChange={() => onWriteModeChange('direct')}
              />
              <span className="radio__body">
                <span className="radio__label">Add directly to originals</span>
                <span className="radio__meta">
                  This changes the originals. A 24-hour undo is available only when tracking
                  succeeds and Spotify confirms the playlists have not changed since the sort.
                </span>
              </span>
            </label>
          </fieldset>
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
                    disabled={disabled || blocked}
                    checked={editablePlaylistIds.includes(playlist.id)}
                    onChange={(event) => onEditableChange(playlist.id, event.target.checked)}
                  />
                  <span className="checkbox__name">{playlist.name}</span>
                  <span className="checkbox__meta">{meta}</span>
                </label>
              )
            })}
          </div>
          {writeMode === 'copy' && destinationIds.length > 0 ? (
            <div className="copy-names">
              <h3 className="copy-names__title">Name safe copies</h3>
              <p className="copy-names__note">
                Each safe copy is a new private playlist. Edit the names below —
                your originals stay unchanged.
              </p>
              <div className="copy-names__list">
                {destinationIds.map((playlistId) => {
                  const playlist = playlists.find((item) => item.id === playlistId)
                  const value = safeCopyNames[playlistId] ?? defaultCopyName(playlist)
                  const trimmed = value.trim()
                  const invalid = trimmed.length === 0 || trimmed.length > 100
                  const inputId = `safe-copy-name-${playlistId}`
                  const errorId = `${inputId}-error`
                  return (
                    <div
                      className={`copy-name${invalid ? ' copy-name--invalid' : ''}`}
                      key={playlistId}
                    >
                      <label className="copy-name__label" htmlFor={inputId}>
                        {playlist?.name ?? 'Selected playlist'}
                      </label>
                      <input
                        id={inputId}
                        className="copy-name__input"
                        type="text"
                        value={value}
                        maxLength={100}
                        disabled={disabled}
                        onChange={(event) =>
                          onSafeCopyNameChange(playlistId, event.target.value)
                        }
                        aria-invalid={invalid || undefined}
                        aria-describedby={invalid ? errorId : undefined}
                      />
                      {invalid ? (
                        <p className="copy-name__error" id={errorId}>
                          {trimmed.length === 0
                            ? 'Enter a name for this safe copy.'
                            : 'Keep the name to 100 characters or fewer.'}
                        </p>
                      ) : null}
                    </div>
                  )
                })}
              </div>
            </div>
          ) : null}
          {unavailable.length > 0 ? (
            <p className="group__note">
              {unavailable.length} playlist{unavailable.length === 1 ? '' : 's'} shown{' '}
              {unavailable.length === 1 ? 'is' : 'are'} disabled — only playlists you own or
              collaborate on can receive tracks. The source playlist is shown above but never used
              as a destination.
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
    response: SortResponse,
  ) => void
}) {
  const [sourceType, setSourceType] = useState<SourceType>('liked')
  const [playlistId, setPlaylistId] = useState('')
  const [createBackup, setCreateBackup] = useState(true)
  const [outputMode, setOutputMode] = useState<OutputMode>('auto-create')
  const [writeMode, setWriteMode] = useState<ExistingPlaylistWriteMode>('copy')
  const [editablePlaylistIds, setEditablePlaylistIds] = useState<string[]>([])
  const [safeCopyNames, setSafeCopyNames] = useState<Record<string, string>>({})
  const [isSorting, setIsSorting] = useState(false)
  const [sortError, setSortError] = useState<string | null>(null)
  const [progressStage, setProgressStage] = useState<'analyzing' | 'adding'>('analyzing')

  useEffect(() => {
    if (!isSorting) {
      setProgressStage('analyzing')
      return
    }
    setProgressStage('analyzing')
    const timer = window.setTimeout(() => setProgressStage('adding'), 5000)
    return () => window.clearTimeout(timer)
  }, [isSorting])

  useEffect(() => {
    if (sourceType !== 'playlist' || playlistId === '') {
      return
    }
    const selected = playlists.find((playlist) => playlist.id === playlistId)
    if (!selected || !isEditable(selected, spotifyId)) {
      setPlaylistId('')
      setEditablePlaylistIds((current) => current.filter((id) => id !== playlistId))
    }
  }, [playlists, playlistId, sourceType, spotifyId])

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

  const copyNamesValid =
    outputMode !== 'sort-into-existing' ||
    writeMode !== 'copy' ||
    destinationIds.every((id) => {
      const playlist = playlists.find((item) => item.id === id)
      const trimmed = (safeCopyNames[id] ?? defaultCopyName(playlist)).trim()
      return trimmed.length > 0 && trimmed.length <= 100
    })

  const canSubmit = ready && copyNamesValid && !isSorting

  function handleSourceChange(value: SourceType) {
    setSourceType(value)
    if (value === 'liked') {
      setPlaylistId('')
    }
    setEditablePlaylistIds((current) => current.filter((id) => id !== playlistId))
    setSafeCopyNames((current) => {
      if (!(playlistId in current)) {
        return current
      }
      const next = { ...current }
      delete next[playlistId]
      return next
    })
  }

  function handlePlaylistChange(value: string) {
    setEditablePlaylistIds((current) =>
      current.filter((id) => id !== playlistId && id !== value),
    )
    setPlaylistId(value)
    setSafeCopyNames((current) => {
      if (!(playlistId in current) && !(value in current)) {
        return current
      }
      const next = { ...current }
      delete next[playlistId]
      delete next[value]
      return next
    })
  }

  function handleEditableChange(playlistIdToToggle: string, checked: boolean) {
    setEditablePlaylistIds((current) =>
      checked
        ? [...current, playlistIdToToggle]
        : current.filter((id) => id !== playlistIdToToggle),
    )
    if (!checked) {
      setSafeCopyNames((current) => {
        if (!(playlistIdToToggle in current)) {
          return current
        }
        const next = { ...current }
        delete next[playlistIdToToggle]
        return next
      })
    }
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!ready || isSorting) {
      return
    }
    setIsSorting(true)
    setSortError(null)
    onSortStart()

    const copyNamePayload: Record<string, string> = {}
    for (const id of destinationIds) {
      const playlist = playlists.find((item) => item.id === id)
      copyNamePayload[id] = (safeCopyNames[id] ?? defaultCopyName(playlist)).trim()
    }

    const payload: SortRequest = {
      sourceType,
      outputMode,
      ...(sourceType === 'playlist' && playlistId ? { playlistId } : {}),
      ...(sourceType === 'playlist' ? { createBackup } : {}),
      ...(outputMode === 'sort-into-existing'
        ? {
            editablePlaylistIds: destinationIds,
            existingPlaylistWriteMode: writeMode,
            ...(writeMode === 'copy' ? { safeCopyNames: copyNamePayload } : {}),
          }
        : {}),
    }

    try {
      const response = await runSort(payload)
      onSortSuccess(response)
    } catch (error) {
      setSortError(
        userFacingErrorMessage(
          error,
          'The sort didn’t complete. Check that the backend is running, then try again.',
        ),
      )
    } finally {
      setIsSorting(false)
    }
  }

  const progressCopy =
    progressStage === 'adding'
      ? 'Adding tracks in paced batches…'
      : outputMode === 'sort-into-existing' && writeMode === 'copy'
        ? 'Analyzing genres and preparing safe copies…'
        : 'Analyzing genres…'

  return (
    <form
      id="setup"
      className={`workspace${isSorting ? ' workspace--busy' : ''}`}
      onSubmit={handleSubmit}
    >
      <SourceFieldset
        sourceType={sourceType}
        playlistId={playlistId}
        playlists={playlists}
        createBackup={createBackup}
        spotifyId={spotifyId}
        disabled={isSorting}
        onSourceChange={(value) => {
          handleSourceChange(value)
        }}
        onPlaylistChange={handlePlaylistChange}
        onCreateBackupChange={setCreateBackup}
      />

      <OutputFieldset
        outputMode={outputMode}
        writeMode={writeMode}
        editablePlaylistIds={editablePlaylistIds}
        destinationIds={destinationIds}
        safeCopyNames={safeCopyNames}
        playlists={playlists}
        spotifyId={spotifyId}
        sourcePlaylistId={sourceType === 'playlist' ? playlistId || null : null}
        disabled={isSorting}
        onOutputModeChange={(value) => {
          setOutputMode(value)
          if (value === 'auto-create') {
            setEditablePlaylistIds([])
            setSafeCopyNames({})
          }
        }}
        onWriteModeChange={setWriteMode}
        onEditableChange={handleEditableChange}
        onSafeCopyNameChange={(playlistId, value) =>
          setSafeCopyNames((current) => ({ ...current, [playlistId]: value }))
        }
      />

      {sortError ? (
        <p className="form-error" role="alert">
          {sortError}
        </p>
      ) : null}

      {isSorting ? (
        <div className="sort-progress" role="status" aria-live="polite">
          <div
            className="sort-progress__bar"
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuetext={progressCopy}
          >
            <span className="sort-progress__fill" aria-hidden="true" />
          </div>
          <p className="sort-progress__stage">{progressCopy}</p>
          <p className="sort-progress__note">Large playlists may take a few minutes.</p>
        </div>
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
  destinationCopies,
  undoneBuckets,
}: {
  results: SortResultItem[] | null
  excluded: ExcludedPlaylist[] | null
  backup: SortBackup | null
  destinationCopies: DestinationCopy[] | null
  undoneBuckets: Set<string>
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
  const uniqueCopies = (destinationCopies ?? []).filter(
    (copy, index, all) => all.findIndex((other) => other.playlistId === copy.playlistId) === index,
  )

  return (
    <section className="ledger ledger--reveal" id="results" aria-live="polite">
      <div className="ledger__heading">
        <h2>Results</h2>
        <p>
          {results.length === 0
            ? 'No tracks to organize'
            : `${successful.length} bucket${successful.length === 1 ? '' : 's'} updated · ${tracksAdded} track${tracksAdded === 1 ? '' : 's'} added`}
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

      {uniqueCopies.length > 0 ? (
        <div className="ledger__copies">
          <h3>Destination safe copies</h3>
          <p className="ledger__copies-note">
            Source backups protect the source playlist; destination safe copies protect the
            playlists you selected as targets.
          </p>
          <ul className="ledger__copy-list">
            {uniqueCopies.map((copy) => (
              <li
                className={`ledger__copy ledger__copy--${copy.status}`}
                key={copy.playlistId}
              >
                <div className="ledger__bucket">
                  <span className="ledger__status" aria-hidden="true" />
                  {copy.playlistName || 'Copy'}
                </div>
                <div className="ledger__detail">
                  <span className="ledger__count">Copy of {copy.sourcePlaylistName}</span>
                  <span className="ledger__count">
                    Base tracks copied: {copy.tracksCopied}
                  </span>
                  {copy.error ? (
                    <span className="ledger__error">{copy.error}</span>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
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
          {results.map((result) => {
            const tracks = result.tracks ?? []
            const undone =
              result.status === 'success' && undoneBuckets.has(result.bucket)
            return (
              <li
                className={`ledger__row ledger__row--${result.status}${undone ? ' ledger__row--undone' : ''}`}
                key={result.bucket}
              >
                <details className="ledger__details">
                  <summary className="ledger__summary">
                    <span className="ledger__bucket">
                      <span className="ledger__status" aria-hidden="true" />
                      {result.bucket}
                    </span>
                    <span className="ledger__detail">
                      {result.status === 'success' ? (
                        <>
                          <span className="ledger__dest">
                            {result.playlistName || 'New playlist'}
                          </span>
                          <span className="ledger__count">
                            {undone
                              ? `Undone · ${result.tracksAdded} track${result.tracksAdded === 1 ? '' : 's'} removed`
                              : `${result.tracksAdded} track${result.tracksAdded === 1 ? '' : 's'} added`}
                            {tracks.length > 0
                              ? ` · ${tracks.length} candidate${tracks.length === 1 ? '' : 's'}`
                              : ''}
                          </span>
                        </>
                      ) : (
                        <span className="ledger__error">
                          {result.error ?? 'Failed to write tracks'}
                        </span>
                      )}
                    </span>
                  </summary>
                  <div className="ledger__tracks">
                    {tracks.length > 0 ? (
                      <ul className="ledger__tracks-list">
                        {tracks.map((track, trackIndex) => (
                          <li className="ledger__track" key={track.id || `${result.bucket}-${trackIndex}`}>
                            <span className="ledger__track-name">{track.name}</span>
                            <span className="ledger__track-meta">
                              {track.artists.join(', ')}
                              {track.albumName ? ` · ${track.albumName}` : ''}
                            </span>
                            {track.spotifyUrl ? (
                              <a
                                className="ledger__track-link"
                                href={track.spotifyUrl}
                                target="_blank"
                                rel="noreferrer"
                              >
                                Open on Spotify
                              </a>
                            ) : null}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="ledger__tracks-empty">
                        No candidate tracks were reported for this bucket.
                      </p>
                    )}
                  </div>
                </details>
              </li>
            )
          })}
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
  isSigningOut,
}: {
  user: CurrentUser
  onLogout: () => void
  isSigningOut: boolean
}) {
  const queryClient = useQueryClient()
  const [logoutError, setLogoutError] = useState<string | null>(null)
  const [results, setResults] = useState<SortResultItem[] | null>(null)
  const [excluded, setExcluded] = useState<ExcludedPlaylist[] | null>(null)
  const [backup, setBackup] = useState<SortBackup | null>(null)
  const [destinationCopies, setDestinationCopies] = useState<DestinationCopy[] | null>(null)
  const [sortActionWarning, setSortActionWarning] = useState<string | null>(null)
  const [selectedUndoBuckets, setSelectedUndoBuckets] = useState<string[]>([])
  const [lastUndoResponse, setLastUndoResponse] = useState<UndoResponse | null>(null)
  const [undoConflict, setUndoConflict] = useState<UndoConflictResponse | null>(null)
  const [undoError, setUndoError] = useState<string | null>(null)

  const playlistsQuery = useQuery({
    queryKey: ['playlists', user.spotifyId],
    queryFn: fetchPlaylists,
  })

  const latestActionQuery = useQuery({
    queryKey: ['latest-sort-action', user.spotifyId],
    queryFn: fetchLatestSortAction,
    retry: false,
  })

  const undoMutation = useMutation({
    mutationFn: ({ actionId, buckets }: { actionId: string; buckets: string[] }) =>
      undoSortAction(actionId, buckets),
    onSuccess: (response) => {
      queryClient.setQueryData(['latest-sort-action', user.spotifyId], response.action)
      setSelectedUndoBuckets([])
      setLastUndoResponse(response)
      setUndoConflict(null)
      setUndoError(null)
    },
    onError: (error: Error) => {
      setLastUndoResponse(null)
      setUndoConflict(null)
      setUndoError(null)
      if (error instanceof ApiError && error.status === 409) {
        setUndoConflict(error.body as UndoConflictResponse)
      } else {
        setUndoError(
          error.message ||
            'The undo didn’t complete. Check that the backend is running, then try again.',
        )
      }
    },
  })

  const latestAction = latestActionQuery.data ?? null
  const undoneBucketNames = useMemo(
    () =>
      new Set(
        latestAction
          ? latestAction.buckets
              .filter((bucket) => bucket.status === 'undone')
              .map((bucket) => bucket.bucket)
          : [],
      ),
    [latestAction],
  )

  useEffect(() => {
    if (results) {
      const resultsSection = document.getElementById('results')
      resultsSection?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [results])

  // Normalize selections: dedupe bucket names and drop any that were undone or
  // disappeared when the tracked action data changes. Deriving at render time
  // guarantees the undo payload can never include stale names.
  const normalizedSelectedUndoBuckets = useMemo(() => {
    if (selectedUndoBuckets.length === 0) {
      return selectedUndoBuckets
    }
    const appliedNames = new Set(
      latestAction
        ? latestAction.buckets
            .filter((bucket) => bucket.status === 'applied')
            .map((bucket) => bucket.bucket)
        : [],
    )
    return Array.from(new Set(selectedUndoBuckets)).filter((name) =>
      appliedNames.has(name),
    )
  }, [selectedUndoBuckets, latestAction])

  const playlists = playlistsQuery.data ?? []

  return (
    <div className="app">
      <DashboardHeader
        user={user}
        isSigningOut={isSigningOut}
        onLogout={async () => {
          if (isSigningOut) {
            return
          }
          setLogoutError(null)
          try {
            await onLogout()
          } catch (error) {
            setLogoutError(
              error instanceof Error && error.message
                ? error.message
                : 'Sign out didn’t complete. Please try again.',
            )
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
          <PlaylistLoadError
            message={userFacingErrorMessage(
              playlistsQuery.error,
              'We couldn’t load your playlists. Check that the backend is running, then try again.',
            )}
            onRetry={() => void playlistsQuery.refetch()}
          />
        ) : null}

        {playlistsQuery.isSuccess ? (
          <>
            <nav className="section-nav" aria-label="On this page">
              <a className="section-nav__link" href="#setup">
                Setup
              </a>
              <a className="section-nav__link" href="#results">
                Results
              </a>
              {latestAction ? (
                <a className="section-nav__link" href="#undo">
                  Undo
                </a>
              ) : null}
            </nav>
            <div className="dashboard__grid">
              <SortWorkspace
                playlists={playlists}
                spotifyId={user.spotifyId}
                onSortStart={() => {
                  setResults(null)
                  setExcluded(null)
                  setBackup(null)
                  setDestinationCopies(null)
                  setSortActionWarning(null)
                  setSelectedUndoBuckets([])
                  setLastUndoResponse(null)
                  setUndoConflict(null)
                  setUndoError(null)
                }}
                onSortSuccess={(response) => {
                  setResults(response.results)
                  setExcluded(response.excluded ?? null)
                  setBackup(response.backup ?? null)
                  setDestinationCopies(response.destinationCopies ?? null)
                  setSortActionWarning(response.actionWarning ?? null)
                  if (response.action) {
                    queryClient.setQueryData(
                      ['latest-sort-action', user.spotifyId],
                      response.action,
                    )
                    setSelectedUndoBuckets([])
                  }
                  void playlistsQuery.refetch()
                }}
              />
              <div className="dashboard__side">
                {latestActionQuery.isError ? (
                  <div className="undo-history-warning" role="status">
                    <p>Undo history couldn’t be loaded right now.</p>
                    <button
                      className="button button--ghost"
                      type="button"
                      onClick={() => void latestActionQuery.refetch()}
                    >
                      Retry
                    </button>
                  </div>
                ) : null}
                {sortActionWarning ? (
                  <div className="action-warning" role="alert">
                    <p className="action-warning__title">
                      Playlist changes succeeded, but this run can’t be undone.
                    </p>
                    <p className="action-warning__detail">
                      {sortActionWarning} An older tracked action may still appear below and remains
                      protected by Spotify’s snapshot check.
                    </p>
                  </div>
                ) : null}
                {latestAction ? (
                  <UndoPanel
                    action={latestAction}
                    isUndoing={undoMutation.isPending}
                    selectedBuckets={normalizedSelectedUndoBuckets}
                    onSelectionChange={setSelectedUndoBuckets}
                    onUndo={(buckets) => {
                      undoMutation.mutate({
                        actionId: latestAction.id,
                        buckets,
                      })
                    }}
                    lastResponse={lastUndoResponse}
                    conflict={undoConflict}
                    undoError={undoError}
                  />
                ) : null}
                <ResultsLedger
                  results={results}
                  excluded={excluded}
                  backup={backup}
                  destinationCopies={destinationCopies}
                  undoneBuckets={undoneBucketNames}
                />
              </div>
            </div>
          </>
        ) : null}
      </main>
    </div>
  )
}
