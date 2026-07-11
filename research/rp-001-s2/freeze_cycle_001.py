"""Freeze the minimum execution contract for RP-001-S2 cycle 001."""

from __future__ import annotations

import argparse
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
from rp001_s2.sample_design import (
    CANDIDATE_POOL,
    EXPOSED_SYMBOLS,
    EXPOSURE_EVIDENCE,
    SEED_SHA256,
    SEED_TEXT,
)


_PROGRAM_ID = "RP-001-S2"
_CYCLE_ID = "RP-001-S2-CYCLE-001"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--frozen-at")
    values = parser.parse_args(argv)
    root = values.repository_root.absolute()
    frozen_at = values.frozen_at or datetime.now(timezone.utc).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")
    store = LocalArtifactStore(root)
    ledger_parent = root / "research/rp-001-s2/local-ledgers"
    store.ensure_directory(ledger_parent)
    ledger = AppendOnlyLocalLedger(ledger_parent / "program")
    predecessor = _predecessor_bindings(root)
    implementation = _implementation_bindings(root)
    contract_directory = root / "research/rp-001-s2/contracts"

    merc = store.publish_json(
        contract_directory / "cycle-001-merc-v1.json",
        _merc_body(frozen_at, predecessor, implementation),
    )
    sample = store.publish_json(
        contract_directory / "metadata-sample-design-v1.json",
        _sample_body(frozen_at, merc, root),
    )
    source = store.publish_json(
        contract_directory / "read-only-source-contract-v1.json",
        _source_body(frozen_at, merc, sample, implementation, root),
    )
    event = ledger.append(
        "rp001_s2_cycle_001_merc_frozen",
        {
            "programId": _PROGRAM_ID,
            "cycleId": _CYCLE_ID,
            "merc": _binding(merc, root),
            "metadataSampleDesign": _binding(sample, root),
            "readOnlySourceContract": _binding(source, root),
            "predecessorArtifactsRemainImmutable": True,
            "priceVolumeOpened": False,
            "ordersAccountsAssetsAllowed": False,
        },
        frozen_at,
    )
    print(
        json.dumps(
            {
                "status": "frozen",
                "mercSha256": merc.artifact_sha256,
                "sampleDesignSha256": sample.artifact_sha256,
                "sourceContractSha256": source.artifact_sha256,
                "ledgerEventSha256": event.record_sha256,
            },
            separators=(",", ":"),
        )
    )
    return 0


def _merc_body(
    frozen_at: str,
    predecessor: dict[str, dict[str, str]],
    implementation: dict[str, dict[str, str]],
) -> dict[str, object]:
    return {
        "schemaVersion": "rp001-s2-merc.v1",
        "programId": _PROGRAM_ID,
        "cycleId": _CYCLE_ID,
        "protocolVersion": "1.0.0",
        "status": "frozen_before_metadata_and_price_open",
        "frozenAt": frozen_at,
        "usageScope": "research_only",
        "operationalDisposition": "NoTrade/no integration",
        "predecessorEvidence": predecessor,
        "question": (
            "Can point-in-time native price and volume mechanisms forecast an "
            "observable upside-price onset within five sessions that remains "
            "positive at session ten?"
        ),
        "estimand": {
            "id": "upside_price_regime_onset_by_5_persistent_at_10",
            "class": "onset_forecast",
            "primaryHorizonSessions": 10,
            "onsetSearchWindowSessions": 5,
            "claimLevel": "price_volume_regime_proxy_only",
            "humanPsychologyIdentified": False,
            "eligibleSignalState": "m5_native < 1.0",
            "positiveLabel": (
                "first k in 1..5 with (ln(P_adj[t+k])-ln(P_adj[t]))/sigma_t "
                ">=2 and g_10>=1"
            ),
            "futureUse": "adjusted future closes are used only in label construction",
        },
        "features": {
            "priceInput": "native_unadjusted_close",
            "turnoverInput": "ln(native_close)+ln(native_volume)",
            "returnScale": "1.4826*MAD(native_log_returns[t-20:t-1])",
            "turnoverScale": "1.4826*MAD(log_turnover[t-20:t-1])",
            "basisInputs": [
                "z1",
                "m3",
                "m5",
                "m10",
                "m20",
                "trend_consistency_10",
                "acceleration_3_vs_10",
                "return_curvature",
                "turnover_surprise",
            ],
            "availability": "official daily close usable next session",
            "providerRevisionAndPublication": "not_documented_research_only_limitation",
        },
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
        "candidateFamilies": [
            {
                "id": "rp001_s2.m1.multi_horizon_trend.v1",
                "mechanism": "multi-horizon trend persistence with turnover confirmation",
                "basis": [
                    "H(m3;.25,2.5)",
                    "H(m10;.25,2.5)",
                    "H(positive_share_10;.5,.9)",
                    "H(zv;0,3)",
                ],
            },
            {
                "id": "rp001_s2.m2.acceleration_curvature.v1",
                "mechanism": "recent return acceleration and curvature with turnover",
                "basis": [
                    "H(m3-m10;0,2)",
                    "H(curvature;0,2)",
                    "H(zv;0,3)",
                    "H(m3-m10;0,2)*H(curvature;0,2)",
                ],
            },
            {
                "id": "rp001_s2.m1.volume_confirmed_gate.v1",
                "mechanism": "every trend or shock path is gated by turnover surprise",
                "basis": [
                    "sqrt(H(m5;.25,2.5)*H(zv;0,3))",
                    "sqrt(H(z1;.25,2.5)*H(zv;0,3))",
                    "cuberoot(H(m10;.25,2.5)*H(positive_share_10;.5,.9)*H(zv;0,3))",
                ],
            },
        ],
        "probabilityModel": {
            "formula": "sigmoid(alpha + sum_j beta_j*basis_j)",
            "constraint": "beta_j>=0",
            "fit": "active-set Newton ridge logistic; both outcome classes required",
            "l2Grid": [0.01, 0.1, 1.0, 10.0],
            "selection": "inner purged OOF pooled Brier minimum; larger lambda on exact tie",
            "convergence": "normalized KKT residual <=1e-6 or run invalid",
        },
        "validation": {
            "outer": {
                "minimumTrainingSessions": 252,
                "purgeSessions": 10,
                "validationSessions": 63,
                "embargoSessions": 10,
                "mode": "expanding_walk_forward",
            },
            "inner": {
                "minimumTrainingSessions": 126,
                "purgeSessions": 10,
                "validationSessions": 42,
                "embargoSessions": 10,
                "mode": "expanding_walk_forward",
            },
            "sameEligibleRowMask": True,
            "alarmThreshold": "type-7 Q0.90 of nested development OOF probability",
            "seed": 20260711,
            "blockBootstrap": {
                "replicates": 2000,
                "blockLengthSessions": 20,
                "method": "synchronized_studentized_maxT",
                "contrastCount": 6,
            },
            "primaryMetric": "Brier improvement over each of two baselines",
            "minimumEffectDelta": 0.005,
            "gate": "both simultaneous 95% lower bounds exceed 0.005",
        },
        "inputContracts": {
            "missing": "abstain; no zero fill; no reweight",
            "outOfDomain": "abstain outside closed standardized [-8,8]",
            "constantSeries": "abstain if MAD scale <1e-6",
            "corporateAction": "abstain if any native window return magnitude >=ln(1.35)",
            "sessionOrder": "strictly increasing unique ISO session dates",
            "modelFamily": "basis, training rows, and model must share exact Formula ID",
        },
        "sampleRoles": {
            "predecessor": "seen_development",
            "metadataRun": "metadata_only",
            "firstSelectedSix": "seen_development_after_price_open",
            "nextSelectedSix": "unseen_historical_confirmation_until_formula_freeze",
            "confirmationReuse": "forbidden",
        },
        "period": {
            "startDate": "2023-01-03",
            "endDate": "2026-06-30",
            "inclusive": True,
            "interval": "1d",
            "timezone": "America/New_York",
            "inference": "cross_symbol_historical_replication_in_same_market_era",
        },
        "costs": [
            {"id": "baseline_100bps", "totalBps": 100.0},
            {"id": "stress_300bps", "totalBps": 300.0},
        ],
        "economics": {
            "signalEntry": "next-session close hypothetical only",
            "exit": "session-ten close hypothetical only",
            "overlap": "one closed interval per symbol",
            "zeroTrades": "returns_and_tail_risk_not_estimable",
            "actualOrders": False,
        },
        "failureDisclosure": [
            "all candidate attempts and selected lambdas",
            "invalid folds and convergence failures",
            "missing, OOD, corporate-action, and label exclusions",
            "all symbols including adverse results",
            "zero alarms and zero trades as not_estimable economics",
        ],
        "implementationBindings": implementation,
        "qualityEvidence": {
            "s2TestsPassed": 42,
            "s2TestsTotal": 42,
            "verificationCommand": (
                "PYTHONDONTWRITEBYTECODE=1 "
                "PYTHONPATH=research/rp-001-s2/src:research/rp-001/src "
                "<bundled-python> -m unittest discover -s research/rp-001-s2/tests"
            ),
        },
        "deferredUntilFinalAdoption": [
            "external_CAS",
            "signed_multi_anchor_receipts",
            "third_party_identity_infrastructure",
            "global_ID_allocator",
            "external_reproduction_sink",
        ],
    }


def _sample_body(
    frozen_at: str,
    merc: LocalArtifactBinding,
    root: Path,
) -> dict[str, object]:
    return {
        "schemaVersion": "rp001-s2-metadata-sample-design.v1",
        "programId": _PROGRAM_ID,
        "cycleId": _CYCLE_ID,
        "status": "frozen_before_metadata_open",
        "frozenAt": frozen_at,
        "merc": _binding(merc, root),
        "candidatePool": list(CANDIDATE_POOL),
        "permanentlyExcludedSymbols": list(EXPOSED_SYMBOLS),
        "exposureEvidence": [
            {"path": path, "sha256": sha256}
            for path, sha256 in EXPOSURE_EVIDENCE
        ],
        "metadataProjection": [
            "symbol",
            "name",
            "englishName",
            "isinCode",
            "market",
            "securityType",
            "isCommonShare",
            "status",
            "currency",
            "sharesOutstanding",
        ],
        "unregisteredMetadataFields": "reject",
        "eligibility": {
            "status": "ACTIVE",
            "isCommonShare": True,
            "currency": "USD",
            "markets": ["NASDAQ", "NYSE", "AMEX"],
            "securityTypes": ["STOCK", "FOREIGN_STOCK"],
            "uniqueIsinRequired": True,
        },
        "ranking": {
            "seedText": SEED_TEXT,
            "seedSha256": SEED_SHA256,
            "algorithm": "sha256(seed_sha256 + ':' + symbol), then symbol",
            "development": "first six eligible",
            "confirmation": "next six eligible",
            "minimumEligible": 12,
            "replacementAfterPriceOpen": "forbidden",
        },
        "period": {
            "startDate": "2023-01-03",
            "endDate": "2026-06-30",
            "inclusive": True,
            "interval": "1d",
            "timezone": "America/New_York",
        },
        "survivorshipScope": "conditional_on_metadata_observed_2026-07-11",
        "priceOpenOrder": "development_before_confirmation",
        "ordersAccountsAssetsAllowed": False,
    }


def _source_body(
    frozen_at: str,
    merc: LocalArtifactBinding,
    sample: LocalArtifactBinding,
    implementation: dict[str, dict[str, str]],
    root: Path,
) -> dict[str, object]:
    return {
        "schemaVersion": "rp001-s2-read-only-source-contract.v1",
        "programId": _PROGRAM_ID,
        "cycleId": _CYCLE_ID,
        "status": "metadata_only_authorized_price_unopened",
        "frozenAt": frozen_at,
        "candidatePool": list(CANDIDATE_POOL),
        "allowedRequests": [
            {"method": "POST", "path": "/oauth2/token"},
            {"method": "GET", "path": "/api/v1/stocks"},
        ],
        "forbiddenRequestFamilies": [
            "orders",
            "order_changes",
            "order_cancellations",
            "accounts",
            "balances",
            "assets",
            "candles_before_development_freeze",
            "trades",
            "orderbook",
        ],
        "ordersAccountsAssetsAllowed": False,
        "credentialBoundary": {
            "input": "one_shot_process_environment",
            "variableNames": ["TOSS_CLIENT_ID", "TOSS_CLIENT_SECRET"],
            "consumeImmediately": True,
            "commandLineValues": "forbidden",
            "persistenceInArtifactsLogsOrManifest": "forbidden",
            "oauthTokenPersistence": "forbidden",
        },
        "merc": _binding(merc, root),
        "metadataSampleDesign": _binding(sample, root),
        "implementationBindings": implementation,
        "outputRoot": "research/rp-001-s2/metadata-runs",
        "ledgerPath": "research/rp-001-s2/local-ledgers/program",
    }


def _predecessor_bindings(root: Path) -> dict[str, dict[str, str]]:
    paths = {
        "decision": "research/rp-001/final/DR-002-no-adoptable-formula.json",
        "completion": "research/rp-001/final/PC-001-program-completion.json",
        "evaluation": "research/rp-001/evaluation-runs/RP001-EVAL-20260711-001/result.json",
        "formulaContract": "research/rp-001/contracts/interim-formula-contract-v1.0.1.json",
    }
    return {
        role: _file_binding(root, path)
        for role, path in paths.items()
    }


def _implementation_bindings(root: Path) -> dict[str, dict[str, str]]:
    paths = {
        "formulaSource": "research/rp-001-s2/src/rp001_s2/discovery.py",
        "formulaTests": "research/rp-001-s2/tests/test_discovery.py",
        "sampleSource": "research/rp-001-s2/src/rp001_s2/sample_design.py",
        "sampleTests": "research/rp-001-s2/tests/test_sample_design.py",
        "tossBoundarySource": "research/rp-001-s2/src/rp001_s2/toss_boundary.py",
        "tossBoundaryTests": "research/rp-001-s2/tests/test_toss_boundary.py",
        "metadataRunSource": "research/rp-001-s2/src/rp001_s2/metadata_run.py",
        "metadataRunTests": "research/rp-001-s2/tests/test_metadata_run.py",
        "metadataCli": "research/rp-001-s2/collect_metadata.py",
        "evaluationSource": "research/rp-001-s2/src/rp001_s2/evaluation.py",
        "evaluationTests": "research/rp-001-s2/tests/test_evaluation.py",
        "collectorSource": "research/rp-001/src/rp001/toss_research_collector.py",
        "collectorTests": "research/rp-001/tests/test_toss_research_collector.py",
        "sensitivePolicySource": "research/rp-001/src/rp001/sensitive_value_policy.py",
        "sensitivePolicyTests": "research/rp-001/tests/test_sensitive_value_policy.py",
        "localEvidenceSource": "research/rp-001/src/rp001/local_evidence.py",
        "localEvidenceTests": "research/rp-001/tests/test_local_evidence_contract.py",
    }
    return {
        role: _file_binding(root, path)
        for role, path in paths.items()
    }


def _file_binding(root: Path, relative_path: str) -> dict[str, str]:
    source = (root / relative_path).read_bytes()
    return {"path": relative_path, "sha256": sha256_bytes(source)}


def _binding(binding: LocalArtifactBinding, root: Path) -> dict[str, str]:
    path = binding.path.relative_to(root) if binding.path.is_absolute() else binding.path
    return {"path": path.as_posix(), "sha256": binding.artifact_sha256}


if __name__ == "__main__":
    sys.exit(main())
