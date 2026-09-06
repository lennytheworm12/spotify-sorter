from pathlib import Path
import json
from audio_similarity.stage5e3_prepare import REPORT,prepare,verify_prepared
from audio_similarity.stage5e3_materialize import embed,build_similarities,build_review
from audio_similarity.stage5e3_artifacts import hashes,read,verify_hashes
root=Path.cwd();run=root/REPORT
initial=hashes([p for p in run.iterdir() if p.is_file()],run)
mtimes={p.name:p.stat().st_mtime_ns for p in run.iterdir() if p.is_file()}
prepare(root,run)
assert all((run/n).stat().st_mtime_ns==t for n,t in mtimes.items())
replay=embed(root,run)
assert replay['track_cache_hits']==100 and replay['forward_passes']==0
verify_hashes(run,initial)
build_similarities(root,run);counts=build_review(root,run)
outputs=['similarity_matrices.npz','historical_reference_matrices.npz','retrieval_top5.parquet','review_blind_payload.json','probe_manifest.parquet','candidate_union.parquet','review_manifest.json']
before=hashes([run/n for n in outputs],run)
output_mtimes={n:(run/n).stat().st_mtime_ns for n in outputs}
build_similarities(root,run);assert build_review(root,run)==counts
verify_hashes(run,before)
assert all((run/n).stat().st_mtime_ns==t for n,t in output_mtimes.items())
verify_prepared(root,run)
result={'passed':True,'prepare_rerun_rewrites':0,'track_cache_hits':replay['track_cache_hits'],
        'forward_passes':replay['forward_passes'],'initial_artifact_hashes_preserved':initial,
        'deterministic_output_hashes':before,'deterministic_output_rewrites':0,'counts':counts,
        'historical_files_verified':len(read(run/'input_reference.json')['historical'])}
Path('/tmp/stage5e3-replay-audit-result.json').write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
print(json.dumps({'passed':True,'counts':counts}))
