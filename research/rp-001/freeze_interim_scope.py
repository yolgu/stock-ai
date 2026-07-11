from __future__ import annotations

import argparse
import fcntl
import os
import re
import stat
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


SOURCE_DIRECTORY = Path(__file__).resolve().parent / "src"
sys.path.insert(0, str(SOURCE_DIRECTORY))

from rp001.local_evidence import (  # noqa: E402
    AppendOnlyLocalLedger,
    LocalArtifactStore,
    LocalEvidenceError,
    canonical_json_bytes,
    sha256_bytes,
)


SCOPE_SCHEMA_VERSION = "rp001-interim-execution-scope.v1"
PROGRAM_ID = "RP-001"
RESEARCH_ONLY_DECISION = "research_only"
DEFERRED_STATUS = "deferred_until_final_adoption"
DEFERRED_CAPABILITY_IDS = (
    "external_artifact_cas",
    "multi_anchor_signed_receipts",
    "third_party_identity_infrastructure",
    "global_six_digit_id_allocator",
    "sealed_full_cli",
    "final_evidence_decision_completion",
    "reproduction_rights_external_sink",
)
MUST_HOLD_QUALITY_RULE_IDS = (
    "predata_scope_and_analysis_plan_freeze",
    "no_future_input",
    "purged_walk_forward_embargo_terminal_holdout_identical_mask",
    "no_post_result_tuning",
    "same_fold_baseline_comparison",
    "all_terminal_run_outcomes_disclosed",
    "no_zero_neutral_or_reweight_missing_inputs",
    "canonical_json_sidecar_no_self_hash_append_only",
    "raw_processed_hashes_timestamps_and_lineage",
    "no_secret_persistence",
    "no_order_account_asset_api_or_operating_app_modification",
)
ALLOWED_PLAN_CHANGE_REASONS = (
    "leakage",
    "data_or_result_tampering",
    "secret_exposure",
    "formula_implementation_inequivalence",
    "statistical_test_changes_conclusion",
)
FORBIDDEN_API_FAMILIES = ("account", "asset", "order")
FREEZE_LOCK_FILENAME = ".freeze-interim-scope.lock"

_SHA256 = re.compile(r"[0-9a-f]{64}")


class FreezeInterimScopeError(ValueError):
    """Raised when the requested interim scope cannot be frozen safely."""


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Freeze the RP-001 local interim execution scope."
    )
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--frozen-at", required=True)
    parser.add_argument("--scope-output", required=True, type=Path)
    parser.add_argument("--ledger-directory", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    try:
        summary = freeze_interim_scope(arguments)
    except (FreezeInterimScopeError, LocalEvidenceError) as error:
        print(f"INVALID {error}", file=sys.stderr)
        return 1
    print(canonical_json_bytes(summary).decode("utf-8"))
    return 0


def freeze_interim_scope(arguments: argparse.Namespace) -> dict[str, object]:
    repository_root = _resolve_repository_root(arguments.repository_root)
    plan_path, plan_relative_path = _resolve_repository_path(
        repository_root,
        arguments.plan,
        "plan",
    )
    scope_path, scope_relative_path = _resolve_repository_path(
        repository_root,
        arguments.scope_output,
        "scope output",
    )
    ledger_directory, _ledger_relative_path = _resolve_repository_path(
        repository_root,
        arguments.ledger_directory,
        "ledger directory",
    )

    expected_plan_sha256 = _require_sha256(arguments.expected_plan_sha256)
    plan_sha256 = sha256_bytes(_read_plan_source(plan_path))
    if plan_sha256 != expected_plan_sha256:
        raise FreezeInterimScopeError("plan SHA-256 mismatch")

    scope = _build_scope(
        plan_relative_path,
        plan_sha256,
        arguments.frozen_at,
    )
    artifact_store = LocalArtifactStore(repository_root)
    ledger = AppendOnlyLocalLedger(ledger_directory)
    with _exclusive_freeze_lock(ledger_directory):
        ledger.require_empty()
        _require_scope_pair_absent(scope_path)
        scope_binding = artifact_store.publish_json(scope_path, scope)
        try:
            ledger_entry = ledger.append(
                event_type="interim_scope_frozen",
                payload={
                    "plan": {
                        "path": plan_relative_path,
                        "sha256": plan_sha256,
                    },
                    "scope": {
                        "path": scope_relative_path,
                        "sha256": scope_binding.artifact_sha256,
                    },
                },
                occurred_at=arguments.frozen_at,
            )
        except Exception as append_error:
            try:
                artifact_store.rollback_publication(scope_binding)
            except LocalEvidenceError as rollback_error:
                raise FreezeInterimScopeError(
                    "published scope changed; rollback refused"
                ) from rollback_error
            if isinstance(append_error, LocalEvidenceError):
                raise
            raise FreezeInterimScopeError(
                "failed to append scope freeze event"
            ) from append_error
    return {
        "deferredCapabilityCount": len(DEFERRED_CAPABILITY_IDS),
        "ledgerEntryCount": ledger_entry.sequence,
        "mustHoldQualityRuleCount": len(MUST_HOLD_QUALITY_RULE_IDS),
        "planSha256": plan_sha256,
        "recordSha256": ledger_entry.record_sha256,
        "scopeSha256": scope_binding.artifact_sha256,
    }


@contextmanager
def _exclusive_freeze_lock(ledger_directory: Path) -> Iterator[None]:
    directory_descriptor = _open_lock_directory(ledger_directory)
    lock_flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    try:
        try:
            lock_descriptor = os.open(
                FREEZE_LOCK_FILENAME,
                lock_flags,
                0o600,
                dir_fd=directory_descriptor,
            )
        except OSError as error:
            raise FreezeInterimScopeError(
                "freeze lock is unavailable"
            ) from error

        try:
            opened_lock_metadata = os.fstat(lock_descriptor)
            path_lock_metadata = os.stat(
                FREEZE_LOCK_FILENAME,
                dir_fd=directory_descriptor,
                follow_symlinks=False,
            )
            if (
                not stat.S_ISREG(opened_lock_metadata.st_mode)
                or not stat.S_ISREG(path_lock_metadata.st_mode)
                or not _same_file(opened_lock_metadata, path_lock_metadata)
            ):
                raise FreezeInterimScopeError(
                    "freeze lock must be a real regular file"
                )
        except BaseException:
            os.close(lock_descriptor)
            raise
    finally:
        os.close(directory_descriptor)

    try:
        fcntl.flock(lock_descriptor, fcntl.LOCK_EX)
    except OSError as error:
        os.close(lock_descriptor)
        raise FreezeInterimScopeError("failed to acquire freeze lock") from error
    try:
        yield
    finally:
        os.close(lock_descriptor)


def _open_lock_directory(ledger_directory: Path) -> int:
    try:
        ledger_directory.mkdir(parents=True, exist_ok=True)
        path_metadata = os.lstat(ledger_directory)
    except OSError as error:
        raise FreezeInterimScopeError(
            "ledger directory is unavailable"
        ) from error
    if not stat.S_ISDIR(path_metadata.st_mode):
        raise FreezeInterimScopeError(
            "ledger directory must be a real directory"
        )

    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(ledger_directory, flags)
    except OSError as error:
        raise FreezeInterimScopeError(
            "ledger directory is unavailable"
        ) from error
    try:
        opened_metadata = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(opened_metadata.st_mode)
            or not _same_file(path_metadata, opened_metadata)
        ):
            raise FreezeInterimScopeError(
                "ledger directory changed while being opened"
            )
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def _same_file(
    first: os.stat_result,
    second: os.stat_result,
) -> bool:
    return first.st_dev == second.st_dev and first.st_ino == second.st_ino


def _require_scope_pair_absent(scope_path: Path) -> None:
    sidecar_path = Path(f"{scope_path}.sha256")
    if os.path.lexists(scope_path) or os.path.lexists(sidecar_path):
        raise FreezeInterimScopeError("scope publication already exists")


def _build_scope(
    plan_relative_path: str,
    plan_sha256: str,
    frozen_at: str,
) -> dict[str, object]:
    return {
        "schemaVersion": SCOPE_SCHEMA_VERSION,
        "programId": PROGRAM_ID,
        "decision": RESEARCH_ONLY_DECISION,
        "frozenAt": frozen_at,
        "frozenPlan": {
            "path": plan_relative_path,
            "sha256": plan_sha256,
        },
        "mustHoldQualityRuleIds": list(MUST_HOLD_QUALITY_RULE_IDS),
        "deferredCapabilities": [
            {"id": capability_id, "status": DEFERRED_STATUS}
            for capability_id in DEFERRED_CAPABILITY_IDS
        ],
        "security": {
            "forbiddenApiFamilies": list(FORBIDDEN_API_FAMILIES),
            "operatingAppModificationProhibited": True,
        },
        "allowedPlanChangeReasons": list(ALLOWED_PLAN_CHANGE_REASONS),
    }


def _resolve_repository_root(path: Path) -> Path:
    try:
        repository_root = path.resolve(strict=True)
    except OSError as error:
        raise FreezeInterimScopeError("repository root is unavailable") from error
    if not repository_root.is_dir():
        raise FreezeInterimScopeError("repository root must be a directory")
    return repository_root


def _resolve_repository_path(
    repository_root: Path,
    requested_path: Path,
    label: str,
) -> tuple[Path, str]:
    candidate = requested_path if requested_path.is_absolute() else (
        repository_root / requested_path
    )
    try:
        resolved_path = candidate.resolve(strict=False)
        relative_path = resolved_path.relative_to(repository_root).as_posix()
    except (OSError, ValueError) as error:
        raise FreezeInterimScopeError(
            f"{label} must stay within the repository root"
        ) from error
    if relative_path == ".":
        raise FreezeInterimScopeError(f"{label} must name a repository child")
    return resolved_path, relative_path


def _require_sha256(value: str) -> str:
    if _SHA256.fullmatch(value) is None:
        raise FreezeInterimScopeError(
            "expected plan SHA-256 must be lowercase hexadecimal"
        )
    return value


def _read_plan_source(path: Path) -> bytes:
    if not path.is_file():
        raise FreezeInterimScopeError("plan must be a readable file")
    try:
        return path.read_bytes()
    except OSError as error:
        raise FreezeInterimScopeError("plan must be a readable file") from error


if __name__ == "__main__":
    raise SystemExit(main())
