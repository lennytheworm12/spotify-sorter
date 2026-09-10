import { writeFileSync, mkdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { fixture } from '../tests/genre-force-fixture.ts'
const out = process.argv[2]
if (!out) throw Error('Specify disposable output directory')
mkdirSync(out, { recursive: true })
const packet = fixture()
writeFileSync(resolve(out, 'explorer.json'), JSON.stringify(packet))
writeFileSync(
  resolve(out, 'audio-index.json'),
  JSON.stringify(
    Object.fromEntries(
      packet.songs.map((s) => [
        s.id,
        {
          path: resolve(
            '../ml/audio_similarity/.research_audio/gemini_style_pilot/frozen100-free-genre-v1/prepared/N001.flac',
          ),
        },
      ]),
    ),
  ),
)
