import { useState } from 'react'
import type {
  SortAction,
  SortActionBucket,
  UndoConflictResponse,
  UndoResponse,
} from '../api/types'

function formatDateTime(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) {
    return ''
  }
  return date.toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
}

function bucketInputId(actionId: string, bucketName: string): string {
  return `undo-bucket-${actionId}-${bucketName.replace(/\s+/g, '-')}`
}

interface UndoPanelProps {
  action: SortAction | null
  isUndoing: boolean
  selectedBuckets: string[]
  onSelectionChange: (buckets: string[]) => void
  onUndo: (buckets: string[]) => void
  lastResponse: UndoResponse | null
  conflict: UndoConflictResponse | null
  undoError: string | null
}

function BucketTracks({ bucket }: { bucket: SortActionBucket }) {
  if (bucket.tracks.length === 0) {
    return (
      <p className="undo__tracks-empty">
        No candidate tracks were reported for this bucket.
      </p>
    )
  }

  return (
    <ul className="undo__track-list">
      {bucket.tracks.map((track, trackIndex) => (
        <li className="undo__track" key={track.id || `${bucket.bucket}-${trackIndex}`}>
          <div className="undo__track-info">
            <span className="undo__track-name">{track.name}</span>
            <span className="undo__track-meta">
              {track.artists.join(', ')}
              {track.albumName ? ` · ${track.albumName}` : ''}
            </span>
          </div>
          {track.spotifyUrl ? (
            <a
              className="undo__track-link"
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
  )
}

export function UndoPanel({
  action,
  isUndoing,
  selectedBuckets,
  onSelectionChange,
  onUndo,
  lastResponse,
  conflict,
  undoError,
}: UndoPanelProps) {
  const [renderNow] = useState(() => Date.now())

  if (!action) {
    return null
  }

  if (new Date(action.expiresAt).getTime() <= renderNow) {
    return (
      <section className="undo" id="undo" aria-labelledby="undo-heading">
        <h2 id="undo-heading">Undo last action</h2>
        <p className="undo__empty">
          No recent undo available — the 24-hour recovery window has ended.
        </p>
      </section>
    )
  }

  const bucketsByName = new Map(action.buckets.map((bucket) => [bucket.bucket, bucket]))
  const groups = action.destinations.map((destination) => ({
    playlistId: destination.playlistId,
    playlistName: destination.playlistName,
    buckets: destination.bucketOrder
      .map((bucketName) => bucketsByName.get(bucketName))
      .filter((bucket): bucket is SortActionBucket => Boolean(bucket)),
  }))
  const groupedIds = new Set(groups.map((group) => group.playlistId))
  const orphanBuckets = action.buckets.filter(
    (bucket) => !groupedIds.has(bucket.playlistId),
  )
  if (orphanBuckets.length > 0) {
    groups.push({
      playlistId: '',
      playlistName: 'Other destinations',
      buckets: orphanBuckets,
    })
  }

  const appliedCount = action.buckets.filter(
    (bucket) => bucket.status === 'applied',
  ).length
  const undoneCount = action.buckets.length - appliedCount
  const appliedBucketNames = action.buckets
    .filter((bucket) => bucket.status === 'applied')
    .map((bucket) => bucket.bucket)
  const undoneBucketCount = lastResponse
    ? lastResponse.undoneDestinations.reduce(
        (sum, destination) => sum + destination.undoneBuckets.length,
        0,
      )
    : 0
  const failedBucketCount = lastResponse?.failedDestinations
    ? lastResponse.failedDestinations.reduce(
        (sum, destination) => sum + destination.buckets.length,
        0,
      )
    : 0

  function toggleBucket(bucketName: string, checked: boolean) {
    onSelectionChange(
      checked
        ? selectedBuckets.includes(bucketName)
          ? selectedBuckets
          : [...selectedBuckets, bucketName]
        : selectedBuckets.filter((name) => name !== bucketName),
    )
  }

  function selectAllApplied() {
    onSelectionChange(appliedBucketNames)
  }

  function clearSelection() {
    onSelectionChange([])
  }

  function handleUndo() {
    if (selectedBuckets.length === 0 || isUndoing) {
      return
    }
    onUndo(selectedBuckets)
  }

  return (
    <section className="undo" id="undo" aria-labelledby="undo-heading">
      <div className="undo__heading">
        <h2 id="undo-heading">Undo last action</h2>
        <span className="undo__window">
          Ran {formatDateTime(action.createdAt) || 'recently'} · available until{' '}
          {formatDateTime(action.expiresAt) || 'the window ends'}
        </span>
        <span className="undo__count">
          {appliedCount} applied · {undoneCount} undone
        </span>
      </div>

      <p className="undo__explainer">
        Checking a row only selects it — nothing changes on Spotify until you press the undo
        button. Undo compares each playlist’s current Spotify snapshot before changing
        anything, so newer edits you’ve made are protected.
      </p>

      {lastResponse ? (
        <div
          className={`undo__outcome${lastResponse.status === 'partial' ? ' undo__outcome--partial' : ''}`}
          role="status"
          aria-live="polite"
        >
          <p>
            {lastResponse.status === 'complete'
              ? `${undoneBucketCount} bucket${undoneBucketCount === 1 ? '' : 's'} undone across ${lastResponse.undoneDestinations.length} playlist${lastResponse.undoneDestinations.length === 1 ? '' : 's'}.`
              : `Undo finished with ${undoneBucketCount} bucket${undoneBucketCount === 1 ? '' : 's'} undone and ${failedBucketCount} not undone.`}
          </p>
          {lastResponse.undoneDestinations.length > 0 ? (
            <ul className="undo__outcome-list">
              {lastResponse.undoneDestinations.map((destination) => (
                <li key={destination.playlistId}>
                  <span className="undo__outcome-name">
                    {destination.playlistName}
                  </span>
                  <span className="undo__outcome-buckets">
                    Removed {destination.undoneBuckets.join(', ')}
                  </span>
                </li>
              ))}
            </ul>
          ) : null}
          {lastResponse.failedDestinations &&
          lastResponse.failedDestinations.length > 0 ? (
            <div className="undo__failed" role="alert">
              <p>Couldn’t undo these destinations:</p>
              <ul>
                {lastResponse.failedDestinations.map((destination) => (
                  <li key={destination.playlistId}>
                    <span className="undo__failed-name">
                      {destination.playlistName}
                    </span>
                    <span className="undo__failed-error">
                      {destination.error}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {lastResponse.actionPersistWarning ? (
            <p className="undo__persist-warning" role="alert">
              {lastResponse.actionPersistWarning}
            </p>
          ) : null}
        </div>
      ) : null}

      {conflict ? (
        <div className="undo__conflict" role="alert">
          <p className="undo__conflict-title">
            Undo stopped to protect newer edits
          </p>
          <p className="undo__conflict-copy">
            One or more of these playlists changed since this run, so nothing was
            undone and your newer additions are safe.
          </p>
          <ul className="undo__conflict-list">
            {conflict.conflicts.map((item) => (
              <li key={item.playlistId}>
                <span className="undo__conflict-name">{item.playlistName}</span>
                <span className="undo__conflict-buckets">
                  {item.buckets.join(', ')}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {undoError ? (
        <p className="undo__error" role="alert">
          {undoError}
        </p>
      ) : null}

      {appliedCount === 0 ? (
        <div className="undo__all-undone" role="status">
          <p className="undo__all-undone-title">
            Everything from this run has been undone.
          </p>
          <p className="undo__all-undone-copy">
            All additions were removed and the destination playlists remain — a playlist
            whose baseline was empty is now empty again.
          </p>
        </div>
      ) : null}

      {groups.map((group) => (
        <div className="undo__group" key={group.playlistId || 'other'}>
          <h3 className="undo__group-title">{group.playlistName}</h3>
          <ul className="undo__list">
            {group.buckets.map((bucket) => {
              const undone = bucket.status === 'undone'
              const selected = !undone && selectedBuckets.includes(bucket.bucket)
              const statusLabel = undone
                ? 'Undone'
                : selected
                  ? 'Selected for undo'
                  : 'Applied'
              const inputId = bucketInputId(action.id, bucket.bucket)
              return (
                <li
                  className={`undo__row${undone ? ' undo__row--undone' : ''}${selected ? ' undo__row--selected' : ''}`}
                  key={bucket.bucket}
                >
                  <div className="undo__row-main">
                    <input
                      type="checkbox"
                      id={inputId}
                      className="undo__checkbox"
                      checked={selected}
                      disabled={undone || isUndoing}
                      onChange={(event) =>
                        toggleBucket(bucket.bucket, event.target.checked)
                      }
                    />
                    <label className="undo__bucket-info" htmlFor={inputId}>
                      <span className="undo__bucket-name">{bucket.bucket}</span>
                      <span className="undo__bucket-meta">
                        {bucket.playlistName} · {bucket.tracks.length} candidate
                        {bucket.tracks.length === 1 ? '' : 's'}
                      </span>
                    </label>
                    <span
                      className={`undo__status${undone ? ' undo__status--undone' : ''}${selected ? ' undo__status--selected' : ''}`}
                    >
                      {statusLabel}
                    </span>
                  </div>
                  <details className="undo__details">
                    <summary className="undo__summary">
                      {bucket.tracks.length} track
                      {bucket.tracks.length === 1 ? '' : 's'} in this bucket
                    </summary>
                    <div className="undo__tracks">
                      <BucketTracks bucket={bucket} />
                    </div>
                  </details>
                </li>
              )
            })}
          </ul>
        </div>
      ))}

      {appliedCount > 0 ? (
        <div className="undo__actions">
          <div className="undo__selection-tools">
            <button
              className="button button--ghost button--small"
              type="button"
              disabled={isUndoing}
              onClick={selectAllApplied}
            >
              Select all applied
            </button>
            <button
              className="button button--ghost button--small"
              type="button"
              disabled={selectedBuckets.length === 0 || isUndoing}
              onClick={clearSelection}
            >
              Clear selection
            </button>
          </div>
          <div className="undo__actions-row">
            <p className="undo__selection-hint">
              {selectedBuckets.length === 0
                ? 'Select at least one applied bucket to undo.'
                : `${selectedBuckets.length} bucket${selectedBuckets.length === 1 ? '' : 's'} selected.`}
            </p>
            <button
              className="button button--ghost"
              type="button"
              disabled={selectedBuckets.length === 0 || isUndoing}
              onClick={handleUndo}
            >
              {selectedBuckets.length === 0
                ? 'Undo selected additions'
                : `Undo ${selectedBuckets.length} selected addition${selectedBuckets.length === 1 ? '' : 's'}`}
            </button>
          </div>
        </div>
      ) : null}

      {isUndoing ? (
        <div className="undo__progress" role="status" aria-live="polite">
          <span className="spinner" aria-hidden="true" />
          <p>Undoing selected additions…</p>
        </div>
      ) : null}

    </section>
  )
}
