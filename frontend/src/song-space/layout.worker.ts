import { buildLayout } from './layout'
import type { SongSpaceDataset } from './types'
self.onmessage = (event: MessageEvent<SongSpaceDataset>) => {
  try { self.postMessage({ layout: buildLayout(event.data) }) }
  catch (error) { self.postMessage({ error: error instanceof Error ? error.message : 'Layout could not be computed.' }) }
}
