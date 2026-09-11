/** Expected temporary geometry for comparison with actual browser-worker output. */
import { readFileSync, writeFileSync, existsSync } from 'node:fs'
import { resolve } from 'node:path'
import { createHash } from 'node:crypto'
import { fileURLToPath } from 'node:url'
import { parseForcePacket } from '../src/genre-force/data.ts'
import { pairEvidence, adjustedScore, type Settings } from '../src/genre-force/scoring.ts'
import { graphDataset } from '../src/genre-force/graph.ts'
import { buildLayout } from '../src/song-space/layout.ts'
const [input, qa] = process.argv.slice(2)
if (!input || !qa) throw Error('Specify frozen run and separate QA output directory')
if (resolve(qa) === resolve(input) || resolve(qa).startsWith(resolve(input) + '/'))
  throw Error('QA output must be separate')
const packet = parseForcePacket(JSON.parse(readFileSync(resolve(input, 'explorer.json'), 'utf8')))
const contract = JSON.parse(readFileSync(resolve(qa, 'contract.json'), 'utf8'))
const byId = new Map(packet.songs.map((s) => [s.id, s]))
const layouts = contract.scenarios
  .filter(
    (s: { settings: Settings }) =>
      s.settings.alpha === 1 && s.settings.beta === 0.05 && s.settings.eta === 0.25,
  )
  .map((scenario: { id: string; settings: Settings }) => {
    const pairs = packet.pairs.map((p) => {
      const evidence = pairEvidence(byId.get(p.a)!, byId.get(p.b)!, packet.concepts)
      return { ...p, evidence, score: adjustedScore(p.audio, evidence, scenario.settings) }
    })
    const graph = graphDataset(packet, pairs)
    return {
      ...scenario,
      edges: graph.links.length,
      coordinates: buildLayout(graph).songs.map((s) => [s.id, s.x, s.y]),
    }
  })
const result = {
  scriptSha256: createHash('sha256')
    .update(readFileSync(fileURLToPath(import.meta.url)))
    .digest('hex'),
  contractSha256: createHash('sha256')
    .update(readFileSync(resolve(qa, 'contract.json')))
    .digest('hex'),
  layouts,
}
const path = resolve(qa, 'expected_graphs.json'),
  text = JSON.stringify(result, null, 2) + '\n'
if (existsSync(path)) {
  if (readFileSync(path, 'utf8') !== text) throw Error('Graph expectation replay differs')
} else writeFileSync(path, text, { flag: 'wx' })
console.log(JSON.stringify({ expectedAdjustedLayouts: layouts.length }))
