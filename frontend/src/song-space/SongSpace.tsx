import { useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { httpProvider, MAX_FILE_BYTES, parseDataset, providerKey } from './data'
import { useLayout } from './useLayout'
import { SpaceCanvas } from './SpaceCanvas'
import { Inspector } from './Inspector'
import type { SongSpaceDataset, SongSpaceProvider, DatasetSource, SongSpaceLayout } from './types'
import '@fontsource/ibm-plex-sans/400.css'
import '@fontsource/ibm-plex-sans/500.css'
import '@fontsource/ibm-plex-sans/600.css'
import '@fontsource/ibm-plex-mono/400.css'
import './song-space.css'

const defaultProvider = httpProvider(
  import.meta.env.VITE_SONG_SPACE_CATALOG_URL || '/__song-space/catalog',
)
export function SongSpace({ provider = defaultProvider }: { provider?: SongSpaceProvider }) {
  const catalog = useQuery({
    queryKey: ['song-space-catalog', providerKey(provider)],
    queryFn: ({ signal }) => provider.catalog(signal),
    retry: false,
  })
  const [sourceId, setSourceId] = useState(''),
    [imported, setImported] = useState<SongSpaceDataset | null>(null),
    [importError, setImportError] = useState('')
  const [importSerial, setImportSerial] = useState(0)
  const file = useRef<HTMLInputElement>(null)
  const source = catalog.data?.find((s) => s.id === sourceId) ?? catalog.data?.[0]
  async function importFile(input: File | undefined) {
    if (!input) return
    try {
      if (input.size > MAX_FILE_BYTES) throw new Error('Map files must be smaller than 25 MB.')
      const data = parseDataset(JSON.parse(await input.text()))
      setImported(data)
      setImportSerial((n) => n + 1)
      setImportError('')
    } catch (error) {
      setImportError(error instanceof Error ? error.message : 'The map could not be opened.')
    }
    if (file.current) file.current.value = ''
  }
  return (
    <main className="song-space">
      <header className="space-header">
        <a href="#/" className="space-brand" aria-label="Song space home">
          <span className="space-brand-mark">⠿</span>
          <span>
            song space<span className="space-brand-sub">SPOTIFY SORTER</span>
          </span>
        </a>
        <div className="space-header-divider" />
        <span className="space-header-caption">A map of your listening world</span>
        <nav>
          <button onClick={() => file.current?.click()}>
            Open map <span>↗</span>
          </button>
          <a href="#/organize">
            Organizer <span>↗</span>
          </a>
        </nav>
        <input
          ref={file}
          type="file"
          accept=".json,application/json"
          hidden
          aria-label="Open song-space JSON"
          onChange={(e) => void importFile(e.target.files?.[0])}
        />
      </header>
      {importError && (
        <div className="space-import-error" role="alert">
          {importError}
          <button onClick={() => setImportError('')} aria-label="Dismiss import error">
            ×
          </button>
        </div>
      )}
      <div className="space-source-bar">
        <label>
          MAP{' '}
          <select
            aria-label="Map source"
            value={imported ? 'imported' : (source?.id ?? '')}
            onChange={(e) => {
              setImported(null)
              setSourceId(e.target.value)
            }}
          >
            {imported && <option value="imported">{imported.name} · local file</option>}
            {catalog.data?.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
            {!imported && !catalog.data?.length && <option value="">No map connected</option>}
          </select>
        </label>
        <span className="space-read-only">
          <i />
          Exploration only
        </span>
      </div>
      {imported ? (
        <LayoutScreen key={'import:' + importSerial} dataset={imported} />
      ) : source ? (
        <RemoteMap key={source.id} source={source} provider={provider} />
      ) : catalog.isPending ? (
        <StateScreen title="Finding your song maps…" busy />
      ) : catalog.isError ? (
        <StateScreen
          title="Your map source is unavailable"
          message={catalog.error.message}
          retry={() => void catalog.refetch()}
        />
      ) : (
        <StateScreen
          title="Your next listening world starts here"
          message="Open a song-space JSON snapshot, or connect a map source. Your songs will form a field of neighborhoods you can explore."
          action={() => file.current?.click()}
          actionLabel="Open a local map"
        />
      )}
    </main>
  )
}
function RemoteMap({ source, provider }: { source: DatasetSource; provider: SongSpaceProvider }) {
  const query = useQuery({
    queryKey: ['song-space-data', source.id, source.url, providerKey(provider)],
    queryFn: ({ signal }) => provider.load(source, signal),
    retry: false,
    staleTime: Infinity,
  })
  return query.isPending ? (
    <StateScreen title="Reading your songs…" busy />
  ) : query.isError ? (
    <StateScreen
      title="This map couldn’t be opened"
      message={query.error.message}
      retry={() => void query.refetch()}
    />
  ) : (
    <LayoutScreen key={query.data.id + query.dataUpdatedAt} dataset={query.data} />
  )
}
function StateScreen({
  title,
  message,
  busy,
  retry,
  action,
  actionLabel,
}: {
  title: string
  message?: string
  busy?: boolean
  retry?: () => void
  action?: () => void
  actionLabel?: string
}) {
  return (
    <section className="space-state" role={retry ? 'alert' : 'status'}>
      <span
        className={busy ? 'space-state-orbit is-loading' : 'space-state-orbit'}
        aria-hidden="true"
      >
        ⊙
      </span>
      <h1>{title}</h1>
      {message && <p>{message}</p>}
      {retry && <button onClick={retry}>Try again</button>}
      {action && <button onClick={action}>{actionLabel}</button>}
    </section>
  )
}
function LayoutScreen({ dataset }: { dataset: SongSpaceDataset }) {
  const { layout, error } = useLayout(dataset)
  if (!dataset.songs.length)
    return (
      <StateScreen
        title="This map has no songs yet"
        message="Choose another map or open a snapshot containing processed songs."
      />
    )
  if (error) return <StateScreen title="The map couldn’t be arranged" message={error} />
  if (!layout)
    return (
      <StateScreen
        title="Finding the shape of your library…"
        message={`${dataset.songs.length.toLocaleString()} songs · arranging connections and neighborhoods`}
        busy
      />
    )
  return <Explorer dataset={dataset} layout={layout} />
}
function Explorer({ dataset, layout }: { dataset: SongSpaceDataset; layout: SongSpaceLayout }) {
  const [visibleSongs, setVisibleSongs] = useState(200)
  const [selected, setSelected] = useState<string | null>(null),
    [edgeId, setEdgeId] = useState<string | null>(null),
    [community, setCommunity] = useState<string | null>(null)
  const [search, setSearch] = useState(''),
    [tab, setTab] = useState<'communities' | 'songs' | 'bridges'>('communities'),
    [bridgesOnly, setBridgesOnly] = useState(false),
    [sidebarOpen, setSidebarOpen] = useState(false)
  const searchRef = useRef<HTMLInputElement>(null)
  const byId = useMemo(() => new Map(layout.songs.map((s) => [s.id, s])), [layout])
  const matches = useMemo(
    () =>
      layout.songs
        .filter(
          (s) =>
            (!community || s.community === community) &&
            (!search ||
              `${s.title} ${s.artists.join(' ')}`
                .toLocaleLowerCase()
                .includes(search.toLocaleLowerCase())),
        )
        .sort((a, b) => a.title.localeCompare(b.title) || a.id.localeCompare(b.id)),
    [layout, community, search],
  )
  const bridges = useMemo(
    () =>
      layout.links
        .filter((e) => e.bridge)
        .sort(
          (a, b) =>
            a.sharedNeighbors - b.sharedNeighbors ||
            (dataset.scorer.higherIsCloser ? b.score - a.score : a.score - b.score),
        ),
    [layout, dataset],
  )
  const activeCommunity = layout.communities.find((c) => c.id === community)
  function select(id: string | null) {
    setSelected(id)
    setEdgeId(null)
    if (id && community && byId.get(id)?.community !== community) setCommunity(null)
    setSidebarOpen(false)
  }
  return (
    <>
      <div
        className="space-workspace"
        onKeyDown={(e) => {
          if (e.key === 'Escape') {
            select(null)
            setCommunity(null)
          }
          if (e.key === '/' && !(e.target instanceof HTMLInputElement)) {
            e.preventDefault()
            searchRef.current?.focus()
            setSidebarOpen(true)
          }
        }}
      >
        <button
          className="space-mobile-browse"
          onClick={() => setSidebarOpen(!sidebarOpen)}
          aria-expanded={sidebarOpen}
        >
          ☰ Browse songs
        </button>
        <aside
          className={`space-sidebar ${sidebarOpen ? 'is-open' : ''}`}
          aria-label="Browse song map"
        >
          <div className="space-sidebar-intro">
            <div className="space-eyebrow">YOUR LIBRARY, CONNECTED</div>
            <h1>Follow the sound.</h1>
            <p>
              {layout.songs.length.toLocaleString()} songs. {layout.communities.length}{' '}
              neighborhoods.
              <br />
              Find the connections between them.
            </p>
          </div>
          <div className="space-search">
            <span aria-hidden="true">⌕</span>
            <input
              ref={searchRef}
              aria-label="Find a song or artist"
              placeholder="Find a song or artist"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value)
                setTab('songs')
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && matches[0]) select(matches[0].id)
              }}
            />
            {search ? (
              <button onClick={() => setSearch('')} aria-label="Clear search">
                ×
              </button>
            ) : (
              <kbd>/</kbd>
            )}
          </div>
          <div className="space-tabs" role="tablist" aria-label="Browse by">
            {(['communities', 'songs', 'bridges'] as const).map((t) => (
              <button
                key={t}
                role="tab"
                aria-selected={tab === t}
                onClick={() => {
                  setTab(t)
                  setSearch('')
                }}
              >
                {t === 'communities' ? 'Areas' : t === 'songs' ? 'Songs' : 'Bridges'}
              </button>
            ))}
          </div>
          {activeCommunity && (
            <div className="space-filter-tag">
              <span>{activeCommunity.label}</span>
              <button onClick={() => setCommunity(null)} aria-label="Show all communities">
                ×
              </button>
            </div>
          )}
          <div className="space-sidebar-scroll" role="tabpanel">
            {tab === 'communities' && (
              <>
                <p className="space-list-caption">
                  NEIGHBORHOODS <span>{layout.communities.length}</span>
                </p>
                <ul className="space-communities">
                  {layout.communities.map((c, i) => (
                    <li key={c.id}>
                      <button
                        aria-pressed={community === c.id}
                        onClick={() => {
                          setCommunity(community === c.id ? null : c.id)
                          setBridgesOnly(false)
                          select(null)
                        }}
                      >
                        <span className="space-area-number">{String(i + 1).padStart(2, '0')}</span>
                        <i style={{ background: c.color }} />
                        <span>{c.label}</span>
                        <small>{c.members.length}</small>
                      </button>
                    </li>
                  ))}
                </ul>
                <p className="space-explanation">
                  Areas emerge from the connections. Artist names help you navigate; they aren’t
                  genre labels.
                </p>
                {community && (
                  <button className="space-text-button" onClick={() => setTab('songs')}>
                    Browse songs in this area →
                  </button>
                )}
              </>
            )}
            {tab === 'songs' && (
              <>
                <p className="space-list-caption">
                  {search ? 'SEARCH RESULTS' : 'SONGS'} <span>{matches.length}</span>
                </p>
                {!matches.length && (
                  <p className="space-explanation">
                    No songs found. Try another title or artist
                    {community ? ' or clear the area filter' : ''}.
                  </p>
                )}
                <ul className="space-song-list">
                  {matches.slice(0, visibleSongs).map((s) => (
                    <li key={s.id}>
                      <button aria-pressed={selected === s.id} onClick={() => select(s.id)}>
                        <i style={{ background: s.color }} />
                        <span>
                          <strong>{s.title}</strong>
                          <small>{s.artists.join(', ')}</small>
                        </span>
                        <span>↗</span>
                      </button>
                    </li>
                  ))}
                </ul>
                {matches.length > visibleSongs && (
                  <button
                    className="space-text-button"
                    onClick={() => setVisibleSongs((n) => n + 200)}
                  >
                    Show more songs ({visibleSongs} of {matches.length})
                  </button>
                )}
              </>
            )}
            {tab === 'bridges' && (
              <>
                <p className="space-list-caption">
                  CROSSING BETWEEN AREAS <span>{bridges.length}</span>
                </p>
                <p className="space-explanation">
                  Start with bridges that share few neighbors. These are listening leads, not
                  confirmed mismatches.
                </p>
                <ul className="space-bridge-list">
                  {bridges.slice(0, 80).map((e) => (
                    <li key={e.id}>
                      <button
                        aria-pressed={edgeId === e.id}
                        onClick={() => {
                          setEdgeId(e.id)
                          setSelected(null)
                          setCommunity(null)
                          setSidebarOpen(false)
                        }}
                      >
                        <strong>
                          {byId.get(e.source)!.title}
                          <span> ↔ </span>
                          {byId.get(e.target)!.title}
                        </strong>
                        <small>
                          {e.sharedNeighbors} shared · score {e.score.toFixed(3)}
                        </small>
                      </button>
                    </li>
                  ))}
                </ul>
                {bridges.length > 80 && (
                  <p className="space-explanation">
                    80 of {bridges.length} bridges shown, ordered by shared-neighbor count then
                    score. Click any map edge to inspect more.
                  </p>
                )}
              </>
            )}
          </div>
          <div className="space-sidebar-bottom">
            <span className="space-eyebrow">REPRESENTATION</span>
            <strong>{dataset.scorer.label}</strong>
            <p>{dataset.scorer.description}</p>
          </div>
        </aside>
        <section className="space-map-panel" aria-label="Song space">
          <div className="space-map-toolbar">
            <div>
              <span className="space-eyebrow">
                {activeCommunity ? 'NEIGHBORHOOD VIEW' : 'THE WHOLE CONSTELLATION'}
              </span>
              <strong>{activeCommunity?.label ?? 'Every song has a place.'}</strong>
            </div>
            <label className="space-toggle">
              <input
                type="checkbox"
                checked={bridgesOnly}
                onChange={(e) => {
                  setBridgesOnly(e.target.checked)
                  if (e.target.checked) setCommunity(null)
                }}
              />
              Bridges only
            </label>
          </div>
          <SpaceCanvas
            layout={layout}
            selected={selected}
            edge={edgeId}
            community={community}
            bridgesOnly={bridgesOnly}
            onSelect={select}
            onEdge={(id) => {
              setEdgeId(id)
              setSelected(null)
            }}
          />
          <div className="space-map-bottom">
            <span>
              <i />
              {layout.links.length.toLocaleString()} connections · k = {dataset.neighborhoodSize}
            </span>
            <span>Map distance ≠ exact similarity</span>
          </div>
        </section>
        <Inspector
          song={selected ? byId.get(selected) : undefined}
          edge={layout.links.find((e) => e.id === edgeId)}
          layout={layout}
          dataset={dataset}
          onSelect={select}
          onClose={() => select(null)}
          onCommunity={(id) => {
            setCommunity(id)
            setBridgesOnly(false)
            setTab('songs')
            setSidebarOpen(true)
          }}
        />
      </div>
      <footer className="space-footer">
        <span>
          SONG SPACE <span className="space-footer-dot">/</span> {dataset.name}
        </span>
        <span>Communities guide exploration. Your ears decide what belongs.</span>
      </footer>
    </>
  )
}
