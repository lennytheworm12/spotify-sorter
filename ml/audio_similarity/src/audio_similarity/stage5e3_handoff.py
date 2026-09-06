"""Engineering handoff and manifest; contains no real-data quality selection."""
from .stage5e3_artifacts import read,freeze_json,freeze,hashes,verify_hashes
from .stage5e3_prepare import verify_prepared


def handoff(root,run):
    verify_prepared(root,run)
    cache=read(run/'full_song_muq_cache_rerun.json')
    verify_hashes(run,cache['scientific_hashes'])
    if cache['track_cache_hits']!=100 or cache['forward_passes']!=0 or cache['unchanged_vectors']!=100:raise ValueError('cache replay gate failed')
    if read(run/'track_status.json')['status_counts']!={'OK':100}:raise ValueError('full100 gate failed')
    manifest=read(run/'review_manifest.json');verify_hashes(run,manifest['scientific_hashes'])
    engineering=read(run/'engineering_verification.json')
    required=('targeted_tests','full_nonheavy_suite','chromium_fixture','real_source_playback','deterministic_artifacts','historical_integrity','analysis_fixtures')
    if any(engineering.get(k,{}).get('passed') is not True for k in required):raise ValueError('engineering verification incomplete')
    if (run/'closeout.json').exists() or (run/'verdict_predicates.json').exists():raise ValueError('premature scientific closeout present')
    result={'status':'READY_FOR_HUMAN_REVIEW','experiment_status':'AWAITING_HUMAN_REVIEW',
            'tracks':100,'counts':manifest['counts'],'production_activation':False,
            'configuration_hash':read(run/'preparation_status.json')['configuration_hash'],
            'design_sha256':read(run/'algorithm_spec.json')['governing_design_sha256'],
            'pending_artifacts':['post_review_rating_snapshot.json','review_reveal.json','rating_coverage.json',
             'playlist_compatibility_metrics.json','known_good_recovery.json','known_false_positive_recurrence.json',
             'method_overlap.json','paired_method_comparison.json','track_node_sensitivity.json',
             'revision_sensitivity.json','missing_rating_bounds.json','verdict_predicates.json','closeout.json']}
    freeze_json(run/'handoff.json',result)
    text='# Stage 5E.3 engineering handoff\n\nREADY_FOR_HUMAN_REVIEW. Human review and representation recommendation pending. No production activation.\n\n'
    text+='See handoff.json for counts and hashes, engineering_verification.json for actual checks, and original_execution_ledger.json plus numbered replay ledgers for execution evidence.\n\n'
    text+='From ml/audio_similarity:\n\n```bash\n.venv/bin/python -m audio_similarity.cli.stage5e3 review --port 8785\n```\n\nAfter completing the entire queue:\n\n```bash\n.venv/bin/python -m audio_similarity.cli.stage5e3 snapshot-labels\n.venv/bin/python -m audio_similarity.cli.stage5e3 analyze\n.venv/bin/python -m audio_similarity.cli.stage5e3 closeout\n```\n\nReview resumes from .research_audio/stage5e3_frozen100_v1_review. Scientific reports are pending, not placeholders.\n'
    freeze(run/'experiment_report.md',text.encode())
    freeze_json(run/'artifact_manifest.json',hashes([p for p in run.rglob('*') if p.is_file() and p.name!='artifact_manifest.json'],run))
    verify_hashes(run,read(run/'artifact_manifest.json'))
    return result
