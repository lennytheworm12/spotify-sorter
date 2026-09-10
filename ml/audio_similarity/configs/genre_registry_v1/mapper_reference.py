"""Offline reference normalizer for the draft genre mapping. No model calls or scoring.

python mapper_reference.py --input classifications.csv --output mapped_profiles.json
Use the full local frozen100 CSV; its bytes are never modified.
"""
from __future__ import annotations
import argparse, copy, csv, hashlib, json, re, unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

GENRE_FIELDS=('primary_family','primary_style','secondary_families','secondary_styles')

def normalize(label: str) -> str:
    if not isinstance(label,str): raise TypeError('Genre labels must be strings')
    s=unicodedata.normalize('NFKC',label).casefold().strip()
    s=re.sub(r'[_\-\u2010-\u2015\u2212]+',' ',s)
    s=s.replace('&',' and ')
    return re.sub(r'\s+',' ',s).strip()

class Mapper:
    def __init__(self, config: dict[str,Any]) -> None:
        self.config=config
        self.concepts={c['id']:c for c in config['concepts']}
        if len(self.concepts)!=len(config['concepts']): raise ValueError('Duplicate concept IDs')
        self.index:dict[str,tuple[str,...]]={}
        self.rules:dict[str,str]={}
        for c in config['concepts']:
            for alias in c['aliases']:
                self._register(alias,(c['id'],),'registered_alias')
        for comp in config['composite_labels']:
            for target in comp['targets']:
                if target not in self.concepts: raise ValueError(f'Unknown target {target}')
            for alias in comp['aliases']:
                self._register(alias,tuple(comp['targets']),comp['rule'])
        for c in config['concepts']:
            if not set(c['families'])<=set(config['families']): raise ValueError(c['id'])
            if not set(c['neighborhoods'])<=set(config['neighborhoods']): raise ValueError(c['id'])
            if not set(c['neighborhoods'].values()) <= {'core','related'}: raise ValueError(c['id'])
    def _register(self,alias:str,targets:tuple[str,...],rule:str)->None:
        key=normalize(alias)
        if key in self.index and self.index[key]!=targets:
            raise ValueError(f'Conflicting alias {alias}: {self.index[key]} vs {targets}')
        self.index[key]=targets
        self.rules[key]=rule
    def resolve(self,label:str)->dict[str,Any]:
        key=normalize(label)
        targets=self.index.get(key)
        status='unmapped' if targets is None else 'review_required' if not targets else 'mapped'
        return {'raw_label':label,'normalized_key':key,'status':status,
                'concept_ids':list(targets or []),'rule':self.rules.get(key,'no_registered_mapping')}
    def profile(self, raw:dict[str,Any])->dict[str,Any]:
        memberships:dict[str,float]={}; traces=[]; concepts=set(); families=set()
        source_fields={k:copy.deepcopy(raw.get(k)) for k in GENRE_FIELDS}
        p=self.config['membership_proposal']
        for field in GENRE_FIELDS:
            value=raw.get(field,[] if field.startswith('secondary') else None)
            if value is None: values=[]
            elif field.startswith('secondary'):
                if not isinstance(value,list):raise ValueError(f'{field} must be a list')
                values=value
            else:
                if not isinstance(value,str):raise ValueError(f'{field} must be a string or null')
                values=[value]
            for value in values:
                if not isinstance(value,str): raise ValueError(f'{field} contains non-string')
                if not value.strip():continue
                resolved=self.resolve(value); resolved['source_field']=field
                resolved['contributions']=[]
                for cid in resolved['concept_ids']:
                    c=self.concepts[cid]; concepts.add(cid);families.update(c['families'])
                    if c['mapping_review_required']:
                        resolved['status']='review_required';continue
                    if c['kind'] not in ('style','style_context'):continue
                    for n,relationship in c['neighborhoods'].items():
                        strength=p['field_strengths'][field]*p[f'{relationship}_relation_strength']
                        memberships[n]=max(memberships.get(n,0.0),strength)
                        resolved['contributions'].append({'neighborhood':n,'strength':strength,'relation':relationship,'concept_id':cid})
                traces.append(resolved)
        unknown=[x for x in traces if x['status']!='mapped']
        return {'mapping_version':self.config['version'],'raw_genre_fields':source_fields,
                'canonical_concepts':sorted(concepts),'families':sorted(families),
                'neighborhood_memberships':dict(sorted(memberships.items())),
                'mapping_status':'no_specific_style_signal' if not memberships else 'partial' if unknown else 'mapped',
                'unresolved_labels':unknown,'label_traces':traces,
                'classification_accuracy':'not_assessed','score_adjustment':None}

def main()->None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mapping',type=Path,default=Path(__file__).with_name('genre-neighborhood-map-v1.json'))
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise SystemExit('Refusing to overwrite output; choose a new path.')
    config=json.loads(args.mapping.read_text(encoding='utf-8')); mapper=Mapper(config)
    input_bytes=args.input.read_bytes()
    with args.input.open(encoding='utf-8-sig',newline='') as f:
        rows=list(csv.DictReader(f))
    seen=set(); mapped=[]; labels=Counter(); unresolved=Counter()
    for row in rows:
        identity=row.get('spotify_track_id')
        if not identity or identity in seen:raise ValueError(f'Missing or duplicate Spotify identity: {identity}')
        seen.add(identity)
        raw={k:row.get(k) for k in GENRE_FIELDS}
        for k in ('secondary_families','secondary_styles'):
            raw[k]=json.loads(raw[k]) if raw[k] else []
        m=mapper.profile(raw)
        for t in m['label_traces']:
            labels[t['raw_label']]+=1
            if t['status']!='mapped':unresolved[t['raw_label']]+=1
        mapped.append({'spotify_track_id':identity,'pilot_id':row.get('pilot_id'),**m})
    result={'input_sha256':hashlib.sha256(input_bytes).hexdigest(),'mapping_sha256':hashlib.sha256(args.mapping.read_bytes()).hexdigest(),
            'records':mapped,'audit':{'rows':len(rows),'unique_raw_genre_strings':len(labels),'raw_label_counts':dict(sorted(labels.items())),
             'unresolved_label_counts':dict(sorted(unresolved.items())),'profiles_with_style_signal':sum(bool(m['neighborhood_memberships']) for m in mapped),
             'classification_accuracy':'not_assessed','scores_changed':False}}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps({k:v for k,v in result['audit'].items() if not isinstance(v,dict)},indent=2))

if __name__=='__main__':main()
