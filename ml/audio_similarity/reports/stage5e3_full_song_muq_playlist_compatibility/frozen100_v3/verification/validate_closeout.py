"""Read-only independent arithmetic audit; run with the project's locked Python."""
import json
from pathlib import Path
import numpy as np
import pyarrow.parquet as pq
from audio_similarity.stage5e3_prepare import verify_prepared
from audio_similarity.stage5e3_artifacts import read, verify_hashes

run = Path(__file__).resolve().parents[1]
root = run.parents[2]
verify_prepared(root, run)
verify_hashes(run, read(run / 'artifact_manifest.json'))
verify_hashes(root, read(root / 'reports/stage5e3_completed_review_v1/artifact_manifest.json'))
assert read(run / 'track_status.json')['status_counts'] == {'OK': 100}
assert read(run / 'full_song_muq_cache_rerun.json')['forward_passes'] == 0
snapshot = read(run / 'post_review_rating_snapshot.json')
assert snapshot['review_complete'] and len({e['packet_id'] for e in snapshot['events']}) == 98
labels = snapshot['labels']
rows = pq.read_table(run / 'retrieval_top5.parquet').to_pylist()
methods = sorted({r['method_id'] for r in rows})
ids = sorted(t['spotify_track_id'] for t in read(run / 'source_manifest.json')['tracks'])
assert len(ids) == 100 and len(rows) == 2000 and len(methods) == 4
independent = {}
for method in methods:
    values = []
    for track in ids:
        slots = sorted([r for r in rows if r['method_id'] == method and r['query'] == track], key=lambda r:r['rank'])
        assert [r['rank'] for r in slots] == [1,2,3,4,5]
        assert all(r['candidate'] in ids and r['candidate'] != track for r in slots)
        ratings = [labels[r['pair_id']] for r in slots]
        assert all(type(v) is int and 1 <= v <= 5 for v in ratings)
        values.append(ratings)
    a = np.array(values)
    independent[method] = {'unacceptable':(a <= 2).mean(axis=1), 'coherent':(a >= 4).mean(axis=1),
                           'mean_rating':a.mean(axis=1), 'median_rating':np.median(a,axis=1)}
for key, comparison in read(run / 'paired_method_comparison.json').items():
    x,y = key.split('__vs__')
    assert comparison['eligible_ids'] == ids
    for metric in independent[x]:
        delta = independent[x][metric] - independent[y][metric]
        np.testing.assert_allclose(delta, comparison['vectors'][metric], atol=1e-12, rtol=0)
        np.testing.assert_allclose(delta.mean(), comparison['point'][metric], atol=1e-12, rtol=0)
        rng = np.random.Generator(np.random.PCG64(20260906))
        means = [delta[rng.integers(0,100,100)].mean() for _ in range(2000)]
        expected = np.percentile(means, [2.5,97.5], method='linear')
        actual = comparison['intervals'][metric]
        np.testing.assert_allclose(expected, [actual['low'],actual['high']], atol=1e-12, rtol=0)
    assert len(comparison['track_node_deletion']) == 100
    assert len(comparison['leave_one_anchor_out']) == 100
# Reject NaN/Infinity in every JSON report, including nested sensitivity results.
def reject_constant(value):
    raise ValueError('Nonfinite JSON: '+value)
for path in run.rglob('*.json'):
    json.loads(path.read_text(), parse_constant=reject_constant)
with np.load(run / 'similarity_matrices.npz', allow_pickle=False) as matrices:
    for name in matrices.files:
        matrix = matrices[name]
        if matrix.shape == (100,100):
            assert np.isfinite(matrix).all()
            np.testing.assert_allclose(matrix,matrix.T,atol=1e-6,rtol=0)
            np.testing.assert_allclose(np.diag(matrix),1,atol=1e-6,rtol=0)
print(json.dumps({'status':'PASS','methods':4,'natural_slots':2000,'paired_quality_anchors':100,
                  'independently_checked_comparisons':12,'bootstrap_replicates':2000,
                  'historical_and_frozen_review_hashes':'PASS','finite_json_and_symmetric_matrices':'PASS'},sort_keys=True))
