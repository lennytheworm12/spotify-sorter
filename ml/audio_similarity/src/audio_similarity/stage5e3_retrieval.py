"""Frozen both-axis retrieval and globally unique blinded packet assignment."""
import hashlib
import numpy as np
from .stage5c2_analysis import canonical_pair_id
from .stage5e3_inputs import eligible
from .playlist_compatibility_eval import METHODS, SEED, numeric

QUESTION='How well do the anchor track and candidate track belong in the same coherent playlist group?'
RUBRIC={'5':'Definitely belong in the same coherent playlist group.',
        '4':'Probably belong; the pairing feels cohesive.',
        '3':'Borderline; the pairing could work, but is not strongly cohesive.',
        '2':'Probably should not belong in the same coherent playlist group.',
        '1':'Definitely should not belong in the same coherent playlist group.',
        'UNSURE':'I cannot judge this pair with enough confidence.'}


def shuffled(values, namespace):
    return sorted(values,key=lambda v:(hashlib.sha256(f'{SEED}:{namespace}:{v}'.encode()).hexdigest(),v))


def rank_tracks(tracks,matrices):
    ids=[t['spotify_track_id'] for t in tracks]
    if ids!=sorted(set(ids)): raise ValueError('track IDs must be sorted and unique')
    rows=[]
    for method in METHODS:
        matrix=matrices[method]
        if matrix.shape!=(len(ids),len(ids)) or not np.isfinite(matrix).all(): raise ValueError('invalid matrix')
        for i,q in enumerate(tracks):
            candidates=[j for j,c in enumerate(tracks) if eligible(q,c)]
            ordered=sorted(candidates,key=lambda j:(-float(matrix[i,j]),ids[j]))[:5]
            for rank,j in enumerate(ordered,1):
                rows.append({'method_id':method,'query':ids[i],'candidate':ids[j],
                             'pair_id':canonical_pair_id(ids[i],ids[j]),'rank':rank,'score':float(matrix[i,j])})
    return rows


def public_track(track):
    return {k:track[k] for k in ('spotify_track_id','title','artists')}|{'audio_url':'/audio/track/'+track['spotify_track_id']}


def build_packets(tracks,rows,snapshot):
    by={t['spotify_track_id']:t for t in tracks};ids=sorted(by)
    union={q:{r['candidate'] for r in rows if r['query']==q} for q in ids}
    labels=snapshot['labels'];probes=[]
    for q in ids:
        for kind in ('good','bad'):
            choices=[]
            for c in ids:
                if c == q: continue
                p=canonical_pair_id(q,c)
                value=labels.get(p)
                if c not in union[q] and eligible(by[q],by[c]) and numeric(value) and (value>=4 if kind=='good' else value<=2): choices.append(p)
            if choices:
                p=shuffled(sorted(choices),f'probe:{q}:{kind}')[0]
                sides=snapshot['pairs'][p];c=next(t for t in sides if t!=q)
                probes.append({'query':q,'candidate':c,'pair_id':p,'probe_type':kind})
    natural={r['pair_id'] for r in rows}
    repeat={p['pair_id'] for p in probes}
    needed=(natural-labels.keys())|repeat
    seen=set();packets=[];hidden=[]
    # One global assignment among all eligible natural/probe appearances.
    for q in shuffled(ids,'anchors'):
        appearances={canonical_pair_id(q,c):c for c in union[q]}
        appearances.update({p['pair_id']:p['candidate'] for p in probes if p['query']==q})
        candidates=[]
        for p in shuffled(sorted(appearances),f'candidates:{q}'):
            if p not in needed or p in seen: continue
            seen.add(p);c=appearances[p]
            candidates.append({'pair_id':p,'track':public_track(by[c])})
            hidden.append({'pair_id':p,'assigned_anchor':q,'candidate':c,'drift_repeat':p in repeat,
                           'conflicted':p in snapshot['conflicts']})
        if candidates:
            packets.append({'packet_id':hashlib.sha256(f'packet:{SEED}:{q}'.encode()).hexdigest(),
                            'anchor':public_track(by[q]),'candidates':candidates})
    if seen!=needed: raise ValueError('review assignment incomplete')
    counts={'natural_directional_slots':len(rows),'natural_unique_pairs':len(natural),
            'all_unique_pairs':len(natural|repeat),'compatible_reused_natural_pairs':len(natural&labels.keys()),
            'reused_without_repeat':len((natural&labels.keys())-repeat),
            'unresolved_natural_pairs':len(natural-labels.keys()),
            'conflicted_natural_pairs':len(natural&snapshot['conflicts'].keys()),
            'unresolved_nonconflicted_pairs':len(natural-labels.keys()-snapshot['conflicts'].keys()),
            'drift_repeat_pairs':len(repeat),'probe_directional_appearances':len(probes),
            'review_unique_pairs':len(needed),'packets':len(packets)}
    return {'question':QUESTION,'rubric':RUBRIC,'packets':packets},probes,hidden,counts
