"""Read-only inputs for canonical-first frozen100 development exploration."""
import argparse
from pathlib import Path
import numpy as np
from .genre_registry_review import mapper
from .stage5b1a_models import file_sha256
from .stage5e3_artifacts import freeze_json, read, verify_hashes

CONFIG = Path('configs/genre_force_v1')
SOURCE = Path('reports/gemini_style_pilot/frozen100_free_genre_v1')
E3 = Path('reports/stage5e3_full_song_muq_playlist_compatibility/frozen100_v3')
MAP = Path('.research_audio/song_space/v3/clap-c.json')
AUDIO_KEYS = {'M3_C_PLUS_FIXED_MUQ': 'Frozen C + existing centered30 MuQ (Stage 5E.3 M3)',
              'M4_C_PLUS_FULL_MUQ': 'Frozen C + full-song MuQ (Stage 5E.3 M4)'}


def canonical_profile(profile, engine, force):
    """Keep explicit families in canonical Jaccard, gated by specific style evidence."""
    mapped = engine.profile(profile)
    weights = force['representations']['canonical']['field_weights']
    eligible = force['representations']['canonical']['eligible']
    canonical, excluded, specific = {}, {}, set()
    for trace in mapped['label_traces']:
        for cid in trace['concept_ids']:
            c = engine.concepts[cid]
            if c['mapping_review_required'] or c['kind'] not in eligible:
                excluded[cid] = {'id': cid, 'label': c['label'], 'reason':
                                 'mapping review required' if c['mapping_review_required'] else c['kind'] + ': display only'}
                continue
            canonical[cid] = max(canonical.get(cid, 0), weights[trace['source_field']])
            # Rap/electronica are explicitly broad umbrellas in this registry; they
            # are eligible canonical context but cannot open the specificity gate.
            if c['kind'] == 'style':
                specific.add(cid)
    return {'canonical': dict(sorted(canonical.items())), 'specificStyleIds': sorted(specific),
            'neighborhoods': mapped['neighborhood_memberships'], 'excluded': [excluded[k] for k in sorted(excluded)],
            'warnings': [f"{t['raw_label']}: {t['status']} ({t['rule']})" for t in mapped['unresolved_labels']],
            'traces': mapped['label_traces']}


def load_audio(root, key):
    if key not in AUDIO_KEYS:
        raise ValueError('Select an explicit frozen C + MuQ matrix; no implicit baseline')
    with np.load(root / E3 / 'similarity_matrices.npz', allow_pickle=False) as data:
        ids, matrix = list(map(str, data['spotify_ids'])), data[key].copy()
    if len(ids) != 100 or len(set(ids)) != 100 or matrix.shape != (100,100) or not np.isfinite(matrix).all() or not np.array_equal(matrix,matrix.T):
        raise ValueError('Exact symmetric frozen100 matrix required')
    return ids, matrix


def build(root, output, key):
    root, output = Path(root).resolve(), Path(output).resolve()
    if not output.is_relative_to(root / '.research_audio/genre_force'):
        raise ValueError('Use a separate .research_audio/genre_force run')
    force = read(root/CONFIG/'genre-force-explorer-v1.json')
    if force['schema_version'] != 'genre-force-explorer-v1.2' or force['scoring_revision'] != 'canonical-first-residual-v1':
        raise ValueError('Unsupported current scoring contract')
    if file_sha256(root/CONFIG/'genre-neighborhood-map-v1.json') != file_sha256(root/'configs/genre_registry_v1/genre-neighborhood-map-v1.json'):
        raise ValueError('Reference mapper registry differs from current vault registry')
    # Existing public manifests verify source profiles and original scoring evidence.
    for directory in (SOURCE, E3):
        verify_hashes(root/directory, read(root/directory/'artifact_manifest.json')['files'])
    execution=read(root/SOURCE/'execution_manifest.json')
    historical={t['spotify_track_id']:t for t in read(root/E3/'source_manifest.json')['tracks']}
    ids,matrix=load_audio(root,key)
    tracks=execution['tracks']
    if {t['spotify_track_id'] for t in tracks} != set(ids) or len(tracks)!=100:
        raise ValueError('Frozen genre/audio membership differs')
    engine=mapper(root)
    if len(engine.concepts)!=138 or len(engine.config['neighborhoods'])!=29:
        raise ValueError('Use the 138-concept / 29-neighborhood mapper')
    concepts={c['id']:{'id':c['id'],'label':c['label'],'kind':c['kind'],
              'neighborhoods':{n:force_value for n,rel in c['neighborhoods'].items()
                 for force_value in [engine.config['membership_proposal'][rel+'_relation_strength']]} }
              for c in engine.config['concepts'] if not c['mapping_review_required'] and c['kind'] in force['representations']['canonical']['eligible']}
    songs,index,source_checks=[],{},[]
    for t in sorted(tracks,key=lambda t:t['spotify_track_id']):
        tid=t['spotify_track_id'];p=root/SOURCE/'profiles'/f"{t['pilot_id']}.json";profile=read(p)
        if profile['spotify_track_id']!=tid:raise ValueError('Profile identity differs')
        prepared=t['prepared'];audio_path=root/execution['prepared_root']/prepared['prepared_filename']
        if not prepared['full_recording_preserved'] or file_sha256(audio_path)!=prepared['prepared_sha256']:
            raise ValueError('Prepared audio missing, changed or partial')
        if file_sha256(root/t['retained_source_path'])!=t['source_sha256']:
            raise ValueError('Retained source has changed')
        source_match=t['source_sha256']==historical[tid]['source_sha256']
        mapped=canonical_profile(profile['profile'],engine,force)
        if not source_match:mapped['warnings'].append('Gemini source differs from frozen audio-score source; compare provenance before interpreting this pair.')
        source_checks.append({'id':tid,'profile_sha256':file_sha256(p),'prepared_sha256':prepared['prepared_sha256'],
            'gemini_source_sha256':t['source_sha256'],'frozen_representation_source_sha256':historical[tid]['source_sha256'],
            'same_source':source_match})
        songs.append({'id':tid,'pilotId':t['pilot_id'],'title':t['catalog_title'],'artists':t['catalog_artists'],
                      'durationSeconds':prepared['duration_seconds'],'audioUrl':'/__song-space/genre/audio/'+tid,
                      'raw':profile['profile'],**mapped})
        index[tid]={'path':str(audio_path),'sha256':prepared['prepared_sha256']}
    pairs=[{'a':a,'b':b,'audio':float(matrix[i,j])} for i,a in enumerate(ids) for j,b in enumerate(ids) if a<b]
    pairs.sort(key=lambda p:(p['a'],p['b']))
    paths=[root/E3/'similarity_matrices.npz',root/E3/'source_manifest.json',root/E3/'artifact_manifest.json',
           root/SOURCE/'artifact_manifest.json',root/MAP,root/'configs/genre_registry_v1/mapper_reference.py',Path(__file__),
           *(p for p in (root/CONFIG).iterdir() if p.is_file())]
    provenance={'audio_matrix_key':key,'input_hashes':{str(p.relative_to(root)):file_sha256(p) for p in paths},
                'source_checks':source_checks,'inference_calls':0,'old_mapper_used':False,
                'specificity_gate':'at least one reviewed kind=style concept on both endpoints; family/rap/electronica alone do not open gate',
                'tie_break':'descending exact score then Spotify ID ascending','parameter_policy':'manual development only; beta UI 0..0.20; eta 0..1',
                'unrated_pairs':'No ratings are read or manufactured; rank changes are not accuracy gains'}
    freeze_json(output/'input.json',{'schemaVersion':'genre-force-explorer-v1','songs':songs,'pairs':pairs,'concepts':concepts,
                'neighborhoodLabels':{k:v['label'] for k,v in engine.config['neighborhoods'].items()},
                'defaults':{'alpha':0,'beta':force['beta']['default'],'eta':force['eta']['default'],'genreMode':'canonical_plus_residual','forceMode':'pull_only'},
                'audioIdentity':AUDIO_KEYS[key],'provenance':provenance,
                'coordinateOrigin':'Existing frozen100 CLAP C Song Space view (v3), recreated with its unchanged deterministic layout engine. C + MuQ scores are a separate frozen source.'})
    freeze_json(output/'audio-index.json',index)
    freeze_json(output/'base-map.json',read(root/MAP))
    freeze_json(output/'input_manifest.json',{'files':{n:file_sha256(output/n) for n in ['input.json','audio-index.json','base-map.json']}})
    for directory in (SOURCE,E3):verify_hashes(root/directory,read(root/directory/'artifact_manifest.json')['files'])
    return {'tracks':100,'pairs':len(pairs),'audio_key':key,'specific_style_tracks':sum(bool(s['specificStyleIds']) for s in songs),
            'source_mismatches':sum(not s['same_source'] for s in source_checks),'inference_calls':0}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--audio-key',choices=AUDIO_KEYS,required=True);a=p.parse_args()
    root=Path(__file__).resolve().parents[2];print(build(root,root/a.output,a.audio_key))


if __name__=='__main__':main()
