import test from 'node:test'
import assert from 'node:assert/strict'
import {
  weightedJaccard,
  project,
  pairEvidence,
  adjustedScore,
  rankNeighbors,
  topKChanges,
  type GenreSong,
  type Settings,
} from '../src/genre-force/scoring.ts'
const concepts = {
  soul: { id: 'soul', label: 'Soul', kind: 'style', neighborhoods: { rnb: 1 } },
  alt: { id: 'alt', label: 'Alt', kind: 'style', neighborhoods: { rnb: 1 } },
  trap: { id: 'trap', label: 'Trap', kind: 'style', neighborhoods: { trap: 1 } },
}
const song = (id: string, c: Record<string, number>): GenreSong => ({
  id,
  pilotId: id,
  title: id,
  artists: ['ignored'],
  audioUrl: '',
  durationSeconds: 1,
  canonical: c,
  specificStyleIds: Object.keys(c),
  neighborhoods: project(c, concepts),
  excluded: [],
  raw: {},
  warnings: [],
  traces: [],
})
const settings: Settings = {
  alpha: 1,
  beta: 0.05,
  eta: 0.25,
  genreMode: 'canonical_plus_residual',
  forceMode: 'pull_only',
}
test('weighted Jaccard uses weighted union; empty is unknown; rejects invalid inputs', () => {
  assert.equal(weightedJaccard({ a: 1, b: 0.5 }, { a: 0.5, c: 0.5 }), 0.25)
  assert.equal(weightedJaccard({}, {}), 0)
  assert.throws(() => weightedJaccard({ a: NaN }, {}))
  assert.throws(() => weightedJaccard({ a: -1 }, {}))
})
test('same labels exhaust residual mass, no double count; reliable self equals one', () => {
  const a = song('a', { soul: 1, alt: 0.5 }),
    e = pairEvidence(a, a, concepts)
  assert.equal(e.jc, 1)
  assert.equal(e.jnr, 0)
  assert.deepEqual(e.residualA, {})
  assert.equal(adjustedScore(0.7, e, settings).genre, 1)
})
test('same neighborhood different canonicals is discounted, not exact agreement', () => {
  const e = pairEvidence(song('a', { soul: 1 }), song('b', { alt: 1 }), concepts)
  assert.equal(e.jc, 0)
  assert.equal(e.jnr, 1)
  assert.equal(adjustedScore(0.6, e, settings).genre, 0.25)
  assert.equal(adjustedScore(0.6, e, { ...settings, genreMode: 'canonical_only' }).genre, 0)
  assert.equal(
    adjustedScore(0.6, e, { ...settings, genreMode: 'neighborhood_only_diagnostic' }).genre,
    1,
  )
})
test('unequal shared mass is removed before projection; duplicate neighborhoods use max', () => {
  const e = pairEvidence(
    song('a', { soul: 1, alt: 0.5 }),
    song('b', { soul: 0.5, trap: 1 }),
    concepts,
  )
  assert.deepEqual(e.shared, { soul: 0.5 })
  assert.deepEqual(e.residualA, { alt: 0.5, soul: 0.5 })
  assert.deepEqual(e.residualNeighborhoodA, { rnb: 0.5 })
  assert.equal(e.jnr, 0)
})
test('unknown no-op in signed mode; known disjoint pull-only does not repel', () => {
  const e = pairEvidence(song('a', {}), song('b', { soul: 1 }), concepts)
  assert.equal(
    adjustedScore(0.4, e, { ...settings, forceMode: 'signed_experimental' }).adjusted,
    0.4,
  )
  const d = pairEvidence(song('a', { trap: 1 }), song('b', { soul: 1 }), concepts)
  assert.equal(adjustedScore(0.4, d, settings).delta, 0)
  assert.equal(
    adjustedScore(0.4, d, { ...settings, forceMode: 'signed_experimental' }).delta,
    -0.05,
  )
})
test('symmetric scores, finite bounded deltas, alpha zero exact rankings with stable ties', () => {
  const a = song('a', { soul: 1 }),
    b = song('b', { alt: 0.5 }),
    c = song('c', { soul: 1 })
  const e = pairEvidence(a, b, concepts),
    reverse = pairEvidence(b, a, concepts)
  assert.equal(e.jc, reverse.jc)
  assert.equal(e.jnr, reverse.jnr)
  for (const alpha of [0, 0.25, 1])
    for (const forceMode of ['pull_only', 'signed_experimental'] as const) {
      const s = { ...settings, alpha, forceMode }
      assert.deepEqual(adjustedScore(0.61, e, s), adjustedScore(0.61, reverse, s))
      assert.ok(Math.abs(adjustedScore(0.61, e, s).delta) <= 0.05)
    }
  const pairs = [b, c].map((x) => ({
    a: 'a',
    b: x.id,
    audio: 0.6,
    evidence: pairEvidence(a, x, concepts),
    score: adjustedScore(0.6, pairEvidence(a, x, concepts), { ...settings, alpha: 0 }),
  }))
  assert.deepEqual(
    rankNeighbors('a', pairs).map((r) => [r.id, r.originalRank, r.adjustedRank]),
    [
      ['b', 1, 1],
      ['c', 2, 2],
    ],
  )
  const changed = pairs.map((p) => ({ ...p, score: adjustedScore(p.audio, p.evidence, settings) }))
  const rows = rankNeighbors('a', changed)
  assert.equal(topKChanges(rows, 1).entering[0].id, 'c')
  assert.equal(topKChanges(rows, 1).leaving[0].id, 'b')
})
test('broad-only profiles cannot open canonical gate even when families match', () => {
  const all = {
    ...concepts,
    hiphop: { id: 'hiphop', label: 'Hip hop', kind: 'family', neighborhoods: { trap: 1 } },
  }
  const a = { ...song('a', {}), canonical: { hiphop: 0.5 }, specificStyleIds: [] },
    b = { ...song('b', {}), canonical: { hiphop: 0.5 }, specificStyleIds: [] }
  const e = pairEvidence(a, b, all)
  assert.equal(e.jc, 0)
  assert.equal(e.canonicalAvailable, false)
  assert.deepEqual(project({ hiphop: 0.5 }, all), {})
  assert.equal(adjustedScore(0.8, e, { ...settings, forceMode: 'signed_experimental' }).delta, 0)
  const x = { ...a, canonical: { hiphop: 0.5, soul: 1 }, specificStyleIds: ['soul'] },
    y = { ...b, canonical: { hiphop: 0.5, alt: 1 }, specificStyleIds: ['alt'] }
  const useful = pairEvidence(x, y, all)
  assert.equal(useful.jc, 0.2)
  assert.equal(useful.jnr, 1)
  assert.equal(adjustedScore(0.6, useful, settings).genre, 0.4)
})

import { fixture } from './genre-force-fixture.ts'
import { parseForcePacket } from '../src/genre-force/data.ts'
import { graphDataset, fixedCoordinates } from '../src/genre-force/graph.ts'
import { buildLayout } from '../src/song-space/layout.ts'
test('100 tracks / 4950 pairs validated; coordinate-off is exact; move layout deterministic and disposable', () => {
  const p = parseForcePacket(fixture()),
    byId = new Map(p.songs.map((s) => [s.id, s]))
  const pairs = p.pairs.map((x) => {
    const evidence = pairEvidence(byId.get(x.a)!, byId.get(x.b)!, p.concepts)
    return { ...x, evidence, score: adjustedScore(x.audio, evidence, { ...settings, alpha: 1 }) }
  })
  const before = JSON.stringify(p),
    graph = graphDataset(p, pairs),
    fixed = fixedCoordinates(p.baseLayout, graph)
  assert.deepEqual(
    fixed.songs.map((s) => [s.id, s.x, s.y]),
    p.baseLayout.songs.map((s) => [s.id, s.x, s.y]),
  )
  const a = buildLayout(graph),
    b = buildLayout(graph)
  assert.deepEqual(a.songs, b.songs)
  assert.notDeepEqual(
    a.songs.map((s) => [s.x, s.y]),
    fixed.songs.map((s) => [s.x, s.y]),
  )
  assert.equal(JSON.stringify(p), before)
  assert.throws(() => parseForcePacket({ ...p, pairs: p.pairs.slice(1) }))
  assert.throws(() => parseForcePacket({ ...p, pairs: [p.pairs[0], ...p.pairs.slice(0, -1)] }))
})
