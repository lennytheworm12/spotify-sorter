from pathlib import Path
from copy import deepcopy
import pytest
from audio_similarity.genre_force_export import canonical_profile, CONFIG, load_audio
from audio_similarity.genre_registry_review import mapper
from audio_similarity.stage5e3_artifacts import read
ROOT=Path(__file__).resolve().parents[1]

def profile(style,**kw):
    return {'primary_style':style,'secondary_styles':[],'primary_family':'R&B','secondary_families':[],**kw}

def test_current_contract_canonical_gate_aliases_and_no_context_votes():
    engine=mapper(ROOT);force=read(ROOT/CONFIG/'genre-force-explorer-v1.json')
    p=profile('Alternative R&B',secondary_styles=['Alt-R&B'],secondary_families=['K-Pop']);before=deepcopy(p)
    r=canonical_profile(p,engine,force)
    assert p==before
    assert r['canonical']=={'family:rnb_soul':.5,'style:alternative_rnb':1}
    assert r['specificStyleIds']==['style:alternative_rnb']
    assert r['excluded'][0]['id']=='context:k_pop'
    a=canonical_profile(profile('Pop',primary_family='Pop'),engine,force)
    assert a['canonical']=={'family:pop':1} and not a['specificStyleIds']

def test_unreviewed_and_umbrella_dont_open_specificity_gate():
    engine=mapper(ROOT);force=read(ROOT/CONFIG/'genre-force-explorer-v1.json')
    for raw in ['Digicore','Electronica','Rap','Alien Genre']:
        p=canonical_profile(profile(raw,primary_family='Electronic'),engine,force)
        assert not p['specificStyleIds']
    p=canonical_profile(profile('Hyperpop',primary_family='Electronic'),engine,force)
    assert p['specificStyleIds']==['style:hyperpop']

def test_metadata_vocals_arrangement_certainty_never_affect_score_vectors():
    engine=mapper(ROOT);force=read(ROOT/CONFIG/'genre-force-explorer-v1.json')
    a=profile('Neo-Soul');b={**a,'title':'Anything','artist':'Someone','vocal_role':'rap_led','arrangement_focus':'beat_or_instrumental','certainty':{'style':'tentative'}}
    assert canonical_profile(a,engine,force)==canonical_profile(b,engine,force)

def test_audio_matrix_selection_explicit_and_symmetric():
    with pytest.raises(ValueError):load_audio(ROOT,'automatic')
    ids,matrix=load_audio(ROOT,'M3_C_PLUS_FIXED_MUQ')
    assert len(ids)==100 and matrix.shape==(100,100)


def test_secondary_label_strength_and_duplicate_aliases_preserve_max_mass():
    engine=mapper(ROOT);force=read(ROOT/CONFIG/'genre-force-explorer-v1.json')
    original=profile('Neo-Soul', secondary_styles=['Alt-R&B'])
    duplicated=profile('Neo-Soul', secondary_styles=['Alt-R&B','Alternative R&B','Alt-R&B'])
    a=canonical_profile(original,engine,force)
    b=canonical_profile(duplicated,engine,force)
    assert a['canonical']==b['canonical']=={
        'family:rnb_soul':.5,'style:neo_soul':1,'style:alternative_rnb':.5}
    assert a['neighborhoods']==b['neighborhoods']
    primary=canonical_profile(profile('Alt-R&B', secondary_styles=['Alternative R&B']),engine,force)
    assert primary['canonical']['style:alternative_rnb']==1


@pytest.mark.parametrize('style,family', [('K-Pop','J-Pop'), ('Imaginary genre','Unknown')])
def test_context_only_and_unresolved_profiles_cannot_supply_sonic_mass(style,family):
    engine=mapper(ROOT);force=read(ROOT/CONFIG/'genre-force-explorer-v1.json')
    raw=profile(style,primary_family=family);before=deepcopy(raw)
    result=canonical_profile(raw,engine,force)
    assert raw==before
    assert result['canonical']=={} and result['specificStyleIds']==[]
    assert result['neighborhoods']=={}
    assert result['excluded'] or result['warnings']
