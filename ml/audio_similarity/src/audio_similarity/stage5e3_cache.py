"""Transactional versioned track/chunk cache; exact identities, no rekeying."""
import hashlib
import json
import sqlite3
import numpy as np
from .stage5e3_artifacts import digest


class MuQCache:
    def __init__(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute('CREATE TABLE IF NOT EXISTS chunks_v1 (identity TEXT, idx INTEGER, vector BLOB, sha TEXT, metadata TEXT, PRIMARY KEY(identity,idx))')
        self.db.execute('CREATE TABLE IF NOT EXISTS tracks_v1 (identity TEXT PRIMARY KEY, vector BLOB, sha TEXT, metadata TEXT)')
        self.db.commit()

    @staticmethod
    def identity(track, config):
        return digest({'source_sha256': track['source_sha256'], 'extractor': config})

    def chunk(self, identity, index):
        row = self.db.execute('SELECT vector,sha,metadata FROM chunks_v1 WHERE identity=? AND idx=?', (identity,index)).fetchone()
        if row is None:
            return None
        if hashlib.sha256(row[0]).hexdigest() != row[1]:
            raise ValueError('chunk cache hash mismatch')
        return np.frombuffer(row[0], dtype='<f8').copy(), json.loads(row[2])

    def save_chunk(self, identity, index, vector, metadata):
        blob = np.asarray(vector, dtype='<f8').tobytes()
        with self.db:
            self.db.execute('INSERT INTO chunks_v1 VALUES (?,?,?,?,?)',
                            (identity,index,blob,hashlib.sha256(blob).hexdigest(),json.dumps(metadata,sort_keys=True,allow_nan=False)))

    def track(self, identity):
        row = self.db.execute('SELECT vector,sha,metadata FROM tracks_v1 WHERE identity=?', (identity,)).fetchone()
        if row is None:
            return None
        if hashlib.sha256(row[0]).hexdigest() != row[1]:
            raise ValueError('track cache hash mismatch')
        return np.frombuffer(row[0], dtype='<f4').copy(), json.loads(row[2])

    def save_track(self, identity, result):
        if result['status'] != 'OK' or len(result['chunks']) != (result['sample_count'] + 239999)//240000:
            raise ValueError('cannot cache incomplete track')
        blob = result['vector'].astype('<f4').tobytes()
        metadata = {k:v for k,v in result.items() if k not in ('vector','forward_passes','chunk_cache_hits')}
        with self.db:
            self.db.execute('INSERT INTO tracks_v1 VALUES (?,?,?,?)',
                            (identity,blob,hashlib.sha256(blob).hexdigest(),json.dumps(metadata,sort_keys=True,allow_nan=False)))

    def close(self):
        self.db.close()
