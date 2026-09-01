import json
from dataclasses import replace
from pathlib import Path

import pytest

from audio_similarity.cli.stage5b1a import (
    _preflight_run_artifacts,
    firecrawl_transport,
    verify_inputs,
)
from audio_similarity.stage5b1a_config import load_config
from audio_similarity.stage5b1a_experiment import (
    load_discovery_results,
    run_discovery_experiment,
)
from audio_similarity.stage5b1a_models import Stage5B1AValidationError, load_frozen_manifest
from tests.test_stage5b1a_experiment import FakeAdapter


ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "configs/stage5b1a_firecrawl.json"


def test_verify_inputs_is_network_free_and_reports_frozen_gate():
    status = verify_inputs(CONFIG)
    assert status["status"] == "READY_FOR_REAL_DISCOVERY"
    assert status["track_count"] == 25
    assert status["candidate_limit"] == 5
    assert status["gate"] == {
        "pass_min_recall_at_5": 0.9,
        "conditional_min_recall_at_5": 0.8,
    }


def test_transport_selection_uses_keyless_when_credential_is_absent():
    config = load_config(CONFIG)
    transport = firecrawl_transport(config, environment={})
    assert transport.authentication_mode == "keyless"


def test_transport_selection_prefers_environment_credential():
    config = load_config(CONFIG)
    transport = firecrawl_transport(config, environment={"FIRECRAWL_API_KEY": "secret"})
    assert transport.authentication_mode == "api_key"


def test_real_run_preflight_protects_existing_results_and_human_labels(tmp_path):
    config = load_config(CONFIG)
    artifacts = config.artifacts | {
        "discovery_results": tmp_path / "results.json",
        "review": tmp_path / "review.csv",
    }
    isolated = replace(config, artifacts=artifacts)
    artifacts["discovery_results"].write_text("{}")
    with pytest.raises(FileExistsError, match="discovery artifact"):
        _preflight_run_artifacts(isolated, overwrite=False)


def test_result_loader_binds_manifest_config_order_and_unique_candidates(tmp_path):
    config = load_config(CONFIG)
    manifest = load_frozen_manifest(config.manifest_path, expected_sha256=config.manifest_sha256)
    results = run_discovery_experiment(manifest, config, FakeAdapter(), clock=lambda: "fixed")
    path = tmp_path / "results.json"
    path.write_text(json.dumps(results))
    assert load_discovery_results(path, manifest, config) == results

    changed = json.loads(json.dumps(results))
    changed["tracks"] = list(reversed(changed["tracks"]))
    path.write_text(json.dumps(changed))
    with pytest.raises(Stage5B1AValidationError, match="manifest order"):
        load_discovery_results(path, manifest, config)
