"""Artifact-only Arm D evaluation; no encoder or acquisition execution."""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

from .stage5b1a_models import file_sha256
from .stage5b1b_artifacts import atomic_json
from .stage5c2_analysis import canonical_pair_id
from .stage5e1_analysis import REVIEW_COLUMNS
from .stage5e1_review import LABELS

REPORT = Path("reports/stage5e2_arm_d_original100_v2")
PRIOR = Path("reports/stage5e1_four_arm_retrieval")
STATE = Path(".research_audio/stage5e2_original100_v2_review/human_similarity_review.csv")
SEED = "stage5e2-d-missing-pairs-v1"


def read(path):
    return json.loads(path.read_text())


def resolve_labels(evidence):
    """Repeated copies are provenance, not independent judgments."""
    grouped = defaultdict(list)
    for row in evidence:
        grouped[row["pair_id"]].append(row)
    labels, conflicts = {}, {}
    for pair, rows in sorted(grouped.items()):
        numeric = {r["label"] for r in rows if r["label"] in {"1", "2", "3", "4", "5"}}
        if len(numeric) == 1:
            labels[pair] = int(next(iter(numeric)))
        elif len(numeric) > 1:
            conflicts[pair] = sorted(numeric)
    return labels, conflicts


def audit_labels(root, tracks, exports=()):
    prior_queue = root / PRIOR / 'review_queue.json'
    prior_pairs = {p['pair_id']: p for p in read(prior_queue)['pairs']} if prior_queue.exists() else {}
    retired_queue = root / 'reports/stage5e2_arm_d_evaluation/review_queue.json'
    retired_pairs = {p['pair_id']: p for p in read(retired_queue)['pairs']} if retired_queue.exists() else {}
    paths = set()
    for directory in (root / "reports", root / ".research_audio"):
        paths.update(p for p in directory.rglob("*.csv")
                     if any(word in p.name.lower() for word in ("review", "rating", "judgment"))
                     and not p.is_relative_to(root / REPORT)
                     and not p.is_relative_to(root / STATE.parent))
    paths.update(Path(p) for p in exports if Path(p).is_file())
    audit, evidence = [], []
    for path in sorted(paths):
        name = str(path.relative_to(root)) if path.is_relative_to(root) else "external_export/" + path.name
        counts = Counter()
        source_hash = file_sha256(path)
        with path.open(newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))
        sources = {}
        selected = path.parent / "selected_sources.json"
        if not path.is_relative_to(root):
            selected = root / "reports/stage5c2_representative_100_amended_v2/selected_sources.json"
        if selected.exists():
            sources = {r["spotify_track_id"]: r.get("selected_youtube_video_id") for r in read(selected).get("tracks", [])}
        for row in rows:
            label = row.get("human_label", "").strip().upper()
            schema = row.get("review_schema_version")
            if schema not in {"stage5c2-human-similarity-review-v2", "stage5e1-human-similarity-review-v1"}:
                counts["incompatible_rating_contract"] += 1
                continue
            left = row.get("query_spotify_id", row.get("left_spotify_id"))
            right = row.get("neighbor_spotify_id", row.get("right_spotify_id"))
            if left not in tracks or right not in tracks or left == right:
                counts["outside_corpus"] += 1
                continue
            pair = canonical_pair_id(left, right)
            if row.get("pair_id") != pair:
                counts["invalid_pair_id"] += 1
                continue
            if schema.startswith("stage5c2"):
                compatible = all(tracks[t]["youtube_video_id"] == sources.get(t) for t in (left, right))
                basis = "same frozen YouTube sources; full-source bytes may differ from historical excerpts"
            else:
                known_state = path == root / '.research_audio/stage5e2_review/human_similarity_review.csv'
                frozen_pair = (retired_pairs if known_state else prior_pairs).get(pair)
                compatible = ((known_state or path == root / ".research_audio/stage5e1_review/human_similarity_review.csv")
                              and frozen_pair is not None
                              and all(side['source_sha256'] == tracks[side['spotify_track_id']]['source_sha256']
                                      and side['youtube_video_id'] == tracks[side['spotify_track_id']]['youtube_video_id']
                                      for side in (frozen_pair['left'], frozen_pair['right'])))
                basis = "same Stage5E1 frozen source SHA and review queue"
            if not compatible:
                counts["unverified_source_identity"] += 1
                continue
            if label not in LABELS:
                counts["blank_or_invalid_label"] += 1
                continue
            counts["compatible_label"] += 1
            evidence.append({"pair_id": pair, "label": label, "source": name,
                             "source_sha256": source_hash, "source_identity_basis": basis,
                             "note": row.get("human_note", ""), "timestamp": row.get("review_timestamp", "")})
        audit.append({"path": name, "sha256": source_hash, "rows": len(rows), "outcomes": dict(counts)})
    return audit, evidence


def missing_queue(tracks, pairs, labels):
    ordered = sorted(set(pairs) - labels.keys(), key=lambda p: (hashlib.sha256(f"{SEED}\0{p}".encode()).hexdigest(), p))
    fields = ("spotify_track_id", "title", "artists", "album", "retained_source_path", "source_sha256", "youtube_video_id")
    return {"schema_version": "stage5e1-blinded-review-queue-v1", "experiment_id": "STAGE5E2_ARM_D",
            "order_seed": SEED, "pairs": [
                {"review_index": i, "pair_id": pair,
                 "left": {k: tracks[pairs[pair][0]].get(k) for k in fields},
                 "right": {k: tracks[pairs[pair][1]].get(k) for k in fields}}
                for i, pair in enumerate(ordered, 1)]}


def quality(rows, labels):
    rated = [r for r in rows if r["pair_id"] in labels]
    values = [labels[r["pair_id"]] for r in rated]
    top1 = [labels[r["pair_id"]] for r in rated if r["rank"] == 1]
    groups = defaultdict(list)
    for r in rows:
        groups[r["query"]].append(r)
    complete = [mean(labels[r["pair_id"]] for r in group) for group in groups.values()
                if len(group) == 5 and all(r["pair_id"] in labels for r in group)]
    return {"directional_relationships": len(rows), "rated_relationships": len(rated),
            "coverage": len(rated) / len(rows) if rows else 0,
            "observed_mean_top1": mean(top1) if top1 else None,
            "observed_mean_rating_at5": mean(values) if values else None,
            "observed_fraction_at_least3": mean(v >= 3 for v in values) if values else None,
            "observed_fraction_at_least4": mean(v >= 4 for v in values) if values else None,
            "complete_top5_queries": len(complete), "complete_query_similarity_at5": mean(complete) if complete else None,
            "rating_by_rank": {str(rank): {"count": len(v := [labels[r['pair_id']] for r in rated if r['rank'] == rank]),
                                           "mean": mean(v) if v else None} for rank in range(1, 6)}}


def evaluate(neighbors, labels):
    pools, pairs = defaultdict(list), {}
    for query in neighbors["tracks"]:
        for key in ("D_CLAP", "D_COMBINED", "A_CLAP", "A_COMBINED"):
            for r in query["retrievals"][key][:5]:
                pair = canonical_pair_id(query["spotify_track_id"], r["spotify_track_id"])
                pools[key].append({"query": query["spotify_track_id"], "neighbor": r["spotify_track_id"],
                                   "pair_id": pair, "rank": r["rank"], "similarity": r["similarity"]})
                if key.startswith("D_"):
                    pairs[pair] = tuple(sorted((query["spotify_track_id"], r["spotify_track_id"])))
    paired = {}
    for mode in ("CLAP", "COMBINED"):
        by = {}
        for arm in ("D", "A"):
            groups = defaultdict(list)
            for row in pools[f"{arm}_{mode}"]:
                groups[row["query"]].append(row)
            by[arm] = {q: mean(labels[r["pair_id"]] for r in rs) for q, rs in groups.items()
                       if len(rs) == 5 and all(r["pair_id"] in labels for r in rs)}
        differences = [{"query": q, "D": by['D'][q], "A": by['A'][q], "delta": by['D'][q] - by['A'][q]}
                       for q in sorted(by['D'].keys() & by['A'].keys())]
        paired[mode] = {"fully_rated_queries": len(differences), "per_query": differences,
                        "wins": sum(r['delta'] > 0 for r in differences), "ties": sum(r['delta'] == 0 for r in differences),
                        "losses": sum(r['delta'] < 0 for r in differences),
                        "mean_delta": mean(r['delta'] for r in differences) if differences else None}
    failures = sorted([r | {"mode": mode, "human_rating": labels[r['pair_id']]}
                       for mode in ('D_CLAP', 'D_COMBINED') for r in pools[mode]
                       if labels.get(r['pair_id'], 6) <= 2], key=lambda r: (r['human_rating'], r['rank'], -r['similarity'], r['pair_id']))[:20]
    disagreements = []
    for mode in ('CLAP', 'COMBINED'):
        baseline = {(r['query'], r['neighbor']): r['rank'] for r in pools[f'A_{mode}']}
        for row in pools[f'D_{mode}']:
            a_rank = baseline.get((row['query'], row['neighbor']))
            if a_rank != row['rank']:
                disagreements.append(row | {'mode': mode, 'A_top5_rank': a_rank,
                                            'human_rating': labels.get(row['pair_id'])})
    disagreements.sort(key=lambda r: (r['A_top5_rank'] is not None, r['rank'], r['pair_id'], r['mode']))
    return pairs, {"quality": {k: quality(v, labels) for k, v in pools.items()}, "paired_D_vs_A": paired,
                   "strongest_observed_failures": failures,
                   "largest_top5_membership_disagreements": disagreements[:20]}


def run(root, exports=()):
    root = Path(root).resolve()
    prior = root / PRIOR
    inventory = read(prior / "artifact_manifest.json")
    for item in inventory['files']:
        if file_sha256(prior / item['path']) != item['sha256']:
            raise ValueError('Stage5E1 artifact integrity failure: ' + item['path'])
    manifest = read(prior / 'corpus_manifest.json')
    tracks = {r['spotify_track_id']: r for r in manifest['tracks']}
    if len(tracks) != 741 or manifest['track_count'] != 741:
        raise ValueError('expected frozen 741-track corpus')
    neighbors = read(prior / 'nearest_neighbors.json')
    if {r['spotify_track_id'] for r in neighbors['tracks']} != tracks.keys():
        raise ValueError('retrieval corpus mismatch')
    import numpy as np
    from .stage5e2_subset import subset_retrieval
    selected_path = root / 'reports/stage5c2_representative_100_amended_v2/selected_sources.json'
    with np.load(prior / 'similarity_matrices.npz', allow_pickle=False) as matrices:
        tracks, neighbors = subset_retrieval(tracks, read(selected_path), matrices)
    audit, evidence = audit_labels(root, tracks, exports)
    labels, conflicts = resolve_labels(evidence)
    pairs, metrics = evaluate(neighbors, labels)
    queue = missing_queue(tracks, pairs, labels)
    covered = len(pairs.keys() & labels.keys())
    metrics.update(total_D_pairs=len(pairs), covered_D_pairs=covered, covered_percent=100 * covered / len(pairs),
                   new_judgments=len(queue['pairs']), conflicts=conflicts,
                   verdict='ARM_D_HUMAN_EVIDENCE_INSUFFICIENT', production_activation=False,
                   limitation='Observed ratings are selected historical coverage, not an unbiased estimate of all 100 queries. UNSURE is nonnumeric. Paired results require complete Top-5 ratings for both arms. No winner is inferred from partial evidence.')
    report = root / REPORT
    if (report / 'review_queue.json').exists():
        if read(report / 'review_queue.json') != queue:
            raise ValueError('frozen Stage5E2 queue would change; use a versioned evaluation')
    report.mkdir(parents=True, exist_ok=True)
    for name, data in [('input_reference.json', {'prior_manifest_sha256': file_sha256(prior/'artifact_manifest.json'),
                       'corpus_sha256': file_sha256(prior/'corpus_manifest.json'), 'ordering_seed': SEED, 'scale': LABELS,
                       'inference_calls': 0, 'queue_scope': 'union of D CLAP and COMBINED Top5 missing numeric labels'}),
                       ('subset_reference.json', {'selected_sources_sha256':file_sha256(selected_path),
                        'query_count':100, 'candidate_count':100, 'spotify_ids':sorted(tracks),
                        'retired_report':'stage5e2_arm_d_evaluation', 'rank_policy':'restrict both axes before ranking'}),
                       ('nearest_neighbors.json', neighbors),
                       ('label_search_audit.json', audit), ('label_evidence.json', evidence),
                       ('reused_labels.json', labels), ('evaluation_metrics.json', metrics), ('review_queue.json', queue)]:
        atomic_json(report / name, data)
    state = root / STATE
    if not state.exists():
        state.parent.mkdir(parents=True, exist_ok=True)
        with state.open('x', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS)
            writer.writeheader()
            for pair in queue['pairs']:
                writer.writerow({'review_schema_version':'stage5e1-human-similarity-review-v1', 'pair_id':pair['pair_id'],
                                 'left_spotify_id':pair['left']['spotify_track_id'], 'right_spotify_id':pair['right']['spotify_track_id']})
    text = f"""# Stage 5E.2 Arm D evaluation

Verdict: `{metrics['verdict']}`. D remains an experimental challenger; no winner or activation is justified yet.

Scope correction: only the original amended frozen 100 tracks are queries AND candidates.
The 741-track Stage5E1 experiment and retired Stage5E2 queue remain preserved, but are not the active review target.
Frozen A/D similarities are restricted on both axes before recomputing native Top-5 ranks, with zero inference.
D CLAP + COMBINED contain {len(pairs)} unique pairs. Prior numeric ratings cover {covered} ({metrics['covered_percent']:.2f}%).
The blinded queue contains only the remaining {metrics['new_judgments']} pairs.

| Retrieval | Rated / total | Observed mean rating@5 | Fully rated queries |
| --- | ---: | ---: | ---: |
"""
    for key, q in metrics['quality'].items():
        text += f"| {key} | {q['rated_relationships']} / {q['directional_relationships']} | {q['observed_mean_rating_at5']} | {q['complete_top5_queries']} |\n"
    text += '\n' + metrics['limitation'] + '\n\n'
    for mode, p in metrics['paired_D_vs_A'].items():
        text += f"{mode}: {p['fully_rated_queries']} complete paired queries; wins/losses/ties {p['wins']}/{p['losses']}/{p['ties']}; mean D-A {p['mean_delta']}.\n\n"
    text += "Conflicting numeric labels are held out for review. Duplicate exports and reciprocal pairs do not add independent evidence. Existing labels retain source-file hashes, notes, and timestamps in label_evidence.json. Scale-v1, FMA comparisons, and song-identity SAFE labels are incompatible.\n\nStrongest observed low-rated D results are recorded in evaluation_metrics.json; these are examples, not a population failure rate. A/C and B/D use different checkpoints in Stage5E1, so D-versus-A is a system comparison, not an isolated pooling comparison.\n\nLaunch the reused local player with `python -m audio_similarity.cli.stage5e2 review --no-browser` (port 8784). Mutable judgments remain in the ignored research directory. Run `python -m audio_similarity.cli.stage5e2 metrics` after review to refresh metrics without changing the queue.\n"
    (report/'evaluation_report.md').write_text(text)
    atomic_json(report/'artifact_manifest.json', {p.name:file_sha256(p) for p in sorted(report.iterdir()) if p.is_file() and p.name!='artifact_manifest.json'})
    return metrics
