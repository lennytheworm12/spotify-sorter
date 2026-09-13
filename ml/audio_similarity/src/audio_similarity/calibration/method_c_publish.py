"""Publish verified counts/provenance without copying audio or starting calibration."""
from pathlib import Path
import re
from .contracts import file_hash,freeze_json,require
from .method_c_full_inputs import RUN,read

PUBLIC='reports/playlist_weight_calibration/v1/method_c_full'
MONITOR='.research_audio/playlist_calibration_method_c_handoff_v1'


def publish(root):
    run=root/RUN
    output=root/PUBLIC
    verification=read(run/'verification.json')
    readiness=read(run/'readiness.json')
    require(verification['status']=='VERIFIED' and readiness['method_c_status']=='COMPLETE','materialization not verified')
    monitor=root/MONITOR
    require(read(monitor/'complete.json')['status']=='MATERIALIZATION_AND_VERIFICATION_COMPLETE','supervised verification/tests incomplete')
    log=(monitor/'nonheavy_tests.log').read_text()
    match=re.search(r'(\d+) passed, (\d+) deselected, (\d+) warnings in ([\d.]+)s',log)
    require(match is not None,'non-heavy test result not recognized')
    tests={'passed':int(match[1]),'heavy_excluded':int(match[2]),'warnings':int(match[3]),
           'seconds':float(match[4]),'source_log_sha256':file_hash(monitor/'nonheavy_tests.log')}
    freeze_json(output/'configuration.json',read(run/'configuration.json'))
    imports=read(run/'continuation_imports.json')
    freeze_json(output/'cpu_configuration.json',imports['configuration'])
    for name in imports['configuration']['implementation']:
        raw=(root/imports['cpu_run']/'implementation_snapshot'/name).read_bytes()
        target=output/'frozen_cpu_implementation'/name
        target.parent.mkdir(parents=True,exist_ok=True)
        require(not target.exists() or target.read_bytes()==raw, 'archived CPU implementation differs')
        if not target.exists():target.write_bytes(raw)
    validation=output/'validation'
    validation.mkdir(parents=True,exist_ok=True)
    target=validation/'nonheavy.log'
    require(not target.exists() or target.read_text()==log, 'published test log differs')
    if not target.exists():target.write_text(log)
    focused=(monitor/'focused-final.log').read_text()
    focused_match=re.search(r'(\d+) passed',focused)
    require(focused_match is not None,'focused test result not recognized')
    tests['focused_passed']=int(focused_match[1])
    for name in ('focused-final.log','matrix-readiness-tests.log','reused-sampling-contract-audit.log'):
        raw=(monitor/name).read_bytes()
        target=validation/name
        require(not target.exists() or target.read_bytes()==raw, 'validation log changed')
        if not target.exists():target.write_bytes(raw)
    counts=readiness['counts']
    parity=read(run/'gpu_parity.json')
    evidence={'verification':verification,'readiness_counts':counts,'tests':tests,'gpu_parity':parity,
              'pooling_repairs':{r['recording_id']:r['pooling_repair'] for r in readiness['recordings'] if r.get('pooling_repair')},
              'private_run':str(run.relative_to(root)),
              'private_artifact_manifest_sha256':file_hash(run/'artifact_manifest.json'),
              'calibration_started':False,'production_activation':False}
    freeze_json(output/'execution_validation.json',evidence)
    freeze_json(output/'track_status.json',readiness['recordings'])
    freeze_json(output/'recording_ids.json',read(run/'matrices/recording_ids.json'))
    freeze_json(output/'common_recording_ids.json',read(run/'matrices/common_recording_ids.json'))
    report=f'''# Full-corpus Method C materialization

**Method C: COMPLETE. Calibration readiness: {readiness['status']}.**

The original 28-playlist manifest contains {counts['frozen_requests']:,} requests.
{counts['distinct_retained_recordings']:,} distinct retained recording IDs were
materialized without changing source membership. The {counts['source_unavailable_requests']}
requests without validated retained audio remain explicit; the extension corpus
was not added.

| Evidence | Count |
|---|---:|
| Method C complete | {counts['method_c_complete']} |
| Existing Method C reused | {counts['method_c_reused']} |
| Newly computed Method C | {counts['method_c_new']} |
| New on CPU / GPU | {counts['method_c_cpu_new']} / {counts['method_c_gpu_new']} |
| Missing Method C / source-blocked retained recordings | {counts['method_c_missing']} / {counts['source_blocked_recordings']} |
| Exact-source MuQ / centered30 | {counts['M_complete']} / {counts['C_center30_complete']} |
| Existing Gemini profiles / usable specific-style mappings | {counts['gemini_complete']} / {counts['genre_available_complete']} |
| Common audio + existing profile population | {counts['common_audio_genre_profile_population']} |

The full corpus still lacks {counts['distinct_retained_recordings']-counts['gemini_complete']}
Gemini profiles. Completing Method C does not silently substitute the smaller
profile-covered population for the full corpus. Profile presence and usable
specific-style mapping are reported separately. No new Gemini calls occurred.

The GPU handoff required terminal acquisition states, actual process exit and
released VRAM. Its predeclared CPU/GPU parity check passed on
{len(parity['comparisons'])} chunk comparisons; maximum component difference was
{max(r['max_abs_error'] for r in parity['comparisons']):.9g}, and minimum cosine was
{min(r['cosine'] for r in parity['comparisons']):.12g}. Completed CPU outputs and
original ledgers were preserved. Engineering parity attempts are counted
separately from extraction; any interrupted CPU chunk attempts remain in the
original append-only ledgers.

Continuation validation caught a float32 cast in the original CPU resume path.
{counts['pooling_repairs_without_inference']} affected pool was reconstructed from unchanged
original float64 chunk vectors, with no inference. The original artifact remains
intact, and the corrected continuation records explicit source hashes and repair
provenance. A regression test reproduces the original failure and verifies that
future resumes preserve the original chunk values exactly.

The ordered full Method C matrix and common-population submatrix passed
symmetry, diagonal and byte-replay checks. The replay reused
{verification['replay']['cached']} features with **zero inference calls**.
Historical input/source and published-artifact integrity checks passed.

The focused suite passed **{tests['focused_passed']} tests**.
The final non-heavy suite passed **{tests['passed']} tests**;
{tests['heavy_excluded']} heavy tests were excluded and {tests['warnings']} warnings
were reported. Focused fixtures cover native chunk boundaries, explicit legacy
boundary failure, incomplete-track resume, source/config mismatch rejection,
zero-encoder replay, matrix ordering/symmetry/byte replay, separate readiness,
and acquisition-release/continuation guards.

## Artifacts

Private run: `{RUN}`.
Full matrix SHA-256: `{verification['matrix']['sha256']}`.
Configuration SHA-256: `{verification['configuration_sha256']}`.
Corpus SHA-256: `{verification['corpus_sha256']}`.
Private artifact-manifest SHA-256: `{evidence['private_artifact_manifest_sha256']}`.
See `execution_validation.json`, `track_status.json`, and ordered ID sidecars
for exact counts, hashes, status rows and validation details.

No weight search, calibration, representation selection, playlist mutation or
production activation was performed. Source identity is hash-linked to retained
validated acquisitions; it is not a claim of owner listening verification for
every recording. Split and source-use feasibility remain separate from this
feature-materialization result.
'''
    target=output/'REPORT.md'
    require(not target.exists() or target.read_text()==report,'published report differs')
    if not target.exists():target.write_text(report)
    manifest={str(p.relative_to(output)):file_hash(p) for p in sorted(output.rglob('*')) if p.is_file() and p.name!='artifact_manifest.json'}
    freeze_json(output/'artifact_manifest.json',{'files':manifest})
    return {'report':str(target),'status':readiness['status'],'tests':tests}


if __name__=='__main__':
    print(publish(Path.cwd()))
