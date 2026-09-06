"""Post-review-only scientific analysis; never called by pre-review run-all."""
import pyarrow.parquet as pq
from .stage5e3_artifacts import read,freeze_json,freeze,hashes,verify_hashes,digest
from .stage5e3_prepare import verify_prepared
from .playlist_compatibility_eval import analyze_fixture,method_metrics,positive_bank


def require_frozen_review(root,run):
    verify_prepared(root,run)
    path=run/'post_review_rating_snapshot.json'
    if not path.is_file():raise ValueError('AWAITING_HUMAN_REVIEW: analysis/reveal/closeout locked')
    snapshot=read(path);manifest=read(run/'review_manifest.json')
    verify_hashes(run,manifest['scientific_hashes'])
    submitted={e['packet_id'] for e in snapshot.get('events',[])}
    expected={p['packet_id'] for p in read(run/'review_blind_payload.json')['packets']}
    if snapshot.get('review_complete') is not True or snapshot.get('manifest_hash')!=digest(manifest) or submitted!=expected:raise ValueError('invalid frozen review')
    return snapshot


def analyze(root,run):
    snapshot=require_frozen_review(root,run)
    rows=pq.read_table(run/'retrieval_top5.parquet').to_pylist()
    source=read(run/'source_manifest.json');ids=[t['spotify_track_id'] for t in source['tracks']]
    original=read(run/'pre_review_rating_snapshot.json')
    result=analyze_fixture(rows,ids,snapshot['labels'],original['labels'],original['conflicts'],set(original['pairs']),
                           semantic_tags=snapshot['semantic_tags'])
    import numpy as np
    from .stage5e3_retrieval import rank_tracks
    from .playlist_compatibility_eval import METHODS
    bank=positive_bank(ids,set(original['pairs']),original['labels'])
    references={}
    with np.load(run/'historical_reference_matrices.npz',allow_pickle=False) as archive:
        for name in ('a_clap','a_combined','d_clap','d_combined'):
            reference_rows=[r|{'method_id':name} for r in rank_tracks(source['tracks'],{m:archive[name] for m in METHODS}) if r['method_id']==METHODS[0]]
            references[name]=method_metrics(reference_rows,name,snapshot['labels'],bank,original['labels'])
    freeze_json(run/'historical_reference_metrics.json',references)
    comparisons=result['comparisons']
    freeze_json(run/'rating_coverage.json',{'metrics':result['metrics'],'support_gates':result['support_gates']})
    freeze_json(run/'playlist_compatibility_metrics.json',{'methods':result['metrics'],'semantic_strata':result['semantic_strata']})
    freeze_json(run/'paired_method_comparison.json',comparisons)
    freeze_json(run/'known_good_recovery.json',result['recovery'])
    freeze_json(run/'known_false_positive_recurrence.json',{m:v['known_bad_recurrence'] for m,v in result['metrics'].items()})
    freeze_json(run/'method_overlap.json',result['overlap'])
    freeze_json(run/'missing_rating_bounds.json',result['missing_rating_bounds'])
    freeze_json(run/'track_node_sensitivity.json',{k:v['track_node_deletion'] for k,v in comparisons.items()})
    freeze_json(run/'revision_sensitivity.json',{'comparisons':{k:v['original_label_sensitivity'] for k,v in comparisons.items()},'revisions':snapshot['revisions']})
    freeze_json(run/'verdict_predicates.json',{'comparisons':{k:{p:v[p] for p in ('ACCEPT','GAIN','WIN','STABLE','ROBUST_WIN')} for k,v in comparisons.items()},'support_gates':result['support_gates'],'verdict':result['verdict']})
    freeze_json(run/'analysis_reference.json',{'snapshot_hash':digest(snapshot),'input_hashes':hashes([run/'post_review_rating_snapshot.json',run/'verdict_predicates.json'],run)})
    return {'status':'ANALYZED','verdict':result['verdict']}


def closeout(root,run):
    snapshot=require_frozen_review(root,run)
    reference=read(run/'analysis_reference.json');verify_hashes(run,reference['input_hashes'])
    if reference['snapshot_hash']!=digest(snapshot):raise ValueError('analysis snapshot mismatch')
    verdict=read(run/'verdict_predicates.json')['verdict']
    freeze_json(run/'closeout.json',{'verdict':verdict,'production_activation':False,
                 'limitations':['Selected frozen100, mixed historical labels, one owner; not held-out playlist validation.',
                                'Coverage, input context and pooling change jointly; shared candidate dependence remains.'],
                 'analysis_reference':reference})
    freeze_json(run/'review_reveal.json',{'retrievals':pq.read_table(run/'retrieval_top5.parquet').to_pylist(),
                                        'probes':pq.read_table(run/'probe_manifest.parquet').to_pylist()})
    freeze_json(run/'closeout_artifact_manifest.json',hashes([p for p in run.rglob('*') if p.is_file() and p.name!='closeout_artifact_manifest.json'],run))
    verify_hashes(run,read(run/'closeout_artifact_manifest.json'))
    return {'verdict':verdict}
