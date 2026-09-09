import { createReadStream } from 'node:fs'
import { readFile, realpath, stat } from 'node:fs/promises'
import { resolve, relative } from 'node:path'
import type { Plugin } from 'vite'

export function byteRange(header: string | undefined, size: number): [number, number] | null {
  if (!header) return null
  const match = /^bytes=(\d*)-(\d*)$/.exec(header)
  if (!match || (!match[1] && !match[2]) || size <= 0) throw new Error('Invalid range')
  const start = match[1] ? Number(match[1]) : Math.max(0, size - Number(match[2]))
  const end = match[1] ? (match[2] ? Math.min(Number(match[2]), size - 1) : size - 1) : size - 1
  if (!Number.isSafeInteger(start) || !Number.isSafeInteger(end) || start >= size || start > end) throw new Error('Unsatisfiable range')
  return [start, end]
}

/** Explicitly opt-in, loopback-only development bridge. Never bundled for deployment. */
export function songSpacePlugin(directory?: string, mediaDirectory = resolve('../ml/audio_similarity/.research_audio')): Plugin {
  return {
    name: 'local-song-space', apply: 'serve',
    config: () => directory ? { server: { host: '127.0.0.1' } } : undefined,
    configureServer(server) {
      server.middlewares.use(async (req, res, next) => {
        const pathname = new URL(req.url ?? '/', 'http://127.0.0.1').pathname
        if (!pathname.startsWith('/__song-space/')) return next()
        const send = (status: number, value: unknown) => {
          res.statusCode = status; res.setHeader('Content-Type', 'application/json'); res.setHeader('Cache-Control', 'no-store')
          res.end(JSON.stringify(value))
        }
        if (!['GET', 'HEAD'].includes(req.method ?? '')) return send(405, { message: 'Read-only endpoint.' })
        const host = req.headers.host ?? ''
        if (!/^(127\.0\.0\.1|localhost|\[::1\])(:\d+)?$/.test(host)) return send(403, { message: 'Local access only.' })
        try {
          if (req.headers.origin && new URL(req.headers.origin).host !== host) return send(403, { message: 'Same-origin access only.' })
        } catch { return send(403, { message: 'Invalid origin.' }) }
        if (!directory) return pathname === '/__song-space/catalog' ? send(200, []) : send(404, { message: 'No local map configured.' })
        try {
          const folder = await realpath(resolve(directory))
          if (pathname === '/__song-space/catalog') return send(200, JSON.parse(await readFile(resolve(folder, 'catalog.json'), 'utf8')))
          const data = /^\/__song-space\/data\/(library|clap-c)$/.exec(pathname)
          if (data) return send(200, JSON.parse(await readFile(resolve(folder, `${data[1]}.json`), 'utf8')))
          const audio = /^\/__song-space\/audio\/([a-zA-Z0-9]{22})$/.exec(pathname)
          if (!audio) return send(404, { message: 'Unknown resource.' })
          const index: Record<string, { path: string }> = JSON.parse(await readFile(resolve(folder, 'audio-index.json'), 'utf8'))
          if (!index[audio[1]]) return send(404, { message: 'Audio not retained.' })
          const file = await realpath(index[audio[1]].path), mediaRoot = await realpath(mediaDirectory)
          const pathWithinRoot = relative(mediaRoot, file)
          if (pathWithinRoot.startsWith('..') || pathWithinRoot.startsWith('/') || !/\.(webm|mp3|m4a|ogg|opus|wav|flac|aac)$/i.test(file)) return send(403, { message: 'Invalid media path.' })
          const { size } = await stat(file)
          let range: [number, number] | null
          try { range = byteRange(req.headers.range, size) } catch {
            res.setHeader('Content-Range', `bytes */${size}`); return send(416, { message: 'Invalid audio range.' })
          }
          const [start, end] = range ?? [0, size - 1]
          const types: Record<string, string> = { webm: 'audio/webm', mp3: 'audio/mpeg', m4a: 'audio/mp4', ogg: 'audio/ogg', opus: 'audio/ogg', wav: 'audio/wav', flac: 'audio/flac', aac: 'audio/aac' }
          res.statusCode = range ? 206 : 200
          res.setHeader('Content-Type', types[file.split('.').at(-1)?.toLowerCase() ?? ''] ?? 'application/octet-stream')
          res.setHeader('Accept-Ranges', 'bytes'); res.setHeader('Content-Length', end - start + 1)
          res.setHeader('Cache-Control', 'private, no-store')
          if (range) res.setHeader('Content-Range', `bytes ${start}-${end}/${size}`)
          if (req.method === 'HEAD') return res.end()
          const stream = createReadStream(file, { start, end })
          stream.on('error', () => res.destroy()); res.on('close', () => stream.destroy()); stream.pipe(res)
        } catch { send(503, { message: 'Local map files are unavailable. Run the exporter or open a local map file.' }) }
      })
    },
  }
}
