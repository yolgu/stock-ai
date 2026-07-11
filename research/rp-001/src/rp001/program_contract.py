from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn


class ProgramContractError(ValueError):
    """Raised when the RP-001 foundation contract is invalid."""


@dataclass(frozen=True)
class FoundationValidationReport:
    requirement_count: int
    source_requirement_coverage: float
    study_slot_coverage: float
    candidate_family_coverage: float

    def to_canonical_dict(self) -> dict[str, float | int]:
        return {
            "candidateFamilyCoverage": self.candidate_family_coverage,
            "requirementCount": self.requirement_count,
            "sourceRequirementCoverage": self.source_requirement_coverage,
            "studySlotCoverage": self.study_slot_coverage,
        }


@dataclass(frozen=True)
class RequirementRecord:
    identifier: str


@dataclass(frozen=True)
class StudyContract:
    study_slot: str
    question_id: str
    dataset_contract_id: str
    protocol_id: str
    trial_ledger_path: str


_REQUIRED_STUDY_CONTRACTS = (
    StudyContract(
        study_slot="ST-ONT-001",
        question_id="RQ-001",
        dataset_contract_id="DC-001",
        protocol_id="SP-001",
        trial_ledger_path="research/rp-001/trials/ST-ONT-001.json",
    ),
    StudyContract(
        study_slot="ST-DAT-001",
        question_id="RQ-002",
        dataset_contract_id="DC-002",
        protocol_id="SP-002",
        trial_ledger_path="research/rp-001/trials/ST-DAT-001.json",
    ),
    StudyContract(
        study_slot="ST-BEH-001",
        question_id="RQ-003",
        dataset_contract_id="DC-003",
        protocol_id="SP-003",
        trial_ledger_path="research/rp-001/trials/ST-BEH-001.json",
    ),
    StudyContract(
        study_slot="ST-VAL-001",
        question_id="RQ-004",
        dataset_contract_id="DC-004",
        protocol_id="SP-004",
        trial_ledger_path="research/rp-001/trials/ST-VAL-001.json",
    ),
    StudyContract(
        study_slot="ST-MIC-001",
        question_id="RQ-005",
        dataset_contract_id="DC-005",
        protocol_id="SP-005",
        trial_ledger_path="research/rp-001/trials/ST-MIC-001.json",
    ),
    StudyContract(
        study_slot="ST-EXE-001",
        question_id="RQ-006",
        dataset_contract_id="DC-006",
        protocol_id="SP-006",
        trial_ledger_path="research/rp-001/trials/ST-EXE-001.json",
    ),
    StudyContract(
        study_slot="ST-RSK-001",
        question_id="RQ-007",
        dataset_contract_id="DC-007",
        protocol_id="SP-007",
        trial_ledger_path="research/rp-001/trials/ST-RSK-001.json",
    ),
    StudyContract(
        study_slot="ST-SYN-001",
        question_id="RQ-008",
        dataset_contract_id="DC-008",
        protocol_id="SP-008",
        trial_ledger_path="research/rp-001/trials/ST-SYN-001.json",
    ),
)
_REQUIRED_STUDY_CONTRACT_BY_SLOT = {
    contract.study_slot: contract for contract in _REQUIRED_STUDY_CONTRACTS
}


@dataclass(frozen=True)
class CandidateRegistration:
    family: str
    status: str
    object_id: str | None


class ProgramContractValidator:
    REQUIREMENTS_SCHEMA_VERSION = "rp001-requirements.v1"
    TRACEABILITY_SCHEMA_VERSION = "rp001-traceability.v1"
    STUDY_REGISTRY_SCHEMA_VERSION = "rp001-study-registry.v1"
    CANDIDATE_REGISTRY_SCHEMA_VERSION = "rp001-candidate-registry.v1"
    SEEN_DATA_REGISTER_SCHEMA_VERSION = "rp001-seen-data-register.v1"
    REQUIRED_GOAL_ID = "GOAL-RP-001"
    REQUIRED_GOAL_VERSION = "1.0"
    REQUIRED_SOURCE_SHA256 = (
        "089ee3236ad913388106d0b569cc931e451d6be661c55ee62c2993f093afaad3"
    )
    REQUIRED_GOAL_COPY_SHA256 = (
        "542160cbad66426db09eb8ec6741c48464a9d80a3a6be2fd71ab1871f8f55594"
    )
    REQUIRED_GOAL_COPY_SIZE_BYTES = 13_876
    REQUIRED_GOAL_LOGICAL_LINES = 392
    REQUIRED_REQUIREMENT_COUNT = 254
    REQUIRED_REQUIREMENTS_SHA256 = (
        "852a8efa16be0554856aea2d6dd5cb0230bb112e96a36bac6543406a2622917e"
    )
    REQUIRED_TRACE_PROJECTION_SHA256 = (
        "88d5c0dbde20480374687ad5dc43585cac513fd116135fd490f390fd38073789"
    )
    REQUIRED_SEEN_DATA_REGISTER_SHA256 = (
        "a68b770245251795651a203e202cdfc46ce40802bdbf9d277ee2cffa21c7ad9a"
    )
    REQUIRED_STUDY_CONTRACTS = _REQUIRED_STUDY_CONTRACTS
    REQUIRED_STUDY_SLOTS = tuple(_REQUIRED_STUDY_CONTRACT_BY_SLOT)
    REQUIRED_CANDIDATE_FAMILIES = (
        "unconditional",
        "simple_price_volume",
        "legacy_weighted_sum",
        "repair_candidate",
        "bayesian_competing_risk",
        "hmm_hsmm",
        "dynamic_relative_value",
        "prospect_reference_price",
        "ofi_depth_hawkes",
        "execution_control",
        "nonlinear",
    )
    REQUIRED_RP_DEPENDENCIES = frozenset({"MC-001", "MS-001", "RB-001"})
    REQUIRED_RP_ARTIFACTS = frozenset(
        {
            "research/meta-research/objects/programs/"
            "RP-001-quantitative-market-behavior/README.md",
            "research/meta-research/objects/programs/"
            "RP-001-quantitative-market-behavior/candidate-registry.json",
            "research/meta-research/objects/programs/"
            "RP-001-quantitative-market-behavior/goal-v1.0.md",
            "research/meta-research/objects/programs/"
            "RP-001-quantitative-market-behavior/integration-contract.md",
            "research/meta-research/objects/programs/"
            "RP-001-quantitative-market-behavior/question-map.md",
            "research/meta-research/objects/programs/"
            "RP-001-quantitative-market-behavior/requirements.json",
            "research/meta-research/objects/programs/"
            "RP-001-quantitative-market-behavior/seen-data-register.json",
            "research/meta-research/objects/programs/"
            "RP-001-quantitative-market-behavior/study-portfolio.md",
            "research/meta-research/objects/programs/"
            "RP-001-quantitative-market-behavior/study-registry.json",
            "research/meta-research/objects/programs/"
            "RP-001-quantitative-market-behavior/traceability.json",
        }
    )
    _REQUIREMENT_ID_PATTERN = re.compile(r"^REQ-[0-9]{3}$")
    _STUDY_SLOT_PATTERN = re.compile(r"^ST-[A-Z]{3}-[0-9]{3}$")
    _OBJECT_ID_PATTERN = re.compile(r"^[A-Z]{2,4}-[0-9]{3}$")
    _FAMILY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
    _LEDGER_SCHEMA_VERSIONS = {
        "requirements.json": REQUIREMENTS_SCHEMA_VERSION,
        "traceability.json": TRACEABILITY_SCHEMA_VERSION,
        "study-registry.json": STUDY_REGISTRY_SCHEMA_VERSION,
        "candidate-registry.json": CANDIDATE_REGISTRY_SCHEMA_VERSION,
        "seen-data-register.json": SEEN_DATA_REGISTER_SCHEMA_VERSION,
    }
    _CANONICAL_LEDGER_FILENAMES = frozenset(_LEDGER_SCHEMA_VERSIONS)
    _LEDGER_FIELDS = {
        "requirements.json": frozenset(
            {
                "schemaVersion",
                "goalId",
                "goalVersion",
                "sourceSha256",
                "requirements",
            }
        ),
        "traceability.json": frozenset({"schemaVersion", "traceability"}),
        "study-registry.json": frozenset({"schemaVersion", "studies"}),
        "candidate-registry.json": frozenset({"schemaVersion", "candidates"}),
        "seen-data-register.json": frozenset(
            {"schemaVersion", "baselineId", "entries"}
        ),
    }
    _REQUIREMENT_FIELDS = frozenset(
        {"id", "sourceSection", "sourceLines", "category", "text"}
    )
    _TRACE_FIELDS = frozenset(
        {
            "sourceRequirementId",
            "questionIds",
            "studySlots",
            "evidenceIds",
            "decisionIds",
            "reportPaths",
        }
    )
    _STUDY_CHAIN_FIELDS = frozenset(
        {
            "studySlot",
            "questionId",
            "datasetContractId",
            "protocolId",
            "trialLedgerPath",
        }
    )
    _CANDIDATE_STATUSES = frozenset({"registry_only", "object_registered"})
    _REGISTRY_ONLY_CANDIDATE_FIELDS = frozenset({"family", "status"})
    _OBJECT_REGISTERED_CANDIDATE_FIELDS = frozenset(
        {"family", "status", "objectId"}
    )
    _REQUIRED_STUDY_CONTRACT_BY_SLOT = _REQUIRED_STUDY_CONTRACT_BY_SLOT
    _OBJECT_REGISTERED_CANDIDATE_FAMILY = "bayesian_competing_risk"
    _OBJECT_REGISTERED_CANDIDATE_ID = "MC-001"

    def __init__(self, program_directory: Path) -> None:
        self._program_directory = program_directory.resolve()

    def validate_foundation(self) -> FoundationValidationReport:
        self._validate_goal_copy()
        requirements = self._read_requirements()
        traced_requirement_ids = self._read_traceability(requirements)
        studies = self._read_study_registry()
        candidates = self._read_candidate_registry()
        self._read_seen_data_register()
        self._validate_program_descriptor()
        requirement_ids = {requirement.identifier for requirement in requirements}
        return FoundationValidationReport(
            requirement_count=len(requirements),
            source_requirement_coverage=(
                len(traced_requirement_ids) / len(requirement_ids)
            ),
            study_slot_coverage=len(studies) / len(self.REQUIRED_STUDY_SLOTS),
            candidate_family_coverage=(
                len(candidates) / len(self.REQUIRED_CANDIDATE_FAMILIES)
            ),
        )

    def _read_requirements(self) -> tuple[RequirementRecord, ...]:
        document = self._load_document("requirements.json")
        self._validate_schema_version(document, "requirements.json")
        self._validate_requirements_metadata(document)
        self._require_exact_keys(
            document,
            self._LEDGER_FIELDS["requirements.json"],
            "requirements.json",
        )
        values = self._require_list(document.get("requirements"), "requirements")
        if not values:
            raise ProgramContractError("requirements must not be empty")
        identifiers: list[str] = []
        source_ranges: list[tuple[int, int]] = []
        records: list[RequirementRecord] = []
        for value in values:
            if not isinstance(value, dict):
                raise ProgramContractError("requirement must be an object")
            identifier = self._require_text(value.get("id"), "requirement id")
            if self._REQUIREMENT_ID_PATTERN.fullmatch(identifier) is None:
                raise ProgramContractError(f"invalid requirement id: {identifier}")
            source_section = value.get("sourceSection")
            if not isinstance(source_section, str) or not source_section.strip():
                raise ProgramContractError("blank requirement sourceSection")
            text = value.get("text")
            if not isinstance(text, str) or not text.strip():
                raise ProgramContractError("blank requirement text")
            self._require_text(value.get("category"), "requirement category")
            source_ranges.append(
                self._validate_source_lines(value.get("sourceLines"), identifier)
            )
            self._require_exact_keys(value, self._REQUIREMENT_FIELDS, "requirement")
            identifiers.append(identifier)
            records.append(RequirementRecord(identifier=identifier))
        if len(set(identifiers)) != len(identifiers):
            raise ProgramContractError("duplicate requirement id")
        expected = [f"REQ-{index:03d}" for index in range(1, len(identifiers) + 1)]
        if sorted(identifiers) != expected:
            raise ProgramContractError("nonsequential requirement ids")
        if identifiers != expected:
            raise ProgramContractError("unsorted requirement ids")
        if len(identifiers) != self.REQUIRED_REQUIREMENT_COUNT:
            raise ProgramContractError("invalid frozen requirement count")
        if any(
            current_range < previous_range
            for previous_range, current_range in zip(
                source_ranges,
                source_ranges[1:],
            )
        ):
            raise ProgramContractError("nondecreasing requirement sourceLines required")
        if self._sha256_canonical(document) != self.REQUIRED_REQUIREMENTS_SHA256:
            raise ProgramContractError("frozen requirements drift")
        return tuple(records)

    def _validate_source_lines(
        self,
        value: Any,
        identifier: str,
    ) -> tuple[int, int]:
        if (
            not isinstance(value, list)
            or len(value) != 2
            or any(
                not isinstance(line, int) or isinstance(line, bool) or line <= 0
                for line in value
            )
            or value[0] > value[1]
            or value[1] > self.REQUIRED_GOAL_LOGICAL_LINES
        ):
            raise ProgramContractError(
                f"invalid requirement sourceLines: {identifier}"
            )
        return value[0], value[1]

    def _read_traceability(
        self,
        requirements: tuple[RequirementRecord, ...],
    ) -> frozenset[str]:
        document = self._load_document("traceability.json")
        self._validate_schema_version(document, "traceability.json")
        self._require_exact_keys(
            document,
            self._LEDGER_FIELDS["traceability.json"],
            "traceability.json",
        )
        rows = self._require_list(document.get("traceability"), "traceability")
        requirement_ids = {requirement.identifier for requirement in requirements}
        traced_ids: list[str] = []
        frozen_projection: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict) or not self._TRACE_FIELDS.issubset(row):
                raise ProgramContractError("incomplete traceability row")
            self._require_exact_keys(row, self._TRACE_FIELDS, "traceability row")
            requirement_id = self._require_text(
                row.get("sourceRequirementId"),
                "sourceRequirementId",
            )
            if requirement_id not in requirement_ids:
                raise ProgramContractError(
                    f"unknown traceability requirement: {requirement_id}"
                )
            self._validate_trace_ids(row)
            traced_ids.append(requirement_id)
            frozen_projection.append(
                {
                    "sourceRequirementId": requirement_id,
                    "questionIds": row["questionIds"],
                    "studySlots": row["studySlots"],
                }
            )
        if len(set(traced_ids)) != len(traced_ids):
            raise ProgramContractError("duplicate traceability requirement")
        missing = requirement_ids - set(traced_ids)
        if missing:
            raise ProgramContractError(
                f"missing traceability requirement: {', '.join(sorted(missing))}"
            )
        expected_order = tuple(
            requirement.identifier for requirement in requirements
        )
        if tuple(traced_ids) != expected_order:
            raise ProgramContractError(
                "traceability rows must follow requirement order"
            )
        if (
            self._sha256_canonical(frozen_projection)
            != self.REQUIRED_TRACE_PROJECTION_SHA256
        ):
            raise ProgramContractError("frozen traceability mapping drift")
        return frozenset(traced_ids)

    def _validate_trace_ids(self, row: dict[str, Any]) -> None:
        question_ids = self._require_list(row.get("questionIds"), "questionIds")
        study_slots = self._require_list(row.get("studySlots"), "studySlots")
        if not question_ids or not study_slots:
            raise ProgramContractError("incomplete traceability row")
        validated_question_ids = [
            self._validate_object_id(identifier) for identifier in question_ids
        ]
        self._require_unique_trace_references(
            validated_question_ids,
            "questionIds",
        )
        validated_study_slots: list[str] = []
        for study_slot in study_slots:
            if (
                not isinstance(study_slot, str)
                or self._STUDY_SLOT_PATTERN.fullmatch(study_slot) is None
            ):
                raise ProgramContractError(f"invalid study slot id: {study_slot}")
            validated_study_slots.append(study_slot)
        self._require_unique_trace_references(
            validated_study_slots,
            "studySlots",
        )
        required_question_ids: set[str] = set()
        for study_slot in validated_study_slots:
            contract = self._REQUIRED_STUDY_CONTRACT_BY_SLOT.get(study_slot)
            if contract is None:
                raise ProgramContractError(
                    f"unknown traceability study slot: {study_slot}"
                )
            required_question_ids.add(contract.question_id)
        if set(validated_question_ids) != required_question_ids:
            raise ProgramContractError(
                "traceability questionIds do not match studySlots"
            )
        for field in ("evidenceIds", "decisionIds"):
            for identifier in self._require_list(row.get(field), field):
                self._validate_object_id(identifier)
        for path in self._require_list(row.get("reportPaths"), "reportPaths"):
            self._validate_relative_path(path, "report path")

    def _read_study_registry(self) -> tuple[StudyContract, ...]:
        document = self._load_document("study-registry.json")
        self._validate_schema_version(document, "study-registry.json")
        self._require_exact_keys(
            document,
            self._LEDGER_FIELDS["study-registry.json"],
            "study-registry.json",
        )
        values = self._require_list(document.get("studies"), "studies")
        contracts: list[StudyContract] = []
        for value in values:
            if not isinstance(value, dict) or not self._STUDY_CHAIN_FIELDS.issubset(value):
                raise ProgramContractError("incomplete study contract")
            self._require_exact_keys(value, self._STUDY_CHAIN_FIELDS, "study contract")
            study_slot = self._require_text(value.get("studySlot"), "studySlot")
            if self._STUDY_SLOT_PATTERN.fullmatch(study_slot) is None:
                raise ProgramContractError(f"invalid study slot id: {study_slot}")
            question_id = self._validate_object_id(value.get("questionId"))
            dataset_contract_id = self._validate_object_id(
                value.get("datasetContractId")
            )
            protocol_id = self._validate_object_id(value.get("protocolId"))
            trial_ledger_path = self._require_text(
                value.get("trialLedgerPath"),
                "trialLedgerPath",
            )
            expected_path = f"research/rp-001/trials/{study_slot}.json"
            if trial_ledger_path != expected_path:
                raise ProgramContractError(
                    f"invalid trial ledger path: {trial_ledger_path}"
                )
            contracts.append(
                StudyContract(
                    study_slot=study_slot,
                    question_id=question_id,
                    dataset_contract_id=dataset_contract_id,
                    protocol_id=protocol_id,
                    trial_ledger_path=trial_ledger_path,
                )
            )
        study_slots = [contract.study_slot for contract in contracts]
        if (
            len(set(study_slots)) != len(study_slots)
            or set(study_slots) != set(self.REQUIRED_STUDY_SLOTS)
        ):
            raise ProgramContractError("invalid required study slots")
        if tuple(study_slots) != self.REQUIRED_STUDY_SLOTS:
            raise ProgramContractError("invalid required study order")
        if set(contracts) != set(self.REQUIRED_STUDY_CONTRACTS):
            raise ProgramContractError("invalid required study contract")
        return tuple(contracts)

    def _read_candidate_registry(self) -> tuple[CandidateRegistration, ...]:
        document = self._load_document("candidate-registry.json")
        self._validate_schema_version(document, "candidate-registry.json")
        self._require_exact_keys(
            document,
            self._LEDGER_FIELDS["candidate-registry.json"],
            "candidate-registry.json",
        )
        values = self._require_list(document.get("candidates"), "candidates")
        registrations: list[CandidateRegistration] = []
        for value in values:
            if not isinstance(value, dict):
                raise ProgramContractError("candidate registration must be an object")
            family = self._require_text(value.get("family"), "candidate family")
            if self._FAMILY_PATTERN.fullmatch(family) is None:
                raise ProgramContractError(f"invalid candidate family: {family}")
            status = self._require_text(value.get("status"), "candidate status")
            if status not in self._CANDIDATE_STATUSES:
                raise ProgramContractError(f"invalid candidate status: {status}")
            has_object_id = "objectId" in value
            requires_object_id = status == "object_registered"
            if has_object_id != requires_object_id:
                raise ProgramContractError(
                    "candidate objectId does not match status"
                )
            expected_fields = (
                self._OBJECT_REGISTERED_CANDIDATE_FIELDS
                if requires_object_id
                else self._REGISTRY_ONLY_CANDIDATE_FIELDS
            )
            self._require_exact_keys(
                value,
                expected_fields,
                "candidate registration",
            )
            object_id = (
                self._validate_object_id(value.get("objectId"))
                if requires_object_id
                else None
            )
            registration = CandidateRegistration(
                family=family,
                status=status,
                object_id=object_id,
            )
            self._validate_required_candidate_registration(registration)
            registrations.append(registration)
        families = [registration.family for registration in registrations]
        if (
            len(set(families)) != len(families)
            or set(families) != set(self.REQUIRED_CANDIDATE_FAMILIES)
        ):
            raise ProgramContractError("invalid required candidate families")
        if tuple(families) != self.REQUIRED_CANDIDATE_FAMILIES:
            raise ProgramContractError("invalid required candidate order")
        return tuple(registrations)

    def _validate_required_candidate_registration(
        self,
        registration: CandidateRegistration,
    ) -> None:
        if registration.family == self._OBJECT_REGISTERED_CANDIDATE_FAMILY:
            valid = (
                registration.status == "object_registered"
                and registration.object_id == self._OBJECT_REGISTERED_CANDIDATE_ID
            )
        else:
            valid = (
                registration.status == "registry_only"
                and registration.object_id is None
            )
        if not valid:
            raise ProgramContractError("invalid required candidate registration")

    def _read_seen_data_register(self) -> None:
        document = self._load_document("seen-data-register.json")
        self._validate_schema_version(document, "seen-data-register.json")
        self._require_exact_keys(
            document,
            self._LEDGER_FIELDS["seen-data-register.json"],
            "seen-data-register.json",
        )
        if document.get("baselineId") != "RB-001":
            raise ProgramContractError("frozen seen-data register drift")
        entries = self._require_list(document.get("entries"), "seen-data entries")
        if len(entries) != 11:
            raise ProgramContractError("frozen seen-data register drift")
        if (
            self._sha256_canonical(document)
            != self.REQUIRED_SEEN_DATA_REGISTER_SHA256
        ):
            raise ProgramContractError("frozen seen-data register drift")

    def _validate_goal_copy(self) -> None:
        goal_path = self._program_directory / "goal-v1.0.md"
        try:
            source = goal_path.read_bytes()
        except OSError as error:
            raise ProgramContractError("invalid frozen goal copy") from error
        is_exact_copy = (
            len(source) == self.REQUIRED_GOAL_COPY_SIZE_BYTES
            and len(source.splitlines()) == self.REQUIRED_GOAL_LOGICAL_LINES
            and source.endswith(b"\n")
            and hashlib.sha256(source).hexdigest()
            == self.REQUIRED_GOAL_COPY_SHA256
        )
        if not is_exact_copy:
            raise ProgramContractError("invalid frozen goal copy")

    def _validate_program_descriptor(self) -> None:
        value = self._load_json(self._program_directory / "object.json")
        if not isinstance(value, dict):
            raise ProgramContractError("object.json must contain a JSON object")
        if (
            value.get("schemaVersion") != "research-object.v1"
            or value.get("id") != "RP-001"
            or value.get("type") != "ResearchProgram"
        ):
            raise ProgramContractError("invalid RP object identity")
        if (
            value.get("lifecycleState") != "proposed"
            or value.get("evidenceLevel") != "conceptual"
        ):
            raise ProgramContractError("invalid RP foundation status")
        dependencies = frozenset(
            self._validate_object_id(dependency)
            for dependency in self._require_list(
                value.get("dependsOn"),
                "RP dependencies",
            )
        )
        artifacts = frozenset(
            self._validate_relative_path(artifact, "RP artifact path")
            for artifact in self._require_list(
                value.get("artifacts"),
                "RP artifacts",
            )
        )
        if (
            not self.REQUIRED_RP_DEPENDENCIES.issubset(dependencies)
            or not self.REQUIRED_RP_ARTIFACTS.issubset(artifacts)
        ):
            raise ProgramContractError("missing RP foundation binding")
        if any(
            not (self._program_directory / Path(artifact).name).is_file()
            for artifact in self.REQUIRED_RP_ARTIFACTS
        ):
            raise ProgramContractError("missing RP foundation artifact")

    @staticmethod
    def _require_unique_trace_references(
        references: list[str],
        label: str,
    ) -> None:
        if len(references) != len(set(references)):
            raise ProgramContractError(f"duplicate traceability {label}")

    def _load_document(self, filename: str) -> dict[str, Any]:
        path = self._program_directory / filename
        value = self._load_json(path)
        if not isinstance(value, dict):
            raise ProgramContractError(f"{filename} must contain a JSON object")
        if filename in self._CANONICAL_LEDGER_FILENAMES:
            try:
                source = path.read_bytes()
            except OSError as error:
                raise ProgramContractError(f"invalid JSON file: {path}: {error}") from error
            if source != self._canonical_json_bytes(value):
                raise ProgramContractError(f"{filename} is not canonical JSON")
        return value

    def _validate_schema_version(
        self,
        document: dict[str, Any],
        filename: str,
    ) -> None:
        if document.get("schemaVersion") != self._LEDGER_SCHEMA_VERSIONS[filename]:
            raise ProgramContractError(f"invalid {filename} schemaVersion")

    def _validate_requirements_metadata(self, document: dict[str, Any]) -> None:
        if document.get("goalId") != self.REQUIRED_GOAL_ID:
            raise ProgramContractError("invalid requirements goalId")
        if document.get("goalVersion") != self.REQUIRED_GOAL_VERSION:
            raise ProgramContractError("invalid requirements goalVersion")
        if document.get("sourceSha256") != self.REQUIRED_SOURCE_SHA256:
            raise ProgramContractError("invalid requirements sourceSha256")

    @staticmethod
    def _canonical_json_bytes(value: Any) -> bytes:
        try:
            return json.dumps(
                value,
                allow_nan=False,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        except ProgramContractError:
            raise
        except (
            OverflowError,
            RecursionError,
            TypeError,
            UnicodeEncodeError,
            ValueError,
        ) as error:
            raise ProgramContractError(f"invalid JSON value: {error}") from error

    @classmethod
    def _sha256_canonical(cls, value: Any) -> str:
        return hashlib.sha256(cls._canonical_json_bytes(value)).hexdigest()

    @staticmethod
    def _require_exact_keys(
        value: dict[str, Any],
        expected_keys: frozenset[str],
        label: str,
    ) -> None:
        if set(value) != expected_keys:
            raise ProgramContractError(f"invalid {label} keys")

    @staticmethod
    def _load_json(path: Path) -> Any:
        if not path.is_file():
            raise ProgramContractError(f"missing JSON file: {path}")
        try:
            return json.loads(
                path.read_text(encoding="utf-8"),
                object_pairs_hook=ProgramContractValidator._reject_duplicate_keys,
                parse_constant=ProgramContractValidator._reject_json_constant,
            )
        except ProgramContractError:
            raise
        except (
            OSError,
            OverflowError,
            RecursionError,
            TypeError,
            UnicodeDecodeError,
            ValueError,
        ) as error:
            raise ProgramContractError(f"invalid JSON file: {path}: {error}") from error

    @staticmethod
    def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ProgramContractError(f"duplicate JSON key: {key}")
            value[key] = item
        return value

    @staticmethod
    def _reject_json_constant(value: str) -> NoReturn:
        raise ProgramContractError(f"invalid JSON constant: {value}")

    @staticmethod
    def _require_list(value: Any, label: str) -> list[Any]:
        if not isinstance(value, list):
            raise ProgramContractError(f"{label} must be an array")
        return value

    @staticmethod
    def _require_text(value: Any, label: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ProgramContractError(f"{label} must be non-blank text")
        return value

    def _validate_object_id(self, value: Any) -> str:
        identifier = self._require_text(value, "catalog object id")
        if self._OBJECT_ID_PATTERN.fullmatch(identifier) is None:
            raise ProgramContractError(f"invalid catalog object id: {identifier}")
        return identifier

    @staticmethod
    def _validate_relative_path(value: Any, label: str) -> str:
        path = ProgramContractValidator._require_text(value, label)
        candidate = Path(path)
        if candidate.is_absolute() or ".." in candidate.parts or "\\" in path:
            raise ProgramContractError(f"invalid {label}: {path}")
        return path
