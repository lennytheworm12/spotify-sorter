"""Exact selected source retention and frozen representation reuse for seed tracks."""
from __future__ import annotations

import json
import hashlib
import re
import shutil
import sqlite3
import tempfile
from contextlib import closing
from dataclasses import replace
from pathlib import Path

import numpy as np

from .stage5a_contract import load_contract
from .stage5a_cache import Stage5ACache
from .stage5a_materialize import TrackInput, materialize
from .stage5b1a_models import SpotifyTrack, file_sha256
from .stage5b1b_artifacts import atomic_json
from .stage5b_selector_aware_fallback import discover_and_select_with_fallback, PROVIDER_ERROR
from .stage5c2_discovery import default_provider
from .stage5c2a_retention import PersistentExactAudioAcquirer, probe_and_validate
from .stage5c1_pipeline import load_frozen_encoders, verify_model_files
from .stage5c2_rate_limit import classify_acquisition_failure
from .stage5d0a_network import WorkerStopped
from .stage5d0a_manifest import _write_immutable_json, document_sha256


def json_file(path):
    if not path.exists():
        return None
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError("expected a JSON object in persistent source state")
    return value


class GovernedSearch:
    def __init__(self, governor):
        self.governor = governor
        self.provider = default_provider()
        self.provider.provider = replace(self.provider.provider, max_attempts=1)
        import yt_dlp
        self.provider.backend._youtube_dl_factory = lambda options: yt_dlp.YoutubeDL(
            options | {"sleep_interval_requests": 1.5, "extractor_retries": 0,
                       "fragment_retries": 0})

    def discover_query(self, track, query, *, limit=3):
        return self.governor.call(track.spotify_track_id, "SEARCH", query,
                                  lambda: self.provider.discover_query(track, query, limit=limit))


class SeedProcessor:
    def __init__(self, root: Path, directory: Path, governor):
        self.root, self.directory, self.governor = root, directory, governor
        self.media = root / ".research_audio"
        self.contract = load_contract(root / "reports/holistic_stage4a_dual/audio_representation_v1.json")
        if self.contract.centers_sec != (5, 15, 25) or self.contract.clap_weight != 0.7172981519 or self.contract.muq_weight != 0.2827018481:
            raise ValueError("frozen centered30 contract changed")
        frozen_modules = (
            "stage5b4a_query_contract_repair.py", "stage5b4c_artist_decomposition.py",
            "stage5b_selector_aware_fallback.py", "stage5b3_minimal_selector.py",
            "stage5a_contract.py", "stage5a_materialize.py", "stage4a_sampling.py",
            "stage4a_dual_scoring.py", "holistic_encoders.py", "stage5c1_pipeline.py")
        _write_immutable_json(directory / "frozen_upstream_contracts.json", {
            "representation_artifact_sha256": self.contract.artifact_sha256,
            "vector_contract_sha256": self.contract.vector_contract_sha256,
            "encoder_provenance": {encoder.encoder_id: encoder.provenance for encoder in self.contract.encoders},
            "code_sha256": {name: file_sha256(Path(__file__).parent / name) for name in frozen_modules}})
        self.encoders = None
        self.provider = GovernedSearch(governor)
        self.acquirer = PersistentExactAudioAcquirer(extraction_request_sleep_seconds=1.5)
        self.cache_file = root / "artifacts/stage5d_centered30/representations.sqlite"
        self.corpus = "spotify_research"
        self.corpus_version = "centered30_v1-commercial-source-v1"
        self.historical = {}
        for path in sorted((root / "artifacts").glob("stage5c*/media_identity.json")):
            cache = path.parent / "representations.sqlite"
            if cache.exists():
                for spotify_id, link in (json_file(path) or {}).get("tracks", {}).items():
                    self.historical.setdefault(spotify_id, []).append((cache, link))

    def selection_path(self, spotify_id):
        return self.directory / "selected" / f"{spotify_id}.json"

    def freeze_selection(self, spotify_id, selection):
        path = self.selection_path(spotify_id)
        _write_immutable_json(path, {"selection": selection,
                                    "selection_sha256": document_sha256(selection)})

    def inspect(self, track):
        spotify_id = track["spotify_track_id"]
        frozen_selection = json_file(self.selection_path(spotify_id))
        selection = frozen_selection["selection"] if frozen_selection is not None else None
        if frozen_selection is not None and frozen_selection["selection_sha256"] != document_sha256(selection):
            raise ValueError("frozen selected source digest mismatch")
        provenance = json_file(self.media / spotify_id / "provenance.json")
        if provenance and provenance.get("spotify_track_id") != spotify_id:
            raise ValueError("retained provenance Spotify identity mismatch")
        if selection is None and provenance:
            selection = {"youtube_video_id": provenance["youtube_video_id"],
                         "source_url": provenance["source_url"],
                         "selected_rank": provenance["selected_rank"],
                         "provenance": provenance}
        links = self.historical.get(spotify_id, [])
        if selection is None and links:
            videos = {link["video_id"] for _, link in links}
            if len(videos) != 1:
                raise ValueError("conflicting historical source selections")
            video = next(iter(videos))
            selection = {"youtube_video_id": video, "source_url": f"https://www.youtube.com/watch?v={video}",
                         "selected_rank": None, "historical_media_ledger": True}
        if selection:
            video = selection.get("youtube_video_id", "")
            if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video) or selection.get("source_url") != f"https://www.youtube.com/watch?v={video}":
                raise ValueError("frozen selection has invalid exact YouTube identity")
            if provenance and provenance["youtube_video_id"] != selection["youtube_video_id"]:
                raise ValueError("retained source differs from frozen selection")
            if not self.selection_path(spotify_id).exists():
                self.freeze_selection(spotify_id, selection)
        retained = None
        if provenance:
            source = (self.media / provenance["retained_relative_path"]).resolve()
            if (self.media / spotify_id).resolve() not in source.parents:
                raise ValueError("retained source escapes media root")
            if source.exists():
                if source.stat().st_size != provenance["file_size_bytes"] or file_sha256(source) != provenance["source_sha256"]:
                    raise ValueError("existing retained source failed SHA integrity")
                if provenance.get("full_decode_validated") is not True:
                    raise ValueError("source lacks full-decode validation")
                retained = source
        representation = self.find_representation(spotify_id, selection, provenance)
        return {"selection": selection, "provenance": provenance, "source": retained,
                "representation": representation, "network_required": retained is None}

    def find_representation(self, spotify_id, selection, provenance):
        if selection is None:
            return None
        candidates = [(path, link["source_audio_sha256"]) for path, link in self.historical.get(spotify_id, [])
                      if link["video_id"] == selection["youtube_video_id"]]
        if provenance and self.cache_file.exists():
            candidates.append((self.cache_file, provenance["source_sha256"]))
        for path, source_hash in candidates:
            with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
                db.row_factory = sqlite3.Row
                rows = db.execute("SELECT * FROM tracks WHERE stable_track_id=? AND source_audio_sha256=? AND vector_contract_sha256=? AND status='SUCCESS'",
                                  (spotify_id, source_hash, self.contract.vector_contract_sha256)).fetchall()
                for row in rows:
                    for encoder in self.contract.encoders:
                        identity = self.contract.encoder_analysis_identity(corpus=row["corpus"], corpus_version=row["corpus_version"],
                            stable_track_id=spotify_id, source_audio_sha256=source_hash, canonical_pcm_sha256=row["canonical_pcm_sha256"], encoder_id=encoder.encoder_id)
                        pooled = db.execute("SELECT * FROM pooled WHERE encoder_analysis_identity=? AND status='SUCCESS'", (identity,)).fetchall()
                        segments = db.execute("SELECT * FROM segments WHERE encoder_analysis_identity=? AND status='SUCCESS'", (identity,)).fetchall()
                        if len(pooled) != 1 or len(segments) != 3 or {item["center_sec"] for item in segments} != {5, 15, 25}:
                            raise ValueError("successful cache row lacks complete vectors")
                        for item in pooled + segments:
                            vector = np.frombuffer(item["embedding"], dtype="<f4")
                            if vector.shape != (encoder.dimension,) or not np.isfinite(vector).all() or not np.isclose(np.linalg.norm(vector), 1, atol=1e-5) or hashlib.sha256(item["embedding"]).hexdigest() != item["embedding_sha256"]:
                                raise ValueError("representation cache vector integrity failed")
                    return {"cache_path": str(path.relative_to(self.root)), **dict(row)}
        return None

    def process(self, track, inspected, checkpoint):
        spotify_id = track["spotify_track_id"]
        result = {"downloaded_bytes": 0, "source_retained": inspected["source"] is not None,
                  "representation_complete": inspected["representation"] is not None,
                  "clap_inferred_segments": 0, "muq_inferred_segments": 0}
        selection = inspected["selection"]
        if selection is None:
            checkpoint("DISCOVERING")
            target = SpotifyTrack.from_dict({"stable_track_id": track["stage5d0a_track_id"],
                **{key: track.get(key) for key in ("spotify_track_id", "title", "artists", "album", "duration_ms", "release_year", "isrc")}})
            discovery = discover_and_select_with_fallback(target, self.provider)
            atomic_json(self.directory / "discovery" / f"{spotify_id}.json", discovery)
            if discovery["outcome"] == PROVIDER_ERROR:
                return {"state": "ACQUISITION_FAILED", "failure_category": "RESOLVER_PROVIDER_ERROR", "result": result}
            if not discovery.get("selected_video_id"):
                return {"state": "MANUAL_TAIL", "result": result}
            video = discovery["selected_video_id"]
            selection = {"youtube_video_id": video, "source_url": f"https://www.youtube.com/watch?v={video}",
                         "selected_rank": discovery["selected_rank"], "resolver": discovery}
            self.freeze_selection(spotify_id, selection)
        checkpoint("RESOLVED", selected_video_id=selection["youtube_video_id"])
        source, provenance = inspected["source"], inspected["provenance"]
        if source is None:
            checkpoint("ACQUIRING")
            scratch = Path(tempfile.mkdtemp(prefix=".stage5d-scratch-", dir=self.media))
            failure_stage = "ACQUISITION_FAILED"
            try:
                acquisition_track = {"spotify_track_id": spotify_id, **selection}
                def acquire_attempt():
                    attempt_dir = Path(tempfile.mkdtemp(prefix="attempt-", dir=scratch))
                    try:
                        acquisition = self.acquirer.acquire(acquisition_track, attempt_dir)
                        completed = Path(acquisition["downloaded_path"]).resolve()
                        if attempt_dir.resolve() not in completed.parents:
                            raise ValueError("download escaped its attempt directory")
                        return acquisition | {"downloaded_bytes": completed.stat().st_size}
                    except BaseException:
                        shutil.rmtree(attempt_dir)
                        raise
                acquisition = self.governor.call(spotify_id, "MEDIA", selection["source_url"],
                    acquire_attempt)
                downloaded = Path(acquisition["downloaded_path"]).resolve()
                if scratch.resolve() not in downloaded.parents:
                    raise ValueError("acquisition output escaped scratch directory")
                failure_stage = "DECODE_FAILED"
                # Retain valid short recordings too; the frozen materializer alone
                # decides whether its unchanged three windows are available.
                technical = probe_and_validate(downloaded, minimum_duration_seconds=0.0)
                failure_stage = "SOURCE_RETENTION_FAILED"
                source_hash = file_sha256(downloaded)
                destination = self.media / spotify_id
                destination.mkdir(parents=True, exist_ok=True)
                source = destination / f"source{downloaded.suffix}"
                if source.exists():
                    raise ValueError("refusing to overwrite retained source")
                provenance = {"schema_version": "stage5d0a-retained-source-v1",
                    "spotify_track_id": spotify_id, "spotify_title": track["title"],
                    "spotify_artists": track["artists"], "album": track.get("album"),
                    "release_year": track["release_year"], **selection,
                    "retained_relative_path": str(source.relative_to(self.media)),
                    "source_sha256": source_hash, "file_size_bytes": downloaded.stat().st_size,
                    "source_duration_seconds": technical["duration_seconds"], **technical,
                    "acquisition_timestamp": acquisition["acquisition_started_at"],
                    "representation_linkage": inspected["representation"],
                    "warnings": acquisition.get("warnings", [])}
                # Stage provenance first, so a crash after promotion remains identifiable.
                atomic_json(destination / "provenance.json", provenance)
                downloaded.replace(source)
                result.update(source_retained=True, downloaded_bytes=source.stat().st_size,
                              provider_warnings=acquisition.get("warnings", []))
            except WorkerStopped:
                raise
            except Exception as exc:
                category = classify_acquisition_failure(exc)["category"] if failure_stage == "ACQUISITION_FAILED" else failure_stage
                return {"state": "ACQUISITION_FAILED", "failure_category": category,
                        "failure_detail": str(exc)[:2000], "result": result}
            finally:
                shutil.rmtree(scratch)
        result["retained_bytes"] = source.stat().st_size
        checkpoint("SOURCE_RETAINED", result=dict(result))
        representation = inspected["representation"]
        if representation is None:
            checkpoint("MATERIALIZING")
            if self.encoders is None:
                verify_model_files(self.root, self.contract)
                self.encoders = load_frozen_encoders(self.root, self.contract)
            with Stage5ACache(self.cache_file) as cache:
                stats = materialize([TrackInput(spotify_id, source, provenance["source_sha256"])],
                    corpus=self.corpus, corpus_version=self.corpus_version, contract=self.contract,
                    cache=cache, encoders=self.encoders,
                    output_dir=self.cache_file.parent / "tracks" / spotify_id)
            result.update(clap_inferred_segments=stats.clap.inferred_segments,
                          muq_inferred_segments=stats.muq.inferred_segments)
            representation = self.find_representation(spotify_id, selection, provenance)
            if representation is None:
                return {"state": "MATERIALIZATION_FAILED", "result": result,
                        "failure_category": str(stats.failure_categories)}
        result.update(representation_complete=True, representation=representation,
                      retained_relative_path=provenance["retained_relative_path"],
                      source_sha256=provenance["source_sha256"])
        if provenance.get("schema_version") == "stage5d0a-retained-source-v1":
            provenance["representation_linkage"] = representation
            atomic_json(self.media / spotify_id / "provenance.json", provenance)
        # Keep prior Stage 5C provenance intact; attach new linkage in this batch's index.
        atomic_json(self.directory / "source_index" / f"{spotify_id}.json", {
            "spotify_track_id": spotify_id, "youtube_video_id": selection["youtube_video_id"],
            "source_sha256": provenance["source_sha256"], "representation": representation,
            "retained_relative_path": provenance["retained_relative_path"]})
        return {"state": "COMPLETE", "result": result}
