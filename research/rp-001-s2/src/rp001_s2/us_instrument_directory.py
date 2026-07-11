"""Official Nasdaq Trader directory boundary and eligible US universe parser."""

from __future__ import annotations

import base64
import hashlib
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from urllib.parse import urlsplit
from urllib.request import Request, build_opener

from rp001.toss_research_collector import HttpRequest, HttpResponse, RawHttpCapture
from rp001_s2.toss_boundary import (
    ReadOnlyBoundaryError,
    _Opener,
    _RejectRedirectHandler,
    _open_http_response,
)


_NASDAQ_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
_OTHER_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
_ALLOWED_URLS = frozenset({_NASDAQ_URL, _OTHER_URL})
_RESPONSE_LIMIT_BYTES = 16 * 1024 * 1024
_NASDAQ_HEADER = (
    "Symbol",
    "Security Name",
    "Market Category",
    "Test Issue",
    "Financial Status",
    "Round Lot Size",
    "ETF",
    "NextShares",
)
_OTHER_HEADER = (
    "ACT Symbol",
    "Security Name",
    "Exchange",
    "CQS Symbol",
    "ETF",
    "Round Lot Size",
    "Test Issue",
    "NASDAQ Symbol",
)
_COMMON_EQUITY_MARKERS_V1 = (
    "common stock",
    "common shares",
    "ordinary share",
)
_COMMON_EQUITY_MARKERS_V2 = (
    "common stock",
    "common share",
    "ordinary share",
)
_NON_COMMON_PATTERN_V1 = re.compile(
    r"\b(?:warrants?|rights?|units?|preferred|depositary shares?|"
    r"depository shares?|notes?|bonds?|debentures?)\b",
    re.IGNORECASE,
)
_NON_COMMON_PATTERN_V2 = re.compile(
    r"\b(?:warrants?|rights?|units?|depositary shares?|"
    r"depository shares?|adrs?)\b",
    re.IGNORECASE,
)
_SYMBOL_PATTERN = re.compile(r"^[A-Z][A-Z0-9.-]{0,13}$")


class DirectoryContractVersion(str, Enum):
    V1 = "v1"
    V2 = "v2"

    @property
    def parser_version(self) -> str:
        return f"rp001-s2-us-instrument-directory-parser.{self.value}"

    @property
    def classifier_version(self) -> str:
        return f"rp001-s2-us-instrument-classifier.{self.value}"


class InstrumentEligibility(str, Enum):
    COMMON_STOCK = "common_stock"
    ETF = "etf_asset_class_unresolved"
    EXCLUDED_TEST_ISSUE = "excluded_test_issue"
    EXCLUDED_NON_COMMON = "excluded_non_common"
    EXCLUDED_PROVIDER_SYMBOL = "excluded_provider_symbol"


class InstrumentDirectoryCollectionError(ValueError):
    """Collection failure retaining every safe official-file response."""

    def __init__(
        self,
        code: str,
        captures: tuple[RawHttpCapture, ...] = (),
    ) -> None:
        self.code = code
        self.captures = captures
        super().__init__(code)


@dataclass(frozen=True)
class DirectoryInstrument:
    symbol: str
    provider_symbol: str
    security_name: str
    listing_market: str
    source_directory: str
    is_etf: bool
    is_test_issue: bool
    eligibility: InstrumentEligibility


@dataclass(frozen=True)
class UsInstrumentDirectory:
    records: tuple[DirectoryInstrument, ...]
    eligible_symbols: tuple[str, ...]
    nasdaq_file_created_at: str
    other_file_created_at: str
    etf_asset_class_status: str = "not_identifiable_from_directory"


@dataclass(frozen=True)
class CollectedUsInstrumentDirectory:
    directory: UsInstrumentDirectory
    captures: tuple[RawHttpCapture, ...]


class StrictNasdaqDirectoryTransport:
    """Allow only the two public Nasdaq Trader symbol-directory reads."""

    def __init__(self, *, opener: _Opener) -> None:
        self._opener = opener

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if not _is_allowed_request(request):
            raise ReadOnlyBoundaryError("endpoint_not_allowed")
        outgoing = Request(request.url, headers=dict(request.headers), method="GET")
        return _open_http_response(
            self._opener,
            outgoing,
            _RESPONSE_LIMIT_BYTES,
            "instrument_directory_transport_error",
        )


def build_live_nasdaq_directory_transport() -> StrictNasdaqDirectoryTransport:
    """Build the public directory transport with redirects rejected."""
    return StrictNasdaqDirectoryTransport(
        opener=build_opener(_RejectRedirectHandler()),
    )


def collect_us_instrument_directory(
    *,
    transport: StrictNasdaqDirectoryTransport,
    clock: Callable[[], datetime],
) -> CollectedUsInstrumentDirectory:
    """Capture both official files before parsing the eligible universe."""
    captures: list[RawHttpCapture] = []
    bodies: list[bytes] = []
    for endpoint_id, url in (
        ("nasdaq_listed_symbol_directory", _NASDAQ_URL),
        ("other_listed_symbol_directory", _OTHER_URL),
    ):
        try:
            response = transport(
                HttpRequest(method="GET", url=url, headers={"Accept": "text/plain"})
            )
            capture = _capture(endpoint_id, url, response, clock)
        except ReadOnlyBoundaryError as error:
            raise InstrumentDirectoryCollectionError(
                error.code,
                tuple(captures),
            ) from None
        except ValueError as error:
            raise InstrumentDirectoryCollectionError(
                str(error),
                tuple(captures),
            ) from None
        captures.append(capture)
        bodies.append(response.body)
        if not 200 <= response.status < 300:
            raise InstrumentDirectoryCollectionError(
                "instrument_directory_http_status",
                tuple(captures),
            )
        content_type = _content_type(response)
        if content_type != "text/plain":
            raise InstrumentDirectoryCollectionError(
                "instrument_directory_content_type_invalid",
                tuple(captures),
            )
    try:
        directory = parse_us_instrument_directory(bodies[0], bodies[1])
    except ValueError:
        raise InstrumentDirectoryCollectionError(
            "instrument_directory_invalid",
            tuple(captures),
        ) from None
    return CollectedUsInstrumentDirectory(
        directory=directory,
        captures=tuple(captures),
    )


def parse_us_instrument_directory(
    nasdaq_body: bytes,
    other_body: bytes,
    *,
    contract_version: DirectoryContractVersion = DirectoryContractVersion.V2,
) -> UsInstrumentDirectory:
    """Parse every official row, then derive a direction-agnostic collection set."""
    if not isinstance(contract_version, DirectoryContractVersion):
        raise ValueError("instrument_directory_contract_invalid")
    nasdaq_rows, nasdaq_created = _rows(
        nasdaq_body,
        _NASDAQ_HEADER,
        footer_field_count=8,
    )
    other_rows, other_created = _rows(
        other_body,
        _OTHER_HEADER,
        footer_field_count=7,
    )
    records = tuple(
        _nasdaq_record(row, contract_version) for row in nasdaq_rows
    ) + tuple(
        _other_record(row, contract_version) for row in other_rows
    )
    symbols = tuple(record.symbol for record in records)
    if len(symbols) != len(set(symbols)):
        raise ValueError("instrument_directory_invalid")
    ordered_records = tuple(sorted(records, key=lambda record: record.symbol))
    eligible = tuple(
        record.symbol
        for record in ordered_records
        if record.eligibility
        in {InstrumentEligibility.COMMON_STOCK, InstrumentEligibility.ETF}
    )
    return UsInstrumentDirectory(
        records=ordered_records,
        eligible_symbols=eligible,
        nasdaq_file_created_at=nasdaq_created,
        other_file_created_at=other_created,
    )


def _rows(
    body: bytes,
    expected_header: tuple[str, ...],
    *,
    footer_field_count: int,
) -> tuple[tuple[tuple[str, ...], ...], str]:
    try:
        text = body.decode("utf-8")
    except (AttributeError, UnicodeDecodeError):
        raise ValueError("instrument_directory_invalid") from None
    lines = text.splitlines()
    if len(lines) < 2 or tuple(lines[0].split("|")) != expected_header:
        raise ValueError("instrument_directory_invalid")
    footer = tuple(lines[-1].split("|"))
    prefix = "File Creation Time: "
    if (
        len(footer) != footer_field_count
        or not footer[0].startswith(prefix)
        or not footer[0][len(prefix) :]
        or any(footer[1:])
    ):
        raise ValueError("instrument_directory_invalid")
    parsed_rows: list[tuple[str, ...]] = []
    for line in lines[1:-1]:
        row = tuple(line.split("|"))
        if len(row) != len(expected_header) or any(not value for value in row):
            raise ValueError("instrument_directory_invalid")
        parsed_rows.append(row)
    return tuple(parsed_rows), footer[0][len(prefix) :]


def _nasdaq_record(
    row: tuple[str, ...],
    contract_version: DirectoryContractVersion,
) -> DirectoryInstrument:
    return _record(
        symbol=row[0],
        provider_symbol=row[0],
        security_name=row[1],
        listing_market=f"NASDAQ:{row[2]}",
        source_directory="nasdaqlisted",
        etf=row[6],
        test_issue=row[3],
        contract_version=contract_version,
    )


def _other_record(
    row: tuple[str, ...],
    contract_version: DirectoryContractVersion,
) -> DirectoryInstrument:
    return _record(
        symbol=row[0],
        provider_symbol=row[7],
        security_name=row[1],
        listing_market=row[2],
        source_directory="otherlisted",
        etf=row[4],
        test_issue=row[6],
        contract_version=contract_version,
    )


def _record(
    *,
    symbol: str,
    provider_symbol: str,
    security_name: str,
    listing_market: str,
    source_directory: str,
    etf: str,
    test_issue: str,
    contract_version: DirectoryContractVersion,
) -> DirectoryInstrument:
    if (
        not _safe_identifier(symbol)
        or not _safe_identifier(provider_symbol)
        or not _safe_text(security_name)
        or not _safe_text(listing_market)
        or etf not in {"Y", "N"}
        or test_issue not in {"Y", "N"}
    ):
        raise ValueError("instrument_directory_invalid")
    is_etf = etf == "Y"
    is_test = test_issue == "Y"
    eligibility = _eligibility(
        symbol,
        provider_symbol,
        security_name,
        is_etf,
        is_test,
        contract_version,
    )
    return DirectoryInstrument(
        symbol=symbol,
        provider_symbol=provider_symbol,
        security_name=security_name,
        listing_market=listing_market,
        source_directory=source_directory,
        is_etf=is_etf,
        is_test_issue=is_test,
        eligibility=eligibility,
    )


def _eligibility(
    symbol: str,
    provider_symbol: str,
    security_name: str,
    is_etf: bool,
    is_test: bool,
    contract_version: DirectoryContractVersion,
) -> InstrumentEligibility:
    if is_test:
        return InstrumentEligibility.EXCLUDED_TEST_ISSUE
    if (
        _SYMBOL_PATTERN.fullmatch(symbol) is None
        or _SYMBOL_PATTERN.fullmatch(provider_symbol) is None
    ):
        return InstrumentEligibility.EXCLUDED_PROVIDER_SYMBOL
    if is_etf:
        return InstrumentEligibility.ETF
    normalized = security_name.casefold()
    non_common_pattern = (
        _NON_COMMON_PATTERN_V1
        if contract_version is DirectoryContractVersion.V1
        else _NON_COMMON_PATTERN_V2
    )
    common_markers = (
        _COMMON_EQUITY_MARKERS_V1
        if contract_version is DirectoryContractVersion.V1
        else _COMMON_EQUITY_MARKERS_V2
    )
    if non_common_pattern.search(normalized) is not None:
        return InstrumentEligibility.EXCLUDED_NON_COMMON
    if any(marker in normalized for marker in common_markers):
        return InstrumentEligibility.COMMON_STOCK
    return InstrumentEligibility.EXCLUDED_NON_COMMON


def _is_allowed_request(request: object) -> bool:
    if not isinstance(request, HttpRequest) or request.method != "GET":
        return False
    try:
        parsed = urlsplit(request.url)
    except (TypeError, ValueError):
        return False
    return (
        request.url in _ALLOWED_URLS
        and parsed.scheme == "https"
        and parsed.netloc == "www.nasdaqtrader.com"
        and not parsed.query
        and not parsed.fragment
        and parsed.username is None
        and parsed.password is None
        and dict(request.headers) == {"Accept": "text/plain"}
    )


def _content_type(response: HttpResponse) -> str:
    values = {
        name.lower(): value for name, value in response.headers.items()
    }
    value = values.get("content-type", "")
    return value.split(";", 1)[0].strip().lower()


def _capture(
    endpoint_id: str,
    url: str,
    response: HttpResponse,
    clock: Callable[[], datetime],
) -> RawHttpCapture:
    try:
        received = clock()
        if not isinstance(received, datetime) or received.tzinfo is None:
            raise ValueError
        received_at = received.astimezone(timezone.utc).isoformat(
            timespec="seconds"
        ).replace("+00:00", "Z")
    except Exception:
        raise ValueError("instrument_directory_clock_invalid") from None
    return RawHttpCapture(
        endpoint_id=endpoint_id,
        method="GET",
        sanitized_url=url,
        query=(),
        status=response.status,
        headers=(("content-type", _content_type(response)),),
        received_at=received_at,
        body_base64=base64.b64encode(response.body).decode("ascii"),
        body_sha256=hashlib.sha256(response.body).hexdigest(),
    )


def _safe_text(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and not any(unicodedata.category(character) in {"Cc", "Cf"} for character in value)
    )


def _safe_identifier(value: object) -> bool:
    return (
        isinstance(value, str)
        and 1 <= len(value) <= 32
        and value == value.strip()
        and "|" not in value
        and all("!" <= character <= "~" for character in value)
    )
