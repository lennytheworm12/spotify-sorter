"""Separate supplied model instructions from private pilot identities/evaluation."""
from __future__ import annotations

import json
import re
from pathlib import Path

from audio_similarity.stage5e3_artifacts import freeze, freeze_json, hashes


def extract_contract(document: str) -> dict:
    """Accept the supplied v1 layout, failing closed on ambiguous or missing inputs."""
    candidates_section = document.split('### Candidate manifest and pre-run hypotheses\n', 1)[1]
    candidates_section = candidates_section.split('**Resolution notes', 1)[0]
    candidates = []
    for line in candidates_section.splitlines():
        if not re.match(r'^\| [AC]\d\d \|', line):
            continue
        cells = [cell.strip() for cell in line.split('|')[1:-1]]
        if len(cells) != 7:
            raise ValueError('unexpected candidate table layout')
        match = re.fullmatch(r'\[(\w{22})\]\(https://open.spotify.com/track/\1\)', cells[3])
        if not match:
            raise ValueError('candidate has no unambiguous stable Spotify identity')
        # Deliberately do not carry slice, hypotheses or rationale into the manifest.
        candidates.append({'pilot_id': cells[0], 'spotify_track_id': match[1],
                           'catalog_description': cells[2]})
    expected = [f'A{i:02d}' for i in range(1, 11)] + [f'C{i:02d}' for i in range(1, 7)]
    if [row['pilot_id'] for row in candidates] != expected:
        raise ValueError('the complete ordered 16-candidate design is required')
    if len({row['spotify_track_id'] for row in candidates}) != 16:
        raise ValueError('duplicate candidate identity')
    ontology = document.split('## 3. Operational ontology\n', 1)[1].split('\n## 4.', 1)[0]
    schema_section = document.split('## 4. Exact JSON response contract\n', 1)[1]
    blocks = re.findall(r'```json\n(.*?)\n```', schema_section, flags=re.DOTALL)
    if len(blocks) != 1:
        raise ValueError('expected exactly one response schema')
    schema_text = blocks[0] + '\n'
    schema = json.loads(schema_text)
    style_section = ontology.split('### 3.2 Allowed styles', 1)[1].split('### 3.3', 1)[0]
    styles = {}
    for line in style_section.splitlines():
        if not line.startswith('| '):
            continue
        cells = [cell.strip() for cell in line.split('|')[1:-1]]
        if cells[0] not in schema['properties']['primary_style']['enum']:
            continue
        styles[cells[0]] = cells[1].split(', ')
    if set(styles) != set(schema['properties']['primary_style']['enum']):
        raise ValueError('incomplete style/family mapping')
    return {'candidates': candidates, 'ontology': ontology, 'schema_text': schema_text,
            'schema': schema, 'style_allowed_families': styles}


def freeze_contract(design: Path, prompt: Path, destination: Path) -> dict:
    """Freeze exact input bytes and only the safe ontology/schema for later requests."""
    contract = extract_contract(design.read_text())
    freeze(destination / 'private/design-contract.md', design.read_bytes())
    freeze(destination / 'model/prompt.txt', prompt.read_bytes())
    freeze(destination / 'model/ontology.md', contract['ontology'].encode())
    freeze(destination / 'model/response_schema.json', contract['schema_text'].encode())
    freeze_json(destination / 'private/candidates.json', contract['candidates'])
    freeze_json(destination / 'style_allowed_families.json', contract['style_allowed_families'])
    checksums = hashes([p for p in destination.rglob('*') if p.is_file()], destination)
    # Hash index excludes itself so identical extraction is replayable.
    checksums.pop('input_hashes.json', None)
    freeze_json(destination / 'input_hashes.json', checksums)
    return contract
