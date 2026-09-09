import json
from pathlib import Path
import numpy as np
import essentia.standard as es
from audio_similarity.stage5e3_artifacts import freeze_json
config=json.load(open('reports/style_prior_pilot/v2/protocol.json'))
m=es.TensorflowPredictEffnetDiscogs(graphFilename='models/discogs-effnet-bs64-1.pb',**config['preprocessing']['predictor'])
rows=[]
for n in (32000,160000,170001):
    x=(.05*np.sin(2*np.pi*440*np.arange(n)/16000)).astype(np.float32)
    a=m(x);b=m(x)
    assert a.ndim==2 and a.shape[1]==400 and len(a)>0 and np.isfinite(a).all()
    error=float(np.max(np.abs(a-b)))
    assert error<=1e-6
    rows.append({'samples':n,'shape':list(a.shape),'repeat_max_error':error,'finite':True})
freeze_json(Path('reports/style_prior_pilot/v2/engineering_golden.json'),{'synthetic_sine_hz':440,'amplitude':.05,'checks':rows,'no_human_ratings_used':True})
print(rows)
