"""Freeze RP-001-S2 Cycle 003 before recovery candidate evaluation."""

from __future__ import annotations

import argparse
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


_CONTRACT = Path(
    "research/rp-001-s2/contracts/cycle-003-development-contract-v1.json"
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", required=True, type=Path)
    values = parser.parse_args(argv)
    root = values.repository_root.absolute()
    frozen_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )
    processed = _verified(
        root,
        "research/rp-001-s2/candle-runs/S2-CANDLE-20260711-001/processed-candles.json",
    )
    bindings = {
        "cycle002Result": _verified(
            root,
            "research/rp-001-s2/evaluation-runs/S2-EVAL-20260711-002/result.json",
        ),
        "cycle002Decision": _verified(
            root,
            "research/rp-001-s2/cycle-decisions/cycle-002-decision.json",
        ),
        "cycle002PrefreezeDisclosure": _verified(
            root,
            "research/rp-001-s2/cycle-decisions/cycle-002-prefreeze-review-trial.json",
        ),
        "cycle002Contract": _verified(
            root,
            "research/rp-001-s2/contracts/cycle-002-development-contract-v1.json",
        ),
        "candleManifest": _verified(
            root,
            "research/rp-001-s2/candle-runs/S2-CANDLE-20260711-001/manifest.json",
        ),
        "metadataSampleSelection": _verified(
            root,
            "research/rp-001-s2/metadata-runs/S2-META-20260711-002/sample-selection.json",
        ),
        "cycle003FormulaSource": _file(
            root, "research/rp-001-s2/src/rp001_s2/cycle003.py"
        ),
        "cycle003EvaluationSource": _file(
            root, "research/rp-001-s2/src/rp001_s2/cycle003_evaluation.py"
        ),
        "cycle003RunSource": _file(
            root, "research/rp-001-s2/src/rp001_s2/cycle003_run.py"
        ),
        "cycle003Tests": _file(
            root, "research/rp-001-s2/tests/test_cycle003.py"
        ),
        "cycle003Cli": _file(root, "run_s2_cycle_003.py"),
        "cycle003FreezeSource": _file(
            root, "research/rp-001-s2/freeze_cycle_003.py"
        ),
        "cycleControlSource": _file(
            root, "research/rp-001-s2/src/rp001_s2/cycle_control.py"
        ),
        "reusedFormulaModelSource": _file(
            root, "research/rp-001-s2/src/rp001_s2/discovery.py"
        ),
        "reusedFoldMaxTSource": _file(
            root, "research/rp-001-s2/src/rp001_s2/evaluation.py"
        ),
        "reusedCandleConversionSource": _file(
            root, "research/rp-001-s2/src/rp001_s2/development_run.py"
        ),
        "localEvidenceSource": _file(
            root, "research/rp-001/src/rp001/local_evidence.py"
        ),
    }
    contract = LocalArtifactStore(root).publish_json(
        root / _CONTRACT,
        {
            "schemaVersion": "rp001-s2-cycle-003-development-contract.v1",
            "programId": "RP-001-S2",
            "cycleId": "RP-001-S2-CYCLE-003",
            "status": "development_authorized_confirmation_price_unopened",
            "frozenAt": frozen_at,
            "sampleRole": "seen_development_reused_for_internal_discovery",
            "eligibleForConfirmationEvidence": False,
            "usageScope": "research_only",
            "priorArtifactResultsInformedDesign": True,
            "candidatePerformanceOpenedBeforeFreeze": False,
            "cycle003RealLabelPrevalenceOpenedBeforeFreeze": False,
            "confirmationPriceVolumeOpened": False,
            "confirmationReuseStatus": "not_used_price_unopened",
            "nextCycleOnFailure": "RP-001-S2-CYCLE-004",
            "estimand": {
                "id": "downside_price_regime_recovery_by_5_nonnegative_at_10",
                "class": "active_downside_regime_recovery_forecast",
                "claimLevel": "price_volume_regime_proxy_only",
                "humanPsychologyIdentified": False,
                "eligibleSignalState": "m5_native <= -1.0",
                "recoverySearchWindowSessions": 5,
                "primaryHorizonSessions": 10,
                "rollingRecoveryStatistic": (
                    "r[t,k]=(ln(P_adj[t+k])-ln(P_adj[t+k-5]))/"
                    "(sqrt(5)*sigma_t)"
                ),
                "positiveLabel": (
                    "first k in 1..5 with r[t,k]>=0 exists and r[t,10]>=0"
                ),
                "futureUse": "adjusted future closes are used only in label construction",
            },
            "features": {
                "sharedMask": "41 PIT rows ending at t for every candidate and baseline",
                "base": "Cycle 001 native-return and turnover features",
                "downsideDuration": (
                    "consecutive prior PIT states with m5_s<=-1, capped at 20"
                ),
                "cumulativeDrawdown": (
                    "q=(ln(C_native[t-d])-ln(C_native[t]))/(sqrt(d)*sigma_t)"
                ),
                "sourceBinding": "separate SHA-256 over every one of the 41 read rows",
                "availability": "official daily close usable next session",
            },
            "candidateFamilies": [
                {
                    "id": "rp001_s2.m3.downside_deceleration_capitulation.v1",
                    "mechanism": "downside deceleration and turnover-confirmed capitulation",
                    "basis": [
                        "H(z1;0,2.5)",
                        "H(m3-m10;0,2.5)",
                        "H(curvature;0,2.5)",
                        "cuberoot(H(z1)*H(curvature)*H(zv;0,3))",
                    ],
                },
                {
                    "id": "rp001_s2.m2.lower_tail_stretch_reversal.v1",
                    "mechanism": "multi-horizon lower-tail stretch and reversal",
                    "basis": [
                        "H(-m5;1,3)",
                        "H(-m10;.5,3)",
                        "H(-m20;0,3)",
                        "cuberoot(H(-m5)*H(-m10)*H(-m20))",
                    ],
                },
                {
                    "id": "rp001_s2.m4.downside_duration_recovery_hazard.v1",
                    "mechanism": "downside-regime age and cumulative-drawdown recovery hazard",
                    "basis": [
                        "H(d;1,6)",
                        "H(d;3,10)",
                        "H(q;1,4)",
                        "sqrt(H(d;3,10)*H(q;1,4))",
                    ],
                },
            ],
            "baselines": [
                {
                    "id": "rp001_s2.baseline.jeffreys_constant.v1",
                    "formula": "p=(successes+0.5)/(trials+1)",
                },
                {
                    "id": "rp001_s2.baseline.directional_z1_bins.v1",
                    "formula": (
                        "training-only z1 bins [-8,-1.5),[-1.5,-.5),[-.5,.5),"
                        "[.5,1.5),[1.5,8], Jeffreys probability"
                    ),
                },
            ],
            "probabilityModel": {
                "formula": "sigmoid(alpha+sum_j beta_j*basis_j)",
                "constraint": "beta_j>=0",
                "fit": "active-set Newton ridge logistic; both outcome classes required",
                "l2Grid": [0.01, 0.1, 1.0, 10.0],
                "selection": (
                    "inner purged OOF pooled Brier minimum; larger lambda on exact tie"
                ),
                "convergence": "normalized KKT residual <=1e-6 or run invalid",
            },
            "validation": {
                "outer": {
                    "minimumTrainingSessions": 252,
                    "purgeSessions": 10,
                    "validationSessions": 63,
                    "embargoSessions": 10,
                },
                "inner": {
                    "minimumTrainingSessions": 126,
                    "purgeSessions": 10,
                    "validationSessions": 42,
                    "embargoSessions": 10,
                },
                "sameEligibleRowMask": True,
                "alarmThreshold": "nextafter(type-7 Q0.90,+infinity)",
                "alarmComparison": "candidate_probability >= threshold",
                "tiePolicy": "Q90 ties are not alarms",
                "primaryMetric": "Brier improvement over each of two baselines",
                "minimumEffectDelta": 0.005,
                "blockBootstrap": {
                    "method": "synchronized_studentized_maxT",
                    "blockLengthSessions": 20,
                    "replicates": 2000,
                    "contrastCount": 6,
                },
                "gate": "both simultaneous 95% lower bounds exceed 0.005",
                "seed": 20260711,
            },
            "inputContracts": {
                "missing": "abstain; no zero fill; no reweight",
                "constantSeries": "abstain if MAD scale <1e-6",
                "corporateAction": (
                    "abstain if any native feature-window return magnitude >=ln(1.35)"
                ),
                "outOfDomain": "abstain outside closed standardized [-8,8]",
                "sessionOrder": "strictly increasing unique ISO session dates",
                "formulaFamily": "basis, training rows, and model share exact Formula ID",
            },
            "economics": {
                "actualOrders": False,
                "actionProxy": "hypothetical long entry at next-session close",
                "netBenefit": "P_adj[t+10]/P_adj[t+1]-1-cost",
                "costsBps": [100.0, 300.0],
                "formalG8Status": (
                    "not_evaluated_action_execution_impact_and_capital_contract_absent"
                ),
                "portfolioMdd": "not_identifiable_no_capital_allocation",
            },
            "predecessorDiagnosis": {
                "cycle002BestBrierImprovementVsB1": 0.0001421133557248132,
                "cycle002MinimumEffectDelta": 0.005,
                "cycle002Decision": "CycleTerminal_to_RP-001-S2-CYCLE-003",
                "cycle002Q90TieIssue": (
                    "classification_only_nonconclusion_changing; repaired in Cycle003"
                ),
                "cycle002PrefreezeDiagnostic": "disclosed_in_append_only_event_000012",
                "programTerminal": False,
            },
            "discoveryCoverageAfterExecution": {
                "empiricalCycleCount": 3,
                "candidateFormulaVersionCount": 9,
                "mechanismClasses": ["M1", "M2", "M3", "M4"],
                "estimandClasses": [
                    "upside_onset",
                    "upside_end",
                    "downside_recovery",
                ],
            },
            "qualityEvidence": {
                "redToGreenTests": 11,
                "s2TestsPassed": 67,
                "s2TestsTotal": 67,
                "verificationCommand": (
                    "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=research/rp-001-s2/src:"
                    "research/rp-001/src <bundled-python> -m unittest discover -s "
                    "research/rp-001-s2/tests"
                ),
            },
            "processedCandles": processed,
            "bindings": bindings,
            "ordersAccountsAssetsAllowed": False,
            "operationalDisposition": "NoTrade/no integration",
        },
    )
    event = AppendOnlyLocalLedger(
        root / "research/rp-001-s2/local-ledgers/program"
    ).append(
        "rp001_s2_cycle_003_development_frozen",
        {
            "contract": _binding(contract, root),
            "processedCandles": processed,
            "candidatePerformanceOpenedBeforeFreeze": False,
            "confirmationPriceVolumeOpened": False,
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
    sidecar = Path(f"{root / relative}.sha256").read_text(encoding="ascii")
    if sidecar != f"{value['sha256']}\n":
        raise ValueError("sidecar_mismatch")
    return value


def _binding(value: LocalArtifactBinding, root: Path) -> dict[str, str]:
    path = value.path.relative_to(root) if value.path.is_absolute() else value.path
    return {"path": path.as_posix(), "sha256": value.artifact_sha256}


if __name__ == "__main__":
    sys.exit(main())
