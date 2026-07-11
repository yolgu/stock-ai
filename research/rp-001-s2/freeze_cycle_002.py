"""Freeze RP-001-S2 Cycle 002 before candidate performance evaluation."""

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
    "research/rp-001-s2/contracts/cycle-002-development-contract-v1.json"
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
        "cycle001Result": _verified(
            root,
            "research/rp-001-s2/evaluation-runs/S2-EVAL-20260711-001/result.json",
        ),
        "cycle001Decision": _verified(
            root,
            "research/rp-001-s2/cycle-decisions/cycle-001-decision.json",
        ),
        "cycle001AnalysisContract": _verified(
            root,
            "research/rp-001-s2/contracts/development-analysis-contract-v1.0.1.json",
        ),
        "candleManifest": _verified(
            root,
            "research/rp-001-s2/candle-runs/S2-CANDLE-20260711-001/manifest.json",
        ),
        "metadataSampleSelection": _verified(
            root,
            "research/rp-001-s2/metadata-runs/S2-META-20260711-002/sample-selection.json",
        ),
        "cycle002FormulaSource": _file(
            root, "research/rp-001-s2/src/rp001_s2/cycle002.py"
        ),
        "cycle002EvaluationSource": _file(
            root, "research/rp-001-s2/src/rp001_s2/cycle002_evaluation.py"
        ),
        "cycle002RunSource": _file(
            root, "research/rp-001-s2/src/rp001_s2/cycle002_run.py"
        ),
        "cycle002Tests": _file(
            root, "research/rp-001-s2/tests/test_cycle002.py"
        ),
        "cycle002Cli": _file(root, "run_s2_cycle_002.py"),
        "cycle002FreezeSource": _file(
            root, "research/rp-001-s2/freeze_cycle_002.py"
        ),
        "cycleControlSource": _file(
            root, "research/rp-001-s2/src/rp001_s2/cycle_control.py"
        ),
        "cycleControlTests": _file(
            root, "research/rp-001-s2/tests/test_cycle_control.py"
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
            "schemaVersion": "rp001-s2-cycle-002-development-contract.v1",
            "programId": "RP-001-S2",
            "cycleId": "RP-001-S2-CYCLE-002",
            "status": "development_authorized_confirmation_price_unopened",
            "frozenAt": frozen_at,
            "sampleRole": "seen_development_reused_for_internal_discovery",
            "eligibleForConfirmationEvidence": False,
            "usageScope": "research_only",
            "previousCycleResultInformedDesign": True,
            "cycle002LabelPrevalenceOpenedBeforeFreeze": True,
            "cycle002CandidatePerformanceOpenedBeforeFreeze": False,
            "confirmationPriceVolumeOpened": False,
            "confirmationReuseStatus": "not_used_price_unopened",
            "nextCycleOnFailure": "RP-001-S2-CYCLE-003",
            "estimand": {
                "id": "upside_price_regime_end_by_5_nonpositive_at_10",
                "class": "active_upside_regime_end_forecast",
                "claimLevel": "price_volume_regime_proxy_only",
                "humanPsychologyIdentified": False,
                "eligibleSignalState": "m5_native >= 1.0",
                "endSearchWindowSessions": 5,
                "primaryHorizonSessions": 10,
                "rollingEndStatistic": (
                    "e[t,k]=(ln(P_adj[t+k])-ln(P_adj[t+k-5]))/"
                    "(sqrt(5)*sigma_t)"
                ),
                "positiveLabel": (
                    "first k in 1..5 with e[t,k]<=0 exists and e[t,10]<=0"
                ),
                "futureUse": "adjusted future closes are used only in label construction",
            },
            "features": {
                "sharedMask": "41 PIT rows ending at t for every candidate and baseline",
                "base": "Cycle 001 native-return and turnover features",
                "activeDuration": (
                    "consecutive prior PIT states with m5_s>=1, capped at 20"
                ),
                "cumulativeRunup": (
                    "q=(ln(C_native_t)-ln(C_native_t-d))/(sqrt(d)*sigma_t)"
                ),
                "sourceBinding": "separate SHA-256 over every one of the 41 read rows",
                "availability": "official daily close usable next session",
            },
            "candidateFamilies": [
                {
                    "id": "rp001_s2.m2.tail_stretch_reversion.v1",
                    "mechanism": "multi-horizon tail stretch and mean reversion",
                    "basis": [
                        "H(m5;1,3)",
                        "H(m10;.5,3)",
                        "H(m20;0,3)",
                        "cuberoot(H(m5)*H(m10)*H(m20))",
                    ],
                },
                {
                    "id": "rp001_s2.m3.deceleration_distribution.v1",
                    "mechanism": "deceleration and turnover-confirmed distribution",
                    "basis": [
                        "H(-z1;0,2.5)",
                        "H(m10-m3;0,2.5)",
                        "H(-curvature;0,2.5)",
                        "cuberoot(H(-z1)*H(-curvature)*H(zv;0,3))",
                    ],
                },
                {
                    "id": "rp001_s2.m4.active_duration_hazard.v1",
                    "mechanism": "active-regime age and cumulative-runup duration hazard",
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
                "alarmThreshold": "type-7 Q0.90 of nested development OOF probability",
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
                "actionProxy": "hypothetical long exit at next-session close",
                "netBenefit": (
                    "-(P_adj[t+10]/P_adj[t+1]-1)-cost; never the long-entry return"
                ),
                "costsBps": [100.0, 300.0],
                "formalG8Status": (
                    "not_evaluated_action_execution_impact_and_capital_contract_absent"
                ),
                "portfolioMdd": "not_identifiable_no_capital_allocation",
            },
            "predecessorDiagnosis": {
                "cycle001CanonicalDispositions": {
                    "rp001_s2.m1.multi_horizon_trend.v1": "reject",
                    "rp001_s2.m2.acceleration_curvature.v1": "repair",
                    "rp001_s2.m1.volume_confirmed_gate.v1": "repair",
                },
                "cycle001FormalG8Status": "not_evaluated",
                "cycle001MddStatus": "descriptive_nonportfolio_order_dependent",
                "cycle001Transition": "CycleTerminal_to_RP-001-S2-CYCLE-002",
                "programTerminal": False,
            },
            "discoveryCoverageAfterExecution": {
                "empiricalCycleCount": 2,
                "candidateFormulaVersionCount": 6,
                "mechanismClasses": ["M1", "M2", "M3", "M4"],
            },
            "qualityEvidence": {
                "redToGreenTests": 10,
                "s2TestsPassed": 56,
                "s2TestsTotal": 56,
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
        "rp001_s2_cycle_002_development_frozen",
        {
            "contract": _binding(contract, root),
            "processedCandles": processed,
            "previousCycleResultInformedDesign": True,
            "cycle002CandidatePerformanceOpened": False,
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
