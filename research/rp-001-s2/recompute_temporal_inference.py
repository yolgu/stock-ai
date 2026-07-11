"""Recompute Cycle 001-003 maxT inference on chronological OOF fold segments."""

from __future__ import annotations

import dataclasses
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
from rp001_s2.cycle002_evaluation import run_cycle002_purged_oof
from rp001_s2.cycle002_run import _prepare_examples as _prepare_cycle002_examples
from rp001_s2.cycle003_evaluation import run_cycle003_purged_oof
from rp001_s2.cycle003_run import _prepare_examples as _prepare_cycle003_examples
from rp001_s2.development_run import (
    _convert_processed,
    _prepare_examples as _prepare_cycle001_examples,
)
from rp001_s2.evaluation import run_purged_oof
from rp001_s2.temporal_inference import synchronized_calendar_block_max_t


_ROOT = Path("/Users/jik/Documents/stock-sub")
_PROCESSED = Path(
    "research/rp-001-s2/candle-runs/S2-CANDLE-20260711-001/processed-candles.json"
)
_OUTPUT = Path(
    "research/rp-001-s2/inference-corrections/calendar-block-max-t-v1.json"
)
_CYCLES = (
    (
        "RP-001-S2-CYCLE-001",
        Path("research/rp-001-s2/contracts/development-analysis-contract-v1.0.1.json"),
        Path("research/rp-001-s2/evaluation-runs/S2-EVAL-20260711-001/result.json"),
    ),
    (
        "RP-001-S2-CYCLE-002",
        Path("research/rp-001-s2/contracts/cycle-002-development-contract-v1.json"),
        Path("research/rp-001-s2/evaluation-runs/S2-EVAL-20260711-002/result.json"),
    ),
    (
        "RP-001-S2-CYCLE-003",
        Path("research/rp-001-s2/contracts/cycle-003-development-contract-v1.json"),
        Path("research/rp-001-s2/evaluation-runs/S2-EVAL-20260711-003/result.json"),
    ),
)


def main() -> int:
    for _cycle_id, contract_path, result_path in _CYCLES:
        _verify_document(contract_path)
        _verify_document(result_path)
    processed = json.loads((_ROOT / _PROCESSED).read_text(encoding="utf-8"))
    observations, _adjusted_prices, session_count = _convert_processed(processed)

    cycle001_examples, _ = _prepare_cycle001_examples(observations)
    cycle001 = run_purged_oof(cycle001_examples, session_count=session_count)
    cycle002_examples, _ = _prepare_cycle002_examples(observations)
    cycle002 = run_cycle002_purged_oof(cycle002_examples, session_count=session_count)
    cycle003_examples, _ = _prepare_cycle003_examples(observations)
    cycle003 = run_cycle003_purged_oof(cycle003_examples, session_count=session_count)
    evaluations = (cycle001, cycle002, cycle003)

    corrected_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )
    cycle_corrections: list[dict[str, object]] = []
    for (cycle_id, contract_path, result_path), evaluation in zip(
        _CYCLES,
        evaluations,
        strict=True,
    ):
        old_result = json.loads((_ROOT / result_path).read_text(encoding="utf-8"))
        corrected = synchronized_calendar_block_max_t(evaluation.predictions)
        corrected_body = dataclasses.asdict(corrected)
        _verify_observed_contrasts_unchanged(old_result["maxTInference"], corrected_body)
        corrected_passed = _passed_families(corrected_body)
        old_passed = tuple(old_result["passedFamilies"])
        if old_passed or corrected_passed:
            raise ValueError("correction_changed_or_found_passing_family")
        cycle_corrections.append(
            {
                "cycleId": cycle_id,
                "contract": _binding_for_path(contract_path),
                "originalResult": _binding_for_path(result_path),
                "predictionRowCountPerFamily": len(evaluation.predictions) // 3,
                "originalInference": old_result["maxTInference"],
                "correctedInference": corrected_body,
                "originalPassedFamilies": list(old_passed),
                "correctedPassedFamilies": list(corrected_passed),
                "decisionAfterCorrection": "CycleTerminal",
                "confirmationAuthorizedAfterCorrection": False,
            }
        )

    store = LocalArtifactStore(_ROOT)
    artifact = store.publish_json(
        _ROOT / _OUTPUT,
        {
            "schemaVersion": "rp001-s2-calendar-block-max-t-correction.v1",
            "programId": "RP-001-S2",
            "correctedAt": corrected_at,
            "defect": (
                "original maxT used first-encounter session order from symbol-major "
                "OOF rows and allowed blocks to cross validation-fold gaps"
            ),
            "correction": (
                "sort ISO sessions chronologically and sample synchronized moving "
                "blocks independently within each OOF validation fold"
            ),
            "cycles": cycle_corrections,
            "decisionImpact": (
                "none; every observed Brier improvement and every corrected lower "
                "bound remains below delta 0.005"
            ),
            "confirmationPriceVolumeOpened": False,
            "ordersAccountsAssetsAccessed": False,
            "implementationBindings": {
                "correctionSource": _binding_for_path(
                    Path("research/rp-001-s2/src/rp001_s2/temporal_inference.py")
                ),
                "correctionTests": _binding_for_path(
                    Path("research/rp-001-s2/tests/test_temporal_inference.py")
                ),
                "recomputeSource": _binding_for_path(
                    Path("research/rp-001-s2/recompute_temporal_inference.py")
                ),
            },
            "inputProcessedCandles": _binding_for_path(_PROCESSED),
            "operationalDisposition": "NoTrade/no integration",
        },
    )
    event = AppendOnlyLocalLedger(
        _ROOT / "research/rp-001-s2/local-ledgers/program"
    ).append(
        "rp001_s2_cycles_001_003_temporal_inference_corrected",
        {
            "correction": _binding(artifact),
            "cycleIds": [value[0] for value in _CYCLES],
            "allDevelopmentGatesRemainFailed": True,
            "confirmationPriceVolumeOpened": False,
            "programTerminal": False,
            "nextState": "NEXT_CYCLE",
        },
        corrected_at,
    )
    print(
        json.dumps(
            {
                "status": "corrected",
                "correctionSha256": artifact.artifact_sha256,
                "ledgerSha256": event.record_sha256,
            },
            separators=(",", ":"),
        )
    )
    return 0


def _verify_observed_contrasts_unchanged(
    original: dict[str, object],
    corrected: dict[str, object],
) -> None:
    original_values = {
        (value["family_id"], value["baseline_id"]): value["brier_improvement"]
        for value in original["contrasts"]
    }
    corrected_values = {
        (value["family_id"], value["baseline_id"]): value["brier_improvement"]
        for value in corrected["contrasts"]
    }
    if original_values != corrected_values:
        raise ValueError("observed_contrast_changed_during_inference_correction")
    if any(float(value) >= 0.005 for value in corrected_values.values()):
        raise ValueError("observed_contrast_not_robustly_below_delta")


def _passed_families(inference: dict[str, object]) -> tuple[str, ...]:
    by_family: dict[str, list[bool]] = {}
    for value in inference["contrasts"]:
        by_family.setdefault(value["family_id"], []).append(
            bool(value["passed_delta_0_005"])
        )
    return tuple(
        family
        for family, passed in sorted(by_family.items())
        if len(passed) == 2 and all(passed)
    )


def _verify_document(relative: Path) -> None:
    path = _ROOT / relative
    digest = sha256_bytes(path.read_bytes())
    if Path(f"{path}.sha256").read_text(encoding="ascii") != f"{digest}\n":
        raise ValueError("document_sidecar_mismatch")


def _binding_for_path(relative: Path) -> dict[str, str]:
    return {
        "path": relative.as_posix(),
        "sha256": sha256_bytes((_ROOT / relative).read_bytes()),
    }


def _binding(value: LocalArtifactBinding) -> dict[str, str]:
    path = value.path.relative_to(_ROOT) if value.path.is_absolute() else value.path
    return {"path": path.as_posix(), "sha256": value.artifact_sha256}


if __name__ == "__main__":
    sys.exit(main())
