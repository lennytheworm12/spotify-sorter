"""Capture/replay a read-only real-corpus audit. Never calls the selection harness."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import subprocess

from ..calibration.audit_analysis import analyze
from ..calibration.audit_capture import capture
from ..calibration.audit_report import draft_manifest, markdown
from ..calibration.contracts import digest, file_hash, freeze_json, require

VAULT_COMMIT = '1be145263f0e6405a68b3d9a0949ce7218ddc6a4'
PROTOCOLS = (
    'Spotify Playlist Reconstruction — Joint Audio and Genre Weight Calibration Design.md',
    'Spotify Playlist Reconstruction — v1.1 Protocol Reference.md',
    'Spotify Output Calibration — Scores, Admission and User Strictness.md',
)


def write_text(path, text):
    raw = text.encode()
    if path.exists():
        require(path.read_bytes() == raw, f'audit artifact differs: {path}')
    else:
        with path.open('xb') as stream:
            stream.write(raw)


def implementation_hashes(root):
    paths = sorted((root / 'src/audio_similarity/calibration').glob('*.py'))
    paths += [Path(__file__).resolve(), root / 'src/audio_similarity/stage5e1_cache.py',
              root / 'src/audio_similarity/stage5a_contract.py', root / 'src/audio_similarity/stage5d0a_manifest.py']
    return {str(p.relative_to(root)): file_hash(p) for p in paths}


def emit(data, output):
    audit = analyze(data)
    manifest = draft_manifest(data, audit)
    freeze_json(output / 'audit.private.json', audit)
    freeze_json(output / 'draft_execution_manifest.json', manifest)
    write_text(output / 'REPORT.md', markdown(audit, manifest))
    columns = ('title', 'curator', 'provenance_kind', 'cohort', 'stratum', 'actual_eligibility',
               'original_table_rows', 'distinct_requests', 'primary_artists', 'sample_primary_artists',
               'sample_verified_audio', 'membership_use_permission', 'source_note_sha256')
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=columns, lineterminator='\n')
    writer.writeheader()
    writer.writerows({k: p[k] for k in columns} for p in audit['playlists'])
    write_text(output / 'source_inventory.private.csv', stream.getvalue())
    freeze_json(output / 'artifact_manifest.json', {'schema': 'real-calibration-audit-artifacts-v1',
        'capture_sha256': digest(data), 'files': {name: file_hash(output / name) for name in
            ('audit.private.json', 'draft_execution_manifest.json', 'REPORT.md', 'source_inventory.private.csv')}})
    return {k: audit[k] for k in ('source_readiness', 'feature_readiness', 'full_evaluation_feasibility',
            'initial_requests', 'initial_queue_states', 'verified_features', 'all_four_features', 'provenance_counts')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('capture', 'replay'))
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--snapshot', type=Path)
    parser.add_argument('--owner-statement', type=Path,
                        help='Optional explicit provenance statement captured with a new audit, not a clearance override')
    parser.add_argument('--vault-git-dir', type=Path, default=Path('/tmp/spotify-vault-review'))
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output.resolve()
    audit_root = root / '.research_audio/calibration_corpus_audits'
    require(output.is_relative_to(audit_root) and output != audit_root,
            'output must be a new run under .research_audio/calibration_corpus_audits/')
    output.mkdir(parents=True, exist_ok=True)
    if args.command == 'capture':
        require(not (output / 'capture.private.json').exists(), 'capture exists; use replay or a new run')
        data = capture(root)
        if args.owner_statement:
            raw = args.owner_statement.read_bytes()
            statement = json.loads(raw)
            require(set(statement) == {'owner_message', 'recorded_date', 'interpretation'}, 'owner statement schema differs')
            data['owner_clarification'] = statement | {'sha256': hashlib.sha256(raw).hexdigest()}
        protocols = []
        for name in PROTOCOLS:
            path = 'Projects/Spotify Sorter/' + name
            raw = subprocess.check_output(['git', '--git-dir=' + str(args.vault_git_dir), 'show', VAULT_COMMIT + ':' + path])
            protocols.append({'vault_commit': VAULT_COMMIT, 'path': path,
                              'sha256': hashlib.sha256(raw).hexdigest(), 'text': raw.decode()})
        for name in ('playlist-reconstruction-calibration-v1.md', 'output-calibration-v1.md'):
            p = root.parent.parent / 'docs/genre-force' / name
            protocols.append({'path': str(p.relative_to(root.parent.parent)), 'sha256': file_hash(p), 'text': p.read_text()})
        data['protocols'] = protocols
        data['implementation_hashes'] = implementation_hashes(root)
        freeze_json(output / 'capture.private.json', data)
        freeze_json(output / 'capture_hash.json', {'sha256': file_hash(output / 'capture.private.json')})
    else:
        require(args.owner_statement is None, 'replay cannot amend captured owner statements')
        require(args.snapshot is not None, 'replay requires --snapshot')
        expected = json.loads(args.snapshot.with_name('capture_hash.json').read_text())['sha256']
        require(file_hash(args.snapshot) == expected, 'captured input hash mismatch')
        data = json.loads(args.snapshot.read_text())
        require(data['implementation_hashes'] == implementation_hashes(root), 'audit implementation changed')
    print(json.dumps(emit(data, output), indent=2))


if __name__ == '__main__':
    main()
