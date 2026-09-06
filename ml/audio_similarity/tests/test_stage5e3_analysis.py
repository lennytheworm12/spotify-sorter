import numpy as np
import pytest
from audio_similarity.playlist_compatibility_eval import METHODS,choose_verdict,point_accept,gain,interval,comparison,positive_bank,analyze_fixture
from audio_similarity.stage5c2_analysis import canonical_pair_id


def fixture():
    ids=[f't{i:03d}' for i in range(100)];rows=[];labels={};pairs={}
    for i,q in enumerate(ids):
        for j in range(1,6):
            c=ids[(i+j)%100];p=canonical_pair_id(q,c);labels[p]=4;pairs[p]=[q,c]
            for m in METHODS:rows.append({'method_id':m,'query':q,'candidate':c,'pair_id':p,'rank':j,'score':.9-j*.01})
    return ids,rows,labels,pairs

@pytest.mark.parametrize('edges,expected',[
 ([(1,3,'ROBUST_WIN'),(1,4,'ROBUST_WIN')],'RECOMMEND_C_CLAP_FOUNDATION'),
 ([(4,3,'ROBUST_WIN'),(4,1,'ACCEPT')],'RECOMMEND_C_PLUS_FULL_MUQ_FOUNDATION'),
 ([(2,3,'ROBUST_WIN'),(2,4,'ROBUST_WIN')],'FULL_MUQ_PROMISING_FUSION_UNRESOLVED'),
 ([(3,4,'ROBUST_WIN'),(3,1,'ACCEPT')],'KEEP_C_PLUS_EXISTING_MUQ_FOUNDATION'),
 ([], 'INCONCLUSIVE'),
 ([(1,3,'ROBUST_WIN'),(1,4,'ROBUST_WIN'),(4,3,'ROBUST_WIN'),(4,1,'ACCEPT')],'RECOMMEND_C_CLAP_FOUNDATION'),
 ([(4,3,'ROBUST_WIN'),(4,1,'ACCEPT'),(2,4,'ROBUST_WIN')],'INCONCLUSIVE')])
def test_precedence(edges,expected):
    comparisons={}
    for x,y,k in edges:comparisons.setdefault(f'{METHODS[x-1]}__vs__{METHODS[y-1]}',{})[k]=True
    assert choose_verdict(comparisons,True)==expected
    assert choose_verdict(comparisons,False)=='INCONCLUSIVE'


def test_numeric_boundaries_and_nulls():
    p={'unacceptable':.03,'coherent':-.03,'mean_rating':-.15,'median_rating':0.,'recovery':.08}
    assert point_accept(p) and gain(p)
    for k,v in [('unacceptable',.0300001),('coherent',-.0300001),('mean_rating',-.1500001)]:assert not point_accept(p|{k:v})
    for v in (None,float('nan')):assert not gain(p|{'recovery':v})
    assert interval([])['high'] is None
    assert interval([0,1,-1])==interval([0,1,-1])


def test_full_fixture_missingness_and_no_artificial_probe_recall():
    ids,rows,labels,pairs=fixture()
    result=analyze_fixture(rows,ids,labels,labels,{},set(pairs))
    assert result['verdict']=='INCONCLUSIVE'
    assert all(result['support_gates'].values())
    for metric in result['metrics'].values():
        assert metric['complete_anchor_count']==100 and metric['numeric_slots']==500
    missing=dict(labels);missing[next(iter(labels))]='UNSURE'
    bank=positive_bank(ids,set(pairs),labels)
    compared=comparison(rows,METHODS[3],METHODS[2],missing,labels,{},bank,ids)
    assert len(compared['eligible_ids'])<100
    assert compared['point']['unacceptable']==0
    original={p:1 for p in labels};bank=positive_bank(ids,set(pairs),original)
    assert not comparison(rows,METHODS[3],METHODS[2],labels,original,{},bank,ids)['ACCEPT']


def test_original_sensitivity_insufficient():
    ids,rows,labels,pairs=fixture();bank=positive_bank(ids,set(pairs),labels)
    result=comparison(rows,METHODS[0],METHODS[1],labels,labels,dict.fromkeys(labels),bank,ids)
    assert not result['original_label_sensitivity']['pass']
    assert not result['STABLE']


def test_end_to_end_robust_full_muq_win_and_no_backfill():
    ids=[f't{i:03d}' for i in range(100)];rows=[];labels={};pairs={}
    for i,q in enumerate(ids):
        for method in METHODS:
            for rank in range(1,6):
                shift=rank if method==METHODS[3] else rank+5
                c=ids[(i+shift)%100];p=canonical_pair_id(q,c)
                labels[p]=5 if shift<=5 else 1;pairs[p]=[q,c]
                rows.append({'method_id':method,'query':q,'candidate':c,'pair_id':p,'rank':rank,'score':.9})
    bank=positive_bank(ids,set(pairs),labels)
    c=comparison(rows,METHODS[3],METHODS[2],labels,labels,{},bank,ids)
    assert c['ROBUST_WIN'] and c['STABLE']
    assert c['point']['unacceptable']==-1 and c['point']['coherent']==1
    assert len(c['track_node_deletion'])==100 and all(r['pass'] for r in c['track_node_deletion'])
    result=analyze_fixture(rows,ids,labels,labels,{},set(pairs))
    assert result['verdict']=='RECOMMEND_C_PLUS_FULL_MUQ_FOUNDATION'


def test_upper_interval_strict_boundary(monkeypatch):
    import audio_similarity.playlist_compatibility_eval as module
    ids,rows,labels,pairs=fixture();bank=positive_bank(ids,set(pairs),labels)
    monkeypatch.setattr(module,'interval',lambda _: {'low':0,'high':.05,'reason':None})
    assert not comparison(rows,METHODS[0],METHODS[1],labels,labels,{},bank,ids)['ACCEPT']
    monkeypatch.setattr(module,'interval',lambda _: {'low':0,'high':.049999,'reason':None})
    assert comparison(rows,METHODS[0],METHODS[1],labels,labels,{},bank,ids)['ACCEPT']
