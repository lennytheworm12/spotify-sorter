import hashlib
import sqlite3

import numpy as np
import pytest

from audio_similarity.calibration.audit_analysis import (
    classify_source, recording_groups, sample_members, split_preflight,
)
from audio_similarity.calibration.audit_capture import Capture, read_db, vector_valid


def test_external_credit_is_not_owner_authorship_or_algorithm_proof():
    note = 'Captured playlist reference — 50 tracks, curated by Spotify.\n**Source:** https://open.spotify.com/playlist/abc123\n'
    row = classify_source(note, 'Boom Bap Mix', {'artist1', 'artist2'})
    assert row['curator'] == 'Spotify'
    assert row['provenance_kind'] == 'externally_attributed_capture'
    assert row['layer'] == 'C_candidate'
    assert 'TITLE_DOES_NOT_PROVE_PERSONALIZED_ALGORITHM_OR_HUMAN_MIX' in row['warnings']
    unknown = classify_source(note.replace('Spotify.', 'unknown.'), 'Neo Soul', {'a', 'b'})
    assert unknown['curator'] is None
    assert classify_source(note, 'Jazz', {'a'})['layer'] is None


def test_purge_links_are_conservative_and_do_not_merge_remix_by_title():
    tracks = {
        'a': {'title': 'Song', 'artists': ['Artist'], 'duration_ms': 100000},
        'b': {'title': ' song ', 'artists': ['ARTIST'], 'duration_ms': 200000},
        'c': {'title': 'Song (Remix)', 'artists': ['Artist'], 'duration_ms': 100000},
    }
    groups, links = recording_groups(tracks, {})
    assert groups['a'] == groups['b'] != groups['c']
    assert links == [{'a': 'b', 'b': 'a', 'basis': 'exact_title_credits'}]


def test_sampling_is_whole_list_deterministic_artist_capped_and_no_feature_input():
    tracks = {f'r{i:03}': {'artists': [f'a{i // 5}']} for i in range(100)}
    versions = {k: k for k in tracks}
    sample = sample_members(list(tracks), tracks, versions, 'fixed')
    assert sample == sample_members(list(reversed(tracks)), tracks, versions, 'fixed')
    assert len(sample) == 30
    assert max(sum(tracks[k]['artists'] == tracks[j]['artists'] for j in sample) for k in sample) <= 3
    assert sample != list(tracks)[:30]


def fixtures():
    tracks, playlists = {}, []
    for p in range(9):
        keys = [f'p{p}r{i:02}' for i in range(30)]
        for i, k in enumerate(keys):
            tracks[k] = {'title': k, 'artists': [f'artist{i}']}
        playlists.append({'playlist_id': f'p{p}', 'curator': f'curator{p}', 'layer': 'A_candidate',
            'sample_primary_artists': 30, 'sample_request_ids': keys, 'request_ids': keys})
    return tracks, playlists, {k: k for k in tracks}


def test_conditional_split_does_not_clear_sources_and_single_owner_fails():
    tracks, playlists, versions = fixtures()
    # Force a known cross-playlist recording-version link.
    versions['p1r00'] = versions['p0r00']
    result = split_preflight(playlists, tracks, versions, set(tracks))
    assert result['status'] == 'CONDITIONAL_DEVELOPMENT_GEOMETRY_FEASIBLE'
    assert result['cleared_sources'] == 0 and result['lockbox_reserved'] is False
    for row in result['partitions']:
        for r in [row, *row['inner']]:
            p = r['partition']
            assert not {versions[k] for k in p['fit_recordings']} & {versions[k] for k in p['evaluation_recordings']}
    owner = split_preflight(playlists, tracks, versions, set(tracks), collapse_owner=True)
    assert owner['status'] == 'INSUFFICIENT_DATA' and owner['source_groups'] == 1


def test_full_source_duplicates_survive_distinct_sampling():
    tracks, playlists, versions = fixtures()
    # Same full source list, but samples intentionally select disjoint halves.
    full = playlists[0]['request_ids'] + playlists[1]['request_ids']
    playlists[0]['request_ids'] = full
    playlists[1]['request_ids'] = full
    result = split_preflight(playlists, tracks, versions, set(tracks))
    assert result['cluster_map']['p0'] == result['cluster_map']['p1']


def test_capture_detects_changing_inputs(tmp_path):
    path = tmp_path / 'state.json'
    path.write_text('{}')
    cap = Capture(tmp_path)
    cap.read('state.json')
    path.write_text('{"changed":true}')
    with pytest.raises(ValueError, match='changed'):
        cap.read('state.json')


def test_sqlite_connection_is_read_only(tmp_path):
    path = tmp_path / 'test.sqlite'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE sample (value TEXT)')
    before = path.read_bytes()
    db = read_db(path)
    try:
        with pytest.raises(sqlite3.OperationalError):
            db.execute("INSERT INTO sample VALUES ('mutation')")
    finally:
        db.close()
    assert path.read_bytes() == before


def test_embedding_hash_shape_and_normalization_fail_closed():
    x = np.zeros(512, dtype='<f4')
    x[0] = 1
    blob = x.tobytes()
    row = {'embedding': blob, 'embedding_sha256': hashlib.sha256(blob).hexdigest()}
    assert vector_valid(row)
    assert not vector_valid(row, 256)
    assert not vector_valid(dict(row, embedding_sha256='0' * 64))
    zero = np.zeros(512, dtype='<f4').tobytes()
    assert not vector_valid({'embedding': zero, 'embedding_sha256': hashlib.sha256(zero).hexdigest()})
