"""Apply the pinned vault reference mapper without changing old mappings or scores."""
import argparse
from collections import Counter
import importlib.util
from pathlib import Path

from .stage5e3_artifacts import read, freeze_json, verify_hashes
from .stage5b1a_models import file_sha256

CONFIG = Path('configs/genre_registry_v1')
OLD = Path('reports/genre_neighborhood_map/v1/frozen100')
SOURCE = Path('reports/gemini_style_pilot/frozen100_free_genre_v1')
REPORT = Path('reports/genre_registry_review/v1/frozen100')


def mapper(root):
    path = root / CONFIG / 'mapper_reference.py'
    spec = importlib.util.spec_from_file_location('pinned_genre_mapper', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Mapper(read(root / CONFIG / 'genre-neighborhood-map-v1.json'))


def build(root, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    protected = [root / p for p in (OLD, SOURCE, CONFIG, Path('artifacts'), Path('.research_audio'))]
    if output == root or any(output == p or output in p.parents or p in output.parents for p in protected):
        raise ValueError('Output overlaps protected inputs')
    for directory in (OLD, SOURCE):
        verify_hashes(root / directory, read(root / directory / 'artifact_manifest.json')['files'])
    engine = mapper(root)
    old = read(root / OLD / 'review_packet.json')
    if len(old['tracks']) != 100 or len({t['spotify_track_id'] for t in old['tracks']}) != 100:
        raise ValueError('Exact frozen 100 required')
    rows, unresolved, occupancy, raw_counts = [], Counter(), Counter(), Counter()
    for t in old['tracks']:
        raw_path = root / SOURCE / 'profiles' / f'{t["pilot_id"]}.json'
        raw = read(raw_path)
        if raw['spotify_track_id'] != t['spotify_track_id'] or file_sha256(raw_path) != t['mapping']['input_profile_sha256']:
            raise ValueError('Frozen profile identity/hash differs')
        new = engine.profile(raw['profile'])
        if new['raw_genre_fields'] != t['mapping']['raw_genre_labels']:
            raise ValueError('Raw labels differ across mapping versions')
        for trace in new['label_traces']:
            raw_counts[trace['raw_label']] += 1
            if trace['status'] != 'mapped':
                unresolved[trace['raw_label']] += 1
        occupancy.update(new['neighborhood_memberships'].keys())
        rows.append({k: t[k] for k in ('pilot_id','spotify_track_id','title','artists','duration_seconds')} |
                    {'audio_url': '/audio/track/'+t['pilot_id'], 'raw_profile': raw['profile'],
                     'old': t['mapping'], 'new': new})
    summary = {'tracks':100,'old_concepts':len(old['map']['concepts']), 'new_concepts':len(engine.concepts),
        'old_neighborhoods':len(old['map']['style_neighborhoods']), 'new_neighborhoods':len(engine.config['neighborhoods']),
        'old_tracks_flagged':sum(r['old']['mapping_review_required'] for r in rows),
        'new_tracks_flagged':sum(bool(r['new']['unresolved_labels']) for r in rows),
        'new_tracks_with_style_signal':sum(bool(r['new']['neighborhood_memberships']) for r in rows),
        'unresolved_label_counts':dict(sorted(unresolved.items())), 'raw_label_counts':dict(sorted(raw_counts.items())),
        'neighborhood_occupancy':dict(sorted(occupancy.items())), 'classification_accuracy':'not_assessed',
        'scores_changed':False,'model_calls':0,
        'warning':'Old and new neighborhood names/scopes differ; occupancy changes are not accuracy gains.'}
    freeze_json(output/'comparison.json', {'summary':summary,'registry':engine.config,'tracks':rows})
    freeze_json(output/'coverage.json',summary)
    freeze_json(output/'provenance.json',{'inputs':{str(p.relative_to(root)):file_sha256(p) for p in
        [root/OLD/'artifact_manifest.json',root/SOURCE/'artifact_manifest.json',*(root/CONFIG).glob('*')] if p.is_file()},
        'implementation_sha256':file_sha256(Path(__file__))})
    freeze_json(output/'artifact_manifest.json',{'files':{p.name:file_sha256(p) for p in sorted(output.iterdir()) if p.is_file() and p.name!='artifact_manifest.json'}})
    return rows


def load_comparison(root):
    path = root / REPORT
    verify_hashes(path, read(path/'artifact_manifest.json')['files'])
    return read(path/'comparison.json')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=REPORT)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[2]
    build(root,root/args.output)


if __name__=='__main__':main()
