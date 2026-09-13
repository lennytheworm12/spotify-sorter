"""Content-addressed, immutable Method C chunk and pooled-feature storage."""
from pathlib import Path
import numpy as np
from .contracts import digest, freeze_json, require
from .development_audio import vector_ok
from .method_c_full_inputs import read
from ..stage5e1_sampling import normalized_mean


def identity(recording, config):
    return digest({'recording_id': recording['recording_id'],
                   'audio_sha256': recording['audio_sha256'], 'configuration_sha256': digest(config)})


def validate_feature(value, recording, config):
    require(value['identity'] == identity(recording, config), 'Method C cache identity mismatch')
    require(value['recording_id'] == recording['recording_id'], 'recording mismatch')
    require(value['audio_sha256'] == recording['audio_sha256'], 'audio mismatch')
    require(value['representation'] == 'method_c_full_song', 'representation mismatch')
    require(vector_ok(value['vector']), 'invalid pooled Method C vector')
    require(value['vector_sha256'] == digest(value['vector']), 'vector hash mismatch')
    if value['views'] is not None:
        require(bool(value['views']) and all(vector_ok(v) for v in value['views']), 'invalid chunk vectors')
        require(np.array_equal(normalized_mean(value['views']), np.asarray(value['vector'], dtype=np.float32)), 'pooling mismatch')
    return value


def store_feature(path, recording, config, vector, views, origin):
    value = {'identity': identity(recording, config), 'recording_id': recording['recording_id'],
             'audio_sha256': recording['audio_sha256'], 'representation': 'method_c_full_song',
             'configuration_sha256': digest(config), 'vector': np.asarray(vector).tolist(),
             'views': views, 'origin': origin}
    value['vector_sha256'] = digest(value['vector'])
    validate_feature(value, recording, config)
    freeze_json(Path(path), value)
    return value


def load_feature(path, recording, config):
    return validate_feature(read(Path(path)), recording, config)
