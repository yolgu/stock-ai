from __future__ import annotations

import dataclasses
import json
import unittest
from collections.abc import Iterator, Mapping
from datetime import date

from rp001 import sample_selection
from rp001.sensitive_value_policy import find_sensitive_values


FORMULA_SOURCE_SHA256 = "0" * 64
FORMULA_ARTIFACT_SHA256 = "1" * 64
FAKE_API_KEY_SENTINEL = "".join(("ts", "ck_", "live_", "TEST_SENTINEL"))
FAKE_SECRET_KEY_SENTINEL = "".join(("ts", "sk_", "live_", "TEST_SENTINEL"))
AUTHORIZATION_SENTINEL = "".join(("Bearer", " "))
HOSTILE_MAPPING_DETAIL = "UNTRUSTED_MAPPING_FAILURE_DETAIL"
REQUIRED_API = (
    "CANDIDATE_POOL",
    "SampleSelectionContractError",
    "SampleSelectionResult",
    "evaluate_eligibility",
    "project_stock_metadata",
    "select_metadata_sample",
)
API_READY = all(hasattr(sample_selection, name) for name in REQUIRED_API)

KNOWN_RANKING = (
    ("AVGO", "02227a809a819d40629ab49c36fd30b707287b135be920a33a810d30b3fe22b6"),
    ("CAT", "0fd5c9dd4d5652c0ef5eaef94940505c3f1f7e739e46f444cc7a6d7b5adadecd"),
    ("META", "19807165567c6c3464d98130f3e4ed831d15881b648b3de78c871681affa2169"),
    ("AMD", "3b0dc944f7151899bb60a6f96b39b0107ec4d35225f5e9d5aa8545a8dac5a5e4"),
    ("KO", "52eecca8fee55e58d57fccb2c19d602cbfe76e103382182698620339ede6a194"),
    ("AMZN", "6e0ecfdd86ff38312d24fa8aaab3c5ee05cdbdc043b079baba9b3897b2b6a280"),
    ("QCOM", "791d8872b2650b3edfc759a3ea5fe0533e705298efb8aaf435a2f12a278c8d8a"),
    ("MSFT", "9b81e0c1905fedf8336820e0f97352c5c98f8c4422332db9712aae2f112b63e7"),
    ("JPM", "af283ee3bb5f0df9e6179293ff2c692ad93dfdf588a1e8ab6b825fde6b89c3d1"),
    ("COST", "e43903d49bea78b4aa2a172e9a78104bd39bf3139f03e168dfa67b745acf1ffc"),
    ("XOM", "ee38c616513ccec3a89563a0e4cf8158c7a88da53058ad982e53408e56d58da6"),
    ("AAPL", "fda1773c40d613ae8a5beee2d0a768637eedff08d2b056d5cb9e8c66bb0241f9"),
)


def stock_metadata(
    symbol: str,
    **overrides: object,
) -> dict[str, object]:
    values: dict[str, object] = {
        "symbol": symbol,
        "name": f"{symbol} Inc.",
        "englishName": f"{symbol} Incorporated",
        "isinCode": f"US{symbol:0<10}"[:12],
        "market": "NASDAQ",
        "securityType": "STOCK",
        "isCommonShare": True,
        "status": "ACTIVE",
        "currency": "USD",
        "sharesOutstanding": "1000000",
    }
    values.update(overrides)
    return values


def eligible_pool() -> list[dict[str, object]]:
    return [stock_metadata(symbol) for symbol in sample_selection.CANDIDATE_POOL]


def select(
    payloads: list[object],
    *,
    formula_source_sha256: str = FORMULA_SOURCE_SHA256,
    formula_artifact_sha256: str | None = FORMULA_ARTIFACT_SHA256,
) -> sample_selection.SampleSelectionResult:
    return sample_selection.select_metadata_sample(
        payloads,
        formula_source_sha256=formula_source_sha256,
        formula_artifact_sha256=formula_artifact_sha256,
    )


class ReadOnceMapping(Mapping[str, object]):
    def __init__(self, values: Mapping[str, object]) -> None:
        self._values = dict(values)
        self.read_counts: dict[str, int] = {}

    def __getitem__(self, key: str) -> object:
        count = self.read_counts.get(key, 0) + 1
        self.read_counts[key] = count
        if count > 1:
            raise RuntimeError(HOSTILE_MAPPING_DETAIL)
        return self._values[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)


class ExplodingMapping(Mapping[str, object]):
    def __getitem__(self, key: str) -> object:
        raise RuntimeError(HOSTILE_MAPPING_DETAIL)

    def __iter__(self) -> Iterator[str]:
        raise RuntimeError(HOSTILE_MAPPING_DETAIL)

    def __len__(self) -> int:
        return 1


class ApiSurfaceTest(unittest.TestCase):
    def test_required_sample_selection_api_exists(self) -> None:
        missing = tuple(
            name for name in REQUIRED_API if not hasattr(sample_selection, name)
        )

        self.assertEqual((), missing)


@unittest.skipUnless(API_READY, "sample selection API is not implemented yet")
class DeterministicRankingTest(unittest.TestCase):
    def test_known_sha256_vector_determines_entire_ranked_pool(self) -> None:
        result = select(eligible_pool())

        actual = tuple(
            (entry.metadata.symbol, entry.ranking_digest)
            for entry in result.ranked_pool
        )

        self.assertEqual(KNOWN_RANKING, actual)
        self.assertEqual(tuple(symbol for symbol, _ in KNOWN_RANKING[:6]), result.selected_symbols)
        self.assertEqual(tuple(range(1, 13)), tuple(entry.rank for entry in result.ranked_pool))
        self.assertEqual(
            f"{FORMULA_SOURCE_SHA256}:AVGO",
            result.ranked_pool[0].selection_basis_hash_input,
        )

    def test_input_permutation_does_not_change_selection_output(self) -> None:
        forward = select(eligible_pool())
        reverse = select(list(reversed(eligible_pool())))

        self.assertEqual(forward, reverse)

    def test_optional_formula_artifact_binding_does_not_change_ranking(self) -> None:
        first = select(eligible_pool(), formula_artifact_sha256="1" * 64)
        second = select(eligible_pool(), formula_artifact_sha256="2" * 64)

        self.assertEqual(
            tuple(entry.ranking_digest for entry in first.ranked_pool),
            tuple(entry.ranking_digest for entry in second.ranked_pool),
        )
        self.assertEqual("1" * 64, first.ranking_binding.formula_artifact_sha256)
        self.assertEqual("2" * 64, second.ranking_binding.formula_artifact_sha256)


@unittest.skipUnless(API_READY, "sample selection API is not implemented yet")
class MetadataCoverageTest(unittest.TestCase):
    def assert_contract_error(
        self,
        expected_code: str,
        payloads: list[Mapping[str, object]],
        *,
        formula_source_sha256: str = FORMULA_SOURCE_SHA256,
        formula_artifact_sha256: str | None = FORMULA_ARTIFACT_SHA256,
    ) -> None:
        with self.assertRaises(sample_selection.SampleSelectionContractError) as raised:
            select(
                payloads,
                formula_source_sha256=formula_source_sha256,
                formula_artifact_sha256=formula_artifact_sha256,
            )

        self.assertEqual(expected_code, raised.exception.code)

    def test_duplicate_symbol_is_rejected(self) -> None:
        payloads = eligible_pool() + [stock_metadata("AAPL")]

        self.assert_contract_error("duplicate_symbol", payloads)

    def test_missing_pool_symbol_is_rejected(self) -> None:
        payloads = [row for row in eligible_pool() if row["symbol"] != "XOM"]

        self.assert_contract_error("missing_pool_symbol", payloads)

    def test_symbol_outside_frozen_pool_is_rejected(self) -> None:
        payloads = eligible_pool() + [stock_metadata("TSLA")]

        self.assert_contract_error("symbol_outside_pool", payloads)

    def test_invalid_formula_source_sha256_is_rejected(self) -> None:
        invalid_hashes = ("0" * 63, "A" * 64, "g" * 64, "0" * 65)

        for invalid_hash in invalid_hashes:
            with self.subTest(invalid_hash=invalid_hash):
                self.assert_contract_error(
                    "invalid_formula_source_sha256",
                    eligible_pool(),
                    formula_source_sha256=invalid_hash,
                )

    def test_invalid_optional_formula_artifact_sha256_is_rejected(self) -> None:
        self.assert_contract_error(
            "invalid_formula_artifact_sha256",
            eligible_pool(),
            formula_artifact_sha256="F" * 64,
        )


@unittest.skipUnless(API_READY, "sample selection API is not implemented yet")
class EligibilityTest(unittest.TestCase):
    def test_each_frozen_eligibility_rule_has_a_deterministic_reason(self) -> None:
        cases = (
            ({"status": "SUSPENDED"}, ("status_not_active",)),
            ({"isCommonShare": False}, ("not_common_share",)),
            ({"currency": "KRW"}, ("currency_not_usd",)),
            ({"market": "KOSPI"}, ("market_not_supported",)),
            ({"securityType": "ETF"}, ("security_type_not_supported",)),
            ({"market": "NYSE", "securityType": "FOREIGN_STOCK"}, ()),
            ({"market": "AMEX"}, ()),
        )

        for overrides, expected_values in cases:
            with self.subTest(overrides=overrides):
                metadata = sample_selection.project_stock_metadata(
                    stock_metadata("AAPL", **overrides)
                )
                reasons = sample_selection.evaluate_eligibility(metadata)

                self.assertEqual(expected_values, tuple(reason.value for reason in reasons))

    def test_multiple_ineligibility_reasons_use_fixed_rule_order(self) -> None:
        metadata = sample_selection.project_stock_metadata(
            stock_metadata(
                "AAPL",
                status="SUSPENDED",
                isCommonShare=False,
                currency="KRW",
                market="KOSPI",
                securityType="ETF",
            )
        )

        reasons = sample_selection.evaluate_eligibility(metadata)

        self.assertEqual(
            (
                "status_not_active",
                "not_common_share",
                "currency_not_usd",
                "market_not_supported",
                "security_type_not_supported",
            ),
            tuple(reason.value for reason in reasons),
        )

    def test_too_few_eligible_symbols_is_rejected_without_replacement(self) -> None:
        payloads = eligible_pool()
        for index in range(7):
            payloads[index] = dict(payloads[index], status="SUSPENDED")

        with self.assertRaises(sample_selection.SampleSelectionContractError) as raised:
            select(payloads)

        self.assertEqual("too_few_eligible", raised.exception.code)
        self.assertNotIn("replacement", str(raised.exception).lower())

    def test_ineligible_entries_remain_in_entire_ranked_pool(self) -> None:
        payloads = eligible_pool()
        payloads[0] = dict(payloads[0], status="SUSPENDED")

        result = select(payloads)
        decision = next(
            entry for entry in result.ranked_pool if entry.metadata.symbol == "AAPL"
        )

        self.assertFalse(decision.eligible)
        self.assertEqual(("status_not_active",), tuple(reason.value for reason in decision.reasons))
        self.assertEqual(12, len(result.ranked_pool))
        self.assertNotIn("AAPL", result.selected_symbols)


@unittest.skipUnless(API_READY, "sample selection API is not implemented yet")
class ProjectionBoundaryTest(unittest.TestCase):
    def test_price_outcome_and_performance_fields_are_rejected(self) -> None:
        forbidden_fields = (
            "price",
            "open",
            "high",
            "low",
            "close",
            "closePrice",
            "adjusted_close",
            "volume",
            "turnoverValue",
            "return10d",
            "label",
            "outcome",
            "performanceScore",
            "candles",
            "ohlcv",
        )

        for forbidden_field in forbidden_fields:
            with self.subTest(forbidden_field=forbidden_field):
                payloads = eligible_pool()
                payloads[0] = dict(payloads[0], **{forbidden_field: 123})

                with self.assertRaises(sample_selection.SampleSelectionContractError) as raised:
                    select(payloads)

                self.assertEqual("forbidden_selection_field", raised.exception.code)

    def test_unknown_non_market_fields_are_explicitly_removed_by_projection(self) -> None:
        payload = stock_metadata(
            "AAPL",
            providerExtension="not-a-selection-input",
        )

        projected = sample_selection.project_stock_metadata(payload)

        self.assertFalse(hasattr(projected, "providerExtension"))

    def test_official_non_selection_fields_are_projected_away(self) -> None:
        official_non_selection_fields = {
            "listDate": "1980-12-12",
            "delistDate": None,
            "leverageFactor": "1",
            "koreanMarketDetail": "NONE",
        }
        payload = stock_metadata("AAPL", **official_non_selection_fields)

        projected = sample_selection.project_stock_metadata(payload)
        canonical_body = projected.to_canonical_body()

        for field_name in official_non_selection_fields:
            with self.subTest(field_name=field_name):
                self.assertNotIn(field_name, canonical_body)

    def test_missing_or_invalid_required_metadata_is_rejected_at_projection(self) -> None:
        missing = stock_metadata("AAPL")
        missing.pop("market")

        with self.assertRaises(sample_selection.SampleSelectionContractError) as missing_error:
            sample_selection.project_stock_metadata(missing)
        with self.assertRaises(sample_selection.SampleSelectionContractError) as type_error:
            sample_selection.project_stock_metadata(
                stock_metadata("AAPL", isCommonShare="true")
            )

        self.assertEqual("missing_metadata_field", missing_error.exception.code)
        self.assertEqual("invalid_metadata_field", type_error.exception.code)


@unittest.skipUnless(API_READY, "sample selection API is not implemented yet")
class MetadataSnapshotBoundaryTest(unittest.TestCase):
    def test_non_mapping_items_raise_stable_contract_error(self) -> None:
        for invalid_item in (42, None):
            with self.subTest(invalid_item=invalid_item):
                try:
                    sample_selection.project_stock_metadata(invalid_item)
                except sample_selection.SampleSelectionContractError as error:
                    self.assertEqual("invalid_metadata_item", error.code)
                    self.assertEqual("invalid_metadata_item", str(error))
                except Exception as error:
                    self.fail(f"non-mapping leaked {type(error).__name__}")
                else:
                    self.fail("non-mapping metadata item was accepted")

    def test_external_mapping_is_copied_once_before_validation(self) -> None:
        external = ReadOnceMapping(stock_metadata("AAPL"))

        try:
            projected = sample_selection.project_stock_metadata(external)
        except Exception as error:
            self.fail(f"external mapping was reread: {type(error).__name__}")

        self.assertEqual("AAPL", projected.symbol)
        self.assertEqual(
            {field_name: 1 for field_name in stock_metadata("AAPL")},
            external.read_counts,
        )

    def test_hostile_mapping_copy_failure_is_sanitized(self) -> None:
        try:
            sample_selection.project_stock_metadata(ExplodingMapping())
        except sample_selection.SampleSelectionContractError as error:
            self.assertEqual("invalid_metadata_item", error.code)
            self.assertEqual("invalid_metadata_item", str(error))
            self.assertNotIn(HOSTILE_MAPPING_DETAIL, str(error))
        except Exception as error:
            self.fail(f"mapping failure leaked {type(error).__name__}")
        else:
            self.fail("hostile mapping was accepted")


@unittest.skipUnless(API_READY, "sample selection API is not implemented yet")
class SensitiveMetadataBoundaryTest(unittest.TestCase):
    def test_test_sentinels_are_detected_by_the_central_policy(self) -> None:
        self.assertNotEqual((), find_sensitive_values(FAKE_API_KEY_SENTINEL))
        self.assertNotEqual((), find_sensitive_values(FAKE_SECRET_KEY_SENTINEL))

    def test_sensitive_material_is_rejected_in_every_projected_string_field(
        self,
    ) -> None:
        projected_string_fields = (
            "symbol",
            "name",
            "englishName",
            "isinCode",
            "market",
            "securityType",
            "status",
            "currency",
            "sharesOutstanding",
        )

        for field_name in projected_string_fields:
            with self.subTest(field_name=field_name):
                payload = stock_metadata("AAPL")
                payload[field_name] = FAKE_API_KEY_SENTINEL

                with self.assertRaises(
                    sample_selection.SampleSelectionContractError
                ) as raised:
                    sample_selection.project_stock_metadata(payload)

                self.assertEqual("sensitive_metadata", raised.exception.code)
                self.assertEqual("sensitive_metadata", str(raised.exception))
                self.assertNotIn(FAKE_API_KEY_SENTINEL, str(raised.exception))

    def test_sensitive_unknown_field_names_and_values_are_rejected(self) -> None:
        fixtures = (
            {FAKE_API_KEY_SENTINEL: "ordinary"},
            {"providerNote": FAKE_SECRET_KEY_SENTINEL},
        )

        for fixture in fixtures:
            with self.subTest(field_names=tuple(fixture)):
                payload = stock_metadata("AAPL", **fixture)

                with self.assertRaises(
                    sample_selection.SampleSelectionContractError
                ) as raised:
                    sample_selection.project_stock_metadata(payload)

                self.assertEqual("sensitive_metadata", raised.exception.code)
                self.assertEqual("sensitive_metadata", str(raised.exception))

    def test_external_symbols_and_fields_are_not_echoed_in_errors(self) -> None:
        external_symbol = "UNREGISTERED_EXTERNAL_SYMBOL"
        with self.assertRaises(
            sample_selection.SampleSelectionContractError
        ) as symbol_error:
            select(eligible_pool() + [stock_metadata(external_symbol)])

        external_field = "closePrice_UNTRUSTED_EXTERNAL_FIELD"
        payloads = eligible_pool()
        payloads[0] = dict(payloads[0], **{external_field: "123"})
        with self.assertRaises(
            sample_selection.SampleSelectionContractError
        ) as field_error:
            select(payloads)

        self.assertEqual("symbol_outside_pool", symbol_error.exception.code)
        self.assertEqual("symbol_outside_pool", str(symbol_error.exception))
        self.assertNotIn(external_symbol, str(symbol_error.exception))
        self.assertEqual("forbidden_selection_field", field_error.exception.code)
        self.assertEqual("forbidden_selection_field", str(field_error.exception))
        self.assertNotIn(external_field, str(field_error.exception))


@unittest.skipUnless(API_READY, "sample selection API is not implemented yet")
class OfficialStockInfoCompatibilityTest(unittest.TestCase):
    def test_shares_outstanding_preserves_required_decimal_string(self) -> None:
        try:
            metadata = sample_selection.project_stock_metadata(
                stock_metadata("AAPL", sharesOutstanding="000123")
            )
        except sample_selection.SampleSelectionContractError as error:
            self.fail(f"valid decimal string was rejected with {error.code}")

        self.assertEqual("000123", metadata.shares_outstanding)
        self.assertEqual(
            "000123",
            metadata.to_canonical_body()["sharesOutstanding"],
        )

    def test_shares_outstanding_accepts_thirty_ascii_digits(self) -> None:
        try:
            metadata = sample_selection.project_stock_metadata(
                stock_metadata("AAPL", sharesOutstanding="9" * 30)
            )
        except sample_selection.SampleSelectionContractError as error:
            self.fail(f"valid maximum-length value was rejected with {error.code}")

        self.assertEqual("9" * 30, metadata.shares_outstanding)

    def test_shares_outstanding_rejects_non_decimal_string_contract(self) -> None:
        invalid_values: tuple[object, ...] = (
            True,
            1,
            None,
            "",
            "12.3",
            "-1",
            "１２３",
            "1" * 31,
        )

        for invalid_value in invalid_values:
            with self.subTest(invalid_value=invalid_value):
                with self.assertRaises(
                    sample_selection.SampleSelectionContractError
                ) as raised:
                    sample_selection.project_stock_metadata(
                        stock_metadata(
                            "AAPL",
                            sharesOutstanding=invalid_value,
                        )
                    )

                self.assertEqual("invalid_metadata_field", raised.exception.code)

    def test_shares_outstanding_does_not_affect_ranking_or_selection(self) -> None:
        first_payloads = eligible_pool()
        second_payloads = [
            dict(payload, sharesOutstanding=str(index + 1))
            for index, payload in enumerate(eligible_pool())
        ]

        first = select(first_payloads)
        second = select(second_payloads)

        self.assertEqual(
            tuple(entry.ranking_digest for entry in first.ranked_pool),
            tuple(entry.ranking_digest for entry in second.ranked_pool),
        )
        self.assertEqual(first.selected_symbols, second.selected_symbols)


@unittest.skipUnless(API_READY, "sample selection API is not implemented yet")
class FrozenValueObjectInvariantTest(unittest.TestCase):
    def test_selection_period_rejects_every_non_frozen_construction(self) -> None:
        invalid_overrides: tuple[dict[str, object], ...] = (
            {"start_date": date(2026, 7, 1)},
            {"timezone": ""},
            {"interval": ""},
            {"inclusive": False},
            {"start_date": date(2023, 1, 4)},
        )

        for overrides in invalid_overrides:
            with self.subTest(overrides=overrides):
                values: dict[str, object] = {
                    "start_date": date(2023, 1, 3),
                    "end_date": date(2026, 6, 30),
                    "inclusive": True,
                    "timezone": "America/New_York",
                    "interval": "1d",
                }
                values.update(overrides)

                with self.assertRaises(ValueError) as raised:
                    sample_selection.SelectionPeriod(**values)  # type: ignore[arg-type]

                self.assertEqual("invalid_selection_period", str(raised.exception))

    def test_sample_data_roles_rejects_swapped_or_untyped_roles(self) -> None:
        invalid_roles = (
            (
                sample_selection.DataRole.AUDIT_ONLY,
                sample_selection.DataRole.UNSEEN_HISTORICAL_CONFIRMATION,
                sample_selection.DataRole.METADATA_ONLY,
            ),
            (
                "metadata_only",
                sample_selection.DataRole.UNSEEN_HISTORICAL_CONFIRMATION,
                sample_selection.DataRole.AUDIT_ONLY,
            ),
        )

        for metadata_role, selected_role, unselected_role in invalid_roles:
            with self.subTest(metadata_role=metadata_role):
                with self.assertRaises(ValueError) as raised:
                    sample_selection.SampleDataRoles(
                        metadata_request=metadata_role,  # type: ignore[arg-type]
                        selected_candles=selected_role,
                        unselected_symbols=unselected_role,
                    )

                self.assertEqual("invalid_sample_data_roles", str(raised.exception))


@unittest.skipUnless(API_READY, "sample selection API is not implemented yet")
class FrozenContractOutputTest(unittest.TestCase):
    def test_output_freezes_scope_period_roles_count_and_bindings(self) -> None:
        result = select(eligible_pool())

        self.assertEqual("rp001-metadata-sample-selection.v1", result.schema_id)
        self.assertEqual("RP-001", result.program_id)
        self.assertEqual("1.2-COMPACT", result.goal_version)
        self.assertEqual("research_only", result.usage_scope)
        self.assertEqual("no_trade_no_integration", result.operational_disposition)
        self.assertEqual(
            ("AAPL", "AMD", "AMZN", "AVGO", "CAT", "COST", "JPM", "KO", "META", "MSFT", "QCOM", "XOM"),
            result.candidate_pool,
        )
        self.assertEqual(6, result.desired_selection_count)
        self.assertEqual("2023-01-03", result.period.start_date.isoformat())
        self.assertEqual("2026-06-30", result.period.end_date.isoformat())
        self.assertTrue(result.period.inclusive)
        self.assertEqual("America/New_York", result.period.timezone)
        self.assertEqual("1d", result.period.interval)
        self.assertEqual("metadata_only", result.data_roles.metadata_request.value)
        self.assertEqual(
            "unseen_historical_confirmation",
            result.data_roles.selected_candles.value,
        )
        self.assertEqual("audit_only", result.data_roles.unselected_symbols.value)
        self.assertEqual(FORMULA_SOURCE_SHA256, result.ranking_binding.formula_source_sha256)
        self.assertEqual(
            f"{FORMULA_SOURCE_SHA256}:{{symbol}}",
            result.ranking_binding.selection_basis_hash_input_template,
        )

    def test_contract_objects_are_frozen_dataclasses(self) -> None:
        result = select(eligible_pool())

        with self.assertRaises(dataclasses.FrozenInstanceError):
            result.desired_selection_count = 7  # type: ignore[misc]
        with self.assertRaises(dataclasses.FrozenInstanceError):
            result.period.interval = "1m"  # type: ignore[misc]

    def test_canonical_body_contains_no_own_hash_or_secret_shaped_values(self) -> None:
        payloads = eligible_pool()
        payloads[0] = dict(payloads[0], providerNote="ordinary provider metadata")

        body = select(payloads).to_canonical_body()
        serialized = json.dumps(body, sort_keys=True)

        self.assertNotIn("artifactSha256", serialized)
        self.assertNotIn("selfSha256", serialized)
        self.assertNotIn("recordSha256", serialized)
        self.assertEqual((), find_sensitive_values(serialized))
        self.assertNotIn(AUTHORIZATION_SENTINEL, serialized)
        self.assertEqual(12, len(body["rankedPool"]))
        self.assertEqual(6, len(body["selectedSymbols"]))


if __name__ == "__main__":
    unittest.main()
