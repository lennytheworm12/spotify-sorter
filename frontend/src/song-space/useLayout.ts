import { useEffect, useState } from 'react'
import type { SongSpaceDataset, SongSpaceLayout } from './types'
export function useLayout(dataset: SongSpaceDataset) {
  const [result, setResult] = useState<{ layout?: SongSpaceLayout; error?: string }>({})
  useEffect(() => {
    const worker = new Worker(new URL('./layout.worker.ts', import.meta.url), { type: 'module' })
    const timer = window.setTimeout(() => { worker.terminate(); setResult({ error: 'This map took too long to arrange. Try a smaller snapshot or include saved positions.' }) }, 60_000)
    worker.onmessage = event => { clearTimeout(timer); setResult(event.data); worker.terminate() }
    worker.onerror = () => { clearTimeout(timer); setResult({ error: 'The map worker could not start. Reload the page and try again.' }); worker.terminate() }
    worker.postMessage(dataset)
    return () => { clearTimeout(timer); worker.terminate() }
  }, [dataset])
  return result
}
