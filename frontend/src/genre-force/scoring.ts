/** Pure development scoring. No metadata, labels from people, or audio inference. */
export type Vector = Record<string, number>
export type GenreMode =
  | 'canonical_only'
  | 'canonical_plus_residual'
  | 'neighborhood_only_diagnostic'
export type ForceMode = 'pull_only' | 'signed_experimental'
export interface Concept {
  id: string
  label: string
  kind: string
  neighborhoods: Vector
}
export interface GenreSong {
  id: string
  pilotId: string
  title: string
  artists: string[]
  audioUrl: string
  durationSeconds: number
  canonical: Vector
  specificStyleIds: string[]
  neighborhoods: Vector
  excluded: { id: string; label: string; reason: string }[]
  raw: Record<string, unknown>
  warnings: string[]
  traces: unknown[]
}
export interface Settings {
  alpha: number
  beta: number
  eta: number
  genreMode: GenreMode
  forceMode: ForceMode
}
export const compareIds = (a: string, b: string) => (a < b ? -1 : a > b ? 1 : 0)
function keys(a: Vector, b: Vector): string[] {
  return [...new Set([...Object.keys(a), ...Object.keys(b)])].sort(compareIds)
}
function validate(v: Vector) {
  if (Object.values(v).some((x) => !Number.isFinite(x) || x < 0))
    throw new Error('Invalid nonnegative genre vector')
}
/** Empty evidence has zero overlap, including empty/empty. */
export function weightedJaccard(a: Vector, b: Vector): number {
  validate(a)
  validate(b)
  let intersection = 0,
    union = 0
  for (const k of keys(a, b)) {
    intersection += Math.min(a[k] ?? 0, b[k] ?? 0)
    union += Math.max(a[k] ?? 0, b[k] ?? 0)
  }
  return union > 0 ? intersection / union : 0
}
export function project(v: Vector, concepts: Record<string, Concept>): Vector {
  validate(v)
  const out: Vector = {}
  for (const k of Object.keys(v).sort(compareIds)) {
    if (!concepts[k]) throw new Error('Missing eligible canonical concept: ' + k)
    if (!['style', 'style_umbrella'].includes(concepts[k].kind)) continue
    for (const [n, multiplier] of Object.entries(concepts[k].neighborhoods)) {
      if (!Number.isFinite(multiplier) || multiplier < 0 || multiplier > 1)
        throw new Error('Invalid relation strength')
      const value = v[k] * multiplier
      if (value > 0) out[n] = Math.max(out[n] ?? 0, value)
    }
  }
  return out
}
export function pairEvidence(a: GenreSong, b: GenreSong, concepts: Record<string, Concept>) {
  validate(a.canonical)
  validate(b.canonical)
  const union: Vector = {}
  const shared: Vector = {},
    aOnly: Vector = {},
    bOnly: Vector = {},
    residualA: Vector = {},
    residualB: Vector = {}
  for (const k of keys(a.canonical, b.canonical)) {
    const x = a.canonical[k] ?? 0,
      y = b.canonical[k] ?? 0,
      matched = Math.min(x, y)
    union[k] = Math.max(x, y)
    if (matched > 0) shared[k] = matched
    if (x > 0 && y === 0) aOnly[k] = x
    if (y > 0 && x === 0) bOnly[k] = y
    // Subtract mass before neighborhood projection: a shared style cannot vote twice.
    if (x > matched) residualA[k] = x - matched
    if (y > matched) residualB[k] = y - matched
  }
  const residualNeighborhoodA = project(residualA, concepts),
    residualNeighborhoodB = project(residualB, concepts)
  const specificAvailable = a.specificStyleIds.length > 0 && b.specificStyleIds.length > 0
  return {
    union,
    shared,
    aOnly,
    bOnly,
    residualA,
    residualB,
    residualNeighborhoodA,
    residualNeighborhoodB,
    jc: specificAvailable ? weightedJaccard(a.canonical, b.canonical) : 0,
    jnr: weightedJaccard(residualNeighborhoodA, residualNeighborhoodB),
    jn: weightedJaccard(a.neighborhoods, b.neighborhoods),
    canonicalAvailable: specificAvailable,
    neighborhoodAvailable:
      specificAvailable &&
      Object.values(a.neighborhoods).some((x) => x > 0) &&
      Object.values(b.neighborhoods).some((x) => x > 0),
  }
}
export type PairEvidence = ReturnType<typeof pairEvidence>
export function adjustedScore(audio: number, e: PairEvidence, s: Settings) {
  if (
    !Number.isFinite(audio) ||
    ![s.alpha, s.beta, s.eta].every(Number.isFinite) ||
    s.alpha < 0 ||
    s.alpha > 1 ||
    s.beta < 0 ||
    s.beta > 1 ||
    s.eta < 0 ||
    s.eta > 1
  )
    throw new Error('Invalid score settings')
  if (
    !['canonical_only', 'canonical_plus_residual', 'neighborhood_only_diagnostic'].includes(
      s.genreMode,
    ) ||
    !['pull_only', 'signed_experimental'].includes(s.forceMode)
  )
    throw new Error('Unknown scoring mode')
  const available =
    s.genreMode === 'neighborhood_only_diagnostic' ? e.neighborhoodAvailable : e.canonicalAvailable
  const genre = !available
    ? 0
    : s.genreMode === 'canonical_only'
      ? e.jc
      : s.genreMode === 'neighborhood_only_diagnostic'
        ? e.jn
        : e.jc + s.eta * (1 - e.jc) * e.jnr
  const force = !available ? 0 : s.forceMode === 'pull_only' ? genre : 2 * genre - 1
  const delta = s.alpha * s.beta * force
  return {
    audio,
    genre,
    force,
    delta,
    adjusted: s.alpha === 0 || delta === 0 ? audio : audio + delta,
    available,
  }
}
export interface AudioPair {
  a: string
  b: string
  audio: number
}
export interface ScoredPair extends AudioPair {
  evidence: PairEvidence
  score: ReturnType<typeof adjustedScore>
}
export interface Neighbor {
  id: string
  originalRank: number
  adjustedRank: number
  movement: number
  pair: ScoredPair
}
export function rankNeighbors(anchor: string, pairs: ScoredPair[]): Neighbor[] {
  const relevant = pairs
    .filter((p) => p.a === anchor || p.b === anchor)
    .map((pair) => ({ id: pair.a === anchor ? pair.b : pair.a, pair }))
  const original = [...relevant].sort(
    (a, b) => b.pair.audio - a.pair.audio || compareIds(a.id, b.id),
  )
  const ranks = new Map(original.map((p, i) => [p.id, i + 1]))
  return relevant
    .sort((a, b) => b.pair.score.adjusted - a.pair.score.adjusted || compareIds(a.id, b.id))
    .map((p, i) => ({
      ...p,
      originalRank: ranks.get(p.id)!,
      adjustedRank: i + 1,
      movement: ranks.get(p.id)! - i - 1,
    }))
}
export function topKChanges(rows: Neighbor[], k: number) {
  return {
    entering: rows.filter((r) => r.adjustedRank <= k && r.originalRank > k),
    leaving: rows.filter((r) => r.originalRank <= k && r.adjustedRank > k),
    movers: [...rows]
      .sort((a, b) => Math.abs(b.movement) - Math.abs(a.movement) || compareIds(a.id, b.id))
      .filter((r) => r.movement !== 0)
      .slice(0, 10),
  }
}

/** Retrieval diagnosis never restricts the exhaustive scorer or invents labels. */
export function retrievalDiagnostic(rows: Neighbor[], k: number) {
  const audio = new Set(rows.filter((r) => r.originalRank <= k).map((r) => r.id))
  const neighborhood = [...rows]
    .filter((r) => r.pair.evidence.neighborhoodAvailable && r.pair.evidence.jn > 0)
    .sort((a, b) => b.pair.evidence.jn - a.pair.evidence.jn || compareIds(a.id, b.id))
    .slice(0, k)
  return {
    neighborhoodOnly: neighborhood.filter((r) => !audio.has(r.id)),
    unionSize: new Set([...audio, ...neighborhood.map((r) => r.id)]).size,
  }
}
export function deltaDistribution(pairs: ScoredPair[]) {
  const values = pairs.map((p) => p.score.delta).sort((a, b) => a - b)
  const quantile = (q: number) => values[Math.floor((values.length - 1) * q)] ?? 0
  return {
    pairs: values.length,
    min: quantile(0),
    p25: quantile(0.25),
    median: quantile(0.5),
    p75: quantile(0.75),
    max: quantile(1),
    positive: values.filter((x) => x > 0).length,
    zero: values.filter((x) => x === 0).length,
    negative: values.filter((x) => x < 0).length,
  }
}
