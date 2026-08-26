"""Frozen contract and query splitting for the Stage 2B fusion benchmark."""

from __future__ import annotations

import hashlib
import itertools
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

SPLITS = ("TRAIN", "VALIDATION", "TEST")
ENCODERS = ("laion_clap", "mert_5120", "muq_mulan_large")
REPRESENTATION_SETS = (
    ("laion_clap",),
    ("mert_5120",),
    ("muq_mulan_large",),
    ("laion_clap", "mert_5120"),
    ("laion_clap", "muq_mulan_large"),
    ("mert_5120", "muq_mulan_large"),
    ENCODERS,
)


class ContractError(RuntimeError):
    """The frozen Stage 2B contract or one of its inputs is invalid."""


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize_artist(value: object) -> str:
    """NFKC + casefold + collapsed Unicode whitespace artist identity."""
    text = unicodedata.normalize("NFKC", str(value)).casefold()
    return re.sub(r"\s+", " ", text, flags=re.UNICODE).strip()


def load_contract(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    with config_path.open(encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    validate_contract_shape(config)
    return config


def validate_contract_shape(config: dict[str, Any]) -> None:
    if config.get("experiment_id") != "holistic_stage2b_fusion_benchmark":
        raise ContractError("unexpected experiment_id")
    if not isinstance(config.get("seed"), int):
        raise ContractError("seed must be an integer")
    if tuple(config["provenance"]["encoders"]) != ENCODERS:
        raise ContractError("encoder order/identity changed")
    if config["provenance"]["excerpt_strategy"] != "center5_v1":
        raise ContractError("Stage 2B requires center5_v1")
    if config["provenance"]["source_sample_rate"] != 24000:
        raise ContractError("Stage 2B requires 24 kHz canonical source")
    if tuple(tuple(x) for x in config["selection"]["permitted_representation_sets"]) != REPRESENTATION_SETS:
        raise ContractError("the seven representation sets are frozen")
    model = config["selection"]["fusion_model"]
    expected = {"penalty": "l2", "solver": "lbfgs", "fit_intercept": False}
    if any(model.get(k) != v for k, v in expected.items()):
        raise ContractError("fusion model must be L2 lbfgs with no intercept")
    if model.get("C_grid") != [0.01, 0.1, 1, 10, 100]:
        raise ContractError("C grid changed")
    if config["split"]["counts"] != {"TRAIN": 16, "VALIDATION": 8, "TEST": 16}:
        raise ContractError("split counts changed")
    if config["split"]["per_genre"] != {"TRAIN": 2, "VALIDATION": 1, "TEST": 2}:
        raise ContractError("per-genre split changed")
    if config["trials"]["source_balance_min_ratio"] != 0.90:
        raise ContractError("source balance gate changed")
    if config["ratings"]["choices"] != ["A", "B", "Tie", "Neither"]:
        raise ContractError("rating choices changed")


def validate_input_hashes(config: dict[str, Any], root: str | Path) -> dict[str, str]:
    root = Path(root)
    checked: dict[str, str] = {}
    entries = [
        config["inputs"]["manifest"],
        config["inputs"]["frozen_queries"],
        config["inputs"]["frozen_query_manifest"],
        *config["inputs"]["embeddings"].values(),
        *config["inputs"]["historical_reports"].values(),
    ]
    for entry in entries:
        path = root / entry["path"]
        actual = sha256_file(path)
        if actual != entry["sha256"]:
            raise ContractError(f"SHA-256 mismatch for {entry['path']}: {actual}")
        checked[entry["path"]] = actual
    checkpoint = config["provenance"]["encoders"]["laion_clap"]
    checkpoint_path = root / checkpoint["checkpoint"]
    actual = sha256_file(checkpoint_path)
    if actual != checkpoint["checkpoint_sha256"]:
        raise ContractError(f"SHA-256 mismatch for {checkpoint['checkpoint']}: {actual}")
    checked[checkpoint["checkpoint"]] = actual
    for filename, expected in config["provenance"]["implementation"].items():
        path = root / "src" / "audio_similarity" / filename
        actual = sha256_file(path)
        if actual != expected:
            raise ContractError(f"SHA-256 mismatch for {path.relative_to(root)}: {actual}")
        checked[str(path.relative_to(root))] = actual
    return checked


def _group_order(seed: int, genre: str, artist: str) -> str:
    return hashlib.sha256(f"{seed}|{genre}|{artist}".encode()).hexdigest()


def _choose_groups(groups: list[tuple[str, list[dict]]], target: int, seed: int, genre: str) -> set[str]:
    eligible: list[tuple[tuple[str, ...], tuple[str, ...]]] = []
    for mask in itertools.product((False, True), repeat=len(groups)):
        chosen = [groups[i] for i, yes in enumerate(mask) if yes]
        if sum(len(rows) for _, rows in chosen) != target:
            continue
        artists = tuple(sorted(artist for artist, _ in chosen))
        key = tuple(sorted(_group_order(seed, genre, artist) for artist in artists))
        eligible.append((key, artists))
    if not eligible:
        raise ContractError(f"cannot allocate {target} grouped queries for genre {genre}")
    return set(min(eligible)[1])


def generate_query_split(query_csv: str | Path, seed: int) -> dict[str, Any]:
    frame = pd.read_csv(query_csv)
    required = {"query_id", "top_genre", "artist"}
    if not required.issubset(frame.columns):
        raise ContractError(f"query CSV missing {sorted(required - set(frame.columns))}")
    if frame["query_id"].duplicated().any():
        raise ContractError("duplicate query ID")
    rows = frame.to_dict("records")
    for row in rows:
        row["query_id"] = int(row["query_id"])
        row["artist_normalized"] = normalize_artist(row["artist"])

    artist_genres: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        artist_genres[row["artist_normalized"]].add(str(row["top_genre"]))
    cross_genre = {a: sorted(g) for a, g in artist_genres.items() if len(g) > 1}
    if cross_genre:
        raise ContractError(f"artist groups span genres; group-first global solver required: {cross_genre}")

    assignment: dict[int, str] = {}
    for genre in sorted({str(row["top_genre"]) for row in rows}):
        genre_rows = [row for row in rows if str(row["top_genre"]) == genre]
        grouped_map: dict[str, list[dict]] = defaultdict(list)
        for row in genre_rows:
            grouped_map[row["artist_normalized"]].append(row)
        groups = sorted(grouped_map.items())
        validation = _choose_groups(groups, 1, seed, genre)
        remaining = [(artist, values) for artist, values in groups if artist not in validation]
        train = _choose_groups(remaining, 2, seed, genre)
        for artist, values in groups:
            split = "VALIDATION" if artist in validation else "TRAIN" if artist in train else "TEST"
            for row in values:
                assignment[row["query_id"]] = split

    items = []
    for row in sorted(rows, key=lambda value: value["query_id"]):
        items.append({
            "query_id": row["query_id"],
            "top_genre": str(row["top_genre"]),
            "artist": str(row["artist"]),
            "artist_normalized": row["artist_normalized"],
            "split": assignment[row["query_id"]],
        })
    validate_split(items)
    return {
        "schema_version": 1,
        "algorithm": "genre_artist_group_validation_then_train_seeded_sha256_v1",
        "seed": seed,
        "query_source_sha256": sha256_file(query_csv),
        "counts": dict(Counter(item["split"] for item in items)),
        "queries": items,
        "deviations": [],
    }


def validate_split(items: list[dict[str, Any]]) -> None:
    ids = [int(item["query_id"]) for item in items]
    if len(ids) != 40 or len(set(ids)) != 40:
        raise ContractError("split must contain 40 unique queries")
    artist_splits: dict[str, set[str]] = defaultdict(set)
    genre_split = Counter()
    for item in items:
        artist_splits[item["artist_normalized"]].add(item["split"])
        genre_split[(item["top_genre"], item["split"])] += 1
    if any(len(splits) != 1 for splits in artist_splits.values()):
        raise ContractError("artist group crosses query splits")
    counts = Counter(item["split"] for item in items)
    if counts != Counter({"TRAIN": 16, "VALIDATION": 8, "TEST": 16}):
        raise ContractError(f"incorrect split counts: {dict(counts)}")
    for genre in {item["top_genre"] for item in items}:
        actual = {split: genre_split[(genre, split)] for split in SPLITS}
        if actual != {"TRAIN": 2, "VALIDATION": 1, "TEST": 2}:
            raise ContractError(f"genre imbalance for {genre}: {actual}")


def write_split_manifest(config_path: str | Path, root: str | Path, output: str | Path) -> dict[str, Any]:
    root = Path(root)
    config_path = Path(config_path)
    config = load_contract(config_path)
    checked = validate_input_hashes(config, root)
    source = root / config["inputs"]["frozen_queries"]["path"]
    manifest = generate_query_split(source, config["seed"])
    manifest["experiment_id"] = config["experiment_id"]
    manifest["config_sha256"] = sha256_file(config_path)
    manifest["validated_input_hashes"] = checked
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    output.write_text(payload, encoding="utf-8")
    return manifest
