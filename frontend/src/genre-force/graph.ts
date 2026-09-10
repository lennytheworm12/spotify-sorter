import type { SongSpaceDataset, SongSpaceLayout, PlacedLink } from '../song-space/types'
import { rankNeighbors, type ScoredPair } from './scoring'
import type { ForcePacket } from './data'
/** Only graph edges are Top-k; authoritative neighbor tables always include all 99. */
export function graphDataset(packet: ForcePacket, pairs: ScoredPair[], k = 12): SongSpaceDataset {
  const links = new Map<
    string,
    {
      source: string
      target: string
      score: number
      sourceRank: number | null
      targetRank: number | null
    }
  >()
  for (const s of packet.songs)
    for (const n of rankNeighbors(s.id, pairs).slice(0, k)) {
      const [a, b] = [s.id, n.id].sort(),
        key = a + ':' + b
      const link = links.get(key) ?? {
        source: a,
        target: b,
        score: n.pair.score.adjusted,
        sourceRank: null,
        targetRank: null,
      }
      if (s.id === a) link.sourceRank = n.adjustedRank
      else link.targetRank = n.adjustedRank
      links.set(key, link)
    }
  return {
    schemaVersion: 'song-space-v1',
    id: 'genre-temporary',
    name: 'Temporary genre view',
    description: 'Development only',
    scorer: {
      id: 'genre-adjusted',
      label: 'Audio + genre',
      description: 'Temporary layout weights; ranks are authoritative',
      scoreRange: [-1.2, 1.2],
      higherIsCloser: true,
    },
    neighborhoodSize: k,
    songs: packet.songs.map((s) => ({
      id: s.id,
      title: s.title,
      artists: s.artists,
      audioUrl: s.audioUrl,
    })),
    links: [...links.values()].sort(
      (a, b) => a.source.localeCompare(b.source) || a.target.localeCompare(b.target),
    ),
  }
}
export function fixedCoordinates(base: SongSpaceLayout, data: SongSpaceDataset): SongSpaceLayout {
  const songs = new Map(base.songs.map((s) => [s.id, s])),
    neighbors = new Map(base.songs.map((s) => [s.id, new Set<string>()]))
  for (const l of data.links) {
    neighbors.get(l.source)!.add(l.target)
    neighbors.get(l.target)!.add(l.source)
  }
  const links: PlacedLink[] = data.links.map((l) => ({
    ...l,
    id: l.source + ':' + l.target,
    bridge: songs.get(l.source)!.community !== songs.get(l.target)!.community,
    sharedNeighbors: [...neighbors.get(l.source)!].filter((n) => neighbors.get(l.target)!.has(n))
      .length,
    weight: Math.max(0.01, ((l.score + 1.2) / 2.4) ** 2),
  }))
  return {
    ...base,
    songs: base.songs.map((s) => ({ ...s, degree: neighbors.get(s.id)!.size })),
    links,
  }
}
