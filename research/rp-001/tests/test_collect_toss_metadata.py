from __future__ import annotations

import base64
import contextlib
import dataclasses
import hashlib
import importlib.util
import io
import json
import os
import shutil
import stat
import sys
import tempfile
import threading
import time
import traceback
import types
import unittest
from collections.abc import Callable, Iterator, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from urllib.error import HTTPError
from urllib.parse import parse_qs
from urllib.request import Request
from unittest import mock

from rp001.local_evidence import (
    LocalArtifactStore,
    canonical_json_bytes,
)
from rp001.sample_selection import CANDIDATE_POOL
from rp001.sensitive_value_policy import find_sensitive_values


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
RUNNER_PATH = REPOSITORY_ROOT / "research/rp-001/collect_toss_metadata.py"


def load_module(path: Path, module_name: str) -> object:
    specification = importlib.util.spec_from_file_location(
        module_name,
        path,
    )
    if specification is None or specification.loader is None:
        raise AssertionError("test module could not be loaded")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def load_runner(
    path: Path = RUNNER_PATH,
    module_name: str = "rp001_collect_toss_metadata_test_target",
) -> object:
    return load_module(path, module_name)


def load_isolated_runner(repository_root: Path) -> tuple[object, tuple[str, ...]]:
    suffix = hashlib.sha256(str(repository_root).encode("utf-8")).hexdigest()[:12]
    sensitive_name = f"rp001_fixture_sensitive_policy_{suffix}"
    local_evidence_name = f"rp001_fixture_local_evidence_{suffix}"
    selection_name = f"rp001_fixture_selection_{suffix}"
    collector_name = f"rp001_fixture_collector_{suffix}"
    runner_name = f"rp001_fixture_runner_{suffix}"
    sensitive_policy = load_module(
        repository_root
        / "research/rp-001/src/rp001/sensitive_value_policy.py",
        sensitive_name,
    )
    canonical_names = (
        "rp001.sensitive_value_policy",
        "rp001.local_evidence",
        "rp001.sample_selection",
        "rp001.toss_research_collector",
    )
    prior_modules = {name: sys.modules.get(name) for name in canonical_names}
    aliases: dict[str, object] = {
        "rp001.sensitive_value_policy": sensitive_policy,
    }
    try:
        sys.modules.update(aliases)
        local_evidence = load_module(
            repository_root / "research/rp-001/src/rp001/local_evidence.py",
            local_evidence_name,
        )
        aliases["rp001.local_evidence"] = local_evidence
        sys.modules["rp001.local_evidence"] = local_evidence
        selection = load_module(
            repository_root / "research/rp-001/src/rp001/sample_selection.py",
            selection_name,
        )
        collector = load_module(
            repository_root
            / "research/rp-001/src/rp001/toss_research_collector.py",
            collector_name,
        )
        aliases["rp001.sample_selection"] = selection
        aliases["rp001.toss_research_collector"] = collector
        sys.modules["rp001.sample_selection"] = selection
        sys.modules["rp001.toss_research_collector"] = collector
        runner = load_runner(
            repository_root / "research/rp-001/collect_toss_metadata.py",
            runner_name,
        )
    finally:
        for name in aliases:
            prior = prior_modules.get(name)
            if prior is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = prior
    return runner, (
        runner_name,
        collector_name,
        selection_name,
        local_evidence_name,
        sensitive_name,
    )


RUNNER = load_runner()


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixed_clock() -> datetime:
    return datetime(2026, 7, 11, 1, 2, 3, tzinfo=timezone.utc)


def traceback_exposed_strings(error: BaseException) -> tuple[str, ...]:
    exposed: list[str] = []
    pending: list[BaseException] = [error]
    seen_errors: set[int] = set()

    def collect(value: object, seen_values: set[int], depth: int = 0) -> None:
        if depth > 8:
            return
        if id(value) in seen_values:
            return
        seen_values.add(id(value))
        if isinstance(value, str):
            exposed.append(value)
            return
        if isinstance(value, bytes):
            exposed.append(value.decode("utf-8", errors="ignore"))
            return
        if isinstance(value, Mapping):
            for key, nested in value.items():
                collect(key, seen_values, depth + 1)
                collect(nested, seen_values, depth + 1)
            return
        if isinstance(value, (tuple, list, set, frozenset)):
            for nested in value:
                collect(nested, seen_values, depth + 1)
            return
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            for field in dataclasses.fields(value):
                collect(getattr(value, field.name), seen_values, depth + 1)
            return
        if isinstance(value, types.FunctionType):
            for closure in value.__closure__ or ():
                try:
                    collect(closure.cell_contents, seen_values, depth + 1)
                except ValueError:
                    continue
            return
        if isinstance(value, (types.ModuleType, type, types.MethodType)):
            return
        try:
            attributes = vars(value)
        except TypeError:
            return
        collect(attributes, seen_values, depth + 1)

    while pending:
        current = pending.pop()
        if id(current) in seen_errors:
            continue
        seen_errors.add(id(current))
        current_traceback = current.__traceback__
        while current_traceback is not None:
            frame = current_traceback.tb_frame
            executed_runner = Path(
                getattr(RUNNER, "__file__", RUNNER_PATH)
            ).resolve()
            if Path(frame.f_code.co_filename).resolve() == executed_runner:
                for local_name, local_value in frame.f_locals.items():
                    collect(local_value, set())
            current_traceback = current_traceback.tb_next
        if current.__cause__ is not None:
            pending.append(current.__cause__)
        if current.__context__ is not None:
            pending.append(current.__context__)
    return tuple(exposed)


class FakeUrlResponse:
    def __init__(
        self,
        status: int,
        headers: Mapping[str, str],
        body: bytes,
    ) -> None:
        self.status = status
        self.headers = MappingProxyType(dict(headers))
        self._body = body
        self._offset = 0
        self.read_sizes: list[int] = []

    def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        if size < 0:
            value = self._body[self._offset :]
            self._offset = len(self._body)
            return value
        value = self._body[self._offset : self._offset + size]
        self._offset += len(value)
        return value

    def close(self) -> None:
        return None


class FragmentedUrlResponse(FakeUrlResponse):
    def __init__(
        self,
        status: int,
        headers: Mapping[str, str],
        chunks: Sequence[bytes],
    ) -> None:
        super().__init__(status, headers, b"")
        self._chunks = list(chunks)

    def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        if not self._chunks:
            return b""
        chunk = self._chunks.pop(0)
        if size >= 0 and len(chunk) > size:
            self._chunks.insert(0, chunk[size:])
            return chunk[:size]
        return chunk


class RecordingBytesIO(io.BytesIO):
    def __init__(self, source: bytes) -> None:
        super().__init__(source)
        self.read_sizes: list[int] = []

    def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        return super().read(size)


class RecordingOpener:
    def __init__(self, responses: Sequence[object]) -> None:
        self.responses = list(responses)
        self.requests: list[Request] = []

    def open(self, request: Request, timeout: float) -> FakeUrlResponse:
        del timeout
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("unexpected HTTP request")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        if not isinstance(response, FakeUrlResponse):
            raise AssertionError("invalid fake response")
        return response


class BlockingOpener(RecordingOpener):
    def __init__(
        self,
        responses: Sequence[object],
        entered: threading.Event,
        release: threading.Event,
    ) -> None:
        super().__init__(responses)
        self.entered = entered
        self.release = release

    def open(self, request: Request, timeout: float) -> FakeUrlResponse:
        if not self.requests:
            self.entered.set()
            if not self.release.wait(timeout=5.0):
                raise AssertionError("fixture release timed out")
        return super().open(request, timeout)


class FailingLedger:
    def append(
        self,
        event_type: str,
        payload: Mapping[str, object],
        occurred_at: str,
    ) -> object:
        del event_type, payload, occurred_at
        raise RUNNER.LocalEvidenceError("fixture ledger failure")


class InterruptAfterAppendLedger:
    def __init__(self, ledger_directory: Path) -> None:
        self._ledger = RUNNER.AppendOnlyLocalLedger(ledger_directory)
        self._append_count = 0

    def append(
        self,
        event_type: str,
        payload: Mapping[str, object],
        occurred_at: str,
    ) -> object:
        self._append_count += 1
        entry = self._ledger.append(event_type, payload, occurred_at)
        if self._append_count == 1:
            raise SystemExit("fixture interrupt after ledger append")
        return entry


class InterruptAfterArtifactPublishStore:
    def __init__(
        self,
        trusted_root: Path,
        interrupt_at: int,
        interruption: BaseException,
    ) -> None:
        self._store = RUNNER.LocalArtifactStore(trusted_root.resolve())
        self._interrupt_at = interrupt_at
        self._interruption = interruption
        self._publish_count = 0

    def publish_json(
        self,
        path: Path,
        value: Mapping[str, object],
    ) -> object:
        self._publish_count += 1
        binding = self._store.publish_json(path, value)
        if self._publish_count == self._interrupt_at:
            raise self._interruption
        return binding


class InterruptAfterPartialArtifactBodyStore:
    def __init__(self, trusted_root: Path) -> None:
        self._store = RUNNER.LocalArtifactStore(trusted_root.resolve())
        self._publish_count = 0

    def publish_json(
        self,
        path: Path,
        value: Mapping[str, object],
    ) -> object:
        self._publish_count += 1
        if self._publish_count == 1:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(canonical_json_bytes(value))
            raise KeyboardInterrupt("fixture interrupt after body only")
        return self._store.publish_json(path, value)


class FailFirstArtifactPublishStore:
    def __init__(self, trusted_root: Path) -> None:
        self._store = RUNNER.LocalArtifactStore(trusted_root.resolve())
        self._publish_count = 0

    def publish_json(
        self,
        path: Path,
        value: Mapping[str, object],
    ) -> object:
        self._publish_count += 1
        if self._publish_count == 1:
            raise RUNNER.LocalEvidenceError("fixture first publication failure")
        return self._store.publish_json(path, value)


class MetadataRunnerFixture(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repository_root = Path(self.temporary_directory.name).resolve()
        self.output_directory = self.repository_root / "research/rp-001/runs"
        self.ledger_directory = (
            self.repository_root
            / "research/rp-001/local-ledgers/interim-program"
        )

        self._copy_bound_path("research/rp-001/contracts/metadata-sample-design-v1.json")
        self._copy_bound_path("research/rp-001/contracts/interim-formula-contract-v1.0.1.json")
        self._copy_bound_path(
            "research/rp-001/contracts/toss-read-only-source-contract-v1.1.json"
        )
        for relative_path in (
            "research/rp-001/src/rp001/interim_candidates.py",
            "research/rp-001/tests/test_interim_candidates.py",
            "research/rp-001/src/rp001/toss_research_collector.py",
            "research/rp-001/tests/test_toss_research_collector.py",
            "research/rp-001/src/rp001/sample_selection.py",
            "research/rp-001/tests/test_sample_selection.py",
            "research/rp-001/src/rp001/local_evidence.py",
            "research/rp-001/tests/test_local_evidence_contract.py",
            "research/rp-001/src/rp001/sensitive_value_policy.py",
            "research/rp-001/tests/test_sensitive_value_policy.py",
            "research/rp-001/collect_toss_metadata.py",
            "research/rp-001/tests/test_collect_toss_metadata.py",
        ):
            self._copy_path(relative_path)
        global RUNNER
        self._prior_runner = RUNNER
        RUNNER, self._isolated_module_names = load_isolated_runner(
            self.repository_root
        )
        self._publish_fixture_source_contract()

        self.credentials_path = (
            self.repository_root / ".storage/toss-credentials.local.json"
        )
        self.credentials_path.parent.mkdir(parents=True)
        self.client_identifier = "".join(("fixture", "-client-", "identifier-value"))
        self.private_credential = "".join(("fixture", "-private-", "credential-value"))
        credential_body = {
            "".join(("client", "Id")): self.client_identifier,
            "".join(("client", "Secret")): self.private_credential,
        }
        self.credentials_path.write_text(
            json.dumps(credential_body, separators=(",", ":")),
            encoding="utf-8",
        )
        self.credentials_path.chmod(0o600)

        self.ephemeral_bearer = "".join(("ephemeral", "-bearer-", "fixture-value"))
        self.metadata_body = json.dumps(
            {"result": [self._metadata_row(symbol) for symbol in CANDIDATE_POOL]},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        self.arguments = self._arguments()

    def tearDown(self) -> None:
        global RUNNER
        RUNNER = self._prior_runner
        for module_name in self._isolated_module_names:
            sys.modules.pop(module_name, None)
        self.temporary_directory.cleanup()

    def _copy_path(self, relative_path: str) -> None:
        destination = self.repository_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPOSITORY_ROOT / relative_path, destination)

    def _copy_bound_path(self, relative_path: str) -> None:
        self._copy_path(relative_path)
        self._copy_path(f"{relative_path}.sha256")

    def _publish_fixture_source_contract(self) -> None:
        template_path = (
            self.repository_root
            / "research/rp-001/contracts/toss-read-only-source-contract-v1.1.json"
        )
        value = json.loads(template_path.read_text(encoding="utf-8"))
        value["schemaVersion"] = "rp001-toss-read-only-source-contract.v1.2"
        value["status"] = "read_only_metadata_runner_authorized"
        value["frozenAt"] = "2026-07-10T22:35:20Z"
        value["frozenAtMeaning"] = (
            "metadata_only_policy_boundary_before_runner_finalization"
        )
        value["finalizedAt"] = "2026-07-11T00:00:00Z"
        value["supersedes"] = {
            "path": (
                "research/rp-001/contracts/"
                "toss-read-only-source-contract-v1.1.json"
            ),
            "reason": (
                "bind_metadata_runner_execution_lineage_and_restrict_"
                "live_transport_to_metadata_only"
            ),
            "sha256": sha256_path(template_path),
        }
        value["provider"] = {
            "baseUrl": "https://openapi.tossinvest.com",
            "name": "Toss Securities OpenAPI",
            "officialSpecificationUrl": (
                "https://openapi.tossinvest.com/openapi-docs/latest/"
                "openapi.json"
            ),
            "rawSha256": (
                "2c54ebfd038a8c135f4b7f9036c42934d8ab9906c026251a7ae827b81e8e6aa8"
            ),
            "version": "1.2.2",
        }
        value["credentialBoundary"]["pathClass"] = (
            "repository_dot_storage_0600_pinned_regular_file"
        )
        value["allowedRequests"] = [
            {
                "method": "POST",
                "path": "/oauth2/token",
                "purpose": "ephemeral_authentication_only",
                "responsePersistence": "forbidden",
            },
            {
                "method": "GET",
                "parameters": ["symbols"],
                "path": "/api/v1/stocks",
                "purpose": "metadata_only_sample_selection",
            },
        ]
        value["deferredUntilSampleFreeze"] = [
            {
                "method": "GET",
                "parameters": [
                    "symbol",
                    "interval=1d",
                    "count=200",
                    "adjusted",
                    "before",
                ],
                "path": "/api/v1/candles",
                "purpose": "predeclared_daily_price_volume",
                "reason": (
                    "price_volume_open_forbidden_during_metadata_only_selection"
                ),
                "successorContract": (
                    "required_after_metadata_sample_freeze"
                ),
            }
        ]
        value["qualityEvidence"] = {
            "collectorTestsPassed": 62,
            "collectorTestsTotal": 62,
            "criticalFindings": 0,
            "finalReviewVerdict": "APPROVE",
            "importantFindings": 0,
            "localEvidenceTestsPassed": 21,
            "localEvidenceTestsTotal": 21,
            "minorFindings": 0,
            "preflightHistory": [
                "runner_metadata_only_transport_and_source_lineage_reviewed",
                "namespace_toctou_and_interrupt_recovery_reviewed",
                "credential_path_class_fail_closed",
                "fragmented_http_body_lineage_reviewed",
            ],
            "programRegressionTestsPassed": 374,
            "programRegressionTestsTotal": 374,
            "reviewScope": [
                "parent_fd_trust_anchor_active_lifecycle",
                "post_return_external_cas_deferred",
            ],
            "reviewVerdicts": {
                "collector": "APPROVE_C0_I0_M0",
                "localEvidence": "APPROVE_C0_I0_M0",
                "runner": "APPROVE_C0_I0_M0",
                "selection": "APPROVE_C0_I0_M0",
                "sensitiveValuePolicy": "APPROVE_C0_I0_M0",
            },
            "runnerTestsPassed": 87,
            "runnerTestsTotal": 87,
            "runnerDependencyRegressionTestsPassed": 266,
            "runnerDependencyRegressionTestsTotal": 266,
            "selectionTestsPassed": 33,
            "selectionTestsTotal": 33,
            "sensitivePolicyTestsPassed": 6,
            "sensitivePolicyTestsTotal": 6,
        }
        value["canonicalLedgerPath"] = (
            "research/rp-001/local-ledgers/interim-program"
        )
        value["bindings"]["runner"] = {
            "sourcePath": "research/rp-001/collect_toss_metadata.py",
            "sourceSha256": sha256_path(
                self.repository_root
                / "research/rp-001/collect_toss_metadata.py"
            ),
            "testPath": "research/rp-001/tests/test_collect_toss_metadata.py",
            "testSha256": sha256_path(
                self.repository_root
                / "research/rp-001/tests/test_collect_toss_metadata.py"
            ),
        }
        for binding_name, source_path, test_path in (
            (
                "collector",
                "research/rp-001/src/rp001/toss_research_collector.py",
                "research/rp-001/tests/test_toss_research_collector.py",
            ),
            (
                "selection",
                "research/rp-001/src/rp001/sample_selection.py",
                "research/rp-001/tests/test_sample_selection.py",
            ),
            (
                "localEvidence",
                "research/rp-001/src/rp001/local_evidence.py",
                "research/rp-001/tests/test_local_evidence_contract.py",
            ),
            (
                "sensitiveValuePolicy",
                "research/rp-001/src/rp001/sensitive_value_policy.py",
                "research/rp-001/tests/test_sensitive_value_policy.py",
            ),
        ):
            value["bindings"][binding_name] = {
                "sourcePath": source_path,
                "sourceSha256": sha256_path(self.repository_root / source_path),
                "testPath": test_path,
                "testSha256": sha256_path(self.repository_root / test_path),
            }
        value["bindings"]["formulaContract"] = {
            "path": "research/rp-001/contracts/interim-formula-contract-v1.0.1.json",
            "protocolVersion": "1.0.1",
            "sha256": sha256_path(
                self.repository_root
                / "research/rp-001/contracts/interim-formula-contract-v1.0.1.json"
            ),
        }
        value["bindings"]["metadataSampleDesign"] = {
            "path": "research/rp-001/contracts/metadata-sample-design-v1.json",
            "sha256": sha256_path(
                self.repository_root
                / "research/rp-001/contracts/metadata-sample-design-v1.json"
            ),
        }
        destination = (
            self.repository_root
            / "research/rp-001/contracts/toss-read-only-source-contract-v1.2.json"
        )
        LocalArtifactStore(self.repository_root.resolve()).publish_json(
            destination,
            value,
        )

    def _arguments(self) -> object:
        return RUNNER.MetadataRunArguments(
            repository_root=self.repository_root,
            credentials_path=self.credentials_path,
            sample_design_path=Path(
                "research/rp-001/contracts/metadata-sample-design-v1.json"
            ),
            sample_design_sha256=sha256_path(
                self.repository_root
                / "research/rp-001/contracts/metadata-sample-design-v1.json"
            ),
            formula_contract_path=Path(
                "research/rp-001/contracts/interim-formula-contract-v1.0.1.json"
            ),
            formula_contract_sha256=sha256_path(
                self.repository_root
                / "research/rp-001/contracts/interim-formula-contract-v1.0.1.json"
            ),
            source_contract_path=Path(
                "research/rp-001/contracts/toss-read-only-source-contract-v1.2.json"
            ),
            source_contract_sha256=sha256_path(
                self.repository_root
                / "research/rp-001/contracts/toss-read-only-source-contract-v1.2.json"
            ),
            runner_source_path=Path(
                "research/rp-001/collect_toss_metadata.py"
            ),
            runner_source_sha256=sha256_path(
                self.repository_root
                / "research/rp-001/collect_toss_metadata.py"
            ),
            runner_test_path=Path(
                "research/rp-001/tests/test_collect_toss_metadata.py"
            ),
            runner_test_sha256=sha256_path(
                self.repository_root
                / "research/rp-001/tests/test_collect_toss_metadata.py"
            ),
            formula_source_path=Path(
                "research/rp-001/src/rp001/interim_candidates.py"
            ),
            formula_source_sha256=sha256_path(
                self.repository_root
                / "research/rp-001/src/rp001/interim_candidates.py"
            ),
            formula_test_path=Path(
                "research/rp-001/tests/test_interim_candidates.py"
            ),
            formula_test_sha256=sha256_path(
                self.repository_root
                / "research/rp-001/tests/test_interim_candidates.py"
            ),
            collector_source_path=Path(
                "research/rp-001/src/rp001/toss_research_collector.py"
            ),
            collector_source_sha256=sha256_path(
                self.repository_root
                / "research/rp-001/src/rp001/toss_research_collector.py"
            ),
            collector_test_path=Path(
                "research/rp-001/tests/test_toss_research_collector.py"
            ),
            collector_test_sha256=sha256_path(
                self.repository_root
                / "research/rp-001/tests/test_toss_research_collector.py"
            ),
            selection_source_path=Path(
                "research/rp-001/src/rp001/sample_selection.py"
            ),
            selection_source_sha256=sha256_path(
                self.repository_root
                / "research/rp-001/src/rp001/sample_selection.py"
            ),
            selection_test_path=Path(
                "research/rp-001/tests/test_sample_selection.py"
            ),
            selection_test_sha256=sha256_path(
                self.repository_root
                / "research/rp-001/tests/test_sample_selection.py"
            ),
            local_evidence_source_path=Path(
                "research/rp-001/src/rp001/local_evidence.py"
            ),
            local_evidence_source_sha256=sha256_path(
                self.repository_root
                / "research/rp-001/src/rp001/local_evidence.py"
            ),
            local_evidence_test_path=Path(
                "research/rp-001/tests/test_local_evidence_contract.py"
            ),
            local_evidence_test_sha256=sha256_path(
                self.repository_root
                / "research/rp-001/tests/test_local_evidence_contract.py"
            ),
            sensitive_policy_source_path=Path(
                "research/rp-001/src/rp001/sensitive_value_policy.py"
            ),
            sensitive_policy_source_sha256=sha256_path(
                self.repository_root
                / "research/rp-001/src/rp001/sensitive_value_policy.py"
            ),
            sensitive_policy_test_path=Path(
                "research/rp-001/tests/test_sensitive_value_policy.py"
            ),
            sensitive_policy_test_sha256=sha256_path(
                self.repository_root
                / "research/rp-001/tests/test_sensitive_value_policy.py"
            ),
            output_directory=Path("research/rp-001/runs"),
            ledger_directory=Path(
                "research/rp-001/local-ledgers/interim-program"
            ),
            run_id="metadata-run-001",
        )

    def _metadata_row(self, symbol: str) -> dict[str, object]:
        return {
            "symbol": symbol,
            "name": f"{symbol} name",
            "englishName": f"{symbol} Corporation",
            "isinCode": f"US{symbol:0<10}"[:12],
            "market": "NASDAQ",
            "securityType": "STOCK",
            "isCommonShare": True,
            "status": "ACTIVE",
            "currency": "USD",
            "sharesOutstanding": "1000000",
        }

    def _success_opener(self) -> RecordingOpener:
        auth_body = json.dumps(
            {
                "_".join(("access", "token")): self.ephemeral_bearer,
                "expires_in": 3600,
            },
            separators=(",", ":"),
        ).encode("utf-8")
        return RecordingOpener(
            (
                FakeUrlResponse(
                    200,
                    {"Content-Type": "application/json"},
                    auth_body,
                ),
                FakeUrlResponse(
                    200,
                    {
                        "Content-Type": "application/json",
                        "ETag": '"fixture"',
                        "Set-Cookie": "must-not-persist",
                    },
                    self.metadata_body,
                ),
            )
        )

    def _run(self, opener: RecordingOpener, **dependencies: object) -> object:
        return RUNNER.run_metadata_collection(
            self.arguments,
            opener=opener,
            clock=fixed_clock,
            **dependencies,
        )

    def _capture_run_error(
        self,
        operation: Callable[[], object],
    ) -> BaseException:
        try:
            operation()
        except RUNNER.MetadataRunError as error:
            return error
        self.fail("metadata run unexpectedly succeeded")

    def _capture_any_error(
        self,
        operation: Callable[[], object],
    ) -> BaseException:
        try:
            operation()
        except BaseException as error:
            return error
        self.fail("metadata run unexpectedly succeeded")

    def _failure_body(self) -> dict[str, object]:
        path = (
            self.output_directory
            / self.arguments.run_id
            / "failure.json"
        )
        self.assertTrue(path.is_file(), "terminal failure artifact is missing")
        return json.loads(path.read_text(encoding="utf-8"))

    def _json_files(self) -> tuple[Path, ...]:
        return tuple(
            sorted(
                path
                for path in self.repository_root.rglob("*.json")
                if self.output_directory in path.parents
                or self.ledger_directory in path.parents
            )
        )

    def _assert_sidecar(self, path: Path) -> None:
        sidecar = Path(f"{path}.sha256")
        self.assertTrue(sidecar.is_file())
        self.assertEqual(
            sidecar.read_text(encoding="ascii"),
            f"{sha256_path(path)}\n",
        )

    def _expected_source_lineage(self) -> list[dict[str, object]]:
        return [
            {
                "role": role,
                "path": str(getattr(self.arguments, f"{field}_path")),
                "sha256": getattr(self.arguments, f"{field}_sha256"),
            }
            for role, field in (
                ("sample_design", "sample_design"),
                ("formula_contract", "formula_contract"),
                ("source_contract", "source_contract"),
                ("runner_source", "runner_source"),
                ("runner_test", "runner_test"),
                ("formula_source", "formula_source"),
                ("formula_test", "formula_test"),
                ("collector_source", "collector_source"),
                ("collector_test", "collector_test"),
                ("selection_source", "selection_source"),
                ("selection_test", "selection_test"),
                ("local_evidence_source", "local_evidence_source"),
                ("local_evidence_test", "local_evidence_test"),
                ("sensitive_policy_source", "sensitive_policy_source"),
                ("sensitive_policy_test", "sensitive_policy_test"),
            )
        ]

    def _assert_no_terminal_evidence(self) -> None:
        run_directory = self.output_directory / self.arguments.run_id
        self.assertFalse(run_directory.exists())
        events_directory = self.ledger_directory / "events"
        self.assertEqual(
            tuple(events_directory.glob("*.json"))
            if events_directory.exists()
            else (),
            (),
        )

    def _bind_decoy_execution_source(self, role: str) -> None:
        field = f"{role}_source"
        decoy_relative = Path(
            f"research/rp-001/src/rp001/{role}_execution_decoy.py"
        )
        decoy_path = self.repository_root / decoy_relative
        decoy_path.parent.mkdir(parents=True, exist_ok=True)
        decoy_path.write_text(
            f'"""Bound decoy for {role}; this module is not executed."""\n',
            encoding="utf-8",
        )
        decoy_sha256 = sha256_path(decoy_path)
        object.__setattr__(self.arguments, f"{field}_path", decoy_relative)
        object.__setattr__(self.arguments, f"{field}_sha256", decoy_sha256)

        if role == "selection":
            self._replace_sample_design(
                lambda value: value["selectionImplementation"].update(
                    {
                        "sourcePath": decoy_relative.as_posix(),
                        "sourceSha256": decoy_sha256,
                    }
                )
            )

        binding_name = {
            "local_evidence": "localEvidence",
            "sensitive_policy": "sensitiveValuePolicy",
        }.get(role, role)

        def update_source_contract(value: dict[str, object]) -> None:
            bindings = value["bindings"]
            bindings[binding_name].update(
                {
                    "sourcePath": decoy_relative.as_posix(),
                    "sourceSha256": decoy_sha256,
                }
            )
            if role == "selection":
                bindings["metadataSampleDesign"]["sha256"] = (
                    self.arguments.sample_design_sha256
                )

        self._replace_source_contract(update_source_contract)

    def _replace_sample_design(self, mutator: object) -> None:
        path = self.repository_root / self.arguments.sample_design_path
        sidecar = Path(f"{path}.sha256")
        value = json.loads(path.read_text(encoding="utf-8"))
        mutator(value)
        path.unlink()
        sidecar.unlink()
        binding = LocalArtifactStore(
            self.repository_root.resolve()
        ).publish_json(path, value)
        object.__setattr__(
            self.arguments,
            "sample_design_sha256",
            binding.artifact_sha256,
        )

    def _replace_source_contract(self, mutator: object) -> None:
        path = self.repository_root / self.arguments.source_contract_path
        sidecar = Path(f"{path}.sha256")
        value = json.loads(path.read_text(encoding="utf-8"))
        mutator(value)
        path.unlink()
        sidecar.unlink()
        binding = LocalArtifactStore(
            self.repository_root.resolve()
        ).publish_json(path, value)
        object.__setattr__(
            self.arguments,
            "source_contract_sha256",
            binding.artifact_sha256,
        )


class FrozenInputPreflightTest(MetadataRunnerFixture):
    def test_source_contract_distinguishes_policy_freeze_and_finalization(self) -> None:
        valid_chronology = {
            "finalizedAt": "2026-07-11T00:00:00Z",
            "frozenAtMeaning": (
                "metadata_only_policy_boundary_before_runner_finalization"
            ),
        }
        self._replace_source_contract(
            lambda value: value.update(valid_chronology)
        )

        summary = self._run(self._success_opener())

        self.assertEqual(summary.status, "succeeded")

        mutations = (
            lambda value: value.pop("frozenAtMeaning"),
            lambda value: value.__setitem__(
                "frozenAtMeaning",
                "runner_was_already_final",
            ),
            lambda value: value.__setitem__(
                "finalizedAt",
                "2026-07-11T00:00:00+00:00",
            ),
            lambda value: value.__setitem__(
                "finalizedAt",
                "2026-07-10T22:35:19Z",
            ),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                self.tearDown()
                self.setUp()

                def update_invalid_chronology(value: dict[str, object]) -> None:
                    value.update(valid_chronology)
                    mutate(value)

                self._replace_source_contract(update_invalid_chronology)
                opener = self._success_opener()

                error = self._capture_run_error(lambda: self._run(opener))

                self.assertEqual(error.code, "SOURCE_CONTRACT_INVALID")
                self.assertEqual(opener.requests, [])

    def test_v12_source_contract_semantics_are_exact_and_fail_closed(self) -> None:
        baseline = self._run(self._success_opener())
        self.assertEqual(baseline.status, "succeeded")
        mutations = (
            lambda value: value["supersedes"].__setitem__(
                "sha256", "0" * 64
            ),
            lambda value: value.__setitem__(
                "frozenAt", "2026-07-10T22:35:21Z"
            ),
            lambda value: value["provider"].__setitem__(
                "rawSha256", "0" * 64
            ),
            lambda value: value["metadataFailClosed"]["safeExtraFields"].append(
                "unreviewedField"
            ),
            lambda value: value["rawLineage"].__setitem__(
                "captureBeforeDomainParsing", False
            ),
            lambda value: value["qualityEvidence"].__setitem__(
                "runnerTestsPassed", 65
            ),
            lambda value: value["allowedRequests"].append(
                {
                    "method": "GET",
                    "path": "/api/v1/candles",
                    "purpose": "premature_price_open",
                }
            ),
            lambda value: value["deferredUntilSampleFreeze"][0].__setitem__(
                "reason", "changed_after_freeze"
            ),
            lambda value: value["credentialBoundary"].__setitem__(
                "pathClass", "external_local_0600_real_regular_file"
            ),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                self.tearDown()
                self.setUp()
                self._replace_source_contract(mutate)
                opener = self._success_opener()

                with self.assertRaises(RUNNER.MetadataRunError) as raised:
                    self._run(opener)

                self.assertEqual(
                    raised.exception.code,
                    "SOURCE_CONTRACT_INVALID",
                )
                self.assertEqual(opener.requests, [])

    def test_decoy_execution_sources_are_rejected_before_authentication(self) -> None:
        for role in (
            "runner",
            "collector",
            "selection",
            "local_evidence",
            "sensitive_policy",
        ):
            with self.subTest(role=role):
                self.tearDown()
                self.setUp()
                self._bind_decoy_execution_source(role)
                opener = self._success_opener()

                with self.assertRaises(RUNNER.MetadataRunError) as raised:
                    self._run(opener)

                self.assertEqual(
                    raised.exception.code,
                    "EXECUTION_SOURCE_MISMATCH",
                )
                self.assertEqual(opener.requests, [])
                self.assertEqual(self._json_files(), ())

    def test_runner_source_hash_mismatch_is_rejected_before_authentication(self) -> None:
        object.__setattr__(
            self.arguments,
            "runner_source_sha256",
            "0" * 64,
        )
        opener = self._success_opener()

        with self.assertRaises(RUNNER.MetadataRunError) as raised:
            self._run(opener)

        self.assertEqual(raised.exception.code, "INPUT_HASH_MISMATCH")
        self.assertEqual(opener.requests, [])

    def test_source_contract_hash_mismatch_is_rejected_before_authentication(self) -> None:
        object.__setattr__(
            self.arguments,
            "source_contract_sha256",
            "0" * 64,
        )
        opener = self._success_opener()

        with self.assertRaises(RUNNER.MetadataRunError) as raised:
            self._run(opener)

        self.assertEqual(raised.exception.code, "INPUT_HASH_MISMATCH")
        self.assertEqual(opener.requests, [])

    def test_source_contract_authorization_or_binding_mutation_fails_before_auth(self) -> None:
        cases = (
            lambda value: value["exposureState"].__setitem__(
                "ordersAccountsAssetsAccessed", True
            ),
            lambda value: value["bindings"]["collector"].__setitem__(
                "sourceSha256", "f" * 64
            ),
            lambda value: value["liveTransportGate"].__setitem__(
                "automaticRedirects", "allowed"
            ),
            lambda value: value["bindings"]["runner"].__setitem__(
                "sourceSha256", "f" * 64
            ),
            lambda value: value.__setitem__(
                "canonicalLedgerPath",
                "research/rp-001/local-ledgers/alternate",
            ),
        )
        for mutator in cases:
            with self.subTest(mutator=mutator):
                self.tearDown()
                self.setUp()
                self._replace_source_contract(mutator)
                opener = self._success_opener()

                with self.assertRaises(RUNNER.MetadataRunError) as raised:
                    self._run(opener)

                self.assertEqual(
                    raised.exception.code,
                    "SOURCE_CONTRACT_INVALID",
                )
                self.assertEqual(opener.requests, [])

    def test_hash_mismatch_is_rejected_before_authentication(self) -> None:
        object.__setattr__(
            self.arguments,
            "collector_source_sha256",
            "0" * 64,
        )
        opener = self._success_opener()

        with self.assertRaises(RUNNER.MetadataRunError) as raised:
            self._run(opener)

        self.assertEqual(raised.exception.code, "INPUT_HASH_MISMATCH")
        self.assertEqual(opener.requests, [])
        self.assertEqual(self._json_files(), ())

    def test_noncanonical_or_sidecar_mismatched_design_is_rejected_before_auth(self) -> None:
        design_path = self.repository_root / self.arguments.sample_design_path
        design_path.write_bytes(design_path.read_bytes() + b"\n")
        object.__setattr__(
            self.arguments,
            "sample_design_sha256",
            sha256_path(design_path),
        )
        opener = self._success_opener()

        with self.assertRaises(RUNNER.MetadataRunError) as raised:
            self._run(opener)

        self.assertEqual(raised.exception.code, "FROZEN_INPUT_INVALID")
        self.assertEqual(opener.requests, [])

    def test_price_opened_status_or_changed_pool_is_rejected_before_auth(self) -> None:
        cases = (
            lambda value: value.__setitem__("status", "metadata_opened"),
            lambda value: value["exposureState"].__setitem__(
                "priceVolumeOutcomePerformanceOpened", True
            ),
            lambda value: value.__setitem__(
                "candidatePool", list(CANDIDATE_POOL[:-1])
            ),
            lambda value: value["formulaBinding"].__setitem__(
                "sha256", "f" * 64
            ),
        )
        for mutator in cases:
            with self.subTest(mutator=mutator):
                self.tearDown()
                self.setUp()
                self._replace_sample_design(mutator)
                opener = self._success_opener()

                with self.assertRaises(RUNNER.MetadataRunError) as raised:
                    self._run(opener)

                self.assertEqual(raised.exception.code, "SAMPLE_DESIGN_INVALID")
                self.assertEqual(opener.requests, [])

    def test_existing_output_is_rejected_before_authentication(self) -> None:
        existing = self.output_directory / self.arguments.run_id / "raw-metadata.json"
        existing.parent.mkdir(parents=True)
        existing.write_text("existing", encoding="utf-8")
        opener = self._success_opener()

        with self.assertRaises(RUNNER.MetadataRunError) as raised:
            self._run(opener)

        self.assertEqual(raised.exception.code, "OUTPUT_ALREADY_EXISTS")
        self.assertEqual(opener.requests, [])


class RepositoryPathAndRunLockPreflightTest(MetadataRunnerFixture):
    def test_input_intermediate_symlink_resolving_outside_repository_is_rejected(self) -> None:
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        outside_root = Path(outside.name)
        source = self.repository_root / self.arguments.source_contract_path
        shutil.copyfile(source, outside_root / "source-contract.json")
        shutil.copyfile(
            Path(f"{source}.sha256"),
            outside_root / "source-contract.json.sha256",
        )
        alias = self.repository_root / "external-input-alias"
        alias.symlink_to(outside_root, target_is_directory=True)
        object.__setattr__(
            self.arguments,
            "source_contract_path",
            Path("external-input-alias/source-contract.json"),
        )
        opener = self._success_opener()

        with self.assertRaises(RUNNER.MetadataRunError) as raised:
            self._run(opener)

        self.assertEqual(raised.exception.code, "INPUT_PATH_INVALID")
        self.assertEqual(opener.requests, [])

    def test_input_intermediate_symlink_resolving_inside_uses_canonical_lineage(self) -> None:
        alias = self.repository_root / "internal-input-alias"
        alias.symlink_to(
            self.repository_root / "research/rp-001/contracts",
            target_is_directory=True,
        )
        object.__setattr__(
            self.arguments,
            "source_contract_path",
            Path(
                "internal-input-alias/toss-read-only-source-contract-v1.2.json"
            ),
        )
        opener = self._success_opener()

        self._run(opener)

        manifest = json.loads(
            (
                self.output_directory
                / self.arguments.run_id
                / "manifest.json"
            ).read_text(encoding="utf-8")
        )
        lineage = {
            value["role"]: value for value in manifest["sourceLineage"]
        }
        self.assertEqual(
            lineage["source_contract"]["path"],
            "research/rp-001/contracts/toss-read-only-source-contract-v1.2.json",
        )

    def test_output_intermediate_symlink_is_rejected_for_inside_and_outside_targets(self) -> None:
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        inside_target = self.repository_root / "real-output"
        inside_target.mkdir()
        for name, target in (
            ("inside-output-alias", inside_target),
            ("outside-output-alias", Path(outside.name)),
        ):
            with self.subTest(name=name):
                alias = self.repository_root / name
                alias.symlink_to(target, target_is_directory=True)
                object.__setattr__(
                    self.arguments,
                    "output_directory",
                    Path(name),
                )
                opener = self._success_opener()

                with self.assertRaises(RUNNER.MetadataRunError) as raised:
                    self._run(opener)

                self.assertEqual(raised.exception.code, "OUTPUT_PATH_INVALID")
                self.assertEqual(opener.requests, [])

    def test_ledger_intermediate_symlink_and_arbitrary_directory_are_rejected(self) -> None:
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        self.ledger_directory.mkdir(parents=True)
        cases = (
            (
                "inside-ledger-alias",
                self.ledger_directory,
                Path("inside-ledger-alias"),
            ),
            (
                "outside-ledger-alias",
                Path(outside.name),
                Path("outside-ledger-alias"),
            ),
        )
        for name, target, argument_path in cases:
            with self.subTest(name=name):
                alias = self.repository_root / name
                alias.symlink_to(target, target_is_directory=True)
                object.__setattr__(
                    self.arguments,
                    "ledger_directory",
                    argument_path,
                )
                opener = self._success_opener()

                with self.assertRaises(RUNNER.MetadataRunError) as raised:
                    self._run(opener)

                self.assertEqual(raised.exception.code, "LEDGER_PATH_INVALID")
                self.assertEqual(opener.requests, [])
                object.__setattr__(
                    self.arguments,
                    "ledger_directory",
                    Path("research/rp-001/local-ledgers/interim-program"),
                )

        object.__setattr__(
            self.arguments,
            "ledger_directory",
            Path("research/rp-001/local-ledgers/alternate"),
        )
        opener = self._success_opener()
        with self.assertRaises(RUNNER.MetadataRunError) as raised:
            self._run(opener)
        self.assertEqual(raised.exception.code, "LEDGER_PATH_INVALID")
        self.assertEqual(opener.requests, [])

    def test_existing_run_directory_is_rejected_even_when_empty(self) -> None:
        run_directory = self.output_directory / self.arguments.run_id
        run_directory.mkdir(parents=True)
        opener = self._success_opener()

        with self.assertRaises(RUNNER.MetadataRunError) as raised:
            self._run(opener)

        self.assertEqual(raised.exception.code, "OUTPUT_ALREADY_EXISTS")
        self.assertEqual(opener.requests, [])


class LockedNamespaceIdentityTest(MetadataRunnerFixture):
    def test_terminal_gate_rejects_preexisting_opposite_artifact_names(self) -> None:
        with self.subTest(case="failure_before_success"):
            original_select = RUNNER._select_sample
            published_pairs: list[str] = []

            def select_after_failure_injection(*args: object) -> object:
                selection = original_select(*args)
                failure_path = (
                    self.output_directory
                    / self.arguments.run_id
                    / "failure.json"
                )
                failure_path.write_text("{}", encoding="utf-8")
                return selection

            def observe_pairs(operation: str, target: str) -> None:
                if operation == "pair_published" and target.startswith(
                    "artifact:"
                ):
                    published_pairs.append(target)

            with (
                mock.patch.object(
                    RUNNER,
                    "_select_sample",
                    select_after_failure_injection,
                ),
                mock.patch.object(
                    RUNNER,
                    "_run_lifecycle_observer",
                    observe_pairs,
                ),
            ):
                error = self._capture_run_error(
                    lambda: self._run(self._success_opener())
                )

            self.assertEqual(error.code, "EVIDENCE_PUBLICATION_FAILED")
            self.assertEqual(published_pairs, [])
            self.assertEqual(
                tuple((self.ledger_directory / "events").glob("*.json")),
                (),
            )

        with self.subTest(case="success_before_failure"):
            self.tearDown()
            self.setUp()
            original_publish_failure = RUNNER._publish_terminal_failure

            def publish_after_success_injection(**kwargs: object) -> object:
                run_paths = kwargs["run_paths"]
                run_paths.raw.write_text("{}", encoding="utf-8")
                return original_publish_failure(**kwargs)

            opener = RecordingOpener(
                (
                    FakeUrlResponse(
                        401,
                        {"Content-Type": "application/json"},
                        b'{"error":"denied"}',
                    ),
                )
            )
            with mock.patch.object(
                RUNNER,
                "_publish_terminal_failure",
                publish_after_success_injection,
            ):
                error = self._capture_run_error(lambda: self._run(opener))

            self.assertEqual(error.code, "EVIDENCE_PUBLICATION_FAILED")
            run_directory = self.output_directory / self.arguments.run_id
            self.assertFalse((run_directory / "failure.json").exists())
            self.assertEqual(
                tuple((self.ledger_directory / "events").glob("*.json")),
                (),
            )

    def test_post_commit_artifact_tamper_appends_invalidation_and_fails(self) -> None:
        cases = (
            ("raw-metadata.json", "raw-metadata", "body_hash_mismatch"),
            ("manifest.json", "manifest", "body_hash_mismatch"),
            ("unexpected.json", "run_directory", "unexpected_entry"),
        )
        for filename, expected_role, expected_category in cases:
            with self.subTest(filename=filename):
                self.tearDown()
                self.setUp()
                tampered = False

                def tamper_after_success_event(
                    operation: str,
                    target: str,
                ) -> None:
                    nonlocal tampered
                    if (
                        not tampered
                        and operation == "ledger_event_published"
                        and target == "000001.json"
                    ):
                        tampered = True
                        destination = (
                            self.output_directory
                            / self.arguments.run_id
                            / filename
                        )
                        destination.write_text(
                            '{"tampered":true}',
                            encoding="utf-8",
                        )

                opener = self._success_opener()
                with mock.patch.object(
                    RUNNER,
                    "_run_lifecycle_observer",
                    tamper_after_success_event,
                ):
                    error = self._capture_run_error(lambda: self._run(opener))

                self.assertTrue(tampered)
                self.assertEqual(error.code, "EVIDENCE_INTEGRITY_LOST")
                self.assertEqual(len(opener.requests), 2)
                events = tuple(
                    sorted((self.ledger_directory / "events").glob("*.json"))
                )
                self.assertEqual(len(events), 2)
                success_event = json.loads(events[0].read_text(encoding="utf-8"))
                invalidation_event = json.loads(
                    events[1].read_text(encoding="utf-8")
                )
                self.assertEqual(
                    success_event["eventType"],
                    "toss_metadata_collection_succeeded",
                )
                self.assertEqual(
                    invalidation_event["eventType"],
                    "toss_metadata_collection_invalidated",
                )
                self.assertEqual(
                    invalidation_event["payload"],
                    {
                        "invalidatedSuccessEventSha256": sha256_path(events[0]),
                        "mismatches": [
                            {
                                "category": expected_category,
                                "role": expected_role,
                            }
                        ],
                        "runId": self.arguments.run_id,
                    },
                )
                self.assertEqual(
                    error.artifact_hashes,
                    (
                        ("ledgerSuccessEvent", sha256_path(events[0])),
                        ("ledgerInvalidationEvent", sha256_path(events[1])),
                    ),
                )

    def test_post_commit_failure_tamper_appends_invalidation_and_fails(self) -> None:
        cases = (
            ("failure.json", "failure", "body_hash_mismatch"),
            ("failure.json.sha256", "failure", "sidecar_hash_mismatch"),
            ("unexpected.json", "run_directory", "unexpected_entry"),
        )
        for filename, expected_role, expected_category in cases:
            with self.subTest(filename=filename):
                self.tearDown()
                self.setUp()
                tampered = False

                def tamper_after_failure_event(
                    operation: str,
                    target: str,
                ) -> None:
                    nonlocal tampered
                    if (
                        not tampered
                        and operation == "ledger_event_published"
                        and target == "000001.json"
                    ):
                        tampered = True
                        destination = (
                            self.output_directory
                            / self.arguments.run_id
                            / filename
                        )
                        destination.write_text(
                            "0" * 64 + "\n"
                            if filename.endswith(".sha256")
                            else '{"tampered":true}',
                            encoding="utf-8",
                        )

                opener = RecordingOpener(
                    (
                        FakeUrlResponse(
                            401,
                            {"Content-Type": "application/json"},
                            b'{"error":"denied"}',
                        ),
                    )
                )
                with mock.patch.object(
                    RUNNER,
                    "_run_lifecycle_observer",
                    tamper_after_failure_event,
                ):
                    error = self._capture_run_error(lambda: self._run(opener))

                self.assertTrue(tampered)
                self.assertEqual(error.code, "EVIDENCE_INTEGRITY_LOST")
                self.assertEqual(len(opener.requests), 1)
                events = tuple(
                    sorted((self.ledger_directory / "events").glob("*.json"))
                )
                self.assertEqual(len(events), 2)
                failure_event = json.loads(events[0].read_text(encoding="utf-8"))
                invalidation_event = json.loads(
                    events[1].read_text(encoding="utf-8")
                )
                self.assertEqual(
                    failure_event["eventType"],
                    "toss_metadata_collection_failed",
                )
                self.assertEqual(
                    invalidation_event["eventType"],
                    "toss_metadata_collection_invalidated",
                )
                self.assertEqual(
                    invalidation_event["payload"],
                    {
                        "invalidatedTerminalEventSha256": sha256_path(events[0]),
                        "mismatches": [
                            {
                                "category": expected_category,
                                "role": expected_role,
                            }
                        ],
                        "runId": self.arguments.run_id,
                        "terminalEventType": "failure",
                    },
                )
                self.assertEqual(
                    error.artifact_hashes,
                    (
                        ("ledgerFailureEvent", sha256_path(events[0])),
                        ("ledgerInvalidationEvent", sha256_path(events[1])),
                    ),
                )

    def test_post_selection_failure_tamper_preserves_invalidation_hashes(self) -> None:
        tampered = False

        def tamper_after_failure_event(operation: str, target: str) -> None:
            nonlocal tampered
            if (
                not tampered
                and operation == "ledger_event_published"
                and target == "000001.json"
            ):
                tampered = True
                failure_path = (
                    self.output_directory
                    / self.arguments.run_id
                    / "failure.json"
                )
                failure_path.write_text(
                    '{"tampered":true}',
                    encoding="utf-8",
                )

        with (
            mock.patch.object(
                RUNNER,
                "_select_sample",
                side_effect=RUNNER.SampleSelectionContractError(
                    "FIXTURE_SELECTION_FAILURE"
                ),
            ),
            mock.patch.object(
                RUNNER,
                "_run_lifecycle_observer",
                tamper_after_failure_event,
            ),
        ):
            error = self._capture_run_error(
                lambda: self._run(self._success_opener())
            )

        self.assertTrue(tampered)
        self.assertEqual(error.code, "EVIDENCE_INTEGRITY_LOST")
        events = tuple(
            sorted((self.ledger_directory / "events").glob("*.json"))
        )
        self.assertEqual(len(events), 2)
        self.assertEqual(
            error.artifact_hashes,
            (
                ("ledgerFailureEvent", sha256_path(events[0])),
                ("ledgerInvalidationEvent", sha256_path(events[1])),
            ),
        )

    def test_output_swap_after_frozen_verification_never_rebinds_run(self) -> None:
        moved_output = self.output_directory.with_name(
            "runs-after-frozen-verification"
        )
        original_verify = RUNNER._verify_frozen_inputs
        swapped = False

        def verify_then_swap(*args: object, **kwargs: object) -> object:
            nonlocal swapped
            verified = original_verify(*args, **kwargs)
            if not swapped:
                swapped = True
                self.output_directory.rename(moved_output)
                self.output_directory.mkdir()
            return verified

        opener = self._success_opener()
        with mock.patch.object(
            RUNNER,
            "_verify_frozen_inputs",
            verify_then_swap,
        ):
            error = self._capture_run_error(lambda: self._run(opener))

        self.assertTrue(swapped)
        self.assertEqual(error.code, "NAMESPACE_IDENTITY_CHANGED")
        self.assertEqual(opener.requests, [])
        self.assertFalse(
            (self.output_directory / self.arguments.run_id).exists()
        )
        self.assertFalse(
            (moved_output / self.arguments.run_id).exists()
        )

    def test_ledger_swap_after_frozen_verification_never_restarts_history(self) -> None:
        first_summary = self._run(self._success_opener())
        self.assertEqual(first_summary.status, "succeeded")
        object.__setattr__(self.arguments, "run_id", "metadata-run-002")
        moved_ledger = self.ledger_directory.with_name(
            "interim-program-after-frozen-verification"
        )
        original_verify = RUNNER._verify_frozen_inputs
        swapped = False

        def verify_then_swap(*args: object, **kwargs: object) -> object:
            nonlocal swapped
            verified = original_verify(*args, **kwargs)
            if not swapped:
                swapped = True
                self.ledger_directory.rename(moved_ledger)
                self.ledger_directory.mkdir()
            return verified

        opener = self._success_opener()
        with mock.patch.object(
            RUNNER,
            "_verify_frozen_inputs",
            verify_then_swap,
        ):
            error = self._capture_run_error(lambda: self._run(opener))

        self.assertTrue(swapped)
        self.assertEqual(error.code, "NAMESPACE_IDENTITY_CHANGED")
        self.assertEqual(opener.requests, [])
        self.assertEqual(
            tuple(self.ledger_directory.glob("events/*.json")),
            (),
        )
        self.assertTrue((moved_ledger / "events/000001.json").is_file())
        self.assertFalse(
            (self.output_directory / "metadata-run-002").exists()
        )

    def test_repository_root_swap_after_verification_never_redirects_run(self) -> None:
        original_lock = RUNNER._exclusive_output_run_lock
        moved_repository = self.repository_root.with_name(
            f"{self.repository_root.name}-verified"
        )
        credential_relative = self.credentials_path.relative_to(
            self.repository_root
        )
        swapped = False

        @contextlib.contextmanager
        def lock_after_root_swap(
            repository_root: object,
            output_root: object,
            run_id: str,
        ) -> object:
            nonlocal swapped
            if not swapped:
                swapped = True
                self.repository_root.rename(moved_repository)
                self.repository_root.mkdir()
                redirected_credentials = (
                    self.repository_root / credential_relative
                )
                redirected_credentials.parent.mkdir(parents=True)
                redirected_credentials.write_bytes(
                    (moved_repository / credential_relative).read_bytes()
                )
                redirected_credentials.chmod(0o600)
            with original_lock(repository_root, output_root, run_id) as locked:
                yield locked

        opener = self._success_opener()
        with mock.patch.object(
            RUNNER,
            "_exclusive_output_run_lock",
            lock_after_root_swap,
        ):
            error = self._capture_run_error(lambda: self._run(opener))

        self.assertTrue(swapped)
        self.assertEqual(error.code, "NAMESPACE_IDENTITY_CHANGED")
        self.assertEqual(opener.requests, [])
        self.assertFalse(
            (
                self.repository_root
                / self.arguments.output_directory
                / self.arguments.run_id
            ).exists()
        )
        self.assertFalse(
            (
                moved_repository
                / self.arguments.output_directory
                / self.arguments.run_id
            ).exists()
        )

    def test_output_root_swap_before_lock_never_reopens_namespace(self) -> None:
        first_summary = self._run(self._success_opener())
        self.assertEqual(first_summary.status, "succeeded")
        moved_output = self.output_directory.with_name("runs-before-swap")
        original_lock = RUNNER._exclusive_output_run_lock
        swapped = False

        @contextlib.contextmanager
        def lock_after_output_swap(*args: object, **kwargs: object) -> object:
            nonlocal swapped
            if not swapped:
                swapped = True
                self.output_directory.rename(moved_output)
                self.output_directory.mkdir()
            with original_lock(*args, **kwargs) as locked:
                yield locked

        opener = self._success_opener()
        with mock.patch.object(
            RUNNER,
            "_exclusive_output_run_lock",
            lock_after_output_swap,
        ):
            error = self._capture_run_error(lambda: self._run(opener))

        self.assertTrue(swapped)
        self.assertEqual(error.code, "NAMESPACE_IDENTITY_CHANGED")
        self.assertEqual(opener.requests, [])
        self.assertFalse(
            (self.output_directory / self.arguments.run_id).exists()
        )
        self.assertTrue(
            (moved_output / self.arguments.run_id / "manifest.json").is_file()
        )

    def test_ledger_root_swap_before_lock_never_restarts_history(self) -> None:
        first_summary = self._run(self._success_opener())
        self.assertEqual(first_summary.status, "succeeded")
        object.__setattr__(self.arguments, "run_id", "metadata-run-002")
        moved_ledger = self.ledger_directory.with_name(
            "interim-program-before-swap"
        )
        original_lock = RUNNER._exclusive_ledger_lock
        swapped = False

        @contextlib.contextmanager
        def lock_after_ledger_swap(*args: object, **kwargs: object) -> object:
            nonlocal swapped
            if not swapped:
                swapped = True
                self.ledger_directory.rename(moved_ledger)
                self.ledger_directory.mkdir()
            with original_lock(*args, **kwargs) as locked:
                yield locked

        opener = self._success_opener()
        with mock.patch.object(
            RUNNER,
            "_exclusive_ledger_lock",
            lock_after_ledger_swap,
        ):
            error = self._capture_run_error(lambda: self._run(opener))

        self.assertTrue(swapped)
        self.assertEqual(error.code, "NAMESPACE_IDENTITY_CHANGED")
        self.assertEqual(opener.requests, [])
        self.assertEqual(
            tuple(self.ledger_directory.glob("events/*.json")),
            (),
        )
        self.assertTrue((moved_ledger / "events/000001.json").is_file())
        self.assertFalse(
            (self.output_directory / "metadata-run-002").exists()
        )

    def test_lock_file_replacement_cannot_start_a_second_same_run(self) -> None:
        entered = threading.Event()
        release = threading.Event()
        first_source = self._success_opener()
        first_opener = BlockingOpener(first_source.responses, entered, release)
        first_results: list[object] = []
        first_errors: list[BaseException] = []
        second_results: list[object] = []
        second_errors: list[BaseException] = []

        def run_first() -> None:
            try:
                first_results.append(self._run(first_opener))
            except BaseException as error:
                first_errors.append(error)

        first_thread = threading.Thread(target=run_first)
        first_thread.start()
        self.assertTrue(entered.wait(timeout=2.0))
        output_locks = tuple(
            (self.output_directory / ".rp001-metadata-run-locks").glob(
                "*.lock"
            )
        )
        self.assertEqual(len(output_locks), 1)
        lock_paths = (
            output_locks[0],
            self.ledger_directory / ".freeze-interim-scope.lock",
        )
        for lock_path in lock_paths:
            detached = lock_path.with_name(f"{lock_path.name}.detached")
            lock_path.rename(detached)
            lock_path.write_bytes(b"")
            lock_path.chmod(0o600)

        second_opener = self._success_opener()

        def run_second() -> None:
            try:
                second_results.append(self._run(second_opener))
            except BaseException as error:
                second_errors.append(error)

        second_thread = threading.Thread(target=run_second)
        second_thread.start()
        time.sleep(0.1)
        requests_while_first_held = tuple(second_opener.requests)
        release.set()
        first_thread.join(timeout=5.0)
        second_thread.join(timeout=5.0)

        self.assertFalse(first_thread.is_alive())
        self.assertFalse(second_thread.is_alive())
        self.assertEqual(requests_while_first_held, ())
        self.assertEqual(first_results, [])
        self.assertEqual(len(first_errors), 1)
        self.assertIsInstance(first_errors[0], RUNNER.MetadataRunError)
        self.assertEqual(first_errors[0].code, "NAMESPACE_IDENTITY_CHANGED")
        self.assertEqual(second_errors, [])
        self.assertEqual(len(second_results), 1)
        self.assertEqual(second_results[0].status, "succeeded")
        self.assertTrue(
            (
                self.output_directory
                / self.arguments.run_id
                / "manifest.json"
            ).is_file()
        )
        self.assertEqual(
            len(tuple((self.ledger_directory / "events").glob("*.json"))),
            1,
        )

    def test_ledger_lock_replacement_cannot_overlap_distinct_runs(self) -> None:
        entered = threading.Event()
        release = threading.Event()
        first_source = self._success_opener()
        first_opener = BlockingOpener(first_source.responses, entered, release)
        second_opener = self._success_opener()
        first_results: list[object] = []
        first_errors: list[BaseException] = []
        second_results: list[object] = []
        second_errors: list[BaseException] = []

        def run_first() -> None:
            try:
                first_results.append(self._run(first_opener))
            except BaseException as error:
                first_errors.append(error)

        second_arguments = dataclasses.replace(
            self.arguments,
            run_id="metadata-run-002",
        )

        def run_second() -> None:
            try:
                second_results.append(
                    RUNNER.run_metadata_collection(
                        second_arguments,
                        opener=second_opener,
                        clock=fixed_clock,
                    )
                )
            except BaseException as error:
                second_errors.append(error)

        first_thread = threading.Thread(target=run_first)
        first_thread.start()
        self.assertTrue(entered.wait(timeout=2.0))
        ledger_lock = self.ledger_directory / ".freeze-interim-scope.lock"
        detached_lock = ledger_lock.with_name(f"{ledger_lock.name}.detached")
        ledger_lock.rename(detached_lock)
        ledger_lock.write_bytes(b"")
        ledger_lock.chmod(0o600)
        second_thread = threading.Thread(target=run_second)
        second_thread.start()
        time.sleep(0.1)
        requests_while_first_held = tuple(second_opener.requests)
        release.set()
        first_thread.join(timeout=5.0)
        second_thread.join(timeout=5.0)

        self.assertFalse(first_thread.is_alive())
        self.assertFalse(second_thread.is_alive())
        self.assertEqual(requests_while_first_held, ())
        self.assertEqual(first_results, [])
        self.assertEqual(len(first_errors), 1)
        self.assertIsInstance(first_errors[0], RUNNER.MetadataRunError)
        self.assertEqual(first_errors[0].code, "NAMESPACE_IDENTITY_CHANGED")
        self.assertEqual(second_errors, [])
        self.assertEqual(len(second_results), 1)
        self.assertEqual(second_results[0].status, "succeeded")

    def test_ledger_root_replacement_cannot_split_concurrent_runs(self) -> None:
        first_summary = self._run(self._success_opener())
        self.assertEqual(first_summary.status, "succeeded")
        blocked_arguments = dataclasses.replace(
            self.arguments,
            run_id="metadata-run-002",
        )
        replacement_arguments = dataclasses.replace(
            self.arguments,
            run_id="metadata-run-003",
        )
        entered = threading.Event()
        release = threading.Event()
        blocked_source = self._success_opener()
        blocked_opener = BlockingOpener(
            blocked_source.responses,
            entered,
            release,
        )
        replacement_opener = self._success_opener()
        blocked_results: list[object] = []
        blocked_errors: list[BaseException] = []
        replacement_results: list[object] = []
        replacement_errors: list[BaseException] = []

        def run_blocked() -> None:
            try:
                blocked_results.append(
                    RUNNER.run_metadata_collection(
                        blocked_arguments,
                        opener=blocked_opener,
                        clock=fixed_clock,
                    )
                )
            except BaseException as error:
                blocked_errors.append(error)

        def run_replacement() -> None:
            try:
                replacement_results.append(
                    RUNNER.run_metadata_collection(
                        replacement_arguments,
                        opener=replacement_opener,
                        clock=fixed_clock,
                    )
                )
            except BaseException as error:
                replacement_errors.append(error)

        blocked_thread = threading.Thread(target=run_blocked)
        blocked_thread.start()
        self.assertTrue(entered.wait(timeout=2.0))
        moved_ledger = self.ledger_directory.with_name(
            "interim-program-concurrent-original"
        )
        self.ledger_directory.rename(moved_ledger)
        self.ledger_directory.mkdir()
        replacement_thread = threading.Thread(target=run_replacement)
        replacement_thread.start()
        time.sleep(0.1)
        requests_while_blocked = tuple(replacement_opener.requests)
        release.set()
        blocked_thread.join(timeout=5.0)
        replacement_thread.join(timeout=5.0)

        self.assertFalse(blocked_thread.is_alive())
        self.assertFalse(replacement_thread.is_alive())
        self.assertEqual(requests_while_blocked, ())
        self.assertEqual(blocked_results, [])
        self.assertEqual(len(blocked_errors), 1)
        self.assertIsInstance(blocked_errors[0], RUNNER.MetadataRunError)
        self.assertEqual(
            blocked_errors[0].code,
            "NAMESPACE_IDENTITY_CHANGED",
        )
        self.assertEqual(replacement_errors, [])
        self.assertEqual(len(replacement_results), 1)
        self.assertEqual(replacement_results[0].status, "succeeded")
        self.assertTrue((moved_ledger / "events/000001.json").is_file())
        self.assertTrue(
            (self.ledger_directory / "events/000001.json").is_file()
        )

    def test_repository_clone_cannot_split_concurrent_runs(self) -> None:
        entered = threading.Event()
        release = threading.Event()
        blocked_source = self._success_opener()
        blocked_opener = BlockingOpener(
            blocked_source.responses,
            entered,
            release,
        )
        replacement_opener = self._success_opener()
        blocked_results: list[object] = []
        blocked_errors: list[BaseException] = []
        replacement_results: list[object] = []
        replacement_errors: list[BaseException] = []
        replacement_arguments = dataclasses.replace(
            self.arguments,
            run_id="metadata-run-002",
        )

        def run_blocked() -> None:
            try:
                blocked_results.append(self._run(blocked_opener))
            except BaseException as error:
                blocked_errors.append(error)

        def run_replacement() -> None:
            try:
                replacement_results.append(
                    RUNNER.run_metadata_collection(
                        replacement_arguments,
                        opener=replacement_opener,
                        clock=fixed_clock,
                    )
                )
            except BaseException as error:
                replacement_errors.append(error)

        blocked_thread = threading.Thread(target=run_blocked)
        blocked_thread.start()
        self.assertTrue(entered.wait(timeout=2.0))
        moved_repository = self.repository_root.with_name(
            f"{self.repository_root.name}-concurrent-original"
        )
        self.addCleanup(shutil.rmtree, moved_repository, True)
        self.repository_root.rename(moved_repository)
        shutil.copytree(moved_repository, self.repository_root, symlinks=True)
        replacement_thread = threading.Thread(target=run_replacement)
        replacement_thread.start()
        time.sleep(0.1)
        requests_while_blocked = tuple(replacement_opener.requests)
        release.set()
        blocked_thread.join(timeout=5.0)
        replacement_thread.join(timeout=5.0)

        self.assertFalse(blocked_thread.is_alive())
        self.assertFalse(replacement_thread.is_alive())
        self.assertEqual(requests_while_blocked, ())
        self.assertEqual(blocked_results, [])
        self.assertEqual(len(blocked_errors), 1)
        self.assertIsInstance(blocked_errors[0], RUNNER.MetadataRunError)
        self.assertEqual(
            blocked_errors[0].code,
            "NAMESPACE_IDENTITY_CHANGED",
        )
        self.assertEqual(replacement_errors, [])
        self.assertEqual(len(replacement_results), 1)
        self.assertEqual(replacement_results[0].status, "succeeded")
        self.assertTrue(
            (
                self.output_directory
                / "metadata-run-002"
                / "manifest.json"
            ).is_file()
        )

    def test_existing_events_swap_during_auth_never_restarts_ledger(self) -> None:
        first_summary = self._run(self._success_opener())
        self.assertEqual(first_summary.status, "succeeded")
        original_events = self.ledger_directory / "events"
        self.assertTrue((original_events / "000001.json").is_file())
        object.__setattr__(
            self.arguments,
            "run_id",
            "metadata-run-002",
        )
        entered = threading.Event()
        release = threading.Event()
        source = self._success_opener()
        opener = BlockingOpener(source.responses, entered, release)
        results: list[object] = []
        errors: list[BaseException] = []

        def run_second() -> None:
            try:
                results.append(self._run(opener))
            except BaseException as error:
                errors.append(error)

        thread = threading.Thread(target=run_second)
        thread.start()
        self.assertTrue(entered.wait(timeout=2.0))
        moved_events = self.ledger_directory / "events-before-swap"
        original_events.rename(moved_events)
        original_events.mkdir()
        release.set()
        thread.join(timeout=5.0)

        self.assertFalse(thread.is_alive())
        self.assertEqual(results, [])
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], RUNNER.MetadataRunError)
        self.assertEqual(errors[0].code, "NAMESPACE_IDENTITY_CHANGED")
        self.assertEqual(tuple(original_events.glob("*.json")), ())
        self.assertTrue((moved_events / "000001.json").is_file())
        self.assertFalse(
            (self.output_directory / "metadata-run-002").exists()
        )

    def test_child_swap_after_body_prevents_sidecar_and_pair_completion(self) -> None:
        for namespace in ("run", "events"):
            with self.subTest(namespace=namespace):
                self.tearDown()
                self.setUp()
                outside = Path(tempfile.mkdtemp())
                self.addCleanup(shutil.rmtree, outside, True)
                moved = outside / f"moved-{namespace}"
                redirect = outside / f"redirect-{namespace}"
                redirect.mkdir()
                swapped = False
                pair_completed_after_swap = False

                def swap_after_body(operation: str, target: str) -> None:
                    nonlocal swapped, pair_completed_after_swap
                    expected_target = (
                        "artifact:raw-metadata.json"
                        if namespace == "run"
                        else "ledger:000001"
                    )
                    if operation == "pair_published" and target == expected_target:
                        pair_completed_after_swap = swapped
                    if (
                        not swapped
                        and operation == "pair_body_published"
                        and target == expected_target
                    ):
                        swapped = True
                        child = (
                            self.output_directory / self.arguments.run_id
                            if namespace == "run"
                            else self.ledger_directory / "events"
                        )
                        child.rename(moved)
                        child.symlink_to(redirect, target_is_directory=True)

                with mock.patch.object(
                    RUNNER,
                    "_run_lifecycle_observer",
                    swap_after_body,
                ):
                    error = self._capture_run_error(
                        lambda: self._run(self._success_opener())
                    )

                self.assertTrue(swapped)
                self.assertFalse(pair_completed_after_swap)
                self.assertEqual(error.code, "NAMESPACE_IDENTITY_CHANGED")
                self.assertEqual(tuple(moved.rglob("*.json")), ())
                self.assertEqual(tuple(moved.rglob("*.sha256")), ())
                self.assertEqual(tuple(redirect.rglob("*")), ())

    def test_locked_root_replacement_before_guard_is_rejected_for_output_and_ledger(self) -> None:
        for namespace in ("output", "ledger"):
            with self.subTest(namespace=namespace):
                self.tearDown()
                self.setUp()
                target = (
                    self.output_directory
                    if namespace == "output"
                    else self.ledger_directory
                )
                moved = self.repository_root / f"moved-locked-{namespace}"
                swapped = False

                def replace_after_locks(operation: str, label: str) -> None:
                    nonlocal swapped
                    if operation == "locks_acquired" and not swapped:
                        swapped = True
                        target.rename(moved)
                        target.mkdir(parents=True)

                opener = self._success_opener()
                with mock.patch.object(
                    RUNNER,
                    "_run_lifecycle_observer",
                    replace_after_locks,
                ):
                    error = self._capture_run_error(
                        lambda: self._run(opener)
                    )

                self.assertTrue(swapped)
                self.assertEqual(error.code, "NAMESPACE_IDENTITY_CHANGED")
                self.assertEqual(opener.requests, [])
                self.assertFalse(
                    (self.output_directory / self.arguments.run_id).exists()
                )
                self.assertEqual(tuple(moved.rglob("*.json")), ())

    def test_run_directory_swap_after_raw_pair_leaves_no_external_artifact(self) -> None:
        outside = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, outside, True)
        moved_run = outside / "moved-run-inode"
        redirect = outside / "redirected-run"
        redirect.mkdir()
        swapped = False

        def swap_run_directory(operation: str, target: str) -> None:
            nonlocal swapped
            if (
                not swapped
                and operation == "pair_published"
                and target == "artifact:raw-metadata.json"
            ):
                swapped = True
                run_directory = self.output_directory / self.arguments.run_id
                run_directory.rename(moved_run)
                run_directory.symlink_to(redirect, target_is_directory=True)

        with mock.patch.object(
            RUNNER,
            "_run_lifecycle_observer",
            swap_run_directory,
        ):
            error = self._capture_run_error(
                lambda: self._run(self._success_opener())
            )

        self.assertTrue(swapped)
        self.assertEqual(error.code, "NAMESPACE_IDENTITY_CHANGED")
        self.assertEqual(tuple(moved_run.rglob("*.json")), ())
        self.assertEqual(tuple(moved_run.rglob("*.sha256")), ())
        self.assertEqual(tuple(redirect.rglob("*")), ())
        self.assertEqual(
            tuple((self.ledger_directory / "events").glob("*.json")),
            (),
        )

    def test_events_directory_swap_before_append_leaves_no_external_event(self) -> None:
        outside = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, outside, True)
        moved_events = outside / "moved-events-inode"
        redirect = outside / "redirected-events"
        redirect.mkdir()
        swapped = False

        def swap_events_directory(operation: str, target: str) -> None:
            nonlocal swapped
            if operation == "before_ledger_append" and not swapped:
                swapped = True
                events = self.ledger_directory / "events"
                events.rename(moved_events)
                events.symlink_to(redirect, target_is_directory=True)

        with mock.patch.object(
            RUNNER,
            "_run_lifecycle_observer",
            swap_events_directory,
        ):
            error = self._capture_run_error(
                lambda: self._run(self._success_opener())
            )

        self.assertTrue(swapped)
        self.assertEqual(error.code, "NAMESPACE_IDENTITY_CHANGED")
        self.assertEqual(tuple(moved_events.rglob("*.json")), ())
        self.assertEqual(tuple(moved_events.rglob("*.sha256")), ())
        self.assertEqual(tuple(redirect.rglob("*")), ())
        self.assertFalse(
            (self.output_directory / self.arguments.run_id).exists()
        )

    def test_output_root_rename_and_symlink_swap_leaves_no_external_artifacts(self) -> None:
        outside = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, outside, True)
        moved_output = self.repository_root / "moved-output-root"
        original_acquire = RUNNER._acquire_metadata_no_raise

        def acquire_after_swap(*arguments: object) -> object:
            self.output_directory.rename(moved_output)
            self.output_directory.symlink_to(outside, target_is_directory=True)
            return original_acquire(*arguments)

        opener = self._success_opener()
        with mock.patch.object(
            RUNNER,
            "_acquire_metadata_no_raise",
            acquire_after_swap,
        ):
            error = self._capture_run_error(lambda: self._run(opener))

        self.assertEqual(error.code, "NAMESPACE_IDENTITY_CHANGED")
        self.assertEqual(tuple(outside.rglob("*.json")), ())
        self.assertEqual(tuple(outside.rglob("*.sha256")), ())
        self.assertFalse((moved_output / self.arguments.run_id).exists())
        self.assertEqual(
            tuple((self.ledger_directory / "events").glob("*.json")),
            (),
        )

    def test_ledger_rename_and_symlink_swap_leaves_no_external_events_or_run(self) -> None:
        outside = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, outside, True)
        moved_ledger = self.repository_root / "moved-canonical-ledger"
        original_acquire = RUNNER._acquire_metadata_no_raise

        def acquire_after_swap(*arguments: object) -> object:
            self.ledger_directory.rename(moved_ledger)
            self.ledger_directory.symlink_to(outside, target_is_directory=True)
            return original_acquire(*arguments)

        opener = self._success_opener()
        with mock.patch.object(
            RUNNER,
            "_acquire_metadata_no_raise",
            acquire_after_swap,
        ):
            error = self._capture_run_error(lambda: self._run(opener))

        self.assertEqual(error.code, "NAMESPACE_IDENTITY_CHANGED")
        self.assertEqual(tuple(outside.rglob("*.json")), ())
        self.assertEqual(tuple(outside.rglob("*.sha256")), ())
        self.assertEqual(tuple((moved_ledger / "events").glob("*.json")), ())
        self.assertFalse(
            (self.output_directory / self.arguments.run_id).exists()
        )

    def test_output_swap_after_artifact_pair_cleans_the_pinned_run_inode(self) -> None:
        outside = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, outside, True)
        moved_output = self.repository_root / "moved-output-after-publish"
        swapped = False

        def swap_after_pair(operation: str, target: str) -> None:
            nonlocal swapped
            if (
                not swapped
                and operation == "pair_published"
                and target == "artifact:raw-metadata.json"
            ):
                swapped = True
                self.output_directory.rename(moved_output)
                self.output_directory.symlink_to(
                    outside,
                    target_is_directory=True,
                )

        with mock.patch.object(
            RUNNER,
            "_run_lifecycle_observer",
            swap_after_pair,
        ):
            error = self._capture_run_error(
                lambda: self._run(self._success_opener())
            )

        self.assertEqual(error.code, "NAMESPACE_IDENTITY_CHANGED")
        self.assertTrue(swapped)
        self.assertFalse((moved_output / self.arguments.run_id).exists())
        self.assertEqual(tuple(outside.rglob("*.json")), ())
        self.assertEqual(
            tuple((self.ledger_directory / "events").glob("*.json")),
            (),
        )

    def test_ledger_swap_immediately_before_append_never_creates_an_event(self) -> None:
        outside = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, outside, True)
        moved_ledger = self.repository_root / "moved-ledger-before-append"
        swapped = False

        def swap_before_append(operation: str, target: str) -> None:
            nonlocal swapped
            if not swapped and operation == "before_ledger_append":
                swapped = True
                self.ledger_directory.rename(moved_ledger)
                self.ledger_directory.symlink_to(
                    outside,
                    target_is_directory=True,
                )

        with mock.patch.object(
            RUNNER,
            "_run_lifecycle_observer",
            swap_before_append,
        ):
            error = self._capture_run_error(
                lambda: self._run(self._success_opener())
            )

        self.assertEqual(error.code, "NAMESPACE_IDENTITY_CHANGED")
        self.assertTrue(swapped)
        self.assertEqual(tuple((moved_ledger / "events").glob("*.json")), ())
        self.assertEqual(tuple(outside.rglob("*.json")), ())
        self.assertFalse(
            (self.output_directory / self.arguments.run_id).exists()
        )

    def test_output_swap_during_rollback_still_removes_the_exact_empty_run(self) -> None:
        outside = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, outside, True)
        moved_output = self.repository_root / "moved-output-during-rollback"
        swapped = False

        def swap_during_rollback(operation: str, target: str) -> None:
            nonlocal swapped
            if not swapped and operation == "artifact_rolled_back":
                swapped = True
                self.output_directory.rename(moved_output)
                self.output_directory.symlink_to(
                    outside,
                    target_is_directory=True,
                )

        with mock.patch.object(
            RUNNER,
            "_run_lifecycle_observer",
            swap_during_rollback,
        ):
            error = self._capture_run_error(
                lambda: self._run(
                    self._success_opener(),
                    ledger_factory=lambda _path: FailingLedger(),
                )
            )

        self.assertEqual(error.code, "NAMESPACE_IDENTITY_CHANGED")
        self.assertTrue(swapped)
        self.assertFalse((moved_output / self.arguments.run_id).exists())
        self.assertEqual(tuple(outside.rglob("*.json")), ())
        self.assertEqual(
            tuple((self.ledger_directory / "events").glob("*.json")),
            (),
        )


class OutputRunLockConcurrencyTest(MetadataRunnerFixture):
    def test_same_output_run_is_serialized_without_relying_on_ledger_lock(self) -> None:
        entered = threading.Event()
        release = threading.Event()
        first = self._success_opener()
        first_opener = BlockingOpener(first.responses, entered, release)
        second_opener = self._success_opener()
        results: list[object] = []
        errors: list[BaseException] = []
        second_started = threading.Event()

        def run_first() -> None:
            try:
                results.append(self._run(first_opener))
            except BaseException as error:
                errors.append(error)

        def run_second() -> None:
            second_started.set()
            try:
                results.append(self._run(second_opener))
            except BaseException as error:
                errors.append(error)

        @contextlib.contextmanager
        def no_ledger_lock(
            _repository_root: Path,
            _path: Path,
        ) -> Iterator[None]:
            yield

        with mock.patch.object(RUNNER, "_exclusive_ledger_lock", no_ledger_lock):
            first_thread = threading.Thread(target=run_first)
            second_thread = threading.Thread(target=run_second)
            first_thread.start()
            self.assertTrue(entered.wait(timeout=2.0))
            second_thread.start()
            self.assertTrue(second_started.wait(timeout=2.0))
            time.sleep(0.1)
            second_request_count_while_first_held = len(second_opener.requests)
            release.set()
            first_thread.join(timeout=5.0)
            second_thread.join(timeout=5.0)

        self.assertFalse(first_thread.is_alive())
        self.assertFalse(second_thread.is_alive())
        self.assertEqual(second_request_count_while_first_held, 0)
        self.assertEqual(len(results), 1)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], RUNNER.MetadataRunError)
        self.assertEqual(errors[0].code, "OUTPUT_ALREADY_EXISTS")
        self.assertEqual(len(first_opener.requests), 2)
        self.assertEqual(len(second_opener.requests), 0)
        self.assertEqual(
            len(tuple((self.ledger_directory / "events").glob("*.json"))),
            1,
        )
        run_directory = self.output_directory / self.arguments.run_id
        self.assertFalse((run_directory / "failure.json").exists())
        lock_paths = tuple(
            (self.output_directory / ".rp001-metadata-run-locks").glob("*.lock")
        )
        self.assertEqual(len(lock_paths), 1)
        self.assertEqual(stat.S_IMODE(os.lstat(lock_paths[0]).st_mode), 0o600)

    def test_alternate_ledger_cannot_bypass_same_output_run_namespace(self) -> None:
        entered = threading.Event()
        release = threading.Event()
        first = self._success_opener()
        first_opener = BlockingOpener(first.responses, entered, release)
        alternate_opener = self._success_opener()
        alternate_arguments = dataclasses.replace(
            self.arguments,
            ledger_directory=Path(
                "research/rp-001/local-ledgers/alternate"
            ),
        )
        first_results: list[object] = []
        first_errors: list[BaseException] = []

        def run_first() -> None:
            try:
                first_results.append(self._run(first_opener))
            except BaseException as error:
                first_errors.append(error)

        first_thread = threading.Thread(target=run_first)
        first_thread.start()
        self.assertTrue(entered.wait(timeout=2.0))

        with self.assertRaises(RUNNER.MetadataRunError) as raised:
            RUNNER.run_metadata_collection(
                alternate_arguments,
                opener=alternate_opener,
                clock=fixed_clock,
            )

        self.assertEqual(raised.exception.code, "LEDGER_PATH_INVALID")
        self.assertEqual(alternate_opener.requests, [])
        release.set()
        first_thread.join(timeout=5.0)

        self.assertFalse(first_thread.is_alive())
        self.assertEqual(first_errors, [])
        self.assertEqual(len(first_results), 1)
        self.assertEqual(
            len(tuple((self.ledger_directory / "events").glob("*.json"))),
            1,
        )
        run_directory = self.output_directory / self.arguments.run_id
        self.assertEqual(
            {path.name for path in run_directory.glob("*.json")},
            {
                "raw-metadata.json",
                "processed-metadata.json",
                "sample-selection.json",
                "metadata-exposure.json",
                "manifest.json",
            },
        )
        self.assertFalse((run_directory / "failure.json").exists())


class CredentialBoundaryTest(MetadataRunnerFixture):
    def test_lexically_external_alias_into_repository_private_is_rejected(self) -> None:
        private_credential = self.repository_root / "private/credentials.json"
        private_credential.parent.mkdir()
        private_credential.write_bytes(self.credentials_path.read_bytes())
        private_credential.chmod(0o600)
        external = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, external, True)
        (external / "repository-private").symlink_to(
            private_credential.parent,
            target_is_directory=True,
        )
        object.__setattr__(
            self.arguments,
            "credentials_path",
            external / "repository-private/credentials.json",
        )
        opener = self._success_opener()

        error = self._capture_run_error(lambda: self._run(opener))

        self.assertEqual(error.code, "CREDENTIAL_PATH_INVALID")
        self.assertEqual(opener.requests, [])

    def test_dot_storage_swap_before_read_never_uses_redirected_credentials(self) -> None:
        external = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, external, True)
        redirected_storage = external / "redirected-storage"
        redirected_storage.mkdir()
        redirected_credential = redirected_storage / self.credentials_path.name
        redirected_credential.write_bytes(self.credentials_path.read_bytes())
        redirected_credential.chmod(0o600)
        moved_storage = self.repository_root / "moved-original-storage"
        original_load = RUNNER._load_credentials
        swapped = False

        def load_after_swap(value: object) -> object:
            nonlocal swapped
            if not swapped:
                swapped = True
                self.credentials_path.parent.rename(moved_storage)
                self.credentials_path.parent.symlink_to(
                    redirected_storage,
                    target_is_directory=True,
                )
            return original_load(value)

        opener = self._success_opener()
        with mock.patch.object(
            RUNNER,
            "_load_credentials",
            load_after_swap,
        ):
            error = self._capture_run_error(lambda: self._run(opener))

        self.assertTrue(swapped)
        self.assertEqual(error.code, "CREDENTIAL_PATH_INVALID")
        self.assertEqual(opener.requests, [])

    def test_repository_internal_credentials_are_allowed_only_below_dot_storage(self) -> None:
        source = self.credentials_path.read_bytes()
        for relative_path in (
            Path("private/credentials.json"),
            Path("research/rp-001/credentials.json"),
        ):
            with self.subTest(relative_path=relative_path):
                self.tearDown()
                self.setUp()
                destination = self.repository_root / relative_path
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(source)
                destination.chmod(0o600)
                object.__setattr__(
                    self.arguments,
                    "credentials_path",
                    destination,
                )
                opener = self._success_opener()

                with self.assertRaises(RUNNER.MetadataRunError) as raised:
                    self._run(opener)

                self.assertEqual(
                    raised.exception.code,
                    "CREDENTIAL_PATH_INVALID",
                )
                self.assertEqual(opener.requests, [])

    def test_dot_storage_intermediate_symlink_is_rejected_before_authentication(self) -> None:
        real_storage = self.repository_root / "real-storage"
        self.credentials_path.parent.rename(real_storage)
        self.credentials_path.parent.symlink_to(
            real_storage,
            target_is_directory=True,
        )
        opener = self._success_opener()

        with self.assertRaises(RUNNER.MetadataRunError) as raised:
            self._run(opener)

        self.assertEqual(raised.exception.code, "CREDENTIAL_PATH_INVALID")
        self.assertEqual(opener.requests, [])

    def test_external_credentials_are_rejected_before_authentication(self) -> None:
        external = tempfile.TemporaryDirectory()
        self.addCleanup(external.cleanup)
        external_path = Path(external.name) / "credentials.json"
        external_path.write_bytes(self.credentials_path.read_bytes())
        external_path.chmod(0o600)
        object.__setattr__(
            self.arguments,
            "credentials_path",
            external_path,
        )

        opener = self._success_opener()

        error = self._capture_run_error(lambda: self._run(opener))

        self.assertEqual(error.code, "CREDENTIAL_PATH_INVALID")
        self.assertEqual(opener.requests, [])

    def test_credentials_must_be_real_regular_mode_0600(self) -> None:
        self.credentials_path.chmod(0o640)
        opener = self._success_opener()

        with self.assertRaises(RUNNER.MetadataRunError) as raised:
            self._run(opener)

        self.assertEqual(raised.exception.code, "CREDENTIAL_FILE_INVALID")
        self.assertEqual(opener.requests, [])

    def test_credential_symlink_is_rejected_without_reading_target(self) -> None:
        target = self.credentials_path
        link = self.repository_root / ".storage/credential-link.json"
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(target)
        object.__setattr__(self.arguments, "credentials_path", link)
        opener = self._success_opener()

        with self.assertRaises(RUNNER.MetadataRunError) as raised:
            self._run(opener)

        self.assertEqual(raised.exception.code, "CREDENTIAL_FILE_INVALID")
        self.assertEqual(opener.requests, [])

    def test_empty_or_wrong_typed_credentials_are_rejected_without_disclosure(self) -> None:
        for case in ("missing", "empty_identifier", "wrong_private_type"):
            with self.subTest(case=case):
                self.tearDown()
                self.setUp()
                identifier_field = "".join(("client", "Id"))
                private_field = "".join(("client", "Secret"))
                invalid_body: dict[str, object]
                if case == "missing":
                    invalid_body = {}
                elif case == "empty_identifier":
                    invalid_body = {
                        identifier_field: "",
                        private_field: self.private_credential,
                    }
                else:
                    invalid_body = {
                        identifier_field: self.client_identifier,
                        private_field: 7,
                    }
                self.credentials_path.write_text(
                    json.dumps(invalid_body), encoding="utf-8"
                )
                opener = self._success_opener()

                with self.assertRaises(RUNNER.MetadataRunError) as raised:
                    self._run(opener)

                rendered = "".join(
                    traceback.format_exception(raised.exception)
                )
                self.assertEqual(raised.exception.code, "CREDENTIAL_FILE_INVALID")
                self.assertNotIn(self.private_credential, rendered)
                self.assertNotIn(self.client_identifier, rendered)
                self.assertEqual(opener.requests, [])

    def test_auth_error_traceback_does_not_retain_credential_values(self) -> None:
        opener = RecordingOpener((OSError(self.private_credential),))

        error = self._capture_run_error(lambda: self._run(opener))

        exposed = traceback_exposed_strings(error)
        self.assertFalse(
            any(self.client_identifier in value for value in exposed)
        )
        self.assertFalse(
            any(self.private_credential in value for value in exposed)
        )


class MetadataOnlyNetworkBoundaryTest(MetadataRunnerFixture):
    def test_success_uses_exact_oauth_post_then_one_exact_stocks_get(self) -> None:
        opener = self._success_opener()

        summary = self._run(opener)

        self.assertEqual(summary.status, "succeeded")
        self.assertEqual(len(opener.requests), 2)
        auth_request, metadata_request = opener.requests
        self.assertEqual(auth_request.get_method(), "POST")
        self.assertEqual(
            auth_request.full_url,
            "https://openapi.tossinvest.com/oauth2/token",
        )
        self.assertEqual(
            auth_request.data,
            (
                "grant_type=client_credentials"
                f"&client_id={self.client_identifier}"
                f"&client_secret={self.private_credential}"
            ).encode("ascii"),
        )
        self.assertEqual(
            auth_request.headers["Content-type"],
            "application/x-www-form-urlencoded",
        )
        self.assertEqual(metadata_request.get_method(), "GET")
        self.assertEqual(
            metadata_request.full_url,
            "https://openapi.tossinvest.com/api/v1/stocks?symbols="
            + "%2C".join(CANDIDATE_POOL),
        )
        self.assertEqual(
            parse_qs(metadata_request.full_url.split("?", 1)[1]),
            {"symbols": [",".join(CANDIDATE_POOL)]},
        )
        self.assertTrue(
            metadata_request.headers["Authorization"].startswith("Bearer ")
        )

    def test_transport_rejects_every_non_stocks_endpoint_without_opening(self) -> None:
        opener = RecordingOpener(())
        transport = RUNNER.UrllibMetadataTransport(opener=opener, timeout_seconds=5.0)
        forbidden_urls = (
            "https://openapi.tossinvest.com/api/v1/candles?symbol=AAPL",
            "https://openapi.tossinvest.com/api/v1/orders",
            "https://openapi.tossinvest.com/api/v1/accounts",
            "https://openapi.tossinvest.com/api/v1/assets",
            "https://example.com/api/v1/stocks?symbols=AAPL",
        )
        for url in forbidden_urls:
            with self.subTest(url=url):
                request = RUNNER.HttpRequest(
                    method="GET",
                    url=url,
                    headers={
                        "Accept": "application/json",
                        "Authorization": f"Bearer {self.ephemeral_bearer}",
                    },
                )
                with self.assertRaises(RUNNER.MetadataRunError) as raised:
                    transport(request)
                self.assertEqual(raised.exception.code, "ENDPOINT_NOT_ALLOWED")
        self.assertEqual(opener.requests, [])

    def test_direct_transport_error_traceback_does_not_retain_authorization(self) -> None:
        opener = RecordingOpener(())
        transport = RUNNER.UrllibMetadataTransport(opener=opener, timeout_seconds=5.0)
        request = RUNNER.HttpRequest(
            method="GET",
            url="https://openapi.tossinvest.com/api/v1/orders",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self.ephemeral_bearer}",
            },
        )

        error = self._capture_run_error(lambda: transport(request))

        self.assertFalse(
            any(
                self.ephemeral_bearer in value
                for value in traceback_exposed_strings(error)
            )
        )

    def test_http_error_is_returned_as_exact_response_without_redirect_follow(self) -> None:
        body = b'{"error":"temporarily_unavailable"}'
        redirect_error = HTTPError(
            "https://openapi.tossinvest.com/api/v1/stocks?symbols=AAPL",
            302,
            "redirect",
            {"Content-Type": "application/json", "Location": "https://example.com"},
            io.BytesIO(body),
        )
        opener = RecordingOpener((redirect_error,))
        transport = RUNNER.UrllibMetadataTransport(opener=opener, timeout_seconds=5.0)
        request = RUNNER.HttpRequest(
            method="GET",
            url="https://openapi.tossinvest.com/api/v1/stocks?symbols=AAPL",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self.ephemeral_bearer}",
            },
        )

        response = transport(request)

        self.assertEqual(response.status, 302)
        self.assertEqual(response.body, body)
        self.assertEqual(len(opener.requests), 1)


class BoundedResponseReadTest(MetadataRunnerFixture):
    OAUTH_LIMIT = 1024 * 1024
    METADATA_LIMIT = 2 * 1024 * 1024

    def _exact_oauth_body(self) -> tuple[bytes, str]:
        field_name = "_".join(("access", "token"))
        empty = json.dumps(
            {field_name: ""}, separators=(",", ":")
        ).encode("utf-8")
        ephemeral = "z" * (self.OAUTH_LIMIT - len(empty))
        body = json.dumps(
            {field_name: ephemeral}, separators=(",", ":")
        ).encode("utf-8")
        self.assertEqual(len(body), self.OAUTH_LIMIT)
        return body, ephemeral

    def _exact_metadata_body(self) -> bytes:
        rows = [self._metadata_row(symbol) for symbol in CANDIDATE_POOL]
        rows[0]["koreanMarketDetail"] = ""
        empty = json.dumps(
            {"result": rows},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        rows[0]["koreanMarketDetail"] = "x" * (
            self.METADATA_LIMIT - len(empty)
        )
        body = json.dumps(
            {"result": rows},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        self.assertEqual(len(body), self.METADATA_LIMIT)
        return body

    def test_fragmented_auth_and_metadata_are_read_exactly_to_eof(self) -> None:
        auth_body = self._success_opener().responses[0]._body
        auth_response = FragmentedUrlResponse(
            200,
            {"Content-Type": "application/json"},
            (auth_body[:7], auth_body[7:19], auth_body[19:]),
        )
        metadata_response = FragmentedUrlResponse(
            200,
            {"Content-Type": "application/json"},
            (
                self.metadata_body[:11],
                self.metadata_body[11:101],
                self.metadata_body[101:],
            ),
        )
        opener = RecordingOpener((auth_response, metadata_response))

        summary = self._run(opener)

        self.assertEqual(summary.status, "succeeded")
        self.assertEqual(len(auth_response.read_sizes), 4)
        self.assertEqual(len(metadata_response.read_sizes), 4)
        raw = json.loads(
            (
                self.output_directory
                / self.arguments.run_id
                / "raw-metadata.json"
            ).read_text(encoding="utf-8")
        )
        captured = base64.b64decode(raw["capture"]["bodyBase64"])
        self.assertEqual(captured, self.metadata_body)
        self.assertEqual(
            raw["capture"]["bodySha256"],
            hashlib.sha256(self.metadata_body).hexdigest(),
        )

    def test_fragmented_limit_plus_one_stops_at_bound_and_is_terminal(self) -> None:
        chunks = (
            b"x" * 300_000,
            b"y" * 400_000,
            b"z" * (self.OAUTH_LIMIT + 1 - 700_000),
            b"must-not-be-read",
        )
        response = FragmentedUrlResponse(
            200,
            {"Content-Type": "application/json"},
            chunks,
        )
        opener = RecordingOpener((response,))

        error = self._capture_run_error(lambda: self._run(opener))

        self.assertEqual(error.code, "AUTH_RESPONSE_TOO_LARGE")
        self.assertEqual(len(response.read_sizes), 3)
        self.assertEqual(self._failure_body()["captures"], [])

    def test_exact_oauth_and_metadata_limits_succeed_with_bounded_reads(self) -> None:
        auth_body, ephemeral = self._exact_oauth_body()
        metadata_body = self._exact_metadata_body()
        auth_response = FakeUrlResponse(
            200,
            {"Content-Type": "application/json", "Content-Length": "1"},
            auth_body,
        )
        metadata_response = FakeUrlResponse(
            200,
            {
                "Content-Type": "application/json",
                "Content-Length": str(self.METADATA_LIMIT + 1000),
            },
            metadata_body,
        )
        opener = RecordingOpener((auth_response, metadata_response))

        summary = self._run(opener)

        self.assertEqual(summary.status, "succeeded")
        self.assertEqual(
            auth_response.read_sizes,
            [self.OAUTH_LIMIT + 1, 1],
        )
        self.assertEqual(
            metadata_response.read_sizes,
            [self.METADATA_LIMIT + 1, 1],
        )
        self.assertNotIn(
            ephemeral,
            "".join(
                path.read_text(encoding="utf-8") for path in self._json_files()
            ),
        )

    def test_oauth_limit_plus_one_is_terminal_without_partial_body(self) -> None:
        response = FakeUrlResponse(
            200,
            {"Content-Type": "application/json", "Content-Length": "1"},
            b"x" * (self.OAUTH_LIMIT + 1),
        )
        opener = RecordingOpener((response,))

        error = self._capture_run_error(lambda: self._run(opener))

        self.assertEqual(error.code, "AUTH_RESPONSE_TOO_LARGE")
        self.assertEqual(response.read_sizes, [self.OAUTH_LIMIT + 1])
        failure = self._failure_body()
        self.assertEqual(failure["stage"], "auth")
        self.assertTrue(failure["requestAttempted"])
        self.assertTrue(failure["responseReceived"])
        self.assertFalse(failure["metadataOpened"])
        self.assertTrue(failure["rawResponseOmitted"])
        self.assertEqual(failure["captures"], [])

    def test_metadata_limit_plus_one_ignores_content_length_and_omits_partial_raw(self) -> None:
        auth_response = self._success_opener().responses[0]
        private_marker = json.dumps(
            {
                "".join(("client", "Secret")): self.private_credential,
            },
            separators=(",", ":"),
        ).encode("utf-8")
        oversized = private_marker + b"x" * (
            self.METADATA_LIMIT + 1 - len(private_marker)
        )
        metadata_response = FakeUrlResponse(
            200,
            {"Content-Type": "application/json", "Content-Length": "1"},
            oversized,
        )
        opener = RecordingOpener((auth_response, metadata_response))

        error = self._capture_run_error(lambda: self._run(opener))

        self.assertEqual(error.code, "METADATA_RESPONSE_TOO_LARGE")
        self.assertEqual(
            metadata_response.read_sizes,
            [self.METADATA_LIMIT + 1],
        )
        failure = self._failure_body()
        self.assertEqual(failure["stage"], "metadata")
        self.assertTrue(failure["requestAttempted"])
        self.assertTrue(failure["responseReceived"])
        self.assertEqual(failure["metadataOpened"], "unknown")
        self.assertTrue(failure["rawResponseOmitted"])
        self.assertEqual(failure["captures"], [])
        persisted = "".join(
            path.read_text(encoding="utf-8") for path in self._json_files()
        )
        self.assertNotIn(self.private_credential, persisted)
        self.assertFalse(
            any(
                self.private_credential in value
                for value in traceback_exposed_strings(error)
            )
        )

    def test_oauth_http_error_limit_plus_one_is_bounded_and_terminal(self) -> None:
        body_stream = RecordingBytesIO(b"x" * (self.OAUTH_LIMIT + 1))
        opener = RecordingOpener(
            (
                HTTPError(
                    "https://openapi.tossinvest.com/oauth2/token",
                    401,
                    "unauthorized",
                    {"Content-Type": "application/json"},
                    body_stream,
                ),
            )
        )

        error = self._capture_run_error(lambda: self._run(opener))

        self.assertEqual(error.code, "AUTH_RESPONSE_TOO_LARGE")
        self.assertEqual(body_stream.read_sizes, [self.OAUTH_LIMIT + 1])
        self.assertEqual(self._failure_body()["captures"], [])

    def test_metadata_http_error_limit_plus_one_is_bounded_without_capture(self) -> None:
        auth_response = self._success_opener().responses[0]
        body_stream = RecordingBytesIO(b"x" * (self.METADATA_LIMIT + 1))
        opener = RecordingOpener(
            (
                auth_response,
                HTTPError(
                    "https://openapi.tossinvest.com/api/v1/stocks",
                    503,
                    "unavailable",
                    {"Content-Type": "application/json"},
                    body_stream,
                ),
            )
        )

        error = self._capture_run_error(lambda: self._run(opener))

        self.assertEqual(error.code, "METADATA_RESPONSE_TOO_LARGE")
        self.assertEqual(body_stream.read_sizes, [self.METADATA_LIMIT + 1])
        failure = self._failure_body()
        self.assertTrue(failure["responseReceived"])
        self.assertTrue(failure["rawResponseOmitted"])
        self.assertEqual(failure["captures"], [])


class SuccessEvidenceContractTest(MetadataRunnerFixture):
    def test_success_publishes_canonical_pairs_manifest_exposure_and_one_event(self) -> None:
        opener = self._success_opener()

        summary = self._run(opener)

        self.assertEqual(summary.run_id, "metadata-run-001")
        self.assertEqual(summary.record_count, len(CANDIDATE_POOL))
        self.assertEqual(
            summary.selected_symbols,
            ("AMZN", "CAT", "XOM", "AAPL", "AMD", "COST"),
        )
        run_directory = self.output_directory / self.arguments.run_id
        expected_names = {
            "raw-metadata.json",
            "processed-metadata.json",
            "sample-selection.json",
            "metadata-exposure.json",
            "manifest.json",
        }
        self.assertEqual(
            {path.name for path in run_directory.glob("*.json")},
            expected_names,
        )
        for path in run_directory.glob("*.json"):
            self._assert_sidecar(path)

        raw_body = json.loads(
            (run_directory / "raw-metadata.json").read_text(encoding="utf-8")
        )
        capture = raw_body["capture"]
        self.assertEqual(base64.b64decode(capture["bodyBase64"]), self.metadata_body)
        self.assertEqual(capture["bodySha256"], hashlib.sha256(self.metadata_body).hexdigest())
        self.assertEqual(capture["status"], 200)
        self.assertEqual(capture["receivedAt"], "2026-07-11T01:02:03Z")
        self.assertNotIn("set-cookie", dict(capture["headers"]))

        processed = json.loads(
            (run_directory / "processed-metadata.json").read_text(encoding="utf-8")
        )
        self.assertEqual(processed["recordCount"], len(CANDIDATE_POOL))
        self.assertEqual(
            {record["symbol"] for record in processed["records"]},
            set(CANDIDATE_POOL),
        )
        exposure = json.loads(
            (run_directory / "metadata-exposure.json").read_text(encoding="utf-8")
        )
        self.assertEqual(exposure["sampleRole"], "metadata_only")
        self.assertTrue(exposure["metadataOpened"])
        self.assertFalse(exposure["priceVolumeOutcomePerformanceOpened"])

        manifest = json.loads(
            (run_directory / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["status"], "succeeded")
        self.assertEqual(manifest["request"]["endpointId"], "stocks_metadata_v1")
        self.assertEqual(len(manifest["publishedArtifacts"]), 4)
        source_lineage = {
            binding["role"]: binding for binding in manifest["sourceLineage"]
        }
        self.assertEqual(
            source_lineage["source_contract"],
            {
                "role": "source_contract",
                "path": str(self.arguments.source_contract_path),
                "sha256": self.arguments.source_contract_sha256,
            },
        )
        self.assertEqual(
            source_lineage["runner_source"]["sha256"],
            self.arguments.runner_source_sha256,
        )
        self.assertEqual(
            source_lineage["runner_test"]["sha256"],
            self.arguments.runner_test_sha256,
        )
        self.assertEqual(
            {binding["path"] for binding in manifest["publishedArtifacts"]},
            {
                str(path.relative_to(self.repository_root))
                for path in run_directory.glob("*.json")
                if path.name != "manifest.json"
            },
        )

        event_path = self.ledger_directory / "events/000001.json"
        self._assert_sidecar(event_path)
        event = json.loads(event_path.read_text(encoding="utf-8"))
        self.assertEqual(event["eventType"], "toss_metadata_collection_succeeded")
        self.assertEqual(event["previousRecordSha256"], None)
        self.assertEqual(event["payload"]["runId"], self.arguments.run_id)

    def test_no_credential_or_token_appears_in_files_summary_or_exception_text(self) -> None:
        opener = self._success_opener()

        summary = self._run(opener)

        rendered = repr(summary)
        for path in self._json_files():
            rendered += path.read_text(encoding="utf-8")
        for private_value in (
            self.client_identifier,
            self.private_credential,
            self.ephemeral_bearer,
        ):
            self.assertNotIn(private_value, rendered)
        self.assertEqual(find_sensitive_values(rendered), ())

    def test_ledger_failure_rolls_back_every_success_and_failure_pair(self) -> None:
        opener = self._success_opener()

        with self.assertRaises(RUNNER.MetadataRunError) as raised:
            self._run(opener, ledger_factory=lambda _path: FailingLedger())

        self.assertEqual(raised.exception.code, "EVIDENCE_PUBLICATION_FAILED")
        self.assertEqual(tuple(self.output_directory.rglob("*.json")), ())
        self.assertEqual(tuple(self.output_directory.rglob("*.sha256")), ())
        self.assertFalse(
            (self.output_directory / self.arguments.run_id).exists()
        )
        self.assertEqual(
            tuple((self.ledger_directory / "events").glob("*.json")),
            (),
        )

        retry = self._run(self._success_opener())

        self.assertEqual(retry.status, "succeeded")


class EvidenceTransactionInterruptionTest(MetadataRunnerFixture):
    def test_base_exception_after_each_success_pair_rolls_back_to_failure_terminal(self) -> None:
        for interrupt_at in range(1, 6):
            with self.subTest(interrupt_at=interrupt_at):
                self.tearDown()
                self.setUp()
                interruption: BaseException
                if interrupt_at % 2:
                    interruption = KeyboardInterrupt("fixture publication interrupt")
                else:
                    interruption = SystemExit("fixture publication interrupt")
                store = InterruptAfterArtifactPublishStore(
                    self.repository_root,
                    interrupt_at,
                    interruption,
                )

                error = self._capture_any_error(
                    lambda: self._run(
                        self._success_opener(),
                        artifact_store_factory=lambda: store,
                    )
                )

                self.assertIsInstance(error, RUNNER.MetadataRunError)
                self.assertEqual(error.code, "RUN_INTERRUPTED")
                run_directory = self.output_directory / self.arguments.run_id
                self.assertEqual(
                    {path.name for path in run_directory.glob("*.json")},
                    {"failure.json"},
                )
                self._assert_sidecar(run_directory / "failure.json")
                event_paths = tuple(
                    (self.ledger_directory / "events").glob("*.json")
                )
                self.assertEqual(len(event_paths), 1)
                event = json.loads(event_paths[0].read_text(encoding="utf-8"))
                self.assertEqual(
                    event["eventType"],
                    "toss_metadata_collection_failed",
                )

    def test_body_only_interrupt_is_removed_before_failure_terminal(self) -> None:
        store = InterruptAfterPartialArtifactBodyStore(self.repository_root)

        error = self._capture_any_error(
            lambda: self._run(
                self._success_opener(),
                artifact_store_factory=lambda: store,
            )
        )

        self.assertIsInstance(error, RUNNER.MetadataRunError)
        self.assertEqual(error.code, "RUN_INTERRUPTED")
        run_directory = self.output_directory / self.arguments.run_id
        self.assertEqual(
            {path.name for path in run_directory.iterdir()},
            {"failure.json", "failure.json.sha256"},
        )

    def test_interrupt_after_durable_success_event_reconciles_committed_success(self) -> None:
        summary = self._run(
            self._success_opener(),
            ledger_factory=InterruptAfterAppendLedger,
        )

        self.assertEqual(summary.status, "succeeded")
        run_directory = self.output_directory / self.arguments.run_id
        self.assertEqual(
            {path.name for path in run_directory.glob("*.json")},
            {
                "raw-metadata.json",
                "processed-metadata.json",
                "sample-selection.json",
                "metadata-exposure.json",
                "manifest.json",
            },
        )
        events = tuple((self.ledger_directory / "events").glob("*.json"))
        self.assertEqual(len(events), 1)
        event = json.loads(events[0].read_text(encoding="utf-8"))
        self.assertEqual(event["eventType"], "toss_metadata_collection_succeeded")
        self.assertEqual(event["sequence"], 1)

    def test_interrupt_after_durable_failure_event_reconciles_committed_failure(self) -> None:
        opener = RecordingOpener((OSError("fixture auth failure"),))

        error = self._capture_run_error(
            lambda: self._run(
                opener,
                ledger_factory=InterruptAfterAppendLedger,
            )
        )

        self.assertEqual(error.code, "AUTH_TRANSPORT_ERROR")
        self.assertEqual(
            {name for name, _digest in error.artifact_hashes},
            {"failure", "ledgerEvent"},
        )
        run_directory = self.output_directory / self.arguments.run_id
        self.assertEqual(
            {path.name for path in run_directory.glob("*.json")},
            {"failure.json"},
        )
        event_path = self.ledger_directory / "events/000001.json"
        event = json.loads(event_path.read_text(encoding="utf-8"))
        self.assertEqual(event["eventType"], "toss_metadata_collection_failed")
        self.assertEqual(event["payload"]["runId"], self.arguments.run_id)


class FailureEvidenceContractTest(MetadataRunnerFixture):
    def test_every_post_preflight_terminal_failure_binds_verified_source_lineage(self) -> None:
        for scenario in (
            "auth",
            "metadata_no_response",
            "sensitive_omitted",
            "selection",
            "evidence",
        ):
            with self.subTest(scenario=scenario):
                self.tearDown()
                self.setUp()
                dependencies: dict[str, object] = {}
                patcher: contextlib.AbstractContextManager[object]
                patcher = contextlib.nullcontext()
                if scenario == "auth":
                    opener = RecordingOpener((OSError("fixture auth failure"),))
                elif scenario == "metadata_no_response":
                    opener = RecordingOpener(
                        (
                            self._success_opener().responses[0],
                            OSError("fixture GET failure"),
                        )
                    )
                elif scenario == "sensitive_omitted":
                    body = json.dumps(
                        {
                            "result": [],
                            "".join(("client", "Secret")): (
                                self.private_credential
                            ),
                        },
                        separators=(",", ":"),
                    ).encode("utf-8")
                    opener = RecordingOpener(
                        (
                            self._success_opener().responses[0],
                            FakeUrlResponse(
                                200,
                                {"Content-Type": "application/json"},
                                body,
                            ),
                        )
                    )
                elif scenario == "selection":
                    opener = self._success_opener()
                    patcher = mock.patch.object(
                        RUNNER,
                        "_select_sample",
                        side_effect=RUNNER.SampleSelectionContractError(
                            "FIXTURE_SELECTION_FAILURE"
                        ),
                    )
                else:
                    opener = self._success_opener()
                    dependencies["artifact_store_factory"] = lambda: (
                        FailFirstArtifactPublishStore(self.repository_root)
                    )

                with patcher:
                    self._capture_run_error(
                        lambda: self._run(opener, **dependencies)
                    )

                failure = self._failure_body()
                self.assertEqual(
                    failure["sourceLineage"],
                    self._expected_source_lineage(),
                )
                event = json.loads(
                    (
                        self.ledger_directory / "events/000001.json"
                    ).read_text(encoding="utf-8")
                )
                self.assertEqual(
                    event["payload"]["sourceLineage"],
                    self._expected_source_lineage(),
                )

    def test_metadata_transport_without_response_records_terminal_failure(self) -> None:
        auth_response = self._success_opener().responses[0]
        opener = RecordingOpener(
            (auth_response, OSError("provider detail must be sanitized"))
        )

        error = self._capture_run_error(lambda: self._run(opener))

        self.assertEqual(error.code, "METADATA_TRANSPORT_ERROR")
        failure = self._failure_body()
        self.assertEqual(failure["stage"], "metadata")
        self.assertTrue(failure["requestAttempted"])
        self.assertFalse(failure["responseReceived"])
        self.assertFalse(failure["metadataOpened"])
        self.assertFalse(failure["rawResponseOmitted"])
        self.assertEqual(failure["captures"], [])

    def test_clock_failure_after_response_records_terminal_unknown_raw_omission(self) -> None:
        opener = self._success_opener()

        def invalid_clock() -> datetime:
            raise ValueError("clock fixture detail")

        error = self._capture_run_error(
            lambda: RUNNER.run_metadata_collection(
                self.arguments,
                opener=opener,
                clock=invalid_clock,
            )
        )

        self.assertEqual(error.code, "CLOCK_INVALID")
        failure = self._failure_body()
        self.assertEqual(failure["stage"], "metadata")
        self.assertTrue(failure["requestAttempted"])
        self.assertTrue(failure["responseReceived"])
        self.assertTrue(failure["metadataOpened"])
        self.assertTrue(failure["rawResponseOmitted"])
        self.assertEqual(failure["captures"], [])
        datetime.fromisoformat(failure["failedAt"].replace("Z", "+00:00"))

    def test_invalid_metadata_http_response_records_terminal_failure(self) -> None:
        auth_response = self._success_opener().responses[0]
        invalid_response = FakeUrlResponse(
            99,
            {"Content-Type": "application/json"},
            b"{}",
        )
        opener = RecordingOpener((auth_response, invalid_response))

        error = self._capture_run_error(lambda: self._run(opener))

        self.assertEqual(error.code, "METADATA_TRANSPORT_ERROR")
        failure = self._failure_body()
        self.assertEqual(failure["stage"], "metadata")
        self.assertTrue(failure["requestAttempted"])
        self.assertTrue(failure["responseReceived"])
        self.assertEqual(failure["metadataOpened"], "unknown")
        self.assertTrue(failure["rawResponseOmitted"])
        self.assertEqual(failure["captures"], [])

    def test_oauth_keyboard_interrupt_is_sanitized_without_secret_traceback(self) -> None:
        opener = RecordingOpener((KeyboardInterrupt(),))

        error = self._capture_any_error(lambda: self._run(opener))

        self.assertIsInstance(error, RUNNER.MetadataRunError)
        self.assertEqual(error.code, "RUN_INTERRUPTED")
        exposed = traceback_exposed_strings(error)
        for private_value in (
            self.client_identifier,
            self.private_credential,
            self.ephemeral_bearer,
        ):
            self.assertFalse(
                any(private_value in value for value in exposed)
            )
        failure = self._failure_body()
        self.assertEqual(failure["stage"], "auth")
        self.assertTrue(failure["requestAttempted"])
        self.assertFalse(failure["responseReceived"])
        self.assertFalse(failure["metadataOpened"])
        self.assertEqual(failure["captures"], [])

    def test_get_keyboard_interrupt_is_sanitized_without_token_or_authorization(self) -> None:
        auth_response = self._success_opener().responses[0]
        opener = RecordingOpener((auth_response, KeyboardInterrupt()))

        error = self._capture_any_error(lambda: self._run(opener))

        self.assertIsInstance(error, RUNNER.MetadataRunError)
        self.assertEqual(error.code, "RUN_INTERRUPTED")
        exposed = traceback_exposed_strings(error)
        for private_value in (
            self.client_identifier,
            self.private_credential,
            self.ephemeral_bearer,
            f"Bearer {self.ephemeral_bearer}",
        ):
            self.assertFalse(
                any(private_value in value for value in exposed)
            )
        failure = self._failure_body()
        self.assertEqual(failure["stage"], "metadata")
        self.assertTrue(failure["requestAttempted"])
        self.assertFalse(failure["responseReceived"])
        self.assertFalse(failure["metadataOpened"])
        self.assertEqual(failure["captures"], [])

    def test_safe_post_response_failure_preserves_capture_and_terminal_event(self) -> None:
        auth_response = self._success_opener().responses[0]
        invalid_body = b'{"result":[]}'
        opener = RecordingOpener(
            (
                auth_response,
                FakeUrlResponse(
                    200,
                    {"Content-Type": "application/json"},
                    invalid_body,
                ),
            )
        )

        with self.assertRaises(RUNNER.MetadataRunError) as raised:
            self._run(opener)

        self.assertEqual(raised.exception.code, "MISSING_METADATA_SYMBOLS")
        run_directory = self.output_directory / self.arguments.run_id
        failure_path = run_directory / "failure.json"
        self._assert_sidecar(failure_path)
        self.assertEqual(
            {path.name for path in run_directory.glob("*.json")},
            {"failure.json"},
        )
        failure = json.loads(failure_path.read_text(encoding="utf-8"))
        self.assertEqual(failure["status"], "failed")
        self.assertEqual(failure["sampleRole"], "metadata_only")
        self.assertEqual(failure.get("stage"), "metadata")
        self.assertIs(failure.get("requestAttempted"), True)
        self.assertIs(failure.get("responseReceived"), True)
        self.assertIs(failure.get("metadataOpened"), True)
        self.assertIs(failure.get("sensitiveRawOmitted"), False)
        self.assertIs(failure.get("rawResponseOmitted"), False)
        self.assertEqual(len(failure["captures"]), 1)
        self.assertEqual(
            base64.b64decode(failure["captures"][0]["bodyBase64"]),
            invalid_body,
        )
        event = json.loads(
            (self.ledger_directory / "events/000001.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(event["eventType"], "toss_metadata_collection_failed")
        self.assertFalse(failure["priceVolumeOutcomePerformanceOpened"])
        self.assertFalse((run_directory / "metadata-exposure.json").exists())

    def test_post_response_error_traceback_does_not_retain_ephemeral_token(self) -> None:
        auth_response = self._success_opener().responses[0]
        opener = RecordingOpener(
            (
                auth_response,
                FakeUrlResponse(
                    200,
                    {"Content-Type": "application/json"},
                    b'{"result":[]}',
                ),
            )
        )

        error = self._capture_run_error(lambda: self._run(opener))

        exposed = traceback_exposed_strings(error)
        self.assertFalse(
            any(self.ephemeral_bearer in value for value in exposed)
        )
        self.assertFalse(
            any(self.private_credential in value for value in exposed)
        )

    def test_get_http_error_body_and_status_remain_in_safe_failure_lineage(self) -> None:
        auth_response = self._success_opener().responses[0]
        body = b'{"error":"service_unavailable"}'
        error = HTTPError(
            "https://openapi.tossinvest.com/api/v1/stocks",
            503,
            "unavailable",
            {"Content-Type": "application/json", "X-RateLimit-Remaining": "0"},
            io.BytesIO(body),
        )
        opener = RecordingOpener((auth_response, error))

        with self.assertRaises(RUNNER.MetadataRunError) as raised:
            self._run(opener)

        self.assertEqual(raised.exception.code, "HTTP_STATUS")
        failure = json.loads(
            (
                self.output_directory
                / self.arguments.run_id
                / "failure.json"
            ).read_text(encoding="utf-8")
        )
        capture = failure["captures"][0]
        self.assertEqual(capture["status"], 503)
        self.assertEqual(base64.b64decode(capture["bodyBase64"]), body)
        self.assertEqual(capture["bodySha256"], hashlib.sha256(body).hexdigest())

    def test_sensitive_current_response_is_never_published_or_disclosed(self) -> None:
        auth_response = self._success_opener().responses[0]
        sensitive_body = json.dumps(
            {
                "result": [],
                "".join(("client", "Secret")): self.private_credential,
            },
            separators=(",", ":"),
        ).encode("utf-8")
        opener = RecordingOpener(
            (
                auth_response,
                FakeUrlResponse(
                    200,
                    {"Content-Type": "application/json"},
                    sensitive_body,
                ),
            )
        )

        error = self._capture_run_error(lambda: self._run(opener))

        rendered = "".join(traceback.format_exception(error))
        self.assertEqual(error.code, "SENSITIVE_RESPONSE")
        self.assertNotIn(self.private_credential, rendered)
        self.assertNotIn(self.ephemeral_bearer, rendered)
        exposed = traceback_exposed_strings(error)
        self.assertFalse(
            any(self.private_credential in value for value in exposed)
        )
        failure = self._failure_body()
        self.assertEqual(failure["stage"], "metadata")
        self.assertTrue(failure["requestAttempted"])
        self.assertTrue(failure["responseReceived"])
        self.assertTrue(failure["metadataOpened"])
        self.assertTrue(failure["sensitiveRawOmitted"])
        self.assertTrue(failure["rawResponseOmitted"])
        self.assertEqual(failure["captures"], [])
        persisted = "".join(
            path.read_text(encoding="utf-8") for path in self._json_files()
        )
        self.assertNotIn(self.private_credential, persisted)

    def test_auth_failure_records_terminal_non_exposure_evidence(self) -> None:
        body = b'{"error":"invalid_client"}'
        opener = RecordingOpener(
            (
                HTTPError(
                    "https://openapi.tossinvest.com/oauth2/token",
                    401,
                    "unauthorized",
                    {"Content-Type": "application/json"},
                    io.BytesIO(body),
                ),
            )
        )

        with self.assertRaises(RUNNER.MetadataRunError) as raised:
            self._run(opener)

        self.assertEqual(raised.exception.code, "AUTH_HTTP_STATUS")
        failure = self._failure_body()
        self.assertEqual(failure["stage"], "auth")
        self.assertTrue(failure["requestAttempted"])
        self.assertTrue(failure["responseReceived"])
        self.assertFalse(failure["metadataOpened"])
        self.assertFalse(failure["sensitiveRawOmitted"])
        self.assertTrue(failure["rawResponseOmitted"])
        self.assertEqual(failure["captures"], [])
        event = json.loads(
            (self.ledger_directory / "events/000001.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(event["eventType"], "toss_metadata_collection_failed")


class CommandLineBoundaryTest(MetadataRunnerFixture):
    def _argv(self) -> list[str]:
        values: list[str] = []
        for option, value in (
            ("--repository-root", self.repository_root),
            ("--credentials-path", self.credentials_path),
            ("--sample-design-path", self.arguments.sample_design_path),
            ("--sample-design-sha256", self.arguments.sample_design_sha256),
            ("--formula-contract-path", self.arguments.formula_contract_path),
            ("--formula-contract-sha256", self.arguments.formula_contract_sha256),
            ("--source-contract-path", self.arguments.source_contract_path),
            ("--source-contract-sha256", self.arguments.source_contract_sha256),
            ("--runner-source-path", self.arguments.runner_source_path),
            ("--runner-source-sha256", self.arguments.runner_source_sha256),
            ("--runner-test-path", self.arguments.runner_test_path),
            ("--runner-test-sha256", self.arguments.runner_test_sha256),
            ("--formula-source-path", self.arguments.formula_source_path),
            ("--formula-source-sha256", self.arguments.formula_source_sha256),
            ("--formula-test-path", self.arguments.formula_test_path),
            ("--formula-test-sha256", self.arguments.formula_test_sha256),
            ("--collector-source-path", self.arguments.collector_source_path),
            ("--collector-source-sha256", self.arguments.collector_source_sha256),
            ("--collector-test-path", self.arguments.collector_test_path),
            ("--collector-test-sha256", self.arguments.collector_test_sha256),
            ("--selection-source-path", self.arguments.selection_source_path),
            ("--selection-source-sha256", self.arguments.selection_source_sha256),
            ("--selection-test-path", self.arguments.selection_test_path),
            ("--selection-test-sha256", self.arguments.selection_test_sha256),
            ("--local-evidence-source-path", self.arguments.local_evidence_source_path),
            ("--local-evidence-source-sha256", self.arguments.local_evidence_source_sha256),
            ("--local-evidence-test-path", self.arguments.local_evidence_test_path),
            ("--local-evidence-test-sha256", self.arguments.local_evidence_test_sha256),
            ("--sensitive-policy-source-path", self.arguments.sensitive_policy_source_path),
            ("--sensitive-policy-source-sha256", self.arguments.sensitive_policy_source_sha256),
            ("--sensitive-policy-test-path", self.arguments.sensitive_policy_test_path),
            ("--sensitive-policy-test-sha256", self.arguments.sensitive_policy_test_sha256),
            ("--output-directory", self.arguments.output_directory),
            ("--ledger-directory", self.arguments.ledger_directory),
            ("--run-id", self.arguments.run_id),
        ):
            values.extend((option, str(value)))
        return values

    def test_cli_has_only_path_hash_and_run_id_inputs(self) -> None:
        parser = RUNNER.build_argument_parser()
        destinations = {
            action.dest for action in parser._actions if action.dest != "help"
        }
        self.assertEqual(
            destinations,
            {
                "repository_root",
                "credentials_path",
                "sample_design_path",
                "sample_design_sha256",
                "formula_contract_path",
                "formula_contract_sha256",
                "source_contract_path",
                "source_contract_sha256",
                "runner_source_path",
                "runner_source_sha256",
                "runner_test_path",
                "runner_test_sha256",
                "formula_source_path",
                "formula_source_sha256",
                "formula_test_path",
                "formula_test_sha256",
                "collector_source_path",
                "collector_source_sha256",
                "collector_test_path",
                "collector_test_sha256",
                "selection_source_path",
                "selection_source_sha256",
                "selection_test_path",
                "selection_test_sha256",
                "local_evidence_source_path",
                "local_evidence_source_sha256",
                "local_evidence_test_path",
                "local_evidence_test_sha256",
                "sensitive_policy_source_path",
                "sensitive_policy_source_sha256",
                "sensitive_policy_test_path",
                "sensitive_policy_test_sha256",
                "output_directory",
                "ledger_directory",
                "run_id",
            },
        )
        help_text = parser.format_help().lower()
        self.assertNotIn("--client-id", help_text)
        self.assertNotIn("--client-secret", help_text)
        self.assertNotIn("--access-token", help_text)

    def test_unknown_secret_argument_is_rejected_without_echoing_value(self) -> None:
        parser = RUNNER.build_argument_parser()
        unknown_private_value = "".join(("unknown", "-private-", "fixture-value"))

        with self.assertRaises(RUNNER.MetadataRunError) as raised:
            parser.parse_args(
                self._argv()
                + ["--client-secret", unknown_private_value]
            )

        self.assertEqual(raised.exception.code, "INVALID_ARGUMENTS")
        self.assertNotIn(unknown_private_value, str(raised.exception))

    def test_main_stdout_is_one_canonical_summary_with_only_allowed_fields(self) -> None:
        opener = self._success_opener()
        stdout = io.StringIO()
        stderr = io.StringIO()

        exit_code = RUNNER.main(
            self._argv(),
            opener=opener,
            clock=fixed_clock,
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        line = stdout.getvalue()
        self.assertTrue(line.endswith("\n"))
        parsed = json.loads(line)
        self.assertEqual(
            set(parsed),
            {
                "runId",
                "status",
                "count",
                "selectedSymbols",
                "artifactHashes",
            },
        )
        self.assertEqual(
            line.encode("utf-8")[:-1],
            RUNNER.canonical_json_bytes(parsed),
        )
        for private_value in (
            self.client_identifier,
            self.private_credential,
            self.ephemeral_bearer,
        ):
            self.assertNotIn(private_value, line)

    def test_main_sanitizes_network_error_without_request_or_credentials(self) -> None:
        opener = RecordingOpener((OSError(self.private_credential),))
        stdout = io.StringIO()
        stderr = io.StringIO()

        exit_code = RUNNER.main(
            self._argv(),
            opener=opener,
            clock=fixed_clock,
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(stderr.getvalue(), "AUTH_TRANSPORT_ERROR\n")
        self.assertNotIn(self.private_credential, stdout.getvalue())
        self.assertNotIn(self.private_credential, stderr.getvalue())
        parsed = json.loads(stdout.getvalue())
        self.assertEqual(set(parsed), {"runId", "status", "count", "selectedSymbols", "artifactHashes"})

    def test_main_failure_summary_binds_published_terminal_evidence(self) -> None:
        auth_response = self._success_opener().responses[0]
        opener = RecordingOpener(
            (
                auth_response,
                FakeUrlResponse(
                    200,
                    {"Content-Type": "application/json"},
                    b'{"result":[]}',
                ),
            )
        )
        stdout = io.StringIO()
        stderr = io.StringIO()

        exit_code = RUNNER.main(
            self._argv(),
            opener=opener,
            clock=fixed_clock,
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(exit_code, 1)
        parsed = json.loads(stdout.getvalue())
        self.assertEqual(parsed["status"], "failed")
        self.assertEqual(
            set(parsed["artifactHashes"]),
            {"failure", "ledgerEvent"},
        )
        failure_path = (
            self.output_directory / self.arguments.run_id / "failure.json"
        )
        event_path = self.ledger_directory / "events/000001.json"
        self.assertEqual(
            parsed["artifactHashes"]["failure"],
            sha256_path(failure_path),
        )
        self.assertEqual(
            parsed["artifactHashes"]["ledgerEvent"],
            sha256_path(event_path),
        )


class MetadataRunnerModuleContractTest(unittest.TestCase):
    def test_metadata_runner_module_exists(self) -> None:
        self.assertTrue(RUNNER_PATH.is_file())

    def test_metadata_runner_exposes_typed_execution_boundary(self) -> None:
        module = load_runner()

        self.assertTrue(hasattr(module, "MetadataRunArguments"))
        self.assertTrue(hasattr(module, "MetadataRunSummary"))
        self.assertTrue(hasattr(module, "MetadataRunError"))
        self.assertTrue(hasattr(module, "UrllibMetadataTransport"))
        self.assertTrue(hasattr(module, "run_metadata_collection"))
        self.assertTrue(hasattr(module, "build_argument_parser"))
        self.assertTrue(hasattr(module, "main"))

    def test_arguments_bind_the_frozen_read_only_source_contract(self) -> None:
        module = load_runner()
        field_names = {
            field.name for field in dataclasses.fields(module.MetadataRunArguments)
        }

        self.assertTrue(
            {
                "source_contract_path",
                "source_contract_sha256",
                "runner_source_path",
                "runner_source_sha256",
                "runner_test_path",
                "runner_test_sha256",
            }.issubset(field_names)
        )

    def test_arguments_bind_local_evidence_and_sensitive_policy_sources(self) -> None:
        module = load_runner()
        field_names = {
            field.name for field in dataclasses.fields(module.MetadataRunArguments)
        }

        self.assertTrue(
            {
                "local_evidence_source_path",
                "local_evidence_source_sha256",
                "local_evidence_test_path",
                "local_evidence_test_sha256",
                "sensitive_policy_source_path",
                "sensitive_policy_source_sha256",
                "sensitive_policy_test_path",
                "sensitive_policy_test_sha256",
            }.issubset(field_names)
        )


if __name__ == "__main__":
    unittest.main()
