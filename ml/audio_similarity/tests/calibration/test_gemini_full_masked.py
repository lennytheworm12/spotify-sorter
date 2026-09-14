import numpy as np
import pytest
from audio_similarity.calibration.gemini_full_masked import expand


def test_missing_is_null_and_reordered_valid_values_preserved():
    jc=np.array([[1.,.25],[.25,0.]])
    jnr=np.array([[0.,.5],[.5,0.]])
    available,mask,values=expand(['a','b','c'],['c','a'],{'Jc':jc,'Jnr':jnr,'R':(1-jc)*jnr})
    assert available.tolist()==[True,False,True]
    assert np.isnan(values['Jc'][1]).all()
    assert values['Jc'][0,0]==0  # Valid noninformative profile remains distinct from missing.
    assert values['Jc'][2,0]==.25
    assert np.array_equal(np.isfinite(values['R']),mask)


def test_inconsistent_residual_rejected():
    with pytest.raises(ValueError):
        expand(['a'],['a'],{'Jc':np.ones((1,1)),'Jnr':np.zeros((1,1)),'R':np.ones((1,1))})
