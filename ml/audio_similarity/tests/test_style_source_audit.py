import numpy as np
import pytest
from audio_similarity.style_source_reference import prediction_error


def test_reference_checks_actual_patch_content():
    a = np.full((3, 400), .2, dtype=np.float32)
    assert prediction_error(a, a.copy()) == 0
    b = a.copy(); b[1, 27] += .1
    assert prediction_error(a, b) > .09


@pytest.mark.parametrize('bad', [np.zeros((3, 399)), np.full((3, 400), np.nan)])
def test_invalid_reference_rejected(bad):
    with pytest.raises(ValueError):
        prediction_error(np.zeros((3, 400)), bad)
