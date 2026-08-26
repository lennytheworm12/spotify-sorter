"""Hash-only verification of an existing one-time Stage 2B TEST reveal."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .stage2b_contract import ContractError, load_contract, sha256_file
from .stage2b_test import verify_test_lock


def verify_existing_test(config_path: str | Path, root: str | Path = ".") -> dict[str, Any]:
    root, config_path = Path(root).resolve(), Path(config_path).resolve()
    config = load_contract(config_path)
    lock = verify_test_lock(config_path, root, allow_existing=True)
    report_dir = root / config["paths"]["report_dir"]
    metrics_path = report_dir / "test_metrics.json"
    report_path = report_dir / "decision_report.md"
    receipt_path = report_dir / "test_reveal_receipt.json"
    if not all(path.is_file() for path in (metrics_path, report_path, receipt_path)):
        raise ContractError("existing TEST reveal is incomplete")
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("one_time_reveal") is not True:
        raise ContractError("TEST reveal receipt is not marked one-time")
    if receipt["selection_artifact_sha256"] != lock["selection_sha256"]:
        raise ContractError("receipt selection hash mismatch")
    if receipt["test_metrics_sha256"] != sha256_file(metrics_path):
        raise ContractError("receipt TEST metrics hash mismatch")
    if receipt["test_labels_sha256"] != metrics["test_label_sha256"]:
        raise ContractError("receipt TEST label hash mismatch")
    evaluation_code = root / "src/audio_similarity/stage2b_test.py"
    if receipt["test_evaluation_code_sha256"] != sha256_file(evaluation_code):
        raise ContractError("one-time evaluation code changed after reveal")
    allowed = config["verdict"]["allowed"]
    if metrics.get("verdict") not in allowed:
        raise ContractError("TEST verdict is not predeclared")
    report = report_path.read_text(encoding="utf-8")
    verdict_mentions = [verdict for verdict in allowed if f"`{verdict}`" in report]
    if verdict_mentions != [metrics["verdict"]]:
        raise ContractError("decision report must contain exactly the frozen verdict")
    return {
        "verified": True,
        "verdict": metrics["verdict"],
        "selected_representation": metrics["selected_representation"],
        "test_metrics_sha256": sha256_file(metrics_path),
        "decision_report_sha256": sha256_file(report_path),
        "receipt_sha256": sha256_file(receipt_path),
        "selection_checkpoint_commit": metrics["selection_checkpoint"]["commit"],
    }
