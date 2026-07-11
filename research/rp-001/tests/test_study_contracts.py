from __future__ import annotations

import copy
import hashlib
import json
import re
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rp001.sensitive_value_policy import find_sensitive_values


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
OBJECTS_ROOT = REPOSITORY_ROOT / "research" / "meta-research" / "objects"
TRIALS_ROOT = REPOSITORY_ROOT / "research" / "rp-001" / "trials"
PORTFOLIO_CONTRACT_PATH = (
    OBJECTS_ROOT
    / "programs"
    / "RP-001-quantitative-market-behavior"
    / "study-contracts.json"
)
STUDY_REGISTRY_PATH = PORTFOLIO_CONTRACT_PATH.parent / "study-registry.json"
EXPECTED_PORTFOLIO_SHA256 = (
    "c9a73212bdb4dc4bc79dc2fcec1c6b2ffdb5ff23a1879d266ea9d8d1227a9994"
)
PORTFOLIO_FIELDS = {"programId", "schemaVersion", "studies", "version"}
PORTFOLIO_RECORD_FIELDS = {
    "dataContract",
    "dataGate",
    "evidenceLevel",
    "lifecycleState",
    "missingPolicy",
    "operationalDecision",
    "primaryBaseline",
    "primaryEstimand",
    "primaryHorizon",
    "protocol",
    "question",
    "studySlot",
    "terminalStatuses",
}
PORTFOLIO_OBJECT_FIELDS = {
    "documentSha256",
    "id",
    "purpose",
    "slug",
    "title",
}
ALLOWED_TERMINAL_STATUSES = [
    "supported",
    "refuted",
    "insufficient_evidence",
    "not_identifiable",
    "data_unavailable",
    "implementation_invalid",
    "external_failure",
]
EXPECTED_DATA_GATE = (
    "수락된 raw/processed artifact의 SHA-256과 availability timestamp는 모두 "
    "존재해야 하며 하나라도 없으면 실행을 차단한다."
)
EXPECTED_MISSING_POLICY = (
    "결측 direct input을 0 또는 neutral로 대체하지 않고 남은 입력을 reweight 또는 "
    "renormalize하지 않는다."
)

DESCRIPTOR_FIELDS = {
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
}
PLACEHOLDER_PATTERN = re.compile(
    r"(?:<[^>]+>|\bTBD\b|\bTODO\b|\bPLACEHOLDER\b)", re.IGNORECASE
)
CONTRADICTIONS = (
    "결측 direct input을 0 또는 neutral로 대체하고 남은 입력을 reweight한다",
    "terminal holdout으로 threshold를 튜닝한다",
    "external OOF와 in-sample을 혼합한다",
)
COMMON_DATA_TEXT = (
    "DC-002",
    "복사하지 않는다",
    "event timestamp",
    "publication timestamp",
    "clientReceivedAt",
    "raw/processed",
    "availability timestamp",
    "모두 존재해야 하며 하나라도 없으면",
    "0 또는 neutral로 대체하지 않는다",
    "reweight 또는 renormalize하지 않는다",
    "실행을 차단",
)
COMMON_PROTOCOL_TEXT = (
    "현재 lifecycle은 `proposed`",
    "사전등록 상태가 아니며 확증 증거가 아니다",
    "자료 source acceptance와 lifecycle promotion Gate",
    "outer nested purged walk-forward",
    "inner fold에서만",
    "purge 길이는 outcome horizon 이상",
    "terminal holdout",
    "refit하지 않는다",
    "threshold를 바꾸지 않는다",
    "상태명을 바꾸지 않는다",
    "후보를 추가하지 않는다",
    "clustered moving-block bootstrap",
    "Holm family correction",
    "calibration",
    "abstain",
    "risk-coverage",
    "시점 순서 shuffle",
    "future-row invariance",
    "negative control",
    "ablation",
    "최소효과 δ",
    "비용·검정력·synthetic data",
    "lifecycle promotion 전에 동결",
    "무효 실행",
    "중단 규칙",
    "terminal status",
    (
        "terminal status는 `supported`, `refuted`, `insufficient_evidence`, "
        "`not_identifiable`, `data_unavailable`, `implementation_invalid`, "
        "`external_failure` 중 하나"
    ),
    "한 study의 terminal holdout",
    "다른 study",
    "TSLA/NVDA/MU/000660",
    "discovery/regression",
    "시장자료를 열람하지 않았다",
    "`blocked` 또는 `data_unavailable`",
    "ledger에서 삭제하지 않는다",
    "ExperimentRun과 EvidenceBundle을 생성하지 않는다",
)


def load_strict_json(path: Path) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise AssertionError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise AssertionError(f"non-standard JSON constant: {value}")

    value = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=reject_duplicates,
        parse_constant=reject_constant,
    )
    if not isinstance(value, dict):
        raise AssertionError(f"expected JSON object: {path}")
    return value


def canonical_json_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


@dataclass(frozen=True)
class ObjectContractSpec:
    id: str
    slug: str
    title: str
    purpose: str

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> ObjectContractSpec:
        return cls(
            id=record["id"],
            slug=record["slug"],
            title=record["title"],
            purpose=record["purpose"],
        )


@dataclass(frozen=True)
class MethodContract:
    embargo: str
    required_semantics: tuple[str, ...]


@dataclass(frozen=True)
class StudySpec:
    question: ObjectContractSpec
    data_contract: ObjectContractSpec
    protocol: ObjectContractSpec
    study_slot: str
    horizon: str
    lifecycle_state: str
    evidence_level: str
    version: str
    embargo: str
    required_semantics: tuple[str, ...]

    @classmethod
    def from_record(
        cls,
        record: dict[str, Any],
        method_contract: MethodContract,
        portfolio_version: str,
    ) -> StudySpec:
        return cls(
            question=ObjectContractSpec.from_record(record["question"]),
            data_contract=ObjectContractSpec.from_record(record["dataContract"]),
            protocol=ObjectContractSpec.from_record(record["protocol"]),
            study_slot=record["studySlot"],
            horizon=record["primaryHorizon"],
            lifecycle_state=record["lifecycleState"],
            evidence_level=record["evidenceLevel"],
            version=portfolio_version,
            embargo=method_contract.embargo,
            required_semantics=method_contract.required_semantics,
        )

    @property
    def rq_id(self) -> str:
        return self.question.id

    @property
    def rq_slug(self) -> str:
        return self.question.slug

    @property
    def rq_title(self) -> str:
        return self.question.title

    @property
    def rq_purpose(self) -> str:
        return self.question.purpose

    @property
    def dc_id(self) -> str:
        return self.data_contract.id

    @property
    def dc_slug(self) -> str:
        return self.data_contract.slug

    @property
    def dc_title(self) -> str:
        return self.data_contract.title

    @property
    def dc_purpose(self) -> str:
        return self.data_contract.purpose

    @property
    def sp_id(self) -> str:
        return self.protocol.id

    @property
    def sp_slug(self) -> str:
        return self.protocol.slug

    @property
    def sp_title(self) -> str:
        return self.protocol.title

    @property
    def sp_purpose(self) -> str:
        return self.protocol.purpose

    @property
    def question_directory(self) -> Path:
        return OBJECTS_ROOT / "research-questions" / f"{self.rq_id}-{self.rq_slug}"

    @property
    def dataset_directory(self) -> Path:
        return OBJECTS_ROOT / "dataset-contracts" / f"{self.dc_id}-{self.dc_slug}"

    @property
    def protocol_directory(self) -> Path:
        return OBJECTS_ROOT / "study-protocols" / f"{self.sp_id}-{self.sp_slug}"

    @property
    def trial_path(self) -> Path:
        return TRIALS_ROOT / f"{self.study_slot}.json"


METHOD_CONTRACTS = {
    "ST-BEH-001": MethodContract(
        embargo="embargo: 20 sessions",
        required_semantics=(
            "Δlog-loss",
            "human behavior claim",
            "direct attention/news exposure",
            "symbol flow",
            "options/short/borrow",
            "linked account/self-report",
            "interval outcome labels",
        ),
    ),
    "ST-VAL-001": MethodContract(
        embargo="embargo: 20 sessions",
        required_semantics=(
            "cost-adjusted excess return",
            "mean-reversion/momentum",
            "결과 후 선택하지 않는다",
            "PIT universe/membership",
            "factors/fundamentals/industry/rates/FX",
            "native/adjusted reconciliation",
            "delisting/survivorship/vintage",
            "confirmatory VAL",
        ),
    ),
    "ST-MIC-001": MethodContract(
        embargo="embargo: one full session plus 60 seconds",
        required_semantics=(
            "OFI/depth/spread/cancel/aggressor/Hawkes",
            "ordered book/trade/cancel/aggressor sequence",
            "venue clock/sequence",
            "tick/halts/message loss",
            "snapshot/recent trades",
            "대체할 수 없다",
            "currently unavailable",
        ),
    ),
    "ST-EXE-001": MethodContract(
        embargo="embargo: one full session plus 5 minutes",
        required_semantics=(
            "NetEdge=GrossEdge-Fees-Tax-FX-Slippage-Impact-Borrow/Hedge cost",
            "partial/reject",
            "decision/submit/provider-received/ack/fill/cancel/reject timestamps",
            "partial fills/queue",
            "fees/tax/FX/borrow/hedge",
            "spread/depth/impact",
            "operational adoption prohibited",
        ),
    ),
    "ST-RSK-001": MethodContract(
        embargo="embargo: 20 sessions",
        required_semantics=(
            "external OOF BEH/VAL/MIC outputs",
            "EXE cost distribution",
            "holdings/currency/correlation/stress/risk budget",
            "λ,η,α",
            "missing downstream",
        ),
    ),
    "ST-SYN-001": MethodContract(
        embargo="embargo: 20 sessions",
        required_semantics=(
            "Gate-passing external OOF",
            "protocol/run/evidence IDs",
            "uncertainty/OOD/abstain",
            "EXE cost and RSK output",
            "in-sample/holdout-selected/failed output",
        ),
    ),
}


def load_study_contract_portfolio() -> dict[str, Any]:
    portfolio = load_strict_json(PORTFOLIO_CONTRACT_PATH)
    records = portfolio.get("studies")
    if not isinstance(records, list) or not all(
        isinstance(record, dict) for record in records
    ):
        raise AssertionError("study-contracts.json studies must be JSON objects")
    return portfolio


STUDY_CONTRACT_PORTFOLIO = load_study_contract_portfolio()
PORTFOLIO_STUDY_RECORDS = tuple(STUDY_CONTRACT_PORTFOLIO["studies"])
if {record["studySlot"] for record in PORTFOLIO_STUDY_RECORDS} != set(
    METHOD_CONTRACTS
):
    raise AssertionError("method contracts must cover each portfolio study exactly once")

STUDIES = tuple(
    StudySpec.from_record(
        record,
        METHOD_CONTRACTS[record["studySlot"]],
        STUDY_CONTRACT_PORTFOLIO["version"],
    )
    for record in PORTFOLIO_STUDY_RECORDS
)


class StudyContractPortfolioTest(unittest.TestCase):
    def test_study_contract_portfolio_ssot_exists(self) -> None:
        self.assertTrue(PORTFOLIO_CONTRACT_PATH.is_file())
        portfolio = load_strict_json(PORTFOLIO_CONTRACT_PATH)
        self.assertEqual(set(portfolio), PORTFOLIO_FIELDS)
        self.assertEqual(portfolio["programId"], "RP-001")
        self.assertEqual(
            portfolio["schemaVersion"], "rp001-study-contract-portfolio.v1"
        )
        self.assertEqual(portfolio["version"], "1.0.0")
        self.assertEqual(len(portfolio["studies"]), 6)
        self.assertEqual(
            hashlib.sha256(PORTFOLIO_CONTRACT_PATH.read_bytes()).hexdigest(),
            EXPECTED_PORTFOLIO_SHA256,
        )
        self.assertEqual(
            PORTFOLIO_CONTRACT_PATH.read_bytes(), canonical_json_bytes(portfolio)
        )

        registry = load_strict_json(STUDY_REGISTRY_PATH)
        expected_registry_rows = registry["studies"][2:]
        for record, registry_row in zip(
            portfolio["studies"], expected_registry_rows, strict=True
        ):
            self._assert_portfolio_record(record, registry_row=registry_row)

    def test_rejects_six_structured_portfolio_contract_mutations(self) -> None:
        portfolio = load_strict_json(PORTFOLIO_CONTRACT_PATH)
        valid_record = portfolio["studies"][0]
        registry = load_strict_json(STUDY_REGISTRY_PATH)
        registry_row = registry["studies"][2]
        mutation_cases = (
            ("RQ ID to 999", ("question", "id"), "RQ-999"),
            (
                "SP Brier to log-loss",
                ("primaryEstimand",),
                "Δlog-loss for the predefined 5-session onset event",
            ),
            ("DC horizon 5 to 10", ("primaryHorizon",), "10 거래일"),
            (
                "missing to zero and renormalize",
                ("missingPolicy",),
                "결측값은 0으로 채우고 가용 입력을 재정규화한다.",
            ),
            ("NoTrade as terminal", ("terminalStatuses",), ["NoTrade"]),
            ("proposed to preregistered", ("lifecycleState",), "preregistered"),
        )

        for name, path, value in mutation_cases:
            mutated = copy.deepcopy(valid_record)
            target: dict[str, Any] = mutated
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            with self.subTest(mutation=name):
                with self.assertRaises(AssertionError):
                    self._assert_portfolio_record(
                        mutated,
                        registry_row=registry_row,
                        expected_record=valid_record,
                    )

    def test_all_49_study_contract_artifacts_exist(self) -> None:
        expected_paths = self._expected_artifact_paths()
        self.assertEqual(len(expected_paths), 49)
        self.assertEqual(len(set(expected_paths)), 49)
        discovered_paths: list[Path] = [PORTFOLIO_CONTRACT_PATH]
        for study in STUDIES:
            for directory in (
                study.question_directory,
                study.dataset_directory,
                study.protocol_directory,
            ):
                if directory.is_dir():
                    discovered_paths.extend(
                        path for path in directory.iterdir() if path.is_file()
                    )
            if study.trial_path.is_file():
                discovered_paths.append(study.trial_path)
        self.assertEqual(set(discovered_paths), set(expected_paths))
        missing = [
            path.relative_to(REPOSITORY_ROOT).as_posix()
            for path in expected_paths
            if not path.is_file()
        ]
        self.assertEqual(missing, [], "missing Task 7 artifacts:\n" + "\n".join(missing))

    def test_markdown_documents_are_exact_portfolio_contract_projections(self) -> None:
        portfolio = load_strict_json(PORTFOLIO_CONTRACT_PATH)
        for study, record in zip(STUDIES, portfolio["studies"], strict=True):
            for role, source in (
                ("question", (study.question_directory / "question.md").read_bytes()),
                (
                    "dataContract",
                    (study.dataset_directory / "data-contract.md").read_bytes(),
                ),
                ("protocol", (study.protocol_directory / "protocol.md").read_bytes()),
            ):
                with self.subTest(study=study.study_slot, role=role):
                    self._assert_document_projection(record, role, source)

    def test_portfolio_binds_all_18_markdown_documents_by_sha256(self) -> None:
        portfolio = load_strict_json(PORTFOLIO_CONTRACT_PATH)
        for study, record in zip(STUDIES, portfolio["studies"], strict=True):
            document_paths = (
                ("question", study.question_directory / "question.md"),
                ("dataContract", study.dataset_directory / "data-contract.md"),
                ("protocol", study.protocol_directory / "protocol.md"),
            )
            for role, path in document_paths:
                with self.subTest(study=study.study_slot, role=role):
                    self.assertEqual(
                        record[role].get("documentSha256"),
                        hashlib.sha256(path.read_bytes()).hexdigest(),
                    )

    def test_rejects_six_markdown_projection_mutations(self) -> None:
        portfolio = load_strict_json(PORTFOLIO_CONTRACT_PATH)
        behavior = STUDIES[0]
        behavior_record = portfolio["studies"][0]
        question, data_contract, protocol = self._study_documents(behavior)
        execution = STUDIES[3]
        execution_record = portfolio["studies"][3]
        execution_question = (execution.question_directory / "question.md").read_text(
            encoding="utf-8"
        )
        mutation_cases = (
            (
                "RQ ID to 999",
                behavior_record,
                "question",
                question,
                question.replace("`RQ-003`", "`RQ-999`", 1),
            ),
            (
                "SP primary Brier to log-loss",
                behavior_record,
                "protocol",
                protocol,
                protocol.replace("Brier", "log-loss", 1),
            ),
            (
                "DC horizon 5 to 10",
                behavior_record,
                "dataContract",
                data_contract,
                data_contract.replace("`5 거래일`", "`10 거래일`", 1),
            ),
            (
                "missing to zero and renormalize",
                behavior_record,
                "dataContract",
                data_contract,
                data_contract.replace(
                    EXPECTED_MISSING_POLICY,
                    "결측값은 0으로 채우고 가용 입력을 재정규화한다.",
                    1,
                ),
            ),
            (
                "NoTrade as terminal",
                execution_record,
                "question",
                execution_question,
                execution_question.replace(
                    "supported, refuted, insufficient_evidence, not_identifiable, "
                    "data_unavailable, implementation_invalid, external_failure",
                    "NoTrade",
                    1,
                ),
            ),
            (
                "proposed to preregistered",
                behavior_record,
                "protocol",
                protocol,
                protocol.replace(
                    "contract lifecycle: `proposed`",
                    "contract lifecycle: `preregistered`",
                    1,
                ),
            ),
        )
        for name, record, role, source, mutated in mutation_cases:
            with self.subTest(mutation=name):
                self._assert_document_projection(record, role, source)
                self.assertNotEqual(mutated, source)
                with self.assertRaises(AssertionError):
                    self._assert_document_projection(record, role, mutated)

    def test_rejects_five_normative_body_mutations(self) -> None:
        portfolio = load_strict_json(PORTFOLIO_CONTRACT_PATH)
        behavior_record = portfolio["studies"][0]
        behavior_protocol = (
            STUDIES[0].protocol_directory / "protocol.md"
        ).read_text(encoding="utf-8")
        execution_question = (
            STUDIES[3].question_directory / "question.md"
        ).read_text(encoding="utf-8")
        risk_record = portfolio["studies"][4]
        risk_protocol = (STUDIES[4].protocol_directory / "protocol.md").read_text(
            encoding="utf-8"
        )
        mutation_cases = (
            (
                "SP body Brier to log-loss",
                behavior_record,
                "protocol",
                behavior_protocol.replace(
                    "OOF Brier score 감소",
                    "OOF log-loss 감소",
                    1,
                ),
            ),
            (
                "missing set to zero and renormalized",
                behavior_record,
                "protocol",
                behavior_protocol
                + "\n결측값은 0으로 채우고 가용 입력을 재정규화한다.\n",
            ),
            (
                "already preregistered",
                behavior_record,
                "protocol",
                behavior_protocol + "\n이 프로토콜은 이미 사전등록을 완료했다.\n",
            ),
            (
                "NoTrade terminal status",
                portfolio["studies"][3],
                "question",
                execution_question + "\nterminal status는 NoTrade다.\n",
            ),
            (
                "risk preferences selected in inner fold",
                risk_record,
                "protocol",
                risk_protocol + "\nλ,η,α는 inner fold 성과로 선택한다.\n",
            ),
        )
        for name, record, role, mutated in mutation_cases:
            with self.subTest(mutation=name):
                with self.assertRaises(AssertionError):
                    self._assert_document_projection(record, role, mutated)

    def test_descriptors_have_exact_identity_lifecycle_dependencies_and_artifacts(self) -> None:
        self._assert_all_artifacts_exist()
        for study in STUDIES:
            for path, expected in self._expected_descriptors(study).items():
                with self.subTest(path=path.relative_to(REPOSITORY_ROOT).as_posix()):
                    self._assert_descriptor(load_strict_json(path), expected)

    def test_each_study_has_one_primary_estimand_horizon_and_terminal_semantics(self) -> None:
        self._assert_all_artifacts_exist()
        for study in STUDIES:
            question, data_contract, protocol = self._study_documents(study)
            with self.subTest(study=study.study_slot):
                self._assert_document_contract(study, question, data_contract, protocol)

    def test_each_protocol_has_required_methods_and_study_isolation(self) -> None:
        self._assert_all_artifacts_exist()
        for study in STUDIES:
            protocol = (study.protocol_directory / "protocol.md").read_text(encoding="utf-8")
            with self.subTest(study=study.study_slot):
                for required in COMMON_PROTOCOL_TEXT + (study.embargo,):
                    self.assertIn(required, protocol)
                candidate_lines = [
                    line for line in protocol.splitlines() if line.startswith("- 후보군 ")
                ]
                self.assertIn(len(candidate_lines), (2, 3))
                self.assertIn("복잡도 우선순위를 두지 않는다", protocol)
                self.assertEqual(protocol.count("주요 estimand:"), 1)
                self.assertEqual(
                    len(re.findall(r"(?m)^- primary horizon: ", protocol)), 1
                )
                combined = "\n".join(
                    (
                        (study.question_directory / "question.md").read_text(
                            encoding="utf-8"
                        ),
                        protocol,
                    )
                )
                self.assertNotIn("`not_supported`", combined)
                self.assertNotIn("`invalid`", combined)

    def test_risk_preferences_are_fixed_before_data_acceptance(self) -> None:
        risk_protocol = (STUDIES[4].protocol_directory / "protocol.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("λ,η,α는 data source acceptance 전에 고정", risk_protocol)
        self.assertNotIn("λ,η,α 후보", risk_protocol)

    def test_proposed_studies_do_not_preassign_terminal_results(self) -> None:
        for study in STUDIES[3:]:
            question = (study.question_directory / "question.md").read_text(
                encoding="utf-8"
            )
            with self.subTest(study=study.study_slot):
                self.assertIn("현재 실행 disposition: `blocked`", question)
                self.assertIn("terminal status는 미할당", question)
                self.assertNotRegex(question, r"(?m)^- terminal status:")

    def test_risk_failure_states_distinguish_control_and_data_absence(self) -> None:
        risk = STUDIES[4]
        risk_sources = (
            (risk.question_directory / "question.md").read_text(encoding="utf-8"),
            (risk.dataset_directory / "data-contract.md").read_text(
                encoding="utf-8"
            ),
            (risk.protocol_directory / "protocol.md").read_text(encoding="utf-8"),
        )
        for source in risk_sources:
            with self.subTest(document=source.splitlines()[0]):
                self.assertIn("λ,η,α 미고정", source)
                self.assertIn("promotion 전", source)
                self.assertIn("`blocked`", source)
                self.assertIn("적격 실행", source)
                self.assertIn("`implementation_invalid`", source)
                self.assertIn("실제 downstream 자료 부재", source)
                self.assertIn("`data_unavailable`", source)

    def test_protocol_sha_files_and_empty_trial_ledgers_are_bound(self) -> None:
        self._assert_all_artifacts_exist()
        hashes: set[str] = set()
        for study in STUDIES:
            protocol_path = study.protocol_directory / "protocol.md"
            protocol_source = protocol_path.read_bytes()
            protocol_text = protocol_source.decode("utf-8")
            protocol_sha256 = hashlib.sha256(protocol_source).hexdigest()
            hash_source = (study.protocol_directory / "protocol.sha256").read_bytes()
            ledger = load_strict_json(study.trial_path)
            with self.subTest(study=study.study_slot):
                self.assertRegex(hash_source, rb"^[0-9a-f]{64}\n$")
                self.assertEqual(hash_source, f"{protocol_sha256}\n".encode("ascii"))
                self.assertNotIn(protocol_sha256, protocol_text)
                self._assert_ledger(study, ledger)
                self.assertEqual(study.trial_path.read_bytes(), canonical_json_bytes(ledger))
            hashes.add(protocol_sha256)
        self.assertEqual(len(hashes), len(STUDIES))

    def test_rejects_explicit_contract_mutations(self) -> None:
        self._assert_all_artifacts_exist()
        behavior = STUDIES[0]
        question, data_contract, protocol = self._study_documents(behavior)

        with self.subTest(mutation="horizon drift"):
            mutated = question.replace(
                "- horizon: `5 거래일`",
                "- horizon: `10 거래일`",
                1,
            )
            with self.assertRaises(AssertionError):
                self._assert_document_contract(behavior, mutated, data_contract, protocol)

        descriptors = self._expected_descriptors(behavior)
        sp_path = behavior.protocol_directory / "object.json"
        sp_descriptor = load_strict_json(sp_path)
        with self.subTest(mutation="premature preregistration"):
            mutated_descriptor = copy.deepcopy(sp_descriptor)
            mutated_descriptor["lifecycleState"] = "preregistered"
            with self.assertRaises(AssertionError):
                self._assert_descriptor(mutated_descriptor, descriptors[sp_path])

        dc_path = behavior.dataset_directory / "object.json"
        dc_descriptor = load_strict_json(dc_path)
        with self.subTest(mutation="wrong DC-002 dependency"):
            mutated_descriptor = copy.deepcopy(dc_descriptor)
            mutated_descriptor["dependsOn"] = [behavior.rq_id]
            with self.assertRaises(AssertionError):
                self._assert_descriptor(mutated_descriptor, descriptors[dc_path])

        with self.subTest(mutation="missing direct input replaced"):
            mutated = data_contract + (
                "\n결측 direct input을 0 또는 neutral로 대체하고 "
                "남은 입력을 reweight한다.\n"
            )
            with self.assertRaises(AssertionError):
                self._assert_document_contract(behavior, question, mutated, protocol)

        with self.subTest(mutation="terminal holdout tuning allowed"):
            mutated = protocol + "\nterminal holdout으로 threshold를 튜닝한다.\n"
            with self.assertRaises(AssertionError):
                self._assert_document_contract(behavior, question, data_contract, mutated)

        synthesis = STUDIES[-1]
        syn_question, syn_data_contract, syn_protocol = self._study_documents(synthesis)
        with self.subTest(mutation="OOF and in-sample mixed"):
            mutated = syn_protocol + "\nexternal OOF와 in-sample을 혼합한다.\n"
            with self.assertRaises(AssertionError):
                self._assert_document_contract(
                    synthesis, syn_question, syn_data_contract, mutated
                )

        with self.subTest(mutation="cross-study ledger and protocol hash"):
            wrong_study = STUDIES[1]
            wrong_hash = hashlib.sha256(
                (wrong_study.protocol_directory / "protocol.md").read_bytes()
            ).hexdigest()
            ledger = load_strict_json(behavior.trial_path)
            ledger["protocolId"] = wrong_study.sp_id
            ledger["protocolSha256"] = wrong_hash
            with self.assertRaises(AssertionError):
                self._assert_ledger(behavior, ledger)

    def test_artifacts_are_clean_and_do_not_invent_runs_evidence_or_sensitive_values(self) -> None:
        self._assert_all_artifacts_exist()
        for path in self._expected_artifact_paths():
            with self.subTest(path=path.relative_to(REPOSITORY_ROOT).as_posix()):
                source = path.read_text(encoding="utf-8")
                self.assertIsNone(PLACEHOLDER_PATTERN.search(source))
                self.assertEqual(find_sensitive_values(source), ())
                self.assertNotIn("research/indicator-validation", source)
                self.assertNotIn(".storage", source)
                self.assertNotIn('"type":"ExperimentRun"', source)
                self.assertNotIn('"type":"EvidenceBundle"', source)

    def test_task5_and_task6_frozen_hash_pins_remain_unchanged(self) -> None:
        program_directory = (
            OBJECTS_ROOT / "programs" / "RP-001-quantitative-market-behavior"
        )
        expected_hashes = {
            program_directory / "state-ontology.json": (
                "4e11c9c3a754d542759a0e27f43d9181fa749920a41566a67895c49a71cbcaac"
            ),
            OBJECTS_ROOT
            / "dataset-contracts"
            / "DC-001-ontology-evidence"
            / "source-register.json": (
                "faadcdd8e4660f40ca050201201913250a478fb39bbf273be2ac142f356ecc2c"
            ),
            OBJECTS_ROOT / "study-protocols" / "SP-001-market-state-ontology" / "protocol.md": (
                "a180a81c1834f2319e9b16a3d851cbd28b1238c2c383ea36e6f093a203a3138e"
            ),
            OBJECTS_ROOT
            / "research-questions"
            / "RQ-002-data-lineage"
            / "question.md": (
                "371d69165b2c2baddc88e39375dd3a66497d278a5b94f44bd86908cfc862db69"
            ),
            OBJECTS_ROOT
            / "dataset-contracts"
            / "DC-002-program-data"
            / "data-contract.md": (
                "0eb5926196b5ebb1ba6f2f704430a05033336f4363482cdfa85634ecf5a0cca0"
            ),
            OBJECTS_ROOT
            / "dataset-contracts"
            / "DC-002-program-data"
            / "official-source-register.json": (
                "fe976ecd724a3a5f9e81d20804ba823a58c98d4ef1db9d1911e1cae4b4f3412d"
            ),
            OBJECTS_ROOT / "study-protocols" / "SP-002-data-lineage-audit" / "protocol.md": (
                "bbdf0603b55a5b3b18dd20cdc7f2f0161b47dffb35edeffd39026f464fe29a7e"
            ),
            program_directory / "source-matrix.json": (
                "f411dac963717aa7ed8ea1d5351ccbed70987150f6ca0e9a608d54f7677e9e61"
            ),
            program_directory / "source-matrix.md": (
                "2a6ae40a314ade6e02d90ebec10767749696e5ae2e4d2fa25dc8cae14f08428f"
            ),
        }
        self.assertEqual(len(expected_hashes), 9)
        for path, expected_hash in expected_hashes.items():
            with self.subTest(path=path.relative_to(REPOSITORY_ROOT).as_posix()):
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected_hash)

    def _assert_all_artifacts_exist(self) -> None:
        missing = [path for path in self._expected_artifact_paths() if not path.is_file()]
        self.assertEqual(missing, [])

    def _expected_artifact_paths(self) -> list[Path]:
        paths: list[Path] = [PORTFOLIO_CONTRACT_PATH]
        for study in STUDIES:
            paths.extend(
                (
                    study.question_directory / "object.json",
                    study.question_directory / "question.md",
                    study.dataset_directory / "object.json",
                    study.dataset_directory / "data-contract.md",
                    study.protocol_directory / "object.json",
                    study.protocol_directory / "protocol.md",
                    study.protocol_directory / "protocol.sha256",
                    study.trial_path,
                )
            )
        return paths

    def _expected_descriptors(self, study: StudySpec) -> dict[Path, dict[str, Any]]:
        question_root = f"research/meta-research/objects/research-questions/{study.rq_id}-{study.rq_slug}"
        data_root = f"research/meta-research/objects/dataset-contracts/{study.dc_id}-{study.dc_slug}"
        protocol_root = f"research/meta-research/objects/study-protocols/{study.sp_id}-{study.sp_slug}"
        trial_artifact = f"research/rp-001/trials/{study.study_slot}.json"
        common = {
            "schemaVersion": "research-object.v1",
            "version": study.version,
            "lifecycleState": study.lifecycle_state,
            "evidenceLevel": study.evidence_level,
        }
        return {
            study.question_directory / "object.json": {
                **common,
                "id": study.rq_id,
                "type": "ResearchQuestion",
                "title": study.rq_title,
                "purpose": study.rq_purpose,
                "dependsOn": ["RP-001"],
                "artifacts": [f"{question_root}/question.md"],
            },
            study.dataset_directory / "object.json": {
                **common,
                "id": study.dc_id,
                "type": "DatasetContract",
                "title": study.dc_title,
                "purpose": study.dc_purpose,
                "dependsOn": ["DC-002", study.rq_id],
                "artifacts": [f"{data_root}/data-contract.md"],
            },
            study.protocol_directory / "object.json": {
                **common,
                "id": study.sp_id,
                "type": "StudyProtocol",
                "title": study.sp_title,
                "purpose": study.sp_purpose,
                "dependsOn": [study.dc_id, study.rq_id],
                "artifacts": [
                    f"{protocol_root}/protocol.md",
                    f"{protocol_root}/protocol.sha256",
                    trial_artifact,
                ],
            },
        }

    def _assert_descriptor(
        self, actual: dict[str, Any], expected: dict[str, Any]
    ) -> None:
        self.assertEqual(set(actual), DESCRIPTOR_FIELDS)
        self.assertEqual(actual, expected)

    def _study_documents(self, study: StudySpec) -> tuple[str, str, str]:
        return (
            (study.question_directory / "question.md").read_text(encoding="utf-8"),
            (study.dataset_directory / "data-contract.md").read_text(encoding="utf-8"),
            (study.protocol_directory / "protocol.md").read_text(encoding="utf-8"),
        )

    def _assert_document_contract(
        self,
        study: StudySpec,
        question: str,
        data_contract: str,
        protocol: str,
    ) -> None:
        self.assertEqual(question.count("주요 estimand:"), 1)
        self.assertEqual(len(re.findall(r"(?m)^- horizon: ", question)), 1)
        self.assertRegex(
            question,
            rf"(?m)^- horizon: `{re.escape(study.horizon)}`$",
        )
        self.assertEqual(protocol.count("주요 estimand:"), 1)
        self.assertEqual(
            len(re.findall(r"(?m)^- primary horizon: ", protocol)),
            1,
        )
        self.assertRegex(
            protocol,
            rf"(?m)^- primary horizon: `{re.escape(study.horizon)}`$",
        )
        combined = "\n".join((question, data_contract, protocol))
        for required in study.required_semantics:
            self.assertIn(required, combined)
        for required in COMMON_DATA_TEXT:
            self.assertIn(required, data_contract)
        for required in COMMON_PROTOCOL_TEXT + (study.embargo,):
            self.assertIn(required, protocol)
        for contradiction in CONTRADICTIONS:
            self.assertNotIn(contradiction, combined)
        self.assertNotRegex(
            combined,
            r"(?:`data_unavailable`과 NoTrade를 terminal status|"
            r"terminal status:[^\n]*(?:NoTrade|no integration)|"
            r"`data_unavailable`로 중단하고[^\n]*(?:NoTrade|no integration)|"
            r"`data_unavailable`(?:이며|,|와)[^\n]{0,60}(?:NoTrade|no integration)|"
            r"(?:NoTrade|no integration)[^\n]{0,60}(?:와|,)\s*`data_unavailable`)",
        )
        if study.rq_id == "RQ-003":
            for prohibited_baseline in (
                "가격·거래량 이력만 쓰는 기준선",
                "가격·거래량 전용 기준선",
                "가격·거래량·변동성만 쓰는 `price_volume_regime` 기준선",
            ):
                self.assertNotIn(prohibited_baseline, combined)

    def _assert_document_projection(
        self,
        record: dict[str, Any],
        object_role: str,
        source: str | bytes,
    ) -> None:
        source_bytes = source.encode("utf-8") if isinstance(source, str) else source
        self.assertEqual(
            hashlib.sha256(source_bytes).hexdigest(),
            record[object_role]["documentSha256"],
        )
        source_text = source_bytes.decode("utf-8")
        self._assert_document_identity(record, object_role, source_text)
        marker = "## 구조화 계약 projection\n"
        _, separator, remainder = source_text.partition(marker)
        self.assertEqual(separator, marker)
        projection_source = remainder.split("\n## ", 1)[0]
        projection: dict[str, str] = {}
        for line in projection_source.splitlines():
            if not line.startswith("- contract "):
                continue
            label, separator, value = line[2:].partition(": ")
            self.assertEqual(separator, ": ")
            self.assertNotIn(label, projection)
            projection[label] = value

        expected = {
            "contract data gate": record["dataGate"],
            "contract evidence level": f"`{record['evidenceLevel']}`",
            "contract lifecycle": f"`{record['lifecycleState']}`",
            "contract missing policy": record["missingPolicy"],
            "contract object id": f"`{record[object_role]['id']}`",
            "contract operational decision": record["operationalDecision"],
            "contract primary baseline": record["primaryBaseline"],
            "contract primary estimand": record["primaryEstimand"],
            "contract primary horizon": f"`{record['primaryHorizon']}`",
            "contract study slot": f"`{record['studySlot']}`",
            "contract terminal statuses": ", ".join(record["terminalStatuses"]),
        }
        self.assertEqual(projection, expected)

    def _assert_document_identity(
        self,
        record: dict[str, Any],
        object_role: str,
        source: str,
    ) -> None:
        self.assertRegex(
            source,
            rf"(?m)^- 객체 ID: `{re.escape(record[object_role]['id'])}`$",
        )
        study_label = "study slot" if object_role == "protocol" else "적용 study"
        self.assertRegex(
            source,
            rf"(?m)^- {study_label}: `{re.escape(record['studySlot'])}`$",
        )
        if object_role == "question":
            self.assertRegex(
                source,
                rf"(?m)^- (?:자료계약|DatasetContract): `{record['dataContract']['id']}`$",
            )
            self.assertRegex(
                source,
                rf"(?m)^- (?:연구 프로토콜|StudyProtocol): `{record['protocol']['id']}`$",
            )
        if object_role == "dataContract":
            self.assertRegex(
                source,
                rf"(?m)^- 적용 질문: `{record['question']['id']}`$",
            )
        if object_role == "protocol":
            self.assertRegex(
                source,
                rf"(?m)^- 연구질문: `{record['question']['id']}`$",
            )
            self.assertRegex(
                source,
                rf"(?m)^- (?:자료계약|DatasetContract): `{record['dataContract']['id']}`$",
            )

    def _assert_ledger(self, study: StudySpec, ledger: dict[str, Any]) -> None:
        protocol_sha256 = hashlib.sha256(
            (study.protocol_directory / "protocol.md").read_bytes()
        ).hexdigest()
        self.assertEqual(
            ledger,
            {
                "protocolId": study.sp_id,
                "protocolSha256": protocol_sha256,
                "runs": [],
                "schemaVersion": "rp001-trial-ledger.v1",
                "studySlot": study.study_slot,
            },
        )

    def _assert_portfolio_record(
        self,
        record: dict[str, Any],
        *,
        registry_row: dict[str, Any],
        expected_record: dict[str, Any] | None = None,
    ) -> None:
        self.assertIsInstance(record, dict)
        self.assertEqual(set(record), PORTFOLIO_RECORD_FIELDS)
        if expected_record is not None:
            self.assertEqual(record, expected_record)

        expected_ids = {
            "dataContract": registry_row["datasetContractId"],
            "protocol": registry_row["protocolId"],
            "question": registry_row["questionId"],
        }
        for object_role, expected_id in expected_ids.items():
            object_contract = record[object_role]
            self.assertIsInstance(object_contract, dict)
            self.assertEqual(set(object_contract), PORTFOLIO_OBJECT_FIELDS)
            self.assertEqual(object_contract["id"], expected_id)
            self.assertRegex(object_contract["id"], r"^[A-Z]{2}-[0-9]{3}$")
            self.assertIsInstance(object_contract["documentSha256"], str)
            self.assertRegex(object_contract["documentSha256"], r"^[0-9a-f]{64}$")
            for field in ("purpose", "slug", "title"):
                self.assertIsInstance(object_contract[field], str)
                self.assertTrue(object_contract[field].strip())

        self.assertEqual(record["studySlot"], registry_row["studySlot"])
        self.assertEqual(record["lifecycleState"], "proposed")
        self.assertEqual(record["evidenceLevel"], "conceptual")
        self.assertEqual(record["dataGate"], EXPECTED_DATA_GATE)
        self.assertEqual(record["missingPolicy"], EXPECTED_MISSING_POLICY)
        self.assertEqual(record["terminalStatuses"], ALLOWED_TERMINAL_STATUSES)
        for field in (
            "operationalDecision",
            "primaryBaseline",
            "primaryEstimand",
            "primaryHorizon",
        ):
            self.assertIsInstance(record[field], str)
            self.assertTrue(record[field].strip())
        self.assertNotIn(record["operationalDecision"], record["terminalStatuses"])


if __name__ == "__main__":
    unittest.main()
