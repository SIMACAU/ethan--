from __future__ import annotations

import json
from pathlib import Path

import rebuild_submission
import validate_submission


ROOT = Path(__file__).resolve().parents[1]


def test_evidence_matches_locked_candidate() -> None:
    evidence = json.loads((ROOT / "evidence/online_score_evidence.json").read_text(encoding="utf-8"))
    assert evidence["candidate_sha256"] == rebuild_submission.FINAL_SHA256
    assert evidence["score"] == 67.6


def test_quick_rebuild_is_byte_identical_and_valid(tmp_path: Path) -> None:
    package = tmp_path / "submission.zip"
    report = rebuild_submission.build(
        ROOT / "artifacts/intermediate/base_submission.zip",
        ROOT / "artifacts/intermediate/donor_submission.zip",
        package,
    )
    assert report["output"]["sha256"] == rebuild_submission.FINAL_SHA256
    assert len(report["member_lineage"]) == rebuild_submission.FINAL_MEMBERS
    assert {row["name"] for row in report["member_lineage"] if row["origin"] == "donor"} == set(rebuild_submission.REPLACED_MEMBERS)
    assert package.read_bytes() == (ROOT / "artifacts/reference/submission.zip").read_bytes()
    validation = validate_submission.validate_package(package)
    assert validation["valid"] is True
    assert validation["valid_tasks"] == 34
    assert validation["physics_probe_steps"] == 120
