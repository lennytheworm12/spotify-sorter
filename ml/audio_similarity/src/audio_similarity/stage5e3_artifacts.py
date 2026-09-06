"""Canonical, create-once scientific artifacts for the Stage 5E.3 run."""
from __future__ import annotations
import hashlib
import io
import json
import os
import tempfile
import zipfile
from pathlib import Path
import numpy as np
from .stage5b1a_models import file_sha256


def json_bytes(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2) + '\n').encode()


def digest(value):
    return hashlib.sha256(json_bytes(value)).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def freeze(path, data):
    """Publish atomically without ever replacing a different existing artifact."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f'frozen artifact differs: {path}; use a new versioned run')
        return
    fd, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(name, path)
        except FileExistsError:
            if path.read_bytes() != data:
                raise ValueError(f'concurrent frozen artifact differs: {path}')
    finally:
        os.unlink(name)


def freeze_json(path, value):
    freeze(path, json_bytes(value))


def npz_bytes(arrays):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_STORED) as archive:
        for name, array in sorted(arrays.items()):
            buf = io.BytesIO()
            np.save(buf, np.asarray(array), allow_pickle=False)
            info = zipfile.ZipInfo(name + '.npy', date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o600 << 16
            archive.writestr(info, buf.getvalue())
    return output.getvalue()


def freeze_parquet(path, rows, sort_keys):
    import pyarrow as pa
    import pyarrow.parquet as pq
    ordered = sorted(rows, key=lambda r: tuple(r[k] for k in sort_keys))
    table = pa.Table.from_pylist(ordered)
    out = io.BytesIO()
    pq.write_table(table, out, version='2.6', compression='NONE', use_dictionary=False,
                   write_statistics=True, row_group_size=65536)
    freeze(path, out.getvalue())


def hashes(paths, root):
    return {str(p.relative_to(root)): file_sha256(p) for p in sorted(set(paths)) if p.is_file()}


def verify_hashes(root, expected):
    for name, sha in expected.items():
        path = Path(root) / name
        if not path.is_file() or file_sha256(path) != sha:
            raise ValueError(f'integrity mismatch: {name}')
