"""Freeze the development-only candle scope after metadata selection."""

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


_DEVELOPMENT = ["BA", "MRK", "IBM", "PEP", "WMT", "UPS"]
_CONFIRMATION = ["LOW", "DIS", "GE", "MCD", "NFLX", "NKE"]
_CONTRACT_PATH = Path(
    "research/rp-001-s2/contracts/development-candle-contract-v1.json"
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", required=True, type=Path)
    values = parser.parse_args(argv)
    root = values.repository_root.absolute()
    frozen_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )
    selection = _verified_binding(
        root,
        "research/rp-001-s2/metadata-runs/S2-META-20260711-002/sample-selection.json",
    )
    manifest = _verified_binding(
        root,
        "research/rp-001-s2/metadata-runs/S2-META-20260711-002/manifest.json",
    )
    selected = json.loads((root / selection["path"]).read_text())
    if (
        selected.get("developmentSymbols") != _DEVELOPMENT
        or selected.get("confirmationSymbols") != _CONFIRMATION
    ):
        raise ValueError("metadata_selection_mismatch")
    bindings = {
        "merc": _verified_binding(
            root,
            "research/rp-001-s2/contracts/cycle-001-merc-v1.json",
        ),
        "metadataManifest": manifest,
        "metadataSelection": selection,
        "tossBoundarySource": _file_binding(
            root, "research/rp-001-s2/src/rp001_s2/toss_boundary.py"
        ),
        "tossBoundaryTests": _file_binding(
            root, "research/rp-001-s2/tests/test_toss_boundary.py"
        ),
        "candleRunSource": _file_binding(
            root, "research/rp-001-s2/src/rp001_s2/candle_run.py"
        ),
        "candleCli": _file_binding(
            root, "research/rp-001-s2/collect_development_candles.py"
        ),
        "collectorSource": _file_binding(
            root, "research/rp-001/src/rp001/toss_research_collector.py"
        ),
        "collectorTests": _file_binding(
            root, "research/rp-001/tests/test_toss_research_collector.py"
        ),
        "localEvidenceSource": _file_binding(
            root, "research/rp-001/src/rp001/local_evidence.py"
        ),
        "localEvidenceTests": _file_binding(
            root, "research/rp-001/tests/test_local_evidence_contract.py"
        ),
        "sensitivePolicySource": _file_binding(
            root, "research/rp-001/src/rp001/sensitive_value_policy.py"
        ),
        "sensitivePolicyTests": _file_binding(
            root, "research/rp-001/tests/test_sensitive_value_policy.py"
        ),
    }
    store = LocalArtifactStore(root)
    contract = store.publish_json(
        root / _CONTRACT_PATH,
        {
            "schemaVersion": "rp001-s2-development-candle-contract.v1",
            "programId": "RP-001-S2",
            "cycleId": "RP-001-S2-CYCLE-001",
            "status": "development_candles_authorized_confirmation_price_unopened",
            "frozenAt": frozen_at,
            "sampleRole": "seen_development_after_price_open",
            "developmentSymbols": _DEVELOPMENT,
            "confirmationSymbols": _CONFIRMATION,
            "confirmationPolicy": "price_unopened_until_formula_model_threshold_freeze",
            "period": {
                "startDate": "2023-01-03",
                "endDate": "2026-06-30",
                "inclusive": True,
                "interval": "1d",
                "timezone": "America/New_York",
                "initialBefore": "2026-07-01T00:00:00Z",
            },
            "allowedRequests": [
                {"method": "POST", "path": "/oauth2/token"},
                {"method": "GET", "path": "/api/v1/candles"},
            ],
            "credentialBoundary": "one_shot_process_environment_consumed_immediately",
            "ordersAccountsAssetsAllowed": False,
            "operationalDisposition": "NoTrade/no integration",
            "bindings": bindings,
        },
    )
    event = AppendOnlyLocalLedger(
        root / "research/rp-001-s2/local-ledgers/program"
    ).append(
        "rp001_s2_development_candle_scope_frozen",
        {
            "contract": _binding(contract, root),
            "developmentSymbols": _DEVELOPMENT,
            "confirmationSymbols": _CONFIRMATION,
            "confirmationPriceVolumeOpened": False,
            "ordersAccountsAssetsAllowed": False,
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


def _verified_binding(root: Path, relative: str) -> dict[str, str]:
    value = _file_binding(root, relative)
    sidecar = Path(f"{root / relative}.sha256").read_text(encoding="ascii")
    if sidecar != f"{value['sha256']}\n":
        raise ValueError("artifact_sidecar_mismatch")
    return value


def _file_binding(root: Path, relative: str) -> dict[str, str]:
    return {"path": relative, "sha256": sha256_bytes((root / relative).read_bytes())}


def _binding(value: LocalArtifactBinding, root: Path) -> dict[str, str]:
    path = value.path.relative_to(root) if value.path.is_absolute() else value.path
    return {"path": path.as_posix(), "sha256": value.artifact_sha256}


if __name__ == "__main__":
    sys.exit(main())
