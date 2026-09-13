"""Bounded Gemini profiling for the fixed development sample; existing transport/schema."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
import fcntl
import json
from pathlib import Path

from .contracts import digest, file_hash, freeze_json, require
from .development_inputs import RUN, load
from ..gemini_free_genre_runner import FreeGenreRunner
from ..gemini_style_pilot.budget import AttemptLedger
from ..gemini_style_pilot.prepare import prepare_audio
from ..gemini_style_pilot.transport import GeminiTransport, configured_key
from ..gemini_style_pilot.runner import RunStopped
from ..gemini_style_pilot.validation import InvalidProfile


def prepare(root):
    plan = load(root)
    run = root / RUN / 'gemini'
    prior = root / '.research_audio/gemini_style_pilot/frozen100-free-genre-v1'
    old = json.loads((prior/'execution_manifest.json').read_text())
    run.mkdir(parents=True,exist_ok=True)
    for name in ('prompt.txt','response_schema.json'):
        target = run/name
        raw = (prior/name).read_bytes()
        if target.exists():
            require(target.read_bytes()==raw,'frozen prompt/schema differs')
        else:
            target.write_bytes(raw)
    prior_by_hash = {t['source_sha256']: t for t in old['tracks']}
    tracks = [t for t in plan['tracks'] if t['in_sample']]

    def convert(pair):
        i,t = pair
        pid,neutral = f'T{i:03}', f'N{i+199:03}'
        previous = prior_by_hash.get(t['source_sha256'])
        if previous and previous['spotify_track_id'] == t['stable_track_id']:
            path = root / 'reports/gemini_style_pilot/frozen100_free_genre_v1/profiles' / (previous['pilot_id']+'.json')
            profile = json.loads(path.read_text())
            return t | {'pilot_id':pid,'neutral_id':neutral,'cached_profile':profile,
                'cached_profile_path':str(path.relative_to(root)), 'cached_profile_sha256':file_hash(path),
                'prepared':previous['prepared']}
        prepared = prepare_audio(root/t['source_path'],t['source_sha256'],run/'prepared'/(neutral+'.flac'))
        print(json.dumps({'prepared':i,'total':len(tracks)}),flush=True)
        return t | {'pilot_id':pid,'neutral_id':neutral,'prepared':prepared,'cached_profile':None}

    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(convert,enumerate(tracks,1)))
    base = json.loads((run/'response_schema.json').read_text())
    schemas = {}
    for t in rows:
        schema = json.loads(json.dumps(base))
        schema['properties']['audio_evidence']['items']['properties']['at_seconds']['maximum'] = t['prepared']['duration_seconds']
        name = 'schemas/'+t['pilot_id']+'.json'
        freeze_json(run/name,schema)
        schemas[t['pilot_id']] = name
    implementations = {str(p.relative_to(root)):file_hash(p) for p in
        [Path(__file__).resolve(),root/'src/audio_similarity/gemini_free_genre_runner.py',
         root/'src/audio_similarity/gemini_style_pilot/transport.py',root/'src/audio_similarity/gemini_style_pilot/budget.py']}
    manifest = {'schema':'playlist-development-gemini-v1','model_id':old['model_id'],
        'generation_config':old['generation_config'],'environment':old['environment'],
        'implementation_sha256':digest(implementations),'implementation_hashes':implementations,
        'prompt_sha256':file_hash(run/'prompt.txt'),'base_schema_sha256':file_hash(run/'response_schema.json'),
        'rates':{'input':'0.75','output_including_thinking':'3.75','tier':'standard','valid_through':'2026-12-31',
                 'verified_on':'2026-09-13','source':'https://ai.google.dev/gemini-api/docs/pricing'},
        'spend_cap_usd':plan['gemini_run_cap_usd'],'max_attempts':sum(t['cached_profile'] is None for t in rows),
        'tracks':rows,'schedule':[{'pilot_id':t['pilot_id'],'repeat':False} for t in rows if t['cached_profile'] is None],
        'response_schemas':schemas,'prepared_root':str((run/'prepared').relative_to(root)),
        'plan_sha256':digest(plan),'automatic_retries':0,'metadata_to_provider':'neutral ID and duration only; no playlist labels or identities'}
    freeze_json(run/'execution_manifest.json',manifest)
    return {'tracks':len(rows),'new_calls_planned':len(manifest['schedule'])}


class DevelopmentLedger(AttemptLedger):
    def __init__(self,directory,max_attempts):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True,exist_ok=True)
        self.input_limit = 1048576
        self.input_rate,self.output_rate = Decimal('.75')/1000000,Decimal('3.75')/1000000
        self.cap,self.max_attempts = Decimal('5'),max_attempts
        require(0<max_attempts<=300,'development attempt cap')
        freeze_json(self.directory/'policy.json',{'input_limit':self.input_limit,'input_rate':str(self.input_rate),
            'output_rate':str(self.output_rate),'cap_usd':str(self.cap),'max_attempts':max_attempts})


class DevelopmentRunner(FreeGenreRunner):
    def __init__(self,root):
        self.root = root.resolve()
        self.run = root/RUN/'gemini'
        self.manifest = json.loads((self.run/'execution_manifest.json').read_text())
        self.manifest_sha = file_hash(self.run/'execution_manifest.json')
        self.directory = self.run/'execution'
        self.directory.mkdir(parents=True,exist_ok=True)
        self.tracks = {t['pilot_id']:t for t in self.manifest['tracks']}
        self.prompt = (self.run/'prompt.txt').read_text()
        require(file_hash(self.run/'prompt.txt')==self.manifest['prompt_sha256'],'prompt changed')
        for p,h in self.manifest['implementation_hashes'].items():
            require(file_hash(root/p)==h,'producer implementation changed')

    def ledger(self):
        return DevelopmentLedger(self.directory/'attempts',self.manifest['max_attempts'])

    def next(self):
        with (self.directory/'.runner.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            require(not (self.directory/'STOPPED.json').exists(),'operational failure requires explicit reviewed continuation')
            index=1
            while index<=len(self.manifest['schedule']) and self.result_path(index).exists():
                self.verified_result(index)
                index+=1
            if index>len(self.manifest['schedule']):
                return {'status':'COMPLETE','new_calls':0}
            require(len(list((self.directory/'attempts').glob('*.reservation.json')))==index-1,'unaccounted request; no automatic retry')
            require(date.today()<=date.fromisoformat(self.manifest['rates']['valid_through']),'rates expired')
            if index>2:
                require(json.loads((self.directory/'smoke_gate.json').read_text())==self.smoke_record(),'smoke gate differs')
            transport=GeminiTransport(self.directory/'transport',configured_key(self.root/'.env'))
            try:
                result=self._attempt(index,transport)
                if index==2:
                    freeze_json(self.directory/'smoke_gate.json',self.smoke_record())
                return {'status':'VALIDATED','attempt':index,'new_calls':1,'cost_usd':result['actual_cost_usd']}
            except Exception as exc:
                freeze_json(self.directory/'STOPPED.json',{'slot':index,'type':type(exc).__name__,
                    'reason':'Preserved operational or profile failure; no automatic retry or classification repair.'})
                raise
            finally:
                transport.close()

    def freeze_profiles(self):
        profiles={}
        for t in self.manifest['tracks']:
            if t['cached_profile']:
                require(file_hash(self.root/t['cached_profile_path'])==t['cached_profile_sha256'],'prior profile changed')
                profiles[t['request_id']]=t['cached_profile']['profile']
        for i,slot in enumerate(self.manifest['schedule'],1):
            result=self.verified_result(i)
            profiles[self.tracks[slot['pilot_id']]['request_id']]=result['profile']
        freeze_json(self.run/'profiles_frozen.json',{'manifest_sha256':self.manifest_sha,'profiles':profiles})
        return {'status':'PROFILES_FROZEN','profiles':len(profiles),'replay_api_calls':0}
