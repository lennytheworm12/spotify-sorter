/** Synthetic browser fixture only. Never exported as scientific song evidence. */
import { buildLayout } from '../src/song-space/layout.ts'
import { project, type GenreSong } from '../src/genre-force/scoring.ts'
import type { ForcePacket } from '../src/genre-force/data.ts'
export function fixture(): ForcePacket {
  const concepts = {
    a: { id: 'a', label: 'Synthetic style A', kind: 'style', neighborhoods: { group: 1 } },
    b: { id: 'b', label: 'Synthetic style B', kind: 'style', neighborhoods: { group: 1 } },
    c: { id: 'c', label: 'Synthetic style C', kind: 'style', neighborhoods: { different: 1 } },
    family: { id: 'family', label: 'Synthetic family', kind: 'family', neighborhoods: {} },
  }
  const songs: GenreSong[] = Array.from({ length: 100 }, (_, i) => {
    const canonical = i === 99 ? {} : { [(['a', 'b', 'c'] as const)[i % 3]]: 1, family: 0.5 }
    const id = String(i).padStart(22, '0')
    return {
      id,
      pilotId: 'S' + i,
      title: `Synthetic song ${i}`,
      artists: ['Engineering fixture'],
      durationSeconds: 263,
      audioUrl: '/__song-space/genre/audio/' + id,
      canonical,
      specificStyleIds: i === 99 ? [] : [(['a', 'b', 'c'] as const)[i % 3]],
      neighborhoods: project(canonical, concepts),
      excluded: [],
      warnings: i === 99 ? ['Unknown fixture'] : [],
      raw: {
        primary_style: i === 99 ? 'Unknown' : 'Synthetic',
        vocal_role: 'synthetic',
        arrangement_focus: 'synthetic',
      },
      traces: [],
    }
  })
  const pairs = songs.flatMap((a, i) =>
    songs
      .slice(i + 1)
      .map((b, j) => ({ a: a.id, b: b.id, audio: 0.7 - ((i * 17 + j * 7) % 100) * 0.0004 })),
  )
  const layout = buildLayout({
    schemaVersion: 'song-space-v1',
    id: 'synthetic',
    name: 'Synthetic',
    description: 'Engineering fixture',
    scorer: {
      id: 'fixture',
      label: 'Synthetic',
      description: 'Not real ratings',
      scoreRange: [-1, 1],
      higherIsCloser: true,
    },
    neighborhoodSize: 1,
    songs: songs.map((s) => ({
      id: s.id,
      title: s.title,
      artists: s.artists,
      x: (Number(s.id) % 10) * 90,
      y: Math.floor(Number(s.id) / 10) * 90,
    })),
    links: [],
  })
  layout.elapsedMs = 0
  return {
    schemaVersion: 'genre-force-explorer-v1',
    songs,
    pairs,
    concepts,
    neighborhoodLabels: { group: 'Synthetic related group', different: 'Synthetic other group' },
    defaults: {
      alpha: 0,
      beta: 0.05,
      eta: 0.25,
      genreMode: 'canonical_plus_residual',
      forceMode: 'pull_only',
    },
    baseLayout: layout,
    audioIdentity: 'SYNTHETIC ENGINEERING FIXTURE — not real frozen scores',
    coordinateOrigin: 'Synthetic grid',
    provenance: { synthetic: true },
  }
}
