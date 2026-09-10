import { useMemo, useState, useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { SpaceCanvas } from '../song-space/SpaceCanvas'
import { useLayout } from '../song-space/useLayout'
import { loadForcePacket, type ForcePacket } from './data'
import {
  pairEvidence,
  adjustedScore,
  rankNeighbors,
  topKChanges,
  retrievalDiagnostic,
  deltaDistribution,
  type Settings,
  type GenreMode,
  type ForceMode,
} from './scoring'
import { graphDataset, fixedCoordinates } from './graph'
import { AudioPlayer, PairInspector } from './PairInspector'
import type { SongSpaceDataset, SongSpaceLayout } from '../song-space/types'
import '@fontsource/ibm-plex-sans/400.css'
import '@fontsource/ibm-plex-mono/400.css'
import '../song-space/song-space.css'
import './genre-force.css'
function TemporaryGraph({
  dataset,
  onLayout,
}: {
  dataset: SongSpaceDataset
  onLayout: (l: SongSpaceLayout | undefined, error?: string) => void
}) {
  const result = useLayout(dataset)
  useEffect(() => {
    onLayout(result.layout, result.error)
  }, [result.layout, result.error, onLayout])
  return null
}
export default function GenreForceExplorer() {
  const query = useQuery({
    queryKey: ['genre-force-packet-v1'],
    queryFn: ({ signal }) => loadForcePacket(signal),
    retry: false,
    staleTime: Infinity,
  })
  return (
    <main className="song-space genre-force">
      <header className="gf-header">
        <a href="#/">← Song Space</a>
        <h1>
          Genre force explorer <small>Frozen 100 · development</small>
        </h1>
        <a href="http://127.0.0.1:8798/compare">Old / new mapper comparison ↗</a>
      </header>
      {query.isPending ? (
        <p role="status">Loading frozen scores and profiles…</p>
      ) : query.isError ? (
        <section role="alert">
          <p>{query.error.message}</p>
          <button onClick={() => void query.refetch()}>Retry</button>
        </section>
      ) : (
        <Explorer packet={query.data} />
      )}
    </main>
  )
}
function Explorer({ packet }: { packet: ForcePacket }) {
  const [settings, setSettings] = useState<Settings>(packet.defaults),
    [move, setMove] = useState(false),
    [anchorId, setAnchor] = useState(packet.songs[0].id),
    [candidateId, setCandidate] = useState(''),
    [search, setSearch] = useState(''),
    [k, setK] = useState(5)
  const byId = useMemo(() => new Map(packet.songs.map((s) => [s.id, s])), [packet])
  const evidence = useMemo(
    () =>
      packet.pairs.map((p) => ({
        ...p,
        evidence: pairEvidence(byId.get(p.a)!, byId.get(p.b)!, packet.concepts),
      })),
    [packet, byId],
  )
  const pairs = useMemo(
    () => evidence.map((p) => ({ ...p, score: adjustedScore(p.audio, p.evidence, settings) })),
    [evidence, settings],
  )
  const rows = useMemo(() => rankNeighbors(anchorId, pairs), [anchorId, pairs])
  const changes = useMemo(() => topKChanges(rows, k), [rows, k])
  const retrieval = useMemo(() => retrievalDiagnostic(rows, k), [rows, k])
  const distribution = useMemo(() => deltaDistribution(pairs), [pairs])
  const anchor = byId.get(anchorId)!,
    row = rows.find((r) => r.id === candidateId) ?? rows[0],
    candidate = byId.get(row.id)!
  const graph = useMemo(() => graphDataset(packet, pairs), [packet, pairs])
  const fixed = useMemo(() => fixedCoordinates(packet.baseLayout, graph), [packet, graph])
  const [temporary, setTemporary] = useState<{ layout?: SongSpaceLayout; error?: string }>({})
  // Callback identity is stable; each keyed worker corresponds to one immutable settings snapshot.
  const onLayout = useMemo(
    () => (layout: SongSpaceLayout | undefined, error?: string) => setTemporary({ layout, error }),
    [],
  )
  const graphKey = JSON.stringify(settings),
    moved = move && settings.alpha > 0
  const layout = moved && temporary.layout ? temporary.layout : fixed
  const root = useRef<HTMLDivElement>(null)
  const matches = packet.songs.filter(
    (s) =>
      `${s.title} ${s.artists.join(' ')}`.toLowerCase().includes(search.toLowerCase()) ||
      s.id === anchorId,
  )
  function update(change: Partial<Settings>) {
    setSettings((s) => ({ ...s, ...change }))
    setTemporary({})
  }
  function resetSettings() {
    setSettings({ ...packet.defaults })
    setMove(false)
    setTemporary({})
    setK(5)
  }
  function select(id: string) {
    setAnchor(id)
    setCandidate('')
  }
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (
        !['ArrowLeft', 'ArrowRight', ' '].includes(e.key) ||
        e.repeat ||
        e.isComposing ||
        e.altKey ||
        e.ctrlKey ||
        e.metaKey ||
        e.shiftKey
      )
        return
      if (
        e.target instanceof Element &&
        e.target.closest('input,textarea,select,button,a,summary,audio,[contenteditable]')
      )
        return
      e.preventDefault()
      if (e.key === ' ') {
        const audio = root.current?.querySelector('audio')
        if (audio) {
          if (audio.paused)
            void audio.play().catch(() => {
              audio.dataset.failed = 'true'
            })
          else audio.pause()
        }
        return
      }
      const i = packet.songs.findIndex((s) => s.id === anchorId) + (e.key === 'ArrowRight' ? 1 : -1)
      if (packet.songs[i]) {
        setAnchor(packet.songs[i].id)
        setCandidate('')
      }
    }
    document.addEventListener('keydown', key)
    return () => document.removeEventListener('keydown', key)
  }, [anchorId, packet])
  return (
    <div className="gf-body" ref={root}>
      <section className="gf-controls" aria-label="Genre settings">
        <label>
          Genre strength α{' '}
          <input
            aria-label="Genre strength alpha"
            type="range"
            min="0"
            max="1"
            step=".01"
            value={settings.alpha}
            onChange={(e) => update({ alpha: Number(e.target.value) })}
          />
          <output>{settings.alpha.toFixed(2)}</output>
        </label>
        <label>
          Genre source
          <select
            aria-label="Genre source"
            value={settings.genreMode}
            onChange={(e) => update({ genreMode: e.target.value as GenreMode })}
          >
            <option value="canonical_only">Canonical only</option>
            <option value="canonical_plus_residual">Canonical + residual (preferred)</option>
            <option value="neighborhood_only_diagnostic">Neighborhood only (diagnostic)</option>
          </select>
        </label>
        <label>
          Force mode
          <select
            aria-label="Force mode"
            value={settings.forceMode}
            onChange={(e) => update({ forceMode: e.target.value as ForceMode })}
          >
            <option value="pull_only">Pull only</option>
            <option value="signed_experimental">Signed: experimental low-overlap penalty</option>
          </select>
        </label>
        <label>
          <input
            type="checkbox"
            checked={move}
            onChange={(e) => {
              setMove(e.target.checked)
              setTemporary({})
            }}
          />{' '}
          Move graph
        </label>
        <button onClick={() => update({ alpha: 0 })}>Original audio · α = 0</button>
        <button onClick={resetSettings}>Reset to original settings</button>
        <label>
          Maximum genre contribution β
          <input
            aria-label="Genre beta"
            type="number"
            min="0"
            max="0.20"
            step="0.005"
            value={settings.beta}
            onChange={(e) => {
              const value = Number(e.target.value)
              if (Number.isFinite(value) && value >= 0 && value <= 0.2) update({ beta: value })
            }}
          />
        </label>
        <label>
          Residual relation η
          <input
            aria-label="Residual eta"
            type="number"
            min="0"
            max="1"
            step="0.05"
            value={settings.eta}
            onChange={(e) => {
              const value = Number(e.target.value)
              if (Number.isFinite(value) && value >= 0 && value <= 1) update({ eta: value })
            }}
          />
        </label>
        <p>No automatic tuning. β UI range 0–0.20; η 0–1.</p>
      </section>
      {settings.forceMode === 'signed_experimental' && (
        <p className="gf-warning" role="status">
          Experimental: low overlap subtracts score; it is not proven genre incompatibility. Missing
          style evidence remains a no-op.
        </p>
      )}
      <p className="gf-notice">
        {packet.audioIdentity}. All 99 other songs are scored per anchor. Physical distance is
        approximate; pairwise scores and ranks are authoritative.
      </p>
      <div className="gf-top">
        <section className="gf-anchor">
          <label>
            Find a song or artist
            <input
              aria-label="Find genre explorer song"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
          <label>
            Selected song
            <select
              aria-label="Genre anchor"
              value={anchorId}
              onChange={(e) => select(e.target.value)}
            >
              {matches.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.title} — {s.artists.join(', ')}
                </option>
              ))}
            </select>
          </label>
          <h2>{anchor.title}</h2>
          <p>{anchor.artists.join(', ')}</p>
          <AudioPlayer song={anchor} />
          <p>← / → change songs · Space plays anchor audio</p>
          <p>
            Vocal role: {String(anchor.raw.vocal_role)} · Arrangement:{' '}
            {String(anchor.raw.arrangement_focus)} (context only)
          </p>
          <details>
            <summary>Data and coordinate provenance</summary>
            <p>{packet.coordinateOrigin}</p>
            <pre>{JSON.stringify(packet.provenance, null, 2)}</pre>
          </details>
        </section>
        <section
          className="gf-map"
          aria-label="Genre Song Space"
          data-coordinate-signature={JSON.stringify(layout.songs.map((s) => [s.id, s.x, s.y]))}
        >
          <p role="status">
            {!moved
              ? 'Coordinates fixed to the original view'
              : temporary.error
                ? temporary.error
                : temporary.layout
                  ? 'Temporary adjusted layout'
                  : 'Calculating temporary layout…'}
          </p>
          {moved && <TemporaryGraph key={graphKey} dataset={graph} onLayout={onLayout} />}
          <SpaceCanvas
            layout={layout}
            selected={anchorId}
            edge={null}
            community={null}
            bridgesOnly={false}
            onSelect={(id) => {
              if (id) select(id)
            }}
            onEdge={(id) => {
              const edge = layout.links.find((e) => e.id === id)
              if (edge) {
                select(edge.source)
                setCandidate(edge.target)
              }
            }}
          />
        </section>
      </div>
      <section className="gf-diagnostics">
        <label>
          Top-K changes
          <select
            aria-label="Diagnostic top K"
            value={k}
            onChange={(e) => setK(Number(e.target.value))}
          >
            {[5, 10, 12, 20].map((n) => (
              <option key={n}>{n}</option>
            ))}
          </select>
        </label>
        <p>
          <strong>Entering:</strong>{' '}
          {changes.entering.map((r) => byId.get(r.id)!.title).join(' · ') || 'None'}
          <br />
          <strong>Leaving:</strong>{' '}
          {changes.leaving.map((r) => byId.get(r.id)!.title).join(' · ') || 'None'}
        </p>
        <details>
          <summary>Largest rank movers for this anchor ({changes.movers.length})</summary>
          <ul>
            {changes.movers.map((r) => (
              <li key={r.id}>
                <button onClick={() => setCandidate(r.id)}>
                  {byId.get(r.id)!.title}: {r.originalRank} → {r.adjustedRank} (
                  {r.movement > 0 ? '+' : ''}
                  {r.movement})
                </button>
              </li>
            ))}
          </ul>
        </details>
        <details>
          <summary>
            Neighborhood retrieval: {retrieval.neighborhoodOnly.length} candidates outside audio
            Top-{k}
          </summary>
          <p>
            Deduplicated audio/neighborhood Top-{k} union: {retrieval.unionSize}. All 99 candidates
            remain scored regardless.
          </p>
          <ul>
            {retrieval.neighborhoodOnly.map((r) => (
              <li key={r.id}>
                <button onClick={() => setCandidate(r.id)}>
                  {byId.get(r.id)!.title}: Jn {r.pair.evidence.jn.toFixed(4)}, audio rank{' '}
                  {r.originalRank}
                </button>
              </li>
            ))}
          </ul>
        </details>
        <details>
          <summary>Genre delta distribution · all 4,950 pairs</summary>
          <pre>{JSON.stringify(distribution, null, 2)}</pre>
        </details>
        <p className="gf-notice">
          Movers are development observations, not verified improvements. Choosing parameters here
          requires a new held-out set for confirmation.
        </p>
      </section>
      <div className="gf-bottom">
        <section className="gf-ranking">
          <h2>All 99 neighbors</h2>
          <p>
            α {settings.alpha.toFixed(2)} · β {settings.beta} · η {settings.eta}. Select a row for
            its explanation.
          </p>
          <div className="gf-table-wrap">
            <table>
              <thead>
                <tr>
                  {['Song', 'Audio', 'Adjusted', 'Rank old → new', 'Genre Δ', 'G'].map((x) => (
                    <th key={x}>{x}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} aria-selected={r.id === row.id} data-song-id={r.id}>
                    <td>
                      <button onClick={() => setCandidate(r.id)}>
                        {byId.get(r.id)!.title}
                        <small>{byId.get(r.id)!.artists.join(', ')}</small>
                      </button>
                    </td>
                    <td>{r.pair.audio.toFixed(6)}</td>
                    <td>{r.pair.score.adjusted.toFixed(6)}</td>
                    <td>
                      {r.originalRank} → {r.adjustedRank}
                    </td>
                    <td>
                      {r.pair.score.delta >= 0 ? '+' : ''}
                      {r.pair.score.delta.toFixed(6)}
                    </td>
                    <td>{r.pair.score.genre.toFixed(4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
        <PairInspector
          anchor={anchor}
          candidate={candidate}
          row={row}
          packet={packet}
          settings={settings}
        />
      </div>
    </div>
  )
}
