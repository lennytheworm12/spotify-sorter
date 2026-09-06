"""Create-once preparation, frozen input hashes, and offline model identity."""
import importlib.metadata
import os
import platform
import subprocess
from pathlib import Path
from .stage5e3_artifacts import read, freeze_json, digest, hashes, verify_hashes
from .stage5e3_inputs import tracks_and_baselines,rating_snapshot,historical_hashes,PRIOR
from .full_song_muq import POLICY

REPORT=Path('reports/stage5e3_full_song_muq_playlist_compatibility/frozen100_v1')
MODEL_REVISION='2e01c796b71dca71b45251384c04cd7b237c9020'


def code_hashes(root):
    files=list((root/'src/audio_similarity').glob('stage5e3*.py'))
    files += [root/'src/audio_similarity/full_song_muq.py',root/'src/audio_similarity/playlist_compatibility_eval.py']
    files += list((root/'src/audio_similarity/cli').glob('stage5e3*.py'))
    files += list((root/'evaluation/static').glob('stage5e3*'))
    files += [root/'src/audio_similarity'/name for name in ('stage5e2.py','stage5e1_review.py','stage5f1_inputs.py','stage5c2_analysis.py','stage5b1a_models.py','stage5b1b_artifacts.py','stage5a_contract.py')]
    files += [root/'src/audio_similarity/cli/stage5b1b_review_server.py']
    files += list((root/'tests').glob('test_stage5e3*'))+[root/'tests/test_full_song_muq.py']
    return hashes(files,root)


def model_identity(root):
    from .stage5b1a_models import file_sha256
    hub=Path(os.environ.get('HF_HUB_CACHE',str(Path.home()/'.cache/huggingface/hub')))
    snapshot=hub/'models--OpenMuQ--MuQ-MuLan-large/snapshots'/MODEL_REVISION
    model=snapshot/'pytorch_model.bin';config=snapshot/'config.json'
    if not model.is_file() or not config.is_file(): raise ValueError('required frozen local MuQ checkpoint unavailable; downloads prohibited')
    from .stage5a_contract import load_contract
    historical=load_contract(root/'reports/holistic_stage4a_dual/audio_representation_v1.json').encoder('muq_mulan_large').provenance
    if historical['revision']!=MODEL_REVISION or historical['weights_sha256']!=file_sha256(model) or historical['config_sha256']!=file_sha256(config):
        raise ValueError('MuQ differs from historical representation model')
    cfg=read(config)['mulan']
    if (cfg['sr'],cfg['clip_secs'],cfg['dim_latent'])!=(24000,10,512): raise ValueError('MuQ model config mismatch')
    packages={name:importlib.metadata.version(name) for name in ('numpy','torch','torchaudio','muq','transformers','huggingface-hub','pyarrow')}
    import torch
    env={'packages':packages,'python':platform.python_version(),'cuda':torch.version.cuda,
         'device':torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'cpu',
         'threads':1,'autocast':False,'tf32':False,'deterministic_algorithms':True}
    # Record all locally cached model dependencies; never resolve remote revisions.
    dependencies={}
    for repo in ('models--OpenMuQ--MuQ-large-msd-iter','models--xlm-roberta-base'):
        directory=hub/repo
        dependencies[repo]={str(p.relative_to(directory)):file_sha256(p) for p in sorted((directory/'snapshots').glob('*/*')) if p.is_file()}
        if not dependencies[repo]: raise ValueError(f'missing offline dependency: {repo}')
    env['model_dependency_files']=dependencies
    import muq
    muq_path=Path(muq.__file__).parent
    env['muq_source_hashes']=hashes(muq_path.rglob('*.py'),muq_path)
    embedding_code=hashes([root/'src/audio_similarity'/name for name in ('full_song_muq.py','stage5e3_cache.py','holistic_encoders.py','audio.py')],root)
    return POLICY|{'model_identity':'OpenMuQ/MuQ-MuLan-large','model_revision':MODEL_REVISION,
                   'model_file_sha256':file_sha256(model),'model_config_sha256':file_sha256(config),
                   'model_snapshot_path':str(snapshot),'muq_package_version':packages['muq'],
                   'implementation_sha':digest(embedding_code),'embedding_code_files':embedding_code,
                   'embedding_environment_hash':digest(env)},env


def prepare(root,run):
    root=Path(root).resolve();run=Path(run)
    if (run/'preparation_status.json').exists():
        verify_prepared(root,run)
        return read(run/'preparation_status.json')
    tracks,baseline=tracks_and_baselines(root)
    audit,labels=rating_snapshot(root,tracks)
    config,environment=model_identity(root)
    historical=historical_hashes(root)
    historical.update(hashes([root/'docs/designs/stage5e3_revision2.md',root/'docs/designs/stage5e3_handoff_goal.md',root/'uv.lock',root/'reports/holistic_stage4a_dual/audio_representation_v1.json'],root))
    implementation=code_hashes(root)
    source_hashes={t['retained_source_path']:t['source_sha256'] for t in tracks}
    for name,obj in {
        'source_manifest.json':{'track_count':100,'tracks':tracks},
        'baseline_reference.json':{'configuration':baseline,'sampling_plans':read(root/PRIOR/'sampling_plans.json'),
                                   'materialization_provenance':read(root/PRIOR/'materialization_results.json'),
                                   'offset_interpretation':'Use recorded per-track provenance; do not reinterpret centered30 labels.'},
        'full_song_muq_config.json':config,'environment.json':environment,
        'rating_compatibility_audit.json':audit,'pre_review_rating_snapshot.json':labels,
        'input_reference.json':{'historical':historical,'source_hashes':source_hashes,'implementation':implementation,
                                'repository_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()},
        'algorithm_spec.json':{'governing_design_sha256':historical['docs/designs/stage5e3_revision2.md'],
          'policy':POLICY,'evaluation_implementation':implementation,'seed':20260906,
          'shuffle':'SHA256(seed:namespace:stable_id), lexical hash then stable ID',
          'decoder':'shared load_audio; float32 channel mean before torchaudio default resample; full recording',
          'serialization':{'json':'sorted UTF8 finite indent2 final newline','npz':'sorted NPY members, stored ZIP, timestamp 1980-01-01',
                           'parquet':'2.6 NONE compression, no dictionary, statistics, row_group_size=65536; rows sorted by documented keys'},
          'parquet_sort_keys':{'chunk_manifest':['spotify_track_id','chunk_index'],'retrieval':['method_id','query','rank'],
                               'union':['query','candidate'],'probes':['query','pair_id']}},
        'experiment_config.json':{'revision':2,'weights':{'CLAP':.7172981519,'MuQ':.2827018481},'seed':20260906,
                                  'full_song_muq_config_hash':digest(config),'human_boundary':'READY_FOR_HUMAN_REVIEW'},
        'review_playback_policy.json':{'source':'full retained recording','initial_state':'paused_at_zero','seeking':True,
                                       'gain':'identical native player defaults; user volume permitted','minimum_listening_seconds':None},
    }.items(): freeze_json(run/name,obj)
    status={'status':'PREPARED','tracks':100,'configuration_hash':digest(config)}
    freeze_json(run/'preparation_manifest.json',hashes(run.glob('*.json'),run))
    freeze_json(run/'preparation_status.json',status)
    return status


def verify_prepared(root,run):
    verify_hashes(run,read(run/'preparation_manifest.json'))
    reference=read(run/'input_reference.json')
    verify_hashes(root,reference['historical']);verify_hashes(root,reference['source_hashes'])
    verify_hashes(root,reference['implementation'])
    return True
