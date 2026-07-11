from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import patch

from rp001.local_evidence import (
    AppendOnlyLocalLedger,
    LocalArtifactStore,
    canonical_json_bytes,
    sha256_bytes,
)
from rp001.sensitive_value_policy import find_sensitive_values


RP001_DIRECTORY = Path(__file__).resolve().parents[1]
FREEZE_SCRIPT_PATH = RP001_DIRECTORY / "freeze_interim_scope.py"
LEDGER_SCHEMA_VERSION = "rp001-local-ledger-entry.v1"
SCOPE_SCHEMA_VERSION = "rp001-interim-execution-scope.v1"
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
OWN_HASH_KEYS = frozenset(
    {
        "artifactSha256",
        "selfSha256",
        "recordSha256",
    }
)


def load_json_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError(f"expected JSON object: {path}")
    return cast(dict[str, object], value)


def assert_no_own_hash_keys(
    test_case: unittest.TestCase,
    value: object,
) -> None:
    if isinstance(value, dict):
        test_case.assertTrue(OWN_HASH_KEYS.isdisjoint(value))
        for nested_value in value.values():
            assert_no_own_hash_keys(test_case, nested_value)
    elif isinstance(value, list):
        for nested_value in value:
            assert_no_own_hash_keys(test_case, nested_value)


class CanonicalJsonContractTest(unittest.TestCase):
    def test_canonical_json_bytes_uses_exact_utf8_contract_without_trailing_lf(
        self,
    ) -> None:
        value = {
            "z": [3, {"한글": "값"}],
            "a": {"beta": False, "alpha": None},
        }

        source = canonical_json_bytes(value)

        self.assertEqual(
            source,
            '{"a":{"alpha":null,"beta":false},"z":[3,{"한글":"값"}]}'
            .encode("utf-8"),
        )
        self.assertFalse(source.endswith(b"\n"))

    def test_canonical_json_bytes_rejects_non_finite_numbers(self) -> None:
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    canonical_json_bytes({"value": value})

    def test_sha256_bytes_hashes_exact_source_bytes(self) -> None:
        source = "정규 바이트".encode("utf-8")

        self.assertEqual(
            sha256_bytes(source),
            hashlib.sha256(source).hexdigest(),
        )


class LocalArtifactStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name).resolve()
        self.store = LocalArtifactStore(self.root)

    def test_trusted_root_rejects_ancestor_symlink_without_external_writes(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as external_directory_name:
            trusted_root = self.root.resolve()
            external = Path(external_directory_name).resolve()
            alias = trusted_root / "alias"
            alias.symlink_to(external, target_is_directory=True)
            store = LocalArtifactStore(trusted_root)

            with self.assertRaises(ValueError):
                store.publish_json(alias / "artifact.json", {"safe": True})

            self.assertEqual((), tuple(external.iterdir()))

    def test_directory_swap_during_publish_never_writes_outside_trusted_root(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as external_directory_name:
            trusted_root = self.root.resolve()
            external = Path(external_directory_name).resolve()
            destination_parent = trusted_root / "destination"
            detached_parent = trusted_root / "detached"
            destination_parent.mkdir()
            store = LocalArtifactStore(trusted_root)
            original_link = os.link
            swapped = False

            def swap_then_link(*args: object, **kwargs: object) -> None:
                nonlocal swapped
                if not swapped:
                    destination_parent.rename(detached_parent)
                    destination_parent.symlink_to(external, target_is_directory=True)
                    swapped = True
                original_link(*args, **kwargs)

            with (
                patch("rp001.local_evidence.os.link", side_effect=swap_then_link),
                self.assertRaises(ValueError),
            ):
                store.publish_json(
                    destination_parent / "artifact.json",
                    {"safe": True},
                )

            self.assertEqual((), tuple(external.iterdir()))
            self.assertFalse((detached_parent / "artifact.json").exists())
            self.assertFalse((detached_parent / "artifact.json.sha256").exists())

    def test_link_failure_with_cleanup_failure_never_leaves_body_without_sidecar(
        self,
    ) -> None:
        path = self.root / "cleanup-failure.json"
        original_link = os.link
        original_unlink = os.unlink
        link_count = 0

        def fail_second_link(*args: object, **kwargs: object) -> None:
            nonlocal link_count
            link_count += 1
            if link_count == 2:
                raise OSError("injected second link failure")
            original_link(*args, **kwargs)

        def fail_published_cleanup(
            name: str,
            *args: object,
            **kwargs: object,
        ) -> None:
            if name in {path.name, f"{path.name}.sha256"}:
                raise OSError("injected published cleanup failure")
            original_unlink(name, *args, **kwargs)

        with (
            patch("rp001.local_evidence.os.link", side_effect=fail_second_link),
            patch(
                "rp001.local_evidence.os.unlink",
                side_effect=fail_published_cleanup,
            ),
            self.assertRaises(ValueError) as raised,
        ):
            self.store.publish_json(path, {"safe": True})

        self.assertIn("clean", str(raised.exception))
        self.assertFalse(path.exists())

    def test_post_link_failure_preserves_sidecar_when_body_cleanup_fails(
        self,
    ) -> None:
        path = self.root / "post-link-failure.json"
        sidecar_path = Path(f"{path}.sha256")
        original_fsync = os.fsync
        original_unlink = os.unlink
        fsync_count = 0

        def fail_directory_fsync(descriptor: int) -> None:
            nonlocal fsync_count
            fsync_count += 1
            if fsync_count == 3:
                raise OSError("injected post-link fsync failure")
            original_fsync(descriptor)

        def fail_body_cleanup(
            name: str,
            *args: object,
            **kwargs: object,
        ) -> None:
            if name == path.name:
                raise OSError("injected body cleanup failure")
            original_unlink(name, *args, **kwargs)

        with (
            patch("rp001.local_evidence.os.fsync", side_effect=fail_directory_fsync),
            patch("rp001.local_evidence.os.unlink", side_effect=fail_body_cleanup),
            self.assertRaises(ValueError),
        ):
            self.store.publish_json(path, {"safe": True})

        self.assertTrue(path.exists())
        self.assertTrue(sidecar_path.exists())

    def test_rollback_preserves_sidecar_when_body_unlink_fails(self) -> None:
        path = self.root / "rollback-failure.json"
        sidecar_path = Path(f"{path}.sha256")
        binding = self.store.publish_json(path, {"safe": True})
        original_unlink = os.unlink

        def fail_body_unlink(
            name: str,
            *args: object,
            **kwargs: object,
        ) -> None:
            if name == path.name:
                raise OSError("injected body rollback failure")
            original_unlink(name, *args, **kwargs)

        with (
            patch("rp001.local_evidence.os.unlink", side_effect=fail_body_unlink),
            self.assertRaises(ValueError),
        ):
            self.store.rollback_publication(binding)

        self.assertTrue(path.exists())
        self.assertTrue(sidecar_path.exists())

    def test_publish_json_writes_canonical_body_and_lowercase_hash_sidecar(
        self,
    ) -> None:
        path = self.root / "nested" / "scope.json"
        value = {"schemaVersion": "example.v1", "한글": ["값"]}

        binding = self.store.publish_json(path, value)

        expected_source = canonical_json_bytes(value)
        expected_sha256 = sha256_bytes(expected_source)
        self.assertEqual(path.read_bytes(), expected_source)
        self.assertEqual(
            Path(f"{path}.sha256").read_bytes(),
            f"{expected_sha256}\n".encode("ascii"),
        )
        self.assertEqual(binding.path, path)
        self.assertEqual(binding.sidecar_path, Path(f"{path}.sha256"))
        self.assertEqual(binding.artifact_sha256, expected_sha256)

    def test_publish_json_rejects_existing_body_without_overwrite(self) -> None:
        path = self.root / "scope.json"
        original_source = b"existing-body"
        path.write_bytes(original_source)

        with self.assertRaises(ValueError):
            self.store.publish_json(path, {"replacement": True})

        self.assertEqual(path.read_bytes(), original_source)
        self.assertFalse(Path(f"{path}.sha256").exists())

    def test_publish_json_rejects_existing_sidecar_without_overwrite(self) -> None:
        path = self.root / "scope.json"
        sidecar_path = Path(f"{path}.sha256")
        original_source = b"0" * 64 + b"\n"
        sidecar_path.write_bytes(original_source)

        with self.assertRaises(ValueError):
            self.store.publish_json(path, {"replacement": True})

        self.assertFalse(path.exists())
        self.assertEqual(sidecar_path.read_bytes(), original_source)

    def test_publish_json_rejects_exact_own_hash_keys_at_any_depth(self) -> None:
        fixtures = (
            {"artifactSha256": "a" * 64},
            {"nested": [{"selfSha256": "b" * 64}]},
            {"nested": {"deeper": {"recordSha256": "c" * 64}}},
        )

        for index, value in enumerate(fixtures):
            with self.subTest(index=index):
                path = self.root / f"forbidden-{index}.json"
                with self.assertRaises(ValueError):
                    self.store.publish_json(path, value)
                self.assertFalse(path.exists())
                self.assertFalse(Path(f"{path}.sha256").exists())

    def test_publish_json_permits_predecessor_plan_and_scope_hashes(self) -> None:
        path = self.root / "allowed-hashes.json"
        value = {
            "planSha256": "a" * 64,
            "previousRecordSha256": "b" * 64,
            "scopeSha256": "c" * 64,
        }

        self.store.publish_json(path, value)

        self.assertEqual(load_json_object(path), value)

    def test_publish_json_rejects_sensitive_text_without_returning_plaintext(
        self,
    ) -> None:
        path = self.root / "sensitive.json"
        sensitive_text = "client_" + "secret = " + "SyntheticValue_12345"

        with self.assertRaises(ValueError) as caught:
            self.store.publish_json(path, {"description": sensitive_text})

        self.assertNotIn(sensitive_text, str(caught.exception))
        self.assertFalse(path.exists())
        self.assertFalse(Path(f"{path}.sha256").exists())


class AppendOnlyLocalLedgerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name).resolve()
        self.ledger_directory = self.root / "ledger"
        self.events_directory = self.ledger_directory / "events"
        self.ledger = AppendOnlyLocalLedger(self.ledger_directory)

    def test_transaction_holds_exclusive_events_directory_lock(self) -> None:
        self.ledger.append("first", {}, "2026-07-11T12:00:00+09:00")
        contender = AppendOnlyLocalLedger(self.ledger_directory)
        started = threading.Event()
        completed = threading.Event()
        errors: list[BaseException] = []

        def append_contender() -> None:
            started.set()
            try:
                contender.append("second", {}, "2026-07-11T12:01:00+09:00")
            except BaseException as error:
                errors.append(error)
            finally:
                completed.set()

        with self.ledger.transaction() as transaction:
            state = transaction.validate()
            self.assertEqual(1, state.sequence)
            worker = threading.Thread(target=append_contender)
            worker.start()
            self.assertTrue(started.wait(1.0))
            self.assertFalse(completed.wait(0.1))
        worker.join(timeout=2.0)

        self.assertFalse(worker.is_alive())
        self.assertEqual([], errors)
        self.assertTrue(completed.is_set())
        self.assertTrue((self.events_directory / "000002.json").is_file())

    def test_append_revalidates_chain_after_validate_before_publish_tamper(
        self,
    ) -> None:
        first = self.ledger.append(
            "first",
            {},
            "2026-07-11T12:00:00+09:00",
        )
        original_validate = AppendOnlyLocalLedger._validate_existing_entries
        tampered = False

        def validate_then_tamper(
            ledger: AppendOnlyLocalLedger,
            events_identity: object,
        ) -> tuple[int, str | None]:
            nonlocal tampered
            state = original_validate(ledger, events_identity)
            if ledger is self.ledger and state[0] == 1 and not tampered:
                record = load_json_object(first.path)
                record["eventType"] = "tampered"
                source = canonical_json_bytes(record)
                first.path.write_bytes(source)
                first.sidecar_path.write_bytes(
                    f"{sha256_bytes(source)}\n".encode("ascii")
                )
                tampered = True
            return state

        with (
            patch.object(
                AppendOnlyLocalLedger,
                "_validate_existing_entries",
                new=validate_then_tamper,
            ),
            self.assertRaises(ValueError),
        ):
            self.ledger.append(
                "second",
                {},
                "2026-07-11T12:01:00+09:00",
            )

        self.assertTrue((self.events_directory / "000002.json").is_file())

    def test_append_revalidates_full_chain_after_event_publication(self) -> None:
        first = self.ledger.append(
            "first",
            {},
            "2026-07-11T12:00:00+09:00",
        )
        original_publish = self.ledger._store.publish_json

        def publish_then_tamper(
            path: Path,
            value: Mapping[str, object],
        ) -> object:
            binding = original_publish(path, value)
            if path.name == "000002.json":
                record = load_json_object(first.path)
                record["eventType"] = "tampered"
                source = canonical_json_bytes(record)
                first.path.write_bytes(source)
                first.sidecar_path.write_bytes(
                    f"{sha256_bytes(source)}\n".encode("ascii")
                )
            return binding

        with (
            patch.object(
                self.ledger._store,
                "publish_json",
                side_effect=publish_then_tamper,
            ),
            self.assertRaises(ValueError),
        ):
            self.ledger.append(
                "second",
                {},
                "2026-07-11T12:01:00+09:00",
            )

        self.assertTrue((self.events_directory / "000002.json").is_file())

    def test_append_rejects_symlinked_events_directory_without_external_writes(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as external_directory_name:
            external_directory = Path(external_directory_name)
            self.ledger_directory.mkdir(parents=True)
            self.events_directory.symlink_to(
                external_directory,
                target_is_directory=True,
            )

            with self.assertRaises(ValueError):
                self.ledger.append(
                    "scope_frozen",
                    {"scopeSha256": "a" * 64},
                    "2026-07-11T12:00:00+09:00",
                )

            self.assertEqual(tuple(external_directory.iterdir()), ())

    def test_append_rejects_symlinked_existing_body_or_sidecar(self) -> None:
        outcomes: list[tuple[str, bool, bool, bool, bool]] = []
        for linked_role in ("body", "sidecar"):
            with (
                tempfile.TemporaryDirectory() as ledger_root_name,
                tempfile.TemporaryDirectory() as external_directory_name,
            ):
                ledger_root = Path(ledger_root_name).resolve()
                ledger = AppendOnlyLocalLedger(ledger_root / "ledger")
                first_entry = ledger.append(
                    "scope_frozen",
                    {"scopeSha256": "a" * 64},
                    "2026-07-11T12:00:00+09:00",
                )
                linked_path = (
                    first_entry.path
                    if linked_role == "body"
                    else first_entry.sidecar_path
                )
                external_target = Path(external_directory_name) / linked_path.name
                linked_path.replace(external_target)
                linked_path.symlink_to(external_target)
                original_external_source = external_target.read_bytes()

                rejected = False
                try:
                    ledger.append(
                        "second_event",
                        {"scopeSha256": "b" * 64},
                        "2026-07-11T12:01:00+09:00",
                    )
                except ValueError:
                    rejected = True

                events_directory = ledger_root / "ledger" / "events"
                outcomes.append(
                    (
                        linked_role,
                        rejected,
                        external_target.read_bytes() == original_external_source,
                        not (events_directory / "000002.json").exists(),
                        not (events_directory / "000002.json.sha256").exists(),
                    )
                )

        self.assertEqual(
            outcomes,
            [
                ("body", True, True, True, True),
                ("sidecar", True, True, True, True),
            ],
        )

    def test_append_writes_exact_records_and_chains_predecessor_hash(self) -> None:
        first_entry = self.ledger.append(
            "interim_scope_frozen",
            {"scopePath": "evidence/scope.json", "scopeSha256": "a" * 64},
            "2026-07-11T12:00:00+09:00",
        )
        second_entry = self.ledger.append(
            "plan_verified",
            {"planPath": "plans/interim.md", "planSha256": "b" * 64},
            "2026-07-11T12:01:00+09:00",
        )

        first_path = self.events_directory / "000001.json"
        second_path = self.events_directory / "000002.json"
        first_record = load_json_object(first_path)
        second_record = load_json_object(second_path)
        expected_first = {
            "schemaVersion": LEDGER_SCHEMA_VERSION,
            "eventType": "interim_scope_frozen",
            "occurredAt": "2026-07-11T12:00:00+09:00",
            "payload": {
                "scopePath": "evidence/scope.json",
                "scopeSha256": "a" * 64,
            },
            "previousRecordSha256": None,
            "sequence": 1,
        }
        first_sha256 = sha256_bytes(canonical_json_bytes(expected_first))
        expected_second = {
            "schemaVersion": LEDGER_SCHEMA_VERSION,
            "eventType": "plan_verified",
            "occurredAt": "2026-07-11T12:01:00+09:00",
            "payload": {
                "planPath": "plans/interim.md",
                "planSha256": "b" * 64,
            },
            "previousRecordSha256": first_sha256,
            "sequence": 2,
        }
        second_sha256 = sha256_bytes(canonical_json_bytes(expected_second))

        self.assertEqual(first_record, expected_first)
        self.assertEqual(second_record, expected_second)
        self.assertEqual(first_path.read_bytes(), canonical_json_bytes(expected_first))
        self.assertEqual(second_path.read_bytes(), canonical_json_bytes(expected_second))
        self.assertEqual(
            Path(f"{first_path}.sha256").read_bytes(),
            f"{first_sha256}\n".encode("ascii"),
        )
        self.assertEqual(
            Path(f"{second_path}.sha256").read_bytes(),
            f"{second_sha256}\n".encode("ascii"),
        )
        self.assertEqual(first_entry.sequence, 1)
        self.assertEqual(first_entry.path, first_path)
        self.assertEqual(first_entry.record_sha256, first_sha256)
        self.assertEqual(second_entry.sequence, 2)
        self.assertEqual(second_entry.record_sha256, second_sha256)
        assert_no_own_hash_keys(self, first_record)
        assert_no_own_hash_keys(self, second_record)

    def test_append_rejects_tampered_body_and_preserves_prior_events(self) -> None:
        entry = self.ledger.append(
            "scope_frozen",
            {"scopeSha256": "a" * 64},
            "2026-07-11T12:00:00+09:00",
        )
        entry.path.write_bytes(canonical_json_bytes({"tampered": True}))
        before = {
            path.name: path.read_bytes()
            for path in self.events_directory.iterdir()
        }

        with self.assertRaises(ValueError):
            self.ledger.append(
                "second_event",
                {"scopeSha256": "b" * 64},
                "2026-07-11T12:01:00+09:00",
            )

        after = {
            path.name: path.read_bytes()
            for path in self.events_directory.iterdir()
        }
        self.assertEqual(after, before)

    def test_append_rejects_tampered_sidecar(self) -> None:
        entry = self.ledger.append(
            "scope_frozen",
            {"scopeSha256": "a" * 64},
            "2026-07-11T12:00:00+09:00",
        )
        entry.sidecar_path.write_bytes(b"f" * 64 + b"\n")

        with self.assertRaises(ValueError):
            self.ledger.append(
                "second_event",
                {"scopeSha256": "b" * 64},
                "2026-07-11T12:01:00+09:00",
            )

        self.assertFalse((self.events_directory / "000002.json").exists())

    def test_append_rejects_prefix_gap(self) -> None:
        self.events_directory.mkdir(parents=True)
        path = self.events_directory / "000002.json"
        record = {
            "schemaVersion": LEDGER_SCHEMA_VERSION,
            "eventType": "orphan",
            "occurredAt": "2026-07-11T12:00:00+09:00",
            "payload": {},
            "previousRecordSha256": "a" * 64,
            "sequence": 2,
        }
        source = canonical_json_bytes(record)
        path.write_bytes(source)
        Path(f"{path}.sha256").write_bytes(
            f"{sha256_bytes(source)}\n".encode("ascii")
        )

        with self.assertRaises(ValueError):
            self.ledger.append(
                "next_event",
                {},
                "2026-07-11T12:01:00+09:00",
            )

        self.assertFalse((self.events_directory / "000001.json").exists())

    def test_append_rejects_validly_rehashed_broken_predecessor_chain(self) -> None:
        self.ledger.append(
            "first_event",
            {},
            "2026-07-11T12:00:00+09:00",
        )
        second_entry = self.ledger.append(
            "second_event",
            {},
            "2026-07-11T12:01:00+09:00",
        )
        second_record = load_json_object(second_entry.path)
        second_record["previousRecordSha256"] = "f" * 64
        tampered_source = canonical_json_bytes(second_record)
        second_entry.path.write_bytes(tampered_source)
        second_entry.sidecar_path.write_bytes(
            f"{sha256_bytes(tampered_source)}\n".encode("ascii")
        )

        with self.assertRaises(ValueError):
            self.ledger.append(
                "third_event",
                {},
                "2026-07-11T12:02:00+09:00",
            )

        self.assertFalse((self.events_directory / "000003.json").exists())

    def test_append_rejects_sensitive_payload_without_creating_event(self) -> None:
        sensitive_text = "client_" + "secret = " + "SyntheticValue_12345"

        with self.assertRaises(ValueError) as caught:
            self.ledger.append(
                "unsafe_event",
                {"description": sensitive_text},
                "2026-07-11T12:00:00+09:00",
            )

        self.assertNotIn(sensitive_text, str(caught.exception))
        if self.events_directory.exists():
            self.assertEqual(tuple(self.events_directory.iterdir()), ())


class FreezeInterimScopeCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.repository_root = Path(self.temporary_directory.name)
        self.plan_relative_path = Path("plans/interim-plan.md")
        self.plan_path = self.repository_root / self.plan_relative_path
        self.plan_path.parent.mkdir(parents=True)
        self.plan_source = (
            "# Frozen interim plan\n"
            + "private marker: "
            + "client_"
            + "secret = "
            + "SyntheticValue_12345\n"
        ).encode("utf-8")
        self.plan_path.write_bytes(self.plan_source)
        self.plan_sha256 = sha256_bytes(self.plan_source)
        self.scope_relative_path = Path("evidence/interim-scope.json")
        self.ledger_relative_path = Path("evidence/local-ledger")
        self.frozen_at = "2026-07-11T12:34:56+09:00"

    def _run_cli(
        self,
        expected_plan_sha256: str,
        scope_relative_path: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        requested_scope_path = scope_relative_path or self.scope_relative_path
        return subprocess.run(
            [
                sys.executable,
                str(FREEZE_SCRIPT_PATH),
                "--repository-root",
                str(self.repository_root),
                "--plan",
                self.plan_relative_path.as_posix(),
                "--expected-plan-sha256",
                expected_plan_sha256,
                "--frozen-at",
                self.frozen_at,
                "--scope-output",
                requested_scope_path.as_posix(),
                "--ledger-directory",
                self.ledger_relative_path.as_posix(),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_cli_rejects_invalid_ledger_before_publishing_scope_pair(self) -> None:
        events_directory = (
            self.repository_root / self.ledger_relative_path / "events"
        )
        events_directory.mkdir(parents=True)
        invalid_entry = events_directory / "unexpected-entry"
        original_ledger_source = b"prior-ledger-bytes"
        invalid_entry.write_bytes(original_ledger_source)

        result = self._run_cli(self.plan_sha256)

        scope_path = self.repository_root / self.scope_relative_path
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertFalse(scope_path.exists())
        self.assertFalse(Path(f"{scope_path}.sha256").exists())
        self.assertEqual(invalid_entry.read_bytes(), original_ledger_source)

    def test_cli_allows_only_first_equivalent_scope_for_one_ledger(self) -> None:
        first_result = self._run_cli(self.plan_sha256)
        scope_path = self.repository_root / self.scope_relative_path
        event_path = (
            self.repository_root
            / self.ledger_relative_path
            / "events"
            / "000001.json"
        )
        protected_paths = (
            scope_path,
            Path(f"{scope_path}.sha256"),
            event_path,
            Path(f"{event_path}.sha256"),
        )
        first_publication = {
            path.relative_to(self.repository_root).as_posix(): path.read_bytes()
            for path in protected_paths
        }
        retry_scope_relative_path = Path("evidence/retry-interim-scope.json")

        retry_result = self._run_cli(
            self.plan_sha256,
            retry_scope_relative_path,
        )

        retry_scope_path = self.repository_root / retry_scope_relative_path
        final_publication = {
            path.relative_to(self.repository_root).as_posix(): path.read_bytes()
            for path in protected_paths
        }
        self.assertEqual(first_result.returncode, 0, first_result.stderr)
        self.assertEqual(retry_result.returncode, 1)
        self.assertEqual(retry_result.stdout, "")
        self.assertFalse(retry_scope_path.exists())
        self.assertFalse(Path(f"{retry_scope_path}.sha256").exists())
        self.assertEqual(final_publication, first_publication)
        self.assertFalse((event_path.parent / "000002.json").exists())

    def test_cli_freezes_exact_scope_deferred_security_and_evidence_contract(
        self,
    ) -> None:
        result = self._run_cli(self.plan_sha256)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        scope_path = self.repository_root / self.scope_relative_path
        expected_scope = {
            "schemaVersion": SCOPE_SCHEMA_VERSION,
            "programId": "RP-001",
            "decision": "research_only",
            "frozenAt": self.frozen_at,
            "frozenPlan": {
                "path": self.plan_relative_path.as_posix(),
                "sha256": self.plan_sha256,
            },
            "mustHoldQualityRuleIds": list(MUST_HOLD_QUALITY_RULE_IDS),
            "deferredCapabilities": [
                {
                    "id": capability_id,
                    "status": "deferred_until_final_adoption",
                }
                for capability_id in DEFERRED_CAPABILITY_IDS
            ],
            "security": {
                "forbiddenApiFamilies": ["account", "asset", "order"],
                "operatingAppModificationProhibited": True,
            },
            "allowedPlanChangeReasons": list(ALLOWED_PLAN_CHANGE_REASONS),
        }
        scope_source = canonical_json_bytes(expected_scope)
        scope_sha256 = sha256_bytes(scope_source)
        self.assertEqual(scope_path.read_bytes(), scope_source)
        self.assertEqual(load_json_object(scope_path), expected_scope)
        self.assertEqual(
            Path(f"{scope_path}.sha256").read_bytes(),
            f"{scope_sha256}\n".encode("ascii"),
        )

        event_path = (
            self.repository_root
            / self.ledger_relative_path
            / "events"
            / "000001.json"
        )
        expected_event = {
            "schemaVersion": LEDGER_SCHEMA_VERSION,
            "eventType": "interim_scope_frozen",
            "occurredAt": self.frozen_at,
            "payload": {
                "plan": {
                    "path": self.plan_relative_path.as_posix(),
                    "sha256": self.plan_sha256,
                },
                "scope": {
                    "path": self.scope_relative_path.as_posix(),
                    "sha256": scope_sha256,
                },
            },
            "previousRecordSha256": None,
            "sequence": 1,
        }
        event_source = canonical_json_bytes(expected_event)
        record_sha256 = sha256_bytes(event_source)
        self.assertEqual(event_path.read_bytes(), event_source)
        self.assertEqual(
            Path(f"{event_path}.sha256").read_bytes(),
            f"{record_sha256}\n".encode("ascii"),
        )
        assert_no_own_hash_keys(self, expected_scope)
        assert_no_own_hash_keys(self, expected_event)

        expected_summary = {
            "deferredCapabilityCount": len(DEFERRED_CAPABILITY_IDS),
            "ledgerEntryCount": 1,
            "mustHoldQualityRuleCount": len(MUST_HOLD_QUALITY_RULE_IDS),
            "planSha256": self.plan_sha256,
            "recordSha256": record_sha256,
            "scopeSha256": scope_sha256,
        }
        self.assertEqual(
            result.stdout,
            canonical_json_bytes(expected_summary).decode("utf-8") + "\n",
        )
        self.assertNotIn(self.plan_source.decode("utf-8"), result.stdout)
        self.assertNotIn("SyntheticValue_12345", result.stdout)
        self.assertNotIn(SCOPE_SCHEMA_VERSION, result.stdout)
        self.assertEqual(find_sensitive_values(result.stdout), ())

    def test_cli_rejects_plan_hash_mismatch_before_any_evidence_write(self) -> None:
        result = self._run_cli("0" * 64)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("INVALID", result.stderr)
        self.assertNotIn(self.plan_source.decode("utf-8"), result.stderr)
        self.assertFalse(
            (self.repository_root / self.scope_relative_path).exists()
        )
        self.assertFalse(
            (self.repository_root / self.ledger_relative_path).exists()
        )


if __name__ == "__main__":
    unittest.main()
