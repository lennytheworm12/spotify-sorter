"""Read-only reuse of Stage 5E corpus and rating provenance."""
import csv
from pathlib import Path
from .stage5e3_artifacts import read, hashes
from .stage5e2 import audit_labels, resolve_labels
from .stage5c2_analysis import canonical_pair_id
from .stage5f1_inputs import frozen_tracks, _current_stage5e2_evidence
from .stage5b1a_models import file_sha256

PRIOR=Path('reports/stage5e1_four_arm_retrieval')
SELECTED=Path('reports/stage5c2_representative_100_amended_v2/selected_sources.json')


def tracks_and_baselines(root):
    tracks=frozen_tracks(root,'original100')
    if len(tracks)!=100 or len({t['spotify_track_id'] for t in tracks})!=100:
        raise ValueError('expected exactly 100 unique amended identities')
    for t in tracks:
        p=Path(t['retained_source_path'])
        if not p.is_file(): raise ValueError(f"SOURCE_MISSING: {t['spotify_track_id']}")
        if file_sha256(p)!=t['source_sha256']: raise ValueError(f"SOURCE_CHANGED: {t['spotify_track_id']}")
        t['retained_source_path']=str(p.relative_to(root))
    config=read(root/PRIOR/'experiment_config.json')
    expected={'A':'A_CENTERED30_CURRENT_MUSIC_CLAP_V1','C':'C_FULL_SONG_10S_CHUNK_MEAN_MUSIC_CLAP_V1','D':'D_NATIVE_GLOBAL3_EQUAL_MEAN_GENERAL_AUDIO_CLAP_V1'}
    for arm,identity in expected.items():
        if config['arms'][arm]['identity']!=identity: raise ValueError('historical arm changed')
    for arm in ('A','C'):
        if config['arms'][arm]['checkpoint_sha256']!='fae3e9c087f2909c28a09dc31c8dfcdacbc42ba44c70e972b58c1bd1caf6dedd': raise ValueError('A/C checkpoint changed')
    if config['arms']['D']['checkpoint_sha256']!='fb171dd9b608aebdac3d89286cd7615c5100af4cc7dc37797c7fb8d3cc15e3a5': raise ValueError('D checkpoint changed')
    fixed=config['fixed_muq']
    if fixed['centers_seconds']!=[5,15,25] or fixed['window_seconds']!=5 or fixed['sample_rate_hz']!=24000 or fixed['representation']!='centered30_v1': raise ValueError('fixed MuQ changed')
    if config['similarity']['clap_weight']!=.7172981519 or config['similarity']['muq_weight']!=.2827018481: raise ValueError('fusion weights changed')
    return tracks,config


def eligible(a,b):
    return (a['spotify_track_id']!=b['spotify_track_id'] and a['source_sha256']!=b['source_sha256']
            and a['youtube_video_id']!=b['youtube_video_id'])


def rating_snapshot(root,tracks):
    by={t['spotify_track_id']:t for t in tracks}
    audit,evidence=audit_labels(root,by)
    current=_current_stage5e2_evidence(root,set(by))
    queue_path=root/'reports/stage5e2_arm_d_original100_v2/review_queue.json'
    qp={p['pair_id']:p for p in read(queue_path)['pairs']}
    state=root/'.research_audio/stage5e2_original100_v2_review/human_similarity_review.csv'
    current_rows={}
    if state.is_file():
        with state.open(newline='',encoding='utf-8-sig') as handle:
            current_rows={r['pair_id']:r for r in csv.DictReader(handle)}
    for row in current:
        raw=current_rows[row['pair_id']]
        if canonical_pair_id(raw['left_spotify_id'],raw['right_spotify_id'])!=row['pair_id']:
            raise ValueError('current review row identity mismatch')
        pair=qp[row['pair_id']]
        if all(side['source_sha256']==by[side['spotify_track_id']]['source_sha256'] and side['youtube_video_id']==by[side['spotify_track_id']]['youtube_video_id'] for side in (pair['left'],pair['right'])):
            evidence.append(row)
    # Reuse derived evidence only if its original file still has the recorded hash.
    derived=[]
    for rel in ('reports/stage5e2_arm_d_original100_v2/label_evidence.json','reports/stage5f1_energy_motion/energy_motion_v1/label_evidence.json'):
        path=root/rel
        if path.is_file():
            obj=read(path); entries=obj if isinstance(obj,list) else obj.get('evidence',[])
            matched=0
            for row in entries:
                original=root/row.get('source','')
                if original.is_file() and file_sha256(original)==row.get('source_sha256'):
                    # Only retain if the live source already passed identity/semantics audit.
                    if any(e['pair_id']==row.get('pair_id') and e['source']==row.get('source') and e['label']==row.get('label') for e in evidence): matched+=1
            derived.append({'path':rel,'sha256':file_sha256(path),'rows':len(entries),'deduplicated_against_original':matched,'decision':'DERIVED_NOT_INDEPENDENT'})
    valid_pairs={canonical_pair_id(a['spotify_track_id'],b['spotify_track_id']):(a['spotify_track_id'],b['spotify_track_id']) for a in tracks for b in tracks if eligible(a,b)}
    prompt_files={'stage5c2-human-similarity-review-v2':'evaluation/static/stage5c2_similarity_review.html',
                  'stage5e1-human-similarity-review-v1':'evaluation/static/stage5e1_blinded_review.html'}
    sources={e['source'] for e in evidence}; accepted=[]; source_audit=[]
    for source in sorted(sources):
        path=root/source
        with path.open(newline='',encoding='utf-8-sig') as f: source_rows=list(csv.DictReader(f))
        schemas=sorted({r.get('review_schema_version','') for r in source_rows})
        known=len(schemas)==1 and schemas[0] in prompt_files
        prompt=root/prompt_files[schemas[0]] if known else None
        text=prompt.read_text() if prompt else ''
        known=known and 'Not similar' in text and 'Extremely similar' in text
        source_audit.append({'path':source,'sha256':file_sha256(path),'schemas':schemas,
          'decision':'ACCEPT_HOLISTIC_SIMILARITY' if known else 'SEMANTICS_UNRESOLVED',
          'prompt_artifact':str(prompt.relative_to(root)) if prompt else None,
          'prompt_sha256':file_sha256(prompt) if prompt else None,
          'prompt':'Rate each unordered pair for sonic similarity only' if schemas==['stage5c2-human-similarity-review-v2'] else 'Compare only the musical sound of these two tracks.',
          'scale':{'1':'Not similar','2':'Somewhat related','3':'Moderately similar','4':'Very similar','5':'Extremely similar','UNSURE':'UNSURE / SKIP'},
          'identity_scheme':'canonical unordered Spotify pair plus frozen source/video identity'})
        if known:
            accepted.extend(e|{'semantic_tag':'HOLISTIC_SIMILARITY','prompt_scale_id':schemas[0],
                               'compatibility_decision':'ACCEPT_HOLISTIC_SIMILARITY'} for e in evidence if e['source']==source and e['pair_id'] in valid_pairs)
    unique={ (e['source'],e['source_sha256'],e['pair_id'],e['label'],e.get('timestamp',''),e.get('note','')):e for e in accepted}
    accepted=[unique[k] for k in sorted(unique)]
    labels,conflicts=resolve_labels(accepted)
    return {'sources':source_audit,'discovery_audit':audit,'derived_exports':derived}, {
        'labels':labels,'conflicts':conflicts,'evidence':accepted,
        'pairs':{p:list(sorted(valid_pairs[p])) for p in sorted(valid_pairs)},
        'semantic_tags':{p:'HOLISTIC_SIMILARITY' for p in labels}}


def historical_hashes(root):
    paths=[]
    for pattern in ('stage5e*','stage5c2*','stage5f1*'):
        for directory in (root/'reports').glob(pattern):
            if directory.name.startswith('stage5e3'): continue
            paths.extend(p for p in directory.rglob('*') if p.is_file())
    for directory in (root/'artifacts').glob('stage5e*'):
        if not directory.name.startswith('stage5e3'): paths.extend(p for p in directory.rglob('*') if p.is_file())
    paths.extend((root/'configs').glob('*.json'))
    paths.extend((root/'.research_audio').glob('**/*review*.csv'))
    return hashes(paths,root)
