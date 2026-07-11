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
    / "RQ-001-market-state-identifiability"
)
DATASET_DIRECTORY = (
    REPOSITORY_ROOT
    / "research"
    / "meta-research"
    / "objects"
    / "dataset-contracts"
    / "DC-001-ontology-evidence"
)
PROTOCOL_DIRECTORY = (
    REPOSITORY_ROOT
    / "research"
    / "meta-research"
    / "objects"
    / "study-protocols"
    / "SP-001-market-state-ontology"
)
TRIAL_LEDGER_PATH = (
    REPOSITORY_ROOT / "research" / "rp-001" / "trials" / "ST-ONT-001.json"
)
CATALOG_PATH = (
    REPOSITORY_ROOT
    / "research"
    / "meta-research"
    / "catalog"
    / "research-objects.json"
)
EXPECTED_PROTOCOL_SHA256 = (
    "a180a81c1834f2319e9b16a3d851cbd28b1238c2c383ea36e6f093a203a3138e"
)
EXPECTED_SOURCE_REGISTER_SHA256 = (
    "faadcdd8e4660f40ca050201201913250a478fb39bbf273be2ac142f356ecc2c"
)
EXPECTED_ONTOLOGY_SHA256 = (
    "4e11c9c3a754d542759a0e27f43d9181fa749920a41566a67895c49a71cbcaac"
)

EXPECTED_QUESTION = (
    "사전 지정된 각 상태명에 대해, 시점 t까지 가용한 관측과 외부 측정치가 "
    "가격·거래량 국면, 잠재상태, 인간 심리, 거래결정을 서로 구별할 충분한 "
    "관측가능성과 판별타당도를 제공하는가?"
)
EXPECTED_CANDIDATE_REGIMES = {
    "Normal": "baseline",
    "PreFOMO": "pre_upside_acceleration",
    "FOMOIgnition": "upside_breakout_onset",
    "FOMOContinuation": "upside_momentum_continuation",
    "FOMOExhaustion": "upside_momentum_exhaustion",
    "PotentialProfitTaking": "post_rally_sell_risk",
    "RealizedProfitTaking": "post_rally_sell_flow",
    "PrePanic": "pre_downside_stress",
    "PanicOnset": "downside_dislocation_onset",
    "ActivePanic": "high_intensity_selloff",
    "Capitulation": "selloff_climax",
    "Relief": "selloff_reversal",
    "FakeRelief": "failed_rebound",
    "PostEventNormalization": "post_event_normalization",
}
EXPECTED_SOURCE_IDS_BY_CANDIDATE = {
    "Normal": ("SRC-001", "SRC-002", "SRC-009", "SRC-010", "SRC-013"),
    "PreFOMO": (
        "SRC-001",
        "SRC-002",
        "SRC-003",
        "SRC-005",
        "SRC-006",
        "SRC-009",
        "SRC-010",
    ),
    "FOMOIgnition": (
        "SRC-001",
        "SRC-002",
        "SRC-003",
        "SRC-005",
        "SRC-006",
        "SRC-009",
        "SRC-010",
        "SRC-012",
        "SRC-014",
    ),
    "FOMOContinuation": (
        "SRC-001",
        "SRC-002",
        "SRC-003",
        "SRC-005",
        "SRC-006",
        "SRC-009",
        "SRC-010",
        "SRC-012",
        "SRC-014",
    ),
    "FOMOExhaustion": (
        "SRC-001",
        "SRC-002",
        "SRC-003",
        "SRC-005",
        "SRC-006",
        "SRC-009",
        "SRC-010",
        "SRC-012",
        "SRC-014",
    ),
    "PotentialProfitTaking": (
        "SRC-001",
        "SRC-002",
        "SRC-004",
        "SRC-006",
        "SRC-008",
        "SRC-009",
        "SRC-010",
    ),
    "RealizedProfitTaking": (
        "SRC-001",
        "SRC-002",
        "SRC-004",
        "SRC-006",
        "SRC-008",
        "SRC-009",
        "SRC-010",
        "SRC-011",
        "SRC-012",
    ),
    "PrePanic": (
        "SRC-001",
        "SRC-002",
        "SRC-007",
        "SRC-008",
        "SRC-009",
        "SRC-010",
        "SRC-012",
        "SRC-013",
        "SRC-014",
    ),
    "PanicOnset": (
        "SRC-001",
        "SRC-002",
        "SRC-007",
        "SRC-008",
        "SRC-009",
        "SRC-010",
        "SRC-011",
        "SRC-012",
        "SRC-013",
        "SRC-014",
    ),
    "ActivePanic": (
        "SRC-001",
        "SRC-002",
        "SRC-007",
        "SRC-008",
        "SRC-009",
        "SRC-010",
        "SRC-011",
        "SRC-012",
        "SRC-013",
        "SRC-014",
    ),
    "Capitulation": (
        "SRC-001",
        "SRC-002",
        "SRC-007",
        "SRC-008",
        "SRC-009",
        "SRC-010",
        "SRC-011",
        "SRC-012",
        "SRC-013",
        "SRC-014",
    ),
    "Relief": (
        "SRC-001",
        "SRC-002",
        "SRC-007",
        "SRC-008",
        "SRC-009",
        "SRC-010",
        "SRC-011",
        "SRC-012",
    ),
    "FakeRelief": (
        "SRC-001",
        "SRC-002",
        "SRC-007",
        "SRC-008",
        "SRC-009",
        "SRC-010",
        "SRC-012",
        "SRC-014",
    ),
    "PostEventNormalization": (
        "SRC-001",
        "SRC-002",
        "SRC-007",
        "SRC-008",
        "SRC-009",
        "SRC-010",
        "SRC-013",
    ),
}
EXPECTED_TIER_IDS = (
    "T0_OHLCV",
    "T1_AGGREGATE_ATTENTION_FLOW",
    "T2_ORDER_BOOK",
    "T3_ACCOUNT_POSITION",
    "T4_LINKED_VALIDATED_SELF_REPORT",
)
PLACEHOLDER_PATTERN = re.compile(
    r"\b(?:TODO|TBD|FIXME|PLACEHOLDER)\b|<[A-Z][A-Z0-9_-]*>",
    re.IGNORECASE,
)
EXPECTED_ONTOLOGY_FIELDS = {
    "datasetContractId",
    "globalRules",
    "goalId",
    "goalVersion",
    "measurementTiers",
    "programId",
    "programVersion",
    "protocolId",
    "protocolSha256",
    "protocolVersion",
    "researchQuestionId",
    "schemaVersion",
    "sourceRegisterPath",
    "stateCandidates",
    "studySlot",
    "terminalStatuses",
}
EXPECTED_ONTOLOGY_ROW_FIELDS = {
    "allowedOutputsByTier",
    "counterexample",
    "decisionLayerProhibitions",
    "distinguishingEvidence",
    "observablePricePathLabel",
    "requiredDirectBehaviorOrFlowMeasure",
    "sourceIds",
    "stateCandidate",
}
EXPECTED_PERMISSION_FIELDS = {
    "candidateNameAllowed",
    "conditions",
    "outputName",
    "terminalStatus",
    "timeUse",
}
EXPECTED_MEASUREMENT_TIERS = (
    {
        "measurementScope": "시점 t까지의 가격·거래량",
        "name": "OHLCV only",
        "namingConstraint": (
            "price_volume_regime.* only; psychology and intent names prohibited"
        ),
        "tierId": "T0_OHLCV",
    },
    {
        "measurementScope": "집계 검색·뉴스노출·주체별 흐름·집계 옵션과 공매도",
        "name": "Aggregate attention and flow",
        "namingConstraint": (
            "proxy.* only; psychology and motive names prohibited"
        ),
        "tierId": "T1_AGGREGATE_ATTENTION_FLOW",
    },
    {
        "measurementScope": "순서보존 호가·체결·취소·aggressor 추론",
        "name": "Ordered order-book events",
        "namingConstraint": "observed.* or proxy.* microstructure names only",
        "tierId": "T2_ORDER_BOOK",
    },
    {
        "measurementScope": "연결 계좌 거래·포지션·취득원가",
        "name": "Linked account and position",
        "namingConstraint": (
            "direct behavior or proxy names only; motive remains separate"
        ),
        "tierId": "T3_ACCOUNT_POSITION",
    },
    {
        "measurementScope": "계좌·사건에 동시 연결된 검증 자기보고와 독립 행동·흐름",
        "name": "Linked contemporaneous validated self-report",
        "namingConstraint": (
            "latent investor construct name only after every listed validity "
            "condition passes"
        ),
        "tierId": "T4_LINKED_VALIDATED_SELF_REPORT",
    },
)
EXPECTED_TERMINAL_STATUSES = (
    "identifiable",
    "proxy_only",
    "not_identifiable",
)
EXPECTED_GLOBAL_RULES = {
    "fakeReliefAvailability": "retrospective_only",
    "missingDirectMeasureTerminalStatus": "not_identifiable",
    "missingObservationPolicy": "reject_no_zero_or_neutral_imputation",
    "missingObservationRenormalizationAllowed": False,
    "missingObservationReweightingAllowed": False,
    "samePriceDerivedScoresAreIndependentMethods": False,
    "stateDirectlyAuthorizesTrade": False,
    "statisticalIdentifiabilityImpliesConstructValidity": False,
    "t0PsychologicalOrIntentNameCount": 0,
    "t4PermissionsAreConditionalNotCurrentEmpiricalFindings": True,
    "terminalDecisionOrder": [
        "t0_psychology_or_intent_and_time_unavailable_to_not_identifiable",
        "all_direct_measurement_and_validity_gates_to_identifiable",
        "directly_observed_related_nonconstruct_output_to_proxy_only",
        "otherwise_not_identifiable",
    ],
    "unanchoredLatentStateName": "latent_state.k",
}
EXPECTED_T4_VALIDITY_CONDITIONS = (
    "contemporaneous_account_linkage",
    "validated_direct_measurement",
    "convergent_and_discriminant_validity",
    "observational_alternatives_separated",
    "stage_specific_temporal_anchor",
    "label_permutation_anchor_stable",
)
EXPECTED_SOURCE_FIELDS = {
    "sourceId",
    "title",
    "authors",
    "publisher",
    "year",
    "doi",
    "officialUrl",
    "accessedAt",
    "primarySource",
    "corpusRole",
    "appliedClaims",
    "nonApplicableClaims",
}
EXPECTED_SOURCE_IDENTITIES = (
    (
        "SRC-001",
        "Construct Validity in Psychological Tests",
        ("Lee J. Cronbach", "Paul E. Meehl"),
        1955,
        "10.1037/h0040957",
        "https://doi.org/10.1037/h0040957",
    ),
    (
        "SRC-002",
        "Convergent and Discriminant Validation by the Multitrait-Multimethod Matrix",
        ("Donald T. Campbell", "Donald W. Fiske"),
        1959,
        "10.1037/h0046016",
        "https://doi.org/10.1037/h0046016",
    ),
    (
        "SRC-003",
        "Motivational, Emotional, and Behavioral Correlates of Fear of Missing Out",
        (
            "Andrew K. Przybylski",
            "Kou Murayama",
            "Cody R. DeHaan",
            "Valerie Gladwell",
        ),
        2013,
        "10.1016/j.chb.2013.02.014",
        "https://doi.org/10.1016/j.chb.2013.02.014",
    ),
    (
        "SRC-004",
        "Are Investors Reluctant to Realize Their Losses?",
        ("Terrance Odean",),
        1998,
        "10.1111/0022-1082.00072",
        "https://doi.org/10.1111/0022-1082.00072",
    ),
    (
        "SRC-005",
        "In Search of Attention",
        ("Zhi Da", "Joseph Engelberg", "Pengjie Gao"),
        2011,
        "10.1111/j.1540-6261.2011.01679.x",
        "https://doi.org/10.1111/j.1540-6261.2011.01679.x",
    ),
    (
        "SRC-006",
        "All That Glitters: The Effect of Attention and News on the Buying Behavior of Individual and Institutional Investors",
        ("Brad M. Barber", "Terrance Odean"),
        2008,
        "10.1093/rfs/hhm079",
        "https://doi.org/10.1093/rfs/hhm079",
    ),
    (
        "SRC-007",
        "Investor Behavior in the October 1987 Stock Market Crash: Survey Evidence",
        ("Robert J. Shiller",),
        1987,
        "10.3386/w2446",
        "https://www.nber.org/papers/w2446",
    ),
    (
        "SRC-008",
        "Individual Investor Perceptions and Behavior During the Financial Crisis",
        ("Arvid O. I. Hoffmann", "Thomas Post", "Joost M. E. Pennings"),
        2013,
        "10.1016/j.jbankfin.2012.08.007",
        "https://doi.org/10.1016/j.jbankfin.2012.08.007",
    ),
    (
        "SRC-009",
        "Identifiability of Parameters in Latent Structure Models with Many Observed Variables",
        ("Elizabeth S. Allman", "Catherine Matias", "John A. Rhodes"),
        2009,
        "10.1214/09-AOS689",
        "https://arxiv.org/abs/0809.5032",
    ),
    (
        "SRC-010",
        "Inference in finite state space non parametric Hidden Markov Models and applications",
        ("Elisabeth Gassiat", "Alice Cleynen", "Stéphane Robin"),
        2016,
        "10.1007/s11222-014-9523-8",
        "https://link.springer.com/article/10.1007/s11222-014-9523-8",
    ),
    (
        "SRC-011",
        "Inferring Trade Direction from Intraday Data",
        ("Charles M. C. Lee", "Mark J. Ready"),
        1991,
        "10.1111/j.1540-6261.1991.tb02683.x",
        "https://doi.org/10.1111/j.1540-6261.1991.tb02683.x",
    ),
    (
        "SRC-012",
        "The Price Impact of Order Book Events",
        ("Rama Cont", "Arseniy Kukanov", "Sasha Stoikov"),
        2014,
        "10.1093/jjfinec/nbt003",
        "https://arxiv.org/abs/1011.6402",
    ),
    (
        "SRC-013",
        "Simulating and Analyzing Order Book Data: The Queue-Reactive Model",
        ("Weibing Huang", "Charles-Albert Lehalle", "Mathieu Rosenbaum"),
        2015,
        "10.1080/01621459.2014.982278",
        "https://arxiv.org/abs/1312.0563",
    ),
    (
        "SRC-014",
        "Estimation of Slowly Decreasing Hawkes Kernels: Application to High-Frequency Order Book Dynamics",
        ("Emmanuel Bacry", "Thibault Jaisson", "Jean-François Muzy"),
        2016,
        "10.1080/14697688.2015.1123287",
        "https://arxiv.org/abs/1412.7096",
    ),
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


class OntologyContractTest(unittest.TestCase):
    def test_requires_every_planned_artifact(self) -> None:
        required_paths = (
            QUESTION_DIRECTORY / "object.json",
            QUESTION_DIRECTORY / "question.md",
            DATASET_DIRECTORY / "object.json",
            DATASET_DIRECTORY / "data-contract.md",
            DATASET_DIRECTORY / "source-register.json",
            PROTOCOL_DIRECTORY / "object.json",
            PROTOCOL_DIRECTORY / "protocol.md",
            PROTOCOL_DIRECTORY / "protocol.sha256",
            PROGRAM_DIRECTORY / "state-ontology.md",
            PROGRAM_DIRECTORY / "state-ontology.json",
            TRIAL_LEDGER_PATH,
        )

        missing = [
            path.relative_to(REPOSITORY_ROOT).as_posix()
            for path in required_paths
            if not path.is_file()
        ]

        self.assertEqual(missing, [], f"missing ST-ONT-001 artifacts: {missing}")

    def test_descriptors_catalog_and_program_artifacts_are_bound_exactly(self) -> None:
        expected_descriptors = {
            "RQ-001": {
                "path": QUESTION_DIRECTORY / "object.json",
                "type": "ResearchQuestion",
                "version": "1.0.0",
                "state": "completed",
                "dependsOn": ["RP-001"],
                "artifacts": [
                    "research/meta-research/objects/research-questions/"
                    "RQ-001-market-state-identifiability/question.md"
                ],
            },
            "DC-001": {
                "path": DATASET_DIRECTORY / "object.json",
                "type": "DatasetContract",
                "version": "1.0.1",
                "state": "completed",
                "dependsOn": ["RQ-001"],
                "artifacts": [
                    "research/meta-research/objects/dataset-contracts/"
                    "DC-001-ontology-evidence/data-contract.md",
                    "research/meta-research/objects/dataset-contracts/"
                    "DC-001-ontology-evidence/source-register.json",
                ],
            },
            "SP-001": {
                "path": PROTOCOL_DIRECTORY / "object.json",
                "type": "StudyProtocol",
                "version": "1.0.1",
                "state": "preregistered",
                "dependsOn": ["DC-001", "RQ-001"],
                "artifacts": [
                    "research/meta-research/objects/study-protocols/"
                    "SP-001-market-state-ontology/protocol.md",
                    "research/meta-research/objects/study-protocols/"
                    "SP-001-market-state-ontology/protocol.sha256",
                    "research/rp-001/trials/ST-ONT-001.json",
                ],
            },
        }
        for identifier, expected in expected_descriptors.items():
            with self.subTest(identifier=identifier):
                descriptor = load_strict_json(expected["path"])
                self.assertEqual(descriptor["schemaVersion"], "research-object.v1")
                self.assertEqual(descriptor["id"], identifier)
                self.assertEqual(descriptor["type"], expected["type"])
                self.assertEqual(descriptor["version"], expected["version"])
                self.assertEqual(descriptor["lifecycleState"], expected["state"])
                self.assertEqual(descriptor["evidenceLevel"], "conceptual")
                self.assertEqual(descriptor["dependsOn"], expected["dependsOn"])
                self.assertEqual(descriptor["artifacts"], expected["artifacts"])

        catalog = load_strict_json(CATALOG_PATH)
        descriptors = [entry["descriptor"] for entry in catalog["objects"]]
        self.assertEqual(
            descriptors,
            [
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
            ],
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

        catalog_descriptors = [
            load_strict_json(REPOSITORY_ROOT / descriptor)
            for descriptor in descriptors
        ]
        self.assertEqual(len(catalog_descriptors), 30)
        self.assertEqual(
            sum(len(descriptor["dependsOn"]) for descriptor in catalog_descriptors),
            46,
        )
        self.assertEqual(
            sum(len(descriptor["artifacts"]) for descriptor in catalog_descriptors),
            70,
        )

    def test_question_and_data_contract_freeze_the_identifiability_scope(self) -> None:
        question = (QUESTION_DIRECTORY / "question.md").read_text(encoding="utf-8")
        self.assertIn(EXPECTED_QUESTION, question)
        for required_text in (
            "14개 상태 후보 × 5개 자료 계층",
            "identifiable",
            "proxy_only",
            "not_identifiable",
            "horizon: 적용하지 않음",
            "시점 t의 동시적 구성개념 식별",
            "OHLCV는 심리나 의도를 식별할 수 없다",
            "price_volume_regime",
            "뉴스",
            "유동성 충격",
            "리밸런싱",
            "숏커버링",
            "기계적 손절",
            "서로 다른 믿음",
            "독립 방법으로 세지 않는다",
        ):
            self.assertIn(required_text, question)

        contract = (DATASET_DIRECTORY / "data-contract.md").read_text(
            encoding="utf-8"
        )
        for field in sorted(EXPECTED_SOURCE_FIELDS):
            self.assertIn(f"`{field}`", contract)
        for required_text in (
            "source-register.json",
            "계약 버전: `1.0.1`",
            "저작권 원문을 저장하지 않는다",
            "서지·주장 메타데이터만 저장",
            "정정·철회",
            "amendment",
            "nonApplicableClaims",
            "수락을 차단",
        ):
            self.assertIn(required_text, contract)

    def _assert_nonempty_string(self, value: Any) -> None:
        self.assertIsInstance(value, str)
        self.assertTrue(value.strip())

    def _assert_nonempty_string_list(
        self,
        value: Any,
        *,
        unique: bool = False,
    ) -> None:
        self.assertIsInstance(value, list)
        self.assertTrue(value)
        for entry in value:
            self._assert_nonempty_string(entry)
        if unique:
            self.assertEqual(len(value), len(set(value)))

    def _assert_source_register_contract(self, register: dict[str, Any]) -> None:
        self.assertIsInstance(register, dict)
        self.assertEqual(set(register), {"schemaVersion", "sources"})
        self.assertEqual(
            register["schemaVersion"], "rp001-ontology-source-register.v1"
        )
        sources = register["sources"]
        self.assertIsInstance(sources, list)
        self.assertEqual(len(sources), len(EXPECTED_SOURCE_IDENTITIES))

        for source, identity in zip(sources, EXPECTED_SOURCE_IDENTITIES, strict=True):
            self.assertIsInstance(source, dict)
            self.assertEqual(set(source), EXPECTED_SOURCE_FIELDS)
            for field in (
                "sourceId",
                "title",
                "publisher",
                "doi",
                "officialUrl",
                "accessedAt",
                "corpusRole",
            ):
                self._assert_nonempty_string(source[field])
            self._assert_nonempty_string_list(source["authors"])
            self._assert_nonempty_string_list(source["appliedClaims"])
            self._assert_nonempty_string_list(source["nonApplicableClaims"])
            self.assertIs(type(source["year"]), int)
            self.assertIs(type(source["primarySource"]), bool)

            self.assertEqual(source["sourceId"], identity[0])
            self.assertEqual(source["title"], identity[1])
            self.assertEqual(tuple(source["authors"]), identity[2])
            self.assertEqual(source["year"], identity[3])
            self.assertEqual(source["doi"], identity[4])
            self.assertEqual(source["officialUrl"], identity[5])
            self.assertEqual(source["accessedAt"], "2026-07-10")
            self.assertIs(source["primarySource"], True)
            self.assertEqual(source["corpusRole"], "design_seen_before_freeze")
            self.assertIsNone(
                PLACEHOLDER_PATTERN.search(
                    json.dumps(source, ensure_ascii=False, sort_keys=True)
                )
            )

        source_ids = [source["sourceId"] for source in sources]
        self.assertEqual(len(source_ids), len(set(source_ids)))

    def test_source_register_is_complete_primary_design_seen_corpus(self) -> None:
        register_path = DATASET_DIRECTORY / "source-register.json"
        register = load_strict_json(register_path)

        self._assert_source_register_contract(register)

        self.assertEqual(
            hashlib.sha256(register_path.read_bytes()).hexdigest(),
            EXPECTED_SOURCE_REGISTER_SHA256,
        )
        self.assertEqual(register_path.read_bytes(), canonical_json_bytes(register))

    def test_rejects_source_contract_type_and_placeholder_mutations(self) -> None:
        register = load_strict_json(DATASET_DIRECTORY / "source-register.json")
        mutations: tuple[
            tuple[str, Callable[[dict[str, Any]], None]], ...
        ] = (
            (
                "boolean_year",
                lambda value: value["sources"][0].__setitem__("year", True),
            ),
            (
                "float_year",
                lambda value: value["sources"][0].__setitem__("year", 1955.0),
            ),
            (
                "authors_string",
                lambda value: value["sources"][0].__setitem__(
                    "authors", "Lee J. Cronbach"
                ),
            ),
            (
                "applied_claims_string",
                lambda value: value["sources"][0].__setitem__(
                    "appliedClaims", "construct validity"
                ),
            ),
            (
                "placeholder_claim",
                lambda value: value["sources"][0].__setitem__(
                    "appliedClaims", ["PLACEHOLDER"]
                ),
            ),
            (
                "empty_non_applicable_claims",
                lambda value: value["sources"][0].__setitem__(
                    "nonApplicableClaims", []
                ),
            ),
            (
                "boolean_title",
                lambda value: value["sources"][0].__setitem__("title", True),
            ),
            (
                "numeric_primary_source",
                lambda value: value["sources"][0].__setitem__(
                    "primarySource", 1
                ),
            ),
        )
        for case, mutate in mutations:
            with self.subTest(case=case):
                mutated = copy.deepcopy(register)
                mutate(mutated)

                with self.assertRaises(AssertionError):
                    self._assert_source_register_contract(mutated)

    def test_deprecated_source_identity_and_year_field_are_absent(self) -> None:
        legacy_doi = "10.1007/s11222-014-" + "9494-0"
        legacy_title = (
            "Finite State Space Non Parametric Hidden Markov Models "
            + "are in General Identifiable"
        )
        legacy_year_field = "publication" + "Year"
        paths = (
            DATASET_DIRECTORY / "object.json",
            DATASET_DIRECTORY / "data-contract.md",
            DATASET_DIRECTORY / "source-register.json",
            PROTOCOL_DIRECTORY / "object.json",
            PROTOCOL_DIRECTORY / "protocol.md",
            PROGRAM_DIRECTORY / "state-ontology.md",
            PROGRAM_DIRECTORY / "state-ontology.json",
            Path(__file__),
        )
        for path in paths:
            with self.subTest(path=path.relative_to(REPOSITORY_ROOT).as_posix()):
                source = path.read_text(encoding="utf-8")
                self.assertNotIn(legacy_doi, source)
                self.assertNotIn(legacy_title, source)
                self.assertNotIn(legacy_year_field, source)

    def test_protocol_hash_and_empty_trial_ledger_are_bound(self) -> None:
        protocol_path = PROTOCOL_DIRECTORY / "protocol.md"
        protocol_source = protocol_path.read_bytes()
        protocol_text = protocol_source.decode("utf-8")
        protocol_sha256 = hashlib.sha256(protocol_source).hexdigest()
        hash_source = (PROTOCOL_DIRECTORY / "protocol.sha256").read_bytes()
        prior_protocol_sha256 = (
            "30ccf01ea1337a96d316d30c03c0daac"
            "fe3ed2bbba085a500e3e55965f54a895"
        )

        self.assertRegex(hash_source, rb"^[0-9a-f]{64}\n$")
        self.assertEqual(protocol_sha256, EXPECTED_PROTOCOL_SHA256)
        self.assertEqual(
            hash_source, f"{EXPECTED_PROTOCOL_SHA256}\n".encode("ascii")
        )
        self.assertNotEqual(protocol_sha256, prior_protocol_sha256)
        self.assertNotIn(protocol_sha256, protocol_text)
        for required_text in (
            "protocol.sha256",
            "프로토콜 버전: `1.0.1`",
            "## Pre-run amendment 001",
            prior_protocol_sha256,
            "독립 사양 검토",
            "Inference in finite state space non parametric Hidden Markov Models and applications",
            "10.1007/s11222-014-9523-8",
            "`year`로 통일",
            "reject_no_zero_or_neutral_imputation",
            "`runs=[]`",
            "ExperimentRun과 EvidenceBundle은 생성되지 않았다",
            "시장 데이터는 사용하지 않았다",
            "결측 관측을 0, neutral, baseline으로 대체하지 않는다",
            "reweight와 renormalize를 금지한다",
            "빈 direct measure 또는 결측 direct measure",
            "design_seen_before_freeze",
            "설계 전에 이미 열람",
            "회고적 확인 근거가 아니다",
            "독립 2차 추출",
            "불일치",
            "label permutation",
            "latent_state.k",
            "14/14",
            "T0 심리·의도 명칭 0개",
            "판정순서는 상호배타적으로 적용한다",
            "최소 경제효과를 두지 않는다",
            "예측 또는 채택 주장을 하지 않는다",
            "not_identifiable",
            "사후 규칙 변경",
            "비적용 범위",
        ):
            self.assertIn(required_text, protocol_text)

        ledger = load_strict_json(TRIAL_LEDGER_PATH)
        self.assertEqual(
            ledger,
            {
                "protocolId": "SP-001",
                "protocolSha256": EXPECTED_PROTOCOL_SHA256,
                "runs": [],
                "schemaVersion": "rp001-trial-ledger.v1",
                "studySlot": "ST-ONT-001",
            },
        )
        self.assertEqual(TRIAL_LEDGER_PATH.read_bytes(), canonical_json_bytes(ledger))

    def _assert_ontology_contract(self, ontology: dict[str, Any]) -> None:
        self.assertIsInstance(ontology, dict)
        self.assertEqual(set(ontology), EXPECTED_ONTOLOGY_FIELDS)
        expected_scalar_fields = {
            "datasetContractId": "DC-001",
            "goalId": "GOAL-RP-001",
            "goalVersion": "1.0",
            "programId": "RP-001",
            "programVersion": "1.0.0",
            "protocolId": "SP-001",
            "protocolSha256": EXPECTED_PROTOCOL_SHA256,
            "protocolVersion": "1.0.1",
            "researchQuestionId": "RQ-001",
            "schemaVersion": "rp001-state-ontology.v1",
            "sourceRegisterPath": (
                "research/meta-research/objects/dataset-contracts/"
                "DC-001-ontology-evidence/source-register.json"
            ),
            "studySlot": "ST-ONT-001",
        }
        for field, expected_value in expected_scalar_fields.items():
            self._assert_nonempty_string(ontology[field])
            self.assertEqual(ontology[field], expected_value)

        measurement_tiers = ontology["measurementTiers"]
        self.assertIsInstance(measurement_tiers, list)
        self.assertEqual(len(measurement_tiers), len(EXPECTED_MEASUREMENT_TIERS))
        for tier in measurement_tiers:
            self.assertIsInstance(tier, dict)
            self.assertEqual(
                set(tier),
                {"measurementScope", "name", "namingConstraint", "tierId"},
            )
            for value in tier.values():
                self._assert_nonempty_string(value)
        self.assertEqual(tuple(measurement_tiers), EXPECTED_MEASUREMENT_TIERS)

        terminal_statuses = ontology["terminalStatuses"]
        self._assert_nonempty_string_list(terminal_statuses, unique=True)
        self.assertEqual(tuple(terminal_statuses), EXPECTED_TERMINAL_STATUSES)

        rules = ontology["globalRules"]
        self.assertIsInstance(rules, dict)
        self.assertEqual(set(rules), set(EXPECTED_GLOBAL_RULES))
        self.assertEqual(rules, EXPECTED_GLOBAL_RULES)
        for field in (
            "missingObservationRenormalizationAllowed",
            "missingObservationReweightingAllowed",
            "samePriceDerivedScoresAreIndependentMethods",
            "stateDirectlyAuthorizesTrade",
            "statisticalIdentifiabilityImpliesConstructValidity",
            "t4PermissionsAreConditionalNotCurrentEmpiricalFindings",
        ):
            self.assertIs(type(rules[field]), bool)
        self.assertIs(type(rules["t0PsychologicalOrIntentNameCount"]), int)
        self._assert_nonempty_string_list(rules["terminalDecisionOrder"], unique=True)

        rows = ontology["stateCandidates"]
        self.assertIsInstance(rows, list)
        self.assertEqual(len(rows), len(EXPECTED_CANDIDATE_REGIMES))
        self.assertEqual(
            tuple(row["stateCandidate"] for row in rows),
            tuple(EXPECTED_CANDIDATE_REGIMES),
        )
        psychological_or_intent_candidates = {
            "PreFOMO",
            "FOMOIgnition",
            "FOMOContinuation",
            "FOMOExhaustion",
            "PotentialProfitTaking",
            "RealizedProfitTaking",
            "PrePanic",
            "PanicOnset",
            "ActivePanic",
            "Capitulation",
        }
        descriptive_candidates = {
            "Normal",
            "Relief",
            "PostEventNormalization",
        }
        registered_source_ids = {
            identity[0] for identity in EXPECTED_SOURCE_IDENTITIES
        }
        referenced_source_ids: set[str] = set()

        for row in rows:
            self.assertIsInstance(row, dict)
            self.assertEqual(set(row), EXPECTED_ONTOLOGY_ROW_FIELDS)
            candidate = row["stateCandidate"]
            self._assert_nonempty_string(candidate)
            self._assert_nonempty_string(row["observablePricePathLabel"])
            self._assert_nonempty_string(row["counterexample"])
            for field in (
                "requiredDirectBehaviorOrFlowMeasure",
                "distinguishingEvidence",
                "decisionLayerProhibitions",
                "sourceIds",
            ):
                self._assert_nonempty_string_list(
                    row[field],
                    unique=field == "sourceIds",
                )
            self.assertEqual(
                row["observablePricePathLabel"],
                EXPECTED_CANDIDATE_REGIMES[candidate],
            )
            self.assertIn(
                "no_state_directly_authorizes_trade",
                row["decisionLayerProhibitions"],
            )
            self.assertTrue(set(row["sourceIds"]).issubset(registered_source_ids))
            self.assertEqual(
                tuple(row["sourceIds"]),
                EXPECTED_SOURCE_IDS_BY_CANDIDATE[candidate],
            )
            referenced_source_ids.update(row["sourceIds"])

            permissions = row["allowedOutputsByTier"]
            self.assertIsInstance(permissions, dict)
            self.assertEqual(tuple(permissions), EXPECTED_TIER_IDS)
            for tier_id, permission in permissions.items():
                self.assertIsInstance(permission, dict)
                self.assertEqual(set(permission), EXPECTED_PERMISSION_FIELDS)
                self.assertIs(type(permission["candidateNameAllowed"]), bool)
                self._assert_nonempty_string(permission["outputName"])
                self._assert_nonempty_string(permission["terminalStatus"])
                self._assert_nonempty_string(permission["timeUse"])
                self._assert_nonempty_string_list(
                    permission["conditions"],
                    unique=True,
                )

                if candidate == "FakeRelief":
                    expected_status = "not_identifiable"
                    expected_candidate_name_allowed = False
                    expected_time_use = "retrospective_only"
                elif candidate in descriptive_candidates:
                    expected_status = "proxy_only"
                    expected_candidate_name_allowed = False
                    expected_time_use = "time_t_only"
                else:
                    expected_status = (
                        "not_identifiable"
                        if tier_id == "T0_OHLCV"
                        else "identifiable"
                        if tier_id == "T4_LINKED_VALIDATED_SELF_REPORT"
                        else "proxy_only"
                    )
                    expected_candidate_name_allowed = (
                        tier_id == "T4_LINKED_VALIDATED_SELF_REPORT"
                    )
                    expected_time_use = "time_t_only"

                self.assertEqual(permission["terminalStatus"], expected_status)
                self.assertIs(
                    permission["candidateNameAllowed"],
                    expected_candidate_name_allowed,
                )
                self.assertEqual(permission["timeUse"], expected_time_use)

            t0 = permissions["T0_OHLCV"]
            self.assertEqual(
                t0["outputName"],
                f"price_volume_regime.{EXPECTED_CANDIDATE_REGIMES[candidate]}",
            )
            self.assertTrue(
                permissions["T1_AGGREGATE_ATTENTION_FLOW"]["outputName"].startswith(
                    "proxy."
                )
            )
            self.assertTrue(
                permissions["T2_ORDER_BOOK"]["outputName"].startswith(
                    ("observed.", "proxy.")
                )
            )
            self.assertTrue(
                permissions["T3_ACCOUNT_POSITION"]["outputName"].startswith(
                    ("observed.", "proxy.")
                )
            )
            t4 = permissions["T4_LINKED_VALIDATED_SELF_REPORT"]
            if candidate in psychological_or_intent_candidates:
                self.assertTrue(
                    t4["outputName"].startswith("latent_investor_state.")
                )
                self.assertEqual(
                    tuple(t4["conditions"]),
                    EXPECTED_T4_VALIDITY_CONDITIONS,
                )
                self.assertTrue({"SRC-009", "SRC-010"}.issubset(row["sourceIds"]))
            elif candidate in descriptive_candidates:
                self.assertTrue(
                    t4["outputName"].startswith(("observed.", "proxy."))
                )
            else:
                self.assertEqual(
                    t4["outputName"],
                    "retrospective_outcome.failed_rebound",
                )

        self.assertEqual(referenced_source_ids, registered_source_ids)
        rows_by_candidate = {row["stateCandidate"]: row for row in rows}
        self.assertEqual(
            rows_by_candidate["PotentialProfitTaking"]["allowedOutputsByTier"]
            ["T3_ACCOUNT_POSITION"]["outputName"],
            "proxy.unrealized_gain_overhang",
        )
        self.assertEqual(
            rows_by_candidate["PotentialProfitTaking"]["allowedOutputsByTier"]
            ["T1_AGGREGATE_ATTENTION_FLOW"]["outputName"],
            "proxy.aggregate.post_rally_sell_risk",
        )
        self.assertEqual(
            rows_by_candidate["RealizedProfitTaking"]["allowedOutputsByTier"]
            ["T3_ACCOUNT_POSITION"]["outputName"],
            "observed.realized_gain_sale",
        )
        fake_relief = rows_by_candidate["FakeRelief"]
        self.assertIn(
            "never_use_fake_relief_as_time_t_input",
            fake_relief["decisionLayerProhibitions"],
        )
        self.assertTrue(
            any(
                "향후 적용 study가 사전등록한 미래 창" in evidence
                for evidence in fake_relief["distinguishingEvidence"]
            )
        )
    def test_ontology_covers_exactly_fourteen_candidates_and_five_tiers(self) -> None:
        ontology_path = PROGRAM_DIRECTORY / "state-ontology.json"
        ontology = load_strict_json(ontology_path)

        self._assert_ontology_contract(ontology)

        self.assertEqual(
            hashlib.sha256(ontology_path.read_bytes()).hexdigest(),
            EXPECTED_ONTOLOGY_SHA256,
        )
        self.assertEqual(ontology_path.read_bytes(), canonical_json_bytes(ontology))

    def test_rejects_ontology_structure_and_seventy_cell_mutations(self) -> None:
        ontology = load_strict_json(PROGRAM_DIRECTORY / "state-ontology.json")

        def mutate_fake_relief(value: dict[str, Any]) -> None:
            fake_relief = next(
                row
                for row in value["stateCandidates"]
                if row["stateCandidate"] == "FakeRelief"
            )
            for permission in fake_relief["allowedOutputsByTier"].values():
                permission["terminalStatus"] = "proxy_only"
                permission["candidateNameAllowed"] = True
                permission["timeUse"] = "future"

        def swap_candidate_sources(value: dict[str, Any]) -> None:
            normal_sources = value["stateCandidates"][0]["sourceIds"]
            pre_fomo_sources = value["stateCandidates"][1]["sourceIds"]
            value["stateCandidates"][0]["sourceIds"] = pre_fomo_sources
            value["stateCandidates"][1]["sourceIds"] = normal_sources

        mutations: tuple[
            tuple[str, Callable[[dict[str, Any]], None]], ...
        ] = (
            (
                "dataset_contract_id",
                lambda value: value.__setitem__("datasetContractId", "DC-999"),
            ),
            (
                "research_question_id",
                lambda value: value.__setitem__("researchQuestionId", "RQ-999"),
            ),
            (
                "study_slot",
                lambda value: value.__setitem__("studySlot", "ST-ONT-999"),
            ),
            (
                "source_register_path",
                lambda value: value.__setitem__(
                    "sourceRegisterPath", "research/wrong-source-register.json"
                ),
            ),
            (
                "extra_top_level_key",
                lambda value: value.__setitem__("unexpected", True),
            ),
            (
                "counterexample_boolean",
                lambda value: value["stateCandidates"][0].__setitem__(
                    "counterexample", True
                ),
            ),
            (
                "conditions_string",
                lambda value: value["stateCandidates"][0][
                    "allowedOutputsByTier"
                ]["T1_AGGREGATE_ATTENTION_FLOW"].__setitem__(
                    "conditions", "aggregate_attention_or_flow_only"
                ),
            ),
            (
                "direct_measure_string",
                lambda value: value["stateCandidates"][0].__setitem__(
                    "requiredDirectBehaviorOrFlowMeasure", "baseline"
                ),
            ),
            (
                "blank_distinguishing_evidence",
                lambda value: value["stateCandidates"][0].__setitem__(
                    "distinguishingEvidence", [" "]
                ),
            ),
            (
                "duplicate_source_id",
                lambda value: value["stateCandidates"][0]["sourceIds"].append(
                    "SRC-001"
                ),
            ),
            ("candidate_source_binding_swap", swap_candidate_sources),
            (
                "normal_t1_identifiable",
                lambda value: value["stateCandidates"][0][
                    "allowedOutputsByTier"
                ]["T1_AGGREGATE_ATTENTION_FLOW"].__setitem__(
                    "terminalStatus", "identifiable"
                ),
            ),
            (
                "normal_t2_future_time_use",
                lambda value: value["stateCandidates"][0][
                    "allowedOutputsByTier"
                ]["T2_ORDER_BOOK"].__setitem__("timeUse", "future_only"),
            ),
            (
                "normal_t3_candidate_name_allowed",
                lambda value: value["stateCandidates"][0][
                    "allowedOutputsByTier"
                ]["T3_ACCOUNT_POSITION"].__setitem__(
                    "candidateNameAllowed", True
                ),
            ),
            ("fake_relief_all_proxy_future", mutate_fake_relief),
            (
                "terminal_statuses",
                lambda value: value.__setitem__(
                    "terminalStatuses", ["identifiable", "proxy_only"]
                ),
            ),
            (
                "blank_tier_metadata",
                lambda value: value["measurementTiers"][0].__setitem__(
                    "namingConstraint", ""
                ),
            ),
            (
                "core_global_rule_reversal",
                lambda value: value["globalRules"].__setitem__(
                    "t4PermissionsAreConditionalNotCurrentEmpiricalFindings", False
                ),
            ),
        )
        for case, mutate in mutations:
            with self.subTest(case=case):
                mutated = copy.deepcopy(ontology)
                mutate(mutated)

                with self.assertRaises(AssertionError):
                    self._assert_ontology_contract(mutated)

    def test_markdown_explains_structured_ssot_and_cites_every_primary_source(self) -> None:
        ontology_markdown = (PROGRAM_DIRECTORY / "state-ontology.md").read_text(
            encoding="utf-8"
        )
        for required_text in (
            "state-ontology.json",
            "source-register.json",
            "label permutation",
            "latent_state.k",
            "통계적 식별가능성",
            "구성타당도",
            "FakeRelief",
            "미래 경로로만 판정하는 사후 결과명",
            "상태는 거래를 직접 승인하지 않는다",
            "missingObservationPolicy",
            "reject_no_zero_or_neutral_imputation",
            "결측 관측을 0, neutral, baseline으로 대체하지 않는다",
            "reweight와 renormalize를 금지한다",
        ):
            self.assertIn(required_text, ontology_markdown)
        for tier_id in EXPECTED_TIER_IDS:
            self.assertIn(tier_id, ontology_markdown)
        for candidate in EXPECTED_CANDIDATE_REGIMES:
            self.assertIn(candidate, ontology_markdown)
        for identity in EXPECTED_SOURCE_IDENTITIES:
            self.assertIn(identity[5], ontology_markdown)

        ontology = load_strict_json(PROGRAM_DIRECTORY / "state-ontology.json")
        markdown_lines = ontology_markdown.splitlines()
        for row in ontology["stateCandidates"]:
            candidate = row["stateCandidate"]
            with self.subTest(markdown_projection_candidate=candidate):
                table_line = next(
                    line
                    for line in markdown_lines
                    if line.startswith(f"| `{candidate}` |")
                )
                t0_output_name = row["allowedOutputsByTier"]["T0_OHLCV"][
                    "outputName"
                ]
                self.assertIn(f"`{t0_output_name}`", table_line)
                source_cell = table_line.split("|")[-2].strip()
                projected_source_ids = tuple(
                    token if token.startswith("SRC-") else f"SRC-{token}"
                    for token in (part.strip() for part in source_cell.split(","))
                )
                self.assertEqual(projected_source_ids, tuple(row["sourceIds"]))

    def _assert_artifact_text_is_clean(self, source: str) -> None:
        self.assertIsNone(PLACEHOLDER_PATTERN.search(source))
        self.assertEqual(find_sensitive_values(source), ())

    def test_rejects_bare_placeholder_in_artifact_text(self) -> None:
        with self.assertRaises(AssertionError):
            self._assert_artifact_text_is_clean("unfinished PLACEHOLDER content")

    def test_artifacts_have_no_placeholders_or_sensitive_values(self) -> None:
        paths = (
            QUESTION_DIRECTORY / "object.json",
            QUESTION_DIRECTORY / "question.md",
            DATASET_DIRECTORY / "object.json",
            DATASET_DIRECTORY / "data-contract.md",
            DATASET_DIRECTORY / "source-register.json",
            PROTOCOL_DIRECTORY / "object.json",
            PROTOCOL_DIRECTORY / "protocol.md",
            PROTOCOL_DIRECTORY / "protocol.sha256",
            PROGRAM_DIRECTORY / "state-ontology.md",
            PROGRAM_DIRECTORY / "state-ontology.json",
            PROGRAM_DIRECTORY / "object.json",
            TRIAL_LEDGER_PATH,
            CATALOG_PATH,
        )
        for path in paths:
            with self.subTest(path=path.relative_to(REPOSITORY_ROOT).as_posix()):
                source = path.read_text(encoding="utf-8")
                self._assert_artifact_text_is_clean(source)


if __name__ == "__main__":
    unittest.main()
