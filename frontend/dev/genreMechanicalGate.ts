/** QA only: exercise the current scorer without modifying settings or frozen inputs. */
import { readFileSync, writeFileSync, mkdirSync, existsSync, statSync } from 'node:fs'
import { resolve } from 'node:path'
import { createHash } from 'node:crypto'
import { fileURLToPath } from 'node:url'
import { isDeepStrictEqual } from 'node:util'
import { parseForcePacket } from '../src/genre-force/data.ts'
import {
  pairEvidence,
  adjustedScore,
  rankNeighbors,
  type Settings,
} from '../src/genre-force/scoring.ts'
import { graphDataset, fixedCoordinates } from '../src/genre-force/graph.ts'
import { buildLayout } from '../src/song-space/layout.ts'

const [input, destination] = process.argv.slice(2)
if (!input || !destination)
  throw Error('Usage: node --import tsx dev/genreMechanicalGate.ts RUN QA_OUTPUT')
const run = resolve(input),
  out = resolve(destination)
if (out === run || out.startsWith(run + '/'))
  throw Error('QA output must be separate from frozen run')
mkdirSync(out, { recursive: true })
const hash = (value: string | Buffer) => createHash('sha256').update(value).digest('hex')
const read = (name: string) => JSON.parse(readFileSync(resolve(run, name), 'utf8'))
function freeze(name: string, value: unknown) {
  const bytes = Buffer.isBuffer(value) ? value : Buffer.from(JSON.stringify(value, null, 2) + '\n')
  const path = resolve(out, name)
  if (existsSync(path)) {
    if (!readFileSync(path).equals(bytes)) throw Error('QA replay differs: ' + name)
  } else writeFileSync(path, bytes, { flag: 'wx' })
}
const packet = parseForcePacket(read('explorer.json'))
const modes = ['canonical_only', 'canonical_plus_residual', 'neighborhood_only_diagnostic'] as const
const polarities = ['pull_only', 'signed_experimental'] as const
const scenarios: { id: string; settings: Settings }[] = []
for (const genreMode of modes)
  for (const forceMode of polarities)
    for (const alpha of [0, 1])
      scenarios.push({
        id: `${genreMode}:${forceMode}:alpha${alpha}`,
        settings: { ...packet.defaults, genreMode, forceMode, alpha },
      })
// These are fixed QA boundary probes, not parameter selection or calibration.
for (const [id, change] of [
  ['zero_beta', { alpha: 1, beta: 0 }],
  ['zero_eta', { alpha: 1, eta: 0 }],
  ['fractional_alpha_boundary', { alpha: 0.37, beta: 0.2, eta: 1 }],
] as const)
  scenarios.push({ id, settings: { ...packet.defaults, ...change } })
freeze('contract.json', {
  purpose: 'Mechanical QA only; no parameter choice, calibration or human-outcome evaluation',
  inputPacketSha256: hash(readFileSync(resolve(run, 'explorer.json'))),
  scenarios,
  binary: {
    path: 'scores.f64',
    order: 'scenario then packet pair then field',
    fields: ['genre', 'force', 'delta', 'adjusted'],
    format: 'IEEE754 float64 little-endian',
  },
  node: process.version,
  implementationHashes: Object.fromEntries(
    [
      'dev/genreMechanicalGate.ts',
      'src/genre-force/scoring.ts',
      'src/genre-force/graph.ts',
      'src/genre-force/data.ts',
      'src/genre-force/GenreForceExplorer.tsx',
      'src/genre-force/PairInspector.tsx',
      'src/song-space/layout.ts',
      'src/song-space/useLayout.ts',
      'src/song-space/SpaceCanvas.tsx',
      'pnpm-lock.yaml',
    ].map((n) => [n, hash(readFileSync(fileURLToPath(new URL('../' + n, import.meta.url))))]),
  ),
})
const preservedNames = [
  ...Object.keys(read('artifact_manifest.json').files),
  'artifact_manifest.json',
]
const snapshot = () =>
  Object.fromEntries(
    preservedNames.map((n) => [
      n,
      {
        sha256: hash(readFileSync(resolve(run, n))),
        mtimeMs: statSync(resolve(run, n)).mtimeMs,
      },
    ]),
  )
const before = snapshot(),
  inputBefore = JSON.stringify(packet)
const failures: {
  check: string
  pair?: string[]
  scenario?: string
  expected?: unknown
  actual?: unknown
}[] = []
function check(ok: boolean, failure: (typeof failures)[number]) {
  if (!ok) failures.push(failure)
}
const byId = new Map(packet.songs.map((s) => [s.id, s]))
const components = packet.pairs.map((p) => ({
  ...p,
  evidence: pairEvidence(byId.get(p.a)!, byId.get(p.b)!, packet.concepts),
}))
for (const p of components) {
  const reverse = pairEvidence(byId.get(p.b)!, byId.get(p.a)!, packet.concepts),
    e = p.evidence
  for (const key of ['jc', 'jnr', 'jn'] as const) {
    check(Number.isFinite(e[key]) && e[key] >= 0 && e[key] <= 1, {
      check: 'bounded_' + key,
      pair: [p.a, p.b],
      actual: e[key],
    })
    check(e[key] === reverse[key], {
      check: 'symmetric_' + key,
      pair: [p.a, p.b],
      actual: e[key],
      expected: reverse[key],
    })
  }
  check(
    isDeepStrictEqual(e.residualA, reverse.residualB) &&
      isDeepStrictEqual(e.residualB, reverse.residualA),
    { check: 'symmetric_residual_vectors', pair: [p.a, p.b] },
  )
}
freeze('components.json', components)
const binary = Buffer.alloc(scenarios.length * components.length * 4 * 8)
let offset = 0,
  alphaZeroRanks = 0,
  prefixChecks = 0
const frozenRanks = read('baseline_rankings.json')
const graphChecks = []
for (const scenario of scenarios) {
  const pairs = components.map((p) => {
    const score = adjustedScore(p.audio, p.evidence, scenario.settings)
    const reverse = adjustedScore(
      p.audio,
      pairEvidence(byId.get(p.b)!, byId.get(p.a)!, packet.concepts),
      scenario.settings,
    )
    const context = { pair: [p.a, p.b], scenario: scenario.id }
    check(isDeepStrictEqual(score, reverse), {
      check: 'symmetric_score',
      ...context,
      actual: score,
      expected: reverse,
    })
    check(Number.isFinite(score.genre) && score.genre >= 0 && score.genre <= 1, {
      check: 'bounded_G',
      ...context,
      actual: score.genre,
    })
    check(
      Number.isFinite(score.delta) &&
        Math.abs(score.delta) <= scenario.settings.alpha * scenario.settings.beta &&
        Number.isFinite(score.adjusted),
      { check: 'bounded_delta_finite_adjusted', ...context, actual: score },
    )
    check(
      score.delta === scenario.settings.alpha * scenario.settings.beta * score.force &&
        score.adjusted === p.audio + score.delta,
      { check: 'exact_reconstruction', ...context, actual: score },
    )
    if (!score.available)
      check(
        score.genre === 0 && score.force === 0 && score.delta === 0 && score.adjusted === p.audio,
        { check: 'unknown_noop', ...context, actual: score },
      )
    for (const value of [score.genre, score.force, score.delta, score.adjusted]) {
      binary.writeDoubleLE(value, offset)
      offset += 8
    }
    return { ...p, score }
  })
  if (scenario.settings.alpha === 0)
    for (const song of packet.songs) {
      const rows = rankNeighbors(song.id, pairs)
      const expected = frozenRanks[song.id]
      check(rows.length === 99, { check: 'all_candidates', pair: [song.id], scenario: scenario.id })
      for (let i = 0; i < rows.length; i++) {
        const r = rows[i]
        check(
          r.id === expected[i].id &&
            r.originalRank === i + 1 &&
            r.adjustedRank === i + 1 &&
            r.pair.score.adjusted === expected[i].audio,
          {
            check: 'alpha_zero_original_rank',
            pair: [song.id, r.id],
            scenario: scenario.id,
            expected: expected[i],
            actual: { id: r.id, rank: r.adjustedRank, score: r.pair.score.adjusted },
          },
        )
        alphaZeroRanks++
      }
      for (let k = 1; k <= 99; k++) {
        check(
          isDeepStrictEqual(
            rows.slice(0, k).map((r) => r.id),
            expected.slice(0, k).map((r: { id: string }) => r.id),
          ),
          { check: 'alpha_zero_top_' + k, pair: [song.id], scenario: scenario.id },
        )
        prefixChecks++
      }
    }
  const graph = graphDataset(packet, pairs)
  const fixed = fixedCoordinates(packet.baseLayout, graph)
  const coords = (songs: typeof fixed.songs) => songs.map((s) => [s.id, s.x, s.y])
  check(isDeepStrictEqual(coords(fixed.songs), coords(packet.baseLayout.songs)), {
    check: 'fixed_coordinates',
    scenario: scenario.id,
  })
  const scores = new Map(pairs.map((p) => [p.a + ':' + p.b, p.score.adjusted]))
  for (const link of graph.links)
    check(link.score === scores.get(link.source + ':' + link.target), {
      check: 'graph_uses_adjusted_score',
      pair: [link.source, link.target],
      scenario: scenario.id,
      actual: link.score,
      expected: scores.get(link.source + ':' + link.target),
    })
  if (
    scenario.settings.alpha === 1 &&
    scenario.settings.beta === 0.05 &&
    scenario.settings.eta === 0.25
  ) {
    const first = buildLayout(graph),
      second = buildLayout(graph)
    first.elapsedMs = second.elapsedMs = 0
    check(isDeepStrictEqual(first, second), {
      check: 'deterministic_temporary_layout',
      scenario: scenario.id,
    })
    graphChecks.push({
      scenario: scenario.id,
      edges: graph.links.length,
      layoutSha256: hash(JSON.stringify(first)),
      deterministic: isDeepStrictEqual(first, second),
    })
  }
}
check(JSON.stringify(packet) === inputBefore, { check: 'in_memory_frozen_packet_immutable' })
const after = snapshot()
check(isDeepStrictEqual(before, after), {
  check: 'frozen_run_hashes_and_mtimes_unchanged',
  expected: before,
  actual: after,
})
freeze('scores.f64', binary)
freeze('failures_node.json', failures)
freeze('node_checks.json', {
  status: failures.length ? 'FAIL' : 'PASS',
  pairs: components.length,
  scenarios: scenarios.length,
  pairScoreChecks: scenarios.length * components.length,
  alphaZeroRanks,
  topKPrefixChecks: prefixChecks,
  graphChecks,
  frozenRunBefore: before,
  frozenRunAfter: after,
  scoreBinarySha256: hash(binary),
  failureCount: failures.length,
})
console.log(
  JSON.stringify({
    status: failures.length ? 'FAIL' : 'PASS',
    pairs: components.length,
    scenarios: scenarios.length,
    failures: failures.length,
  }),
)
process.exitCode = failures.length ? 1 : 0
