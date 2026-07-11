from __future__ import annotations

import hashlib
import json
import unittest
from dataclasses import fields
from datetime import datetime, timedelta, timezone

from rp001_s2.archive_contract import (
    BENCHMARK_SYMBOLS,
    PRIORITY_SYMBOLS,
    CollectionScope,
    FormulaState,
    InstrumentMaster,
    InstrumentMasterEntry,
    InstrumentRole,
    ResearchDataKind,
    ResearchViewAccess,
    SampleRole,
    build_instrument_master,
)


_EXPECTED_PRIORITY_SYMBOLS: tuple[str, ...] = (
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
_EXPECTED_BENCHMARK_SYMBOLS: tuple[str, ...] = (
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


def _scope(**overrides: object) -> CollectionScope:
    values: dict[str, object] = {
        "provider": "toss",
        "feed": "historical_candles",
        "instrument_id": "AAPL",
        "symbol": "AAPL",
        "interval": "1m",
        "start_at": datetime(2023, 1, 3, tzinfo=timezone.utc),
        "end_at": datetime(2026, 7, 1, tzinfo=timezone.utc),
        "adjustment_mode": "provider_native",
        "session_scope": "provider_all",
        "sample_role": SampleRole.SEEN,
    }
    values.update(overrides)
    return CollectionScope(**values)


class DirectionNeutralInstrumentMasterTest(unittest.TestCase):
    def test_exact_universes_build_one_deterministic_canonical_master(self) -> None:
        first = build_instrument_master()
        second = build_instrument_master()

        self.assertEqual(PRIORITY_SYMBOLS, _EXPECTED_PRIORITY_SYMBOLS)
        self.assertEqual(BENCHMARK_SYMBOLS, _EXPECTED_BENCHMARK_SYMBOLS)
        self.assertEqual(first, second)
        self.assertEqual(
            tuple(entry.symbol for entry in first.entries),
            _EXPECTED_PRIORITY_SYMBOLS + _EXPECTED_BENCHMARK_SYMBOLS,
        )
        self.assertEqual(
            tuple(entry.instrument_id for entry in first.entries),
            _EXPECTED_PRIORITY_SYMBOLS + _EXPECTED_BENCHMARK_SYMBOLS,
        )
        self.assertEqual(
            tuple(entry.role for entry in first.entries),
            (InstrumentRole.PRIORITY,) * len(_EXPECTED_PRIORITY_SYMBOLS)
            + (InstrumentRole.BENCHMARK,) * len(_EXPECTED_BENCHMARK_SYMBOLS),
        )
        self.assertEqual(
            len({entry.instrument_id for entry in first.entries}),
            len(first.entries),
        )
        self.assertEqual(
            len({entry.symbol for entry in first.entries}),
            len(first.entries),
        )

        expected_source = json.dumps(
            first.to_canonical_body(),
            allow_nan=False,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        self.assertEqual(first.canonical_json_bytes(), expected_source)
        self.assertEqual(first.sha256, hashlib.sha256(expected_source).hexdigest())

    def test_instrument_master_rejects_duplicate_identity(self) -> None:
        entry = InstrumentMasterEntry(
            instrument_id="AAPL",
            symbol="AAPL",
            role=InstrumentRole.PRIORITY,
        )

        with self.assertRaisesRegex(ValueError, "duplicate_instrument_identity"):
            InstrumentMaster(entries=(entry, entry))


class CollectionScopeContractTest(unittest.TestCase):
    def test_collection_scope_exposes_every_explicit_typed_field(self) -> None:
        scope = _scope()

        self.assertEqual(
            tuple(field.name for field in fields(CollectionScope)),
            (
                "provider",
                "feed",
                "instrument_id",
                "symbol",
                "interval",
                "start_at",
                "end_at",
                "adjustment_mode",
                "session_scope",
                "sample_role",
            ),
        )
        self.assertEqual(scope.provider, "toss")
        self.assertEqual(scope.interval, "1m")
        self.assertEqual(scope.sample_role, SampleRole.SEEN)

    def test_collection_scope_rejects_empty_or_untyped_identifiers(self) -> None:
        identifier_fields = (
            "provider",
            "feed",
            "instrument_id",
            "symbol",
            "adjustment_mode",
            "session_scope",
        )

        for field_name in identifier_fields:
            for invalid_value in ("", "   ", None, 1):
                with self.subTest(field_name=field_name, invalid_value=invalid_value):
                    with self.assertRaisesRegex(
                        ValueError,
                        "collection_scope_identifier_invalid",
                    ):
                        _scope(**{field_name: invalid_value})

    def test_collection_scope_allows_only_one_minute_or_one_day_interval(self) -> None:
        self.assertEqual(_scope(interval="1m").interval, "1m")
        self.assertEqual(_scope(interval="1d").interval, "1d")

        for invalid_interval in ("", "5m", "1h", None, 1, []):
            with self.subTest(invalid_interval=invalid_interval):
                with self.assertRaisesRegex(
                    ValueError,
                    "collection_scope_interval_invalid",
                ):
                    _scope(interval=invalid_interval)

    def test_collection_scope_requires_an_explicit_sample_role(self) -> None:
        for invalid_role in ("seen", "unseen", "confirmation", None, 1):
            with self.subTest(invalid_role=invalid_role):
                with self.assertRaisesRegex(
                    ValueError,
                    "collection_scope_sample_role_invalid",
                ):
                    _scope(sample_role=invalid_role)

    def test_collection_scope_requires_utc_aware_timestamps(self) -> None:
        non_utc = timezone(timedelta(hours=9))
        invalid_timestamps = (
            datetime(2023, 1, 3),
            datetime(2023, 1, 3, tzinfo=non_utc),
            "2023-01-03T00:00:00Z",
            None,
        )

        for field_name in ("start_at", "end_at"):
            for invalid_timestamp in invalid_timestamps:
                with self.subTest(
                    field_name=field_name,
                    invalid_timestamp=invalid_timestamp,
                ):
                    with self.assertRaisesRegex(
                        ValueError,
                        "collection_scope_timestamp_must_be_utc",
                    ):
                        _scope(**{field_name: invalid_timestamp})

    def test_collection_scope_requires_start_before_end(self) -> None:
        instant = datetime(2026, 7, 1, tzinfo=timezone.utc)

        with self.assertRaisesRegex(ValueError, "collection_scope_window_invalid"):
            _scope(start_at=instant, end_at=instant)
        with self.assertRaisesRegex(ValueError, "collection_scope_window_invalid"):
            _scope(
                start_at=instant,
                end_at=datetime(2023, 1, 3, tzinfo=timezone.utc),
            )

    def test_acquisition_identity_is_invariant_to_analysis_sample_role(self) -> None:
        scopes = tuple(
            _scope(sample_role=role)
            for role in (
                SampleRole.SEEN,
                SampleRole.UNSEEN,
                SampleRole.CONFIRMATION,
            )
        )

        self.assertEqual(
            len({scope.acquisition_key for scope in scopes}),
            1,
        )
        self.assertEqual(
            len({scope.acquisition_digest for scope in scopes}),
            1,
        )
        self.assertEqual(
            len({scope.canonical_acquisition_json_bytes() for scope in scopes}),
            1,
        )
        self.assertNotIn("sampleRole", scopes[0].acquisition_identity_body())
        self.assertEqual(
            tuple(scope.to_canonical_body()["sampleRole"] for scope in scopes),
            ("seen", "unseen", "confirmation"),
        )

        expected_digest = hashlib.sha256(
            scopes[0].canonical_acquisition_json_bytes()
        ).hexdigest()
        self.assertEqual(scopes[0].acquisition_key, expected_digest)
        self.assertEqual(scopes[0].acquisition_digest, expected_digest)
        self.assertNotEqual(
            scopes[0].acquisition_key,
            _scope(symbol="MSFT", instrument_id="MSFT").acquisition_key,
        )


class SealedResearchViewContractTest(unittest.TestCase):
    def test_raw_archive_metadata_hash_and_row_count_are_visible_for_every_role(
        self,
    ) -> None:
        raw_kinds = (
            ResearchDataKind.RAW_ARCHIVE_METADATA,
            ResearchDataKind.RAW_ARCHIVE_HASH,
            ResearchDataKind.RAW_ARCHIVE_ROW_COUNT,
        )

        for role in SampleRole:
            access = ResearchViewAccess(role, FormulaState.DISCOVERY)
            for data_kind in raw_kinds:
                with self.subTest(role=role, data_kind=data_kind):
                    self.assertTrue(access.can_read(data_kind))
                    access.require_read(data_kind)

    def test_confirmation_values_features_and_labels_open_only_after_formula_freeze(
        self,
    ) -> None:
        sensitive_kinds = (
            ResearchDataKind.BAR_VALUES,
            ResearchDataKind.FEATURES,
            ResearchDataKind.LABELS,
        )
        sealed_confirmation = ResearchViewAccess(
            SampleRole.CONFIRMATION,
            FormulaState.DISCOVERY,
        )
        discovery = ResearchViewAccess(SampleRole.SEEN, FormulaState.DISCOVERY)
        unseen = ResearchViewAccess(SampleRole.UNSEEN, FormulaState.DISCOVERY)
        opened_confirmation = ResearchViewAccess(
            SampleRole.CONFIRMATION,
            FormulaState.FORMULA_FROZEN,
        )

        for data_kind in sensitive_kinds:
            with self.subTest(data_kind=data_kind):
                self.assertFalse(sealed_confirmation.can_read(data_kind))
                with self.assertRaisesRegex(
                    PermissionError,
                    "confirmation_research_view_sealed",
                ):
                    sealed_confirmation.require_read(data_kind)
                self.assertTrue(discovery.can_read(data_kind))
                discovery.require_read(data_kind)
                self.assertTrue(unseen.can_read(data_kind))
                unseen.require_read(data_kind)
                self.assertTrue(opened_confirmation.can_read(data_kind))
                opened_confirmation.require_read(data_kind)

    def test_research_view_policy_fails_closed_on_untyped_inputs(self) -> None:
        with self.assertRaisesRegex(ValueError, "research_view_sample_role_invalid"):
            ResearchViewAccess("confirmation", FormulaState.DISCOVERY)
        with self.assertRaisesRegex(ValueError, "research_view_formula_state_invalid"):
            ResearchViewAccess(SampleRole.CONFIRMATION, "formula_frozen")

        access = ResearchViewAccess(
            SampleRole.CONFIRMATION,
            FormulaState.DISCOVERY,
        )
        with self.assertRaisesRegex(ValueError, "research_view_data_kind_invalid"):
            access.can_read("bar_values")


if __name__ == "__main__":
    unittest.main()
