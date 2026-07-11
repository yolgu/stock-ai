"""Deterministic metadata-only sample selection for RP-001."""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from enum import Enum
from types import MappingProxyType
from typing import cast

from rp001.sensitive_value_policy import find_sensitive_values


SCHEMA_ID: str = "rp001-metadata-sample-selection.v1"
PROGRAM_ID: str = "RP-001"
GOAL_VERSION: str = "1.2-COMPACT"
USAGE_SCOPE: str = "research_only"
OPERATIONAL_DISPOSITION: str = "no_trade_no_integration"

CANDIDATE_POOL: tuple[str, ...] = (
    "AAPL",
    "AMD",
    "AMZN",
    "AVGO",
    "CAT",
    "COST",
    "JPM",
    "KO",
    "META",
    "MSFT",
    "QCOM",
    "XOM",
)
DESIRED_SELECTION_COUNT: int = 6
_FROZEN_START_DATE: date = date(2023, 1, 3)
_FROZEN_END_DATE: date = date(2026, 6, 30)
_FROZEN_TIMEZONE: str = "America/New_York"
_FROZEN_INTERVAL: str = "1d"

SUPPORTED_MARKETS: frozenset[str] = frozenset(("NASDAQ", "NYSE", "AMEX"))
SUPPORTED_SECURITY_TYPES: frozenset[str] = frozenset(
    ("STOCK", "FOREIGN_STOCK")
)

_SHA256_PATTERN: re.Pattern[str] = re.compile(r"[0-9a-f]{64}")
_PROJECTION_FIELDS: tuple[str, ...] = (
    "symbol",
    "name",
    "englishName",
    "isinCode",
    "market",
    "securityType",
    "isCommonShare",
    "status",
    "currency",
    "sharesOutstanding",
)
_STRING_FIELDS: tuple[str, ...] = (
    "symbol",
    "name",
    "englishName",
    "isinCode",
    "market",
    "securityType",
    "status",
    "currency",
)
_FORBIDDEN_SELECTION_FIELD_TOKENS: tuple[str, ...] = (
    "price",
    "adjustedclose",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "turnover",
    "return",
    "label",
    "outcome",
    "performance",
    "candle",
    "ohlcv",
)


class SampleSelectionContractError(ValueError):
    """Raised when metadata-only sample selection cannot be completed safely."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class EligibilityReason(str, Enum):
    STATUS_NOT_ACTIVE = "status_not_active"
    NOT_COMMON_SHARE = "not_common_share"
    CURRENCY_NOT_USD = "currency_not_usd"
    MARKET_NOT_SUPPORTED = "market_not_supported"
    SECURITY_TYPE_NOT_SUPPORTED = "security_type_not_supported"


class DataRole(str, Enum):
    METADATA_ONLY = "metadata_only"
    UNSEEN_HISTORICAL_CONFIRMATION = "unseen_historical_confirmation"
    AUDIT_ONLY = "audit_only"


@dataclass(frozen=True)
class StockMetadata:
    symbol: str
    name: str
    english_name: str
    isin_code: str
    market: str
    security_type: str
    is_common_share: bool
    status: str
    currency: str
    shares_outstanding: str

    def to_canonical_body(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "englishName": self.english_name,
            "isinCode": self.isin_code,
            "market": self.market,
            "securityType": self.security_type,
            "isCommonShare": self.is_common_share,
            "status": self.status,
            "currency": self.currency,
            "sharesOutstanding": self.shares_outstanding,
        }


@dataclass(frozen=True)
class SelectionPeriod:
    start_date: date
    end_date: date
    inclusive: bool
    timezone: str
    interval: str

    def __post_init__(self) -> None:
        if (
            self.start_date != _FROZEN_START_DATE
            or self.end_date != _FROZEN_END_DATE
            or self.inclusive is not True
            or self.timezone != _FROZEN_TIMEZONE
            or self.interval != _FROZEN_INTERVAL
        ):
            raise ValueError("invalid_selection_period")

    def to_canonical_body(self) -> dict[str, object]:
        return {
            "startDate": self.start_date.isoformat(),
            "endDate": self.end_date.isoformat(),
            "inclusive": self.inclusive,
            "timezone": self.timezone,
            "interval": self.interval,
        }


@dataclass(frozen=True)
class SampleDataRoles:
    metadata_request: DataRole
    selected_candles: DataRole
    unselected_symbols: DataRole

    def __post_init__(self) -> None:
        if (
            self.metadata_request is not DataRole.METADATA_ONLY
            or self.selected_candles
            is not DataRole.UNSEEN_HISTORICAL_CONFIRMATION
            or self.unselected_symbols is not DataRole.AUDIT_ONLY
        ):
            raise ValueError("invalid_sample_data_roles")

    def to_canonical_body(self) -> dict[str, object]:
        return {
            "metadataRequest": self.metadata_request.value,
            "selectedCandles": self.selected_candles.value,
            "unselectedSymbols": self.unselected_symbols.value,
        }


@dataclass(frozen=True)
class RankingBinding:
    algorithm: str
    selection_basis_hash_input_template: str
    formula_source_sha256: str
    formula_artifact_sha256: str | None

    def to_canonical_body(self) -> dict[str, object]:
        return {
            "algorithm": self.algorithm,
            "selectionBasisHashInputTemplate": (
                self.selection_basis_hash_input_template
            ),
            "formulaSourceSha256": self.formula_source_sha256,
            "formulaArtifactSha256": self.formula_artifact_sha256,
        }


@dataclass(frozen=True)
class RankedPoolEntry:
    rank: int
    metadata: StockMetadata
    selection_basis_hash_input: str
    ranking_digest: str
    eligible: bool
    reasons: tuple[EligibilityReason, ...]

    def to_canonical_body(self) -> dict[str, object]:
        return {
            "rank": self.rank,
            "metadata": self.metadata.to_canonical_body(),
            "selectionBasisHashInput": self.selection_basis_hash_input,
            "rankingDigest": self.ranking_digest,
            "eligible": self.eligible,
            "reasons": [reason.value for reason in self.reasons],
        }


@dataclass(frozen=True)
class SampleSelectionResult:
    schema_id: str
    program_id: str
    goal_version: str
    usage_scope: str
    operational_disposition: str
    candidate_pool: tuple[str, ...]
    desired_selection_count: int
    period: SelectionPeriod
    data_roles: SampleDataRoles
    ranking_binding: RankingBinding
    ranked_pool: tuple[RankedPoolEntry, ...]
    selected_symbols: tuple[str, ...]

    def to_canonical_body(self) -> dict[str, object]:
        return {
            "schemaId": self.schema_id,
            "programId": self.program_id,
            "goalVersion": self.goal_version,
            "usageScope": self.usage_scope,
            "operationalDisposition": self.operational_disposition,
            "candidatePool": list(self.candidate_pool),
            "desiredSelectionCount": self.desired_selection_count,
            "period": self.period.to_canonical_body(),
            "dataRoles": self.data_roles.to_canonical_body(),
            "rankingBinding": self.ranking_binding.to_canonical_body(),
            "rankedPool": [entry.to_canonical_body() for entry in self.ranked_pool],
            "selectedSymbols": list(self.selected_symbols),
        }


FROZEN_PERIOD: SelectionPeriod = SelectionPeriod(
    start_date=_FROZEN_START_DATE,
    end_date=_FROZEN_END_DATE,
    inclusive=True,
    timezone=_FROZEN_TIMEZONE,
    interval=_FROZEN_INTERVAL,
)
FROZEN_DATA_ROLES: SampleDataRoles = SampleDataRoles(
    metadata_request=DataRole.METADATA_ONLY,
    selected_candles=DataRole.UNSEEN_HISTORICAL_CONFIRMATION,
    unselected_symbols=DataRole.AUDIT_ONLY,
)


def project_stock_metadata(payload: object) -> StockMetadata:
    """Project an external StockInfo object onto the frozen metadata boundary."""
    snapshot = _snapshot_metadata(payload)
    _reject_sensitive_metadata(snapshot)
    _reject_forbidden_selection_fields(snapshot)
    _require_projection_fields(snapshot)
    _validate_projection_field_types(snapshot)
    return StockMetadata(
        symbol=cast(str, snapshot["symbol"]),
        name=cast(str, snapshot["name"]),
        english_name=cast(str, snapshot["englishName"]),
        isin_code=cast(str, snapshot["isinCode"]),
        market=cast(str, snapshot["market"]),
        security_type=cast(str, snapshot["securityType"]),
        is_common_share=cast(bool, snapshot["isCommonShare"]),
        status=cast(str, snapshot["status"]),
        currency=cast(str, snapshot["currency"]),
        shares_outstanding=cast(str, snapshot["sharesOutstanding"]),
    )


def evaluate_eligibility(metadata: StockMetadata) -> tuple[EligibilityReason, ...]:
    """Evaluate the frozen eligibility rules in their declared order."""
    reasons: list[EligibilityReason] = []
    if metadata.status != "ACTIVE":
        reasons.append(EligibilityReason.STATUS_NOT_ACTIVE)
    if not metadata.is_common_share:
        reasons.append(EligibilityReason.NOT_COMMON_SHARE)
    if metadata.currency != "USD":
        reasons.append(EligibilityReason.CURRENCY_NOT_USD)
    if metadata.market not in SUPPORTED_MARKETS:
        reasons.append(EligibilityReason.MARKET_NOT_SUPPORTED)
    if metadata.security_type not in SUPPORTED_SECURITY_TYPES:
        reasons.append(EligibilityReason.SECURITY_TYPE_NOT_SUPPORTED)
    return tuple(reasons)


def select_metadata_sample(
    payloads: Iterable[object],
    *,
    formula_source_sha256: str,
    formula_artifact_sha256: str | None = None,
) -> SampleSelectionResult:
    """Select the frozen research sample using metadata and a source hash only."""
    _validate_sha256(
        formula_source_sha256,
        code="invalid_formula_source_sha256",
    )
    if formula_artifact_sha256 is not None:
        _validate_sha256(
            formula_artifact_sha256,
            code="invalid_formula_artifact_sha256",
        )

    projected = tuple(project_stock_metadata(payload) for payload in payloads)
    metadata_by_symbol = _require_exact_pool_coverage(projected)
    ranked_pool = _rank_pool(metadata_by_symbol, formula_source_sha256)
    eligible_entries = tuple(entry for entry in ranked_pool if entry.eligible)
    if len(eligible_entries) < DESIRED_SELECTION_COUNT:
        raise SampleSelectionContractError("too_few_eligible")

    return SampleSelectionResult(
        schema_id=SCHEMA_ID,
        program_id=PROGRAM_ID,
        goal_version=GOAL_VERSION,
        usage_scope=USAGE_SCOPE,
        operational_disposition=OPERATIONAL_DISPOSITION,
        candidate_pool=CANDIDATE_POOL,
        desired_selection_count=DESIRED_SELECTION_COUNT,
        period=FROZEN_PERIOD,
        data_roles=FROZEN_DATA_ROLES,
        ranking_binding=RankingBinding(
            algorithm="sha256_ascii_formula_source_sha256_colon_symbol",
            selection_basis_hash_input_template=(
                f"{formula_source_sha256}:{{symbol}}"
            ),
            formula_source_sha256=formula_source_sha256,
            formula_artifact_sha256=formula_artifact_sha256,
        ),
        ranked_pool=ranked_pool,
        selected_symbols=tuple(
            entry.metadata.symbol
            for entry in eligible_entries[:DESIRED_SELECTION_COUNT]
        ),
    )


def _snapshot_metadata(payload: object) -> Mapping[str, object]:
    if not isinstance(payload, Mapping):
        raise SampleSelectionContractError("invalid_metadata_item")
    try:
        snapshot = dict(payload)
    except Exception:
        raise SampleSelectionContractError("invalid_metadata_item") from None
    return MappingProxyType(snapshot)


def _rank_pool(
    metadata_by_symbol: Mapping[str, StockMetadata],
    formula_source_sha256: str,
) -> tuple[RankedPoolEntry, ...]:
    ranked_values: list[tuple[str, str, str, StockMetadata]] = []
    for symbol in CANDIDATE_POOL:
        hash_input = f"{formula_source_sha256}:{symbol}"
        digest = hashlib.sha256(hash_input.encode("ascii")).hexdigest()
        ranked_values.append((digest, symbol, hash_input, metadata_by_symbol[symbol]))
    ranked_values.sort(key=lambda value: (value[0], value[1]))

    entries: list[RankedPoolEntry] = []
    for rank, (digest, _symbol, hash_input, metadata) in enumerate(
        ranked_values,
        start=1,
    ):
        reasons = evaluate_eligibility(metadata)
        entries.append(
            RankedPoolEntry(
                rank=rank,
                metadata=metadata,
                selection_basis_hash_input=hash_input,
                ranking_digest=digest,
                eligible=not reasons,
                reasons=reasons,
            )
        )
    return tuple(entries)


def _require_exact_pool_coverage(
    metadata: tuple[StockMetadata, ...],
) -> dict[str, StockMetadata]:
    symbols = tuple(value.symbol for value in metadata)
    duplicates = tuple(
        sorted(symbol for symbol, count in Counter(symbols).items() if count > 1)
    )
    if duplicates:
        raise SampleSelectionContractError("duplicate_symbol")

    pool = frozenset(CANDIDATE_POOL)
    observed = frozenset(symbols)
    outside = tuple(sorted(observed - pool))
    if outside:
        raise SampleSelectionContractError("symbol_outside_pool")

    missing = tuple(sorted(pool - observed))
    if missing:
        raise SampleSelectionContractError("missing_pool_symbol")
    return {value.symbol: value for value in metadata}


def _reject_sensitive_metadata(payload: Mapping[str, object]) -> None:
    for field_name, value in payload.items():
        if isinstance(field_name, str) and find_sensitive_values(field_name):
            raise SampleSelectionContractError("sensitive_metadata")
        if not isinstance(value, str):
            continue
        if find_sensitive_values(value):
            raise SampleSelectionContractError("sensitive_metadata")
        if isinstance(field_name, str) and find_sensitive_values(
            f"{field_name}={value}"
        ):
            raise SampleSelectionContractError("sensitive_metadata")


def _reject_forbidden_selection_fields(payload: Mapping[str, object]) -> None:
    for field_name in payload:
        if not isinstance(field_name, str):
            raise SampleSelectionContractError("invalid_metadata_field")
        normalized = re.sub(r"[^a-z0-9]", "", field_name.lower())
        if any(
            token in normalized for token in _FORBIDDEN_SELECTION_FIELD_TOKENS
        ):
            raise SampleSelectionContractError("forbidden_selection_field")


def _require_projection_fields(payload: Mapping[str, object]) -> None:
    missing = tuple(field for field in _PROJECTION_FIELDS if field not in payload)
    if missing:
        raise SampleSelectionContractError("missing_metadata_field")


def _validate_projection_field_types(payload: Mapping[str, object]) -> None:
    for field_name in _STRING_FIELDS:
        value = payload[field_name]
        if not isinstance(value, str) or not value:
            raise SampleSelectionContractError("invalid_metadata_field")

    if not isinstance(payload["isCommonShare"], bool):
        raise SampleSelectionContractError("invalid_metadata_field")

    shares_outstanding = payload["sharesOutstanding"]
    if (
        not isinstance(shares_outstanding, str)
        or re.fullmatch(r"[0-9]{1,30}", shares_outstanding) is None
    ):
        raise SampleSelectionContractError("invalid_metadata_field")


def _validate_sha256(value: str, *, code: str) -> None:
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise SampleSelectionContractError(code)
