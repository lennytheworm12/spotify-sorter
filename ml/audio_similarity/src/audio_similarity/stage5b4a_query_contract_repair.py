"""Bounded supplement repairing the Representative V3 YouTube query contract."""
from __future__ import annotations

import csv
import json
import time
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .stage5b1a2_config import YtDlpProviderConfig
from .stage5b1a2_ytdlp import (
    YtDlpDiscoveryAdapter,
    YtDlpPythonBackend,
    YtDlpSearchError,
)
from .stage5b1a_config import QueryConfig
from .stage5b1a_models import SpotifyTrack, Stage5B1AValidationError, file_sha256
from .stage5b1b_artifacts import atomic_json


SUPPLEMENT_ID = "QUERY_CONTRACT_REPAIR_SUPPLEMENT"
QUERY_CONTRACT_ID = "NATURAL_TITLE_FIRST3_ARTISTS_V1"
V3_BENCHMARK_ID = "STAGE5B4_REPRESENTATIVE_V3"
OUTPUT_DIRECTORY = "reports/stage5b4a_query_contract_repair"
REPAIR_CASE_COUNT = 2
SAFE_LABELS = frozenset({"IDEAL", "ACCEPTABLE"})
REVIEW_LABELS = frozenset({"", "IDEAL", "ACCEPTABLE", "WRONG", "UNCERTAIN"})
REVIEW_COLUMNS = (
    "review_schema_version",
    "benchmark_id",
    "spotify_track_id",
    "expected_title",
    "expected_artists",
    "expected_duration_seconds",
    "search_query",
    "youtube_rank",
    "candidate_video_id",
    "candidate_url",
    "candidate_title",
    "candidate_uploader",
    "candidate_channel",
    "candidate_duration_seconds",
    "candidate_view_count",
    "candidate_description",
    "provider_warnings",
    "provider_error",
    "candidate_review_label",
    "candidate_note",
    "track_note",
)
_DOUBLE_QUOTES = str.maketrans(
    {
        "\u201c": '"',
        "\u201d": '"',
        "\u201e": '"',
        "\u201f": '"',
        "\uff02": '"',
        "\u2018": "'",
        "\u2019": "'",
        "\u201a": "'",
        "\u201b": "'",
    }
)


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Stage5B1AValidationError(f"expected JSON object: {path}")
    return value


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sanitize_query_text(value: str) -> str:
    """Apply only transport-safe Unicode, quote, control, and whitespace cleanup."""

    if not isinstance(value, str):
        raise Stage5B1AValidationError("query component must be text")
    normalized = unicodedata.normalize("NFC", value).translate(_DOUBLE_QUOTES)
    cleaned = "".join(
        " " if unicodedata.category(character).startswith("C") else character
        for character in normalized
        if character != '"'
    )
    return " ".join(cleaned.split())


def _artist_identity(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def first_distinct_artists(
    artists: tuple[str, ...], *, limit: int = 3
) -> tuple[str, ...]:
    """Return the first mechanically distinct credited artists in Spotify order."""

    if limit < 1:
        raise Stage5B1AValidationError("artist limit must be positive")
    selected: list[str] = []
    identities: set[str] = set()
    for raw_artist in artists:
        artist = sanitize_query_text(raw_artist)
        identity = _artist_identity(artist)
        if not artist or not identity or identity in identities:
            continue
        identities.add(identity)
        selected.append(artist)
        if len(selected) == limit:
            break
    if not selected:
        raise Stage5B1AValidationError("query requires at least one searchable credited artist")
    return tuple(selected)


def natural_title_first3_artists_query(track: SpotifyTrack) -> str:
    """Build raw sanitized Spotify title plus up to three credited artists."""

    title = sanitize_query_text(track.title)
    if not title:
        raise Stage5B1AValidationError("query requires a searchable Spotify title")
    query = " ".join((title, *first_distinct_artists(track.artists)))
    if not query.strip():
        raise Stage5B1AValidationError("search query must be non-empty")
    return query


def _track(row: dict[str, Any]) -> SpotifyTrack:
    return SpotifyTrack.from_dict({
        "stable_track_id": row["benchmark_id"],
        "spotify_track_id": row["spotify_track_id"],
        "title": row["title"],
        "artists": row["artists"],
        "album": row.get("album"),
        "duration_ms": row.get("duration_ms"),
        "release_year": row.get("release_year"),
        "isrc": row.get("isrc"),
    })


def _v3_paths(project_root: Path) -> dict[str, Path]:
    directory = project_root / "reports/stage5b4_representative_v3"
    return {
        "benchmark_manifest": directory / "benchmark_manifest.json",
        "benchmark_config": directory / "benchmark_config.json",
        "youtube_top3_discovery": directory / "youtube_top3_discovery.json",
        "automated_selector_decisions": directory / "automated_selector_decisions.json",
        "automated_selector_metrics": directory / "automated_selector_metrics.json",
        "human_review": directory / "human_review.csv",
        "human_review_queue": directory / "human_review_queue.json",
    }


def _frozen_input_identity(project_root: Path) -> dict[str, dict[str, Any]]:
    paths = _v3_paths(project_root)
    if not all(path.is_file() for path in paths.values()):
        raise Stage5B1AValidationError("frozen Representative V3 evidence is incomplete")
    return {
        name: {
            "path": str(path.relative_to(project_root)),
            "sha256": file_sha256(path),
            "size_bytes": path.stat().st_size,
        }
        for name, path in paths.items()
    }


def build_offline_replay(project_root: str | Path) -> tuple[dict[str, Any], dict[str, Any]]:
    project_root = Path(project_root).resolve()
    paths = _v3_paths(project_root)
    manifest = _json(paths["benchmark_manifest"])
    discovery = _json(paths["youtube_top3_discovery"])
    tracks = manifest.get("tracks")
    original_rows = discovery.get("tracks")
    if (
        manifest.get("benchmark_id") != V3_BENCHMARK_ID
        or manifest.get("sampled_track_count") != 100
        or not isinstance(tracks, list)
        or len(tracks) != 100
        or discovery.get("benchmark_id") != V3_BENCHMARK_ID
        or not isinstance(original_rows, list)
        or len(original_rows) != 100
    ):
        raise Stage5B1AValidationError("unexpected frozen Representative V3 inputs")
    original_by_id = {row["benchmark_id"]: row for row in original_rows}
    replay_rows = []
    for row in tracks:
        track = _track(row)
        included_artists = first_distinct_artists(track.artists)
        query = natural_title_first3_artists_query(track)
        replay_rows.append({
            "benchmark_id": track.stable_track_id,
            "spotify_track_id": track.spotify_track_id,
            "raw_spotify_title": track.title,
            "sanitized_spotify_title": sanitize_query_text(track.title),
            "credited_artists": list(track.artists),
            "included_artists": list(included_artists),
            "artist_count_included": len(included_artists),
            "original_v3_query": original_by_id[track.stable_track_id]["query"],
            "repaired_query": query,
        })
    punctuation_titles = [
        row for row in replay_rows
        if any(character in row["raw_spotify_title"] for character in "\"':()[]-&")
    ]
    replay = {
        "schema_version": "stage5b4a-v3-query-replay-v1",
        "supplement_id": SUPPLEMENT_ID,
        "query_contract_id": QUERY_CONTRACT_ID,
        "source_benchmark_id": V3_BENCHMARK_ID,
        "summary": {
            "tracks_total": len(replay_rows),
            "non_empty_query_count": sum(bool(row["repaired_query"]) for row in replay_rows),
            "query_construction_failure_count": 0,
            "maximum_artist_count": max(row["artist_count_included"] for row in replay_rows),
            "tracks_with_harmless_punctuation": len(punctuation_titles),
            "punctuation_rejection_count": 0,
            "live_searches_run": 0,
        },
        "tracks": replay_rows,
    }
    contract = {
        "schema_version": "stage5b4a-repaired-query-contract-v1",
        "status": "QUERY_CONTRACT_REPAIR_OFFLINE_VERIFIED",
        "supplement_id": SUPPLEMENT_ID,
        "query_contract_id": QUERY_CONTRACT_ID,
        "template": "{sanitized_raw_spotify_title} {artist_1} {artist_2} {artist_3}",
        "artist_policy": {
            "source": "Spotify credited artists",
            "order": "credited order",
            "maximum": 3,
            "deduplication": "Unicode NFKC + casefold + collapsed whitespace identity",
            "inferred_artists": False,
        },
        "title_policy": {
            "source": "raw Spotify display title",
            "semantic_rewriting": False,
            "normalization": (
                "Unicode NFC; smart quote normalization; double-quote removal; "
                "control-character and whitespace normalization"
            ),
        },
        "query_policy": {
            "quoted_fields": False,
            "forced_official_token": False,
            "boolean_syntax": False,
            "song_specific_templates": False,
            "query_variants_per_track": 1,
        },
        "offline_verification": replay["summary"],
        "frozen_v3_inputs": _frozen_input_identity(project_root),
        "historical_v3_artifacts_overwritten": False,
    }
    return contract, replay


def write_offline_artifacts(project_root: str | Path, output_dir: str | Path) -> dict[str, Any]:
    output_dir = Path(output_dir).resolve()
    contract, replay = build_offline_replay(project_root)
    atomic_json(output_dir / "repaired_query_contract.json", contract)
    atomic_json(output_dir / "v3_query_replay.json", replay)
    return replay["summary"]


def _provider() -> YtDlpProviderConfig:
    return YtDlpProviderConfig(
        candidate_limit=3,
        search_prefix="ytsearch3:",
        extract_flat="in_playlist",
        skip_download=True,
        simulate=True,
        ignore_user_config=True,
        cache_enabled=False,
        socket_timeout_seconds=30,
        max_attempts=2,
        retry_backoff_seconds=2.0,
        sleep_between_tracks_seconds=3.0,
    )


def _inert_query_config() -> QueryConfig:
    return QueryConfig(
        variant_id="stage5b4a-explicit-query-only",
        template="{normalized_title} {primary_artist}",
        normalize_featured_artist_noise=False,
    )


def _repair_rows(project_root: Path) -> list[dict[str, Any]]:
    manifest = _json(_v3_paths(project_root)["benchmark_manifest"])
    discovery = _json(_v3_paths(project_root)["youtube_top3_discovery"])
    failed_ids = {
        row["benchmark_id"]
        for row in discovery["tracks"]
        if row["outcome"].get("error") is not None
        or not row["outcome"].get("candidates")
    }
    if len(failed_ids) != REPAIR_CASE_COUNT:
        raise Stage5B1AValidationError(
            f"repair supplement requires exactly {REPAIR_CASE_COUNT} observed V3 failures"
        )
    return [row for row in manifest["tracks"] if row["benchmark_id"] in failed_ids]


def run_repaired_discovery(
    project_root: str | Path,
    output_dir: str | Path,
    adapter: YtDlpDiscoveryAdapter | None = None,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    project_root = Path(project_root).resolve()
    output_path = Path(output_dir).resolve() / "repaired_discovery.json"
    if output_path.exists():
        raise Stage5B1AValidationError("repaired discovery is already recorded")
    provider = _provider()
    adapter = adapter or YtDlpDiscoveryAdapter(
        provider,
        _inert_query_config(),
        YtDlpPythonBackend(provider),
    )
    started_at = _now()
    rows = []
    repair_rows = _repair_rows(project_root)
    for index, manifest_row in enumerate(repair_rows):
        track = _track(manifest_row)
        query = natural_title_first3_artists_query(track)
        requested_at = _now()
        try:
            outcome = adapter.discover_query(track, query, limit=3).to_dict()
        except YtDlpSearchError as exc:
            outcome = {
                "track": track.to_dict(),
                "query": query,
                "request": {
                    "search_expression": provider.search_expression(query),
                    "options": provider.metadata_only_options(),
                    "download": False,
                },
                "provider": {"name": "yt_dlp", "attempts": exc.attempts},
                "normalized_results": [],
                "candidates": [],
                "candidate_video_ids": [],
                "warnings": list(exc.warnings),
                "error": exc.to_dict(),
            }
        candidates = outcome.get("candidates", [])
        if len(candidates) > 3 or [row.get("rank") for row in candidates] != list(
            range(1, len(candidates) + 1)
        ):
            raise Stage5B1AValidationError("repaired discovery did not preserve native top-three order")
        rows.append({
            "benchmark_id": track.stable_track_id,
            "requested_at_utc": requested_at,
            "completed_at_utc": _now(),
            "exact_generated_query": query,
            "outcome": outcome,
        })
        if index + 1 < len(repair_rows):
            sleep(provider.sleep_between_tracks_seconds)
    result = {
        "schema_version": "stage5b4a-repaired-discovery-v1",
        "status": "QUERY_CONTRACT_REPAIR_DISCOVERY_COMPLETE",
        "supplement_id": SUPPLEMENT_ID,
        "query_contract_id": QUERY_CONTRACT_ID,
        "source_benchmark_id": V3_BENCHMARK_ID,
        "started_at_utc": started_at,
        "completed_at_utc": _now(),
        "provider": {
            "name": "yt_dlp",
            "search_mode": "ytsearch3",
            "candidate_limit": 3,
            "metadata_only": True,
            "native_rank_preserved": True,
            "sequential": True,
            "sleep_between_tracks_seconds": provider.sleep_between_tracks_seconds,
            "versions": sorted({
                str(row["outcome"].get("provider", {}).get("version"))
                for row in rows
                if row["outcome"].get("provider", {}).get("version")
            }),
        },
        "summary": {
            "authorized_case_count": REPAIR_CASE_COUNT,
            "searches_completed": len(rows),
            "valid_search_count": sum(row["outcome"].get("error") is None for row in rows),
            "search_failure_count": sum(row["outcome"].get("error") is not None for row in rows),
            "tracks_with_candidates": sum(
                bool(row["outcome"].get("candidates")) for row in rows
            ),
            "zero_candidate_tracks": sum(
                not row["outcome"].get("candidates") for row in rows
            ),
            "candidate_count": sum(len(row["outcome"].get("candidates", [])) for row in rows),
            "warning_count": sum(len(row["outcome"].get("warnings", [])) for row in rows),
        },
        "scope_guards": {
            "full_v3_searches_rerun": False,
            "selector_invocations": 0,
            "proof_heavy_resolver_invocations": 0,
            "sol_runs": 0,
            "clap_calls": 0,
            "muq_calls": 0,
            "audio_downloads": 0,
            "video_downloads": 0,
        },
        "tracks": rows,
    }
    atomic_json(output_path, result)
    return result


def write_human_review(output_dir: str | Path) -> Path:
    output_dir = Path(output_dir).resolve()
    discovery = _json(output_dir / "repaired_discovery.json")
    review_path = output_dir / "human_review.csv"
    existing: dict[tuple[str, str], dict[str, str]] = {}
    if review_path.exists():
        with review_path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                existing[(row["benchmark_id"], row["candidate_video_id"])] = row
    rows = []
    for case in discovery["tracks"]:
        outcome = case["outcome"]
        track = outcome["track"]
        warnings = json.dumps(outcome.get("warnings", []), ensure_ascii=False)
        error = json.dumps(outcome.get("error"), ensure_ascii=False) if outcome.get("error") else ""
        candidates = outcome.get("candidates", [])
        candidate_rows = candidates or [None]
        for candidate in candidate_rows:
            candidate_id = candidate["youtube_video_id"] if candidate else ""
            old = existing.get((case["benchmark_id"], candidate_id), {})
            rows.append({
                "review_schema_version": "stage5b4a-human-review-v1",
                "benchmark_id": case["benchmark_id"],
                "spotify_track_id": track.get("spotify_track_id") or "",
                "expected_title": track["title"],
                "expected_artists": " | ".join(track["artists"]),
                "expected_duration_seconds": track["duration_ms"] / 1000,
                "search_query": case["exact_generated_query"],
                "youtube_rank": candidate["rank"] if candidate else "",
                "candidate_video_id": candidate_id,
                "candidate_url": (
                    candidate.get("canonical_url") or candidate.get("url") or ""
                ) if candidate else "",
                "candidate_title": (candidate.get("title") or "") if candidate else "",
                "candidate_uploader": (candidate.get("uploader") or "") if candidate else "",
                "candidate_channel": (candidate.get("channel") or "") if candidate else "",
                "candidate_duration_seconds": (candidate.get("duration_seconds") or "") if candidate else "",
                "candidate_view_count": (
                    candidate.get("view_count")
                    if candidate.get("view_count") is not None
                    else ""
                ) if candidate else "",
                "candidate_description": (candidate.get("description") or "") if candidate else "",
                "provider_warnings": warnings,
                "provider_error": error,
                "candidate_review_label": old.get("candidate_review_label", ""),
                "candidate_note": old.get("candidate_note", ""),
                "track_note": old.get(
                    "track_note",
                    "NO_CANDIDATES_RETURNED" if not candidate else "",
                ),
            })
    review_path.parent.mkdir(parents=True, exist_ok=True)
    with review_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return review_path


def validate_human_review(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        label = row.get("candidate_review_label", "").strip().upper()
        if label not in REVIEW_LABELS:
            raise Stage5B1AValidationError(f"invalid review label: {label}")
        row["candidate_review_label"] = label
        grouped[row["benchmark_id"]].append(row)
    if len(grouped) != REPAIR_CASE_COUNT:
        raise Stage5B1AValidationError("human review must cover both repaired cases")
    cases = []
    for benchmark_id, case_rows in grouped.items():
        unavailable_rows = [row for row in case_rows if not row["candidate_video_id"]]
        if unavailable_rows:
            if len(case_rows) != 1 or unavailable_rows[0]["candidate_review_label"]:
                raise Stage5B1AValidationError(
                    f"{benchmark_id} invalid no-candidate review row"
                )
            cases.append({
                "benchmark_id": benchmark_id,
                "query": unavailable_rows[0]["search_query"],
                "first_safe_rank": None,
                "safe_in_top3": False,
                "candidate_unavailable": True,
            })
            continue
        case_rows.sort(key=lambda row: int(row["youtube_rank"]))
        expected_rank = 1
        first_safe = None
        for row in case_rows:
            rank = int(row["youtube_rank"])
            label = row["candidate_review_label"]
            if first_safe is not None:
                if label:
                    raise Stage5B1AValidationError(
                        f"{benchmark_id} labels continue after first SAFE"
                    )
                continue
            if rank < expected_rank and not label:
                raise Stage5B1AValidationError(f"{benchmark_id} has a gap in sequential review")
            if rank == expected_rank:
                if not label:
                    raise Stage5B1AValidationError(f"{benchmark_id} rank {rank} requires a label")
                if label in SAFE_LABELS:
                    first_safe = rank
                    expected_rank = 4
                else:
                    expected_rank += 1
        if first_safe is None and expected_rank <= 3:
            raise Stage5B1AValidationError(f"{benchmark_id} sequential review is incomplete")
        cases.append({
            "benchmark_id": benchmark_id,
            "query": case_rows[0]["search_query"],
            "first_safe_rank": first_safe,
            "safe_in_top3": first_safe is not None,
            "candidate_unavailable": False,
        })
    safe_count = sum(case["safe_in_top3"] for case in cases)
    return {
        "case_count": len(cases),
        "safe_case_count": safe_count,
        "all_cases_safe": safe_count == REPAIR_CASE_COUNT,
        "cases": cases,
    }


def _phase_verdict(output_dir: Path, review: dict[str, Any]) -> str:
    replay = _json(output_dir / "v3_query_replay.json")
    discovery = _json(output_dir / "repaired_discovery.json")
    passed = (
        replay["summary"]["non_empty_query_count"] == 100
        and replay["summary"]["query_construction_failure_count"] == 0
        and discovery["summary"]["valid_search_count"] == REPAIR_CASE_COUNT
        and review["all_cases_safe"]
    )
    return "PASS" if passed else "FAIL"


def write_report(output_dir: str | Path) -> dict[str, Any]:
    output_dir = Path(output_dir).resolve()
    contract = _json(output_dir / "repaired_query_contract.json")
    replay = _json(output_dir / "v3_query_replay.json")
    discovery = _json(output_dir / "repaired_discovery.json")
    review = validate_human_review(output_dir / "human_review.csv")
    verdict = _phase_verdict(output_dir, review)
    case_by_id = {case["benchmark_id"]: case for case in review["cases"]}
    lines = [
        "# Stage 5B.4A — Natural Multi-Artist Query Contract Repair",
        "",
        (
            f"**Verdict: {verdict}.** Both observed V3 failures received valid "
            "metadata-only searches and a SAFE candidate in the top three."
            if verdict == "PASS"
            else f"**Verdict: {verdict}.** Both searches executed, but at least "
            "one repaired case still lacked a SAFE candidate in the top three."
        ),
        "",
        "## Decision",
        "",
        (
            f"Freeze `{QUERY_CONTRACT_ID}` as the candidate contract for the next "
            "genuinely held-out benchmark."
            if verdict == "PASS"
            else "Do not freeze the repaired contract. No additional query heuristic "
            "is introduced in this phase."
        ),
        (
            "Representative V3 remains unchanged and is not reinterpreted; this work "
            "is recorded only as `QUERY_CONTRACT_REPAIR_SUPPLEMENT`."
        ),
        "",
        "## Contract",
        "",
        (
            "The builder starts from the raw Spotify display title, performs only "
            "mechanical Unicode/quote/control/whitespace sanitation, then appends up "
            "to the first three distinct Spotify-credited artists in credited order. "
            "It adds no `official` token, exact-match quotes, Boolean syntax, semantic "
            "title stripping, inferred artists, or song-specific behavior."
        ),
        "",
        "## Offline V3 replay",
        "",
        (
            f"All {replay['summary']['tracks_total']} frozen V3 tracks produced "
            f"non-empty queries; failures: "
            f"{replay['summary']['query_construction_failure_count']}; maximum artists "
            f"included: {replay['summary']['maximum_artist_count']}; harmless-punctuation "
            f"rejections: {replay['summary']['punctuation_rejection_count']}. No YouTube "
            "request was made during replay."
        ),
        "",
        "## Bounded repair discovery and human review",
        "",
    ]
    for case in discovery["tracks"]:
        outcome = case["outcome"]
        reviewed = case_by_id[case["benchmark_id"]]
        candidate_result = (
            "yt-dlp returned zero candidates, so no human candidate label was possible; "
            "first SAFE rank: **none**. The provider supplied no error or warning that "
            "would explain the empty result."
            if reviewed["candidate_unavailable"]
            else f"first SAFE rank: **{reviewed['first_safe_rank']}**."
        )
        lines.extend([
            f"### {outcome['track']['title']} — {' / '.join(outcome['track']['artists'])}",
            "",
            f"Exact query: `{case['exact_generated_query']}`",
            "",
            f"Provider error: `{json.dumps(outcome.get('error'), ensure_ascii=False)}`; "
            f"warnings: `{json.dumps(outcome.get('warnings', []), ensure_ascii=False)}`; "
            f"{candidate_result}",
            "",
            "| Rank | Video ID | Title | Uploader/channel | Duration | Views |",
            "|---:|---|---|---|---:|---:|",
        ])
        for candidate in outcome.get("candidates", []):
            uploader = candidate.get("uploader") or ""
            channel = candidate.get("channel") or ""
            lines.append(
                f"| {candidate['rank']} | `{candidate['youtube_video_id']}` | "
                f"{candidate.get('title') or ''} | {uploader} / {channel} | "
                f"{candidate.get('duration_seconds')} | {candidate.get('view_count')} |"
            )
        lines.append("")
    lines.extend([
        "## Scope and history guards",
        "",
        "- Live YouTube searches: 2, sequential, metadata-only `ytsearch3`.",
        "- Full V3 discovery reruns: 0.",
        "- Stage 5B.3 selector changes or invocations: 0.",
        "- Audio/video downloads, proof-heavy resolver, Sol, CLAP, and MuQ runs: 0.",
        (
            "- Historical V3 artifacts overwritten: 0; their identities are pinned in "
            "`repaired_query_contract.json` and `artifact_manifest.json`."
        ),
        "",
        "## Reproduction",
        "",
        "```bash",
        "uv run python -m audio_similarity.cli.stage5b4a_query_contract_repair offline",
        "uv run python -m audio_similarity.cli.stage5b4a_query_contract_repair discover",
        "uv run python -m audio_similarity.cli.stage5b4a_query_contract_repair build-review",
        "# Apply sequential human labels to human_review.csv, then:",
        "uv run python -m audio_similarity.cli.stage5b4a_query_contract_repair finalize",
        "```",
        "",
    ])
    (output_dir / "query_contract_report.md").write_text("\n".join(lines), encoding="utf-8")
    return {"verdict": verdict, "review": review, "contract": contract["query_contract_id"]}


def write_artifact_manifest(project_root: str | Path, output_dir: str | Path) -> dict[str, Any]:
    project_root = Path(project_root).resolve()
    output_dir = Path(output_dir).resolve()
    artifacts = (
        "repaired_query_contract.json",
        "v3_query_replay.json",
        "repaired_discovery.json",
        "human_review.csv",
        "query_contract_report.md",
    )
    if not all((output_dir / name).is_file() for name in artifacts):
        raise Stage5B1AValidationError("Stage 5B.4A artifacts are incomplete")
    review = validate_human_review(output_dir / "human_review.csv")
    verdict = _phase_verdict(output_dir, review)
    manifest = {
        "schema_version": "stage5b4a-artifact-manifest-v1",
        "status": "STAGE5B4A_COMPLETE",
        "verdict": verdict,
        "supplement_id": SUPPLEMENT_ID,
        "query_contract_id": QUERY_CONTRACT_ID,
        "frozen_v3_inputs": _frozen_input_identity(project_root),
        "artifacts": {
            name: {
                "sha256": file_sha256(output_dir / name),
                "size_bytes": (output_dir / name).stat().st_size,
            }
            for name in artifacts
        },
        "implementation": {
            "path": "src/audio_similarity/stage5b4a_query_contract_repair.py",
            "sha256": file_sha256(
                project_root / "src/audio_similarity/stage5b4a_query_contract_repair.py"
            ),
        },
        "tests": {
            "path": "tests/test_stage5b4a_query_contract_repair.py",
            "sha256": file_sha256(
                project_root / "tests/test_stage5b4a_query_contract_repair.py"
            ),
        },
        "scope_guards": {
            "historical_v3_artifacts_overwritten": False,
            "live_searches": 2,
            "full_v3_searches_rerun": False,
            "selector_modified": False,
            "selector_invocations": 0,
            "proof_heavy_resolver_invocations": 0,
            "sol_runs": 0,
            "clap_calls": 0,
            "muq_calls": 0,
            "audio_downloads": 0,
            "video_downloads": 0,
        },
    }
    atomic_json(output_dir / "artifact_manifest.json", manifest)
    return manifest
