from __future__ import annotations

import importlib
import importlib.util
import unittest
from enum import Enum
from typing import Callable, cast


POLICY_MODULE_NAME = "rp001.sensitive_value_policy"
EXPECTED_CATEGORY_VALUES = frozenset(
    {
        "account_number",
        "aws_access_key",
        "authorization_assignment",
        "bearer_token",
        "cano_account_number",
        "database_url_credentials",
        "generic_secret_assignment",
        "github_personal_access_token",
        "google_api_key",
        "kis_api_credential",
        "openai_api_key",
        "pem_private_key",
        "slack_token",
        "toss_api_credential",
    }
)


class SensitiveValuePolicyTest(unittest.TestCase):
    def _load_policy_api(
        self,
    ) -> tuple[type[Enum], Callable[[str], tuple[object, ...]]]:
        module_spec = importlib.util.find_spec(POLICY_MODULE_NAME)
        self.assertIsNotNone(
            module_spec,
            "missing RP-001 sensitive-value policy module",
        )
        module = importlib.import_module(POLICY_MODULE_NAME)
        category_type = getattr(module, "SensitiveValueCategory", None)
        scan = getattr(module, "find_sensitive_values", None)
        self.assertTrue(
            isinstance(category_type, type) and issubclass(category_type, Enum),
            "SensitiveValueCategory must be an Enum",
        )
        self.assertTrue(callable(scan), "find_sensitive_values must be callable")
        return (
            cast(type[Enum], category_type),
            cast(Callable[[str], tuple[object, ...]], scan),
        )

    @staticmethod
    def _category_values(matches: tuple[object, ...]) -> tuple[str, ...]:
        return tuple(
            cast(str, cast(Enum, getattr(match, "category")).value)
            for match in matches
        )

    def test_exposes_all_registered_pattern_categories(self) -> None:
        category_type, scan = self._load_policy_api()

        self.assertEqual(
            {cast(str, category.value) for category in category_type},
            EXPECTED_CATEGORY_VALUES,
        )
        self.assertEqual(scan("ordinary research text"), ())

    def test_detects_each_registered_pattern_family_without_returning_values(
        self,
    ) -> None:
        _category_type, scan = self._load_policy_api()
        positive_fixtures = (
            ("toss_api_credential", "ts" + "ck_" + "live_" + "A1" * 12),
            ("toss_api_credential", "ts" + "sk_" + "test_" + "B2" * 12),
            ("toss_api_credential", "ts" + "ck_" + "sandbox_" + "C3" * 12),
            ("openai_api_key", "sk" + "-" + "proj-" + "D4" * 16),
            ("aws_access_key", "AK" + "IA" + "E5" * 8),
            (
                "github_personal_access_token",
                "gh" + "p_" + "F6g" * 8,
            ),
            ("google_api_key", "AI" + "za" + "G7_" * 11 + "HI"),
            ("slack_token", "xo" + "xb-" + "1234567890-" + "Jk8" * 8),
            ("slack_token", "xa" + "pp-" + "1-" + "Kl9" * 8),
            ("slack_token", "xw" + "fp-" + "Mn0" * 8),
            ("bearer_token", "Bear" + "er " + "Lm9._-" * 4),
            (
                "pem_private_key",
                "-----BEGIN " + "PRIVATE KEY-----",
            ),
            (
                "database_url_credentials",
                "post" + "gresql://reader:SyntheticPass_123@localhost/research",
            ),
            (
                "database_url_credentials",
                "my" + "sql://reader:SyntheticPass_123@localhost/research",
            ),
            (
                "database_url_credentials",
                "mongo" + "db://reader:SyntheticPass_123@localhost/research",
            ),
            (
                "database_url_credentials",
                "re" + "dis://reader:SyntheticPass_123@localhost/0",
            ),
            (
                "database_url_credentials",
                "re" + "dis://:SyntheticPass_123@localhost/0",
            ),
            (
                "generic_secret_assignment",
                "client_" + "secret = " + "SyntheticValue_12345",
            ),
            (
                "account_number",
                "account" + "-number = " + "1234-5678-9012",
            ),
            ("account_number", "계좌" + "번호: " + "9876-5432-1098"),
        )

        for expected_category, source in positive_fixtures:
            with self.subTest(expected_category=expected_category):
                matches = scan(source)
                self.assertEqual(self._category_values(matches), (expected_category,))
                match = matches[0]
                self.assertIsInstance(getattr(match, "start_index", None), int)
                self.assertIsInstance(getattr(match, "end_index", None), int)
                self.assertLess(
                    cast(int, getattr(match, "start_index")),
                    cast(int, getattr(match, "end_index")),
                )
                self.assertFalse(hasattr(match, "matched_value"))
                self.assertFalse(hasattr(match, "value"))

    def test_returns_records_in_source_order(self) -> None:
        _category_type, scan = self._load_policy_api()
        source = "prefix " + ("AK" + "IA" + "Q1" * 8) + " then " + (
            "Bear" + "er " + "Rs2._-" * 4
        )

        matches = scan(source)

        self.assertEqual(
            self._category_values(matches),
            ("aws_access_key", "bearer_token"),
        )
        self.assertLess(
            cast(int, getattr(matches[0], "start_index")),
            cast(int, getattr(matches[1], "start_index")),
        )

    def test_detects_kis_credentials_cano_and_authorization_assignments(self) -> None:
        _category_type, scan = self._load_policy_api()
        positive_fixtures = (
            (
                "kis_api_credential",
                "app" + "Key = SyntheticKisAppKey_12345",
            ),
            (
                "kis_api_credential",
                "app_" + "secret: SyntheticKisAppSecret_12345",
            ),
            (
                "kis_api_credential",
                "app-" + "key=AnotherSyntheticKisKey_12345",
            ),
            (
                "kis_api_credential",
                "app" + "Secret = AnotherSyntheticKisSecret_12345",
            ),
            (
                "kis_api_credential",
                "app " + "key = SpacedSyntheticKisKey_12345",
            ),
            (
                "kis_api_credential",
                "app " + "secret = SpacedSyntheticKisSecret_12345",
            ),
            (
                "cano_account_number",
                "CA" + "NO = " + "1234" + "5678",
            ),
            (
                "authorization_assignment",
                "Author" + "ization = SyntheticAuthorizationValue_12345",
            ),
        )

        for expected_category, source in positive_fixtures:
            with self.subTest(expected_category=expected_category, label=source[:12]):
                matches = scan(source)
                self.assertEqual(self._category_values(matches), (expected_category,))
                match = matches[0]
                self.assertIsInstance(getattr(match, "start_index", None), int)
                self.assertIsInstance(getattr(match, "end_index", None), int)
                self.assertFalse(hasattr(match, "matched_value"))
                self.assertFalse(hasattr(match, "value"))

    def test_kis_patterns_do_not_duplicate_existing_secret_families(self) -> None:
        _category_type, scan = self._load_policy_api()
        fixtures = (
            (
                "generic_secret_assignment",
                "client" + "Secret = SyntheticClientSecret_12345",
            ),
            (
                "generic_secret_assignment",
                "access_" + "token = SyntheticAccessToken_12345",
            ),
            (
                "toss_api_credential",
                "ts" + "ck_" + "live_" + "A1" * 12,
            ),
        )

        for expected_category, source in fixtures:
            with self.subTest(expected_category=expected_category):
                self.assertEqual(
                    self._category_values(scan(source)),
                    (expected_category,),
                )

    def test_ignores_benign_hashes_dates_ids_placeholders_and_unlabeled_numbers(
        self,
    ) -> None:
        _category_type, scan = self._load_policy_api()
        benign_fixtures = (
            "sha256=" + "a" * 64,
            "2026-07-10T08:17:10+09:00",
            "RB-001 REQ-216 ST-ONT-001",
            "550e8400-e29b-41d4-a716-446655440000",
            "12345678901234567890",
            "api_" + "key = REDACTED",
            "secret" + " = placeholder",
            "token" + " = unset",
            "post" + "gresql://localhost/research",
            "post" + "gresql://reader@localhost/research",
            "accounting_number=123456789012",
            "API key and access token values are prohibited.",
            "appKey appSecret app_key app-secret CANO Authorization",
            "app" + "Key = REDACTED",
            "app_" + "secret = example",
            "app-" + "key = placeholder",
            "app" + "Secret = null",
            "CA" + "NO = unset",
            "Author" + "ization = not_set",
            "Author" + "ization: Bearer <TOKEN>",
            "doi:10.1007/s11222-014-9523-8",
        )

        for source in benign_fixtures:
            with self.subTest(source_description=source[:24]):
                self.assertEqual(scan(source), ())


if __name__ == "__main__":
    unittest.main()
