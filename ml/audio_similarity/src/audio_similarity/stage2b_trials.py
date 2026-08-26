"""Encoder-neutral balanced disagreement trial generation for Stage 2B."""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .stage2b_audio import PcmIdentity, PcmIdentityCache
from .stage2b_contract import ContractError, load_contract, sha256_file, validate_input_hashes


class BalanceGateError(ContractError):
    """The frozen 10% source-class balance gate failed."""


def identity_duplicate(first: PcmIdentity, second: PcmIdentity) -> bool:
    """Apply only the four frozen exact-identity rules."""
    return (
        first.track_id == second.track_id
        or first.source_sha256 == second.source_sha256
        or first.canonical_30s_pcm_sha256 == second.canonical_30s_pcm_sha256
        or first.center5_v1_pcm_sha256 == second.center5_v1_pcm_sha256
    )


def load_validated_embeddings(path: Path, expected_hash: str, analysis_key: str, dimensions: int) -> dict[int, np.ndarray]:
    if sha256_file(path) != expected_hash:
        raise ContractError(f"embedding SHA-256 mismatch: {path}")
    frame = pd.read_parquet(path)
    if set(frame["analysis_key"].astype(str)) != {analysis_key}:
        raise ContractError(f"analysis key mismatch: {path}")
    frame = frame[frame["status"] == "SUCCESS"]
    vectors: dict[int, np.ndarray] = {}
    for row in frame.itertuples(index=False):
        vector = np.asarray(row.embedding, dtype=np.float64)
        if vector.shape != (dimensions,) or not np.isfinite(vector).all():
            raise ContractError(f"invalid embedding for track {row.track_id} in {path}")
        norm = float(np.linalg.norm(vector))
        if norm <= 0:
            raise ContractError(f"zero embedding for track {row.track_id} in {path}")
        vectors[int(row.track_id)] = (vector / norm).astype(np.float32)
    return vectors


def _score_order(vectors: dict[int, np.ndarray], query_id: int, excluded_queries: set[int]) -> tuple[list[int], dict[int, float], dict[int, int]]:
    ids = np.asarray(sorted(vectors), dtype=np.int64)
    matrix = np.stack([vectors[int(track_id)] for track_id in ids])
    scores = matrix @ vectors[query_id]
    order = np.lexsort((ids, -scores))
    ordered = [int(ids[index]) for index in order if int(ids[index]) not in excluded_queries]
    score_map = {int(ids[index]): float(scores[index]) for index in order}
    ranks = {track_id: rank for rank, track_id in enumerate(ordered, start=1)}
    return ordered, score_map, ranks


def _identity_sets(identities: list[PcmIdentity]) -> tuple[set[str], set[str], set[str]]:
    return (
        {item.source_sha256 for item in identities},
        {item.canonical_30s_pcm_sha256 for item in identities},
        {item.center5_v1_pcm_sha256 for item in identities},
    )


def _matches_identity_sets(identity: PcmIdentity, sets: tuple[set[str], set[str], set[str]]) -> bool:
    return (
        identity.source_sha256 in sets[0]
        or identity.canonical_30s_pcm_sha256 in sets[1]
        or identity.center5_v1_pcm_sha256 in sets[2]
    )


def _orientation(seed: int, canonical_identity: str) -> bool:
    digest = hashlib.sha256(f"{seed}|{canonical_identity}".encode()).digest()
    return bool(digest[0] & 1)


def _opaque_id(seed: int, canonical_identity: str) -> str:
    return "s2b_" + hashlib.sha256(f"trial|{seed}|{canonical_identity}".encode()).hexdigest()[:24]


def _pair_name(pair: list[str] | tuple[str, str]) -> str:
    return f"{pair[0]}__vs__{pair[1]}"


def _eligible_disagreements(
    query_id: int,
    encoder_x: str,
    encoder_y: str,
    pool_x: list[int],
    pool_y: list[int],
    scores: dict[str, dict[int, float]],
    ranks: dict[str, dict[int, int]],
    identities: dict[int, PcmIdentity],
) -> list[dict[str, Any]]:
    eligible = []
    for preferred_x in pool_x:
        for preferred_y in pool_y:
            if preferred_x == preferred_y:
                continue
            identity_x, identity_y = identities[preferred_x], identities[preferred_y]
            if identity_duplicate(identity_x, identity_y):
                continue
            x_gap = scores[encoder_x][preferred_x] - scores[encoder_x][preferred_y]
            y_gap = scores[encoder_y][preferred_y] - scores[encoder_y][preferred_x]
            if x_gap <= 0 or y_gap <= 0:
                continue
            source_rank_x = ranks[encoder_x][preferred_x]
            source_rank_y = ranks[encoder_y][preferred_y]
            opposing_rank_x = ranks[encoder_x][preferred_y]
            opposing_rank_y = ranks[encoder_y][preferred_x]
            eligible.append({
                "preferred_x": preferred_x,
                "preferred_y": preferred_y,
                "source_rank_x": source_rank_x,
                "source_rank_y": source_rank_y,
                "opposing_rank_x": opposing_rank_x,
                "opposing_rank_y": opposing_rank_y,
                "x_gap": float(x_gap),
                "y_gap": float(y_gap),
                "sort_key": (
                    max(source_rank_x, source_rank_y),
                    source_rank_x + source_rank_y,
                    -((opposing_rank_x - source_rank_x) + (opposing_rank_y - source_rank_y)),
                    min(preferred_x, preferred_y),
                    max(preferred_x, preferred_y),
                ),
            })
    return sorted(eligible, key=lambda row: row["sort_key"])


def build_balanced_trials(config_path: str | Path, root: str | Path = ".") -> dict[str, Any]:
    root = Path(root)
    config_path = Path(config_path)
    config = load_contract(config_path)
    validate_input_hashes(config, root)
    report_dir = root / config["paths"]["report_dir"]
    split_manifest = json.loads((report_dir / "query_split_manifest.json").read_text(encoding="utf-8"))
    if split_manifest["config_sha256"] != sha256_file(config_path):
        raise ContractError("query split was not generated from this contract")
    query_rows = split_manifest["queries"]
    query_ids = {int(row["query_id"]) for row in query_rows}
    split_by_query = {int(row["query_id"]): row["split"] for row in query_rows}

    manifest = pd.read_parquet(root / config["inputs"]["manifest"]["path"]).set_index("track_id")
    embeddings: dict[str, dict[int, np.ndarray]] = {}
    for encoder_id, spec in config["inputs"]["embeddings"].items():
        embeddings[encoder_id] = load_validated_embeddings(
            root / spec["path"], spec["sha256"], spec["analysis_key"], int(spec["dimensions"])
        )
        missing = query_ids - set(embeddings[encoder_id])
        if missing:
            raise ContractError(f"{encoder_id} missing frozen queries: {sorted(missing)}")
    common_ids = set.intersection(*(set(values) for values in embeddings.values()))
    if not query_ids.issubset(common_ids):
        raise ContractError("incomplete common query coverage")

    contract_hash = sha256_file(config_path)
    cache = PcmIdentityCache(root / config["paths"]["pcm_identity_cache"], contract_hash)
    identities: dict[int, PcmIdentity] = {}

    def identity(track_id: int) -> PcmIdentity:
        if track_id not in identities:
            row = manifest.loc[track_id]
            identities[track_id] = cache.get_or_compute(
                track_id,
                str(row["audio_sha256"]),
                root / config["paths"]["audio_root"] / str(row["relative_audio_path"]),
            )
        return identities[track_id]

    query_identity_sets = _identity_sets([identity(track_id) for track_id in sorted(query_ids)])
    depth50: dict[int, dict[str, list[int]]] = {}
    all_scores: dict[int, dict[str, dict[int, float]]] = {}
    all_ranks: dict[int, dict[str, dict[int, int]]] = {}
    for query_id in sorted(query_ids):
        depth50[query_id], all_scores[query_id], all_ranks[query_id] = {}, {}, {}
        for encoder_id, vectors in embeddings.items():
            ordered, scores, ranks = _score_order(vectors, query_id, query_ids)
            selected: list[int] = []
            for candidate_id in ordered:
                candidate_identity = identity(candidate_id)
                if _matches_identity_sets(candidate_identity, query_identity_sets):
                    continue
                selected.append(candidate_id)
                if len(selected) == int(config["candidate_policy"]["single_expansion_depth"]):
                    break
            depth50[query_id][encoder_id] = selected
            all_scores[query_id][encoder_id] = scores
            all_ranks[query_id][encoder_id] = ranks

    selected_trials: list[dict[str, Any]] = []
    slots: list[dict[str, Any]] = []
    selected_pair_counts: dict[str, int] = {_pair_name(pair): 0 for pair in config["trials"]["source_pairs"]}
    used_pairs: dict[int, set[tuple[int, int]]] = {query_id: set() for query_id in query_ids}
    target = int(config["trials"]["strict_disagreements_per_pair_query"])
    initial_depth = int(config["candidate_policy"]["initial_depth"])
    expanded_depth = int(config["candidate_policy"]["single_expansion_depth"])

    for query_id in sorted(query_ids):
        for pair in config["trials"]["source_pairs"]:
            encoder_x, encoder_y = pair
            source_pair = _pair_name(pair)
            initial = _eligible_disagreements(
                query_id, encoder_x, encoder_y,
                depth50[query_id][encoder_x][:initial_depth],
                depth50[query_id][encoder_y][:initial_depth],
                all_scores[query_id], all_ranks[query_id], identities,
            )
            expanded = len(initial) < target
            eligible = initial if not expanded else _eligible_disagreements(
                query_id, encoder_x, encoder_y,
                depth50[query_id][encoder_x][:expanded_depth],
                depth50[query_id][encoder_y][:expanded_depth],
                all_scores[query_id], all_ranks[query_id], identities,
            )
            chosen = []
            for candidate in eligible:
                unordered = tuple(sorted((candidate["preferred_x"], candidate["preferred_y"])))
                if unordered in used_pairs[query_id]:
                    continue
                used_pairs[query_id].add(unordered)
                chosen.append(candidate)
                if len(chosen) == target:
                    break
            slots.append({
                "query_id": query_id,
                "split": split_by_query[query_id],
                "source_pair": source_pair,
                "requested": target,
                "available_initial": len(initial),
                "available_final": len(eligible),
                "selected": len(chosen),
                "retrieval_depth": expanded_depth if expanded else initial_depth,
                "missing": target - len(chosen),
            })
            for slot_index, candidate in enumerate(chosen, start=1):
                first, second = candidate["preferred_x"], candidate["preferred_y"]
                canonical = f"{query_id}|{source_pair}|{min(first, second)}|{max(first, second)}"
                keep_xy = _orientation(config["seed"], canonical)
                candidate_a, candidate_b = (first, second) if keep_xy else (second, first)
                trial_id = _opaque_id(config["seed"], canonical)
                selected_trials.append({
                    "trial_id": trial_id,
                    "query_id": query_id,
                    "split": split_by_query[query_id],
                    "source_pair": source_pair,
                    "encoder_x": encoder_x,
                    "encoder_y": encoder_y,
                    "preferred_x": first,
                    "preferred_y": second,
                    "candidate_a": candidate_a,
                    "candidate_b": candidate_b,
                    "a_is_x_preferred": keep_xy,
                    "slot_index": slot_index,
                    "retrieval_depth": expanded_depth if expanded else initial_depth,
                    "ranking": {key: value for key, value in candidate.items() if key != "sort_key"},
                })
                selected_pair_counts[source_pair] += 1

    counts = list(selected_pair_counts.values())
    ratio = min(counts) / max(counts) if counts and max(counts) else 0.0
    balance_passed = ratio >= float(config["trials"]["source_balance_min_ratio"])
    balance = {
        "experiment_id": config["experiment_id"],
        "config_sha256": contract_hash,
        "query_split_manifest_sha256": sha256_file(report_dir / "query_split_manifest.json"),
        "requested_total": len(query_ids) * len(config["trials"]["source_pairs"]) * target,
        "selected_total": len(selected_trials),
        "selected_pair_counts": selected_pair_counts,
        "min_to_max_ratio": ratio,
        "required_min_to_max_ratio": config["trials"]["source_balance_min_ratio"],
        "gate_passed": balance_passed,
        "slots": slots,
    }
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "trial_balance.json").write_text(json.dumps(balance, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not balance_passed:
        raise BalanceGateError(f"source balance gate failed: {selected_pair_counts}, ratio={ratio:.3f}")

    key_trials: dict[str, Any] = {}
    human_rows = []
    for trial in selected_trials:
        qid, aid, bid = trial["query_id"], trial["candidate_a"], trial["candidate_b"]
        same_artist = str(manifest.at[qid, "artist"]).casefold().strip() in {
            str(manifest.at[aid, "artist"]).casefold().strip(), str(manifest.at[bid, "artist"]).casefold().strip()
        }
        key_trials[trial["trial_id"]] = {
            **trial,
            "same_artist_candidate_flag": same_artist,
            "query_identity": asdict(identity(qid)),
            "candidate_a_identity": asdict(identity(aid)),
            "candidate_b_identity": asdict(identity(bid)),
            "scores": {
                encoder: {
                    "query_a": all_scores[qid][encoder][aid],
                    "query_b": all_scores[qid][encoder][bid],
                    "delta_a_minus_b": all_scores[qid][encoder][aid] - all_scores[qid][encoder][bid],
                    "rank_a": all_ranks[qid][encoder][aid],
                    "rank_b": all_ranks[qid][encoder][bid],
                }
                for encoder in config["inputs"]["embeddings"]
            },
        }
        human_rows.append({
            "trial_id": trial["trial_id"],
            "question": config["ratings"]["question"],
            "choice": "",
            "note": "",
            "rated_by": "",
            "choice_log": "",
        })

    keys = {
        "experiment_id": config["experiment_id"],
        "config_sha256": contract_hash,
        "query_split_manifest_sha256": sha256_file(report_dir / "query_split_manifest.json"),
        "trial_balance_sha256": sha256_file(report_dir / "trial_balance.json"),
        "trials": key_trials,
    }
    (report_dir / "trial_keys.json").write_text(json.dumps(keys, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    columns = ["trial_id", "question", "choice", "note", "rated_by", "choice_log"]
    with (report_dir / "holistic_trials.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(human_rows)
    identity_manifest = {
        "experiment_id": config["experiment_id"],
        "config_sha256": contract_hash,
        "float_format": "little-endian float32",
        "sample_rate": 24000,
        # Every lazily evaluated identity is frozen because it participated in
        # retrieval filtering, even when that track was not selected.
        "tracks": [asdict(identities[track_id]) for track_id in sorted(identities)],
    }
    (report_dir / "pcm_identity_manifest.json").write_text(
        json.dumps(identity_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return balance
