import { test } from 'node:test'
import assert from 'node:assert/strict'
import { parseDataset, safeUrl } from '../src/song-space/data.ts'
import { buildLayout } from '../src/song-space/layout.ts'
import { byteRange } from '../dev/songSpacePlugin.ts'
import type { SongSpaceDataset } from '../src/song-space/types.ts'
const fixture = (): SongSpaceDataset => ({
  schemaVersion: 'song-space-v1',
  id: 'test',
  name: 'Test',
  description: 'Synthetic test fixture',
  scorer: {
    id: 'cos',
    label: 'Cosine',
    description: 'Test scores',
    scoreRange: [-1, 1],
    higherIsCloser: true,
  },
  neighborhoodSize: 2,
  songs: ['a', 'b', 'c', 'd'].map((id) => ({
    id,
    title: id,
    artists: ['artist ' + id],
  })),
  links: [
    { source: 'a', target: 'b', score: 0.8, sourceRank: 1, targetRank: 1 },
    { source: 'a', target: 'c', score: 0.4, sourceRank: 2, targetRank: 1 },
    { source: 'c', target: 'd', score: 0.3, sourceRank: 2, targetRank: 1 },
  ],
})
test('snapshot preserves score and rank evidence; rejects ambiguous or unsafe inputs', () => {
  assert.deepEqual(parseDataset(fixture()), fixture())
  for (const mutate of [
    (d: SongSpaceDataset) => {
      d.links[0].score = NaN
    },
    (d: SongSpaceDataset) => {
      d.links[0].target = 'missing'
    },
    (d: SongSpaceDataset) => {
      d.songs.push(d.songs[0])
    },
    (d: SongSpaceDataset) => {
      d.links.push({ ...d.links[0], source: 'b', target: 'a' })
    },
    (d: SongSpaceDataset) => {
      d.links[1].sourceRank = 1
    },
    (d: SongSpaceDataset) => {
      d.songs[0].community = 'unknown'
    },
  ]) {
    const d = fixture()
    mutate(d)
    assert.throws(() => parseDataset(d))
  }
  for (const url of [
    'javascript:alert(1)',
    'file:///tmp/a',
    '//example.com/a',
    'https://user:pass@example.com',
  ])
    assert.throws(() => safeUrl(url))
})
test('layout is deterministic across input order and preserves nearest-neighbor scores', () => {
  const data = fixture(),
    a = buildLayout(data),
    b = buildLayout({
      ...data,
      songs: [...data.songs].reverse(),
      links: [...data.links].reverse(),
    })
  assert.deepEqual({ ...a, elapsedMs: 0 }, { ...b, elapsedMs: 0 })
  assert.equal(a.songs.length, 4)
  assert.equal(a.links[0].score, 0.8)
  assert.ok(a.songs.every((s) => Number.isFinite(s.x) && Number.isFinite(s.y)))
  assert.equal(a.links[0].sourceRank, 1)
})
test('supplied communities and geometry survive; bridge diagnostics are structural', () => {
  const d = fixture()
  d.communities = [
    { id: 'one', label: 'One' },
    { id: 'two', label: 'Two' },
  ]
  d.songs = d.songs.map((s, i) => ({
    ...s,
    community: i < 2 ? 'one' : 'two',
    x: i * 10,
    y: i % 2,
  }))
  const l = buildLayout(d)
  assert.equal(l.songs[0].community, 'one')
  assert.equal(l.communities[0].label, 'One')
  assert.equal(l.links.find((e) => e.target === 'c')?.bridge, true)
  assert.equal(l.links.find((e) => e.target === 'b')?.bridge, false)
  assert.ok(l.songs[1].x > l.songs[0].x)
})
test('empty and isolated snapshots remain valid', () => {
  const d = fixture()
  d.songs = []
  d.links = []
  assert.deepEqual(buildLayout(d).songs, [])
  d.songs = [{ id: 'a', title: 'Alone', artists: ['Solo'] }]
  assert.equal(buildLayout(d).songs[0].degree, 0)
})
test('audio byte ranges include seeking, suffixes, clipping and rejection', () => {
  assert.equal(byteRange(undefined, 100), null)
  assert.deepEqual(byteRange('bytes=20-', 100), [20, 99])
  assert.deepEqual(byteRange('bytes=-20', 100), [80, 99])
  assert.deepEqual(byteRange('bytes=0-999', 100), [0, 99])
  for (const range of ['bytes=100-', 'bytes=30-20', 'bytes=-0', 'bytes=0-1,5-8', 'bad', 'bytes=-'])
    assert.throws(() => byteRange(range, 100))
})
