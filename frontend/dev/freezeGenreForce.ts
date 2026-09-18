/** Finish a new genre run using the unchanged Song Space layout, never old files. */
import { readFileSync, writeFileSync, existsSync } from 'node:fs'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createHash } from 'node:crypto'
import { buildLayout } from '../src/song-space/layout.ts'
import { parseDataset } from '../src/song-space/data.ts'
import { parseForcePacket } from '../src/genre-force/data.ts'
import {
  pairEvidence,
  adjustedScore,
  rankNeighbors,
  type Settings,
} from '../src/genre-force/scoring.ts'
const directory = process.argv[2]
if (!directory) throw Error('Usage: node --import tsx dev/freezeGenreForce.ts RUN_DIRECTORY')
const run = resolve(directory),
  read = (name: string) => JSON.parse(readFileSync(resolve(run, name), 'utf8'))
const hash = (s: string | Buffer) => createHash('sha256').update(s).digest('hex')
const manifest = read('input_manifest.json')
for (const [name, h] of Object.entries(manifest.files))
  if (hash(readFileSync(resolve(run, name))) !== h) throw Error('Input integrity differs')
const baseLayout = buildLayout(parseDataset(read('base-map.json')))
baseLayout.elapsedMs = 0
const packet = parseForcePacket({ ...read('input.json'), baseLayout })
function freeze(name: string, value: unknown) {
  const text = JSON.stringify(value, null, 2) + '\n'
  const p = resolve(run, name)
  if (existsSync(p)) {
    if (readFileSync(p, 'utf8') !== text) throw Error('Frozen output differs: ' + name)
  } else writeFileSync(p, text, { flag: 'wx' })
}
packet.provenance.frontendImplementationHashes = Object.fromEntries(
  [
    'src/genre-force/scoring.ts',
    'src/genre-force/graph.ts',
    'src/song-space/layout.ts',
    'dev/freezeGenreForce.ts',
    'package.json',
    'pnpm-lock.yaml',
  ].map((name) => [
    name,
    hash(readFileSync(fileURLToPath(new URL('../' + name, import.meta.url)))),
  ]),
)
const byId = new Map(packet.songs.map((s) => [s.id, s]))
const evidence = packet.pairs.map((p) => ({
  ...p,
  evidence: pairEvidence(byId.get(p.a)!, byId.get(p.b)!, packet.concepts),
}))
const baseline = evidence.map((p) => ({
  ...p,
  score: adjustedScore(p.audio, p.evidence, packet.defaults),
}))
for (const song of packet.songs) {
  const rows = rankNeighbors(song.id, baseline)
  if (
    rows.length !== 99 ||
    rows.some((r) => r.originalRank !== r.adjustedRank || r.pair.score.adjusted !== r.pair.audio)
  )
    throw Error('Zero alpha must exactly reproduce all audio rankings')
}
for (const p of evidence) {
  const r = pairEvidence(byId.get(p.b)!, byId.get(p.a)!, packet.concepts)
  if (p.evidence.jc !== r.jc || p.evidence.jnr !== r.jnr || p.evidence.jn !== r.jn)
    throw Error('Genre score must be symmetric')
}
freeze('explorer.json', packet)
freeze(
  'baseline_rankings.json',
  Object.fromEntries(
    packet.songs.map((s) => [
      s.id,
      rankNeighbors(s.id, baseline).map((r) => ({
        id: r.id,
        rank: r.originalRank,
        audio: r.pair.audio,
      })),
    ]),
  ),
)
freeze(
  'pair_genre_evidence.json',
  evidence.map((p) => ({
    a: p.a,
    b: p.b,
    audio: p.audio,
    jc: p.evidence.jc,
    jnr: p.evidence.jnr,
    jn: p.evidence.jn,
    available: p.evidence.canonicalAvailable,
  })),
)
const counts: Record<string, unknown> = {
  tracks: 100,
  pairs: 4950,
  zeroAlphaExact: true,
  symmetric: true,
  modelCalls: 0,
}
for (const genreMode of [
  'canonical_only',
  'canonical_plus_residual',
  'neighborhood_only_diagnostic',
] as const)
  for (const forceMode of ['pull_only', 'signed_experimental'] as const) {
    const settings: Settings = { ...packet.defaults, alpha: 1, genreMode, forceMode }
    const deltas = evidence.map((p) => adjustedScore(p.audio, p.evidence, settings).delta)
    if (deltas.some((x) => !Number.isFinite(x) || Math.abs(x) > 0.05))
      throw Error('Invalid bounded delta')
    counts[genreMode + ':' + forceMode] = {
      min: Math.min(...deltas),
      max: Math.max(...deltas),
      nonzero: deltas.filter((x) => x !== 0).length,
    }
  }
freeze('engineering_checks.json', counts)
const files = [
  'input.json',
  'audio-index.json',
  'base-map.json',
  'input_manifest.json',
  'explorer.json',
  'baseline_rankings.json',
  'pair_genre_evidence.json',
  'engineering_checks.json',
]
freeze('artifact_manifest.json', {
  files: Object.fromEntries(files.map((n) => [n, hash(readFileSync(resolve(run, n)))])),
})
console.log(JSON.stringify(counts))
