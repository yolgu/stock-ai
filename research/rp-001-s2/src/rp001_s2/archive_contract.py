"""Direction-neutral archive acquisition and research-view contracts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Literal


PRIORITY_SYMBOLS: tuple[str, ...] = (
    "000660",
    "AAPL",
    "AMD",
    "AMZN",
    "AVGO",
    "BA",
    "CAT",
    "COST",
    "CVX",
    "DIS",
    "GE",
    "GS",
    "HD",
    "IBM",
    "JNJ",
    "JPM",
    "KO",
    "LOW",
    "MCD",
    "META",
    "MRK",
    "MSFT",
    "MU",
    "NFLX",
    "NKE",
    "NVDA",
    "ORCL",
    "PEP",
    "QCOM",
    "SBUX",
    "TSLA",
    "UPS",
    "WMT",
    "XOM",
)
BENCHMARK_SYMBOLS: tuple[str, ...] = (
    "SPY",
    "QQQ",
    "IWM",
    "XLC",
    "XLE",
    "XLF",
    "XLI",
    "XLK",
    "XLP",
    "XLRE",
    "XLU",
    "XLV",
    "XLY",
    "SOXX",
)

_INSTRUMENT_MASTER_SCHEMA_VERSION: str = (
    "rp001-s2-direction-neutral-instrument-master.v1"
)
_ALLOWED_INTERVALS: frozenset[str] = frozenset({"1m", "1d"})


class InstrumentRole(str, Enum):
    PRIORITY = "priority"
    BENCHMARK = "benchmark"


class SampleRole(str, Enum):
    SEEN = "seen"
    UNSEEN = "unseen"
    CONFIRMATION = "confirmation"


class FormulaState(str, Enum):
    DISCOVERY = "discovery"
    FORMULA_FROZEN = "formula_frozen"


class ResearchDataKind(str, Enum):
    RAW_ARCHIVE_METADATA = "raw_archive_metadata"
    RAW_ARCHIVE_HASH = "raw_archive_hash"
    RAW_ARCHIVE_ROW_COUNT = "raw_archive_row_count"
    BAR_VALUES = "bar_values"
    FEATURES = "features"
    LABELS = "labels"


_RAW_ARCHIVE_KINDS: frozenset[ResearchDataKind] = frozenset(
    {
        ResearchDataKind.RAW_ARCHIVE_METADATA,
        ResearchDataKind.RAW_ARCHIVE_HASH,
        ResearchDataKind.RAW_ARCHIVE_ROW_COUNT,
    }
)


@dataclass(frozen=True)
class CollectionScope:
    provider: str
    feed: str
    instrument_id: str
    symbol: str
    interval: Literal["1m", "1d"]
    start_at: datetime
    end_at: datetime
    adjustment_mode: str
    session_scope: str
    sample_role: SampleRole

    def __post_init__(self) -> None:
        identifiers = (
            self.provider,
            self.feed,
            self.instrument_id,
            self.symbol,
            self.adjustment_mode,
            self.session_scope,
        )
        if any(type(value) is not str or not value.strip() for value in identifiers):
            raise ValueError("collection_scope_identifier_invalid")
        if type(self.interval) is not str or self.interval not in _ALLOWED_INTERVALS:
            raise ValueError("collection_scope_interval_invalid")
        if not isinstance(self.sample_role, SampleRole):
            raise ValueError("collection_scope_sample_role_invalid")
        if not _is_utc_aware(self.start_at) or not _is_utc_aware(self.end_at):
            raise ValueError("collection_scope_timestamp_must_be_utc")
        if self.start_at >= self.end_at:
            raise ValueError("collection_scope_window_invalid")

    def acquisition_identity_body(self) -> dict[str, str]:
        return {
            "provider": self.provider,
            "feed": self.feed,
            "instrumentId": self.instrument_id,
            "symbol": self.symbol,
            "interval": self.interval,
            "startAt": _format_utc(self.start_at),
            "endAt": _format_utc(self.end_at),
            "adjustmentMode": self.adjustment_mode,
            "sessionScope": self.session_scope,
        }

    def canonical_acquisition_json_bytes(self) -> bytes:
        return _canonical_json_bytes(self.acquisition_identity_body())

    @property
    def acquisition_digest(self) -> str:
        return hashlib.sha256(self.canonical_acquisition_json_bytes()).hexdigest()

    @property
    def acquisition_key(self) -> str:
        return self.acquisition_digest

    def to_canonical_body(self) -> dict[str, str]:
        return {
            **self.acquisition_identity_body(),
            "sampleRole": self.sample_role.value,
        }


@dataclass(frozen=True)
class ResearchViewAccess:
    sample_role: SampleRole
    formula_state: FormulaState

    def __post_init__(self) -> None:
        if not isinstance(self.sample_role, SampleRole):
            raise ValueError("research_view_sample_role_invalid")
        if not isinstance(self.formula_state, FormulaState):
            raise ValueError("research_view_formula_state_invalid")

    def can_read(self, data_kind: ResearchDataKind) -> bool:
        if not isinstance(data_kind, ResearchDataKind):
            raise ValueError("research_view_data_kind_invalid")
        if data_kind in _RAW_ARCHIVE_KINDS:
            return True
        return (
            self.sample_role is not SampleRole.CONFIRMATION
            or self.formula_state is FormulaState.FORMULA_FROZEN
        )

    def require_read(self, data_kind: ResearchDataKind) -> None:
        if not self.can_read(data_kind):
            raise PermissionError("confirmation_research_view_sealed")


@dataclass(frozen=True)
class InstrumentMasterEntry:
    instrument_id: str
    symbol: str
    role: InstrumentRole


@dataclass(frozen=True)
class InstrumentMaster:
    entries: tuple[InstrumentMasterEntry, ...]

    def __post_init__(self) -> None:
        instrument_ids = tuple(entry.instrument_id for entry in self.entries)
        symbols = tuple(entry.symbol for entry in self.entries)
        if len(set(instrument_ids)) != len(instrument_ids):
            raise ValueError("duplicate_instrument_identity")
        if len(set(symbols)) != len(symbols):
            raise ValueError("duplicate_instrument_identity")

    def to_canonical_body(self) -> dict[str, object]:
        return {
            "schemaVersion": _INSTRUMENT_MASTER_SCHEMA_VERSION,
            "instruments": [
                {
                    "instrumentId": entry.instrument_id,
                    "symbol": entry.symbol,
                    "role": entry.role.value,
                }
                for entry in self.entries
            ],
        }

    def canonical_json_bytes(self) -> bytes:
        return _canonical_json_bytes(self.to_canonical_body())

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json_bytes()).hexdigest()


def build_instrument_master() -> InstrumentMaster:
    """Build the deterministic priority-plus-benchmark archive universe."""
    return InstrumentMaster(
        entries=tuple(
            InstrumentMasterEntry(
                instrument_id=symbol,
                symbol=symbol,
                role=InstrumentRole.PRIORITY,
            )
            for symbol in PRIORITY_SYMBOLS
        )
        + tuple(
            InstrumentMasterEntry(
                instrument_id=symbol,
                symbol=symbol,
                role=InstrumentRole.BENCHMARK,
            )
            for symbol in BENCHMARK_SYMBOLS
        )
    )


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _is_utc_aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() == timedelta(0)
    )


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
