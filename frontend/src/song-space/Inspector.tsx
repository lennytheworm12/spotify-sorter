import { useState } from 'react'
import type { SongSpaceDataset, SongSpaceLayout, PlacedSong, PlacedLink } from './types'

function Player({ song }: { song: PlacedSong }) {
  const [failed, setFailed] = useState(false)
  if (!song.audioUrl) return <p className="space-small">No audio supplied in this snapshot.</p>
  return <div className="space-player"><audio controls preload="none" src={song.audioUrl} aria-label={`Listen to ${song.title}`} onError={() => setFailed(true)} />{failed && <p role="alert">Audio unavailable. The map and scores can still be explored.</p>}</div>
}
export function Inspector({ song, edge, layout, dataset, onSelect, onClose, onCommunity }: {
  song?: PlacedSong; edge?: PlacedLink; layout: SongSpaceLayout; dataset: SongSpaceDataset
  onSelect: (id: string) => void; onClose: () => void; onCommunity: (id: string) => void
}) {
  const byId = new Map(layout.songs.map(s => [s.id, s]))
  if (edge) {
    const a=byId.get(edge.source)!, b=byId.get(edge.target)!
    return <aside className="space-inspector" aria-label="Connection details"><div className="space-panel-heading"><span>Connection</span><button aria-label="Close inspector" onClick={onClose}>×</button></div>
      <div className="space-inspector-body"><h2>A connection to inspect</h2>
        {[a,b].map(s => <button className="space-edge-song" key={s.id} onClick={() => onSelect(s.id)}><i style={{ background:s.color }}/><span><strong>{s.title}</strong><small>{s.artists.join(', ')}</small></span><span>↗</span></button>)}
        <dl className="space-facts"><div><dt>{dataset.scorer.label}</dt><dd>{edge.score.toFixed(3)}</dd></div><div><dt>Community boundary</dt><dd>{edge.bridge?'Crosses':'Within'}</dd></div><div><dt>Shared graph neighbors</dt><dd>{edge.sharedNeighbors}</dd></div><div><dt>First → second rank</dt><dd>{edge.sourceRank ?? 'Outside Top ' + dataset.neighborhoodSize}</dd></div><div><dt>Second → first rank</dt><dd>{edge.targetRank ?? 'Outside Top ' + dataset.neighborhoodSize}</dd></div></dl>
        <p className="space-explanation">{edge.bridge ? 'A bridge joins different graph communities. Few shared neighbors can make it worth listening to, but do not make it a bad match.' : 'These songs belong to the same graph community. Community membership is exploratory, not a playlist decision.'}</p>
      </div></aside>
  }
  if (!song) return null
  const community=layout.communities.find(c=>c.id===song.community)!
  const neighbors=layout.links.flatMap(e=> {
    if(e.source!==song.id && e.target!==song.id)return []
    const rank=e.source===song.id?e.sourceRank:e.targetRank
    return rank===null?[]:[{edge:e,rank,song:byId.get(e.source===song.id?e.target:e.source)!}]
  }).sort((a,b)=>a.rank-b.rank)
  const bridges=neighbors.filter(n=>n.edge.bridge).length
  return <aside className="space-inspector" aria-label="Song details">
    <div className="space-panel-heading"><span>Selected song</span><button aria-label="Close inspector" onClick={onClose}>×</button></div>
    <div className="space-inspector-body"><div className="space-record" style={{ '--record-color':song.color } as React.CSSProperties}><span>◉</span><div><small>IN YOUR SONG SPACE</small><h2>{song.title}</h2><p>{song.artists.join(', ')}</p></div></div>
      {song.album && <p className="space-album">{song.album}{song.durationMs ? ' · ' + Math.floor(song.durationMs/60000)+':'+String(Math.floor(song.durationMs/1000)%60).padStart(2,'0'):''}</p>}
      <Player key={song.id} song={song}/>
      <button className="space-community-link" onClick={()=>onCommunity(community.id)}><i style={{background:community.color}}/><span><small>NEIGHBORHOOD</small>{community.label}</span><span>↗</span></button>
      <div className="space-section-title"><h3>Nearest neighbors</h3><span>TOP {dataset.neighborhoodSize}</span></div>
      <p className="space-small">{dataset.scorer.label} · {dataset.scorer.higherIsCloser?'higher':'lower'} is closer</p>
      <ol className="space-neighbors">{neighbors.map(n=><li key={n.song.id}><button onClick={()=>onSelect(n.song.id)}><span className="space-rank">{String(n.rank).padStart(2,'0')}</span><span className="space-neighbor-text"><strong>{n.song.title}</strong><small>{n.song.artists.join(', ')}{n.edge.bridge && <em> · bridge</em>}</small></span><span className="space-score">{n.edge.score.toFixed(3)}</span></button></li>)}</ol>
      {!neighbors.length && <p className="space-small">No ranked neighbors supplied for this song.</p>}
      <p className="space-explanation">{bridges} of these neighbors cross a community boundary. Scores describe this representation, not a probability of playlist fit.</p>
    </div>
  </aside>
}
