import { useEffect, useRef, useState } from 'react'
import Graph from 'graphology'
import Sigma from 'sigma'
import type { SongSpaceLayout } from './types'

interface Props {
  layout: SongSpaceLayout
  selected: string | null
  edge: string | null
  community: string | null
  bridgesOnly: boolean
  onSelect: (id: string | null) => void
  onEdge: (id: string) => void
}
export function SpaceCanvas({
  layout,
  selected,
  edge,
  community,
  bridgesOnly,
  onSelect,
  onEdge,
}: Props) {
  const container = useRef<HTMLDivElement>(null),
    terrain = useRef<HTMLCanvasElement>(null)
  const sigma = useRef<Sigma | null>(null)
  const [error, setError] = useState(''),
    [hover, setHover] = useState<{
      title: string
      artist: string
      x: number
      y: number
    } | null>(null)
  const callbacks = useRef({ onSelect, onEdge })
  useEffect(() => {
    callbacks.current = { onSelect, onEdge }
  }, [onSelect, onEdge])
  useEffect(() => {
    if (!container.current) return
    const graph = new Graph({ type: 'undirected' })
    layout.songs.forEach((s) =>
      graph.addNode(s.id, {
        x: s.x,
        y: s.y,
        size: Math.min(4.8, 1.7 + Math.sqrt(s.degree) * 0.32),
        color: s.color,
        label: s.title,
        community: s.community,
        artist: s.artists.join(', '),
      }),
    )
    layout.links.forEach((e) =>
      graph.addEdgeWithKey(e.id, e.source, e.target, {
        color: '#1b2b37',
        size: 0.22,
        bridge: e.bridge,
      }),
    )
    let renderer: Sigma
    try {
      renderer = new Sigma(graph, container.current, {
        labelFont: 'IBM Plex Sans',
        labelSize: 12,
        labelColor: { color: '#dce5e8' },
        labelDensity: 0.18,
        labelGridCellSize: 120,
        labelRenderedSizeThreshold: 4,
        renderLabels: true,
        stagePadding: 65,
        hideEdgesOnMove: true,
        enableEdgeEvents: true,
        zIndex: true,
        minCameraRatio: 0.07,
        maxCameraRatio: 2.5,
        enableCameraRotation: false,
        defaultDrawNodeHover: () => {},
      })
    } catch {
      queueMicrotask(() =>
        setError(
          'The graph needs WebGL. Enable hardware acceleration or use the song list to explore this map.',
        ),
      )
      return
    }
    sigma.current = renderer
    renderer.on('clickNode', ({ node }) => callbacks.current.onSelect(node))
    renderer.on('clickStage', () => callbacks.current.onSelect(null))
    renderer.on('clickEdge', ({ edge }) => callbacks.current.onEdge(edge))
    renderer.on('enterNode', ({ node, event }) =>
      setHover({
        title: graph.getNodeAttribute(node, 'label'),
        artist: graph.getNodeAttribute(node, 'artist'),
        x: Math.max(8, Math.min(event.x + 16, renderer.getDimensions().width - 230)),
        y: Math.max(8, event.y - 58),
      }),
    )
    renderer.on('leaveNode', () => setHover(null))
    const drawTerrain = () => {
      const canvas = terrain.current,
        ctx = canvas?.getContext('2d')
      if (!canvas || !ctx) return
      const { width, height } = renderer.getDimensions(),
        dpr = Math.min(devicePixelRatio || 1, 2)
      if (canvas.width !== Math.round(width * dpr) || canvas.height !== Math.round(height * dpr)) {
        canvas.width = Math.round(width * dpr)
        canvas.height = Math.round(height * dpr)
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.clearRect(0, 0, width, height)
      for (let level = 0; level < layout.contours.length; level++) {
        ctx.beginPath()
        for (const polygon of layout.contours[level])
          for (const ring of polygon) {
            ring.forEach((p, i) => {
              const v = renderer.graphToViewport({ x: p[0], y: p[1] })
              if (i === 0) ctx.moveTo(v.x, v.y)
              else ctx.lineTo(v.x, v.y)
            })
            ctx.closePath()
          }
        ctx.strokeStyle = `rgba(111, 158, 165, ${0.065 + level * 0.013})`
        ctx.lineWidth = 0.7
        ctx.stroke()
      }
      if (renderer.getCamera().ratio > 0.55) {
        ctx.font = '10px "IBM Plex Mono", monospace'
        ctx.textAlign = 'center'
        for (const c of layout.communities.filter((c) => c.members.length > 8)) {
          const v = renderer.graphToViewport(c)
          ctx.fillStyle = '#778f9b'
          ctx.fillText(
            `${String(layout.communities.indexOf(c) + 1).padStart(2, '0')} / ${c.label.length > 28 ? c.label.slice(0, 26) + '…' : c.label}`,
            v.x,
            v.y + 26,
          )
        }
      }
    }
    renderer.on('afterRender', drawTerrain)
    return () => {
      sigma.current = null
      renderer.kill()
    }
  }, [layout])
  useEffect(() => {
    const renderer = sigma.current
    if (!renderer) return
    const graph = renderer.getGraph(),
      endpoints = new Set(edge ? graph.extremities(edge) : []),
      nearby = new Set(selected ? graph.neighbors(selected) : [])
    renderer.setSetting('nodeReducer', (id, attrs) => {
      const inCommunity = !community || attrs.community === community
      const active = (!selected && !edge) || id === selected || nearby.has(id) || endpoints.has(id)
      const focused = id === selected || endpoints.has(id)
      return {
        ...attrs,
        color: inCommunity && active ? attrs.color : '#25333f',
        size: attrs.size + (focused ? 3 : 0),
        zIndex: focused ? 3 : active ? 1 : 0,
        highlighted: focused,
        forceLabel: focused,
        label: inCommunity && active ? attrs.label : '',
        hidden: !!community && !inCommunity,
      }
    })
    renderer.setSetting('edgeReducer', (id, attrs) => {
      const [a, b] = graph.extremities(id),
        connected = id === edge || a === selected || b === selected
      const hidden =
        (!!community &&
          (graph.getNodeAttribute(a, 'community') !== community ||
            graph.getNodeAttribute(b, 'community') !== community)) ||
        (bridgesOnly && !attrs.bridge)
      return {
        ...attrs,
        hidden,
        size: connected ? 1.1 : 0.22,
        color: connected
          ? attrs.bridge
            ? '#a77d67'
            : '#6b9b98'
          : bridgesOnly
            ? '#4c5769'
            : selected
              ? '#13232f'
              : '#1b2b37',
        zIndex: connected ? 2 : 0,
      }
    })
    renderer.refresh()
  }, [selected, edge, community, bridgesOnly, layout])
  function camera(action: 'in' | 'out' | 'reset' | 'focus') {
    const renderer = sigma.current
    if (!renderer) return
    const cam = renderer.getCamera(),
      duration = matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 220
    if (action === 'reset') void cam.animate({ x: 0.5, y: 0.5, ratio: 1, angle: 0 }, { duration })
    else if (action === 'focus' && (selected || edge)) {
      const ids = selected ? [selected] : renderer.getGraph().extremities(edge!)
      const points = ids.map((id) => renderer.getNodeDisplayData(id)!)
      const p = {
        x: points.reduce((n, point) => n + point.x, 0) / points.length,
        y: points.reduce((n, point) => n + point.y, 0) / points.length,
      }
      if (p) void cam.animate({ x: p.x, y: p.y, ratio: 0.3 }, { duration })
    } else if (action === 'in') void cam.animatedZoom({ duration })
    else if (action === 'out') void cam.animatedUnzoom({ duration })
  }
  return (
    <div
      className="space-viewport"
      aria-label="Interactive song map"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.target !== e.currentTarget) return
        if (e.key === '+' || e.key === '=') {
          e.preventDefault()
          camera('in')
        }
        if (e.key === '-') {
          e.preventDefault()
          camera('out')
        }
        if (e.key === 'Home') {
          e.preventDefault()
          camera('reset')
        }
        if (e.key === 'Escape') onSelect(null)
      }}
    >
      <canvas ref={terrain} className="space-terrain" aria-hidden="true" />
      <div ref={container} className="space-renderer" aria-hidden="true" />
      {error && (
        <div className="space-graph-error" role="alert">
          {error}
        </div>
      )}
      {hover && (
        <div className="space-tooltip" style={{ left: hover.x, top: hover.y }}>
          <strong>{hover.title}</strong>
          <span>{hover.artist}</span>
        </div>
      )}
      <div className="space-map-hint">
        <span className="space-crosshair">✣</span> Drag to explore <span>·</span> Scroll to zoom
      </div>
      <div className="space-camera-controls" aria-label="Map controls">
        {(selected || edge) && (
          <button onClick={() => camera('focus')} title="Center on selection">
            {selected ? 'Locate song' : 'Locate connection'}
          </button>
        )}
        <button onClick={() => camera('in')} aria-label="Zoom in">
          +
        </button>
        <button onClick={() => camera('out')} aria-label="Zoom out">
          −
        </button>
        <button
          onClick={() => camera('reset')}
          aria-label="Fit entire map"
          title="Fit entire map (Home)"
        >
          ↗
        </button>
      </div>
    </div>
  )
}
