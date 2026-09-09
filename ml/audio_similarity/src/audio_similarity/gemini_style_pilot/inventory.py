"""Resolve every designed candidate through the current retained-source overlay."""
from __future__ import annotations

from pathlib import Path

from audio_similarity.stage5b1a_models import file_sha256
from audio_similarity.stage5e3_artifacts import freeze_json, hashes, read, verify_hashes
from .prepare import prepare_audio


def prepare_inventory(root: Path, run: Path, assessments: dict) -> dict:
    root, run = root.resolve(), run.resolve()
    candidates = read(run / 'contract/private/candidates.json')
    if len(candidates) != 16 or len({t['spotify_track_id'] for t in candidates}) != 16:
        raise ValueError('the full 16-track design is required')
    verify_hashes(run / 'contract', read(run / 'contract/input_hashes.json'))
    library = root / '.research_audio/library_batches_v1'
    catalog = read(library / 'manifest.json')
    tracks = {t['spotify_track_id']: t for b in catalog['batches'] for t in b['tracks']}
    media = read(root / '.research_audio/song_space/v3/audio-index.json')
    map_provenance = read(root / '.research_audio/song_space/v3/provenance.json')
    verify_hashes(root, map_provenance['input_hashes'])
    corrections = {t['spotify_track_id']: t for t in read(library / 'source_corrections.json')['corrections']}
    quarantines = {t['spotify_track_id']: t for t in read(library / 'source_quarantines.json')['tracks']}
    existing = read(run / 'preflight/source_inventory.json')['tracks']
    neutral = {t['spotify_track_id']: t['neutral_id'] for t in existing}
    missing = sorted(t['spotify_track_id'] for t in candidates if t['spotify_track_id'] not in neutral)
    for index, tid in enumerate(missing, len(neutral) + 1):
        neutral[tid] = f'N{index:03d}'
    protected = [library / 'manifest.json', library / 'source_corrections.json',
                 library / 'source_quarantines.json',
                 *(root / '.research_audio/song_space').glob('v*/*.json'),
                 *root.glob('artifacts/**/representations.sqlite')]
    for row in candidates:
        tid = row['spotify_track_id']
        protected.extend(p for p in (root / '.research_audio' / tid).glob('*') if p.is_file())
        if tid in media:
            protected.append(Path(media[tid]['path']))
        if tid in corrections:
            protected.append(root / corrections[tid]['record_path'])
    # Preserve the earlier preflight hash baseline and freeze an expanded one.
    verify_hashes(root, read(run / 'preflight/protected_hashes.json'))
    freeze_json(run / 'source_checks/protected_hashes.json', hashes(protected, root))
    result = []
    for row in candidates:
        tid = row['spotify_track_id']
        item = {**row, 'neutral_id': neutral[tid]}
        if tid not in tracks or tid not in media or tid in quarantines:
            item.update(source_status='BLOCKED_MISSING_OR_QUARANTINED_SOURCE', eligible=False)
            result.append(item)
            continue
        source = Path(media[tid]['path'])
        provenance_path = root / '.research_audio' / tid / 'provenance.json'
        provenance = read(provenance_path)
        if tid in corrections:
            correction = corrections[tid]
            verify_hashes(root, {correction['record_path']: correction['record_sha256']})
            provenance_path = root / correction['record_path']
            provenance = read(provenance_path)['result']
        if provenance['source_sha256'] != media[tid]['sha256']:
            raise ValueError('canonical media/provenance hash mismatch')
        receipt = prepare_audio(source, provenance['source_sha256'], run / 'prepared' / f'{neutral[tid]}.flac')
        assessment = assessments.get(row['pilot_id'], {'eligible': False, 'source_status': 'BLOCKED_NO_IDENTITY_ASSESSMENT'})
        item.update(assessment)
        item.update(
            catalog_title=tracks[tid]['title'], catalog_artists=tracks[tid]['artists'],
            catalog_duration_seconds=tracks[tid]['duration_ms'] / 1000,
            source_url=provenance.get('source_url'), provider_title=provenance.get('provider_title'),
            source_correction_applied=tid in corrections,
            provenance_sha256=file_sha256(provenance_path), prepared=receipt,
        )
        result.append(item)
    verify_hashes(root, read(run / 'source_checks/protected_hashes.json'))
    inventory = {
        'schema_version': 'gemini-style-source-inventory-v1', 'tracks': result,
        'design_count': 16, 'prepared_count': sum('prepared' in t for t in result),
        'eligible_count': sum(t['eligible'] for t in result),
        'blocked_pilot_ids': [t['pilot_id'] for t in result if not t['eligible']],
        'inference_allowed': all(t['eligible'] for t in result),
        'execution_manifest_frozen': False,
    }
    return inventory
