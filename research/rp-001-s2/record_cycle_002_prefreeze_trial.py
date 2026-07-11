"""Disclose the in-memory Cycle 002 diagnostic that preceded the freeze."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from rp001.local_evidence import (
    AppendOnlyLocalLedger,
    LocalArtifactBinding,
    LocalArtifactStore,
    sha256_bytes,
)


_ROOT = Path("/Users/jik/Documents/stock-sub")
_CONTRACT = Path(
    "research/rp-001-s2/contracts/cycle-002-development-contract-v1.json"
)
_DISCLOSURE = Path(
    "research/rp-001-s2/cycle-decisions/cycle-002-prefreeze-review-trial.json"
)


def main() -> int:
    recorded_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )
    contract = json.loads((_ROOT / _CONTRACT).read_text(encoding="utf-8"))
    contract_binding = _verified_path(_CONTRACT)
    formula_binding = contract["bindings"]["cycle002FormulaSource"]
    evaluation_binding = contract["bindings"]["cycle002EvaluationSource"]
    run_binding = contract["bindings"]["cycle002RunSource"]
    for binding in (formula_binding, evaluation_binding, run_binding):
        if _verified_path(Path(binding["path"])) != binding:
            raise ValueError("frozen_implementation_binding_mismatch")
    artifact = LocalArtifactStore(_ROOT).publish_json(
        _ROOT / _DISCLOSURE,
        {
            "schemaVersion": "rp001-s2-prefreeze-review-trial.v1",
            "programId": "RP-001-S2",
            "cycleId": "RP-001-S2-CYCLE-002",
            "recordedAt": recorded_at,
            "trialTiming": "before_cycle_002_freeze",
            "sampleRole": "seen_development_reused_for_internal_discovery",
            "executionMode": "read_only_in_memory_reviewer_diagnostic",
            "artifactPublicationDuringTrial": False,
            "candidateFamilyCount": 3,
            "predictionRowCountPerFamily": 567,
            "maxTReplicates": 100,
            "familyResults": [
                {
                    "familyId": "rp001_s2.m2.tail_stretch_reversion.v1",
                    "developmentGate": "fail",
                },
                {
                    "familyId": "rp001_s2.m3.deceleration_distribution.v1",
                    "developmentGate": "fail",
                },
                {
                    "familyId": "rp001_s2.m4.active_duration_hazard.v1",
                    "developmentGate": "fail",
                },
            ],
            "contractCorrection": {
                "field": "cycle002CandidatePerformanceOpenedBeforeFreeze",
                "sealedValue": False,
                "correctedValue": True,
                "sealedStatementSuperseded": True,
            },
            "officialRunClassification": (
                "unchanged_formula_2000_replicate_repetition_not_first_performance_open"
            ),
            "implementationChangedAfterDiagnostic": False,
            "implementationBindings": {
                "formula": formula_binding,
                "evaluation": evaluation_binding,
                "run": run_binding,
            },
            "contract": contract_binding,
            "confirmationPriceVolumeOpened": False,
            "ordersAccountsAssetsAccessed": False,
            "operationalDisposition": "NoTrade/no integration",
        },
    )
    event = AppendOnlyLocalLedger(
        _ROOT / "research/rp-001-s2/local-ledgers/program"
    ).append(
        "rp001_s2_cycle_002_prefreeze_review_trial_disclosed",
        {
            "cycleId": "RP-001-S2-CYCLE-002",
            "disclosure": _binding(artifact),
            "correctedCandidatePerformanceOpenedBeforeFreeze": True,
            "confirmationPriceVolumeOpened": False,
            "implementationChangedAfterDiagnostic": False,
        },
        recorded_at,
    )
    print(
        json.dumps(
            {
                "status": "disclosed",
                "disclosureSha256": artifact.artifact_sha256,
                "ledgerSha256": event.record_sha256,
            },
            separators=(",", ":"),
        )
    )
    return 0


def _verified_path(relative: Path) -> dict[str, str]:
    path = _ROOT / relative
    digest = sha256_bytes(path.read_bytes())
    sidecar = Path(f"{path}.sha256")
    if sidecar.exists() and sidecar.read_text(encoding="ascii") != f"{digest}\n":
        raise ValueError("artifact_sidecar_mismatch")
    return {"path": relative.as_posix(), "sha256": digest}


def _binding(value: LocalArtifactBinding) -> dict[str, str]:
    path = value.path.relative_to(_ROOT) if value.path.is_absolute() else value.path
    return {"path": path.as_posix(), "sha256": value.artifact_sha256}


if __name__ == "__main__":
    sys.exit(main())
