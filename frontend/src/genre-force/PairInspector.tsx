import type { ForcePacket } from './data'
import type { GenreSong, Neighbor, Settings, Vector } from './scoring'
export function AudioPlayer({ song }: { song: GenreSong }) {
  return (
    <div className="space-player">
      <audio
        key={song.id}
        controls
        preload="metadata"
        src={song.audioUrl}
        aria-label={`Listen to ${song.title}`}
        onError={(e) => {
          e.currentTarget.dataset.failed = 'true'
        }}
      />
      <p className="gf-audio-error">Audio unavailable; scores remain inspectable.</p>
    </div>
  )
}
function Tags({
  title,
  values,
  labels,
  tone,
}: {
  title: string
  values: Vector
  labels: Record<string, string>
  tone: string
}) {
  return (
    <section>
      <h4>{title}</h4>
      <div className={'gf-tags ' + tone}>
        {Object.entries(values).map(([id, w]) => (
          <span key={id} title={id}>
            {labels[id] ?? id} <b>{w.toFixed(3)}</b>
          </span>
        ))}
        {!Object.keys(values).length && <small>None</small>}
      </div>
    </section>
  )
}
function Profile({ song }: { song: GenreSong }) {
  return (
    <details>
      <summary>{song.title}: raw labels, exclusions and context</summary>
      <h4>Original Gemini labels</h4>
      <pre>
        {JSON.stringify(
          Object.fromEntries(
            ['primary_family', 'secondary_families', 'primary_style', 'secondary_styles'].map(
              (k) => [k, song.raw[k]],
            ),
          ),
          null,
          2,
        )}
      </pre>
      <p>
        <strong>Vocal role:</strong> {String(song.raw.vocal_role)} · <strong>Arrangement:</strong>{' '}
        {String(song.raw.arrangement_focus)} (context only)
      </p>
      <h4>Excluded / context-only concepts</h4>
      <ul className="gf-excluded">
        {song.excluded.map((x) => (
          <li key={x.id}>
            {x.label}: {x.reason}
          </li>
        ))}
      </ul>
      {song.warnings.map((w, i) => (
        <p className="gf-warning" key={i}>
          {w}
        </p>
      ))}
      <details>
        <summary>Frozen mapping traces</summary>
        <pre>{JSON.stringify(song.traces, null, 2)}</pre>
      </details>
    </details>
  )
}
export function PairInspector({
  anchor,
  candidate,
  row,
  packet,
  settings,
}: {
  anchor: GenreSong
  candidate: GenreSong
  row: Neighbor
  packet: ForcePacket
  settings: Settings
}) {
  const e = row.pair.evidence,
    s = row.pair.score,
    labels = Object.fromEntries(Object.values(packet.concepts).map((c) => [c.id, c.label]))
  const forward = anchor.id === row.pair.a,
    onlyA = forward ? e.aOnly : e.bOnly,
    onlyB = forward ? e.bOnly : e.aOnly,
    resA = forward ? e.residualA : e.residualB,
    resB = forward ? e.residualB : e.residualA,
    nA = forward ? e.residualNeighborhoodA : e.residualNeighborhoodB,
    nB = forward ? e.residualNeighborhoodB : e.residualNeighborhoodA
  const recovered = Object.fromEntries(
    Object.keys(nA)
      .filter((k) => (nB[k] ?? 0) > 0)
      .map((k) => [k, Math.min(nA[k], nB[k])]),
  )
  return (
    <aside className="gf-pair" aria-label="Genre pair explanation">
      <h2>
        {anchor.title} ↔ {candidate.title}
      </h2>
      <AudioPlayer song={candidate} />
      <dl className="gf-facts">
        {Object.entries({
          'Original audio': s.audio.toFixed(6),
          'Adjusted score': s.adjusted.toFixed(6),
          'Original → adjusted rank': `${row.originalRank} → ${row.adjustedRank}`,
          'Genre delta': `${s.delta >= 0 ? '+' : ''}${s.delta.toFixed(6)}`,
          'α / β / η': `${settings.alpha.toFixed(2)} / ${settings.beta} / ${settings.eta}`,
          Jc: e.jc.toFixed(6),
          Jnr: e.jnr.toFixed(6),
          'Full-neighborhood J (diagnostic)': e.jn.toFixed(6),
          'Final G': s.genre.toFixed(6),
          G_force: s.force.toFixed(6),
        }).map(([k, v]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
      <p className="gf-formula">
        S = {s.audio.toFixed(6)} + {settings.alpha.toFixed(2)} × {settings.beta} ×{' '}
        {s.force.toFixed(6)} = {s.adjusted.toFixed(6)}
      </p>
      {!s.available && (
        <p className="gf-warning">
          Insufficient eligible style evidence: genre is a no-op, including signed mode.
        </p>
      )}
      <Tags title="Canonical union" values={e.union} labels={labels} tone="union" />
      <Tags title="Exact shared canonical mass" values={e.shared} labels={labels} tone="exact" />
      <Tags title={`Only ${anchor.title}`} values={onlyA} labels={labels} tone="unmatched" />
      <Tags title={`Only ${candidate.title}`} values={onlyB} labels={labels} tone="unmatched" />
      <details open>
        <summary>Residual evidence after subtracting matched canonical mass</summary>
        <Tags
          title={`${anchor.title}: unmatched mass`}
          values={resA}
          labels={labels}
          tone="unmatched"
        />
        <Tags
          title={`${candidate.title}: unmatched mass`}
          values={resB}
          labels={labels}
          tone="unmatched"
        />
        <Tags
          title={`${anchor.title}: residual neighborhoods`}
          values={nA}
          labels={packet.neighborhoodLabels}
          tone="related"
        />
        <Tags
          title={`${candidate.title}: residual neighborhoods`}
          values={nB}
          labels={packet.neighborhoodLabels}
          tone="related"
        />
        <Tags
          title="Overlap recovered only through neighborhoods"
          values={recovered}
          labels={packet.neighborhoodLabels}
          tone="related"
        />
      </details>
      <Profile song={anchor} />
      <Profile song={candidate} />
    </aside>
  )
}
