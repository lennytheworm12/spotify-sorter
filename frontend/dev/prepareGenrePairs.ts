/** Real genre-only proof before selecting between existing audio baselines. */
import { readFileSync, writeFileSync, existsSync } from 'node:fs'
import { resolve } from 'node:path'
import { createHash } from 'node:crypto'
import { fileURLToPath } from 'node:url'
import { pairEvidence, adjustedScore } from '../src/genre-force/scoring.ts'
import type { ForcePacket } from '../src/genre-force/data.ts'
const run = process.argv[2]
if (!run) throw Error('Specify the prepared genre directory')
const hash = (b: string | Buffer) => createHash('sha256').update(b).digest('hex')
const manifest = JSON.parse(readFileSync(resolve(run, 'prepared_manifest.json'), 'utf8'))
for (const [name, h] of Object.entries(manifest.files))
  if (hash(readFileSync(resolve(run, name))) !== h) throw Error('Prepared input changed')
const p = JSON.parse(readFileSync(resolve(run, 'prepared_genres.json'), 'utf8')) as Pick<
  ForcePacket,
  'songs' | 'concepts' | 'defaults' | 'audioIdentity'
>
if (p.songs.length !== 100 || p.audioIdentity !== 'PENDING_AUDIO_BASELINE_CONFIRMATION')
  throw Error('Expected explicitly pending real input')
const pairs = p.songs.flatMap((a, i) =>
  p.songs.slice(i + 1).map((b) => {
    const e = pairEvidence(a, b, p.concepts),
      reverse = pairEvidence(b, a, p.concepts)
    if (e.jc !== reverse.jc || e.jnr !== reverse.jnr || e.jn !== reverse.jn)
      throw Error('Asymmetric genre evidence')
    const genre = adjustedScore(0, e, p.defaults).genre
    return {
      a: a.id,
      b: b.id,
      jc: e.jc,
      jnr: e.jnr,
      jn: e.jn,
      genre,
      specificEvidence: e.canonicalAvailable,
    }
  }),
)
const files = ['src/genre-force/scoring.ts', 'dev/prepareGenrePairs.ts'].map((n) => [
  n,
  hash(readFileSync(fileURLToPath(new URL('../' + n, import.meta.url)))),
])
const result = {
  status: 'GENRE_ONLY_PREPARED_AUDIO_BASELINE_PENDING',
  tracks: 100,
  pairs: 4950,
  sourceManifestHash: hash(readFileSync(resolve(run, 'prepared_manifest.json'))),
  implementationHashes: Object.fromEntries(files),
  symmetric: true,
  unknownNoOp: true,
  genrePairEvidence: pairs,
}
const text = JSON.stringify(result, null, 2) + '\n',
  path = resolve(run, 'genre_pairs.json')
if (existsSync(path)) {
  if (readFileSync(path, 'utf8') !== text) throw Error('Frozen pair evidence differs')
} else writeFileSync(path, text, { flag: 'wx' })
console.log(
  JSON.stringify({
    status: result.status,
    tracks: 100,
    pairs: pairs.length,
    symmetric: true,
    sourceManifestHash: result.sourceManifestHash,
  }),
)
