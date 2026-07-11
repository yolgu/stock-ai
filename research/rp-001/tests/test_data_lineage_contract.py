from __future__ import annotations

import copy
import hashlib
import json
import re
import unittest
from pathlib import Path
from typing import Any, Callable

from rp001.sensitive_value_policy import find_sensitive_values


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PROGRAM_DIRECTORY = (
    REPOSITORY_ROOT
    / "research"
    / "meta-research"
    / "objects"
    / "programs"
    / "RP-001-quantitative-market-behavior"
)
QUESTION_DIRECTORY = (
    REPOSITORY_ROOT
    / "research"
    / "meta-research"
    / "objects"
    / "research-questions"
    / "RQ-002-data-lineage"
)
DATASET_DIRECTORY = (
    REPOSITORY_ROOT
    / "research"
    / "meta-research"
    / "objects"
    / "dataset-contracts"
    / "DC-002-program-data"
)
PROTOCOL_DIRECTORY = (
    REPOSITORY_ROOT
    / "research"
    / "meta-research"
    / "objects"
    / "study-protocols"
    / "SP-002-data-lineage-audit"
)
CATALOG_PATH = (
    REPOSITORY_ROOT
    / "research"
    / "meta-research"
    / "catalog"
    / "research-objects.json"
)
SOURCE_MATRIX_PATH = PROGRAM_DIRECTORY / "source-matrix.json"
SOURCE_MATRIX_MARKDOWN_PATH = PROGRAM_DIRECTORY / "source-matrix.md"
TRIAL_LEDGER_PATH = (
    REPOSITORY_ROOT / "research" / "rp-001" / "trials" / "ST-DAT-001.json"
)

EXPECTED_QUESTION = (
    "GOAL-RP-001이 요구하는 각 필수 입력군에 대해, 시점 t 가용성·계보·단위·"
    "수정·권리 계약을 모두 만족하는 자료가 현재 존재하며 어떤 연구에 사용할 수 있는가?"
)
EXPECTED_TASK5_HASHES = {
    PROGRAM_DIRECTORY / "state-ontology.json": (
        "4e11c9c3a754d542759a0e27f43d9181fa749920a41566a67895c49a71cbcaac"
    ),
    DATASET_DIRECTORY.parent / "DC-001-ontology-evidence" / "source-register.json": (
        "faadcdd8e4660f40ca050201201913250a478fb39bbf273be2ac142f356ecc2c"
    ),
    PROTOCOL_DIRECTORY.parent / "SP-001-market-state-ontology" / "protocol.md": (
        "a180a81c1834f2319e9b16a3d851cbd28b1238c2c383ea36e6f093a203a3138e"
    ),
}
EXPECTED_PROTOCOL_SHA256 = (
    "bbdf0603b55a5b3b18dd20cdc7f2f0161b47dffb35edeffd39026f464fe29a7e"
)
PRIOR_PROTOCOL_SHA256 = (
    "54909d419db11ce6394f7be467cd54732b9d5db94ad5b36d0805d663f8e7ee34"
)
EXPECTED_SOURCE_REGISTER_SHA256 = (
    "fe976ecd724a3a5f9e81d20804ba823a58c98d4ef1db9d1911e1cae4b4f3412d"
)
EXPECTED_SOURCE_MATRIX_SHA256 = (
    "f411dac963717aa7ed8ea1d5351ccbed70987150f6ca0e9a608d54f7677e9e61"
)
EXPECTED_QUESTION_SHA256 = (
    "371d69165b2c2baddc88e39375dd3a66497d278a5b94f44bd86908cfc862db69"
)
EXPECTED_DATA_CONTRACT_SHA256 = (
    "0eb5926196b5ebb1ba6f2f704430a05033336f4363482cdfa85634ecf5a0cca0"
)
EXPECTED_SOURCE_MATRIX_MARKDOWN_SHA256 = (
    "2a6ae40a314ade6e02d90ebec10767749696e5ae2e4d2fa25dc8cae14f08428f"
)
EXPECTED_TASK6_DESCRIPTOR_TEXT = {
    "RQ-002": {
        "title": "프로그램 필수자료의 계보·단위·가용시점·권리 판정",
        "purpose": (
            "GOAL-RP-001의 필수 입력군마다 기술 문서와 실제 수집·이용 권한을 "
            "분리하고, 자료 availability와 주장 identifiability를 서로 다른 축으로 "
            "판정해 현재 허용 연구범위를 고정한다."
        ),
    },
    "DC-002": {
        "title": "프로그램 필수 입력군 데이터 계약",
        "purpose": (
            "GOAL-RP-001의 8개 필수 입력군에 대해 공개 기술 문서, "
            "시점·단위·수정·계보 필드, 권리 한계와 현재 사용 가능범위를 보수적으로 "
            "고정한다."
        ),
    },
    "SP-002": {
        "title": "필수자료 계보·가용시점·권리 감사 사전등록",
        "purpose": (
            "공개 기술 문서와 저장소 경계만으로 8개 입력군의 현재 상태·허용 "
            "연구·차단효과를 판정하고, credential 회전과 보존권리 전에는 라이브 "
            "수집을 금지하는 규칙을 동결한다."
        ),
    },
}
EXPECTED_CREDENTIAL_BOUNDARY = {
    "conversationDisclosureRecorded": True,
    "valuesCopiedOrStoredInArtifactsLogsCommands": False,
    "localCredentialFilePresenceOrPathObservedBeforeFreeze": True,
    "localCredentialFileContentsAccessed": False,
    "localCredentialValuesAccessedFromFile": False,
    "liveApiCalled": False,
    "currentCredentialDisposition": "blocked_pending_rotation",
    "liveCollectionGate": (
        "blocked_pending_rotated_credentials_and_provider_retention_clarification"
    ),
    "forbiddenCredentialLocations": [
        "renderer",
        "persistent_repository",
        "cli_arguments",
    ],
    "futureCredentialBoundary": (
        "rotated_credentials_only_one_shot_child_process_environment"
    ),
}
EXPECTED_MARKDOWN_BINDING_PROSE = {
    (
        "이 문서는 구조화 JSON의 사람이 읽는 projection이다. availability 상태는 "
        "`usable`, `limited`, `data_unavailable`만 사용하고 identifiability 상태는 "
        "`identifiable`, `not_identifiable`만 사용한다. raw input availability와 claim "
        "identifiability를 한 terminal 상태로 합치지 않는다."
    ),
    (
        "raw OHLCV schema availability와 derived claim identifiability를 분리한다. "
        "daily/minute component 열에는 raw input만 두고 `price_volume_regime`은 "
        "identifiability implication과 usableFor에만 둔다."
    ),
}
EXPECTED_SOURCE_IDENTITIES = (
    {
        "sourceId": "TOSS-DOC-001",
        "title": "토스증권 Open API 가이드",
        "officialUrl": "https://developers.tossinvest.com/llms.txt",
        "documentVersion": "unversioned",
        "retrievedAt": "2026-07-10T05:06:44Z",
        "httpResponseSha256": (
            "f2c70cf269867ea0c59a8e9b54b57942d28f1ecef301cce4b927895bceec8952"
        ),
        "priorObservedHttpResponseSha256": [],
    },
    {
        "sourceId": "TOSS-DOC-002",
        "title": "토스증권 Open API",
        "officialUrl": (
            "https://openapi.tossinvest.com/openapi-docs/latest/openapi.json"
        ),
        "documentVersion": "1.2.2",
        "retrievedAt": "2026-07-10T05:06:45Z",
        "httpResponseSha256": (
            "2c54ebfd038a8c135f4b7f9036c42934d8ab9906c026251a7ae827b81e8e6aa8"
        ),
        "priorObservedHttpResponseSha256": [
            "3c1d00b61950688b8712382889b24f3e7ceb6b12f8367019794ccb375099c47c"
        ],
    },
    {
        "sourceId": "TOSS-DOC-003",
        "title": "Overview Markdown",
        "officialUrl": "https://openapi.tossinvest.com/openapi-docs/overview.md",
        "documentVersion": "unversioned",
        "retrievedAt": "2026-07-10T05:06:45Z",
        "httpResponseSha256": (
            "a3d40f129c924fe07123495ca064feab4c97f5cb5f3bc9a368c38cf25e1ded03"
        ),
        "priorObservedHttpResponseSha256": [
            "13b3b7b5915e73dabdece99fb6c86e85e901d4a83ed1d6437f7f0e9f3fdb3081"
        ],
    },
    {
        "sourceId": "TOSS-DOC-004",
        "title": "토스증권 Open API | 토스증권 홈페이지",
        "officialUrl": "https://home.tossinvest.com/ko/open-api",
        "documentVersion": "unversioned",
        "retrievedAt": "2026-07-10T05:07:06Z",
        "httpResponseSha256": (
            "4eb3292ce9d6c996e592998a16f5efb4852630eea51963a510d38a435a548108"
        ),
        "priorObservedHttpResponseSha256": [],
    },
)
REGISTERED_EXTERNAL_SOURCE_IDS = {
    identity["sourceId"] for identity in EXPECTED_SOURCE_IDENTITIES
}
SOURCE_FIELDS = {
    "sourceId",
    "title",
    "publisher",
    "officialUrl",
    "accessedAt",
    "documentVersion",
    "httpResponseSha256",
    "hashScope",
    "evidenceExtraction",
    "evidenceAssetUrl",
    "evidenceAssetSha256",
    "extractedTextSha256",
    "extractionPattern",
    "canonicalization",
    "primarySource",
    "corpusRole",
    "appliedClaims",
    "undocumentedOrNonApplicableClaims",
    "retrievedAt",
    "priorObservedHttpResponseSha256",
    "revisionObservation",
}
EXPECTED_AVAILABILITY_STATUSES = (
    "usable",
    "limited",
    "data_unavailable",
)
EXPECTED_IDENTIFIABILITY_STATUSES = (
    "identifiable",
    "not_identifiable",
)
EXPECTED_GROUP_STATUSES = (
    ("daily_ohlcv", "limited"),
    ("minute_ohlcv", "limited"),
    ("market_sector_rates_fx_vol", "limited"),
    ("shares_and_corporate_actions", "limited"),
    ("attention_and_news", "data_unavailable"),
    ("participant_flow", "limited"),
    ("options_short_and_borrow", "data_unavailable"),
    ("ordered_book_trade_cancel", "data_unavailable"),
)
RAW_CANDLE_COMPONENT_STATUSES = {
    "adjusted_request_option_without_method": "limited",
    "bar_start_ohlc_currency_schema": "limited",
    "candle_session_membership": "data_unavailable",
    "volume_field_without_unit_contract": "limited",
}
EXPECTED_COMPONENT_STATUSES = {
    "daily_ohlcv": RAW_CANDLE_COMPONENT_STATUSES,
    "minute_ohlcv": RAW_CANDLE_COMPONENT_STATUSES,
    "market_sector_rates_fx_vol": {
        "kr_index_bond_fx_price_derived_subset": "limited",
        "us_sector_volatility_canonical_factor_feed": "data_unavailable",
    },
    "shares_and_corporate_actions": {
        "current_shares_snapshot": "limited",
        "point_in_time_shares": "data_unavailable",
        "float_shares": "data_unavailable",
        "corporate_actions": "data_unavailable",
    },
    "attention_and_news": {
        "raw_attention": "data_unavailable",
        "raw_news_exposure": "data_unavailable",
    },
    "participant_flow": {
        "krw_market_aggregate_buy_sell_amounts": "limited",
        "updated_at": "limited",
        "symbol_level_flow": "data_unavailable",
        "final_revision_history": "data_unavailable",
    },
    "options_short_and_borrow": {
        "options": "data_unavailable",
        "short_interest": "data_unavailable",
        "securities_lending": "data_unavailable",
    },
    "ordered_book_trade_cancel": {
        "orderbook_snapshot": "limited",
        "recent_same_day_trades": "limited",
        "ordered_sequence": "data_unavailable",
        "cancel_events": "data_unavailable",
        "aggressor_side": "data_unavailable",
        "historical_depth": "data_unavailable",
    },
}
EXPECTED_IDENTIFIABILITY_IMPLICATIONS = {
    "daily_ohlcv": [
        {"claim": "price_path_or_price_volume_regime", "status": "identifiable"},
        {
            "claim": "human_behavior_psychology_or_intent",
            "status": "not_identifiable",
        },
    ],
    "minute_ohlcv": [
        {"claim": "price_path_or_price_volume_regime", "status": "identifiable"},
        {
            "claim": "human_behavior_psychology_or_intent",
            "status": "not_identifiable",
        },
    ],
    "market_sector_rates_fx_vol": [
        {
            "claim": "documented_kr_price_derived_subset_scope",
            "status": "identifiable",
        },
        {
            "claim": "canonical_cross_market_factor_set",
            "status": "not_identifiable",
        },
    ],
    "shares_and_corporate_actions": [
        {"claim": "current_shares_snapshot", "status": "identifiable"},
        {
            "claim": "point_in_time_float_and_corporate_action_state",
            "status": "not_identifiable",
        },
    ],
    "attention_and_news": [
        {
            "claim": "human_psychology_or_intent_from_attention_or_news",
            "status": "not_identifiable",
        }
    ],
    "participant_flow": [
        {"claim": "market_aggregate_buy_sell_amounts", "status": "identifiable"},
        {
            "claim": "symbol_level_behavior_or_intent",
            "status": "not_identifiable",
        },
    ],
    "options_short_and_borrow": [
        {
            "claim": "options_short_or_borrow_state",
            "status": "not_identifiable",
        }
    ],
    "ordered_book_trade_cancel": [
        {"claim": "current_snapshot_or_recent_trade", "status": "identifiable"},
        {
            "claim": "ordered_sequence_cancel_aggressor_historical_depth",
            "status": "not_identifiable",
        },
    ],
}
GROUP_FIELDS = {
    "inputGroupId",
    "availabilityStatus",
    "providerCandidates",
    "authBoundary",
    "timestampCompleteness",
    "unitCompleteness",
    "revisionPolicy",
    "licenseAndRedistribution",
    "currentAvailability",
    "blockingEffects",
    "usableFor",
    "blockedResearchUses",
    "sourceIds",
    "componentStatuses",
    "identifiabilityImplications",
    "evidenceStatements",
}
EVIDENCE_STATEMENT_FIELDS = {
    "evidenceKind",
    "text",
    "sourceIds",
    "sourceLocation",
    "authorityRefs",
}
DOCUMENT_EVIDENCE_KINDS = {
    "document_fact",
    "document_absence_observation",
}
INTERNAL_AUTHORITY_EVIDENCE_KINDS = {
    "research_inference",
    "operational_control",
}
EVIDENCE_KINDS = DOCUMENT_EVIDENCE_KINDS | INTERNAL_AUTHORITY_EVIDENCE_KINDS
REGISTERED_INTERNAL_AUTHORITIES = {
    "GOAL-RP-001",
    "RQ-002",
    "DC-002",
    "SP-002",
}
DERIVED_CLAIM_OR_OUTPUT_NAMES = {
    "price_volume_regime",
    "price_path_or_price_volume_regime",
    "human_behavior_psychology_or_intent",
}
EXPECTED_DATA_CONTRACT_FIELDS = (
    "providerAndSource",
    "eventTimestamp",
    "publicationTimestamp",
    "clientReceivedAt",
    "exchange",
    "timezone",
    "calendarSessionAvailability",
    "candleMembership",
    "adjustedPrice",
    "nativePrice",
    "priceUnit",
    "volumeUnit",
    "sharesOutstanding",
    "floatShares",
    "corporateActions",
    "missingDataPolicy",
    "haltPolicy",
    "zeroVolumePolicy",
    "revisionPolicy",
    "rawHttpResponseSha256",
    "processedCanonicalDataSha256",
    "license",
    "redistribution",
)
PLACEHOLDER_PATTERN = re.compile(
    r"\b(?:TODO|TBD|FIXME|PLACEHOLDER)\b|<[A-Z][A-Z0-9_-]*>",
    re.IGNORECASE,
)


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, entry in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = entry
    return value


def load_strict_json(path: Path) -> Any:
    return json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=lambda constant: (_ for _ in ()).throw(
            ValueError(f"invalid JSON constant: {constant}")
        ),
    )


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _without_code_ticks(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith("`") and stripped.endswith("`"):
        return stripped[1:-1]
    return stripped


def _parse_unique_status_pairs(
    value: str,
    field_name: str,
) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    observed_keys: set[str] = set()
    for entry in value.split("<br />"):
        key, separator, status = entry.partition("=")
        if not separator or not key or not status or "=" in status:
            raise ValueError(f"invalid {field_name} entry: {entry}")
        if key in observed_keys:
            raise ValueError(f"duplicate {field_name} key: {key}")
        observed_keys.add(key)
        pairs.append((key, status))
    return pairs


def parse_markdown_input_groups(markdown: str) -> dict[str, dict[str, Any]]:
    section = markdown.split("## 입력군 판정\n", maxsplit=1)[1].split(
        "## 근거 projection", maxsplit=1
    )[0]
    header = (
        "| inputGroupId | availabilityStatus | componentStatuses | "
        "identifiabilityImplications | blockingEffects | usableFor | "
        "blockedResearchUses |"
    )
    separator = "| --- | --- | --- | --- | --- | --- | --- |"
    lines = [line for line in section.splitlines() if line.strip()]
    if lines[:2] != [header, separator]:
        raise ValueError("invalid source-matrix input-group table header")

    parsed: dict[str, dict[str, Any]] = {}
    for line in lines[2:]:
        if not line.startswith("| ") or not line.endswith(" |"):
            raise ValueError("unexpected source-matrix input-group table content")
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if (
            len(cells) != 7
            or re.fullmatch(r"`[^`]+`", cells[0]) is None
            or re.fullmatch(r"`[^`]+`", cells[1]) is None
        ):
            raise ValueError("invalid source-matrix input-group row")
        input_group_id = _without_code_ticks(cells[0])
        if input_group_id in parsed:
            raise ValueError(f"duplicate source-matrix input-group row: {input_group_id}")
        component_statuses = _parse_unique_status_pairs(
            cells[2],
            "componentStatuses",
        )
        identifiability_implications = _parse_unique_status_pairs(
            cells[3],
            "identifiabilityImplications",
        )
        parsed[input_group_id] = {
            "availabilityStatus": _without_code_ticks(cells[1]),
            "componentStatuses": dict(component_statuses),
            "identifiabilityImplications": [
                {"claim": claim, "status": status}
                for claim, status in identifiability_implications
            ],
            "blockingEffects": cells[4].split("<br />"),
            "usableFor": cells[5].split("<br />"),
            "blockedResearchUses": cells[6].split("<br />"),
        }
    return parsed


def parse_markdown_bindings(markdown: str) -> dict[str, str]:
    section = markdown.split("## 결박\n", maxsplit=1)[1].split(
        "## Provider use policy", maxsplit=1
    )[0]
    label_to_field = {
        "Goal": "goalId",
        "Program": "programId",
        "ResearchQuestion": "researchQuestionId",
        "DatasetContract": "datasetContractId",
        "Study slot": "studySlot",
        "StudyProtocol": "protocolId",
    }
    expected_auxiliary_bullets = {
        "- 구조화 SSOT: [source-matrix.json](source-matrix.json)",
        "- 공식 문서 근거: [official-source-register.json]"
        "(../../dataset-contracts/DC-002-program-data/official-source-register.json)",
        "- 문서 접근일: `2026-07-10`",
    }
    parsed: dict[str, str] = {}
    observed_auxiliary_bullets: set[str] = set()
    observed_prose: set[str] = set()
    for line in section.splitlines():
        if not line.strip():
            continue
        if line in EXPECTED_MARKDOWN_BINDING_PROSE:
            if line in observed_prose:
                raise ValueError("duplicate source-matrix binding prose")
            observed_prose.add(line)
            continue
        if not line.startswith("- "):
            raise ValueError("unexpected source-matrix binding content")
        if line in expected_auxiliary_bullets:
            if line in observed_auxiliary_bullets:
                raise ValueError(f"duplicate source-matrix auxiliary binding: {line}")
            observed_auxiliary_bullets.add(line)
            continue
        match = re.fullmatch(r"- ([^:]+): `([^`]+)`", line)
        if match is None:
            raise ValueError("unexpected source-matrix binding bullet")
        label, identifier = match.groups()
        if label not in label_to_field:
            raise ValueError(f"unexpected source-matrix binding label: {label}")
        field = label_to_field[label]
        if field in parsed:
            raise ValueError(f"duplicate source-matrix binding: {field}")
        parsed[field] = identifier
    if observed_auxiliary_bullets != expected_auxiliary_bullets:
        raise ValueError("missing source-matrix auxiliary binding")
    if observed_prose != EXPECTED_MARKDOWN_BINDING_PROSE:
        raise ValueError("missing source-matrix binding prose")
    return parsed


def parse_markdown_provider_policy(markdown: str) -> dict[str, Any]:
    section = markdown.split("## Provider use policy\n", maxsplit=1)[1].split(
        "## 입력군 판정", maxsplit=1
    )[0]
    expected_fields = (
        "policyId",
        "provider",
        "source",
        "documentedPurpose",
        "documentedExternalDistributionRestriction",
        "commercialUse",
        "localInternalResearch",
        "localRetention",
        "derivedPublication",
        "operationalControl",
        "legalConclusion",
    )
    code_value_fields = set(expected_fields) - {
        "documentedExternalDistributionRestriction"
    }
    expected_prose = (
        "FAQ exact text를 raw market data의 법적 허용·금지 결론으로 확대하지 "
        "않는다. live collection은 credential 회전과 provider clarification 전까지 "
        "`blocked_pending_rotated_credentials_and_provider_retention_clarification`이다."
    )
    parsed: dict[str, Any] = {}
    observed_fields: list[str] = []
    observed_prose = False
    for line in section.splitlines():
        if not line.strip():
            continue
        if line == expected_prose:
            if observed_prose:
                raise ValueError("duplicate provider policy prose")
            observed_prose = True
            continue
        if not line.startswith("- "):
            raise ValueError("unexpected provider policy content")
        field, value = line[2:].split(": ", maxsplit=1)
        if field not in expected_fields:
            raise ValueError(f"unexpected provider policy field: {field}")
        if field in observed_fields:
            raise ValueError(f"duplicate provider policy field: {field}")
        if field in code_value_fields:
            if re.fullmatch(r"`[^`]+`", value) is None:
                raise ValueError(f"invalid provider policy value: {field}")
        elif value.startswith("`") or value.endswith("`"):
            raise ValueError(f"invalid provider policy value: {field}")
        observed_fields.append(field)
        normalized = _without_code_ticks(value)
        if field == "source":
            target_field = "sourceIds"
            parsed_value: Any = [normalized]
        elif field == "legalConclusion":
            target_field = field
            parsed_value = None if normalized == "null" else normalized
        else:
            target_field = field
            parsed_value = normalized
        parsed[target_field] = parsed_value
    if tuple(observed_fields) != expected_fields or not observed_prose:
        raise ValueError("incomplete provider policy projection")
    return parsed


def parse_markdown_evidence(
    markdown: str,
) -> dict[str, list[dict[str, Any]]]:
    section = markdown.split("## 근거 projection\n", maxsplit=1)[1].split(
        "## 공통 운영통제", maxsplit=1
    )[0]
    parsed: dict[str, list[dict[str, Any]]] = {}
    input_group_id: str | None = None
    pattern = re.compile(
        r"^- `(?P<kind>[^`]+)` — (?P<text>.*?) — source: "
        r"(?P<sources>.*?) — authority: (?P<authorities>.*?) — location: "
        r"(?P<location>.*)$"
    )
    heading_pattern = re.compile(r"^### `(?P<input_group_id>[^`]+)`$")
    for line in section.splitlines():
        if not line.strip():
            continue
        heading_match = heading_pattern.fullmatch(line)
        if heading_match is not None:
            input_group_id = heading_match.group("input_group_id")
            if input_group_id in parsed:
                raise ValueError(
                    f"duplicate evidence input-group heading: {input_group_id}"
                )
            parsed[input_group_id] = []
            continue
        if input_group_id is None:
            raise ValueError("evidence row appears before an input-group heading")
        match = pattern.fullmatch(line)
        if match is None:
            raise ValueError("unexpected source-matrix evidence content")
        source_token = match.group("sources")
        authority_token = match.group("authorities")
        parsed[input_group_id].append(
            {
                "evidenceKind": match.group("kind"),
                "text": match.group("text"),
                "sourceIds": (
                    [] if source_token == "none" else source_token.split(", ")
                ),
                "authorityRefs": (
                    []
                    if authority_token == "none"
                    else authority_token.split(", ")
                ),
                "sourceLocation": match.group("location"),
            }
        )
    return parsed


class DataLineageContractTest(unittest.TestCase):
    def _task_artifact_paths(self) -> tuple[Path, ...]:
        return (
            QUESTION_DIRECTORY / "object.json",
            QUESTION_DIRECTORY / "question.md",
            DATASET_DIRECTORY / "object.json",
            DATASET_DIRECTORY / "data-contract.md",
            DATASET_DIRECTORY / "official-source-register.json",
            PROTOCOL_DIRECTORY / "object.json",
            PROTOCOL_DIRECTORY / "protocol.md",
            PROTOCOL_DIRECTORY / "protocol.sha256",
            SOURCE_MATRIX_PATH,
            SOURCE_MATRIX_MARKDOWN_PATH,
            TRIAL_LEDGER_PATH,
        )

    def _assert_task_artifacts_exist(self) -> None:
        missing = [
            path.relative_to(REPOSITORY_ROOT).as_posix()
            for path in self._task_artifact_paths()
            if not path.is_file()
        ]
        self.assertEqual(missing, [], f"missing ST-DAT-001 artifacts: {missing}")

    def _assert_nonempty_string(self, value: Any) -> None:
        self.assertIsInstance(value, str)
        self.assertTrue(value.strip())

    def _assert_nonempty_string_list(self, value: Any) -> None:
        self.assertIsInstance(value, list)
        self.assertTrue(value)
        for entry in value:
            self._assert_nonempty_string(entry)
        self.assertEqual(len(value), len(set(value)))

    def _assert_unique_string_list(self, value: Any) -> None:
        self.assertIsInstance(value, list)
        for entry in value:
            self._assert_nonempty_string(entry)
        self.assertEqual(len(value), len(set(value)))

    def _assert_task6_descriptor_text(
        self,
        descriptor: dict[str, Any],
        identifier: str,
    ) -> None:
        self.assertEqual(
            {field: descriptor[field] for field in ("title", "purpose")},
            EXPECTED_TASK6_DESCRIPTOR_TEXT[identifier],
        )

    def _assert_evidence_authority_contract(
        self,
        statement: dict[str, Any],
        group_source_ids: set[str],
    ) -> None:
        self.assertEqual(set(statement), EVIDENCE_STATEMENT_FIELDS)
        self.assertIn(statement["evidenceKind"], EVIDENCE_KINDS)
        self._assert_nonempty_string(statement["text"])
        self._assert_nonempty_string(statement["sourceLocation"])
        self._assert_unique_string_list(statement["sourceIds"])
        self._assert_unique_string_list(statement["authorityRefs"])
        self.assertTrue(
            set(statement["sourceIds"])
            <= REGISTERED_EXTERNAL_SOURCE_IDS & group_source_ids
        )
        self.assertTrue(
            set(statement["authorityRefs"])
            <= REGISTERED_INTERNAL_AUTHORITIES
        )
        if statement["evidenceKind"] in DOCUMENT_EVIDENCE_KINDS:
            self.assertTrue(statement["sourceIds"])
        elif statement["evidenceKind"] == "research_inference":
            self.assertTrue(statement["authorityRefs"])
        elif statement["evidenceKind"] == "operational_control":
            self.assertEqual(statement["sourceIds"], [])
            self.assertTrue(statement["authorityRefs"])

    def test_requires_every_planned_artifact(self) -> None:
        self._assert_task_artifacts_exist()

    def test_descriptors_catalog_and_program_artifacts_are_bound_exactly(self) -> None:
        self._assert_task_artifacts_exist()
        expected_descriptors = {
            "RQ-002": {
                "path": QUESTION_DIRECTORY / "object.json",
                "type": "ResearchQuestion",
                "state": "completed",
                "dependsOn": ["RP-001"],
                "artifacts": [
                    "research/meta-research/objects/research-questions/"
                    "RQ-002-data-lineage/question.md"
                ],
            },
            "DC-002": {
                "path": DATASET_DIRECTORY / "object.json",
                "type": "DatasetContract",
                "state": "completed",
                "dependsOn": ["RQ-002"],
                "artifacts": [
                    "research/meta-research/objects/dataset-contracts/"
                    "DC-002-program-data/data-contract.md",
                    "research/meta-research/objects/dataset-contracts/"
                    "DC-002-program-data/official-source-register.json",
                ],
            },
            "SP-002": {
                "path": PROTOCOL_DIRECTORY / "object.json",
                "type": "StudyProtocol",
                "state": "preregistered",
                "dependsOn": ["DC-002", "RQ-002"],
                "artifacts": [
                    "research/meta-research/objects/study-protocols/"
                    "SP-002-data-lineage-audit/protocol.md",
                    "research/meta-research/objects/study-protocols/"
                    "SP-002-data-lineage-audit/protocol.sha256",
                    "research/rp-001/trials/ST-DAT-001.json",
                ],
            },
        }
        for identifier, expected in expected_descriptors.items():
            with self.subTest(identifier=identifier):
                descriptor = load_strict_json(expected["path"])
                self.assertEqual(
                    set(descriptor),
                    {
                        "schemaVersion",
                        "id",
                        "type",
                        "title",
                        "version",
                        "lifecycleState",
                        "evidenceLevel",
                        "purpose",
                        "dependsOn",
                        "artifacts",
                    },
                )
                self.assertEqual(descriptor["schemaVersion"], "research-object.v1")
                self.assertEqual(descriptor["id"], identifier)
                self.assertEqual(descriptor["type"], expected["type"])
                self.assertEqual(descriptor["version"], "1.0.1")
                self.assertEqual(descriptor["lifecycleState"], expected["state"])
                self.assertEqual(descriptor["evidenceLevel"], "conceptual")
                self._assert_task6_descriptor_text(descriptor, identifier)
                self.assertEqual(descriptor["dependsOn"], expected["dependsOn"])
                self.assertEqual(descriptor["artifacts"], expected["artifacts"])

        mutated_rq_descriptor = load_strict_json(
            QUESTION_DIRECTORY / "object.json"
        )
        mutated_rq_descriptor["purpose"] = "모든 Gate 실패를 무시한다"
        with self.assertRaises(AssertionError):
            self._assert_task6_descriptor_text(mutated_rq_descriptor, "RQ-002")

        expected_catalog_paths = [
            "research/meta-research/objects/dataset-contracts/"
            "DC-001-ontology-evidence/object.json",
            "research/meta-research/objects/dataset-contracts/"
            "DC-002-program-data/object.json",
            "research/meta-research/objects/dataset-contracts/"
            "DC-003-behavior-regime/object.json",
            "research/meta-research/objects/dataset-contracts/"
            "DC-004-relative-value/object.json",
            "research/meta-research/objects/dataset-contracts/"
            "DC-005-microstructure/object.json",
            "research/meta-research/objects/dataset-contracts/"
            "DC-006-execution-cost/object.json",
            "research/meta-research/objects/dataset-contracts/"
            "DC-007-tail-risk/object.json",
            "research/meta-research/objects/dataset-contracts/"
            "DC-008-synthesis-inputs/object.json",
            "research/meta-research/objects/decision-records/"
            "DR-001-rb001-boundary/object.json",
            "research/meta-research/objects/evidence-bundles/"
            "EB-001-rb001-integrity-audit/object.json",
            "research/meta-research/objects/model-candidates/"
            "MC-001-bayesian-hsmm-competing-risks/object.json",
            "research/meta-research/objects/meta-studies/"
            "MS-001-research-program-governance/object.json",
            "research/meta-research/objects/baselines/"
            "RB-001-v1-4-indicator-validation/object.json",
            "research/meta-research/objects/programs/"
            "RP-001-quantitative-market-behavior/object.json",
            "research/meta-research/objects/research-questions/"
            "RQ-001-market-state-identifiability/object.json",
            "research/meta-research/objects/research-questions/"
            "RQ-002-data-lineage/object.json",
            "research/meta-research/objects/research-questions/"
            "RQ-003-behavior-regime/object.json",
            "research/meta-research/objects/research-questions/"
            "RQ-004-relative-value/object.json",
            "research/meta-research/objects/research-questions/"
            "RQ-005-microstructure/object.json",
            "research/meta-research/objects/research-questions/"
            "RQ-006-execution-cost/object.json",
            "research/meta-research/objects/research-questions/"
            "RQ-007-tail-risk/object.json",
            "research/meta-research/objects/research-questions/"
            "RQ-008-synthesis/object.json",
            "research/meta-research/objects/study-protocols/"
            "SP-001-market-state-ontology/object.json",
            "research/meta-research/objects/study-protocols/"
            "SP-002-data-lineage-audit/object.json",
            "research/meta-research/objects/study-protocols/"
            "SP-003-behavior-regime/object.json",
            "research/meta-research/objects/study-protocols/"
            "SP-004-relative-value/object.json",
            "research/meta-research/objects/study-protocols/"
            "SP-005-microstructure/object.json",
            "research/meta-research/objects/study-protocols/"
            "SP-006-execution-cost/object.json",
            "research/meta-research/objects/study-protocols/"
            "SP-007-tail-risk/object.json",
            "research/meta-research/objects/study-protocols/"
            "SP-008-synthesis/object.json",
        ]
        catalog = load_strict_json(CATALOG_PATH)
        self.assertEqual(
            [entry["descriptor"] for entry in catalog["objects"]],
            expected_catalog_paths,
        )

        program_descriptor = load_strict_json(PROGRAM_DIRECTORY / "object.json")
        program_prefix = (
            "research/meta-research/objects/programs/"
            "RP-001-quantitative-market-behavior/"
        )
        self.assertEqual(program_descriptor["dependsOn"], ["MC-001", "MS-001", "RB-001"])
        self.assertEqual(
            program_descriptor["artifacts"],
            [
                f"{program_prefix}README.md",
                f"{program_prefix}candidate-registry.json",
                f"{program_prefix}goal-v1.0.md",
                f"{program_prefix}integration-contract.md",
                f"{program_prefix}question-map.md",
                f"{program_prefix}requirements.json",
                f"{program_prefix}seen-data-register.json",
                f"{program_prefix}source-matrix.json",
                f"{program_prefix}source-matrix.md",
                f"{program_prefix}state-ontology.json",
                f"{program_prefix}state-ontology.md",
                f"{program_prefix}study-contracts.json",
                f"{program_prefix}study-portfolio.md",
                f"{program_prefix}study-registry.json",
                f"{program_prefix}traceability.json",
            ],
        )

        descriptors = [
            load_strict_json(REPOSITORY_ROOT / path) for path in expected_catalog_paths
        ]
        self.assertEqual([descriptor["id"] for descriptor in descriptors], [
            "DC-001",
            "DC-002",
            "DC-003",
            "DC-004",
            "DC-005",
            "DC-006",
            "DC-007",
            "DC-008",
            "DR-001",
            "EB-001",
            "MC-001",
            "MS-001",
            "RB-001",
            "RP-001",
            "RQ-001",
            "RQ-002",
            "RQ-003",
            "RQ-004",
            "RQ-005",
            "RQ-006",
            "RQ-007",
            "RQ-008",
            "SP-001",
            "SP-002",
            "SP-003",
            "SP-004",
            "SP-005",
            "SP-006",
            "SP-007",
            "SP-008",
        ])
        self.assertEqual(len(descriptors), 30)
        self.assertEqual(sum(len(value["dependsOn"]) for value in descriptors), 46)
        self.assertEqual(sum(len(value["artifacts"]) for value in descriptors), 70)

    def test_question_and_data_contract_define_complete_audit_scope(self) -> None:
        self._assert_task_artifacts_exist()
        question = (QUESTION_DIRECTORY / "question.md").read_text(encoding="utf-8")
        self.assertIn(EXPECTED_QUESTION, question)
        for required_text in (
            "availability: `usable/limited/data_unavailable`",
            "identifiability: `identifiable/not_identifiable`",
            "horizon: `N/A`",
            "contemporaneous data-contract audit",
            "기술 문서의 가용성",
            "수집·이용 권한",
            "별도로 판정",
        ):
            self.assertIn(required_text, question)

        contract = (DATASET_DIRECTORY / "data-contract.md").read_text(
            encoding="utf-8"
        )
        for field in EXPECTED_DATA_CONTRACT_FIELDS:
            self.assertIn(f"`{field}`", contract)
        for required_text in (
            "provider/source",
            "event timestamp",
            "publication timestamp",
            "clientReceivedAt",
            "calendar session availability",
            "candle membership",
            "adjusted/native",
            "발행주식수",
            "유통주식수",
            "기업행동",
            "결측·거래정지·0거래량",
            "revision",
            "raw HTTP response",
            "processed canonical data",
            "license/redistribution",
            "undocumented",
            "0 또는 neutral로 대체하지 않는다",
            "reweight 또는 renormalize하지 않는다",
            "예시를 계약으로 승격하지 않는다",
        ):
            self.assertIn(required_text, contract)
        self.assertEqual(
            hashlib.sha256((QUESTION_DIRECTORY / "question.md").read_bytes()).hexdigest(),
            EXPECTED_QUESTION_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(
                (DATASET_DIRECTORY / "data-contract.md").read_bytes()
            ).hexdigest(),
            EXPECTED_DATA_CONTRACT_SHA256,
        )

    def _assert_source_register_contract(self, register: dict[str, Any]) -> None:
        self.assertEqual(set(register), {"schemaVersion", "sources"})
        self.assertEqual(
            register["schemaVersion"], "rp001-data-lineage-source-register.v1"
        )
        sources = register["sources"]
        self.assertIsInstance(sources, list)
        self.assertEqual(len(sources), 4)
        for source, expected in zip(sources, EXPECTED_SOURCE_IDENTITIES, strict=True):
            self.assertIsInstance(source, dict)
            self.assertEqual(set(source), SOURCE_FIELDS)
            for field in (
                "sourceId",
                "title",
                "publisher",
                "officialUrl",
                "accessedAt",
                "documentVersion",
                "httpResponseSha256",
                "hashScope",
                "evidenceExtraction",
                "corpusRole",
                "retrievedAt",
                "revisionObservation",
            ):
                self._assert_nonempty_string(source[field])
            self._assert_nonempty_string_list(source["appliedClaims"])
            self._assert_nonempty_string_list(
                source["undocumentedOrNonApplicableClaims"]
            )
            self.assertEqual(source["sourceId"], expected["sourceId"])
            self.assertEqual(source["title"], expected["title"])
            self.assertEqual(source["officialUrl"], expected["officialUrl"])
            self.assertEqual(source["documentVersion"], expected["documentVersion"])
            self.assertEqual(source["retrievedAt"], expected["retrievedAt"])
            self.assertEqual(
                source["httpResponseSha256"], expected["httpResponseSha256"]
            )
            self.assertRegex(source["httpResponseSha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(
                source["retrievedAt"],
                r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})$",
            )
            prior_hashes = source["priorObservedHttpResponseSha256"]
            self.assertIsInstance(prior_hashes, list)
            self.assertEqual(
                prior_hashes, expected["priorObservedHttpResponseSha256"]
            )
            self.assertEqual(len(prior_hashes), len(set(prior_hashes)))
            self.assertNotIn(source["httpResponseSha256"], prior_hashes)
            for prior_hash in prior_hashes:
                self.assertRegex(prior_hash, r"^[0-9a-f]{64}$")
            self.assertEqual(source["publisher"], "토스증권")
            self.assertEqual(source["accessedAt"], "2026-07-10")
            self.assertIs(source["primarySource"], True)
            self.assertEqual(source["corpusRole"], "design_seen_before_freeze")

        faq_source = sources[3]
        self.assertEqual(
            faq_source["hashScope"],
            "initial_http_response_bytes_not_rendered_dom",
        )
        self.assertEqual(
            faq_source["evidenceExtraction"],
            "official_nextjs_asset_faq_text_2026-07-10",
        )
        self.assertEqual(
            faq_source["evidenceAssetUrl"],
            "https://home.tossinvest.com/assets/_next/static/chunks/"
            "1a735d1f-24ac5d990ea88e57.js",
        )
        self.assertEqual(
            faq_source["evidenceAssetSha256"],
            "1b69d124058f50cfb97231f1fceb14fe40731a94d43e37d34487afecf728bb79",
        )
        for source in sources[:3]:
            self.assertIsNone(source["evidenceAssetUrl"])
            self.assertIsNone(source["evidenceAssetSha256"])
            self.assertIsNone(source["extractedTextSha256"])
            self.assertIsNone(source["extractionPattern"])
            self.assertIsNone(source["canonicalization"])
        for source in sources:
            self.assertEqual(
                source["evidenceAssetUrl"] is None,
                source["evidenceAssetSha256"] is None,
            )
        self.assertIn("byte_drift_observed", sources[1]["revisionObservation"])
        self.assertIn("info.version=1.2.2", sources[1]["revisionObservation"])
        self.assertIn("byte_drift_observed", sources[2]["revisionObservation"])
        self.assertIn("latest", sources[2]["revisionObservation"])
        self.assertIn("two_gets_stable", sources[0]["revisionObservation"])
        self.assertIn("two_gets_stable", sources[3]["revisionObservation"])
        faq_extracted_text = (
            "API는 본인의 매매 목적으로만 이용할 수 있어요. 외부 배포나 상업적 "
            "용도로는 사용할 수 없으며, 자세한 내용은 이용약관을 확인해 주세요."
        )
        self.assertEqual(faq_source["extractionPattern"], faq_extracted_text)
        self.assertEqual(
            faq_source["extractedTextSha256"],
            "75ac2ac653de6a99ee1095542814aa03133b1c6e5d011d160c462b86b835909f",
        )
        self.assertEqual(
            faq_source["canonicalization"],
            "utf8_original_bytes_plus_single_lf_no_unicode_normalization",
        )
        self.assertEqual(
            hashlib.sha256(f"{faq_extracted_text}\n".encode("utf-8")).hexdigest(),
            faq_source["extractedTextSha256"],
        )

        claims = " ".join(
            claim for source in sources for claim in source["appliedClaims"]
        )
        for required_fact in (
            "1.2.2",
            "OAuth client_credentials",
            "Bearer",
            "/api/v1/candles",
            "1m",
            "1d",
            "1..200",
            "default 100",
            "inclusive before",
            "nextBefore",
            "adjusted default true",
            "bar-start",
            "OHLC",
            "volume",
            "currency",
            "본인의 매매 목적",
            "외부 배포와 상업적 이용 금지",
            "REST only",
            "documented WebSocket endpoint 없음",
            "API credential 제3자 노출 금지",
            "호출량·기능 변경",
            "지연·오류",
        ):
            self.assertIn(required_fact, claims)

        undocumented = " ".join(
            claim
            for source in sources
            for claim in source["undocumentedOrNonApplicableClaims"]
        )
        for required_gap in (
            "timezone",
            "session/venue",
            "volume unit",
            "adjustment method",
            "corporate actions",
            "revision",
            "retention",
            "publication timestamp",
            "received timestamp",
            "local retention",
            "derived-publication",
        ):
            self.assertIn(required_gap, undocumented)

    def test_official_source_register_is_exact_canonical_document_evidence(self) -> None:
        self._assert_task_artifacts_exist()
        register_path = DATASET_DIRECTORY / "official-source-register.json"
        register = load_strict_json(register_path)
        self._assert_source_register_contract(register)
        self.assertEqual(register_path.read_bytes(), canonical_json_bytes(register))
        self.assertEqual(
            hashlib.sha256(register_path.read_bytes()).hexdigest(),
            EXPECTED_SOURCE_REGISTER_SHA256,
        )

    def test_rejects_source_provenance_timestamp_revision_and_asset_mutations(
        self,
    ) -> None:
        self._assert_task_artifacts_exist()
        register = load_strict_json(DATASET_DIRECTORY / "official-source-register.json")
        mutations: tuple[
            tuple[str, Callable[[dict[str, Any]], None]], ...
        ] = (
            (
                "date_without_time",
                lambda value: value["sources"][0].__setitem__(
                    "retrievedAt", "2026-07-10"
                ),
            ),
            (
                "current_hash_repeated_as_prior",
                lambda value: value["sources"][1][
                    "priorObservedHttpResponseSha256"
                ].append(value["sources"][1]["httpResponseSha256"]),
            ),
            (
                "missing_asset_pair",
                lambda value: value["sources"][3].__setitem__(
                    "evidenceAssetSha256", None
                ),
            ),
            (
                "empty_revision_observation",
                lambda value: value["sources"][2].__setitem__(
                    "revisionObservation", ""
                ),
            ),
            (
                "unbound_extracted_text",
                lambda value: value["sources"][3].__setitem__(
                    "extractionPattern", "FAQ text changed"
                ),
            ),
        )
        for case, mutate in mutations:
            with self.subTest(case=case):
                mutated = copy.deepcopy(register)
                mutate(mutated)
                with self.assertRaises(AssertionError):
                    self._assert_source_register_contract(mutated)

    def _assert_matrix_contract(self, matrix: dict[str, Any]) -> None:
        self.assertEqual(
            set(matrix),
            {
                "schemaVersion",
                "goalId",
                "programId",
                "researchQuestionId",
                "datasetContractId",
                "studySlot",
                "protocolId",
                "protocolSha256",
                "sourceRegisterPath",
                "accessedAt",
                "availabilityStatuses",
                "identifiabilityStatuses",
                "credentialBoundary",
                "globalRules",
                "dataContractFields",
                "providerUsePolicies",
                "inputGroups",
            },
        )
        expected_bindings = {
            "schemaVersion": "rp001-source-matrix.v1",
            "goalId": "GOAL-RP-001",
            "programId": "RP-001",
            "researchQuestionId": "RQ-002",
            "datasetContractId": "DC-002",
            "studySlot": "ST-DAT-001",
            "protocolId": "SP-002",
            "sourceRegisterPath": (
                "research/meta-research/objects/dataset-contracts/"
                "DC-002-program-data/official-source-register.json"
            ),
            "accessedAt": "2026-07-10",
        }
        for field, expected in expected_bindings.items():
            self.assertEqual(matrix[field], expected)
        self.assertRegex(matrix["protocolSha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(
            matrix["availabilityStatuses"], list(EXPECTED_AVAILABILITY_STATUSES)
        )
        self.assertEqual(
            matrix["identifiabilityStatuses"],
            list(EXPECTED_IDENTIFIABILITY_STATUSES),
        )
        self.assertEqual(
            matrix["dataContractFields"], list(EXPECTED_DATA_CONTRACT_FIELDS)
        )

        self.assertEqual(
            matrix["credentialBoundary"],
            EXPECTED_CREDENTIAL_BOUNDARY,
        )
        self.assertEqual(
            matrix["globalRules"],
            {
                "missingObservationPolicy": (
                    "reject_no_zero_or_neutral_imputation"
                ),
                "missingDirectInputHandling": (
                    "block_no_reweight_or_renormalize"
                ),
                "rawProcessedSeparation": "required_separate_artifacts_and_hashes",
                "timestampCompleteness": (
                    "event_publication_client_received_timestamps_required"
                ),
                "licenseGate": "noncompensatory",
                "unknownDocumentationPolicy": (
                    "undocumented_never_infer_or_promote_examples"
                ),
                "documentationAuthorizationSeparation": "required",
                "providerRightsDisposition": (
                    "blocked_pending_provider_clarification"
                ),
                "documentationRevisionRisk": (
                    "noncompensatory_exact_response_hash_and_retrieved_at_required"
                ),
                "latestDocumentationVersionPolicy": (
                    "latest_and_info_version_are_not_immutable"
                ),
            },
        )
        self.assertEqual(
            matrix["providerUsePolicies"],
            [
                {
                    "policyId": "TOSS-POLICY-001",
                    "provider": "토스증권",
                    "sourceIds": ["TOSS-DOC-004"],
                    "documentedPurpose": "personal_trading_only",
                    "documentedExternalDistributionRestriction": (
                        "API는 본인의 매매 목적으로만 이용할 수 있어요. 외부 배포나 "
                        "상업적 용도로는 사용할 수 없으며, 자세한 내용은 이용약관을 "
                        "확인해 주세요."
                    ),
                    "commercialUse": "prohibited_by_faq",
                    "localInternalResearch": "not_documented",
                    "localRetention": "not_documented",
                    "derivedPublication": "not_documented",
                    "operationalControl": "blocked_pending_provider_clarification",
                    "legalConclusion": None,
                }
            ],
        )

        groups = matrix["inputGroups"]
        self.assertIsInstance(groups, list)
        self.assertEqual(
            [
                (group["inputGroupId"], group["availabilityStatus"])
                for group in groups
            ],
            list(EXPECTED_GROUP_STATUSES),
        )
        observed_evidence_kinds: set[str] = set()
        for group in groups:
            self.assertIsInstance(group, dict)
            self.assertEqual(set(group), GROUP_FIELDS)
            for field in (
                "inputGroupId",
                "availabilityStatus",
                "authBoundary",
                "timestampCompleteness",
                "unitCompleteness",
                "revisionPolicy",
                "licenseAndRedistribution",
                "currentAvailability",
            ):
                self._assert_nonempty_string(group[field])
            for field in (
                "providerCandidates",
                "blockingEffects",
                "usableFor",
                "blockedResearchUses",
                "sourceIds",
            ):
                self._assert_nonempty_string_list(group[field])
            self.assertTrue(
                set(group["sourceIds"]) <= REGISTERED_EXTERNAL_SOURCE_IDS
            )
            component_statuses = group["componentStatuses"]
            self.assertIsInstance(component_statuses, dict)
            self.assertTrue(component_statuses)
            self.assertEqual(
                component_statuses,
                EXPECTED_COMPONENT_STATUSES[group["inputGroupId"]],
            )
            for component, status in component_statuses.items():
                self._assert_nonempty_string(component)
                self.assertIn(status, EXPECTED_AVAILABILITY_STATUSES)

            implications = group["identifiabilityImplications"]
            self.assertIsInstance(implications, list)
            self.assertEqual(
                implications,
                EXPECTED_IDENTIFIABILITY_IMPLICATIONS[group["inputGroupId"]],
            )
            for implication in implications:
                self.assertEqual(set(implication), {"claim", "status"})
                self._assert_nonempty_string(implication["claim"])
                self.assertIn(
                    implication["status"], EXPECTED_IDENTIFIABILITY_STATUSES
                )

            self.assertEqual(group["licenseAndRedistribution"], "TOSS-POLICY-001")
            self.assertIn(
                "clientReceivedAt=not_applicable_no_collection",
                group["timestampCompleteness"],
            )
            self.assertIn("future collector-generated", group["timestampCompleteness"])

            evidence_statements = group["evidenceStatements"]
            self.assertIsInstance(evidence_statements, list)
            self.assertTrue(evidence_statements)
            for statement in evidence_statements:
                self.assertIsInstance(statement, dict)
                self._assert_evidence_authority_contract(
                    statement,
                    set(group["sourceIds"]),
                )
                observed_evidence_kinds.add(statement["evidenceKind"])
                if statement["evidenceKind"] == "document_absence_observation":
                    self.assertIn(
                        "retrievedAt에 확인한 public v1.2.2 scope에서",
                        statement["text"],
                    )
                    self.assertIn("documented", statement["text"])
                self.assertNotIn("토스에 없다", statement["text"])

        self.assertEqual(observed_evidence_kinds, EVIDENCE_KINDS)

        group_by_id = {group["inputGroupId"]: group for group in groups}
        daily = " ".join(group_by_id["daily_ohlcv"]["usableFor"])
        daily_forbidden = " ".join(
            group_by_id["daily_ohlcv"]["blockedResearchUses"]
        )
        minute = " ".join(group_by_id["minute_ohlcv"]["usableFor"])
        minute_forbidden = " ".join(
            group_by_id["minute_ohlcv"]["blockedResearchUses"]
        )
        self.assertIn("adjusted 가격 경로", daily)
        self.assertIn("adjusted 가격 경로", minute)
        self.assertIn("price_volume_regime", daily)
        self.assertIn("price_volume_regime", minute)
        for forbidden in (
            "human_behavior_psychology_or_intent_inference",
            "미시구조",
            "체결",
        ):
            self.assertIn(forbidden, daily_forbidden)
            self.assertIn(forbidden, minute_forbidden)

        factors = group_by_id["market_sector_rates_fx_vol"]
        self.assertIn("한국 지수·채권·환율 일부", " ".join(factors["usableFor"]))
        self.assertIn(
            "미국·업종·변동성", " ".join(factors["blockedResearchUses"])
        )

        shares = group_by_id["shares_and_corporate_actions"]
        self.assertIn("현재 발행주식수", " ".join(shares["usableFor"]))
        for forbidden in ("유통주식수", "시점 t", "기업행동"):
            self.assertIn(forbidden, " ".join(shares["blockedResearchUses"]))

        flow = group_by_id["participant_flow"]
        self.assertIn("KOSPI/KOSDAQ 시장 집계", " ".join(flow["usableFor"]))
        self.assertIn("종목", " ".join(flow["blockedResearchUses"]))
        self.assertIn("KRW integer", flow["unitCompleteness"])
        self.assertIn("updatedAt", flow["timestampCompleteness"])
        self.assertIn("당일 잠정", flow["revisionPolicy"])

        attention = group_by_id["attention_and_news"]
        self.assertIn(
            "raw availability의 data_unavailable과 인간 심리·의도 implication의 "
            "not_identifiable은 서로 다른 판정",
            " ".join(attention["blockingEffects"]),
        )

        ordered = group_by_id["ordered_book_trade_cancel"]
        self.assertIn("호가 snapshot", ordered["currentAvailability"])
        self.assertIn("당일 최근 체결", ordered["currentAvailability"])
        ordered_blocking = " ".join(ordered["blockingEffects"])
        for missing in ("순서보존", "취소", "aggressor", "historical depth"):
            self.assertIn(missing, ordered_blocking)
        ordered_forbidden = " ".join(ordered["blockedResearchUses"])
        self.assertIn("ST-MIC-001", ordered_forbidden)
        self.assertIn("ST-EXE-001", ordered_forbidden)
        self.assertIn("canonical OpenAPI+overview", ordered_blocking)
        self.assertIn("REST only", ordered_blocking)
        self.assertIn("documented WebSocket endpoint 없음", ordered_blocking)

    def test_source_matrix_is_canonical_complete_and_security_bounded(self) -> None:
        self._assert_task_artifacts_exist()
        matrix = load_strict_json(SOURCE_MATRIX_PATH)
        self._assert_matrix_contract(matrix)
        self.assertEqual(SOURCE_MATRIX_PATH.read_bytes(), canonical_json_bytes(matrix))
        self.assertEqual(
            hashlib.sha256(SOURCE_MATRIX_PATH.read_bytes()).hexdigest(),
            EXPECTED_SOURCE_MATRIX_SHA256,
        )

    def test_candle_components_are_raw_inputs_and_claim_axis_stays_separate(
        self,
    ) -> None:
        self._assert_task_artifacts_exist()
        matrix = load_strict_json(SOURCE_MATRIX_PATH)
        group_by_id = {
            group["inputGroupId"]: group for group in matrix["inputGroups"]
        }
        for input_group_id in ("daily_ohlcv", "minute_ohlcv"):
            with self.subTest(input_group_id=input_group_id):
                components = group_by_id[input_group_id]["componentStatuses"]
                self.assertEqual(components, RAW_CANDLE_COMPONENT_STATUSES)
                self.assertTrue(
                    set(components).isdisjoint(DERIVED_CLAIM_OR_OUTPUT_NAMES)
                )

        for path in (
            QUESTION_DIRECTORY / "question.md",
            DATASET_DIRECTORY / "data-contract.md",
            PROTOCOL_DIRECTORY / "protocol.md",
        ):
            with self.subTest(path=path.relative_to(REPOSITORY_ROOT).as_posix()):
                source = path.read_text(encoding="utf-8")
                self.assertIn(
                    "raw OHLCV schema availability와 derived claim identifiability를 "
                    "분리한다",
                    source,
                )
                self.assertNotIn(
                    "`price_volume_regime`은 limited availability",
                    source,
                )
        self.assertNotIn(
            "price_volume_regime=limited",
            SOURCE_MATRIX_MARKDOWN_PATH.read_text(encoding="utf-8"),
        )

    def _assert_credential_provenance(self, matrix: dict[str, Any]) -> None:
        self.assertEqual(
            matrix["credentialBoundary"],
            EXPECTED_CREDENTIAL_BOUNDARY,
        )

    def test_credential_provenance_matches_pre_freeze_observation(self) -> None:
        self._assert_task_artifacts_exist()
        matrix = load_strict_json(SOURCE_MATRIX_PATH)
        self._assert_credential_provenance(matrix)

        for path in (
            QUESTION_DIRECTORY / "question.md",
            DATASET_DIRECTORY / "data-contract.md",
            PROTOCOL_DIRECTORY / "protocol.md",
        ):
            with self.subTest(path=path.relative_to(REPOSITORY_ROOT).as_posix()):
                source = path.read_text(encoding="utf-8")
                self.assertRegex(
                    source,
                    r"local credential file의 (?:존재 또는 경로|presence/path).*"
                    r"동결 전.*관측",
                )
                self.assertIn(
                    "exact path와 credential 값은 artifact에 기록하지 않는다",
                    source,
                )
                self.assertIn(
                    "file contents와 file-origin credential values는 읽지 않았다",
                    source,
                )
                self.assertNotIn(
                    "credential file의 경로나 내용을 읽지 않았다",
                    source,
                )

        mutations: tuple[tuple[str, str, bool], ...] = (
            (
                "presence_hidden",
                "localCredentialFilePresenceOrPathObservedBeforeFreeze",
                False,
            ),
            (
                "contents_accessed",
                "localCredentialFileContentsAccessed",
                True,
            ),
            (
                "file_values_accessed",
                "localCredentialValuesAccessedFromFile",
                True,
            ),
        )
        for case, field, mutated_value in mutations:
            with self.subTest(case=case):
                mutated = copy.deepcopy(matrix)
                mutated["credentialBoundary"][field] = mutated_value
                with self.assertRaises(AssertionError):
                    self._assert_credential_provenance(mutated)

    def test_evidence_authorities_separate_external_facts_and_internal_controls(
        self,
    ) -> None:
        self._assert_task_artifacts_exist()
        matrix = load_strict_json(SOURCE_MATRIX_PATH)
        for group in matrix["inputGroups"]:
            for statement in group["evidenceStatements"]:
                with self.subTest(
                    input_group=group["inputGroupId"],
                    evidence_kind=statement["evidenceKind"],
                ):
                    self._assert_evidence_authority_contract(
                        statement,
                        set(group["sourceIds"]),
                    )

        missing_data_control = matrix["inputGroups"][6]["evidenceStatements"][1]
        self.assertEqual(missing_data_control["evidenceKind"], "operational_control")
        self.assertEqual(missing_data_control["sourceIds"], [])
        self.assertEqual(missing_data_control["authorityRefs"], ["SP-002"])
        self.assertEqual(missing_data_control["sourceLocation"], "SP-002 missing-data policy")

    def test_rejects_matrix_binding_status_security_missing_and_license_mutations(
        self,
    ) -> None:
        self._assert_task_artifacts_exist()
        matrix = load_strict_json(SOURCE_MATRIX_PATH)
        mutations: tuple[
            tuple[str, Callable[[dict[str, Any]], None]], ...
        ] = (
            (
                "wrong_protocol_binding",
                lambda value: value.__setitem__("protocolId", "SP-001"),
            ),
            (
                "wrong_group_status",
                lambda value: value["inputGroups"][0].__setitem__(
                    "availabilityStatus", "usable"
                ),
            ),
            (
                "hidden_component_status",
                lambda value: value["inputGroups"][3]["componentStatuses"].__setitem__(
                    "float_shares", "limited"
                ),
            ),
            (
                "derived_claim_reentered_component_availability",
                lambda value: value["inputGroups"][0]["componentStatuses"].__setitem__(
                    "price_volume_regime", "limited"
                ),
            ),
            (
                "availability_identifiability_axis_mixed",
                lambda value: value["inputGroups"][3]["componentStatuses"].__setitem__(
                    "float_shares", "not_identifiable"
                ),
            ),
            (
                "identifiability_availability_axis_mixed",
                lambda value: value["inputGroups"][0][
                    "identifiabilityImplications"
                ][0].__setitem__("status", "limited"),
            ),
            (
                "unsupported_evidence_kind",
                lambda value: value["inputGroups"][0]["evidenceStatements"][
                    0
                ].__setitem__("evidenceKind", "result_claim"),
            ),
            (
                "research_inference_without_internal_authority",
                lambda value: value["inputGroups"][0]["evidenceStatements"][
                    1
                ].__setitem__("authorityRefs", []),
            ),
            (
                "operational_control_with_external_source",
                lambda value: value["inputGroups"][0]["evidenceStatements"][
                    2
                ].__setitem__("sourceIds", ["TOSS-DOC-002"]),
            ),
            (
                "invented_legal_conclusion",
                lambda value: value["providerUsePolicies"][0].__setitem__(
                    "legalConclusion", "raw_market_data_use_prohibited"
                ),
            ),
            (
                "credential_values_stored",
                lambda value: value["credentialBoundary"].__setitem__(
                    "valuesCopiedOrStoredInArtifactsLogsCommands", True
                ),
            ),
            (
                "credential_file_accessed",
                lambda value: value["credentialBoundary"].__setitem__(
                    "localCredentialFileContentsAccessed", True
                ),
            ),
            (
                "live_api_called",
                lambda value: value["credentialBoundary"].__setitem__(
                    "liveApiCalled", True
                ),
            ),
            (
                "neutral_imputation",
                lambda value: value["globalRules"].__setitem__(
                    "missingObservationPolicy", "neutral_imputation"
                ),
            ),
            (
                "missing_input_reweight",
                lambda value: value["globalRules"].__setitem__(
                    "missingDirectInputHandling", "reweight"
                ),
            ),
            (
                "compensatory_license",
                lambda value: value["globalRules"].__setitem__(
                    "licenseGate", "compensatory"
                ),
            ),
        )
        for case, mutate in mutations:
            with self.subTest(case=case):
                mutated = copy.deepcopy(matrix)
                mutate(mutated)
                with self.assertRaises(AssertionError):
                    self._assert_matrix_contract(mutated)

    def test_pre_run_amendment_versions_and_prior_protocol_are_explicit(self) -> None:
        self._assert_task_artifacts_exist()
        for path in (
            QUESTION_DIRECTORY / "object.json",
            DATASET_DIRECTORY / "object.json",
            PROTOCOL_DIRECTORY / "object.json",
        ):
            with self.subTest(path=path.relative_to(REPOSITORY_ROOT).as_posix()):
                self.assertEqual(load_strict_json(path)["version"], "1.0.1")
        self.assertEqual(
            load_strict_json(PROGRAM_DIRECTORY / "object.json")["version"],
            "1.0.0",
        )

        question = (QUESTION_DIRECTORY / "question.md").read_text(encoding="utf-8")
        data_contract = (DATASET_DIRECTORY / "data-contract.md").read_text(
            encoding="utf-8"
        )
        protocol = (PROTOCOL_DIRECTORY / "protocol.md").read_text(encoding="utf-8")
        self.assertIn("버전: `1.0.1`", question)
        self.assertIn("계약 버전: `1.0.1`", data_contract)
        self.assertIn("프로토콜 버전: `1.0.1`", protocol)
        for required_text in (
            "## Pre-run amendment 001",
            PRIOR_PROTOCOL_SHA256,
            "independent spec review",
            "raw input component",
            "credential provenance",
            "`authorityRefs`",
            "Markdown semantic validator",
            "어떤 ExperimentRun이나 EvidenceBundle도 생성되기 전",
            "`runs=[]`",
            "라이브 API",
            "credential file contents",
            "시장 데이터",
        ):
            self.assertIn(required_text, protocol)
        self.assertEqual(
            hashlib.sha256(
                (DATASET_DIRECTORY / "official-source-register.json").read_bytes()
            ).hexdigest(),
            EXPECTED_SOURCE_REGISTER_SHA256,
        )

    def test_protocol_hash_matrix_and_empty_trial_ledger_are_bound(self) -> None:
        self._assert_task_artifacts_exist()
        protocol_path = PROTOCOL_DIRECTORY / "protocol.md"
        protocol_source = protocol_path.read_bytes()
        protocol_sha256 = hashlib.sha256(protocol_source).hexdigest()
        protocol_text = protocol_source.decode("utf-8")
        hash_source = (PROTOCOL_DIRECTORY / "protocol.sha256").read_bytes()

        self.assertRegex(hash_source, rb"^[0-9a-f]{64}\n$")
        self.assertEqual(protocol_sha256, EXPECTED_PROTOCOL_SHA256)
        self.assertEqual(hash_source, f"{protocol_sha256}\n".encode("ascii"))
        self.assertNotIn(protocol_sha256, protocol_text)
        for required_text in (
            "design_seen_before_freeze",
            "confirmatory 근거가 아니다",
            "availability estimand",
            "identifiability estimand",
            "latest",
            "info.version",
            "exact response hash",
            "retrievedAt",
            "documentation revision risk",
            "initial HTTP hash",
            "Next.js asset",
            "evidenceStatements",
            "document_absence_observation",
            "legalConclusion=null",
            "기존 등록 seen-data metadata",
            "새로운 unseen data를 읽지 않았다",
            "라이브 API를 호출하지 않았다",
            "local credential file의 존재 또는 경로는 동결 전에",
            "exact path와 credential 값은 artifact에 기록하지 않는다",
            "file contents와 file-origin credential values는 읽지 않았다",
            "대화에서 plaintext credential이 동결 전에 공개",
            "반복·복사·사용하지 않았다",
            "compromised",
            "rotate",
            "blocked_pending_rotated_credentials_and_provider_retention_clarification",
            "blocked_pending_provider_clarification",
            "rotated credential",
            "one-shot child process environment",
            "personal_trading_only",
            "local retention",
            "raw HTTP response",
            "processed canonical data",
            "clientReceivedAt",
            "OHLC",
            "duplicate",
            "cutoff",
            "currency",
            "rate-limit",
            "secret scan 0",
            "reject_no_zero_or_neutral_imputation",
            "reweight와 renormalize를 금지",
            "runs=[]",
            "ExperimentRun과 EvidenceBundle을 생성하지 않는다",
        ):
            self.assertIn(required_text, protocol_text)

        matrix = load_strict_json(SOURCE_MATRIX_PATH)
        self.assertEqual(matrix["protocolSha256"], protocol_sha256)
        ledger = load_strict_json(TRIAL_LEDGER_PATH)
        self.assertEqual(
            ledger,
            {
                "protocolId": "SP-002",
                "protocolSha256": protocol_sha256,
                "runs": [],
                "schemaVersion": "rp001-trial-ledger.v1",
                "studySlot": "ST-DAT-001",
            },
        )
        self.assertEqual(TRIAL_LEDGER_PATH.read_bytes(), canonical_json_bytes(ledger))

    def _assert_markdown_projection(
        self,
        matrix: dict[str, Any],
        markdown: str,
    ) -> None:
        self._assert_document_semantics(markdown)
        self.assertEqual(
            parse_markdown_bindings(markdown),
            {
                field: matrix[field]
                for field in (
                    "goalId",
                    "programId",
                    "researchQuestionId",
                    "datasetContractId",
                    "studySlot",
                    "protocolId",
                )
            },
        )
        expected_groups = {
            group["inputGroupId"]: {
                field: group[field]
                for field in (
                    "availabilityStatus",
                    "componentStatuses",
                    "identifiabilityImplications",
                    "blockingEffects",
                    "usableFor",
                    "blockedResearchUses",
                )
            }
            for group in matrix["inputGroups"]
        }
        self.assertEqual(parse_markdown_input_groups(markdown), expected_groups)
        self.assertEqual(
            parse_markdown_evidence(markdown),
            {
                group["inputGroupId"]: group["evidenceStatements"]
                for group in matrix["inputGroups"]
            },
        )
        self.assertEqual(
            parse_markdown_provider_policy(markdown),
            matrix["providerUsePolicies"][0],
        )

    def _assert_document_semantics(self, source: str) -> None:
        self._assert_clean_artifact_text(source)
        contradiction_patterns = (
            re.compile(r"Gate\s*실패.*usable.*판정"),
            re.compile(
                r"결측\s+direct input.*(?:0\s*또는\s*neutral|0[·/]neutral).*"
                r"reweight"
            ),
        )
        for pattern in contradiction_patterns:
            self.assertIsNone(pattern.search(source))

    def test_markdown_projection_matches_each_matrix_group(self) -> None:
        self._assert_task_artifacts_exist()
        matrix = load_strict_json(SOURCE_MATRIX_PATH)
        markdown = SOURCE_MATRIX_MARKDOWN_PATH.read_text(encoding="utf-8")

        self._assert_markdown_projection(matrix, markdown)
        self.assertEqual(
            hashlib.sha256(SOURCE_MATRIX_MARKDOWN_PATH.read_bytes()).hexdigest(),
            EXPECTED_SOURCE_MATRIX_MARKDOWN_SHA256,
        )

    def test_markdown_semantic_validator_rejects_projection_mutations(self) -> None:
        self._assert_task_artifacts_exist()
        matrix = load_strict_json(SOURCE_MATRIX_PATH)
        markdown = SOURCE_MATRIX_MARKDOWN_PATH.read_text(encoding="utf-8")

        def relocate_daily_evidence(source: str) -> str:
            evidence_line = next(
                line
                for line in source.splitlines()
                if line.startswith(
                    "- `document_fact` — OpenAPI 1.2.2는 /api/v1/candles의 1d"
                )
            )
            without_daily_evidence = source.replace(f"{evidence_line}\n", "", 1)
            return without_daily_evidence.replace(
                "### `minute_ohlcv`\n",
                f"### `minute_ohlcv`\n\n{evidence_line}\n",
                1,
            )

        mutations: tuple[tuple[str, Callable[[str], str]], ...] = (
            (
                "goal_binding_drift",
                lambda source: source.replace(
                    "- Goal: `GOAL-RP-001`",
                    "- Goal: `GOAL-RP-999`",
                    1,
                ),
            ),
            (
                "backtickless_goal_binding_shadow",
                lambda source: source.replace(
                    "- Goal: `GOAL-RP-001`",
                    "- Goal: GOAL-RP-999\n- Goal: `GOAL-RP-001`",
                    1,
                ),
            ),
            (
                "nonbullet_goal_binding_shadow",
                lambda source: source.replace(
                    "- Goal: `GOAL-RP-001`",
                    "Goal: GOAL-RP-999\n- Goal: `GOAL-RP-001`",
                    1,
                ),
            ),
            (
                "nonbullet_program_binding_shadow",
                lambda source: source.replace(
                    "- Program: `RP-001`",
                    "Program: RP-999\n- Program: `RP-001`",
                    1,
                ),
            ),
            (
                "daily_evidence_source_drift",
                lambda source: source.replace(
                    "— source: TOSS-DOC-002 — authority: none — location: "
                    "paths./api/v1/candles; components.schemas.Candle",
                    "— source: TOSS-DOC-004 — authority: none — location: "
                    "paths./api/v1/candles; components.schemas.Candle",
                    1,
                ),
            ),
            (
                "gate_failure_still_usable",
                lambda source: f"{source}\nGate 실패여도 usable로 판정한다.\n",
            ),
            (
                "missing_imputation_and_reweight_allowed",
                lambda source: (
                    f"{source}\n결측 direct input을 0 또는 neutral로 대체하고 "
                    "남은 입력을 reweight한다.\n"
                ),
            ),
            (
                "provider_policy_field_drift",
                lambda source: source.replace(
                    "- documentedPurpose:",
                    "- documentedPurposeDrift:",
                    1,
                ),
            ),
            (
                "nonbullet_provider_policy_shadow",
                lambda source: source.replace(
                    "- documentedPurpose: `personal_trading_only`",
                    "documentedPurpose: unrestricted\n"
                    "- documentedPurpose: `personal_trading_only`",
                    1,
                ),
            ),
            (
                "duplicate_provider_policy_shadow",
                lambda source: source.replace(
                    "- documentedPurpose: `personal_trading_only`",
                    "- documentedPurpose: `conflicting_value`\n"
                    "- documentedPurpose: `personal_trading_only`",
                    1,
                ),
            ),
            (
                "duplicate_evidence_group_shadow",
                lambda source: source.replace(
                    "### `daily_ohlcv`\n",
                    "### `daily_ohlcv`\n\n"
                    "- `document_fact` — shadow claim — source: TOSS-DOC-004 "
                    "— authority: none — location: shadow\n\n"
                    "### `daily_ohlcv`\n",
                    1,
                ),
            ),
            (
                "duplicate_component_status_shadow",
                lambda source: source.replace(
                    "adjusted_request_option_without_method=limited<br />",
                    "adjusted_request_option_without_method=data_unavailable<br />"
                    "adjusted_request_option_without_method=limited<br />",
                    1,
                ),
            ),
            (
                "backtickless_input_group_semantic_row",
                lambda source: source.replace(
                    "| --- | --- | --- | --- | --- | --- | --- |\n",
                    "| --- | --- | --- | --- | --- | --- | --- |\n"
                    "| daily_ohlcv | usable | shadow=usable | "
                    "shadow=identifiable | shadow | shadow | shadow |\n",
                    1,
                ),
            ),
            (
                "backtickless_evidence_semantic_bullet",
                lambda source: source.replace(
                    "### `daily_ohlcv`\n",
                    "### `daily_ohlcv`\n\n"
                    "- document_fact — shadow claim — source: TOSS-DOC-004 "
                    "— authority: none — location: shadow\n",
                    1,
                ),
            ),
            ("evidence_group_relocation", relocate_daily_evidence),
        )
        self._assert_markdown_projection(matrix, markdown)
        for case, mutate in mutations:
            with self.subTest(case=case):
                with self.assertRaises((AssertionError, ValueError)):
                    self._assert_markdown_projection(matrix, mutate(markdown))

    def test_rq_dc_semantic_helpers_reject_explicit_contradictions(self) -> None:
        self._assert_task_artifacts_exist()
        documents = {
            "RQ-002": (QUESTION_DIRECTORY / "question.md").read_text(
                encoding="utf-8"
            ),
            "DC-002": (DATASET_DIRECTORY / "data-contract.md").read_text(
                encoding="utf-8"
            ),
        }
        contradictions = (
            "Gate 실패여도 usable로 판정한다.",
            "결측 direct input을 0 또는 neutral로 대체하고 남은 입력을 reweight한다.",
        )
        for identifier, source in documents.items():
            self._assert_document_semantics(source)
            for contradiction in contradictions:
                with self.subTest(identifier=identifier, contradiction=contradiction):
                    with self.assertRaises(AssertionError):
                        self._assert_document_semantics(
                            f"{source}\n{contradiction}\n"
                        )

    def test_task5_frozen_hashes_remain_invariant(self) -> None:
        for path, expected_hash in EXPECTED_TASK5_HASHES.items():
            with self.subTest(path=path.relative_to(REPOSITORY_ROOT).as_posix()):
                self.assertEqual(
                    hashlib.sha256(path.read_bytes()).hexdigest(), expected_hash
                )

    def _assert_clean_artifact_text(self, source: str) -> None:
        self.assertIsNone(PLACEHOLDER_PATTERN.search(source))
        self.assertEqual(find_sensitive_values(source), ())

    def test_rejects_placeholder_and_synthetic_sensitive_markers(self) -> None:
        with self.assertRaises(AssertionError):
            self._assert_clean_artifact_text("unfinished PLACEHOLDER content")
        synthetic_marker = "client" + "_secret=synthetic_value_only"
        with self.assertRaises(AssertionError):
            self._assert_clean_artifact_text(synthetic_marker)

    def test_task6_artifacts_contain_no_placeholders_or_sensitive_values(self) -> None:
        self._assert_task_artifacts_exist()
        paths = self._task_artifact_paths() + (
            PROGRAM_DIRECTORY / "object.json",
            CATALOG_PATH,
        )
        for path in paths:
            with self.subTest(path=path.relative_to(REPOSITORY_ROOT).as_posix()):
                self._assert_clean_artifact_text(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
