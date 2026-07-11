from __future__ import annotations

import base64
import dataclasses
import hashlib
import importlib.util
import json
import shutil
import stat
import sys
import tempfile
import types
import unittest
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request

from rp001.local_evidence import LocalArtifactStore, canonical_json_bytes
from rp001.toss_research_collector import HttpRequest


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
RUNNER_PATH = REPOSITORY_ROOT / "research/rp-001/collect_toss_candles.py"
SELECTED_SYMBOLS = ("AMZN", "CAT", "XOM", "AAPL", "AMD", "COST")
INITIAL_BEFORE = "2026-07-01T00:00:00Z"


def load_module(path: Path, module_name: str) -> object:
    specification = importlib.util.spec_from_file_location(module_name, path)
    if specification is None or specification.loader is None:
        raise AssertionError("test module could not be loaded")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def load_isolated_runner(repository_root: Path) -> tuple[object, tuple[str, ...]]:
    suffix = hashlib.sha256(str(repository_root).encode("utf-8")).hexdigest()[:12]
    sensitive_name = f"rp001_candle_fixture_sensitive_{suffix}"
    local_name = f"rp001_candle_fixture_local_{suffix}"
    selection_name = f"rp001_candle_fixture_selection_{suffix}"
    collector_name = f"rp001_candle_fixture_collector_{suffix}"
    runner_name = f"rp001_candle_fixture_runner_{suffix}"
    sensitive = load_module(
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
    aliases: dict[str, object] = {"rp001.sensitive_value_policy": sensitive}
    try:
        sys.modules.update(aliases)
        local = load_module(
            repository_root / "research/rp-001/src/rp001/local_evidence.py",
            local_name,
        )
        aliases["rp001.local_evidence"] = local
        sys.modules["rp001.local_evidence"] = local
        selection = load_module(
            repository_root / "research/rp-001/src/rp001/sample_selection.py",
            selection_name,
        )
        aliases["rp001.sample_selection"] = selection
        sys.modules["rp001.sample_selection"] = selection
        collector = load_module(
            repository_root
            / "research/rp-001/src/rp001/toss_research_collector.py",
            collector_name,
        )
        aliases["rp001.toss_research_collector"] = collector
        sys.modules["rp001.toss_research_collector"] = collector
        runner = load_module(
            repository_root / "research/rp-001/collect_toss_candles.py",
            runner_name,
        )
    finally:
        for name in aliases:
            prior = prior_modules.get(name)
            if prior is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = prior
    boundary_name = getattr(runner, "BOUNDARY_MODULE_NAME", "")
    return runner, tuple(
        name
        for name in (
            runner_name,
            boundary_name,
            collector_name,
            selection_name,
            local_name,
            sensitive_name,
        )
        if name
    )


RUNNER = load_module(RUNNER_PATH, "rp001_collect_toss_candles_test_target") if RUNNER_PATH.exists() else None


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixed_clock() -> datetime:
    return datetime(2026, 7, 11, 2, 3, 4, tzinfo=timezone.utc)


def traceback_exposed_strings(error: BaseException) -> tuple[str, ...]:
    exposed: list[str] = []
    pending = [error]
    seen_errors: set[int] = set()

    def collect(value: object, seen: set[int], depth: int = 0) -> None:
        if depth > 8 or id(value) in seen:
            return
        seen.add(id(value))
        if isinstance(value, str):
            exposed.append(value)
            return
        if isinstance(value, bytes):
            exposed.append(value.decode("utf-8", errors="ignore"))
            return
        if isinstance(value, Mapping):
            for key, nested in value.items():
                collect(key, seen, depth + 1)
                collect(nested, seen, depth + 1)
            return
        if isinstance(value, (tuple, list, set, frozenset)):
            for nested in value:
                collect(nested, seen, depth + 1)
            return
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            for field in dataclasses.fields(value):
                collect(getattr(value, field.name), seen, depth + 1)
            return
        if isinstance(value, types.FunctionType):
            for closure in value.__closure__ or ():
                try:
                    collect(closure.cell_contents, seen, depth + 1)
                except ValueError:
                    continue
            return
        if isinstance(value, (types.ModuleType, type, types.MethodType)):
            return
        try:
            collect(vars(value), seen, depth + 1)
        except TypeError:
            return

    while pending:
        current = pending.pop()
        if id(current) in seen_errors:
            continue
        seen_errors.add(id(current))
        current_traceback = current.__traceback__
        while current_traceback is not None:
            if Path(current_traceback.tb_frame.f_code.co_filename).resolve() == Path(
                getattr(RUNNER, "__file__", RUNNER_PATH)
            ).resolve():
                for local_value in current_traceback.tb_frame.f_locals.values():
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
        self.headers = dict(headers)
        self._body = body
        self._offset = 0

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self._body) - self._offset
        chunk = self._body[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk

    def close(self) -> None:
        return None


class RecordingOpener:
    def __init__(self, responses: Sequence[FakeUrlResponse | BaseException]) -> None:
        self.responses = tuple(responses)
        self.requests: list[Request] = []

    def open(self, request: Request, timeout: float) -> object:
        del timeout
        self.requests.append(request)
        index = len(self.requests) - 1
        if index >= len(self.responses):
            raise AssertionError("unexpected HTTP request")
        response = self.responses[index]
        if isinstance(response, BaseException):
            raise response
        return response


class RecordingPacer:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> None:
        self.calls += 1


def candle_row(
    timestamp: str,
    *,
    close_price: str,
    volume: str,
) -> dict[str, object]:
    return {
        "timestamp": timestamp,
        "openPrice": close_price,
        "highPrice": close_price,
        "lowPrice": close_price,
        "closePrice": close_price,
        "volume": volume,
        "currency": "USD",
    }


def candle_response(
    symbol_index: int,
    adjusted: bool,
    *,
    next_before: str | None = None,
) -> FakeUrlResponse:
    base = 1000 + symbol_index * 10 + (1 if adjusted else 2)
    result: dict[str, object] = {
        "candles": [
            candle_row(
                "2026-06-30T16:00:00Z",
                close_price=str(base),
                volume=str(100000 + symbol_index),
            ),
            candle_row(
                "2023-01-03T16:00:00Z",
                close_price=str(base - 1),
                volume=str(95000 + symbol_index),
            ),
            candle_row(
                "2023-01-02T16:00:00Z",
                close_price=str(base - 2),
                volume=str(90000 + symbol_index),
            ),
        ]
    }
    if next_before is not None:
        result["nextBefore"] = next_before
    body = json.dumps(
        {"result": result},
        separators=(",", ":"),
    ).encode("utf-8")
    return FakeUrlResponse(200, {"Content-Type": "application/json"}, body)


class CandleRunnerScaffoldTest(unittest.TestCase):
    def test_daily_candle_runner_module_exists(self) -> None:
        self.assertTrue(RUNNER_PATH.is_file())

    def test_preseeded_boundary_module_is_never_reused(self) -> None:
        boundary_path = RUNNER_PATH.with_name("collect_toss_metadata.py").resolve()
        digest = hashlib.sha256(str(boundary_path).encode("utf-8")).hexdigest()[:16]
        boundary_name = f"_rp001_candle_metadata_boundary_{digest}"
        fake = types.ModuleType(boundary_name)
        fake.__file__ = str(boundary_path)
        prior = sys.modules.get(boundary_name)
        runner_name = "rp001_candle_preseed_boundary_test"
        sys.modules[boundary_name] = fake
        try:
            loaded = load_module(RUNNER_PATH, runner_name)
            self.assertIsNot(loaded.BOUNDARY, fake)
        finally:
            sys.modules.pop(runner_name, None)
            if prior is None:
                sys.modules.pop(boundary_name, None)
            else:
                sys.modules[boundary_name] = prior


@unittest.skipIf(RUNNER is None, "daily candle runner is not implemented")
class CandleRunnerFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repository_root = Path(self.temporary_directory.name).resolve()
        for relative_path in (
            "research/rp-001/collect_toss_candles.py",
            "research/rp-001/tests/test_collect_toss_candles.py",
            "research/rp-001/collect_toss_metadata.py",
            "research/rp-001/tests/test_collect_toss_metadata.py",
            "research/rp-001/src/rp001/toss_research_collector.py",
            "research/rp-001/tests/test_toss_research_collector.py",
            "research/rp-001/src/rp001/local_evidence.py",
            "research/rp-001/tests/test_local_evidence_contract.py",
            "research/rp-001/src/rp001/sensitive_value_policy.py",
            "research/rp-001/tests/test_sensitive_value_policy.py",
            "research/rp-001/src/rp001/sample_selection.py",
            "research/rp-001/tests/test_sample_selection.py",
        ):
            self._copy(relative_path)
        self._copy_bound(
            "research/rp-001/contracts/toss-read-only-source-contract-v1.2.json"
        )
        self._copy_bound(
            "research/rp-001/contracts/selected-sample-freeze-v1.json"
        )
        self._copy_bound(
            "research/rp-001/contracts/st-beh-interim-merc-v1.json"
        )
        for sequence in range(1, 14):
            self._copy_bound(
                "research/rp-001/local-ledgers/interim-program/events/"
                f"{sequence:06d}.json"
            )
        global RUNNER
        self._prior_runner = RUNNER
        RUNNER, self._isolated_module_names = load_isolated_runner(
            self.repository_root
        )
        self.credentials_path = (
            self.repository_root / ".storage/toss-credentials.local.json"
        )
        self.credentials_path.parent.mkdir(parents=True)
        credential_body = {
            "".join(("client", "Id")): "fixture-candle-client",
            "".join(("client", "Secret")): "fixture-candle-private-value",
        }
        self.credentials_path.write_text(
            json.dumps(credential_body, separators=(",", ":")),
            encoding="utf-8",
        )
        self.credentials_path.chmod(0o600)
        self.sample_freeze_path = (
            self.repository_root
            / "research/rp-001/contracts/selected-sample-freeze-v1.json"
        )
        self.merc_freeze_path = (
            self.repository_root
            / "research/rp-001/contracts/st-beh-interim-merc-v1.json"
        )
        self.freeze_ledger_event_path = (
            self.repository_root
            / "research/rp-001/local-ledgers/interim-program/events/000013.json"
        )
        self.source_contract_path = (
            self.repository_root
            / "research/rp-001/contracts/toss-read-only-source-contract-v1.3.json"
        )
        self.sample_binding = types.SimpleNamespace(
            artifact_sha256=sha256_path(self.sample_freeze_path)
        )
        self.merc_binding = types.SimpleNamespace(
            artifact_sha256=sha256_path(self.merc_freeze_path)
        )
        self.freeze_event_binding = types.SimpleNamespace(
            artifact_sha256=sha256_path(self.freeze_ledger_event_path)
        )
        self._publish_source_contract()
        self.output_directory = self.repository_root / "research/rp-001/candle-runs"
        self.ledger_directory = (
            self.repository_root
            / "research/rp-001/local-ledgers/interim-program"
        )
        self.arguments = self._arguments()

    def tearDown(self) -> None:
        global RUNNER
        RUNNER = self._prior_runner
        for module_name in self._isolated_module_names:
            sys.modules.pop(module_name, None)
        self.temporary_directory.cleanup()

    def _copy(self, relative_path: str) -> None:
        destination = self.repository_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPOSITORY_ROOT / relative_path, destination)

    def _copy_bound(self, relative_path: str) -> None:
        self._copy(relative_path)
        self._copy(f"{relative_path}.sha256")

    def _source_binding(self, source: str, test: str) -> dict[str, object]:
        return {
            "sourcePath": source,
            "sourceSha256": sha256_path(self.repository_root / source),
            "testPath": test,
            "testSha256": sha256_path(self.repository_root / test),
        }

    def _publish_source_contract(self) -> None:
        predecessor = (
            self.repository_root
            / "research/rp-001/contracts/toss-read-only-source-contract-v1.2.json"
        )
        value = {
            "schemaVersion": "rp001-toss-read-only-source-contract.v1.3",
            "status": "read_only_daily_candle_runner_authorized",
            "programId": "RP-001",
            "goalVersion": "1.2-COMPACT",
            "decisionScope": "research_only",
            "operationalDisposition": "NoTrade/no integration",
            "finalizedAt": "2026-07-11T02:00:00Z",
            "supersedes": {
                "path": predecessor.relative_to(self.repository_root).as_posix(),
                "sha256": sha256_path(predecessor),
                "reason": "authorize_frozen_daily_candle_collection_only",
            },
            "allowedRequests": [
                {
                    "method": "POST",
                    "path": "/oauth2/token",
                    "purpose": "ephemeral_authentication_only",
                },
                {
                    "method": "GET",
                    "path": "/api/v1/candles",
                    "purpose": "frozen_daily_price_volume_collection",
                    "parameters": [
                        "symbol",
                        "interval=1d",
                        "count=200",
                        "adjusted",
                        "before",
                    ],
                },
            ],
            "candleScope": {
                "symbols": list(SELECTED_SYMBOLS),
                "startDate": "2023-01-03",
                "endDate": "2026-06-30",
                "interval": "1d",
                "timezone": "America/New_York",
                "count": 200,
                "initialBefore": INITIAL_BEFORE,
                "adjustedModes": [True, False],
                "paginationCursor": "opaque_before",
                "requestOrder": "symbol_then_adjusted_true_then_false_sequential",
            },
            "requestPacing": {
                "minimumIntervalSeconds": 0.21,
                "method": "monotonic_sleep_loop",
            },
            "completeness": {
                "requireFrozenStartSession": True,
                "terminalCursorBeforeStart": "data_unavailable",
            },
            "outputRoot": "research/rp-001/candle-runs",
            "credentialBoundary": {
                "pathClass": "repository_dot_storage_0600_pinned_regular_file",
                "tokenLifecycle": "ephemeral_credential_frame_only",
                "oauthResponsePersistence": "forbidden",
            },
            "exposureState": {
                "metadataPreviouslyOpened": True,
                "priceVolumeOpened": False,
                "outcomesPerformanceOpened": False,
                "ordersAccountsAssetsAccessed": False,
            },
            "forbiddenRequests": {
                "families": ["order", "account", "asset"],
                "otherMarketEndpoints": [
                    "stocks",
                    "prices",
                    "trades",
                    "orderbook",
                ],
                "operatingAppIntegration": True,
            },
            "canonicalLedgerPath": "research/rp-001/local-ledgers/interim-program",
            "qualityEvidence": {
                "candleRunnerTestsPassed": 20,
                "candleRunnerTestsTotal": 20,
                "candleDependencyRegressionTestsPassed": 229,
                "candleDependencyRegressionTestsTotal": 229,
                "programRegressionTestsPassed": 399,
                "programRegressionTestsTotal": 399,
                "criticalFindings": 0,
                "importantFindings": 0,
                "minorFindings": 0,
                "finalReviewVerdict": "APPROVE",
                "reviewVerdicts": {
                    "runner": "APPROVE_C0_I0_M0",
                    "metadataBoundary": "APPROVE_C0_I0_M0",
                    "collector": "APPROVE_C0_I0_M0",
                    "localEvidence": "APPROVE_C0_I0_M0",
                    "sensitiveValuePolicy": "APPROVE_C0_I0_M0",
                },
                "reviewScope": [
                    "parent_fd_trust_anchor_active_lifecycle",
                    "metadata_boundary_executed_byte_attestation",
                    "rate_paced_complete_daily_range",
                    "post_return_external_cas_deferred",
                ],
            },
            "bindings": {
                "predecessorContract": {
                    "path": predecessor.relative_to(self.repository_root).as_posix(),
                    "sha256": sha256_path(predecessor),
                },
                "sampleFreeze": {
                    "path": self.sample_freeze_path.relative_to(
                        self.repository_root
                    ).as_posix(),
                    "sha256": self.sample_binding.artifact_sha256,
                },
                "mercFreeze": {
                    "path": self.merc_freeze_path.relative_to(
                        self.repository_root
                    ).as_posix(),
                    "sha256": self.merc_binding.artifact_sha256,
                },
                "freezeLedgerEvent": {
                    "path": self.freeze_ledger_event_path.relative_to(
                        self.repository_root
                    ).as_posix(),
                    "sha256": self.freeze_event_binding.artifact_sha256,
                },
                "runner": self._source_binding(
                    "research/rp-001/collect_toss_candles.py",
                    "research/rp-001/tests/test_collect_toss_candles.py",
                ),
                "metadataBoundary": self._source_binding(
                    "research/rp-001/collect_toss_metadata.py",
                    "research/rp-001/tests/test_collect_toss_metadata.py",
                ),
                "collector": self._source_binding(
                    "research/rp-001/src/rp001/toss_research_collector.py",
                    "research/rp-001/tests/test_toss_research_collector.py",
                ),
                "localEvidence": self._source_binding(
                    "research/rp-001/src/rp001/local_evidence.py",
                    "research/rp-001/tests/test_local_evidence_contract.py",
                ),
                "sensitiveValuePolicy": self._source_binding(
                    "research/rp-001/src/rp001/sensitive_value_policy.py",
                    "research/rp-001/tests/test_sensitive_value_policy.py",
                ),
            },
        }
        self.source_contract_binding = LocalArtifactStore(
            self.repository_root.resolve()
        ).publish_json(
            self.source_contract_path,
            value,
        )

    def _arguments(self) -> object:
        def relative(path: Path) -> Path:
            return path.relative_to(self.repository_root)

        return RUNNER.CandleRunArguments(
            repository_root=self.repository_root,
            credentials_path=self.credentials_path,
            predecessor_contract_path=Path(
                "research/rp-001/contracts/toss-read-only-source-contract-v1.2.json"
            ),
            predecessor_contract_sha256=sha256_path(
                self.repository_root
                / "research/rp-001/contracts/toss-read-only-source-contract-v1.2.json"
            ),
            source_contract_path=relative(self.source_contract_path),
            source_contract_sha256=self.source_contract_binding.artifact_sha256,
            sample_freeze_path=relative(self.sample_freeze_path),
            sample_freeze_sha256=self.sample_binding.artifact_sha256,
            merc_freeze_path=relative(self.merc_freeze_path),
            merc_freeze_sha256=self.merc_binding.artifact_sha256,
            freeze_ledger_event_path=relative(self.freeze_ledger_event_path),
            freeze_ledger_event_sha256=self.freeze_event_binding.artifact_sha256,
            runner_source_path=Path("research/rp-001/collect_toss_candles.py"),
            runner_source_sha256=sha256_path(
                self.repository_root / "research/rp-001/collect_toss_candles.py"
            ),
            runner_test_path=Path(
                "research/rp-001/tests/test_collect_toss_candles.py"
            ),
            runner_test_sha256=sha256_path(
                self.repository_root
                / "research/rp-001/tests/test_collect_toss_candles.py"
            ),
            boundary_source_path=Path("research/rp-001/collect_toss_metadata.py"),
            boundary_source_sha256=sha256_path(
                self.repository_root / "research/rp-001/collect_toss_metadata.py"
            ),
            boundary_test_path=Path(
                "research/rp-001/tests/test_collect_toss_metadata.py"
            ),
            boundary_test_sha256=sha256_path(
                self.repository_root
                / "research/rp-001/tests/test_collect_toss_metadata.py"
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
            output_directory=Path("research/rp-001/candle-runs"),
            ledger_directory=Path(
                "research/rp-001/local-ledgers/interim-program"
            ),
            run_id="RP001-CANDLE-FIXTURE-001",
        )

    def _success_opener(self) -> RecordingOpener:
        bearer_field = "_".join(("access", "token"))
        auth = FakeUrlResponse(
            200,
            {"Content-Type": "application/json"},
            json.dumps(
                {bearer_field: "fixture-ephemeral-candle-bearer", "expires_in": 3600},
                separators=(",", ":"),
            ).encode("utf-8"),
        )
        responses: list[FakeUrlResponse] = [auth]
        for symbol_index, _symbol in enumerate(SELECTED_SYMBOLS):
            responses.append(candle_response(symbol_index, True))
            responses.append(candle_response(symbol_index, False))
        return RecordingOpener(responses)

    def _run(
        self,
        opener: RecordingOpener,
        pacer: Callable[[], None] | None = None,
    ) -> object:
        return RUNNER.run_daily_candle_collection(
            self.arguments,
            opener=opener,
            clock=fixed_clock,
            request_pacer=pacer or RecordingPacer(),
        )

    def _capture_error(self, operation: Callable[[], object]) -> object:
        try:
            operation()
        except RUNNER.CandleRunError as error:
            return error
        self.fail("candle run unexpectedly succeeded")

    def _run_directory(self) -> Path:
        return self.output_directory / self.arguments.run_id


class CandleRunnerContractTest(CandleRunnerFixture):
    def test_success_collects_exact_frozen_scope_and_publishes_reproducible_outputs(self) -> None:
        opener = self._success_opener()
        pacer = RecordingPacer()

        summary = self._run(opener, pacer)

        self.assertEqual(summary.status, "succeeded")
        self.assertEqual(summary.symbol_count, 6)
        self.assertEqual(summary.analysis_row_count, 12)
        self.assertEqual(summary.capture_count, 12)
        self.assertEqual(len(opener.requests), 13)
        self.assertEqual(pacer.calls, 12)
        self.assertEqual(opener.requests[0].full_url, "https://openapi.tossinvest.com/oauth2/token")
        observed: list[tuple[str, str]] = []
        for request in opener.requests[1:]:
            parsed = urlsplit(request.full_url)
            self.assertEqual(parsed.path, "/api/v1/candles")
            query = parse_qs(parsed.query)
            self.assertEqual(query["interval"], ["1d"])
            self.assertEqual(query["count"], ["200"])
            self.assertEqual(query["before"], [INITIAL_BEFORE])
            observed.append((query["symbol"][0], query["adjusted"][0]))
        self.assertEqual(
            observed,
            [
                (symbol, adjusted)
                for symbol in SELECTED_SYMBOLS
                for adjusted in ("true", "false")
            ],
        )
        run_directory = self._run_directory()
        self.assertEqual(
            {path.name for path in run_directory.iterdir()},
            {
                "raw-candles.json",
                "raw-candles.json.sha256",
                "processed-candles.json",
                "processed-candles.json.sha256",
                "candle-scope.json",
                "candle-scope.json.sha256",
                "candle-exposure.json",
                "candle-exposure.json.sha256",
                "manifest.json",
                "manifest.json.sha256",
            },
        )
        raw = json.loads((run_directory / "raw-candles.json").read_text())
        processed = json.loads(
            (run_directory / "processed-candles.json").read_text()
        )
        exposure = json.loads(
            (run_directory / "candle-exposure.json").read_text()
        )
        self.assertEqual(raw["captureCount"], 12)
        self.assertEqual(len(raw["captures"]), 12)
        self.assertEqual([item["symbol"] for item in processed["symbols"]], list(SELECTED_SYMBOLS))
        self.assertTrue(
            all(len(item["analysisRows"]) == 2 for item in processed["symbols"])
        )
        self.assertTrue(
            all(
                len(item["auditOnlyRows"]["adjusted"]) == 1
                and len(item["auditOnlyRows"]["native"]) == 1
                for item in processed["symbols"]
            )
        )
        self.assertEqual(exposure["priceVolumeOpened"], True)
        self.assertEqual(exposure["metadataPreviouslyOpened"], True)
        self.assertEqual(exposure["outcomesPerformanceOpened"], False)
        self.assertEqual(exposure["ordersAccountsAssetsAccessed"], False)
        for body in run_directory.glob("*.json"):
            self.assertEqual(
                Path(f"{body}.sha256").read_text(encoding="ascii"),
                f"{sha256_path(body)}\n",
            )
            self.assertEqual(stat.S_IMODE(body.stat().st_mode), 0o600)

    def test_frozen_hash_mismatch_is_rejected_before_authentication(self) -> None:
        self.arguments = dataclasses.replace(
            self.arguments,
            merc_freeze_sha256="0" * 64,
        )
        opener = self._success_opener()

        error = self._capture_error(lambda: self._run(opener))

        self.assertEqual(error.code, "INPUT_HASH_MISMATCH")
        self.assertEqual(opener.requests, [])

    def test_freeze_ledger_event_mutation_is_rejected_before_authentication(self) -> None:
        self.arguments = dataclasses.replace(
            self.arguments,
            freeze_ledger_event_sha256="0" * 64,
        )
        opener = self._success_opener()

        error = self._capture_error(lambda: self._run(opener))

        self.assertEqual(error.code, "INPUT_HASH_MISMATCH")
        self.assertEqual(opener.requests, [])

    def test_missing_freeze_ledger_event_is_rejected_before_authentication(self) -> None:
        self.freeze_ledger_event_path.unlink()
        opener = self._success_opener()

        error = self._capture_error(lambda: self._run(opener))

        self.assertEqual(error.code, "INPUT_PATH_INVALID")
        self.assertEqual(opener.requests, [])

    def test_external_credentials_are_rejected_before_authentication(self) -> None:
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        external = Path(outside.name) / "credentials.json"
        external.write_bytes(self.credentials_path.read_bytes())
        external.chmod(0o600)
        self.arguments = dataclasses.replace(
            self.arguments,
            credentials_path=external,
        )
        opener = self._success_opener()

        error = self._capture_error(lambda: self._run(opener))

        self.assertEqual(error.code, "CREDENTIAL_PATH_INVALID")
        self.assertEqual(opener.requests, [])

    def test_non_candle_endpoint_is_rejected_without_transport(self) -> None:
        opener = RecordingOpener(())
        transport = RUNNER.CandleTransport(
            opener=opener,
            timeout_seconds=1.0,
            allowed_symbols=SELECTED_SYMBOLS,
            request_pacer=RecordingPacer(),
            namespace_verifier=lambda: None,
        )
        request = HttpRequest(
            method="GET",
            url="https://openapi.tossinvest.com/api/v1/stocks?symbols=AAPL",
            headers={"Accept": "application/json", "Authorization": "Bearer fixture"},
        )

        error = self._capture_error(lambda: transport(request))

        self.assertEqual(error.code, "ENDPOINT_NOT_ALLOWED")
        self.assertEqual(opener.requests, [])

    def test_auth_http_failure_publishes_failure_only_and_appends_ledger(self) -> None:
        opener = RecordingOpener(
            (
                FakeUrlResponse(
                    401,
                    {"Content-Type": "application/json"},
                    b'{"error":"denied"}',
                ),
            )
        )

        error = self._capture_error(lambda: self._run(opener))

        self.assertEqual(error.code, "AUTH_HTTP_STATUS")
        run_directory = self._run_directory()
        self.assertEqual(
            {path.name for path in run_directory.iterdir()},
            {"failure.json", "failure.json.sha256"},
        )
        failure = json.loads((run_directory / "failure.json").read_text())
        self.assertEqual(failure["stage"], "auth")
        self.assertEqual(failure["priceVolumeOpened"], False)
        events = sorted((self.ledger_directory / "events").glob("*.json"))
        self.assertEqual(len(events), 14)
        event = json.loads(events[-1].read_text())
        self.assertEqual(event["eventType"], "toss_daily_candle_collection_failed")

    def test_opaque_multi_page_cursor_is_paced_and_preserved(self) -> None:
        cursor = "opaque/+== cursor"
        page_one = FakeUrlResponse(
            200,
            {"Content-Type": "application/json"},
            json.dumps(
                {
                    "result": {
                        "candles": [
                            candle_row(
                                "2026-06-30T16:00:00Z",
                                close_price="1001",
                                volume="100000",
                            )
                        ],
                        "nextBefore": cursor,
                    }
                },
                separators=(",", ":"),
            ).encode("utf-8"),
        )
        page_two = FakeUrlResponse(
            200,
            {"Content-Type": "application/json"},
            json.dumps(
                {
                    "result": {
                        "candles": [
                            candle_row(
                                "2023-01-03T16:00:00Z",
                                close_price="1000",
                                volume="95000",
                            ),
                            candle_row(
                                "2023-01-02T16:00:00Z",
                                close_price="999",
                                volume="90000",
                            )
                        ]
                    }
                },
                separators=(",", ":"),
            ).encode("utf-8"),
        )
        standard = self._success_opener()
        responses = [standard.responses[0], page_one, page_two]
        responses.extend(standard.responses[2:])
        opener = RecordingOpener(responses)
        pacer = RecordingPacer()

        summary = self._run(opener, pacer)

        self.assertEqual(summary.status, "succeeded")
        self.assertEqual(len(opener.requests), 14)
        self.assertEqual(pacer.calls, 13)
        second_page = parse_qs(urlsplit(opener.requests[2].full_url).query)
        self.assertEqual(second_page["before"], [cursor])
        raw = json.loads((self._run_directory() / "raw-candles.json").read_text())
        self.assertEqual(raw["captureCount"], 13)

    def test_later_symbol_failure_preserves_all_prior_safe_captures(self) -> None:
        standard = self._success_opener()
        invalid = FakeUrlResponse(
            200,
            {"Content-Type": "application/json"},
            b'{"result":{"unexpected":[]}}',
        )
        opener = RecordingOpener(
            (
                standard.responses[0],
                standard.responses[1],
                standard.responses[2],
                invalid,
            )
        )

        error = self._capture_error(lambda: self._run(opener))

        self.assertEqual(error.code, "INVALID_CANDLE_SHAPE")
        failure = json.loads((self._run_directory() / "failure.json").read_text())
        self.assertEqual(failure["stage"], "candles")
        self.assertEqual(failure["priceVolumeOpened"], True)
        self.assertEqual(len(failure["captures"]), 3)
        self.assertEqual(
            [
                base64.b64decode(capture["bodyBase64"])
                for capture in failure["captures"]
            ],
            [
                standard.responses[1]._body,
                standard.responses[2]._body,
                invalid._body,
            ],
        )

    def test_base_exception_during_auth_is_terminal_and_secret_safe(self) -> None:
        private_value = "fixture-candle-private-value"
        opener = RecordingOpener((KeyboardInterrupt(private_value),))

        error = self._capture_error(lambda: self._run(opener))

        self.assertEqual(error.code, "RUN_INTERRUPTED")
        self.assertFalse(
            any(private_value in value for value in traceback_exposed_strings(error))
        )
        failure = json.loads((self._run_directory() / "failure.json").read_text())
        self.assertEqual(failure["errorCode"], "RUN_INTERRUPTED")
        self.assertEqual(failure["priceVolumeOpened"], False)
        self.assertNotIn(private_value, json.dumps(failure))

    def test_direct_transport_error_does_not_retain_authorization(self) -> None:
        bearer = "fixture-direct-transport-secret"
        opener = RecordingOpener(())
        transport = RUNNER.CandleTransport(
            opener=opener,
            timeout_seconds=1.0,
            allowed_symbols=SELECTED_SYMBOLS,
            request_pacer=RecordingPacer(),
            namespace_verifier=lambda: None,
        )
        request = HttpRequest(
            method="GET",
            url="https://openapi.tossinvest.com/api/v1/orders",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {bearer}",
            },
        )

        error = self._capture_error(lambda: transport(request))

        self.assertEqual(error.code, "ENDPOINT_NOT_ALLOWED")
        self.assertEqual(opener.requests, [])
        self.assertFalse(
            any(bearer in value for value in traceback_exposed_strings(error))
        )

    def test_post_commit_tamper_appends_invalidation_and_fails_closed(self) -> None:
        prior = RUNNER.BOUNDARY._run_lifecycle_observer
        tampered = False

        def tamper_after_terminal_event(operation: str, target: str) -> None:
            nonlocal tampered
            if operation == "ledger_event_published" and not tampered:
                tampered = True
                (self._run_directory() / "raw-candles.json").write_text(
                    '{"tampered":true}',
                    encoding="utf-8",
                )

        RUNNER.BOUNDARY._run_lifecycle_observer = tamper_after_terminal_event
        try:
            error = self._capture_error(lambda: self._run(self._success_opener()))
        finally:
            RUNNER.BOUNDARY._run_lifecycle_observer = prior

        self.assertTrue(tampered)
        self.assertEqual(error.code, "EVIDENCE_INTEGRITY_LOST")
        events = sorted((self.ledger_directory / "events").glob("*.json"))
        self.assertEqual(len(events), 15)
        invalidation = json.loads(events[-1].read_text())
        self.assertEqual(
            invalidation["eventType"],
            "toss_daily_candle_collection_invalidated",
        )
        self.assertEqual(invalidation["payload"]["terminalEventType"], "success")

    def test_default_pacer_enforces_point_twenty_one_second_spacing(self) -> None:
        current = [100.0]
        sleeps: list[float] = []

        def monotonic() -> float:
            return current[0]

        def sleeper(seconds: float) -> None:
            sleeps.append(seconds)
            current[0] += seconds

        pacer = RUNNER._MinimumIntervalPacer(
            monotonic=monotonic,
            sleeper=sleeper,
        )

        pacer()
        pacer()
        pacer()

        self.assertEqual(len(sleeps), 2)
        self.assertAlmostEqual(sleeps[0], 0.21)
        self.assertAlmostEqual(sleeps[1], 0.21)

    def test_terminal_cursor_before_start_is_terminal_incomplete_range(self) -> None:
        standard = self._success_opener()
        incomplete = FakeUrlResponse(
            200,
            {"Content-Type": "application/json"},
            json.dumps(
                {
                    "result": {
                        "candles": [
                            candle_row(
                                "2026-06-30T16:00:00Z",
                                close_price="1001",
                                volume="100000",
                            )
                        ]
                    }
                },
                separators=(",", ":"),
            ).encode("utf-8"),
        )
        opener = RecordingOpener(
            (
                standard.responses[0],
                incomplete,
                FakeUrlResponse(
                    incomplete.status,
                    incomplete.headers,
                    incomplete._body,
                ),
            )
        )

        error = self._capture_error(lambda: self._run(opener))

        self.assertEqual(error.code, "CANDLE_RANGE_INCOMPLETE")
        self.assertEqual(len(opener.requests), 3)
        failure = json.loads((self._run_directory() / "failure.json").read_text())
        self.assertEqual(failure["stage"], "candles")
        self.assertEqual(len(failure["captures"]), 2)

    def test_noncanonical_output_root_is_rejected_before_authentication(self) -> None:
        self.arguments = dataclasses.replace(
            self.arguments,
            output_directory=Path("research/rp-001/runs"),
        )
        opener = self._success_opener()

        error = self._capture_error(lambda: self._run(opener))

        self.assertEqual(error.code, "OUTPUT_PATH_INVALID")
        self.assertEqual(opener.requests, [])

    def test_v13_operational_guards_are_required_before_authentication(self) -> None:
        original = json.loads(self.source_contract_path.read_text())
        cases = {
            "missing_pacing": lambda value: value.pop("requestPacing"),
            "mutated_completeness": lambda value: value.__setitem__(
                "completeness",
                {
                    "requireFrozenStartSession": False,
                    "terminalCursorBeforeStart": "data_unavailable",
                },
            ),
            "mutated_output": lambda value: value.__setitem__(
                "outputRoot",
                "research/rp-001/runs",
            ),
        }
        original_arguments = self.arguments
        for index, (case, mutate) in enumerate(cases.items(), start=1):
            with self.subTest(case=case):
                value = json.loads(json.dumps(original))
                mutate(value)
                path = self.source_contract_path.with_name(
                    f"invalid-v1.3-{index}.json"
                )
                binding = LocalArtifactStore(
                    self.repository_root.resolve()
                ).publish_json(path, value)
                self.arguments = dataclasses.replace(
                    original_arguments,
                    source_contract_path=path.relative_to(self.repository_root),
                    source_contract_sha256=binding.artifact_sha256,
                )
                opener = self._success_opener()

                error = self._capture_error(lambda: self._run(opener))

                self.assertEqual(error.code, "SOURCE_CONTRACT_INVALID")
                self.assertEqual(opener.requests, [])
        self.arguments = original_arguments

    def test_v13_contract_is_closed_world_and_canonical_path_only(self) -> None:
        original_value = json.loads(self.source_contract_path.read_text())
        original_source = self.source_contract_path.read_bytes()
        sidecar_path = Path(f"{self.source_contract_path}.sha256")
        original_sidecar = sidecar_path.read_bytes()
        original_arguments = self.arguments

        def extra_top(value: dict[str, object]) -> None:
            value["unregistered"] = True

        def missing_finalized_at(value: dict[str, object]) -> None:
            value.pop("finalizedAt")

        def invalid_finalized_at(value: dict[str, object]) -> None:
            value["finalizedAt"] = "2026-07-11T00:28:08Z"

        def extra_quality(value: dict[str, object]) -> None:
            value["qualityEvidence"]["unregistered"] = 1

        def mutated_quality(value: dict[str, object]) -> None:
            value["qualityEvidence"]["finalReviewVerdict"] = "REJECT"

        def extra_supersedes(value: dict[str, object]) -> None:
            value["supersedes"]["unregistered"] = True

        def mutated_reason(value: dict[str, object]) -> None:
            value["supersedes"]["reason"] = "changed_after_review"

        def extra_binding(value: dict[str, object]) -> None:
            value["bindings"]["unregistered"] = {
                "path": "research/rp-001/README.md",
                "sha256": "0" * 64,
            }

        def missing_binding(value: dict[str, object]) -> None:
            value["bindings"].pop("freezeLedgerEvent")

        cases = (
            ("extra_top", extra_top),
            ("missing_finalized_at", missing_finalized_at),
            ("invalid_finalized_at", invalid_finalized_at),
            ("extra_quality", extra_quality),
            ("mutated_quality", mutated_quality),
            ("extra_supersedes", extra_supersedes),
            ("mutated_reason", mutated_reason),
            ("extra_binding", extra_binding),
            ("missing_binding", missing_binding),
        )
        try:
            for index, (case, mutate) in enumerate(cases, start=1):
                with self.subTest(case=case):
                    value = json.loads(json.dumps(original_value))
                    mutate(value)
                    source = canonical_json_bytes(value)
                    source_sha256 = hashlib.sha256(source).hexdigest()
                    self.source_contract_path.write_bytes(source)
                    sidecar_path.write_text(
                        f"{source_sha256}\n",
                        encoding="ascii",
                    )
                    self.arguments = dataclasses.replace(
                        original_arguments,
                        source_contract_sha256=source_sha256,
                        run_id=f"RP001-CANDLE-INVALID-V13-{index:02d}",
                    )
                    opener = self._success_opener()

                    error = self._capture_error(lambda: self._run(opener))

                    self.assertEqual(error.code, "SOURCE_CONTRACT_INVALID")
                    self.assertEqual(opener.requests, [])
        finally:
            self.source_contract_path.write_bytes(original_source)
            sidecar_path.write_bytes(original_sidecar)
            self.arguments = original_arguments

        alternate_path = self.source_contract_path.with_name(
            "alternate-v1.3.json"
        )
        alternate = LocalArtifactStore(
            self.repository_root.resolve()
        ).publish_json(
            alternate_path,
            original_value,
        )
        self.arguments = dataclasses.replace(
            original_arguments,
            source_contract_path=alternate_path.relative_to(self.repository_root),
            source_contract_sha256=alternate.artifact_sha256,
            run_id="RP001-CANDLE-INVALID-V13-PATH",
        )
        opener = self._success_opener()

        error = self._capture_error(lambda: self._run(opener))

        self.assertEqual(error.code, "SOURCE_CONTRACT_INVALID")
        self.assertEqual(opener.requests, [])
        self.arguments = original_arguments

    def test_boundary_source_swap_and_restore_is_rejected_before_authentication(self) -> None:
        global RUNNER
        trusted_runner = RUNNER
        boundary_path = self.repository_root / self.arguments.boundary_source_path
        trusted_source = boundary_path.read_bytes()
        saved_modules = {
            name: sys.modules.get(name) for name in self._isolated_module_names
        }
        boundary_path.write_bytes(trusted_source + b"\nTOCTOU_MARKER = True\n")
        sys.modules.pop(trusted_runner.BOUNDARY_MODULE_NAME, None)
        try:
            compromised_runner, module_names = load_isolated_runner(
                self.repository_root
            )
            boundary_path.write_bytes(trusted_source)
            RUNNER = compromised_runner
            opener = self._success_opener()

            error = self._capture_error(lambda: self._run(opener))

            self.assertEqual(error.code, "EXECUTION_SOURCE_MISMATCH")
            self.assertEqual(opener.requests, [])
        finally:
            boundary_path.write_bytes(trusted_source)
            RUNNER = trusted_runner
            for name in module_names if "module_names" in locals() else ():
                sys.modules.pop(name, None)
            for name, module in saved_modules.items():
                if module is not None:
                    sys.modules[name] = module
