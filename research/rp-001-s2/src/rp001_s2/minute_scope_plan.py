"""Deterministic exhaustive Toss minute-shard planning."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta

from rp001_s2.archive_contract import CollectionScope, SampleRole


_SCHEMA_VERSION = "rp001-s2-toss-minute-scope-plan.v1"
_IDENTITY_DOMAIN = "rp001_s2.toss_minute_scope_plan"
_SHARD_DURATION = timedelta(days=7)
_ADJUSTMENT_MODES = ("native", "adjusted")


@dataclass(frozen=True)
class TossMinuteScopePlan:
    instruments: tuple[tuple[str, str], ...]
    start_at: datetime
    end_at: datetime
    instrument_master_sha256: str
    sample_role: SampleRole
    adjustment_modes: tuple[str, ...]
    scopes: tuple[CollectionScope, ...]

    @property
    def instrument_count(self) -> int:
        return len(self.instruments)

    @property
    def scope_count(self) -> int:
        return len(self.scopes)

    def collection_identity_body(self) -> dict[str, object]:
        return {
            "schemaVersion": _SCHEMA_VERSION,
            "identityDomain": _IDENTITY_DOMAIN,
            "instrumentMasterSha256": self.instrument_master_sha256,
            "instruments": [
                {"instrumentId": instrument_id, "symbol": symbol}
                for instrument_id, symbol in self.instruments
            ],
            "startAt": _format_utc(self.start_at),
            "endAt": _format_utc(self.end_at),
            "adjustmentModes": list(self.adjustment_modes),
            "shardDurationDays": 7,
            "scopeAcquisitionKeys": [
                scope.acquisition_key for scope in self.scopes
            ],
        }

    def to_canonical_body(self) -> dict[str, object]:
        return {
            **self.collection_identity_body(),
            "sampleRole": self.sample_role.value,
        }

    @property
    def collection_identity_sha256(self) -> str:
        return hashlib.sha256(
            _canonical_json_bytes(self.collection_identity_body())
        ).hexdigest()

    @property
    def presentation_sha256(self) -> str:
        return hashlib.sha256(
            _canonical_json_bytes(self.to_canonical_body())
        ).hexdigest()


def build_toss_minute_scope_plan(
    *,
    instruments: tuple[tuple[str, str], ...],
    start_at: datetime,
    end_at: datetime,
    instrument_master_sha256: str,
    sample_role: SampleRole,
) -> TossMinuteScopePlan:
    """Cover the frozen interval exactly, newest shard first, for every identity."""
    normalized = _validate_instruments(instruments)
    if (
        not _is_utc(start_at)
        or not _is_utc(end_at)
        or start_at >= end_at
        or not _is_sha256(instrument_master_sha256)
        or not isinstance(sample_role, SampleRole)
    ):
        raise ValueError("minute_scope_plan_invalid")
    windows = _reverse_chronological_windows(start_at, end_at)
    scopes = tuple(
        CollectionScope(
            provider="toss",
            feed="provider_all",
            instrument_id=instrument_id,
            symbol=symbol,
            interval="1m",
            start_at=window_start,
            end_at=window_end,
            adjustment_mode=adjustment_mode,
            session_scope="provider_all",
            sample_role=sample_role,
        )
        for instrument_id, symbol in normalized
        for adjustment_mode in _ADJUSTMENT_MODES
        for window_start, window_end in windows
    )
    return TossMinuteScopePlan(
        instruments=normalized,
        start_at=start_at,
        end_at=end_at,
        instrument_master_sha256=instrument_master_sha256,
        sample_role=sample_role,
        adjustment_modes=_ADJUSTMENT_MODES,
        scopes=scopes,
    )


def _validate_instruments(
    instruments: object,
) -> tuple[tuple[str, str], ...]:
    if type(instruments) is not tuple or not instruments:
        raise ValueError("minute_scope_plan_invalid")
    normalized: list[tuple[str, str]] = []
    for value in instruments:
        if (
            type(value) is not tuple
            or len(value) != 2
            or any(
                type(identifier) is not str
                or not identifier
                or identifier != identifier.strip()
                for identifier in value
            )
        ):
            raise ValueError("minute_scope_plan_invalid")
        normalized.append(value)
    instrument_ids = tuple(value[0] for value in normalized)
    symbols = tuple(value[1] for value in normalized)
    if (
        len(instrument_ids) != len(set(instrument_ids))
        or len(symbols) != len(set(symbols))
    ):
        raise ValueError("minute_scope_plan_invalid")
    return tuple(sorted(normalized, key=lambda value: (value[1], value[0])))


def _reverse_chronological_windows(
    start_at: datetime,
    end_at: datetime,
) -> tuple[tuple[datetime, datetime], ...]:
    chronological: list[tuple[datetime, datetime]] = []
    cursor = start_at
    while cursor < end_at:
        shard_end = min(cursor + _SHARD_DURATION, end_at)
        chronological.append((cursor, shard_end))
        cursor = shard_end
    return tuple(reversed(chronological))


def _canonical_json_bytes(value: dict[str, object]) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _format_utc(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def _is_utc(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() == timedelta(0)
    )


def _is_sha256(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
