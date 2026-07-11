from __future__ import annotations

import hashlib
import importlib
import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import zstandard


_AVAILABLE_BYTES = 100 * 1024**3
_CLIENT_ID = "client-id-value"
_CLIENT_SECRET = "client-secret-value"
_TOKEN = "ephemeral-token"


class _Response:
    def __init__(
        self,
        body: bytes,
        *,
        status: int = 200,
        content_type: str = "application/json",
    ) -> None:
        self.status = status
        self.headers = {"Content-Type": content_type}
        self._body = io.BytesIO(body)

    def read(self, size: int = -1) -> bytes:
        return self._body.read(size)

    def close(self) -> None:
        self._body.close()


class _QueueOpener:
    def __init__(self, responses: tuple[_Response, ...]) -> None:
        self.responses = list(responses)
        self.requests: list[object] = []

    def open(self, request: object, timeout: float) -> _Response:
        del timeout
        self.requests.append(request)
        return self.responses.pop(0)


def _body(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode("utf-8")


def _oauth_response(token: str = _TOKEN) -> _Response:
    return _Response(_body({"access_token": token}))


def _trade_response(*, currency: str = "USD") -> _Response:
    return _Response(
        _body(
            {
                "result": [
                    {
                        "price": "250.100",
                        "volume": "10.500",
                        "timestamp": "2026-07-11T01:00:00.000Z",
                        "currency": currency,
                    }
                ]
            }
        )
    )


def _orderbook_response() -> _Response:
    return _Response(
        _body(
            {
                "result": {
                    "timestamp": "2026-07-11T01:00:00.000Z",
                    "currency": "USD",
                    "asks": [{"price": "250.20", "volume": "12.0"}],
                    "bids": [{"price": "250.10", "volume": "9"}],
                }
            }
        )
    )


def _credential_file(root: Path) -> Path:
    path = root / "toss-credentials.json"
    path.write_text(
        json.dumps(
            {
                "clientId": _CLIENT_ID,
                "clientSecret": _CLIENT_SECRET,
            }
        ),
        encoding="utf-8",
    )
    os.chmod(path, 0o600)
    return path


def _storage_root(root: Path) -> Path:
    path = root / "forward-evidence"
    path.mkdir(mode=0o700)
    return path


def _clock() -> datetime:
    return datetime(2026, 7, 11, 1, 0, 1, tzinfo=timezone.utc)


def _artifact_plaintext(root: Path) -> bytes:
    values: list[bytes] = []
    decompressor = zstandard.ZstdDecompressor()
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        body = path.read_bytes()
        values.append(
            decompressor.decompress(body)
            if path.name.endswith(".json.zst")
            else body
        )
    return b"\n".join(values)


class TossForwardCaptureRunContractTest(unittest.TestCase):
    def test_exports_secure_forward_capture_runner_contract(self) -> None:
        try:
            runner = importlib.import_module("rp001_s2.toss_forward_capture_run")
        except ModuleNotFoundError:
            runner = None

        self.assertIsNotNone(runner)
        self.assertTrue(hasattr(runner, "TossForwardCaptureArguments"))
        self.assertTrue(hasattr(runner, "TossForwardCaptureResult"))
        self.assertTrue(hasattr(runner, "run_toss_forward_capture"))

    def test_authenticates_once_and_persists_exactly_two_reads_per_symbol(
        self,
    ) -> None:
        from rp001_s2.toss_forward_capture_run import (
            TossForwardCaptureArguments,
            run_toss_forward_capture,
        )

        opener = _QueueOpener(
            (
                _oauth_response(),
                _trade_response(),
                _orderbook_response(),
                _trade_response(),
                _orderbook_response(),
            )
        )
        pace_events: list[str] = []
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            arguments = TossForwardCaptureArguments(
                credential_file=_credential_file(root),
                storage_root=_storage_root(root),
                symbols=("TSLA", "AAPL"),
            )

            result = run_toss_forward_capture(
                arguments,
                clock=_clock,
                opener=opener,
                request_pacer=lambda: pace_events.append("paced"),
                free_bytes=lambda _path: _AVAILABLE_BYTES,
            )

            self.assertEqual(
                [(outcome.symbol, outcome.status.value) for outcome in result.outcomes],
                [("TSLA", "completed"), ("AAPL", "completed")],
            )
            self.assertEqual(pace_events, ["paced"] * 4)
            self.assertEqual(
                [getattr(request, "get_method")() for request in opener.requests],
                ["POST", "GET", "GET", "GET", "GET"],
            )
            self.assertEqual(
                [getattr(request, "full_url") for request in opener.requests[1:]],
                [
                    "https://openapi.tossinvest.com/api/v1/trades?"
                    "symbol=TSLA&count=50",
                    "https://openapi.tossinvest.com/api/v1/orderbook?symbol=TSLA",
                    "https://openapi.tossinvest.com/api/v1/trades?"
                    "symbol=AAPL&count=50",
                    "https://openapi.tossinvest.com/api/v1/orderbook?symbol=AAPL",
                ],
            )
            self.assertTrue(
                all(outcome.stored_archive is not None for outcome in result.outcomes)
            )
            artifact_plaintext = _artifact_plaintext(arguments.storage_root)
            for secret in (_CLIENT_ID, _CLIENT_SECRET, _TOKEN):
                self.assertNotIn(secret.encode("utf-8"), artifact_plaintext)
                self.assertNotIn(secret, repr(arguments))
                self.assertNotIn(secret, repr(result))

    def test_orderbook_failure_preserves_trade_and_orderbook_raw_captures(
        self,
    ) -> None:
        from rp001_s2.toss_forward_capture_run import (
            TossForwardCaptureArguments,
            run_toss_forward_capture,
        )

        opener = _QueueOpener(
            (
                _oauth_response(),
                _trade_response(),
                _Response(b'{"message":"unavailable"}', status=503),
            )
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            arguments = TossForwardCaptureArguments(
                credential_file=_credential_file(root),
                storage_root=_storage_root(root),
                symbols=("TSLA",),
            )

            result = run_toss_forward_capture(
                arguments,
                clock=_clock,
                opener=opener,
                request_pacer=lambda: None,
                free_bytes=lambda _path: _AVAILABLE_BYTES,
            )

            outcome = result.outcomes[0]
            self.assertEqual(outcome.status.value, "failed")
            self.assertEqual(outcome.error_code, "HTTP_STATUS")
            self.assertIsNotNone(outcome.failure_evidence)
            self.assertEqual(len(outcome.failure_evidence.raw_paths), 2)
            manifest = json.loads(outcome.failure_evidence.manifest_path.read_bytes())
            self.assertEqual(
                [item["rawAvailability"] for item in manifest["captureEvidence"]],
                ["exact", "exact"],
            )

    def test_trade_failure_still_samples_orderbook_once_and_preserves_both(
        self,
    ) -> None:
        from rp001_s2.toss_forward_capture_run import (
            TossForwardCaptureArguments,
            run_toss_forward_capture,
        )

        opener = _QueueOpener(
            (
                _oauth_response(),
                _Response(b'{"message":"unavailable"}', status=503),
                _orderbook_response(),
            )
        )
        pace_events: list[str] = []
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            arguments = TossForwardCaptureArguments(
                credential_file=_credential_file(root),
                storage_root=_storage_root(root),
                symbols=("TSLA",),
            )

            result = run_toss_forward_capture(
                arguments,
                clock=_clock,
                opener=opener,
                request_pacer=lambda: pace_events.append("paced"),
                free_bytes=lambda _path: _AVAILABLE_BYTES,
            )

            outcome = result.outcomes[0]
            self.assertEqual(outcome.error_code, "HTTP_STATUS")
            self.assertEqual(pace_events, ["paced", "paced"])
            self.assertEqual(
                [getattr(request, "full_url") for request in opener.requests[1:]],
                [
                    "https://openapi.tossinvest.com/api/v1/trades?"
                    "symbol=TSLA&count=50",
                    "https://openapi.tossinvest.com/api/v1/orderbook?symbol=TSLA",
                ],
            )
            self.assertEqual(len(outcome.failure_evidence.raw_paths), 2)
            manifest = json.loads(outcome.failure_evidence.manifest_path.read_bytes())
            self.assertEqual(
                [item["endpointId"] for item in manifest["captureEvidence"]],
                ["sampled_trades_v1", "sampled_orderbook_v1"],
            )
            self.assertTrue(
                all(
                    item["rawAvailability"] == "exact"
                    for item in manifest["captureEvidence"]
                )
            )

    def test_auth_failure_persists_only_redacted_capture_metadata(self) -> None:
        from rp001_s2.toss_forward_capture_run import (
            TossForwardCaptureArguments,
            run_toss_forward_capture,
        )

        auth_body = b'{"message":"invalid client"}'
        opener = _QueueOpener((_Response(auth_body, status=401),))
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            arguments = TossForwardCaptureArguments(
                credential_file=_credential_file(root),
                storage_root=_storage_root(root),
                symbols=("TSLA",),
            )

            result = run_toss_forward_capture(
                arguments,
                clock=_clock,
                opener=opener,
                request_pacer=lambda: None,
                free_bytes=lambda _path: _AVAILABLE_BYTES,
            )

            outcome = result.outcomes[0]
            manifest = json.loads(outcome.failure_evidence.manifest_path.read_bytes())
            capture = manifest["captureEvidence"][0]
            self.assertEqual(capture["rawAvailability"], "redacted_at_auth_boundary")
            self.assertEqual(capture["bodySha256"], hashlib.sha256(auth_body).hexdigest())
            self.assertEqual(outcome.failure_evidence.raw_paths, ())
            self.assertNotIn(auth_body, _artifact_plaintext(arguments.storage_root))

    def test_sensitive_reflection_writes_only_sanitized_terminal_manifest(self) -> None:
        from rp001_s2.toss_forward_capture_run import (
            TossForwardCaptureArguments,
            run_toss_forward_capture,
        )

        sensitive_token = "super-secret-token"
        opener = _QueueOpener(
            (
                _oauth_response(sensitive_token),
                _trade_response(currency=sensitive_token),
            )
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            arguments = TossForwardCaptureArguments(
                credential_file=_credential_file(root),
                storage_root=_storage_root(root),
                symbols=("TSLA",),
            )

            result = run_toss_forward_capture(
                arguments,
                clock=_clock,
                opener=opener,
                request_pacer=lambda: None,
                free_bytes=lambda _path: _AVAILABLE_BYTES,
            )

            outcome = result.outcomes[0]
            self.assertEqual(outcome.error_code, "sensitive_response_material")
            manifest = json.loads(outcome.failure_evidence.manifest_path.read_bytes())
            self.assertEqual(manifest["captureEvidence"], [])
            self.assertEqual(outcome.failure_evidence.raw_paths, ())
            artifact_plaintext = _artifact_plaintext(arguments.storage_root)
            self.assertNotIn(sensitive_token.encode("utf-8"), artifact_plaintext)
            self.assertNotIn(_CLIENT_SECRET.encode("utf-8"), artifact_plaintext)

    def test_orderbook_sensitive_reflection_discards_prior_safe_trade_evidence(
        self,
    ) -> None:
        from rp001_s2.toss_forward_capture_run import (
            TossForwardCaptureArguments,
            run_toss_forward_capture,
        )

        sensitive_token = "super-secret-token"
        sensitive_orderbook = _Response(
            _body(
                {
                    "result": {
                        "timestamp": "2026-07-11T01:00:00.000Z",
                        "currency": sensitive_token,
                        "asks": [],
                        "bids": [],
                    }
                }
            )
        )
        opener = _QueueOpener(
            (
                _oauth_response(sensitive_token),
                _trade_response(),
                sensitive_orderbook,
            )
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            arguments = TossForwardCaptureArguments(
                credential_file=_credential_file(root),
                storage_root=_storage_root(root),
                symbols=("TSLA",),
            )

            result = run_toss_forward_capture(
                arguments,
                clock=_clock,
                opener=opener,
                request_pacer=lambda: None,
                free_bytes=lambda _path: _AVAILABLE_BYTES,
            )

            outcome = result.outcomes[0]
            manifest = json.loads(outcome.failure_evidence.manifest_path.read_bytes())
            self.assertEqual(outcome.error_code, "sensitive_response_material")
            self.assertEqual(manifest["captureEvidence"], [])
            self.assertEqual(outcome.failure_evidence.raw_paths, ())
            self.assertNotIn(
                sensitive_token.encode("utf-8"),
                _artifact_plaintext(arguments.storage_root),
            )


if __name__ == "__main__":
    unittest.main()
