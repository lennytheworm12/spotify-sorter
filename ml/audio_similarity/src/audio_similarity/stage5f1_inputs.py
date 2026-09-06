"""Frozen source, matrix, and human-rating adapters for Stage 5F.1."""

from __future__ import annotations

import csv
import itertools
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from .energy_motion_audio import file_sha256
from .stage5c2_analysis import canonical_pair_id


PRIOR = Path("reports/stage5e1_four_arm_retrieval")
SELECTED = Path("reports/stage5c2_representative_100_amended_v2/selected_sources.json")
STAGE5E2 = Path("reports/stage5e2_arm_d_original100_v2")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def frozen_tracks(root: Path, corpus: str = "original100") -> list[dict[str, Any]]:
    manifest = read_json(root / PRIOR / "corpus_manifest.json")
    if manifest.get("track_count") != 741 or len(manifest.get("tracks", [])) != 741:
        raise ValueError("expected frozen 741-track Stage 5E.1 manifest")
    by_id = {row["spotify_track_id"]: row for row in manifest["tracks"]}
    if corpus == "reference741":
        selected_ids = sorted(by_id)
    elif corpus == "original100":
        selected = read_json(root / SELECTED)
        if len(selected.get("tracks", [])) != 100:
            raise ValueError("expected exactly 100 amended selected sources")
        selected_video = {row["spotify_track_id"]: row["selected_youtube_video_id"] for row in selected["tracks"]}
        selected_ids = sorted(selected_video)
        if any(track_id not in by_id or by_id[track_id]["youtube_video_id"] != selected_video[track_id] for track_id in selected_ids):
            raise ValueError("original100 selected video identity mismatch")
    else:
        raise ValueError(f"unsupported corpus: {corpus}")
    rows = []
    for track_id in selected_ids:
        source = by_id[track_id]
        path = root / source["retained_source_path"]
        rows.append({
            "spotify_track_id": track_id,
            "source_sha256": source["source_sha256"],
            "retained_source_path": str(path),
            "youtube_video_id": source["youtube_video_id"],
            "duration_seconds": source.get("duration_seconds"),
            "sample_rate_hz": source.get("sample_rate_hz"),
            "channels": source.get("channels"),
            "source_format": source.get("container"),
            "source_bitrate_when_available": source.get("bit_rate"),
            "title": source.get("title"),
            "artists": source.get("artists", []),
            "artist_credit": ", ".join(source.get("artists", [])),
            "primary_artist_id": None,
            "corpus_memberships": ["stage5e1_741"] + (["original100"] if track_id in set(selected_ids) and corpus == "original100" else []),
            "local_file_exists": path.is_file(),
        })
    return rows


def frozen_matrices(root: Path, ids: list[str]) -> dict[str, np.ndarray]:
    config = read_json(root / PRIOR / "experiment_config.json")
    weights = config["similarity"]
    if not np.isclose(weights["clap_weight"], 0.7172981519) or not np.isclose(weights["muq_weight"], 0.2827018481):
        raise ValueError("frozen fusion weights changed")
    with np.load(root / PRIOR / "similarity_matrices.npz", allow_pickle=False) as archive:
        matrix_ids = list(archive["spotify_ids"].astype(str))
        if len(matrix_ids) != len(set(matrix_ids)):
            raise ValueError("duplicate matrix IDs")
        positions = [matrix_ids.index(track_id) for track_id in ids]
        result = {
            "a_clap": archive["a_clap"][np.ix_(positions, positions)].copy(),
            "muq": archive["muq"][np.ix_(positions, positions)].copy(),
            "a_combined": archive["a_combined"][np.ix_(positions, positions)].copy(),
        }
    expected = weights["clap_weight"] * result["a_clap"] + weights["muq_weight"] * result["muq"]
    if not np.allclose(expected, result["a_combined"], atol=2e-6):
        raise ValueError("frozen combined matrix does not match configured A+MuQ fusion")
    for name, matrix in result.items():
        if not np.isfinite(matrix).all() or not np.allclose(matrix, matrix.T, atol=1e-6):
            raise ValueError(f"invalid frozen {name} matrix")
    return result


def _current_stage5e2_evidence(root: Path, valid_ids: set[str]) -> list[dict[str, Any]]:
    state = root / ".research_audio/stage5e2_original100_v2_review/human_similarity_review.csv"
    queue_path = root / STAGE5E2 / "review_queue.json"
    if not state.is_file() or not queue_path.is_file():
        return []
    queue = read_json(queue_path)
    pairs = {row["pair_id"]: row for row in queue["pairs"]}
    source_file_sha = file_sha256(state)
    evidence = []
    with state.open(newline="", encoding="utf-8-sig") as handle:
        for row_number, row in enumerate(csv.DictReader(handle), 2):
            label = row.get("human_label", "").strip().upper()
            pair_id = row.get("pair_id", "")
            frozen = pairs.get(pair_id)
            if label not in {"1", "2", "3", "4", "5", "UNSURE"} or not frozen:
                continue
            ids = {frozen["left"]["spotify_track_id"], frozen["right"]["spotify_track_id"]}
            if len(ids) != 2 or not ids <= valid_ids:
                continue
            evidence.append({
                "pair_id": pair_id,
                "label": label,
                "source": str(state.relative_to(root)),
                "source_sha256": source_file_sha,
                "source_identity_basis": "same Stage5E2 original100 frozen source SHA and review queue",
                "timestamp": row.get("review_timestamp", ""),
                "note": row.get("human_note", ""),
                "row_number": row_number,
            })
    return evidence


def snapshot_compatible_labels(root: Path, tracks: list[dict[str, Any]]) -> dict[str, Any]:
    valid_ids = {row["spotify_track_id"] for row in tracks}
    base_evidence = read_json(root / STAGE5E2 / "label_evidence.json")
    evidence = [row | {"row_number": row.get("row_number")} for row in base_evidence]
    evidence.extend(_current_stage5e2_evidence(root, valid_ids))
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in evidence:
        grouped[row["pair_id"]].append(row)
    resolved: dict[str, int] = {}
    conflicts: dict[str, list[int]] = {}
    unsure: list[str] = []
    pair_members = {
        canonical_pair_id(left, right): [left, right]
        for left, right in itertools.combinations(sorted(valid_ids), 2)
    }
    for pair_id, rows in sorted(grouped.items()):
        numeric = sorted({int(row["label"]) for row in rows if row["label"] in {"1", "2", "3", "4", "5"}})
        if len(numeric) == 1:
            resolved[pair_id] = numeric[0]
        elif len(numeric) > 1:
            conflicts[pair_id] = numeric
        elif any(row["label"] == "UNSURE" for row in rows):
            unsure.append(pair_id)
    return {
        "schema_version": "stage5f1-compatible-rating-snapshot-v1",
        "evidence": sorted(evidence, key=lambda row: (row["pair_id"], row["source"], row.get("row_number") or 0)),
        "resolved_labels": resolved,
        "pair_members": {pair: pair_members[pair] for pair in sorted(set(grouped) & pair_members.keys())},
        "conflicts": conflicts,
        "unsure_pairs": sorted(unsure),
        "counts": {
            "evidence_rows": len(evidence),
            "resolved_numeric_pairs": len(resolved),
            "conflicting_pairs": len(conflicts),
            "unsure_only_pairs": len(unsure),
        },
    }


def input_hashes(root: Path) -> dict[str, str]:
    paths = [
        PRIOR / "corpus_manifest.json",
        PRIOR / "experiment_config.json",
        PRIOR / "similarity_matrices.npz",
        SELECTED,
        STAGE5E2 / "label_evidence.json",
        STAGE5E2 / "review_queue.json",
    ]
    current = Path(".research_audio/stage5e2_original100_v2_review/human_similarity_review.csv")
    if (root / current).is_file():
        paths.append(current)
    return {str(path): file_sha256(root / path) for path in paths}
