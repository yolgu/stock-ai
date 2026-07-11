"""Frozen GDELT company queries and globally paced read-only collection."""

from __future__ import annotations

import json
import re
import stat
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from rp001.local_evidence import (
    LocalArtifactBinding,
    LocalArtifactStore,
    canonical_json_bytes,
    sha256_bytes,
)
from rp001_s2.archive_contract import BENCHMARK_SYMBOLS, PRIORITY_SYMBOLS


_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"
_START_DATETIME = "20260412000000"
_END_DATETIME = "20260711000000"
_MODES = frozenset({"timelinevolraw", "timelinetone"})
_REQUEST_INTERVAL_SECONDS = 10.0
_RATE_LIMIT_BACKOFF_SECONDS = (30.0, 60.0, 120.0)
_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
_TICKER_PROXY_SYMBOLS = ("TSLA", "NVDA", "AAPL")
_FROZEN_SYMBOLS = tuple(sorted((*PRIORITY_SYMBOLS, *BENCHMARK_SYMBOLS)))
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CANONICAL_COMPANY_NAMES: Mapping[str, str] = {
    "000660": "SK hynix",
    "AAPL": "Apple Inc",
    "AMD": "Advanced Micro Devices Inc",
    "AMZN": "Amazon.com Inc",
    "AVGO": "Broadcom Inc",
    "BA": "Boeing Company",
    "CAT": "Caterpillar Inc",
    "COST": "Costco Wholesale Corporation",
    "CVX": "Chevron Corporation",
    "DIS": "Walt Disney Company",
    "GE": "GE Aerospace",
    "GS": "Goldman Sachs Group Inc",
    "HD": "Home Depot Inc",
    "IBM": "International Business Machines Corporation",
    "IWM": "iShares Russell 2000 Index Fund",
    "JNJ": "Johnson & Johnson",
    "JPM": "JP Morgan Chase & Co",
    "KO": "Coca-Cola Company",
    "LOW": "Lowe's Companies Inc",
    "MCD": "McDonald's Corporation",
    "META": "Meta Platforms Inc",
    "MRK": "Merck & Company Inc",
    "MSFT": "Microsoft Corporation",
    "MU": "Micron Technology Inc",
    "NFLX": "Netflix Inc",
    "NKE": "Nike Inc",
    "NVDA": "NVIDIA Corporation",
    "ORCL": "Oracle Corporation",
    "PEP": "PepsiCo Inc",
    "QCOM": "QUALCOMM Incorporated",
    "QQQ": "Invesco QQQ Trust",
    "SBUX": "Starbucks Corporation",
    "SOXX": "iShares PHLX SOX Semiconductor Sector Index Fund",
    "SPY": "State Street SPDR S&P 500 ETF Trust",
    "TSLA": "Tesla Inc",
    "UPS": "United Parcel Service Inc",
    "WMT": "Walmart Inc",
    "XLC": "State Street Communication Services Select Sector SPDR ETF",
    "XLE": "State Street Energy Select Sector SPDR ETF",
    "XLF": "State Street Financial Select Sector SPDR ETF",
    "XLI": "State Street Industrial Select Sector SPDR ETF",
    "XLK": "State Street Technology Select Sector SPDR ETF",
    "XLP": "State Street Consumer Staples Select Sector SPDR ETF",
    "XLRE": "State Street Real Estate Select Sector SPDR ETF",
    "XLU": "State Street Utilities Select Sector SPDR ETF",
    "XLV": "State Street Health Care Select Sector SPDR ETF",
    "XLY": "State Street Consumer Discretionary Select Sector SPDR ETF",
    "XOM": "ExxonMobil Holdings Corporation",
}


class GdeltNewsArchiveError(ValueError):
    """Stable failure at the GDELT collection boundary."""


@dataclass(frozen=True)
class GdeltQueryEntry:
    instrument_id: str
    symbol: str
    canonical_company_name: str
    query: str
    source_kind: str
    source_name: str
    source_path: str

    def __post_init__(self) -> None:
        if (
            _IDENTIFIER.fullmatch(self.instrument_id) is None
            or _IDENTIFIER.fullmatch(self.symbol) is None
            or not _text(self.canonical_company_name)
            or self.query != f'"{self.canonical_company_name}"'
            or not _text(self.source_kind)
            or not _text(self.source_name)
            or not _text(self.source_path)
            or self.query == f'"{self.symbol}"'
        ):
            raise GdeltNewsArchiveError("gdelt_query_entry_invalid")

    def to_canonical_body(self) -> dict[str, str]:
        return {
            "instrumentId": self.instrument_id,
            "symbol": self.symbol,
            "canonicalCompanyName": self.canonical_company_name,
            "gdeltQuery": self.query,
            "sourceKind": self.source_kind,
            "sourceName": self.source_name,
            "sourcePath": self.source_path,
        }


@dataclass(frozen=True)
class FrozenGdeltQueryMap:
    entries: tuple[GdeltQueryEntry, ...]
    scope_plan_sha256: str
    directory_master_sha256: str
    frozen_at: str

    def __post_init__(self) -> None:
        symbols = tuple(entry.symbol for entry in self.entries)
        if (
            len(self.entries) != 48
            or len(set(symbols)) != 48
            or set(symbols) != set(_CANONICAL_COMPANY_NAMES)
            or _SHA256.fullmatch(self.scope_plan_sha256) is None
            or _SHA256.fullmatch(self.directory_master_sha256) is None
        ):
            raise GdeltNewsArchiveError("gdelt_query_map_invalid")
        _parse_utc(self.frozen_at)

    def to_canonical_body(self) -> dict[str, object]:
        return {
            "schemaVersion": "rp001-s2-gdelt-company-query-map.v1",
            "identityDomain": "rp001_s2.gdelt_company_query_map",
            "frozenAt": self.frozen_at,
            "scopePlan": {
                "path": (
                    "scope-plans-v2/toss-minute-scope-plan-"
                    "9c1841e5c72c6e28d08fc73c24b6dfc1d8e95fcf3d457d40bfe0dd32b36b7ec3.json"
                ),
                "sha256": self.scope_plan_sha256,
            },
            "instrumentDirectoryMaster": {
                "path": (
                    "instrument-directories-v2/"
                    "b24e22d0edfe528aea674a568386238e719f3d67efcdfad102123aa130b9b770/"
                    "instrument-master.json"
                ),
                "sha256": self.directory_master_sha256,
            },
            "queryContract": {
                "endpoint": _ENDPOINT,
                "format": "json",
                "modes": ["timelinevolraw", "timelinetone"],
                "startDatetime": _START_DATETIME,
                "endDatetime": _END_DATETIME,
                "timelineSmooth": 0,
                "requestStartIntervalSeconds": 10,
                "http429BackoffSeconds": [30, 60, 120],
                "maxAttempts": 4,
            },
            "entries": [entry.to_canonical_body() for entry in self.entries],
        }


def build_gdelt_query_map(
    *,
    scope_plan_source: bytes,
    directory_master_source: bytes,
    frozen_at: str,
) -> FrozenGdeltQueryMap:
    """Bind unique company-name searches to the exact frozen instrument set."""
    scope_plan = _canonical_object(scope_plan_source)
    directory = _canonical_object(directory_master_source)
    instruments = scope_plan.get("instruments")
    records = directory.get("records")
    if not isinstance(instruments, list) or not isinstance(records, list):
        raise GdeltNewsArchiveError("gdelt_query_sources_invalid")
    official_names: dict[str, str] = {}
    for value in records:
        if not isinstance(value, dict):
            raise GdeltNewsArchiveError("gdelt_query_sources_invalid")
        symbol = value.get("symbol")
        security_name = value.get("securityName")
        if isinstance(symbol, str) and isinstance(security_name, str):
            official_names[symbol] = security_name
    entries: list[GdeltQueryEntry] = []
    seen: set[str] = set()
    for value in instruments:
        if not isinstance(value, dict):
            raise GdeltNewsArchiveError("gdelt_query_sources_invalid")
        instrument_id = value.get("instrumentId")
        symbol = value.get("symbol")
        if (
            not isinstance(instrument_id, str)
            or not isinstance(symbol, str)
            or symbol in seen
            or symbol not in _CANONICAL_COMPANY_NAMES
        ):
            raise GdeltNewsArchiveError("gdelt_query_sources_invalid")
        seen.add(symbol)
        if symbol == "000660":
            source_kind = "registered_program_identity"
            source_name = "SK hynix"
            source_path = (
                "docs/codex/specs/"
                "2026-07-10-mania-indicator-validation-design.md"
            )
        else:
            source_name = official_names.get(symbol, "")
            if not source_name:
                raise GdeltNewsArchiveError("gdelt_query_sources_invalid")
            source_kind = "official_nasdaq_trader_directory"
            source_path = (
                "instrument-directories-v2/"
                "b24e22d0edfe528aea674a568386238e719f3d67efcdfad102123aa130b9b770/"
                "instrument-master.json"
            )
        canonical_name = _CANONICAL_COMPANY_NAMES[symbol]
        entries.append(
            GdeltQueryEntry(
                instrument_id=instrument_id,
                symbol=symbol,
                canonical_company_name=canonical_name,
                query=f'"{canonical_name}"',
                source_kind=source_kind,
                source_name=source_name,
                source_path=source_path,
            )
        )
    return FrozenGdeltQueryMap(
        entries=tuple(entries),
        scope_plan_sha256=sha256_bytes(scope_plan_source),
        directory_master_sha256=sha256_bytes(directory_master_source),
        frozen_at=frozen_at,
    )


@dataclass(frozen=True)
class FrozenGdeltTickerProxyMap:
    company_query_map_sha256: str
    frozen_at: str

    def __post_init__(self) -> None:
        if _SHA256.fullmatch(self.company_query_map_sha256) is None:
            raise GdeltNewsArchiveError("gdelt_ticker_proxy_map_invalid")
        _parse_utc(self.frozen_at)

    def to_canonical_body(self) -> dict[str, object]:
        forbidden = [
            symbol
            for symbol in _FROZEN_SYMBOLS
            if symbol not in _TICKER_PROXY_SYMBOLS
        ]
        return {
            "schemaVersion": "rp001-s2-gdelt-ticker-query-proxy-map.v1",
            "identityDomain": "rp001_s2.gdelt_ticker_query_proxy_map",
            "frozenAt": self.frozen_at,
            "sourceCompanyQueryMap": {
                "path": (
                    f"query-maps/{self.company_query_map_sha256}/query-map.json"
                ),
                "sha256": self.company_query_map_sha256,
            },
            "queryKind": "ticker_query_proxy",
            "evidenceStatus": "proxy_only",
            "mixingWithCompanyMeasure": "forbidden",
            "eligibleSymbols": list(_TICKER_PROXY_SYMBOLS),
            "entries": [
                {
                    "instrumentId": symbol,
                    "symbol": symbol,
                    "gdeltQuery": symbol,
                    "queryKind": "ticker_query_proxy",
                    "evidenceStatus": "proxy_only",
                }
                for symbol in _TICKER_PROXY_SYMBOLS
            ],
            "fallbackForbiddenSymbols": forbidden,
            "queryContract": {
                "endpoint": _ENDPOINT,
                "format": "json",
                "modes": ["timelinevolraw", "timelinetone"],
                "startDatetime": _START_DATETIME,
                "endDatetime": _END_DATETIME,
                "timelineSmooth": 0,
                "requestStartIntervalSeconds": 10,
                "http429BackoffSeconds": [30, 60, 120],
                "maxAttempts": 4,
            },
        }


def build_gdelt_ticker_proxy_map(
    *,
    company_query_map_sha256: str,
    frozen_at: str,
) -> FrozenGdeltTickerProxyMap:
    """Freeze the isolated three-symbol ticker proxy and forbid all others."""
    return FrozenGdeltTickerProxyMap(
        company_query_map_sha256=company_query_map_sha256,
        frozen_at=frozen_at,
    )


@dataclass(frozen=True)
class GdeltNewsScope:
    entry: GdeltQueryEntry
    mode: str
    start_datetime: str = _START_DATETIME
    end_datetime: str = _END_DATETIME

    def __post_init__(self) -> None:
        if (
            not isinstance(self.entry, GdeltQueryEntry)
            or self.mode not in _MODES
            or not re.fullmatch(r"[0-9]{14}", self.start_datetime)
            or not re.fullmatch(r"[0-9]{14}", self.end_datetime)
            or self.start_datetime >= self.end_datetime
        ):
            raise GdeltNewsArchiveError("gdelt_scope_invalid")

    @classmethod
    def for_entry(cls, entry: GdeltQueryEntry, mode: str) -> GdeltNewsScope:
        return cls(entry=entry, mode=mode)

    def to_canonical_body(self, query_map_sha256: str) -> dict[str, object]:
        if _SHA256.fullmatch(query_map_sha256) is None:
            raise GdeltNewsArchiveError("gdelt_scope_invalid")
        return {
            "schemaVersion": "rp001-s2-gdelt-news-scope.v1",
            "identityDomain": "rp001_s2.gdelt_news_scope",
            "queryMapSha256": query_map_sha256,
            "instrumentId": self.entry.instrument_id,
            "symbol": self.entry.symbol,
            "query": self.entry.query,
            "mode": self.mode,
            "startDatetime": self.start_datetime,
            "endDatetime": self.end_datetime,
            "format": "json",
            "timelineSmooth": 0,
        }


@dataclass(frozen=True)
class GdeltHttpRequest:
    method: str
    url: str
    headers: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class GdeltHttpResponse:
    status: int
    headers: tuple[tuple[str, str], ...]
    body: bytes

    def __post_init__(self) -> None:
        if (
            type(self.status) is not int
            or not 0 <= self.status <= 599
            or type(self.headers) is not tuple
            or type(self.body) is not bytes
        ):
            raise GdeltNewsArchiveError("gdelt_response_invalid")


@dataclass(frozen=True)
class GdeltAttempt:
    ordinal: int
    request: GdeltHttpRequest
    request_started_at: str
    received_at: str
    response: GdeltHttpResponse


@dataclass(frozen=True)
class GdeltScopeOutcome:
    scope: GdeltNewsScope
    terminal_status: str
    terminal_reason: str
    attempts: tuple[GdeltAttempt, ...]


@dataclass(frozen=True)
class StoredGdeltScope:
    scope_sha256: str
    archive_directory: Path
    raw_body_paths: tuple[Path, ...]
    metadata_paths: tuple[Path, ...]
    manifest_path: Path
    manifest_sha256_path: Path
    manifest_sha256: str


GdeltTransport = Callable[[GdeltHttpRequest], GdeltHttpResponse]


class _ReadableHttpResponse(Protocol):
    status: int
    headers: Mapping[str, str]

    def read(self, limit: int) -> bytes: ...

    def close(self) -> None: ...


class _GdeltUrlOpener(Protocol):
    def open(
        self,
        request: urllib.request.Request,
        timeout: int,
    ) -> _ReadableHttpResponse: ...


class _RejectGdeltRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: object,
        code: int,
        msg: str,
        headers: Mapping[str, str],
        newurl: str,
    ) -> None:
        raise GdeltNewsArchiveError("gdelt_redirect_rejected")


class StrictGdeltTransport:
    """Execute only the frozen read-only GDELT DOC request contract."""

    def __init__(
        self,
        *,
        opener: _GdeltUrlOpener,
        response_limit_bytes: int = _MAX_RESPONSE_BYTES,
    ) -> None:
        if response_limit_bytes <= 0:
            raise GdeltNewsArchiveError("gdelt_transport_invalid")
        self._opener = opener
        self._response_limit_bytes = response_limit_bytes

    def __call__(self, request: GdeltHttpRequest) -> GdeltHttpResponse:
        _validate_strict_request(request)
        outgoing = urllib.request.Request(
            request.url,
            method=request.method,
            headers=dict(request.headers),
        )
        try:
            response = self._opener.open(outgoing, timeout=180)
            try:
                status = response.status
                headers = tuple(
                    (str(key).lower(), str(value))
                    for key, value in response.headers.items()
                )
                body = response.read(self._response_limit_bytes + 1)
            finally:
                response.close()
        except urllib.error.HTTPError as error:
            if 300 <= error.code < 400:
                raise GdeltNewsArchiveError("gdelt_redirect_rejected") from None
            status = error.code
            headers = tuple(
                (str(key).lower(), str(value))
                for key, value in error.headers.items()
            )
            body = error.read(self._response_limit_bytes + 1)
            error.close()
        except OSError:
            return GdeltHttpResponse(
                status=0,
                headers=(("content-type", "application/json"),),
                body=canonical_json_bytes(
                    {
                        "schemaVersion": (
                            "rp001-s2-gdelt-transport-failure.v1"
                        ),
                        "errorCode": "gdelt_transport_oserror",
                    }
                ),
            )
        if 300 <= status < 400:
            raise GdeltNewsArchiveError("gdelt_redirect_rejected")
        if len(body) > self._response_limit_bytes:
            raise GdeltNewsArchiveError("gdelt_response_too_large")
        return GdeltHttpResponse(status=status, headers=headers, body=body)


def build_live_gdelt_transport() -> StrictGdeltTransport:
    """Build the production transport with redirects disabled."""
    opener = urllib.request.build_opener(_RejectGdeltRedirectHandler())
    return StrictGdeltTransport(opener=opener)


class GlobalGdeltWorker:
    """Run DOC queries serially under one global request-start clock."""

    def __init__(
        self,
        *,
        transport: GdeltTransport,
        monotonic: Callable[[], float],
        sleeper: Callable[[float], None],
        utc_clock: Callable[[], datetime],
    ) -> None:
        self._transport = transport
        self._monotonic = monotonic
        self._sleeper = sleeper
        self._utc_clock = utc_clock
        self._last_request_start: float | None = None

    def collect(
        self,
        scopes: tuple[GdeltNewsScope, ...],
    ) -> tuple[GdeltScopeOutcome, ...]:
        if type(scopes) is not tuple or any(
            not isinstance(scope, GdeltNewsScope) for scope in scopes
        ):
            raise GdeltNewsArchiveError("gdelt_scopes_invalid")
        return tuple(self._collect_scope(scope) for scope in scopes)

    def _collect_scope(self, scope: GdeltNewsScope) -> GdeltScopeOutcome:
        attempts: list[GdeltAttempt] = []
        for ordinal in range(1, 5):
            self._wait_for_global_slot()
            request = _request_for_scope(scope)
            request_started_at = _format_utc(self._utc_clock())
            self._last_request_start = self._monotonic()
            response = self._transport(request)
            attempts.append(
                GdeltAttempt(
                    ordinal=ordinal,
                    request=request,
                    request_started_at=request_started_at,
                    received_at=_format_utc(self._utc_clock()),
                    response=response,
                )
            )
            if response.status == 200:
                reason = (
                    "http_200_json_valid"
                    if _valid_timeline_json(response.body)
                    else "response_contract_invalid"
                )
                status = "completed" if reason == "http_200_json_valid" else "invalid"
                return GdeltScopeOutcome(scope, status, reason, tuple(attempts))
            if response.status != 429:
                reason = (
                    f"http_status_{response.status}"
                    if response.status
                    else "transport_error"
                )
                return GdeltScopeOutcome(
                    scope,
                    "failed",
                    reason,
                    tuple(attempts),
                )
            if ordinal <= len(_RATE_LIMIT_BACKOFF_SECONDS):
                self._sleeper(_RATE_LIMIT_BACKOFF_SECONDS[ordinal - 1])
        return GdeltScopeOutcome(
            scope,
            "provider_rate_limited",
            "http_429_retry_exhausted",
            tuple(attempts),
        )

    def _wait_for_global_slot(self) -> None:
        if self._last_request_start is None:
            return
        remaining = _REQUEST_INTERVAL_SECONDS - (
            self._monotonic() - self._last_request_start
        )
        if remaining > 0:
            self._sleeper(remaining)


class GdeltArchiveStorage:
    """Publish and verify content-addressed GDELT raw evidence."""

    def __init__(self, root: Path) -> None:
        if not root.is_absolute() or not root.is_dir() or root.is_symlink():
            raise GdeltNewsArchiveError("gdelt_archive_root_invalid")
        self._root = root
        self._store = LocalArtifactStore(root)

    def publish_query_map(
        self,
        query_map: FrozenGdeltQueryMap,
    ) -> LocalArtifactBinding:
        if not isinstance(query_map, FrozenGdeltQueryMap):
            raise GdeltNewsArchiveError("gdelt_query_map_invalid")
        source = canonical_json_bytes(query_map.to_canonical_body())
        artifact_sha256 = sha256_bytes(source)
        path = self._root / "query-maps" / artifact_sha256 / "query-map.json"
        if path.exists() or Path(f"{path}.sha256").exists():
            if _verified_bytes(path, artifact_sha256) != source:
                raise GdeltNewsArchiveError("gdelt_query_map_conflict")
            return LocalArtifactBinding(
                path=path,
                sidecar_path=Path(f"{path}.sha256"),
                artifact_sha256=artifact_sha256,
            )
        return self._store.publish_bytes(path, source)

    def publish_outcome(
        self,
        query_map_binding: LocalArtifactBinding,
        outcome: GdeltScopeOutcome,
    ) -> StoredGdeltScope:
        self._require_query_map_binding(query_map_binding)
        if not isinstance(outcome, GdeltScopeOutcome) or not outcome.attempts:
            raise GdeltNewsArchiveError("gdelt_scope_outcome_invalid")
        scope_body = outcome.scope.to_canonical_body(
            query_map_binding.artifact_sha256
        )
        scope_sha256 = sha256_bytes(canonical_json_bytes(scope_body))
        archive_directory = (
            self._root
            / "captures"
            / query_map_binding.artifact_sha256
            / outcome.scope.entry.symbol
            / outcome.scope.mode
            / scope_sha256
        )
        manifest_path = archive_directory / "manifest.json"
        if manifest_path.exists() or Path(f"{manifest_path}.sha256").exists():
            stored = self._stored_from_manifest(manifest_path)
            self.verify_scope(stored)
            return stored
        recovered = self.recover_partial_scope(
            query_map_binding,
            outcome.scope,
            recovered_at=outcome.attempts[-1].received_at,
        )
        if recovered is not None:
            return recovered
        attempt_bindings: list[dict[str, object]] = []
        raw_paths: list[Path] = []
        metadata_paths: list[Path] = []
        for attempt in outcome.attempts:
            extension = "json" if attempt.response.status == 200 else "txt"
            body_path = (
                archive_directory
                / f"attempt-{attempt.ordinal:03d}.body.{extension}"
            )
            body_binding = self._store.publish_bytes(
                body_path,
                attempt.response.body,
            )
            metadata_body = _attempt_metadata(attempt, body_binding, self._root)
            metadata_binding = self._store.publish_json(
                archive_directory / f"attempt-{attempt.ordinal:03d}.metadata.json",
                metadata_body,
            )
            raw_paths.append(body_binding.path)
            metadata_paths.append(metadata_binding.path)
            attempt_bindings.append(
                {
                    "ordinal": attempt.ordinal,
                    "status": attempt.response.status,
                    "body": _binding_body(body_binding, self._root),
                    "metadata": _binding_body(metadata_binding, self._root),
                }
            )
        manifest_body: dict[str, object] = {
            "schemaVersion": "rp001-s2-gdelt-news-manifest.v1",
            "scope": scope_body,
            "scopeSha256": scope_sha256,
            "queryMap": _binding_body(query_map_binding, self._root),
            "attempts": attempt_bindings,
            "terminal": {
                "status": outcome.terminal_status,
                "reason": outcome.terminal_reason,
            },
            "completedAt": outcome.attempts[-1].received_at,
        }
        manifest_binding = self._store.publish_json(manifest_path, manifest_body)
        stored = StoredGdeltScope(
            scope_sha256=scope_sha256,
            archive_directory=archive_directory,
            raw_body_paths=tuple(raw_paths),
            metadata_paths=tuple(metadata_paths),
            manifest_path=manifest_binding.path,
            manifest_sha256_path=manifest_binding.sidecar_path,
            manifest_sha256=manifest_binding.artifact_sha256,
        )
        self.verify_scope(stored)
        return stored

    def recover_partial_scope(
        self,
        query_map_binding: LocalArtifactBinding,
        scope: GdeltNewsScope,
        *,
        recovered_at: str,
    ) -> StoredGdeltScope | None:
        """Seal verified orphan artifacts as an explicit invalid terminal."""
        self._require_query_map_binding(query_map_binding)
        if not isinstance(scope, GdeltNewsScope):
            raise GdeltNewsArchiveError("gdelt_scope_invalid")
        _parse_utc(recovered_at)
        scope_body = scope.to_canonical_body(query_map_binding.artifact_sha256)
        scope_sha256 = sha256_bytes(canonical_json_bytes(scope_body))
        archive_directory = (
            self._root
            / "captures"
            / query_map_binding.artifact_sha256
            / scope.entry.symbol
            / scope.mode
            / scope_sha256
        )
        manifest_path = archive_directory / "manifest.json"
        if manifest_path.exists() or Path(f"{manifest_path}.sha256").exists():
            stored = self._stored_from_manifest(manifest_path)
            self.verify_scope(stored)
            return stored
        if not archive_directory.exists():
            return None
        artifacts: list[dict[str, object]] = []
        raw_paths: list[Path] = []
        metadata_paths: list[Path] = []
        artifact_paths = sorted(
            path
            for path in archive_directory.iterdir()
            if not path.name.endswith(".sha256")
        )
        if not artifact_paths:
            return None
        for path in artifact_paths:
            match = re.fullmatch(
                r"attempt-([0-9]{3})\.(body\.(?:json|txt)|metadata\.json)",
                path.name,
            )
            if match is None:
                raise GdeltNewsArchiveError(
                    "gdelt_archive_verification_failed"
                )
            source = _verified_bytes(path)
            binding = LocalArtifactBinding(
                path=path,
                sidecar_path=Path(f"{path}.sha256"),
                artifact_sha256=sha256_bytes(source),
            )
            kind = "metadata" if match.group(2) == "metadata.json" else "body"
            artifacts.append(
                {
                    "ordinal": int(match.group(1)),
                    "kind": kind,
                    "artifact": {
                        **_binding_body(binding, self._root),
                        "byteLength": len(source),
                    },
                }
            )
            if kind == "body":
                raw_paths.append(path)
            else:
                metadata_paths.append(path)
        expected_files = {
            item
            for path in artifact_paths
            for item in (path, Path(f"{path}.sha256"))
        }
        actual_files = {
            path
            for path in archive_directory.iterdir()
            if path.is_file() or path.is_symlink()
        }
        if actual_files != expected_files:
            raise GdeltNewsArchiveError("gdelt_archive_verification_failed")
        manifest_body: dict[str, object] = {
            "schemaVersion": "rp001-s2-gdelt-partial-recovery-manifest.v1",
            "scope": scope_body,
            "scopeSha256": scope_sha256,
            "queryMap": _binding_body(query_map_binding, self._root),
            "partialArtifacts": artifacts,
            "terminal": {
                "status": "invalid",
                "reason": "partial_attempt_without_terminal_manifest",
            },
            "recoveredAt": recovered_at,
        }
        manifest_binding = self._store.publish_json(manifest_path, manifest_body)
        stored = StoredGdeltScope(
            scope_sha256=scope_sha256,
            archive_directory=archive_directory,
            raw_body_paths=tuple(raw_paths),
            metadata_paths=tuple(metadata_paths),
            manifest_path=manifest_binding.path,
            manifest_sha256_path=manifest_binding.sidecar_path,
            manifest_sha256=manifest_binding.artifact_sha256,
        )
        self.verify_scope(stored)
        return stored

    def verify_scope(self, stored: StoredGdeltScope) -> None:
        try:
            self._verify_scope(stored)
        except Exception:
            raise GdeltNewsArchiveError(
                "gdelt_archive_verification_failed"
            ) from None

    def _verify_scope(self, stored: StoredGdeltScope) -> None:
        if not isinstance(stored, StoredGdeltScope):
            raise ValueError
        manifest_source = _verified_bytes(
            stored.manifest_path,
            stored.manifest_sha256,
        )
        if stored.manifest_sha256_path != Path(f"{stored.manifest_path}.sha256"):
            raise ValueError
        manifest = _canonical_object(manifest_source)
        schema_version = manifest.get("schemaVersion")
        if (
            schema_version
            not in {
                "rp001-s2-gdelt-news-manifest.v1",
                "rp001-s2-gdelt-partial-recovery-manifest.v1",
            }
            or manifest.get("scopeSha256") != stored.scope_sha256
            or sha256_bytes(canonical_json_bytes(manifest.get("scope")))
            != stored.scope_sha256
        ):
            raise ValueError
        query_map = _binding_from_body(manifest.get("queryMap"), self._root)
        self._require_query_map_binding(query_map)
        scope = manifest.get("scope")
        query_map_body = _canonical_object(
            _verified_bytes(query_map.path, query_map.artifact_sha256)
        )
        _validate_scope_binding(scope, query_map_body, query_map.artifact_sha256)
        if schema_version == "rp001-s2-gdelt-partial-recovery-manifest.v1":
            self._verify_recovery_scope(stored, manifest)
            return
        attempts = manifest.get("attempts")
        if not isinstance(attempts, list) or not attempts:
            raise ValueError
        raw_paths: list[Path] = []
        metadata_paths: list[Path] = []
        expected_files = {stored.manifest_path, stored.manifest_sha256_path}
        statuses: list[int] = []
        valid_bodies: list[bool] = []
        for ordinal, value in enumerate(attempts, start=1):
            if not isinstance(value, dict):
                raise ValueError
            status = value.get("status")
            if (
                type(status) is not int
                or not 0 <= status <= 599
                or value.get("ordinal", ordinal) != ordinal
            ):
                raise ValueError
            raw = _binding_from_body(
                value.get("body"),
                self._root,
                allow_byte_length=True,
            )
            metadata = _binding_from_body(value.get("metadata"), self._root)
            raw_source = _verified_bytes(raw.path, raw.artifact_sha256)
            metadata_source = _verified_bytes(
                metadata.path,
                metadata.artifact_sha256,
            )
            metadata_body = _canonical_object(metadata_source)
            _validate_attempt_binding(
                ordinal=ordinal,
                status=status,
                raw=raw,
                raw_source=raw_source,
                metadata=metadata,
                metadata_body=metadata_body,
                scope=scope,
                manifest_body_binding=value.get("body"),
                archive_directory=stored.archive_directory,
            )
            raw_paths.append(raw.path)
            metadata_paths.append(metadata.path)
            statuses.append(status)
            valid_bodies.append(_valid_timeline_json(raw_source))
            expected_files.update(
                {
                    raw.path,
                    raw.sidecar_path,
                    metadata.path,
                    metadata.sidecar_path,
                }
            )
        if (
            tuple(raw_paths) != stored.raw_body_paths
            or tuple(metadata_paths) != stored.metadata_paths
            or stored.archive_directory != stored.manifest_path.parent
            or any(path.parent != stored.archive_directory for path in raw_paths)
            or any(path.parent != stored.archive_directory for path in metadata_paths)
        ):
            raise ValueError
        actual_files = {
            path
            for path in stored.archive_directory.iterdir()
            if path.is_file() or path.is_symlink()
        }
        if actual_files != expected_files:
            raise ValueError
        _validate_terminal_binding(
            manifest.get("terminal"),
            statuses,
            valid_bodies,
        )
        completed_at = manifest.get("completedAt")
        if not isinstance(completed_at, str):
            raise ValueError
        if _parse_utc(completed_at) < _parse_utc(
            str(_canonical_object(_verified_bytes(
                metadata_paths[-1]
            )).get("receivedAt"))
        ):
            raise ValueError

    def _verify_recovery_scope(
        self,
        stored: StoredGdeltScope,
        manifest: dict[str, object],
    ) -> None:
        if manifest.get("terminal") != {
            "status": "invalid",
            "reason": "partial_attempt_without_terminal_manifest",
        }:
            raise ValueError
        recovered_at = manifest.get("recoveredAt")
        if not isinstance(recovered_at, str):
            raise ValueError
        _parse_utc(recovered_at)
        artifacts = manifest.get("partialArtifacts")
        if not isinstance(artifacts, list) or not artifacts:
            raise ValueError
        raw_paths: list[Path] = []
        metadata_paths: list[Path] = []
        expected_files = {stored.manifest_path, stored.manifest_sha256_path}
        previous_key: tuple[int, str] | None = None
        for value in artifacts:
            if not isinstance(value, dict):
                raise ValueError
            ordinal = value.get("ordinal")
            kind = value.get("kind")
            if type(ordinal) is not int or ordinal <= 0 or kind not in {"body", "metadata"}:
                raise ValueError
            key = (ordinal, str(kind))
            if previous_key is not None and key <= previous_key:
                raise ValueError
            previous_key = key
            binding_body = value.get("artifact")
            binding = _binding_from_body(
                binding_body,
                self._root,
                allow_byte_length=True,
            )
            source = _verified_bytes(binding.path, binding.artifact_sha256)
            if not isinstance(binding_body, dict) or binding_body.get("byteLength") != len(source):
                raise ValueError
            expected_name = (
                f"attempt-{ordinal:03d}.metadata.json"
                if kind == "metadata"
                else rf"attempt-{ordinal:03d}.body.(?:json|txt)"
            )
            if (
                binding.path.parent != stored.archive_directory
                or (
                    kind == "metadata"
                    and binding.path.name != expected_name
                )
                or (
                    kind == "body"
                    and re.fullmatch(expected_name, binding.path.name) is None
                )
            ):
                raise ValueError
            if kind == "body":
                raw_paths.append(binding.path)
            else:
                metadata_paths.append(binding.path)
            expected_files.update({binding.path, binding.sidecar_path})
        if (
            tuple(raw_paths) != stored.raw_body_paths
            or tuple(metadata_paths) != stored.metadata_paths
            or stored.archive_directory != stored.manifest_path.parent
        ):
            raise ValueError
        actual_files = {
            path
            for path in stored.archive_directory.iterdir()
            if path.is_file() or path.is_symlink()
        }
        if actual_files != expected_files:
            raise ValueError

    def _stored_from_manifest(self, manifest_path: Path) -> StoredGdeltScope:
        manifest_source = _verified_bytes(manifest_path)
        manifest = _canonical_object(manifest_source)
        if (
            manifest.get("schemaVersion")
            == "rp001-s2-gdelt-partial-recovery-manifest.v1"
        ):
            artifacts = manifest.get("partialArtifacts")
            if not isinstance(artifacts, list):
                raise GdeltNewsArchiveError("gdelt_archive_verification_failed")
            raw_paths = tuple(
                _binding_from_body(
                    value.get("artifact"),
                    self._root,
                    allow_byte_length=True,
                ).path
                for value in artifacts
                if isinstance(value, dict) and value.get("kind") == "body"
            )
            metadata_paths = tuple(
                _binding_from_body(
                    value.get("artifact"),
                    self._root,
                    allow_byte_length=True,
                ).path
                for value in artifacts
                if isinstance(value, dict) and value.get("kind") == "metadata"
            )
            return StoredGdeltScope(
                scope_sha256=str(manifest.get("scopeSha256")),
                archive_directory=manifest_path.parent,
                raw_body_paths=raw_paths,
                metadata_paths=metadata_paths,
                manifest_path=manifest_path,
                manifest_sha256_path=Path(f"{manifest_path}.sha256"),
                manifest_sha256=sha256_bytes(manifest_source),
            )
        attempts = manifest.get("attempts")
        if not isinstance(attempts, list):
            raise GdeltNewsArchiveError("gdelt_archive_verification_failed")
        raw_paths = tuple(
            _binding_from_body(
                value.get("body"),
                self._root,
                allow_byte_length=True,
            ).path
            for value in attempts
            if isinstance(value, dict)
        )
        metadata_paths = tuple(
            _binding_from_body(value.get("metadata"), self._root).path
            for value in attempts
            if isinstance(value, dict)
        )
        return StoredGdeltScope(
            scope_sha256=str(manifest.get("scopeSha256")),
            archive_directory=manifest_path.parent,
            raw_body_paths=raw_paths,
            metadata_paths=metadata_paths,
            manifest_path=manifest_path,
            manifest_sha256_path=Path(f"{manifest_path}.sha256"),
            manifest_sha256=sha256_bytes(manifest_source),
        )

    def _require_query_map_binding(
        self,
        binding: LocalArtifactBinding,
    ) -> None:
        if (
            not isinstance(binding, LocalArtifactBinding)
            or _SHA256.fullmatch(binding.artifact_sha256) is None
            or binding.path
            != self._root
            / "query-maps"
            / binding.artifact_sha256
            / "query-map.json"
            or binding.sidecar_path != Path(f"{binding.path}.sha256")
        ):
            raise GdeltNewsArchiveError("gdelt_query_map_binding_invalid")
        source = _verified_bytes(binding.path, binding.artifact_sha256)
        body = _canonical_object(source)
        if body.get("schemaVersion") != "rp001-s2-gdelt-company-query-map.v1":
            raise GdeltNewsArchiveError("gdelt_query_map_binding_invalid")


def _request_for_scope(scope: GdeltNewsScope) -> GdeltHttpRequest:
    query = urllib.parse.urlencode(
        {
            "query": scope.entry.query,
            "mode": scope.mode,
            "format": "json",
            "startdatetime": scope.start_datetime,
            "enddatetime": scope.end_datetime,
            "timelinesmooth": "0",
        }
    )
    return GdeltHttpRequest(
        method="GET",
        url=f"{_ENDPOINT}?{query}",
        headers=(
            ("Accept", "application/json"),
            ("User-Agent", "RP-001 research collector (zero-cost, read-only)"),
        ),
    )


def _validate_strict_request(request: GdeltHttpRequest) -> None:
    if not isinstance(request, GdeltHttpRequest) or request.method != "GET":
        raise GdeltNewsArchiveError("gdelt_request_not_allowed")
    parsed = urllib.parse.urlsplit(request.url)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "api.gdeltproject.org"
        or parsed.hostname != "api.gdeltproject.org"
        or parsed.port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path != "/api/v2/doc/doc"
        or parsed.fragment
    ):
        raise GdeltNewsArchiveError("gdelt_request_not_allowed")
    try:
        pairs = urllib.parse.parse_qsl(
            parsed.query,
            keep_blank_values=True,
            strict_parsing=True,
        )
    except ValueError:
        raise GdeltNewsArchiveError("gdelt_request_not_allowed") from None
    query = dict(pairs)
    frozen_queries = {
        f'"{company_name}"'
        for company_name in _CANONICAL_COMPANY_NAMES.values()
    } | set(_TICKER_PROXY_SYMBOLS)
    if (
        len(pairs) != len(query)
        or set(query)
        != {
            "query",
            "mode",
            "format",
            "startdatetime",
            "enddatetime",
            "timelinesmooth",
        }
        or query["query"] not in frozen_queries
        or query["mode"] not in _MODES
        or query["format"] != "json"
        or query["startdatetime"] != _START_DATETIME
        or query["enddatetime"] != _END_DATETIME
        or query["timelinesmooth"] != "0"
        or request.headers
        != (
            ("Accept", "application/json"),
            ("User-Agent", "RP-001 research collector (zero-cost, read-only)"),
        )
    ):
        raise GdeltNewsArchiveError("gdelt_request_not_allowed")


def _attempt_metadata(
    attempt: GdeltAttempt,
    body_binding: LocalArtifactBinding,
    root: Path,
) -> dict[str, object]:
    return {
        "schemaVersion": "rp001-s2-gdelt-raw-capture-metadata.v1",
        "attempt": attempt.ordinal,
        "method": attempt.request.method,
        "endpoint": _ENDPOINT,
        "mode": urllib.parse.parse_qs(
            urllib.parse.urlsplit(attempt.request.url).query
        )["mode"][0],
        "querySha256": sha256_bytes(
            urllib.parse.parse_qs(
                urllib.parse.urlsplit(attempt.request.url).query
            )["query"][0].encode("utf-8")
        ),
        "requestUrlSha256": sha256_bytes(attempt.request.url.encode("utf-8")),
        "requestStartedAt": attempt.request_started_at,
        "receivedAt": attempt.received_at,
        "status": attempt.response.status,
        "contentType": _response_content_type(attempt.response.headers),
        "headers": [
            [key.lower(), value] for key, value in attempt.response.headers
        ],
        "body": {
            **_binding_body(body_binding, root),
            "byteLength": len(attempt.response.body),
        },
    }


def _validate_scope_binding(
    scope: object,
    query_map: dict[str, object],
    query_map_sha256: str,
) -> None:
    if not isinstance(scope, dict) or scope.get("queryMapSha256") != query_map_sha256:
        raise GdeltNewsArchiveError("gdelt_scope_binding_invalid")
    contract = query_map.get("queryContract")
    entries = query_map.get("entries")
    if not isinstance(contract, dict) or not isinstance(entries, list):
        raise GdeltNewsArchiveError("gdelt_scope_binding_invalid")
    matches = [
        entry
        for entry in entries
        if isinstance(entry, dict)
        and entry.get("instrumentId") == scope.get("instrumentId")
        and entry.get("symbol") == scope.get("symbol")
        and entry.get("gdeltQuery") == scope.get("query")
    ]
    if (
        len(matches) != 1
        or scope.get("schemaVersion") != "rp001-s2-gdelt-news-scope.v1"
        or scope.get("identityDomain") != "rp001_s2.gdelt_news_scope"
        or scope.get("mode") not in _MODES
        or scope.get("mode") not in contract.get("modes", [])
        or scope.get("startDatetime") != contract.get("startDatetime")
        or scope.get("endDatetime") != contract.get("endDatetime")
        or scope.get("format") != contract.get("format")
        or scope.get("timelineSmooth") != contract.get("timelineSmooth")
        or contract.get("endpoint") != _ENDPOINT
    ):
        raise GdeltNewsArchiveError("gdelt_scope_binding_invalid")


def _validate_attempt_binding(
    *,
    ordinal: int,
    status: int,
    raw: LocalArtifactBinding,
    raw_source: bytes,
    metadata: LocalArtifactBinding,
    metadata_body: dict[str, object],
    scope: object,
    manifest_body_binding: object,
    archive_directory: Path,
) -> None:
    if not isinstance(scope, dict):
        raise GdeltNewsArchiveError("gdelt_attempt_binding_invalid")
    expected_extension = "json" if status == 200 else "txt"
    expected_raw_name = f"attempt-{ordinal:03d}.body.{expected_extension}"
    expected_metadata_name = f"attempt-{ordinal:03d}.metadata.json"
    expected_query_sha256 = sha256_bytes(str(scope.get("query")).encode("utf-8"))
    expected_url = _url_for_scope_body(scope)
    if (
        raw.path.parent != archive_directory
        or raw.path.name != expected_raw_name
        or metadata.path.parent != archive_directory
        or metadata.path.name != expected_metadata_name
        or metadata_body.get("schemaVersion")
        != "rp001-s2-gdelt-raw-capture-metadata.v1"
        or metadata_body.get("attempt") != ordinal
        or metadata_body.get("method") != "GET"
        or metadata_body.get("endpoint") != _ENDPOINT
        or metadata_body.get("mode") != scope.get("mode")
        or metadata_body.get("querySha256") != expected_query_sha256
        or metadata_body.get("status") != status
        or (
            "requestUrlSha256" in metadata_body
            and metadata_body.get("requestUrlSha256")
            != sha256_bytes(expected_url.encode("utf-8"))
        )
        or (
            "queryKind" in metadata_body
            and metadata_body.get("queryKind") != "company_name_measure"
        )
        or (
            "evidenceStatus" in metadata_body
            and metadata_body.get("evidenceStatus") != "research_measure"
        )
    ):
        raise GdeltNewsArchiveError("gdelt_attempt_binding_invalid")
    metadata_body_binding = metadata_body.get("body")
    if (
        not isinstance(metadata_body_binding, dict)
        or metadata_body_binding.get("path")
        != raw.path.relative_to(archive_directory.parents[4]).as_posix()
        or metadata_body_binding.get("sha256") != raw.artifact_sha256
        or metadata_body_binding.get("byteLength") != len(raw_source)
        or (
            isinstance(manifest_body_binding, dict)
            and "byteLength" in manifest_body_binding
            and manifest_body_binding.get("byteLength") != len(raw_source)
        )
    ):
        raise GdeltNewsArchiveError("gdelt_attempt_binding_invalid")
    headers = _normalized_response_headers(metadata_body.get("headers"))
    content_type = headers.get("content-type")
    if (
        "contentType" in metadata_body
        and metadata_body.get("contentType") != content_type
    ):
        raise GdeltNewsArchiveError("gdelt_attempt_binding_invalid")
    if status in {0, 200} and (
        content_type is None
        or not content_type.lower().startswith("application/json")
    ):
        raise GdeltNewsArchiveError("gdelt_attempt_binding_invalid")
    started_at = metadata_body.get("requestStartedAt")
    received_at = metadata_body.get("receivedAt")
    if (
        not isinstance(started_at, str)
        or not isinstance(received_at, str)
        or _parse_utc(received_at) < _parse_utc(started_at)
    ):
        raise GdeltNewsArchiveError("gdelt_attempt_binding_invalid")


def _validate_terminal_binding(
    terminal: object,
    statuses: list[int],
    valid_bodies: list[bool],
) -> None:
    if not isinstance(terminal, dict) or not statuses:
        raise GdeltNewsArchiveError("gdelt_terminal_binding_invalid")
    status = terminal.get("status")
    reason = terminal.get("reason")
    final_status = statuses[-1]
    final_body_valid = valid_bodies[-1]
    valid = (
        status == "completed"
        and reason == "http_200_json_valid"
        and final_status == 200
        and final_body_valid
        or status == "invalid"
        and reason == "response_contract_invalid"
        and final_status == 200
        and not final_body_valid
        or status == "provider_rate_limited"
        and reason == "http_429_retry_exhausted"
        and statuses == [429, 429, 429, 429]
        or status == "failed"
        and final_status not in {200, 429}
        and reason
        == ("transport_error" if final_status == 0 else f"http_status_{final_status}")
    )
    if not valid:
        raise GdeltNewsArchiveError("gdelt_terminal_binding_invalid")


def _normalized_response_headers(value: object) -> dict[str, str]:
    pairs: list[tuple[str, str]] = []
    if isinstance(value, dict):
        pairs = [(str(key).lower(), str(item)) for key, item in value.items()]
    elif isinstance(value, list):
        for item in value:
            if (
                not isinstance(item, list)
                or len(item) != 2
                or not all(isinstance(part, str) for part in item)
            ):
                raise GdeltNewsArchiveError("gdelt_headers_invalid")
            pairs.append((item[0].lower(), item[1]))
    else:
        raise GdeltNewsArchiveError("gdelt_headers_invalid")
    normalized = dict(pairs)
    if len(normalized) != len(pairs):
        raise GdeltNewsArchiveError("gdelt_headers_invalid")
    return normalized


def _response_content_type(
    headers: tuple[tuple[str, str], ...],
) -> str | None:
    normalized = {key.lower(): value for key, value in headers}
    return normalized.get("content-type")


def _url_for_scope_body(scope: Mapping[str, object]) -> str:
    query = urllib.parse.urlencode(
        {
            "query": scope.get("query"),
            "mode": scope.get("mode"),
            "format": scope.get("format"),
            "startdatetime": scope.get("startDatetime"),
            "enddatetime": scope.get("endDatetime"),
            "timelinesmooth": str(scope.get("timelineSmooth")),
        }
    )
    return f"{_ENDPOINT}?{query}"


def _binding_body(
    binding: LocalArtifactBinding,
    root: Path,
) -> dict[str, str]:
    try:
        relative = binding.path.relative_to(root).as_posix()
    except ValueError:
        raise GdeltNewsArchiveError("gdelt_archive_binding_invalid") from None
    return {"path": relative, "sha256": binding.artifact_sha256}


def _binding_from_body(
    value: object,
    root: Path,
    *,
    allow_byte_length: bool = False,
) -> LocalArtifactBinding:
    return _binding_from_body_contract(
        value,
        root,
        allow_byte_length=allow_byte_length,
    )


def _binding_from_body_contract(
    value: object,
    root: Path,
    *,
    allow_byte_length: bool,
) -> LocalArtifactBinding:
    expected_keys = {"path", "sha256"}
    if allow_byte_length:
        expected_keys.add("byteLength")
    if (
        not isinstance(value, dict)
        or not {"path", "sha256"}.issubset(value)
        or not set(value).issubset(expected_keys)
        or (
            "byteLength" in value
            and (type(value.get("byteLength")) is not int or value["byteLength"] < 0)
        )
    ):
        raise GdeltNewsArchiveError("gdelt_archive_binding_invalid")
    relative = value.get("path")
    artifact_sha256 = value.get("sha256")
    if (
        not isinstance(relative, str)
        or not relative
        or Path(relative).is_absolute()
        or ".." in Path(relative).parts
        or not isinstance(artifact_sha256, str)
        or _SHA256.fullmatch(artifact_sha256) is None
    ):
        raise GdeltNewsArchiveError("gdelt_archive_binding_invalid")
    path = root / relative
    return LocalArtifactBinding(
        path=path,
        sidecar_path=Path(f"{path}.sha256"),
        artifact_sha256=artifact_sha256,
    )


def _verified_bytes(path: Path, expected_sha256: str | None = None) -> bytes:
    sidecar_path = Path(f"{path}.sha256")
    try:
        body_metadata = path.lstat()
        sidecar_metadata = sidecar_path.lstat()
        if (
            path.is_symlink()
            or sidecar_path.is_symlink()
            or not stat.S_ISREG(body_metadata.st_mode)
            or not stat.S_ISREG(sidecar_metadata.st_mode)
        ):
            raise ValueError
        source = path.read_bytes()
        artifact_sha256 = sha256_bytes(source)
        sidecar = sidecar_path.read_bytes()
    except (OSError, ValueError):
        raise GdeltNewsArchiveError("gdelt_archive_verification_failed") from None
    if (
        expected_sha256 is not None
        and artifact_sha256 != expected_sha256
        or sidecar != f"{artifact_sha256}\n".encode("ascii")
    ):
        raise GdeltNewsArchiveError("gdelt_archive_verification_failed")
    return source


def _valid_timeline_json(source: bytes) -> bool:
    try:
        value = json.loads(source)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    return (
        isinstance(value, dict)
        and isinstance(value.get("query_details"), dict)
        and isinstance(value.get("timeline"), list)
    )


def _canonical_object(source: bytes) -> dict[str, object]:
    try:
        value = json.loads(source)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise GdeltNewsArchiveError("gdelt_query_sources_invalid") from None
    if not isinstance(value, dict) or canonical_json_bytes(value) != source:
        raise GdeltNewsArchiveError("gdelt_query_sources_invalid")
    return value


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


def _parse_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        raise GdeltNewsArchiveError("gdelt_timestamp_invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise GdeltNewsArchiveError("gdelt_timestamp_invalid")
    return parsed


def _format_utc(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise GdeltNewsArchiveError("gdelt_timestamp_invalid")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
