from __future__ import annotations

import csv
import hashlib
import json
import shutil
import wave
from pathlib import Path

import numpy as np

from audio_similarity.stage5c2_analysis import canonical_pair_id
from audio_similarity.stage5e1_analysis import REVIEW_COLUMNS, analyze_retrieval, build_review_queue
from audio_similarity.stage5e1_cache import Stage5E1Cache
from audio_similarity.stage5e1_config import experiment_config
from audio_similarity.stage5e1_materialize import _identity_fields, run_materialization
from audio_similarity.stage5e1_review import Stage5E1ReviewStore
from audio_similarity.stage5e1_sampling import CHUNK_SAMPLES, native_fusion_plan, sampling_plan


def _track(index: int, root) -> dict:
    spotify_id = f"track{index:02d}"
    directory = root / ".research_audio" / spotify_id
    directory.mkdir(parents=True, exist_ok=True)
    source = directory / "source.webm"
    source.write_bytes(f"audio-{index}".encode())
    return {
        "spotify_track_id": spotify_id,
        "title": f"Song {index}",
        "artists": [f"Artist {index}"],
        "album": "Album",
        "retained_source_path": str(source.relative_to(root)),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "youtube_video_id": f"video{index:06d}",
    }


def test_experiment_config_keeps_frozen_weights_and_matched_pairs() -> None:
    config = experiment_config()
    assert config["similarity"] == {
        "metric": "cosine",
        "clap_weight": 0.7172981519,
        "muq_weight": 0.2827018481,
        "weights_tuned_in_stage5e1": False,
    }
    assert config["comparison_interpretation"]["A_vs_C_matched_checkpoint"] is True
    assert config["comparison_interpretation"]["B_vs_D_matched_checkpoint_and_views"] is True
    assert config["arms"]["B"]["checkpoint_sha256"] == config["arms"]["D"]["checkpoint_sha256"]


def test_sampling_plan_shares_one_native_plan_for_b_and_d() -> None:
    plan = sampling_plan(CHUNK_SAMPLES * 4 + 17, "a" * 64)
    assert plan["native_fusion"] == native_fusion_plan(CHUNK_SAMPLES * 4 + 17, "a" * 64)
    assert plan["full_song_chunks"][-1]["end_sample"] == CHUNK_SAMPLES * 4 + 17


def test_blinded_queue_deduplicates_union_and_hides_origins_from_session(tmp_path) -> None:
    tracks = [_track(index, tmp_path) for index in range(7)]
    retrievals = {}
    for arm in "ABCD":
        for mode in ("CLAP", "COMBINED"):
            retrievals[f"{arm}_{mode}"] = [
                {"rank": rank, "spotify_track_id": tracks[index]["spotify_track_id"], "title": tracks[index]["title"], "artists": tracks[index]["artists"], "similarity": 0.9 - index / 100}
                for rank, index in enumerate(range(1, 6), 1)
            ]
    neighbors = {
        "tracks": [
            {"spotify_track_id": tracks[0]["spotify_track_id"], "retrievals": retrievals}
        ]
    }
    queue = build_review_queue(tmp_path, tracks, neighbors)
    assert queue["raw_directional_top5_relationships"] == 40
    assert queue["unique_unordered_pair_count"] == 5
    queue_path = tmp_path / "review_queue.json"
    queue_path.write_text(json.dumps(queue), encoding="utf-8")
    review_path = tmp_path / "review.csv"
    with review_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS)
        writer.writeheader()
        for pair in queue["pairs"]:
            writer.writerow(
                {
                    "review_schema_version": "stage5e1-human-similarity-review-v1",
                    "pair_id": pair["pair_id"],
                    "left_spotify_id": pair["left"]["spotify_track_id"],
                    "right_spotify_id": pair["right"]["spotify_track_id"],
                    "human_label": "",
                    "human_note": "",
                    "review_timestamp": "",
                    "label_provenance": "",
                }
            )
    store = Stage5E1ReviewStore(queue_path, review_path, tmp_path)
    session = store.session()
    encoded = json.dumps(session)
    assert '"origins"' not in encoded
    assert '"similarity"' not in encoded
    assert '"arm"' not in encoded
    page = store.session_page(offset=2, limit=2, review_filter="unreviewed")
    assert page["page"] == {
        "offset": 2,
        "limit": 2,
        "returned": 2,
        "filtered_total": 5,
        "filter": "unreviewed",
    }

    pair = session["pairs"][0]
    result = store.submit(pair["left"]["spotify_track_id"], pair["right"]["spotify_track_id"], "3", "moderate")
    assert result["pair_id"] == canonical_pair_id(pair["left"]["spotify_track_id"], pair["right"]["spotify_track_id"])
    assert store.session()["progress"]["reviewed_pairs"] == 1


class _FakeEncoder:
    embedding_dim = 512

    def __init__(self, encoder_id: str):
        self.encoder_id = encoder_id
        self.calls = 0
        self.sample_counts = []

    def encode_segment(self, waveform, sample_rate):
        self.calls += 1
        self.sample_counts.append(len(waveform))
        vector = np.zeros(512, dtype=np.float32)
        vector[self.calls % 512] = 1
        return vector


def _write_wav(path: Path, seconds: int = 30) -> None:
    rate = 8000
    samples = (np.sin(np.arange(rate * seconds) * 2 * np.pi * 220 / rate) * 8000).astype("<i2")
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(samples.tobytes())


def test_local_materialization_resumes_without_reinference(tmp_path) -> None:
    repository_root = Path(__file__).resolve().parents[1]
    report = tmp_path / "reports/stage5e1_four_arm_retrieval"
    report.mkdir(parents=True)
    contract_directory = tmp_path / "reports/holistic_stage4a_dual"
    contract_directory.mkdir(parents=True)
    shutil.copy2(
        repository_root / "reports/holistic_stage4a_dual/audio_representation_v1.json",
        contract_directory / "audio_representation_v1.json",
    )
    source_directory = tmp_path / ".research_audio/local-track"
    source_directory.mkdir(parents=True)
    source = source_directory / "source.wav"
    _write_wav(source, seconds=31)
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    from audio_similarity.stage5e1_encoders import decode_mono

    plan = sampling_plan(len(decode_mono(source, 48000)), source_sha)
    manifest = {
        "schema_version": "stage5e1-frozen-corpus-manifest-v1",
        "experiment_id": "STAGE5E1_FOUR_ARM_FULL_SONG_RETRIEVAL",
        "track_count": 1,
        "tracks": [{
            "spotify_track_id": "local-track",
            "title": "Local",
            "artists": ["Test"],
            "album": "Test",
            "youtube_video_id": "abcdefghijk",
            "retained_source_path": str(source.relative_to(tmp_path)),
            "source_sha256": source_sha,
        }],
    }
    config = experiment_config()
    plans = {
        "schema_version": "stage5e1-sampling-plans-v1",
        "tracks": [{"spotify_track_id": "local-track", "source_sha256": source_sha, "plan": plan}],
    }
    (report / "corpus_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (report / "experiment_config.json").write_text(json.dumps(config), encoding="utf-8")
    (report / "sampling_plans.json").write_text(json.dumps(plans), encoding="utf-8")
    clap, muq = _FakeEncoder("laion_clap"), _FakeEncoder("muq_mulan_large")
    first = run_materialization(
        tmp_path,
        arms=("A", "C", "MUQ"),
        baseline_encoders={"laion_clap": clap, "muq_mulan_large": muq},
    )
    assert first["network_downloads"] == 0
    assert clap.calls == 7
    assert clap.sample_counts[-1] == 48000
    assert muq.calls == 3
    second = run_materialization(
        tmp_path,
        arms=("A", "C", "MUQ"),
        baseline_encoders={"laion_clap": clap, "muq_mulan_large": muq},
    )
    assert clap.calls == 7
    assert muq.calls == 3
    assert all(row["inferred_views"] == 0 for row in second["results"])


def test_common_corpus_analysis_is_deterministic_and_excludes_self(tmp_path) -> None:
    repository_root = Path(__file__).resolve().parents[1]
    report = tmp_path / "reports/stage5e1_four_arm_retrieval"
    report.mkdir(parents=True)
    contract_directory = tmp_path / "reports/holistic_stage4a_dual"
    contract_directory.mkdir(parents=True)
    shutil.copy2(
        repository_root / "reports/holistic_stage4a_dual/audio_representation_v1.json",
        contract_directory / "audio_representation_v1.json",
    )
    tracks = [_track(index, tmp_path) for index in range(7)]
    manifest = {
        "schema_version": "stage5e1-frozen-corpus-manifest-v1",
        "experiment_id": "STAGE5E1_FOUR_ARM_FULL_SONG_RETRIEVAL",
        "track_count": len(tracks),
        "tracks": tracks,
    }
    config = experiment_config()
    plans = {
        "schema_version": "stage5e1-sampling-plans-v1",
        "tracks": [
            {
                "spotify_track_id": track["spotify_track_id"],
                "source_sha256": track["source_sha256"],
                "plan": sampling_plan(CHUNK_SAMPLES * 3, track["source_sha256"]),
            }
            for track in tracks
        ],
    }
    for name, payload in (("corpus_manifest.json", manifest), ("experiment_config.json", config), ("sampling_plans.json", plans)):
        (report / name).write_text(json.dumps(payload), encoding="utf-8")
    config_sha = hashlib.sha256((report / "experiment_config.json").read_bytes()).hexdigest()
    from audio_similarity.stage5e1_analysis import load_muq_checkpoint_identity

    cache_path = tmp_path / "artifacts/stage5e1_four_arm_retrieval/representations.sqlite"
    with Stage5E1Cache(cache_path) as cache:
        for track_index, track in enumerate(tracks):
            plan_sha = plans["tracks"][track_index]["plan"]["sampling_plan_sha256"]
            for arm_index, arm in enumerate(("A", "B", "C", "D", "MUQ")):
                checkpoint = load_muq_checkpoint_identity(tmp_path) if arm == "MUQ" else config["arms"][arm]["checkpoint_sha256"]
                identity, fields = _identity_fields(track, arm, config_sha, plan_sha, checkpoint)
                vector = np.zeros(512, dtype=np.float32)
                vector[(track_index * 7 + arm_index) % 512] = 1
                vector[511] = 0.1 + track_index / 100
                cache.record_vector(identity, fields, status="SUCCESS", embedding=vector, view_count=3, inference_seconds=0)
    first = analyze_retrieval(tmp_path)
    queue_before = (report / "review_queue.json").read_bytes()
    second = analyze_retrieval(tmp_path)
    assert first == second
    assert first["common_comparison_count"] == 7
    assert first["raw_directional_top5_relationships"] == 7 * 4 * 2 * 5
    assert (report / "review_queue.json").read_bytes() == queue_before
    neighbors = json.loads((report / "nearest_neighbors.json").read_text())
    for track in neighbors["tracks"]:
        for rows in track["retrievals"].values():
            assert track["spotify_track_id"] not in {row["spotify_track_id"] for row in rows}
