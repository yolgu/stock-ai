"""Record Cycle 001 as terminal and immediately authorize the next cycle."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from rp001.local_evidence import (
    AppendOnlyLocalLedger,
    LocalArtifactBinding,
    LocalArtifactStore,
    canonical_json_bytes,
    sha256_bytes,
)
from rp001_s2.cycle_control import decide_development_cycle


_ROOT = Path("/Users/jik/Documents/stock-sub")
_RESULT = Path(
    "research/rp-001-s2/evaluation-runs/S2-EVAL-20260711-001/result.json"
)
_MANIFEST = Path(
    "research/rp-001-s2/evaluation-runs/S2-EVAL-20260711-001/manifest.json"
)
_DECISION = Path("research/rp-001-s2/cycle-decisions/cycle-001-decision.json")


def main() -> int:
    result = _verified_json(_ROOT, _RESULT)
    manifest = _verified_json(_ROOT, _MANIFEST)
    _verify_result_manifest_binding(manifest)
    decision = decide_development_cycle(result)
    occurred_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )
    artifact = LocalArtifactStore(_ROOT).publish_json(
        _ROOT / _DECISION,
        {
            "schemaVersion": "rp001-s2-cycle-decision.v1",
            "programId": "RP-001-S2",
            "recordedAt": occurred_at,
            **decision,
            "evidence": {
                "developmentResult": _binding_for_path(_ROOT, _RESULT),
                "developmentManifest": _binding_for_path(_ROOT, _MANIFEST),
            },
            "failureInterpretation": (
                "candidate failure closes this empirical cycle only; it does not "
                "establish ProgramTerminal"
            ),
        },
    )
    event = AppendOnlyLocalLedger(
        _ROOT / "research/rp-001-s2/local-ledgers/program"
    ).append(
        "rp001_s2_cycle_terminal_next_cycle_authorized",
        {
            "cycleId": decision["cycleId"],
            "cycleStatus": decision["cycleStatus"],
            "nextState": decision["nextState"],
            "programTerminal": False,
            "confirmationPriceVolumeOpened": False,
            "decision": _binding(artifact, _ROOT),
        },
        occurred_at,
    )
    print(
        json.dumps(
            {
                "status": decision["cycleStatus"],
                "nextState": decision["nextState"],
                "decisionSha256": artifact.artifact_sha256,
                "ledgerSha256": event.record_sha256,
            },
            separators=(",", ":"),
        )
    )
    return 0


def _verified_json(root: Path, relative: Path) -> dict[str, object]:
    path = root / relative
    source = path.read_bytes()
    digest = sha256_bytes(source)
    if Path(f"{path}.sha256").read_text(encoding="ascii") != f"{digest}\n":
        raise ValueError("evidence_sidecar_mismatch")
    value = json.loads(source.decode("utf-8"))
    if not isinstance(value, dict) or canonical_json_bytes(value) != source:
        raise ValueError("evidence_not_canonical")
    return value


def _verify_result_manifest_binding(manifest: dict[str, object]) -> None:
    artifacts = manifest.get("artifacts")
    expected = _binding_for_path(_ROOT, _RESULT)
    if not isinstance(artifacts, list) or expected not in artifacts:
        raise ValueError("result_manifest_binding_missing")


def _binding_for_path(root: Path, relative: Path) -> dict[str, str]:
    return {"path": relative.as_posix(), "sha256": sha256_bytes((root / relative).read_bytes())}


def _binding(value: LocalArtifactBinding, root: Path) -> dict[str, str]:
    path = value.path.relative_to(root) if value.path.is_absolute() else value.path
    return {"path": path.as_posix(), "sha256": value.artifact_sha256}


if __name__ == "__main__":
    sys.exit(main())
