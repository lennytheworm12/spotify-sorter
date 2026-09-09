import Graph from 'graphology'
import forceAtlas2 from 'graphology-layout-forceatlas2'
import louvain from 'graphology-communities-louvain'
import { contourDensity } from 'd3-contour'
import type { SongSpaceDataset, SongSpaceLayout, PlacedSong } from './types'

const COLORS = ['#8ecbb5', '#b3a2d5', '#d9a080', '#82b6d7', '#d5c486', '#cf96b3', '#91bab8', '#a8b586', '#a4aad7', '#c2b29c']
export function seededRandom(seed = 17531): () => number {
  return () => { seed |= 0; seed = seed + 0x6d2b79f5 | 0; let n = Math.imul(seed ^ seed >>> 15, 1 | seed); n = n + Math.imul(n ^ n >>> 7, 61 | n) ^ n; return ((n ^ n >>> 14) >>> 0) / 4294967296 }
}
const compare = (a: string, b: string) => a < b ? -1 : a > b ? 1 : 0
export function buildLayout(data: SongSpaceDataset): SongSpaceLayout {
  const started = performance.now(), rng = seededRandom()
  const graph = new Graph({ type: 'undirected', multi: false, allowSelfLoops: false })
  const songs = [...data.songs].sort((a, b) => compare(a.id, b.id))
  const links = data.links.map(link => link.source < link.target ? link : { ...link, source: link.target, target: link.source, sourceRank: link.targetRank, targetRank: link.sourceRank })
    .sort((a, b) => compare(a.source, b.source) || compare(a.target, b.target))
  const suppliedPositions = songs.every(s => s.x !== undefined && s.y !== undefined)
  const [min, max] = data.scorer.scoreRange
  songs.forEach(s => graph.addNode(s.id, { x: suppliedPositions ? s.x : rng() * 100, y: suppliedPositions ? s.y : rng() * 100 }))
  links.forEach((link, i) => {
    const closeness = data.scorer.higherIsCloser ? (link.score - min) / (max - min) : (max - link.score) / (max - min)
    graph.addEdgeWithKey(`e${i}`, link.source, link.target, { weight: Math.max(0.01, closeness * closeness) })
  })
  if (songs.every(s => s.community !== undefined)) songs.forEach(s => graph.setNodeAttribute(s.id, 'community', s.community))
  else if (graph.size) louvain.assign(graph, { rng: seededRandom(), resolution: 1, getEdgeWeight: 'weight' })
  else songs.forEach(s => graph.setNodeAttribute(s.id, 'community', s.id))
  if (!suppliedPositions && graph.size) forceAtlas2.assign(graph, { iterations: songs.length > 3000 ? 220 : 360, settings: {
    barnesHutOptimize: true, barnesHutTheta: 0.5, gravity: 0.7, scalingRatio: 12, slowDown: 4, linLogMode: true,
  } })
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
  graph.forEachNode((_, p) => { minX = Math.min(minX, p.x); maxX = Math.max(maxX, p.x); minY = Math.min(minY, p.y); maxY = Math.max(maxY, p.y) })
  const scale = Math.max(maxX - minX, maxY - minY, 1)
  const groups = new Map<string, string[]>()
  for (const s of songs) { const key = String(graph.getNodeAttribute(s.id, 'community')); groups.set(key, [...(groups.get(key) ?? []), s.id]) }
  const sortedGroups = [...groups].sort((a, b) => b[1].length - a[1].length || compare(a[1][0], b[1][0]))
  const songMap = new Map(songs.map(s => [s.id, s]))
  const communities = sortedGroups.map(([key, members], i) => {
    const artists = new Map<string, number>()
    for (const id of members) for (const artist of songMap.get(id)!.artists) artists.set(artist, (artists.get(artist) ?? 0) + 1)
    const label = data.communities?.find(c => c.id === key)?.label ?? [...artists].sort((a, b) => b[1] - a[1] || compare(a[0], b[0])).slice(0, 2).map(a => a[0]).join(' / ')
    return { id: songs.every(s => s.community !== undefined) ? key : `community-${i + 1}`, label, color: COLORS[i % COLORS.length], members, x: 0, y: 0 }
  })
  const membership = new Map(communities.flatMap(c => c.members.map(id => [id, c] as const)))
  const placed: PlacedSong[] = songs.map(s => {
    const p = graph.getNodeAttributes(s.id), c = membership.get(s.id)!
    return { ...s, x: 500 + (p.x - (minX + maxX) / 2) / scale * 880, y: 500 + (p.y - (minY + maxY) / 2) / scale * 880, community: c.id, color: c.color, degree: graph.degree(s.id) }
  })
  const placedMap = new Map(placed.map(s => [s.id, s]))
  for (const c of communities) { c.x = c.members.reduce((v, id) => v + placedMap.get(id)!.x, 0) / c.members.length; c.y = c.members.reduce((v, id) => v + placedMap.get(id)!.y, 0) / c.members.length }
  const neighbors = new Map(songs.map(s => [s.id, new Set(graph.neighbors(s.id))]))
  const placedLinks = links.map((l, i) => ({ ...l, id: `e${i}`, bridge: membership.get(l.source) !== membership.get(l.target),
    sharedNeighbors: [...neighbors.get(l.source)!].filter(id => neighbors.get(l.target)!.has(id)).length, weight: graph.getEdgeAttribute(`e${i}`, 'weight') }))
  const contours = placed.length > 2 ? contourDensity<PlacedSong>().x(s => s.x).y(s => s.y).size([1000, 1000]).bandwidth(30).thresholds(7)(placed).map(c => c.coordinates) : []
  return { songs: placed, links: placedLinks, communities, contours, elapsedMs: performance.now() - started }
}
