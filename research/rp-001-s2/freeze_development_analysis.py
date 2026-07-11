"""Freeze the executable development analysis before any outcome evaluation."""

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
    "research/rp-001-s2/contracts/development-analysis-contract-v1.0.1.json"
)


def main() -> int:
    root = _ROOT
    frozen_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )
    processed = _verified(
        root,
        "research/rp-001-s2/candle-runs/S2-CANDLE-20260711-001/processed-candles.json",
    )
    bindings = {
        "merc": _verified(root, "research/rp-001-s2/contracts/cycle-001-merc-v1.json"),
        "candleManifest": _verified(
            root,
            "research/rp-001-s2/candle-runs/S2-CANDLE-20260711-001/manifest.json",
        ),
        "formulaSource": _file(root, "research/rp-001-s2/src/rp001_s2/discovery.py"),
        "formulaTests": _file(root, "research/rp-001-s2/tests/test_discovery.py"),
        "evaluationSource": _file(root, "research/rp-001-s2/src/rp001_s2/evaluation.py"),
        "evaluationTests": _file(root, "research/rp-001-s2/tests/test_evaluation.py"),
        "developmentRunSource": _file(
            root, "research/rp-001-s2/src/rp001_s2/development_run.py"
        ),
        "developmentRunCli": _file(root, "run_s2_development.py"),
        "localEvidenceSource": _file(root, "research/rp-001/src/rp001/local_evidence.py"),
        "localEvidenceTests": _file(
            root, "research/rp-001/tests/test_local_evidence_contract.py"
        ),
    }
    contract = LocalArtifactStore(root).publish_json(
        root / _CONTRACT,
        {
            "schemaVersion": "rp001-s2-development-analysis-contract.v1.0.1",
            "programId": "RP-001-S2",
            "cycleId": "RP-001-S2-CYCLE-001",
            "status": "analysis_authorized_confirmation_price_unopened",
            "frozenAt": frozen_at,
            "processedCandles": processed,
            "bindings": bindings,
            "postPriceChangeClass": (
                "complete_frozen_maxT_implementation_before_outcome_open"
            ),
            "changeFromMercBoundEvaluator": (
                "implement the already frozen synchronized 20-session block "
                "studentized maxT and evidence publication; candidate formulas, "
                "label, folds, lambda grid, threshold rule, delta, seed, and costs unchanged"
            ),
            "developmentPriceVolumeOpened": True,
            "developmentOutcomePerformanceOpenedBeforeThisFreeze": False,
            "confirmationPriceVolumeOpened": False,
            "postResultTuning": False,
            "candidateFamilyCount": 3,
            "baselineCount": 2,
            "primaryGate": (
                "each candidate's simultaneous 95% Brier-improvement lower bound "
                "must exceed 0.005 versus both B1 and B2"
            ),
            "ordersAccountsAssetsAllowed": False,
            "operationalDisposition": "NoTrade/no integration",
        },
    )
    event = AppendOnlyLocalLedger(
        root / "research/rp-001-s2/local-ledgers/program"
    ).append(
        "rp001_s2_development_analysis_frozen",
        {
            "contract": _binding(contract, root),
            "processedCandles": processed,
            "developmentOutcomePerformanceOpened": False,
            "confirmationPriceVolumeOpened": False,
            "postResultTuning": False,
        },
        frozen_at,
    )
    print(
        json.dumps(
            {
                "status": "frozen",
                "contractSha256": contract.artifact_sha256,
                "ledgerSha256": event.record_sha256,
            },
            separators=(",", ":"),
        )
    )
    return 0


def _file(root: Path, relative: str) -> dict[str, str]:
    return {"path": relative, "sha256": sha256_bytes((root / relative).read_bytes())}


def _verified(root: Path, relative: str) -> dict[str, str]:
    value = _file(root, relative)
    if Path(f"{root / relative}.sha256").read_text(encoding="ascii") != f"{value['sha256']}\n":
        raise ValueError("sidecar_mismatch")
    return value


def _binding(value: LocalArtifactBinding, root: Path) -> dict[str, str]:
    path = value.path.relative_to(root) if value.path.is_absolute() else value.path
    return {"path": path.as_posix(), "sha256": value.artifact_sha256}


if __name__ == "__main__":
    sys.exit(main())
