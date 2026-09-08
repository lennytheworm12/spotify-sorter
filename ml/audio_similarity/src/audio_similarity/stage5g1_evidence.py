"""Inventory human-only supervision and split tracks before feature extraction."""
from collections import Counter, defaultdict
from itertools import combinations
import hashlib
from pathlib import Path

from .stage5e2 import audit_labels, resolve_labels
from .stage5f1_inputs import frozen_tracks, _current_stage5e2_evidence
from .stage5c2_analysis import canonical_pair_id
from .stage5e3_artifacts import read, freeze_json, hashes


def preferences(pairs, ids):
    allowed=set(ids); neighbors=defaultdict(dict)
    for p in pairs:
        a,b=p['tracks']
        if a in allowed and b in allowed:
            neighbors[a][b]=p['rating'];neighbors[b][a]=p['rating']
    result=[];ties=0
    for a in sorted(neighbors):
        for b,c in combinations(sorted(neighbors[a]),2):
            rb,rc=neighbors[a][b],neighbors[a][c]
            if rb==rc:ties+=1;continue
            better,worse=(b,c) if rb>rc else (c,b)
            result.append({'anchor':a,'preferred':better,'other':worse,'gap':abs(rb-rc)})
    return result,ties


def split_tracks(tracks, artist=False):
    parent={t['spotify_track_id']:t['spotify_track_id'] for t in tracks}
    def find(x):
        while parent[x]!=x:
            parent[x]=parent[parent[x]];x=parent[x]
        return x
    seen={}
    for t in sorted(tracks,key=lambda t:t['spotify_track_id']):
        id=t['spotify_track_id'];keys=[('sha',t['source_sha256']),('video',t['youtube_video_id'])]
        if artist:keys += [('artist',a.casefold().strip()) for a in t['artists'] if a.strip()]
        for key in keys:
            if key in seen:parent[find(id)]=find(seen[key])
            seen[key]=id
    groups=defaultdict(list)
    for id in parent:groups[find(id)].append(id)
    groups=sorted((sorted(g) for g in groups.values()),key=lambda g:hashlib.sha256(f'stage5g1:20260908:{g[0]}'.encode()).hexdigest())
    output={k:[] for k in ('train','validation','test')};count=0
    for group in groups:
        name='train' if count<len(tracks)*.6 else 'validation' if count<len(tracks)*.8 else 'test'
        output[name]+=group;count+=len(group)
    return {k:sorted(v) for k,v in output.items()}


def split_inventory(tracks,pairs,gate,artist=False):
    split=split_tracks(tracks,artist);stats={};constraints={}
    for name,ids in split.items():
        ps,ties=preferences(pairs,ids);constraints[name]=ps
        stats[name]={'tracks':len(ids),'rated_pairs':sum(set(p['tracks'])<=set(ids) for p in pairs),
                     'anchors':len({p['anchor'] for p in ps}),'preferences':len(ps),'ties':ties,
                     'strong_preferences':sum(p['gap']>=2 for p in ps)}
        stats[name]['passes']=all(stats[name][key]>=value for key,value in gate[name].items())
    stats['passes']=all(stats[n]['passes'] for n in split)
    stats['cross_partition_pairs']=len(pairs)-sum(stats[n]['rated_pairs'] for n in split)
    return {'partitions':split,'counts':stats,'constraints':constraints}


def inventory(root, run, config):
    tracks=frozen_tracks(root,'reference741');by={t['spotify_track_id']:t for t in tracks}
    audit,ev=audit_labels(root,by);ev+=_current_stage5e2_evidence(root,set(by))
    # Exact source exports are provenance copies, not additional supervision.
    unique={(e['pair_id'],e['source'],e['source_sha256'],e['label']):e for e in ev}
    ev=[unique[k] for k in sorted(unique)];labels,conflicts=resolve_labels(ev)
    uncertain={e['pair_id'] for e in ev if e['label'] in ('UNSURE','SKIP')}
    endpoints={canonical_pair_id(a,b):(a,b) for a,b in combinations(sorted(by),2) if canonical_pair_id(a,b) in labels}
    pairs=[{'pair_id':p,'tracks':list(endpoints[p]),'rating':labels[p]} for p in sorted(labels)
           if p not in uncertain and by[endpoints[p][0]]['source_sha256']!=by[endpoints[p][1]]['source_sha256']
           and by[endpoints[p][0]]['youtube_video_id']!=by[endpoints[p][1]]['youtube_video_id']]
    ids=sorted({id for p in pairs for id in p['tracks']});selected=[by[id] for id in ids]
    all_prefs,ties=preferences(pairs,ids)
    primary=split_inventory(selected,pairs,config['gate']);artist=split_inventory(selected,pairs,config['gate'],True)
    degree=Counter(id for p in pairs for id in p['tracks']);artists=Counter(a.casefold().strip() for t in selected for a in t['artists'])
    playlist=read(root/'reports/stage5e3_full_song_muq_playlist_compatibility/frozen100_v3/post_review_rating_snapshot.json')
    stats={'compatible_tracks':len(ids),'unique_numeric_pairs_before_uncertainty_exclusion':len(labels),'whole_song_similarity_pairs':len(pairs),
           'anchors_with_different_ratings':len({p['anchor'] for p in all_prefs}),'preference_constraints':len(all_prefs),
           'tied_candidate_comparisons':ties,'conflicts':conflicts,'uncertain_pairs':sorted(uncertain),
           'track_pair_degree':dict(sorted(degree.items())),'credited_artist_track_counts':dict(sorted(artists.items())),
           'unique_credited_artists':len(artists),'primary_split':primary['counts'],'artist_split':artist['counts'],
           'stage5e3_playlist_judgments':sum(len(e['answers']) for e in playlist['events']),
           'stage5e3_decision':'separate semantic target; excluded from primary; not duplicate similarity labels',
           'stage2b_decision':'FMA centered5 excerpt preference, different identities; excluded',
           'stage5f1_decision':'derived historical ratings; no independent new supervision; no MIR features used',
           'gate_passes':primary['counts']['passes']}
    for t in selected:t['retained_source_path']=str(Path(t['retained_source_path']).relative_to(root))
    freeze_json(run/'supervision_inventory.json',stats);freeze_json(run/'source_audit.json',audit)
    freeze_json(run/'human_evidence.json',{'evidence':ev,'pairs':pairs});freeze_json(run/'tracks.json',selected)
    freeze_json(run/'split.json',primary);freeze_json(run/'artist_split.json',artist)
    return stats
