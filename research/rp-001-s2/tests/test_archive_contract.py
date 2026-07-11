from __future__ import annotations

import hashlib
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
_INVALID_IDENTIFIER_VALUES: tuple[object, ...] = (
    "",
    "   ",
    " AAPL",
    "AAPL ",
    "AAPL\r",
    "AAPL\n",
    "AAPL\x00",
    "A\u200bAPL",
    "A\u0301",
    None,
    1,
)
_EXPECTED_INSTRUMENT_MASTER_CANONICAL_BYTES: bytes = (
    b'{"instruments":['
    b'{"instrumentId":"000660","role":"priority","symbol":"000660"},'
    b'{"instrumentId":"AAPL","role":"priority","symbol":"AAPL"},'
    b'{"instrumentId":"AMD","role":"priority","symbol":"AMD"},'
    b'{"instrumentId":"AMZN","role":"priority","symbol":"AMZN"},'
    b'{"instrumentId":"AVGO","role":"priority","symbol":"AVGO"},'
    b'{"instrumentId":"BA","role":"priority","symbol":"BA"},'
    b'{"instrumentId":"CAT","role":"priority","symbol":"CAT"},'
    b'{"instrumentId":"COST","role":"priority","symbol":"COST"},'
    b'{"instrumentId":"CVX","role":"priority","symbol":"CVX"},'
    b'{"instrumentId":"DIS","role":"priority","symbol":"DIS"},'
    b'{"instrumentId":"GE","role":"priority","symbol":"GE"},'
    b'{"instrumentId":"GS","role":"priority","symbol":"GS"},'
    b'{"instrumentId":"HD","role":"priority","symbol":"HD"},'
    b'{"instrumentId":"IBM","role":"priority","symbol":"IBM"},'
    b'{"instrumentId":"JNJ","role":"priority","symbol":"JNJ"},'
    b'{"instrumentId":"JPM","role":"priority","symbol":"JPM"},'
    b'{"instrumentId":"KO","role":"priority","symbol":"KO"},'
    b'{"instrumentId":"LOW","role":"priority","symbol":"LOW"},'
    b'{"instrumentId":"MCD","role":"priority","symbol":"MCD"},'
    b'{"instrumentId":"META","role":"priority","symbol":"META"},'
    b'{"instrumentId":"MRK","role":"priority","symbol":"MRK"},'
    b'{"instrumentId":"MSFT","role":"priority","symbol":"MSFT"},'
    b'{"instrumentId":"MU","role":"priority","symbol":"MU"},'
    b'{"instrumentId":"NFLX","role":"priority","symbol":"NFLX"},'
    b'{"instrumentId":"NKE","role":"priority","symbol":"NKE"},'
    b'{"instrumentId":"NVDA","role":"priority","symbol":"NVDA"},'
    b'{"instrumentId":"ORCL","role":"priority","symbol":"ORCL"},'
    b'{"instrumentId":"PEP","role":"priority","symbol":"PEP"},'
    b'{"instrumentId":"QCOM","role":"priority","symbol":"QCOM"},'
    b'{"instrumentId":"SBUX","role":"priority","symbol":"SBUX"},'
    b'{"instrumentId":"TSLA","role":"priority","symbol":"TSLA"},'
    b'{"instrumentId":"UPS","role":"priority","symbol":"UPS"},'
    b'{"instrumentId":"WMT","role":"priority","symbol":"WMT"},'
    b'{"instrumentId":"XOM","role":"priority","symbol":"XOM"},'
    b'{"instrumentId":"SPY","role":"benchmark","symbol":"SPY"},'
    b'{"instrumentId":"QQQ","role":"benchmark","symbol":"QQQ"},'
    b'{"instrumentId":"IWM","role":"benchmark","symbol":"IWM"},'
    b'{"instrumentId":"XLC","role":"benchmark","symbol":"XLC"},'
    b'{"instrumentId":"XLE","role":"benchmark","symbol":"XLE"},'
    b'{"instrumentId":"XLF","role":"benchmark","symbol":"XLF"},'
    b'{"instrumentId":"XLI","role":"benchmark","symbol":"XLI"},'
    b'{"instrumentId":"XLK","role":"benchmark","symbol":"XLK"},'
    b'{"instrumentId":"XLP","role":"benchmark","symbol":"XLP"},'
    b'{"instrumentId":"XLRE","role":"benchmark","symbol":"XLRE"},'
    b'{"instrumentId":"XLU","role":"benchmark","symbol":"XLU"},'
    b'{"instrumentId":"XLV","role":"benchmark","symbol":"XLV"},'
    b'{"instrumentId":"XLY","role":"benchmark","symbol":"XLY"},'
    b'{"instrumentId":"SOXX","role":"benchmark","symbol":"SOXX"}'
    b'],"schemaVersion":"rp001-s2-direction-neutral-instrument-master.v1"}'
)
_EXPECTED_INSTRUMENT_MASTER_SHA256: str = (
    "0feb9fa68067ac9a8bd1844f2bb7f743dae00a97796cd0adb1106d1bc377758a"
)
_EXPECTED_ACQUISITION_CANONICAL_BYTES: bytes = (
    b'{"adjustmentMode":"provider_native",'
    b'"endAt":"2026-07-01T00:00:00Z",'
    b'"feed":"historical_candles",'
    b'"identityDomain":"rp001_s2.direction_neutral_archive_acquisition",'
    b'"instrumentId":"AAPL","interval":"1m","provider":"toss",'
    b'"schemaVersion":"rp001-s2-direction-neutral-acquisition-identity.v1",'
    b'"sessionScope":"provider_all",'
    b'"startAt":"2023-01-03T00:00:00Z","symbol":"AAPL"}'
)
_EXPECTED_ACQUISITION_SHA256: str = (
    "1e1e65efb653853874c035f0290c8198913e972803eb94db4be4671ee175dfe4"
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

        self.assertEqual(
            first.canonical_json_bytes(),
            _EXPECTED_INSTRUMENT_MASTER_CANONICAL_BYTES,
        )
        self.assertEqual(first.sha256, _EXPECTED_INSTRUMENT_MASTER_SHA256)
        self.assertEqual(
            hashlib.sha256(_EXPECTED_INSTRUMENT_MASTER_CANONICAL_BYTES).hexdigest(),
            _EXPECTED_INSTRUMENT_MASTER_SHA256,
        )

    def test_instrument_master_rejects_duplicate_identity(self) -> None:
        entry = InstrumentMasterEntry(
            instrument_id="AAPL",
            symbol="AAPL",
            role=InstrumentRole.PRIORITY,
        )

        with self.assertRaisesRegex(ValueError, "duplicate_instrument_identity"):
            InstrumentMaster(entries=(entry, entry))

    def test_instrument_master_entry_rejects_noncanonical_identity_and_role(
        self,
    ) -> None:
        for field_name in ("instrument_id", "symbol"):
            for invalid_value in _INVALID_IDENTIFIER_VALUES:
                values: dict[str, object] = {
                    "instrument_id": "AAPL",
                    "symbol": "AAPL",
                    "role": InstrumentRole.PRIORITY,
                }
                values[field_name] = invalid_value
                with self.subTest(field_name=field_name, invalid_value=invalid_value):
                    with self.assertRaisesRegex(
                        ValueError,
                        "instrument_master_identifier_invalid",
                    ):
                        InstrumentMasterEntry(**values)

        with self.assertRaisesRegex(ValueError, "instrument_role_invalid"):
            InstrumentMasterEntry(
                instrument_id="AAPL",
                symbol="AAPL",
                role="priority",
            )

    def test_instrument_master_rejects_mutable_or_untyped_entry_collections(
        self,
    ) -> None:
        entry = InstrumentMasterEntry(
            instrument_id="AAPL",
            symbol="AAPL",
            role=InstrumentRole.PRIORITY,
        )
        mutable_entries = [entry]

        with self.assertRaisesRegex(ValueError, "instrument_master_entries_invalid"):
            InstrumentMaster(entries=mutable_entries)
        for invalid_entries in ((), (object(),), None):
            with self.subTest(invalid_entries=invalid_entries):
                with self.assertRaisesRegex(
                    ValueError,
                    "instrument_master_entries_invalid",
                ):
                    InstrumentMaster(entries=invalid_entries)

        master = InstrumentMaster(entries=tuple(mutable_entries))
        initial_sha256 = master.sha256
        mutable_entries.append(
            InstrumentMasterEntry(
                instrument_id="MSFT",
                symbol="MSFT",
                role=InstrumentRole.PRIORITY,
            )
        )
        self.assertEqual(master.sha256, initial_sha256)


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

    def test_collection_scope_rejects_noncanonical_or_untyped_identifiers(self) -> None:
        identifier_fields = (
            "provider",
            "feed",
            "instrument_id",
            "symbol",
            "adjustment_mode",
            "session_scope",
        )

        for field_name in identifier_fields:
            for invalid_value in _INVALID_IDENTIFIER_VALUES:
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
        self.assertEqual(
            scopes[0].canonical_acquisition_json_bytes(),
            _EXPECTED_ACQUISITION_CANONICAL_BYTES,
        )
        self.assertEqual(scopes[0].acquisition_key, _EXPECTED_ACQUISITION_SHA256)
        self.assertEqual(scopes[0].acquisition_digest, _EXPECTED_ACQUISITION_SHA256)
        self.assertEqual(
            hashlib.sha256(_EXPECTED_ACQUISITION_CANONICAL_BYTES).hexdigest(),
            _EXPECTED_ACQUISITION_SHA256,
        )

    def test_every_acquisition_identity_field_changes_the_digest(self) -> None:
        baseline = _scope()
        identity_variants: dict[str, object] = {
            "provider": "alpaca",
            "feed": "daily_bars",
            "instrument_id": "US0378331005",
            "symbol": "MSFT",
            "interval": "1d",
            "start_at": datetime(2023, 1, 4, tzinfo=timezone.utc),
            "end_at": datetime(2026, 6, 30, tzinfo=timezone.utc),
            "adjustment_mode": "raw",
            "session_scope": "provider_extended",
        }

        for field_name, changed_value in identity_variants.items():
            with self.subTest(field_name=field_name):
                self.assertNotEqual(
                    baseline.acquisition_digest,
                    _scope(**{field_name: changed_value}).acquisition_digest,
                )

        self.assertEqual(
            baseline.acquisition_identity_body()["identityDomain"],
            "rp001_s2.direction_neutral_archive_acquisition",
        )
        self.assertEqual(
            baseline.acquisition_identity_body()["schemaVersion"],
            "rp001-s2-direction-neutral-acquisition-identity.v1",
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
