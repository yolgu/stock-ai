"""Metadata-only universe isolation for RP-001-S2 cycle 001."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass


SEED_TEXT: str = "RP-001-S2|CYCLE-001|metadata-only-split|v1"
SEED_SHA256: str = hashlib.sha256(SEED_TEXT.encode("ascii")).hexdigest()
EXPOSED_SYMBOLS: tuple[str, ...] = (
    "000660",
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
    "MU",
    "NVDA",
    "QCOM",
    "TSLA",
    "XOM",
)
EXPOSURE_EVIDENCE: tuple[tuple[str, str], ...] = (
    (
        "research/meta-research/objects/programs/"
        "RP-001-quantitative-market-behavior/seen-data-register.json",
        "a68b770245251795651a203e202cdfc46ce40802bdbf9d277ee2cffa21c7ad9a",
    ),
    (
        "research/rp-001/runs/RP001-META-20260711-001/metadata-exposure.json",
        "e6ee3ccf65f2f7aec97bbd03f4eaf3b04f39940d303738306d93a4dfdd34bd8b",
    ),
    (
        "research/rp-001/candle-runs/RP001-CANDLE-20260711-001/candle-scope.json",
        "72292c6986075dc3ae94bfacc1c705476cd7474b31e1533e1eff991941c80f95",
    ),
)
CANDIDATE_POOL: tuple[str, ...] = (
    "BA",
    "CVX",
    "DIS",
    "GE",
    "GS",
    "HD",
    "IBM",
    "JNJ",
    "LOW",
    "MCD",
    "MRK",
    "NFLX",
    "NKE",
    "ORCL",
    "PEP",
    "SBUX",
    "UPS",
    "WMT",
)
DEVELOPMENT_SYMBOL_COUNT: int = 6
CONFIRMATION_SYMBOL_COUNT: int = 6

_REQUIRED_FIELDS = frozenset(
    {
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
    }
)
_FORBIDDEN_FIELD_TOKENS = (
    "price",
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
_SUPPORTED_MARKETS = frozenset({"NASDAQ", "NYSE", "AMEX"})
_SUPPORTED_SECURITY_TYPES = frozenset({"STOCK", "FOREIGN_STOCK"})


class SampleDesignError(ValueError):
    """Raised when the metadata-only sample contract cannot be satisfied."""


@dataclass(frozen=True)
class RankedMetadata:
    rank: int
    symbol: str
    ranking_digest: str
    eligible: bool
    reasons: tuple[str, ...]
    metadata: tuple[tuple[str, object], ...]


@dataclass(frozen=True)
class SampleSelection:
    seed_text: str
    seed_sha256: str
    ranked_pool: tuple[RankedMetadata, ...]
    development_symbols: tuple[str, ...]
    confirmation_symbols: tuple[str, ...]

    def to_canonical_body(self) -> dict[str, object]:
        return {
            "seedText": self.seed_text,
            "seedSha256": self.seed_sha256,
            "rankingAlgorithm": "sha256(seed_sha256 + ':' + symbol), then symbol",
            "candidatePool": list(CANDIDATE_POOL),
            "permanentlyExcludedSymbols": list(EXPOSED_SYMBOLS),
            "rankedPool": [
                {
                    "rank": entry.rank,
                    "symbol": entry.symbol,
                    "rankingDigest": entry.ranking_digest,
                    "eligible": entry.eligible,
                    "reasons": list(entry.reasons),
                    "metadata": dict(entry.metadata),
                }
                for entry in self.ranked_pool
            ],
            "developmentSymbols": list(self.development_symbols),
            "confirmationSymbols": list(self.confirmation_symbols),
            "period": {
                "startDate": "2023-01-03",
                "endDate": "2026-06-30",
                "inclusive": True,
                "interval": "1d",
                "timezone": "America/New_York",
            },
            "selectionInferenceScope": (
                "survivorship_conditional_on_metadata_observed_2026-07-11"
            ),
            "exposureEvidence": [
                {"path": path, "sha256": sha256}
                for path, sha256 in EXPOSURE_EVIDENCE
            ],
            "priceOpenOrder": "development_first_confirmation_after_formula_freeze",
            "replacementAfterPriceOpen": "forbidden",
        }


def select_samples(payloads: Iterable[Mapping[str, object]]) -> SampleSelection:
    """Rank eligible metadata without reading price, volume, or performance."""
    projected: dict[str, tuple[tuple[str, object], ...]] = {}
    reasons_by_symbol: dict[str, tuple[str, ...]] = {}
    instrument_ids: set[str] = set()
    for payload in payloads:
        _reject_forbidden_fields(payload)
        if frozenset(payload) != _REQUIRED_FIELDS:
            if not _REQUIRED_FIELDS.issubset(payload):
                raise SampleDesignError("required_metadata_field_missing")
            raise SampleDesignError("unregistered_metadata_field")
        if not _REQUIRED_FIELDS.issubset(payload):
            raise SampleDesignError("required_metadata_field_missing")
        symbol = payload.get("symbol")
        if not isinstance(symbol, str) or symbol not in CANDIDATE_POOL:
            raise SampleDesignError("candidate_pool_mismatch")
        if symbol in projected:
            raise SampleDesignError("duplicate_candidate_metadata")
        projection = tuple(
            (field, payload[field]) for field in sorted(_REQUIRED_FIELDS)
        )
        _validate_projection(projection)
        instrument_id = str(payload["isinCode"])
        if instrument_id in instrument_ids:
            raise SampleDesignError("duplicate_instrument_identity")
        instrument_ids.add(instrument_id)
        projected[symbol] = projection
        reasons_by_symbol[symbol] = _eligibility_reasons(dict(projection))
    if set(projected) != set(CANDIDATE_POOL):
        raise SampleDesignError("candidate_pool_mismatch")

    ranked_symbols = sorted(
        CANDIDATE_POOL,
        key=lambda symbol: (_ranking_digest(symbol), symbol),
    )
    ranked = tuple(
        RankedMetadata(
            rank=index + 1,
            symbol=symbol,
            ranking_digest=_ranking_digest(symbol),
            eligible=not reasons_by_symbol[symbol],
            reasons=reasons_by_symbol[symbol],
            metadata=projected[symbol],
        )
        for index, symbol in enumerate(ranked_symbols)
    )
    eligible = tuple(entry.symbol for entry in ranked if entry.eligible)
    required = DEVELOPMENT_SYMBOL_COUNT + CONFIRMATION_SYMBOL_COUNT
    if len(eligible) < required:
        raise SampleDesignError("insufficient_eligible_metadata")
    development = eligible[:DEVELOPMENT_SYMBOL_COUNT]
    confirmation = eligible[
        DEVELOPMENT_SYMBOL_COUNT : DEVELOPMENT_SYMBOL_COUNT
        + CONFIRMATION_SYMBOL_COUNT
    ]
    return SampleSelection(
        seed_text=SEED_TEXT,
        seed_sha256=SEED_SHA256,
        ranked_pool=ranked,
        development_symbols=development,
        confirmation_symbols=confirmation,
    )


def _reject_forbidden_fields(payload: Mapping[str, object]) -> None:
    for field in payload:
        normalized = field.lower().replace("_", "")
        if any(token in normalized for token in _FORBIDDEN_FIELD_TOKENS):
            raise SampleDesignError("forbidden_metadata_field")


def _validate_projection(projection: tuple[tuple[str, object], ...]) -> None:
    value = dict(projection)
    for field in _REQUIRED_FIELDS - {"isCommonShare"}:
        if not isinstance(value[field], str) or not str(value[field]).strip():
            raise SampleDesignError("metadata_field_type_invalid")
    if not isinstance(value["isCommonShare"], bool):
        raise SampleDesignError("metadata_field_type_invalid")
    isin = str(value["isinCode"])
    if (
        len(isin) != 12
        or not isin.isascii()
        or not isin.isalnum()
        or not isin[:2].isalpha()
        or isin != isin.upper()
    ):
        raise SampleDesignError("instrument_identity_invalid")
    shares = str(value["sharesOutstanding"])
    if not shares.isascii() or not shares.isdigit() or not 1 <= len(shares) <= 30:
        raise SampleDesignError("shares_outstanding_invalid")


def _eligibility_reasons(value: Mapping[str, object]) -> tuple[str, ...]:
    reasons: list[str] = []
    if value["status"] != "ACTIVE":
        reasons.append("status_not_active")
    if value["isCommonShare"] is not True:
        reasons.append("not_common_share")
    if value["currency"] != "USD":
        reasons.append("currency_not_usd")
    if value["market"] not in _SUPPORTED_MARKETS:
        reasons.append("market_not_supported")
    if value["securityType"] not in _SUPPORTED_SECURITY_TYPES:
        reasons.append("security_type_not_supported")
    return tuple(reasons)


def _ranking_digest(symbol: str) -> str:
    return hashlib.sha256(f"{SEED_SHA256}:{symbol}".encode("ascii")).hexdigest()
