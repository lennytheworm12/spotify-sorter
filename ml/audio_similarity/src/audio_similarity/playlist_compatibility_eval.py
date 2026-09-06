"""Frozen revision-2 metrics and decision rules. Pure functions, no live data access."""
from itertools import permutations, combinations
import numpy as np
from .stage5c2_analysis import canonical_pair_id

METHODS = ('M1_C_CLAP','M2_FULL_MUQ','M3_C_PLUS_FIXED_MUQ','M4_C_PLUS_FULL_MUQ')
SEED=20260906
METRICS=('unacceptable','coherent','mean_rating','median_rating')


def numeric(v):
    return type(v) is int and 1 <= v <= 5


def average(values):
    return float(np.mean(values)) if len(values) else None


def quality(values):
    return dict(zip(METRICS, (average([v<=2 for v in values]),average([v>=4 for v in values]),
                              average(values),float(np.median(values)) if len(values) else None)))


def groups(rows, method):
    result={}
    for row in rows:
        if row['method_id']==method:
            result.setdefault(row['query'],[]).append(row)
    return result


def pair_value(row, labels):
    return labels.get(row['pair_id'])


def positive_bank(ids, eligible_pairs, original):
    return {q:{c for c in ids if c!=q and canonical_pair_id(q,c) in eligible_pairs
               and numeric(original.get(canonical_pair_id(q,c))) and original[canonical_pair_id(q,c)]>=4}
            for q in ids}


def per_anchor(rows, method, labels, bank, *, allowed=None, removed=None, partial=False):
    output={}
    for q, rs in groups(rows,method).items():
        if q==removed or (allowed is not None and q not in allowed): continue
        rs=[r for r in rs if r['candidate']!=removed]
        values=[pair_value(r,labels) for r in rs]
        if not values or not all(numeric(v) for v in values) or (not partial and len(rs)!=5): continue
        output[q]=quality(values)
    recovery={}
    for q, rs in groups(rows,method).items():
        positives=bank.get(q,set())-{removed}
        if q==removed or not positives: continue
        recovery[q]=len({r['candidate'] for r in rs if r['candidate']!=removed}&positives)/len(positives)
    return output,recovery


def deltas(rows,x,y,labels,bank,*,allowed=None,removed=None,partial=False):
    a,ar=per_anchor(rows,x,labels,bank,allowed=allowed,removed=removed,partial=partial)
    b,br=per_anchor(rows,y,labels,bank,allowed=allowed,removed=removed,partial=partial)
    ids=sorted(a.keys()&b.keys()); positive_ids=sorted(ar.keys()&br.keys())
    vectors={k:[a[q][k]-b[q][k] for q in ids] for k in METRICS}
    vectors['recovery']=[ar[q]-br[q] for q in positive_ids]
    return {'eligible_ids':ids,'positive_ids':positive_ids,'vectors':vectors,
            'point':{k:average(v) for k,v in vectors.items()}}


def interval(values):
    if not values: return {'low':None,'high':None,'reason':'no eligible anchors'}
    values=np.asarray(values)
    rng=np.random.Generator(np.random.PCG64(SEED))
    samples=values[rng.integers(0,len(values),size=(2000,len(values)))].mean(axis=1)
    low,high=np.percentile(samples,[2.5,97.5],method='linear')
    return {'low':float(low),'high':float(high),'reason':None}


def finite_point(point):
    return all(point.get(k) is not None and np.isfinite(point[k]) for k in (*METRICS,'recovery'))


def point_accept(p):
    return finite_point(p) and p['unacceptable']<=.03 and p['coherent']>=-.03 and p['mean_rating']>=-.15


def gain(p):
    return finite_point(p) and (p['recovery']>=.08 or p['unacceptable']<=-.05 or p['coherent']>=.05)


def comparison(rows,x,y,labels,original,conflicts,bank,ids):
    base=deltas(rows,x,y,labels,bank)
    intervals={k:interval(v) for k,v in base['vectors'].items()}
    hi=intervals['unacceptable']['high']
    accept=(len(base['eligible_ids'])>=40 and len(base['positive_ids'])>=30 and point_accept(base['point'])
            and hi is not None and hi<.05)
    leave=[]
    for q in base['eligible_ids']:
        # Delete anchor only, retaining its candidate appearances elsewhere.
        p={k:average([v for i,v in enumerate(vs) if (base['positive_ids'] if k=='recovery' else base['eligible_ids'])[i]!=q])
           for k,vs in base['vectors'].items()}
        leave.append({'removed':q,'point':p,'pass':bool(point_accept(p) and gain(p))})
    nodes=[]
    for node in ids:
        d=deltas(rows,x,y,labels,bank,allowed=set(base['eligible_ids']),removed=node,partial=True)
        p=d['point']; ok=finite_point(p) and p['unacceptable']<=.05 and p['coherent']>=-.05 and p['mean_rating']>=-.15
        nodes.append({'removed':node,'point':p,'eligible_ids':d['eligible_ids'],'pass':bool(ok)})
    historical=dict(labels)
    for pair,value in original.items(): historical[pair]=value
    for pair in conflicts: historical.pop(pair,None)
    sensitivity=deltas(rows,x,y,historical,bank)
    original_ok=(len(sensitivity['eligible_ids'])>=30 and len(sensitivity['positive_ids'])>=30
                 and point_accept(sensitivity['point']) and gain(sensitivity['point']))
    stable=bool(leave and all(r['pass'] for r in leave) and nodes and all(r['pass'] for r in nodes) and original_ok)
    return base|{'intervals':intervals,'leave_one_anchor_out':leave,'track_node_deletion':nodes,
                 'original_label_sensitivity':sensitivity|{'pass':bool(original_ok)},
                 'ACCEPT':bool(accept),'GAIN':bool(gain(base['point'])),'WIN':bool(accept and gain(base['point'])),
                 'STABLE':stable,'ROBUST_WIN':bool(accept and gain(base['point']) and stable)}


def choose_verdict(comparisons, support):
    def predicate(x,y,name):
        return comparisons.get(f'{METHODS[x-1]}__vs__{METHODS[y-1]}',{}).get(name) is True
    def win(x,y): return predicate(x,y,'ROBUST_WIN')
    def accept(x,y): return predicate(x,y,'ACCEPT')
    if not support: return 'INCONCLUSIVE'
    if win(1,3) and win(1,4): return 'RECOMMEND_C_CLAP_FOUNDATION'
    if win(4,3) and accept(4,1) and not win(2,4): return 'RECOMMEND_C_PLUS_FULL_MUQ_FOUNDATION'
    if win(2,3) and win(2,4): return 'FULL_MUQ_PROMISING_FUSION_UNRESOLVED'
    if win(3,4) and accept(3,1): return 'KEEP_C_PLUS_EXISTING_MUQ_FOUNDATION'
    return 'INCONCLUSIVE'


def method_metrics(rows,method,labels,bank,original):
    rs=[r for r in rows if r['method_id']==method]
    rated=[r for r in rs if numeric(pair_value(r,labels))]
    complete,recovery=per_anchor(rows,method,labels,bank)
    unique={r['pair_id'] for r in rs}
    bad=[r for r in rated if labels[r['pair_id']]<=2]
    bounds=[]
    for substitute in (1,5):
        bounds.append({k:average([quality([labels[r['pair_id']] if numeric(labels.get(r['pair_id'])) else substitute for r in group])[k]
                                  for group in groups(rows,method).values()]) for k in METRICS})
    recovered=[r for r in rs if r['candidate'] in bank.get(r['query'],set())]
    return {'slots':len(rs),'numeric_slots':len(rated),'numeric_slot_coverage':len(rated)/len(rs) if rs else 0,
            'unsure_slot_fraction':sum(labels.get(r['pair_id'])=='UNSURE' for r in rs)/len(rs) if rs else 0,
            'unrated_slot_fraction':sum(r['pair_id'] not in labels for r in rs)/len(rs) if rs else 0,
            'complete_anchor_count':len(complete),'complete_anchor_ids':sorted(complete),
            'unique_pairs':len(unique),'unique_pair_numeric_coverage':sum(numeric(labels.get(p)) for p in unique)/len(unique) if unique else 0,
            'complete_anchor_macro':{k:average([v[k] for v in complete.values()]) for k in METRICS},
            'partial_observed_only':quality([labels[r['pair_id']] for r in rated]),
            'raw_unacceptable_count':len(bad),'anchors_with_unacceptable':len({r['query'] for r in bad}),
            'worst_position_distribution':{str(rank):sum(max([r['rank'] for r in bad if r['query']==q],default=0)==rank for q in groups(rows,method)) for rank in range(1,6)},
            'known_bad_recurrence':[r for r in rs if numeric(original.get(r['pair_id'])) and original[r['pair_id']]<=2],
            'recovery_macro':average(list(recovery.values())),'recovery_by_anchor':recovery,
            'recovered':recovered,'recovered_unique_pairs':sorted({r['pair_id'] for r in recovered}),
            'missing_rating_bounds':{k:[min(b[k] for b in bounds),max(b[k] for b in bounds)] for k in METRICS} if rs else {}}


def analyze_fixture(rows,ids,labels,original,conflicts,eligible_pairs,*,integrity=True,review_complete=True,materialized=True,semantic_tags=None):
    """Caller must gate real use on a frozen complete review; fixture tests may vary gates."""
    bank=positive_bank(ids,eligible_pairs,original)
    metrics={m:method_metrics(rows,m,labels,bank,original) for m in METHODS}
    comparisons={f'{x}__vs__{y}':comparison(rows,x,y,labels,original,conflicts,bank,ids) for x,y in permutations(METHODS,2)}
    primary=comparisons[f'{METHODS[3]}__vs__{METHODS[2]}']
    gates={'all_method_coverage':all(metrics[m]['numeric_slot_coverage']>=.8 for m in METHODS),
           'primary_coverage':all(metrics[m]['numeric_slot_coverage']>=.9 for m in METHODS[2:]),
           'complete_paired_anchors':len(primary['eligible_ids'])>=40,
           'positive_bank_anchors':sum(bool(v) for v in bank.values())>=30,
           'paired_evidence_anchors':len(primary['eligible_ids'])>=30,
           'historical_integrity':integrity is True,'review_complete':review_complete is True,
           'full100_materialized':materialized is True and len(ids)==100}
    overlaps={}
    for x,y in combinations(METHODS,2):
        gx,gy=groups(rows,x),groups(rows,y)
        sx={(r['query'],r['candidate']) for r in rows if r['method_id']==x}
        sy={(r['query'],r['candidate']) for r in rows if r['method_id']==y}
        px={r['pair_id'] for r in rows if r['method_id']==x};py={r['pair_id'] for r in rows if r['method_id']==y}
        overlaps[f'{x}__vs__{y}']={'mean_top5_jaccard':average([len({r['candidate'] for r in gx[q]}&{r['candidate'] for r in gy[q]})/len({r['candidate'] for r in gx[q]}|{r['candidate'] for r in gy[q]}) for q in sorted(gx.keys()&gy.keys())]),
           'shared_slots':len(sx&sy),'unique_slots_x':len(sx-sy),'unique_slots_y':len(sy-sx),'shared_unique_pairs':len(px&py),
           'unique_pairs_requiring_new_review':sum(not numeric(original.get(p)) for p in px|py)}
    bounds={f'{x}__vs__{y}':{k:[metrics[x]['missing_rating_bounds'][k][0]-metrics[y]['missing_rating_bounds'][k][1],metrics[x]['missing_rating_bounds'][k][1]-metrics[y]['missing_rating_bounds'][k][0]] for k in METRICS} for x,y in permutations(METHODS,2) if metrics[x]['slots'] and metrics[y]['slots']}
    recovered={m:set(metrics[m]['recovered_unique_pairs']) for m in METHODS}
    recovery={'unique_to_method':{m:sorted(recovered[m]-set().union(*(recovered[n] for n in METHODS if n!=m))) for m in METHODS},
              'M4_lost_vs_M3':sorted(recovered[METHODS[2]]-recovered[METHODS[3]]),
              'M4_new_vs_M3':sorted(recovered[METHODS[3]]-recovered[METHODS[2]])}
    recovered_slots={m:{(r['query'],r['candidate']) for r in metrics[m]['recovered']} for m in METHODS}
    recovery['M4_lost_directional_vs_M3']=[list(p) for p in sorted(recovered_slots[METHODS[2]]-recovered_slots[METHODS[3]])]
    recovery['M4_new_directional_vs_M3']=[list(p) for p in sorted(recovered_slots[METHODS[3]]-recovered_slots[METHODS[2]])]
    semantics={tag:{m:method_metrics(rows,m,{p:v for p,v in labels.items() if (semantic_tags or {}).get(p)==tag},bank,original) for m in METHODS} for tag in sorted(set((semantic_tags or {}).values()))}
    return {'metrics':metrics,'comparisons':comparisons,'support_gates':gates,'overlap':overlaps,
            'missing_rating_bounds':bounds,'recovery':recovery,'semantic_strata':semantics,
            'verdict':choose_verdict(comparisons,all(gates.values()))}
