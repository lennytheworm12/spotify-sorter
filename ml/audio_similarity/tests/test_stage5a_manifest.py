import pandas as pd
import torch

from audio_similarity.stage5a_manifest import (
    build_fma_large_manifest,
    deterministic_smoke_tracks,
    eligible_tracks,
    load_fma_large_manifest,
)
from tests.helpers import save_wav


def metadata(rows):
    columns = pd.MultiIndex.from_tuples(
        [
            ("track", "title"),
            ("artist", "name"),
            ("album", "title"),
            ("track", "genre_top"),
            ("set", "split"),
            ("set", "subset"),
        ]
    )
    values = [["title", "artist", "album", "genre", "training", row[1]] for row in rows]
    frame = pd.DataFrame(values, columns=columns, index=[row[0] for row in rows])
    frame.index.name = "track_id"
    return frame


def test_fma_large_manifest_accounts_for_missing_invalid_and_discovered(tmp_path):
    audio = tmp_path / "audio"
    audio.mkdir()
    save_wav(audio / "000001.wav", torch.full((1, 720000), 0.1), 24000)
    save_wav(audio / "000002.wav", torch.full((1, 24000), 0.1), 24000)
    (audio / "000003.wav").write_bytes(b"corrupt")
    save_wav(audio / "000005.wav", torch.full((1, 720000), 0.1), 24000)
    save_wav(audio / "000006.wav", torch.full((1, 720000), 0.1), 24000)
    tracks_csv = tmp_path / "tracks.csv"
    metadata([(1, "large"), (2, "large"), (3, "large"), (4, "large"), (6, "small")]).to_csv(tracks_csv)

    frame, summary = build_fma_large_manifest(audio, tracks_csv, tmp_path / "manifest.parquet", corpus_version="fixture-v1")
    statuses = dict(zip(frame.track_id, frame.status))
    assert statuses == {
        1: "ELIGIBLE",
        2: "TOO_SHORT",
        3: "DECODE_FAILED",
        4: "MISSING_AUDIO",
        5: "MISSING_METADATA",
        6: "ELIGIBLE",
    }
    assert summary["official_fma_large_metadata_tracks"] == 5
    assert summary["discovered_source_tracks"] == 5
    assert summary["accounted_track_identities"] == 6
    assert summary["eligible_tracks"] == 2
    assert len(summary["manifest_logical_sha256"]) == 64
    selected = eligible_tracks(frame, audio)
    assert [track.stable_track_id for track in selected] == ["1", "6"]
    loaded, loaded_summary = load_fma_large_manifest(tmp_path / "manifest.parquet")
    pd.testing.assert_frame_equal(loaded, frame)
    assert loaded_summary == summary


def test_fma_large_manifest_logical_hash_is_deterministic(tmp_path):
    audio = tmp_path / "audio"
    audio.mkdir()
    save_wav(audio / "000001.wav", torch.full((1, 720000), 0.1), 24000)
    tracks_csv = tmp_path / "tracks.csv"
    metadata([(1, "large")]).to_csv(tracks_csv)
    _, first = build_fma_large_manifest(audio, tracks_csv, tmp_path / "one.parquet", corpus_version="fixture-v1")
    _, second = build_fma_large_manifest(audio, tracks_csv, tmp_path / "two.parquet", corpus_version="fixture-v1")
    assert first["manifest_logical_sha256"] == second["manifest_logical_sha256"]


def test_smoke_selection_is_hash_deterministic_and_bounded(tmp_path):
    frame = pd.DataFrame(
        [
            {
                "track_id": track_id,
                "relative_audio_path": f"{track_id}.wav",
                "source_audio_sha256": str(track_id),
                "file_size_bytes": 1,
                "duration_sec": 30.0,
                "metadata_subset": "large",
                "status": "ELIGIBLE",
                "detail": "",
            }
            for track_id in range(20)
        ]
    )
    first = deterministic_smoke_tracks(frame, tmp_path, manifest_sha256="a" * 64, count=5)
    second = deterministic_smoke_tracks(frame, tmp_path, manifest_sha256="a" * 64, count=5)
    assert first == second and len(first) == 5
