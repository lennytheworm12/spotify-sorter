"""Append frozen chart batches without changing earlier membership or safety state."""
from pathlib import Path

from .chart_download_batches import REPORT, build_cohort, batch_document
from .stage5d0a_catalog import same_recording
from .stage5d0a_manifest import _write_immutable_json
from .stage5b1a_models import file_sha256
from .stage5d0a_worker import read_json


def extension_directories(root):
    return sorted((root / REPORT).glob('extension_*'))


def build_extension(snapshot, digest, previous_recordings, start):
    # Compare recording identity, not only the edition's Spotify ID.
    old_ids = {t['id'] for t in previous_recordings}
    new = [r for r in snapshot['recordings']
           if not old_ids.intersection(r['spotify_ids'])
           and not any(same_recording(r['spotify'], old) for old in previous_recordings)]
    if not new:
        return None
    cohort = build_cohort({**snapshot, 'recordings': new}, digest)
    for row in cohort['tracks']:
        row['batch_number'] += start - 1
        row['stage5d0a_track_id'] = f"chart_{row['spotify_track_id']}"
    cohort['first_batch'] = start
    cohort['batch_count'] += start - 1
    cohort['scope'] = 'append-only newly matched recordings; no automatic acquisition'
    return cohort


def history(root):
    directories = [root / REPORT, *extension_directories(root)]
    recordings, references, last = [], [], 0
    for directory in directories:
        inventory = read_json(directory / 'artifact_manifest.json')
        for name, digest in inventory.items():
            if Path(name).name != name or file_sha256(directory / name) != digest:
                raise ValueError('historical batch artifact changed')
        reference = read_json(directory / 'source_reference.json')
        source = (root / reference['source_path']).resolve()
        if not source.is_relative_to(root / 'reports/stage5d_chart_catalog_v1') or file_sha256(source) != reference['source_sha256']:
            raise ValueError('historical chart source changed')
        snapshot = read_json(source)
        cohort = read_json(directory / 'cohort.json')
        required = {'cohort.json', 'source_reference.json'} | {
            f'batch_{n:04d}.json' for n in range(last+1, cohort['batch_count']+1)}
        if not required <= inventory.keys():
            raise ValueError('historical batch inventory incomplete')
        expected = (build_cohort(snapshot, reference['source_sha256'], batch_size=cohort['batch_size'])
                    if directory == root / REPORT else build_extension(snapshot, reference['source_sha256'], recordings, last + 1))
        if cohort != expected:
            raise ValueError('historical cohort membership changed')
        if directory != root / REPORT and reference['previous_inventories'] != references:
            raise ValueError('extension history changed')
        for number in range(last + 1, cohort['batch_count'] + 1):
            if read_json(directory / f'batch_{number:04d}.json') != batch_document(cohort, number):
                raise ValueError('historical batch membership changed')
        last = cohort['batch_count']
        recordings.extend(r['spotify'] for r in snapshot['recordings'])
        references.append({'path':str((directory/'artifact_manifest.json').relative_to(root)),
                           'sha256':file_sha256(directory/'artifact_manifest.json')})
    return recordings, references, last


def expand(root, source):
    root, source = Path(root).resolve(), Path(source).resolve()
    if not source.is_relative_to(root / 'reports/stage5d_chart_catalog_v1'):
        raise ValueError('expected chart matching report')
    previous, inventories, last = history(root)
    digest = file_sha256(source)
    cohort = build_extension(read_json(source), digest, previous, last + 1)
    if cohort is None:
        return {'new_tracks':0, 'downloads_started':False, 'last_batch':last}
    directory = root / REPORT / f'extension_{last+1:04d}'
    reference = {'source_path':str(source.relative_to(root)), 'source_sha256':digest,
                 'previous_inventories':inventories}
    _write_immutable_json(directory/'source_reference.json', reference)
    _write_immutable_json(directory/'cohort.json', cohort)
    for number in range(last+1, cohort['batch_count']+1):
        _write_immutable_json(directory/f'batch_{number:04d}.json', batch_document(cohort,number))
    _write_immutable_json(directory/'artifact_manifest.json', {
        p.name:file_sha256(p) for p in sorted(directory.glob('*.json')) if p.name!='artifact_manifest.json'})
    return {'new_tracks':cohort['track_count'], 'first_batch':last+1,
            'last_batch':cohort['batch_count'], 'downloads_started':False}


def validate_extension(root, number):
    history(root)
    for directory in extension_directories(root):
        path = directory / f'batch_{number:04d}.json'
        if path.exists():
            return read_json(path), file_sha256(path)
    raise ValueError('batch does not exist')
