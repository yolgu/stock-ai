"""Deterministic whole-period Toss daily collection planning."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from rp001_s2.archive_contract import CollectionScope, SampleRole


_SCHEMA_VERSION = "rp001-s2-toss-daily-scope-plan.v1"
_IDENTITY_DOMAIN = "rp001_s2.toss_daily_scope_plan"
_ADJUSTMENT_MODES = ("native", "adjusted")


class DailyPlanExecutionState(str, Enum):
    ACTIVE = "active"
    DEFERRED_UNTIL_MINUTE_COLLECTION_TERMINAL = (
        "deferred_until_minute_collection_terminal"
    )


@dataclass(frozen=True)
class TossDailyScopePlan:
    instruments: tuple[tuple[str, str], ...]
    start_at: datetime
    end_at: datetime
    instrument_master_sha256: str
    sample_role: SampleRole
    execution_state: DailyPlanExecutionState
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
            "provider": "toss",
            "feed": "provider_all",
            "instrumentMasterSha256": self.instrument_master_sha256,
            "instruments": [
                {"instrumentId": instrument_id, "symbol": symbol}
                for instrument_id, symbol in self.instruments
            ],
            "startAt": _format_utc(self.start_at),
            "endAt": _format_utc(self.end_at),
            "adjustmentModes": list(_ADJUSTMENT_MODES),
            "scopeAcquisitionKeys": [
                scope.acquisition_key for scope in self.scopes
            ],
        }

    def to_canonical_body(self) -> dict[str, object]:
        return {
            **self.collection_identity_body(),
            "sampleRole": self.sample_role.value,
            "executionState": self.execution_state.value,
        }

    @property
    def collection_identity_sha256(self) -> str:
        return hashlib.sha256(
            _canonical_json_bytes(self.collection_identity_body())
        ).hexdigest()

    @property
    def presentation_sha256(self) -> str:
        return hashlib.sha256(canonical_daily_plan_bytes(self)).hexdigest()


def build_toss_daily_scope_plan(
    *,
    instruments: tuple[tuple[str, str], ...],
    start_at: datetime,
    end_at: datetime,
    instrument_master_sha256: str,
    sample_role: SampleRole,
    execution_state: DailyPlanExecutionState,
) -> TossDailyScopePlan:
    normalized = _validate_instruments(instruments)
    if (
        not _is_utc_midnight(start_at)
        or not _is_utc_midnight(end_at)
        or start_at >= end_at
        or not _is_sha256(instrument_master_sha256)
        or not isinstance(sample_role, SampleRole)
        or not isinstance(execution_state, DailyPlanExecutionState)
    ):
        raise ValueError("daily_scope_plan_invalid")
    scopes = tuple(
        CollectionScope(
            provider="toss",
            feed="provider_all",
            instrument_id=instrument_id,
            symbol=symbol,
            interval="1d",
            start_at=start_at,
            end_at=end_at,
            adjustment_mode=adjustment_mode,
            session_scope="provider_all",
            sample_role=sample_role,
        )
        for instrument_id, symbol in normalized
        for adjustment_mode in _ADJUSTMENT_MODES
    )
    return TossDailyScopePlan(
        instruments=normalized,
        start_at=start_at,
        end_at=end_at,
        instrument_master_sha256=instrument_master_sha256,
        sample_role=sample_role,
        execution_state=execution_state,
        scopes=scopes,
    )


def canonical_daily_plan_bytes(plan: TossDailyScopePlan) -> bytes:
    if not isinstance(plan, TossDailyScopePlan):
        raise ValueError("daily_scope_plan_invalid")
    return _canonical_json_bytes(plan.to_canonical_body())


def parse_daily_scope_plan(source: bytes) -> TossDailyScopePlan:
    try:
        value = json.loads(source.decode("utf-8"))
        if not isinstance(value, dict) or _canonical_json_bytes(value) != source:
            raise ValueError
        instruments_value = value["instruments"]
        if not isinstance(instruments_value, list):
            raise ValueError
        instruments = tuple(
            (entry["instrumentId"], entry["symbol"])
            for entry in instruments_value
            if isinstance(entry, dict)
            and set(entry) == {"instrumentId", "symbol"}
        )
        plan = build_toss_daily_scope_plan(
            instruments=instruments,
            start_at=_parse_utc(value["startAt"]),
            end_at=_parse_utc(value["endAt"]),
            instrument_master_sha256=value["instrumentMasterSha256"],
            sample_role=SampleRole(value["sampleRole"]),
            execution_state=DailyPlanExecutionState(value["executionState"]),
        )
    except (KeyError, TypeError, ValueError, UnicodeError):
        raise ValueError("daily_scope_plan_invalid") from None
    if plan.to_canonical_body() != value:
        raise ValueError("daily_scope_plan_invalid")
    return plan


def _validate_instruments(value: object) -> tuple[tuple[str, str], ...]:
    if type(value) is not tuple or not value:
        raise ValueError("daily_scope_plan_invalid")
    normalized: list[tuple[str, str]] = []
    for entry in value:
        if (
            type(entry) is not tuple
            or len(entry) != 2
            or any(
                type(identifier) is not str
                or not identifier
                or identifier != identifier.strip()
                for identifier in entry
            )
        ):
            raise ValueError("daily_scope_plan_invalid")
        normalized.append(entry)
    instrument_ids = tuple(entry[0] for entry in normalized)
    symbols = tuple(entry[1] for entry in normalized)
    if (
        len(instrument_ids) != len(set(instrument_ids))
        or len(symbols) != len(set(symbols))
    ):
        raise ValueError("daily_scope_plan_invalid")
    return tuple(sorted(normalized, key=lambda entry: (entry[1], entry[0])))


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


def _parse_utc(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError
    parsed = datetime.fromisoformat(
        value[:-1] + "+00:00" if value.endswith("Z") else value
    )
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError
    return parsed


def _is_utc_midnight(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() == timedelta(0)
        and value.hour == value.minute == value.second == value.microsecond == 0
    )


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
