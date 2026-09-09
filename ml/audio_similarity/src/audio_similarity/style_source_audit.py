"""Read-only source/feature audit before a new representation experiment."""
from pathlib import Path
import numpy as np
from .stage5b1a_models import file_sha256
from .stage5e3_artifacts import read, freeze_json, hashes, verify_hashes

PRIOR = Path('reports/style_prior_pilot/v2')
RUN = Path('reports/style_source_audit/v1')
SUSPECTS = {
    '0mjbciwK9zhfQl44jXfQv6': 'Credited artist chicken97 versus provider title msftz',
    '1ON9XudZFxwu43tQXBszIX': 'Credited artist sysmint versus provider title ericdoa; unreleased upload',
    '6B9HXnRzmokTTxZNdV5T48': 'Spotify title me2urs2ours versus provider title friendzone',
}


def audit(root):
    prior, run = root / PRIOR, root / RUN
    verify_hashes(root, read(prior / 'input_hashes.json'))
    verify_hashes(prior, read(prior / 'artifact_manifest.json'))
    packet_path = root / 'reports/style_prior_pilot/review_v1/packet.json'
    packet = read(packet_path)
    tracks = {t['spotify_track_id']: t for pair in packet['pairs'] for t in (pair['left'], pair['right'])}
    ledger = {t['track_id']: t for t in read(prior / 'extraction_ledger_000.json')['tracks']}
    classes = read(prior / 'model_metadata.json')['classes']
    records, paths = [], [packet_path]
    with np.load(prior / 'raw_style_means.npz', allow_pickle=False) as means:
        for tid, track in sorted(tracks.items()):
            source = root / track['retained_source_path']
            provenance_path = source.with_name('provenance.json')
            provenance = read(provenance_path)
            assert file_sha256(source) == track['source_sha256'] == provenance['source_sha256']
            assert provenance['spotify_track_id'] == tid
            assert provenance['youtube_video_id'] == track['youtube_video_id']
            assert provenance['spotify_title'] == track['title']
            cache = root / 'artifacts/style_prior_pilot/cache' / ledger[tid]['cache_key']
            receipt = read(cache.with_suffix('.json'))
            assert receipt['identity']['source_sha256'] == track['source_sha256']
            assert file_sha256(cache.with_suffix('.npz')) == receipt['sha256']
            with np.load(cache.with_suffix('.npz'), allow_pickle=False) as z:
                patches = z['patches']
            np.testing.assert_array_equal(patches.mean(axis=0, dtype=np.float64), means[tid])
            quarters = []
            for block in np.array_split(patches, 4):
                mean = block.mean(axis=0, dtype=np.float64)
                best = sorted(range(400), key=lambda j: (-mean[j], j))[:3]
                quarters.append([{'style': classes[j], 'raw_score': float(mean[j])} for j in best])
            records.append({'track_id': tid, 'spotify_title': track['title'], 'spotify_artists': track['artists'],
                            'provider_title': provenance['provider_title'], 'youtube_video_id': track['youtube_video_id'],
                            'source_sha256': track['source_sha256'], 'byte_identity_matches_review_and_extractor': True,
                            'mean_reconstructs_exactly': True, 'provider_duration_seconds': provenance['provider_duration_seconds'],
                            'retained_duration_seconds': track['duration_seconds'], 'patches': len(patches),
                            'identity_status': 'NEEDS_OWNER_CONFIRMATION' if tid in SUSPECTS else 'METADATA_CONSISTENT_NOT_INDEPENDENTLY_IDENTIFIED',
                            'identity_question': SUSPECTS.get(tid), 'quarter_top_styles': quarters})
            paths += [source, provenance_path, cache.with_suffix('.json'), cache.with_suffix('.npz')]
    freeze_json(run / 'source_audit.json', records)
    freeze_json(run / 'reference_protocol.json', {'tracks': sorted(tid for tid, t in tracks.items() if t['title'] in ('Fresh Air', 'Die Right Here', 'Hit the Wall')),
        'selection': 'three already-exposed strong contradictions; engineering reproduction only, not efficacy evaluation',
        'reference': 'fresh process and model per track; official Essentia MonoLoader and TensorflowPredictEffnetDiscogs with frozen v2 settings and lossless PCM bridge',
        'tolerance': 1e-6, 'comparison': 'all cached patch logits after sigmoid; exact shape and maximum absolute prediction error',
        'no_new_scoring_rule': True})
    paths += [root / 'src/audio_similarity/style_source_audit.py', prior / 'protocol.json', prior / 'extractor_identity.json', prior / 'raw_style_means.npz']
    freeze_json(run / 'input_hashes.json', hashes(paths, root))
    return {'tracks': len(records), 'byte_identity_pass': len(records), 'exact_mean_reconstruction_pass': len(records), 'unresolved_source_identities': list(SUSPECTS)}


if __name__ == '__main__':
    print(audit(Path.cwd()))
