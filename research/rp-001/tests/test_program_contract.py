from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

from rp001.program_contract import ProgramContractError, ProgramContractValidator


REQUIRED_STUDY_CONTRACTS = (
    ("ST-ONT-001", "RQ-001", "DC-001", "SP-001"),
    ("ST-DAT-001", "RQ-002", "DC-002", "SP-002"),
    ("ST-BEH-001", "RQ-003", "DC-003", "SP-003"),
    ("ST-VAL-001", "RQ-004", "DC-004", "SP-004"),
    ("ST-MIC-001", "RQ-005", "DC-005", "SP-005"),
    ("ST-EXE-001", "RQ-006", "DC-006", "SP-006"),
    ("ST-RSK-001", "RQ-007", "DC-007", "SP-007"),
    ("ST-SYN-001", "RQ-008", "DC-008", "SP-008"),
)
REQUIRED_STUDY_SLOTS = tuple(
    study_slot
    for study_slot, _question_id, _dataset_contract_id, _protocol_id
    in REQUIRED_STUDY_CONTRACTS
)

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

RUN_PROGRAM_PATH = Path(__file__).resolve().parents[1] / "run_program.py"
PROGRAM_ARTIFACTS_DIRECTORY = (
    Path(__file__).resolve().parents[2]
    / "meta-research"
    / "objects"
    / "programs"
    / "RP-001-quantitative-market-behavior"
)
FOUNDATION_LEDGER_FILENAMES = (
    "requirements.json",
    "traceability.json",
    "study-registry.json",
    "candidate-registry.json",
    "seen-data-register.json",
)
ALL_QUESTION_IDS = tuple(f"RQ-{index:03d}" for index in range(1, 9))
PREDICTIVE_QUESTION_IDS = tuple(f"RQ-{index:03d}" for index in range(3, 9))
PREDICTIVE_STUDY_SLOTS = REQUIRED_STUDY_SLOTS[2:]
ACTIVE_GOAL_SOURCE_SHA256 = (
    "089ee3236ad913388106d0b569cc931e451d6be661c55ee62c2993f093afaad3"
)


class ProgramContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.program_directory = Path(self.temporary_directory.name) / "program"
        self._reset_fixture_values()

    def _reset_fixture_values(self) -> None:
        if self.program_directory.exists():
            shutil.rmtree(self.program_directory)
        shutil.copytree(PROGRAM_ARTIFACTS_DIRECTORY, self.program_directory)
        self.requirements = self._requirements_fixture()
        self.traceability = self._traceability_fixture()
        self.study_registry = self._study_registry_fixture()
        self.candidate_registry = self._candidate_registry_fixture()
        self.seen_data_register = self._seen_data_register_fixture()
        self.program_descriptor = self._program_descriptor_fixture()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_accepts_complete_registered_foundation(self) -> None:
        report = self._validator().validate_foundation()

        self.assertEqual(report.requirement_count, 254)
        self.assertEqual(report.source_requirement_coverage, 1.0)
        self.assertEqual(report.study_slot_coverage, 1.0)
        self.assertEqual(report.candidate_family_coverage, 1.0)

    def test_registers_reviewed_atomic_requirements_and_study_scope(self) -> None:
        requirements_by_id = {
            requirement["id"]: requirement
            for requirement in self.requirements["requirements"]
        }
        traces_by_id = {
            row["sourceRequirementId"]: row
            for row in self.traceability["traceability"]
        }
        atomic_texts = {
            "REQ-099": "각 독립 연구에 별도 질문을 둔다.",
            "REQ-100": "각 독립 연구에 별도 StudyProtocol을 둔다.",
            "REQ-101": "각 독립 연구에 별도 DatasetContract를 둔다.",
            "REQ-102": "각 독립 연구에 별도 trial ledger를 둔다.",
            "REQ-128": (
                "다음 구간을 seen_development_data로 등록한다: "
                "Micron 최근 120거래일."
            ),
            "REQ-129": (
                "다음 구간을 seen_development_data로 등록한다: "
                "Micron 최근 4개월."
            ),
            "REQ-130": (
                "다음 구간을 seen_development_data로 등록한다: "
                "SK하이닉스 최근 120거래일."
            ),
            "REQ-131": (
                "다음 구간을 seen_development_data로 등록한다: "
                "SK하이닉스 최근 4개월."
            ),
            "REQ-141": "모든 반복 시행의 표본 역할을 원장에 기록한다.",
            "REQ-142": "모든 반복 시행의 결과를 원장에 기록한다.",
        }
        for requirement_id, expected_text in atomic_texts.items():
            with self.subTest(requirement_id=requirement_id):
                requirement = requirements_by_id[requirement_id]
                self.assertEqual(requirement["text"], expected_text)

        self.assertEqual(len(requirements_by_id), 254)
        for requirement_id in (
            "REQ-137",
            "REQ-138",
            "REQ-139",
            "REQ-140",
            "REQ-141",
            "REQ-142",
        ):
            with self.subTest(requirement_id=requirement_id, scope="all studies"):
                trace = traces_by_id[requirement_id]
                self.assertEqual(trace["questionIds"], list(ALL_QUESTION_IDS))
                self.assertEqual(trace["studySlots"], list(REQUIRED_STUDY_SLOTS))

        for index in range(143, 152):
            requirement_id = f"REQ-{index:03d}"
            with self.subTest(requirement_id=requirement_id, scope="ontology behavior"):
                trace = traces_by_id[requirement_id]
                self.assertEqual(trace["questionIds"], ["RQ-001", "RQ-003"])
                self.assertEqual(
                    trace["studySlots"],
                    ["ST-ONT-001", "ST-BEH-001"],
                )

        predictive_trace = traces_by_id["REQ-152"]
        self.assertEqual(
            predictive_trace["questionIds"],
            list(PREDICTIVE_QUESTION_IDS),
        )
        self.assertEqual(
            predictive_trace["studySlots"],
            list(PREDICTIVE_STUDY_SLOTS),
        )

    def test_rejects_out_of_bounds_or_decreasing_source_ranges(self) -> None:
        cases = (
            ("out_of_bounds", 0, [393, 393], "invalid requirement sourceLines"),
            (
                "decreasing",
                10,
                [1, 1],
                "nondecreasing requirement sourceLines",
            ),
        )
        for case, index, source_lines, expected_message in cases:
            with self.subTest(case=case):
                self._reset_fixture_values()
                self.requirements["requirements"][index]["sourceLines"] = source_lines
                self._write_requirements()

                with self.assertRaisesRegex(
                    ProgramContractError,
                    expected_message,
                ):
                    self._validator().validate_foundation()

    def test_rejects_frozen_requirement_content_drift(self) -> None:
        self.requirements["requirements"][0]["text"] += " drift"
        self._write_requirements()

        with self.assertRaisesRegex(
            ProgramContractError,
            "frozen requirements drift",
        ):
            self._validator().validate_foundation()

    def test_requires_trace_rows_in_requirement_order(self) -> None:
        self.traceability["traceability"].reverse()
        self._write_traceability()

        with self.assertRaisesRegex(
            ProgramContractError,
            "traceability rows must follow requirement order",
        ):
            self._validator().validate_foundation()

    def test_rejects_frozen_requirement_to_study_mapping_drift(self) -> None:
        row = self.traceability["traceability"][0]
        row["questionIds"] = ["RQ-002"]
        row["studySlots"] = ["ST-DAT-001"]
        self._write_traceability()

        with self.assertRaisesRegex(
            ProgramContractError,
            "frozen traceability mapping drift",
        ):
            self._validator().validate_foundation()

    def test_allows_later_trace_evidence_registration(self) -> None:
        row = self.traceability["traceability"][0]
        row["evidenceIds"] = ["EV-001"]
        row["decisionIds"] = ["DR-001"]
        row["reportPaths"] = ["research/rp-001/reports/ST-ONT-001.md"]
        self._write_traceability()

        report = self._validator().validate_foundation()

        self.assertEqual(report.source_requirement_coverage, 1.0)

    def test_rejects_duplicate_requirement_id(self) -> None:
        duplicate = dict(self.requirements["requirements"][0])
        self.requirements["requirements"].append(duplicate)
        self._write_requirements()

        with self.assertRaisesRegex(ProgramContractError, "duplicate requirement id"):
            self._validator().validate_foundation()

    def test_rejects_nonsequential_requirement_ids(self) -> None:
        self.requirements["requirements"][1]["id"] = "REQ-999"
        self._write_requirements()

        with self.assertRaisesRegex(ProgramContractError, "nonsequential requirement ids"):
            self._validator().validate_foundation()

    def test_rejects_unsorted_requirement_ids(self) -> None:
        self.requirements["requirements"][0], self.requirements["requirements"][1] = (
            self.requirements["requirements"][1],
            self.requirements["requirements"][0],
        )
        self._write_requirements()

        with self.assertRaisesRegex(ProgramContractError, "unsorted requirement ids"):
            self._validator().validate_foundation()

    def test_rejects_blank_requirement_source_or_text(self) -> None:
        for field in ("sourceSection", "text"):
            with self.subTest(field=field):
                self.requirements = self._requirements_fixture()
                self.requirements["requirements"][0][field] = " "
                self._write_requirements()

                with self.assertRaisesRegex(
                    ProgramContractError,
                    f"blank requirement {field}",
                ):
                    self._validator().validate_foundation()

    def test_requires_nonblank_requirement_category(self) -> None:
        for case in ("missing", "blank"):
            with self.subTest(case=case):
                self._reset_fixture_values()
                if case == "missing":
                    self.requirements["requirements"][0].pop("category")
                else:
                    self.requirements["requirements"][0]["category"] = " "
                self._write_fixtures()

                with self.assertRaisesRegex(
                    ProgramContractError,
                    "requirement category",
                ):
                    self._validator().validate_foundation()

    def test_rejects_invalid_positive_source_line_range(self) -> None:
        invalid_ranges = ([0, 1], [3, 2], [1], [1, "2"])
        for source_lines in invalid_ranges:
            with self.subTest(source_lines=source_lines):
                self.requirements["requirements"][0]["sourceLines"] = source_lines
                self._write_requirements()

                with self.assertRaisesRegex(
                    ProgramContractError,
                    "invalid requirement sourceLines",
                ):
                    self._validator().validate_foundation()

                self.requirements = self._requirements_fixture()

    def test_rejects_empty_requirements(self) -> None:
        self.requirements["requirements"] = []
        self.traceability["traceability"] = []
        self._write_fixtures()

        with self.assertRaisesRegex(
            ProgramContractError,
            "requirements must not be empty",
        ):
            self._validator().validate_foundation()

    def test_rejects_missing_or_unknown_traceability_requirement(self) -> None:
        cases = ("missing", "unknown")
        for case in cases:
            with self.subTest(case=case):
                self.traceability = self._traceability_fixture()
                if case == "missing":
                    self.traceability["traceability"].pop()
                    expected = "missing traceability requirement"
                else:
                    self.traceability["traceability"][0]["sourceRequirementId"] = (
                        "REQ-999"
                    )
                    expected = "unknown traceability requirement"
                self._write_traceability()

                with self.assertRaisesRegex(ProgramContractError, expected):
                    self._validator().validate_foundation()

    def test_rejects_unregistered_traceability_study_slot(self) -> None:
        self.traceability["traceability"][0]["studySlots"] = ["ST-EXT-999"]
        self._write_traceability()

        with self.assertRaisesRegex(
            ProgramContractError,
            "unknown traceability study slot",
        ):
            self._validator().validate_foundation()

    def test_requires_traceability_questions_mapped_from_study_slots(self) -> None:
        self.traceability["traceability"][0]["questionIds"] = ["RQ-999"]
        self._write_traceability()

        with self.assertRaisesRegex(
            ProgramContractError,
            "traceability questionIds do not match studySlots",
        ):
            self._validator().validate_foundation()

    def test_rejects_duplicate_traceability_question_ids(self) -> None:
        self.traceability["traceability"][0]["questionIds"] = [
            "RQ-001",
            "RQ-001",
        ]
        self._write_traceability()

        with self.assertRaisesRegex(
            ProgramContractError,
            "duplicate traceability questionIds",
        ):
            self._validator().validate_foundation()

    def test_rejects_duplicate_traceability_study_slots(self) -> None:
        self.traceability["traceability"][0]["studySlots"] = [
            "ST-ONT-001",
            "ST-ONT-001",
        ]
        self._write_traceability()

        with self.assertRaisesRegex(
            ProgramContractError,
            "duplicate traceability studySlots",
        ):
            self._validator().validate_foundation()

    def test_rejects_incomplete_study_contract_chain(self) -> None:
        for field in (
            "questionId",
            "datasetContractId",
            "protocolId",
            "trialLedgerPath",
        ):
            with self.subTest(field=field):
                self.study_registry = self._study_registry_fixture()
                self.study_registry["studies"][0].pop(field)
                self._write_study_registry()

                with self.assertRaisesRegex(
                    ProgramContractError,
                    "incomplete study contract",
                ):
                    self._validator().validate_foundation()

    def test_rejects_legacy_study_protocol_field(self) -> None:
        for case in ("replacement", "extra"):
            with self.subTest(case=case):
                self._reset_fixture_values()
                study = self.study_registry["studies"][0]
                study["studyProtocolId"] = study["protocolId"]
                if case == "replacement":
                    study.pop("protocolId")
                    expected = "incomplete study contract"
                else:
                    expected = "invalid study contract keys"
                self._write_fixtures()

                with self.assertRaisesRegex(ProgramContractError, expected):
                    self._validator().validate_foundation()

    def test_rejects_malformed_study_slot(self) -> None:
        self.study_registry["studies"][0]["studySlot"] = "ST-MIC-1"
        self._write_study_registry()

        with self.assertRaisesRegex(ProgramContractError, "invalid study slot id"):
            self._validator().validate_foundation()

    def test_requires_exact_registered_study_contract_mapping(self) -> None:
        cases = (
            ("questionId", "RQ-999"),
            ("datasetContractId", "DC-999"),
            ("protocolId", "SP-999"),
        )
        for field, value in cases:
            with self.subTest(field=field):
                self._reset_fixture_values()
                self.study_registry["studies"][0][field] = value
                self._write_fixtures()

                with self.assertRaisesRegex(
                    ProgramContractError,
                    "invalid required study contract",
                ):
                    self._validator().validate_foundation()

    def test_requires_exact_unique_study_slots(self) -> None:
        for case in ("missing", "duplicate", "extra"):
            with self.subTest(case=case):
                self.study_registry = self._study_registry_fixture()
                studies = self.study_registry["studies"]
                if case == "missing":
                    studies.pop()
                elif case == "duplicate":
                    studies.append(dict(studies[0]))
                else:
                    extra = dict(studies[0])
                    extra["studySlot"] = "ST-EXT-999"
                    extra["trialLedgerPath"] = "research/rp-001/trials/ST-EXT-999.json"
                    studies.append(extra)
                self._write_study_registry()

                with self.assertRaisesRegex(
                    ProgramContractError,
                    "invalid required study slots",
                ):
                    self._validator().validate_foundation()

    def test_requires_study_registry_order(self) -> None:
        self.study_registry["studies"].reverse()
        self._write_study_registry()

        with self.assertRaisesRegex(
            ProgramContractError,
            "invalid required study order",
        ):
            self._validator().validate_foundation()

    def test_requires_exact_unique_candidate_families(self) -> None:
        for case in ("missing", "duplicate", "extra"):
            with self.subTest(case=case):
                self.candidate_registry = self._candidate_registry_fixture()
                candidates = self.candidate_registry["candidates"]
                if case == "missing":
                    candidates.pop()
                elif case == "duplicate":
                    candidates.append(dict(candidates[0]))
                else:
                    candidates.append(
                        {"family": "extra_family", "status": "registry_only"}
                    )
                self._write_candidate_registry()

                with self.assertRaisesRegex(
                    ProgramContractError,
                    "invalid required candidate families",
                ):
                    self._validator().validate_foundation()

    def test_requires_candidate_registry_order(self) -> None:
        self.candidate_registry["candidates"].reverse()
        self._write_candidate_registry()

        with self.assertRaisesRegex(
            ProgramContractError,
            "invalid required candidate order",
        ):
            self._validator().validate_foundation()

    def test_rejects_invalid_object_ids_and_trial_ledger_paths(self) -> None:
        cases = (
            ("questionId", "question-1", "invalid catalog object id"),
            ("datasetContractId", "DC-1", "invalid catalog object id"),
            ("protocolId", "SP_001", "invalid catalog object id"),
            (
                "trialLedgerPath",
                "research/rp-001/trials/wrong.json",
                "invalid trial ledger path",
            ),
        )
        for field, value, expected in cases:
            with self.subTest(field=field):
                self.study_registry = self._study_registry_fixture()
                self.study_registry["studies"][0][field] = value
                self._write_study_registry()

                with self.assertRaisesRegex(ProgramContractError, expected):
                    self._validator().validate_foundation()

    def test_rejects_invalid_candidate_object_id(self) -> None:
        registered_candidate = next(
            candidate
            for candidate in self.candidate_registry["candidates"]
            if candidate["family"] == "bayesian_competing_risk"
        )
        registered_candidate["objectId"] = "MC-1"
        self._write_candidate_registry()

        with self.assertRaisesRegex(ProgramContractError, "invalid catalog object id"):
            self._validator().validate_foundation()

    def test_rejects_unknown_candidate_status(self) -> None:
        self.candidate_registry["candidates"][0]["status"] = "pending"
        self._write_candidate_registry()

        with self.assertRaisesRegex(ProgramContractError, "invalid candidate status"):
            self._validator().validate_foundation()

    def test_requires_candidate_status_and_object_id_consistency(self) -> None:
        cases = ("registry_only_with_object", "registered_without_object")
        for case in cases:
            with self.subTest(case=case):
                self._reset_fixture_values()
                if case == "registry_only_with_object":
                    candidate = self.candidate_registry["candidates"][0]
                    candidate["objectId"] = "MC-002"
                else:
                    candidate = next(
                        candidate
                        for candidate in self.candidate_registry["candidates"]
                        if candidate["family"] == "bayesian_competing_risk"
                    )
                    candidate.pop("objectId")
                self._write_fixtures()

                with self.assertRaisesRegex(
                    ProgramContractError,
                    "candidate objectId does not match status",
                ):
                    self._validator().validate_foundation()

    def test_requires_exact_candidate_family_registration(self) -> None:
        cases = (
            ("bayesian_status", "bayesian_competing_risk", "registry_only", None),
            (
                "bayesian_object",
                "bayesian_competing_risk",
                "object_registered",
                "MC-002",
            ),
            ("other_registered", "unconditional", "object_registered", "MC-002"),
        )
        for case, family, status, object_id in cases:
            with self.subTest(case=case):
                self._reset_fixture_values()
                candidate = next(
                    candidate
                    for candidate in self.candidate_registry["candidates"]
                    if candidate["family"] == family
                )
                candidate["status"] = status
                if object_id is None:
                    candidate.pop("objectId", None)
                else:
                    candidate["objectId"] = object_id
                self._write_fixtures()

                with self.assertRaisesRegex(
                    ProgramContractError,
                    "invalid required candidate registration",
                ):
                    self._validator().validate_foundation()

    def test_requires_exact_ledger_top_level_keys(self) -> None:
        collection_fields = {
            "requirements.json": "requirements",
            "traceability.json": "traceability",
            "study-registry.json": "studies",
            "candidate-registry.json": "candidates",
            "seen-data-register.json": "entries",
        }
        for filename, collection_field in collection_fields.items():
            for case in ("missing", "extra"):
                with self.subTest(filename=filename, case=case):
                    self._reset_fixture_values()
                    document = self._fixture_documents()[filename]
                    if case == "missing":
                        document.pop(collection_field)
                    else:
                        document["unexpected"] = True
                    self._write_fixtures()

                    with self.assertRaisesRegex(
                        ProgramContractError,
                        f"invalid {filename} keys",
                    ):
                        self._validator().validate_foundation()

    def test_rejects_unknown_requirement_trace_and_study_row_keys(self) -> None:
        cases = (
            ("requirement", "requirements"),
            ("traceability row", "traceability"),
            ("study contract", "studies"),
        )
        for label, collection_field in cases:
            with self.subTest(label=label):
                self._reset_fixture_values()
                current_document = {
                    "requirements": self.requirements,
                    "traceability": self.traceability,
                    "studies": self.study_registry,
                }[collection_field]
                current_document[collection_field][0]["unexpected"] = True
                self._write_fixtures()

                with self.assertRaisesRegex(
                    ProgramContractError,
                    f"invalid {label} keys",
                ):
                    self._validator().validate_foundation()

    def test_requires_status_specific_candidate_row_keys(self) -> None:
        for family in ("unconditional", "bayesian_competing_risk"):
            with self.subTest(family=family):
                self._reset_fixture_values()
                candidate = next(
                    candidate
                    for candidate in self.candidate_registry["candidates"]
                    if candidate["family"] == family
                )
                candidate["unexpected"] = True
                self._write_fixtures()

                with self.assertRaisesRegex(
                    ProgramContractError,
                    "invalid candidate registration keys",
                ):
                    self._validator().validate_foundation()

    def test_requires_exact_ledger_schema_versions(self) -> None:
        expected_versions = {
            "requirements.json": "rp001-requirements.v1",
            "traceability.json": "rp001-traceability.v1",
            "study-registry.json": "rp001-study-registry.v1",
            "candidate-registry.json": "rp001-candidate-registry.v1",
            "seen-data-register.json": "rp001-seen-data-register.v1",
        }
        for filename, expected_version in expected_versions.items():
            for case in ("missing", "wrong"):
                with self.subTest(filename=filename, case=case):
                    self._reset_fixture_values()
                    document = self._fixture_documents()[filename]
                    if case == "missing":
                        document.pop("schemaVersion")
                    else:
                        document["schemaVersion"] = f"{expected_version}.wrong"
                    self._write_fixtures()

                    with self.assertRaisesRegex(
                        ProgramContractError,
                        f"invalid {filename} schemaVersion",
                    ):
                        self._validator().validate_foundation()

    def test_requires_exact_seen_data_register(self) -> None:
        for case in ("missing_file", "missing_entry"):
            with self.subTest(case=case):
                self._reset_fixture_values()
                if case == "missing_file":
                    (self.program_directory / "seen-data-register.json").unlink()
                    expected_message = "missing JSON file"
                else:
                    self.seen_data_register["entries"].pop()
                    self._write_seen_data_register()
                    expected_message = "frozen seen-data register drift"

                with self.assertRaisesRegex(
                    ProgramContractError,
                    expected_message,
                ):
                    self._validator().validate_foundation()

    def test_rejects_seen_window_role_or_confirmatory_drift(self) -> None:
        cases = (
            ("sample_role", "sampleRole", "confirmatory_data"),
            ("confirmatory", "confirmatoryAllowed", True),
        )
        for case, field, value in cases:
            with self.subTest(case=case):
                self._reset_fixture_values()
                self.seen_data_register["entries"][0][field] = value
                self._write_seen_data_register()

                with self.assertRaisesRegex(
                    ProgramContractError,
                    "frozen seen-data register drift",
                ):
                    self._validator().validate_foundation()

    def test_requires_all_raw_archive_exposures_and_matching_hashes(self) -> None:
        raw_window_ids = (
            "tslaRawArchiveExposure",
            "nvdaRawArchiveExposure",
            "muRawArchiveExposure",
            "hynixRawArchiveExposure",
        )
        for window_id in raw_window_ids:
            with self.subTest(window_id=window_id):
                self._reset_fixture_values()
                raw_entry = next(
                    entry
                    for entry in self.seen_data_register["entries"]
                    if entry["windowId"] == window_id
                )
                raw_entry["rawFileSha256"] = "0" * 64
                self._write_seen_data_register()

                with self.assertRaisesRegex(
                    ProgramContractError,
                    "frozen seen-data register drift",
                ):
                    self._validator().validate_foundation()

    def test_rejects_noncanonical_foundation_ledger_bytes(self) -> None:
        for filename in FOUNDATION_LEDGER_FILENAMES:
            with self.subTest(filename=filename):
                self._reset_fixture_values()
                path = self.program_directory / filename
                path.write_bytes(path.read_bytes() + b"\n")

                with self.assertRaisesRegex(
                    ProgramContractError,
                    f"{filename} is not canonical JSON",
                ):
                    self._validator().validate_foundation()

    def test_requires_exact_frozen_goal_copy(self) -> None:
        goal_path = self.program_directory / "goal-v1.0.md"
        for case in ("missing", "drift"):
            with self.subTest(case=case):
                self._reset_fixture_values()
                if case == "missing":
                    goal_path = self.program_directory / "goal-v1.0.md"
                    goal_path.unlink()
                else:
                    goal_path = self.program_directory / "goal-v1.0.md"
                    goal_path.write_bytes(goal_path.read_bytes() + b"drift")

                with self.assertRaisesRegex(
                    ProgramContractError,
                    "invalid frozen goal copy",
                ):
                    self._validator().validate_foundation()

    def test_requires_rp001_foundation_status_and_bindings(self) -> None:
        cases = (
            ("id", "id", "RP-999", "invalid RP object identity"),
            ("type", "type", "MetaStudy", "invalid RP object identity"),
            (
                "lifecycle",
                "lifecycleState",
                "completed",
                "invalid RP foundation status",
            ),
            (
                "evidence",
                "evidenceLevel",
                "replicated",
                "invalid RP foundation status",
            ),
        )
        for case, field, value, expected_message in cases:
            with self.subTest(case=case):
                self._reset_fixture_values()
                self.program_descriptor[field] = value
                self._write_program_descriptor()

                with self.assertRaisesRegex(
                    ProgramContractError,
                    expected_message,
                ):
                    self._validator().validate_foundation()

        for case, field, required_value in (
            ("dependency", "dependsOn", "RB-001"),
            (
                "artifact",
                "artifacts",
                "research/meta-research/objects/programs/"
                "RP-001-quantitative-market-behavior/requirements.json",
            ),
        ):
            with self.subTest(case=case):
                self._reset_fixture_values()
                self.program_descriptor[field].remove(required_value)
                self._write_program_descriptor()

                with self.assertRaisesRegex(
                    ProgramContractError,
                    "missing RP foundation binding",
                ):
                    self._validator().validate_foundation()

    def test_requires_bound_task3_artifact_files(self) -> None:
        (self.program_directory / "integration-contract.md").unlink()

        with self.assertRaisesRegex(
            ProgramContractError,
            "missing RP foundation artifact",
        ):
            self._validator().validate_foundation()

    def test_allows_later_rp_dependencies_and_artifact_bindings(self) -> None:
        self.program_descriptor["dependsOn"].append("EV-001")
        self.program_descriptor["artifacts"].append(
            "research/meta-research/objects/programs/"
            "RP-001-quantitative-market-behavior/future-evidence.md"
        )
        self._write_program_descriptor()

        report = self._validator().validate_foundation()

        self.assertEqual(report.requirement_count, 254)

    def test_requires_exact_requirements_metadata(self) -> None:
        cases = (
            ("goalId", None, "invalid requirements goalId"),
            ("goalId", "GOAL-RP-999", "invalid requirements goalId"),
            ("goalVersion", None, "invalid requirements goalVersion"),
            ("goalVersion", "1.1", "invalid requirements goalVersion"),
            ("sourceSha256", None, "invalid requirements sourceSha256"),
            ("sourceSha256", "A" * 64, "invalid requirements sourceSha256"),
            ("sourceSha256", "a" * 63, "invalid requirements sourceSha256"),
            ("sourceSha256", "g" * 64, "invalid requirements sourceSha256"),
        )
        for field, value, expected_message in cases:
            with self.subTest(field=field, value=value):
                self._reset_fixture_values()
                if value is None:
                    self.requirements.pop(field)
                else:
                    self.requirements[field] = value
                self._write_fixtures()

                with self.assertRaisesRegex(ProgramContractError, expected_message):
                    self._validator().validate_foundation()

    def test_binds_foundation_to_active_goal_source_sha256(self) -> None:
        bindings = {
            "requirements.json sourceSha256": self.requirements["sourceSha256"],
            "ProgramContractValidator source SHA-256": (
                ProgramContractValidator.REQUIRED_SOURCE_SHA256
            ),
        }

        for binding_name, actual_sha256 in bindings.items():
            with self.subTest(binding_name=binding_name):
                self.assertEqual(actual_sha256, ACTIVE_GOAL_SOURCE_SHA256)

    def test_rejects_wrong_frozen_source_sha256(self) -> None:
        self.requirements["sourceSha256"] = "0" * 64
        self._write_requirements()

        with self.assertRaisesRegex(
            ProgramContractError,
            "invalid requirements sourceSha256",
        ):
            self._validator().validate_foundation()

    def test_rejects_duplicate_json_key(self) -> None:
        (self.program_directory / "requirements.json").write_text(
            '{"schemaVersion":"rp001-requirements.v1",'
            '"schemaVersion":"duplicate","requirements":[]}',
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ProgramContractError, "duplicate JSON key"):
            self._validator().validate_foundation()

    def test_rejects_nonstandard_json_constants(self) -> None:
        path = self.program_directory / "requirements.json"
        valid_text = path.read_text(encoding="utf-8")
        for constant in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(constant=constant):
                path.write_text(
                    valid_text.replace('"role"', constant, 1),
                    encoding="utf-8",
                )

                with self.assertRaisesRegex(
                    ProgramContractError,
                    f"invalid JSON constant: {constant}",
                ):
                    self._validator().validate_foundation()

    def test_rejects_invalid_utf8(self) -> None:
        (self.program_directory / "traceability.json").write_bytes(b'{"x":"\xff"}')

        with self.assertRaisesRegex(ProgramContractError, "invalid JSON file"):
            self._validator().validate_foundation()

    def test_cli_rejects_finite_overflow_json_without_traceback(self) -> None:
        self._assert_cli_rejects_invalid_json_bytes(b'{"x":1e309}')

    def test_cli_rejects_unpaired_surrogate_json_without_traceback(self) -> None:
        self._assert_cli_rejects_invalid_json_bytes(b'{"x":"\\ud800"}')

    def test_cli_rejects_oversized_integer_json_without_traceback(self) -> None:
        payload = ('{"x":' + '9' * 5_000 + '}').encode("ascii")

        self._assert_cli_rejects_invalid_json_bytes(payload)

    def test_cli_rejects_excessive_json_nesting_without_traceback(self) -> None:
        payload = b"[" * 10_000 + b"0" + b"]" * 10_000

        self._assert_cli_rejects_invalid_json_bytes(payload)

    def test_cli_outputs_canonical_sorted_foundation_report(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(RUN_PROGRAM_PATH),
                "--verify-foundation",
                "--program-directory",
                str(self.program_directory),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout,
            '{"candidateFamilyCoverage":1.0,"requirementCount":254,'
            '"sourceRequirementCoverage":1.0,"studySlotCoverage":1.0}\n',
        )
        self.assertEqual(result.stderr, "")

    def test_cli_reports_contract_failure_without_traceback(self) -> None:
        empty_directory = Path(self.temporary_directory.name) / "empty"
        empty_directory.mkdir()

        result = subprocess.run(
            [
                sys.executable,
                str(RUN_PROGRAM_PATH),
                "--verify-foundation",
                "--program-directory",
                str(empty_directory),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("INVALID", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_cli_reports_empty_requirements_without_traceback(self) -> None:
        self.requirements["requirements"] = []
        self.traceability["traceability"] = []
        self._write_fixtures()

        result = subprocess.run(
            [
                sys.executable,
                str(RUN_PROGRAM_PATH),
                "--verify-foundation",
                "--program-directory",
                str(self.program_directory),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("INVALID requirements must not be empty", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def _validator(self) -> ProgramContractValidator:
        return ProgramContractValidator(self.program_directory)

    def _assert_cli_rejects_invalid_json_bytes(self, payload: bytes) -> None:
        (self.program_directory / "requirements.json").write_bytes(payload)
        result = subprocess.run(
            [
                sys.executable,
                str(RUN_PROGRAM_PATH),
                "--verify-foundation",
                "--program-directory",
                str(self.program_directory),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("INVALID", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def _write_fixtures(self) -> None:
        self._write_requirements()
        self._write_traceability()
        self._write_study_registry()
        self._write_candidate_registry()
        self._write_seen_data_register()
        self._write_program_descriptor()

    def _write_requirements(self) -> None:
        self._write_json("requirements.json", self.requirements)

    def _write_traceability(self) -> None:
        self._write_json("traceability.json", self.traceability)

    def _write_study_registry(self) -> None:
        self._write_json("study-registry.json", self.study_registry)

    def _write_candidate_registry(self) -> None:
        self._write_json("candidate-registry.json", self.candidate_registry)

    def _write_seen_data_register(self) -> None:
        self._write_json("seen-data-register.json", self.seen_data_register)

    def _write_program_descriptor(self) -> None:
        self._write_json("object.json", self.program_descriptor)

    def _fixture_documents(self) -> dict[str, dict[str, Any]]:
        return {
            "requirements.json": self.requirements,
            "traceability.json": self.traceability,
            "study-registry.json": self.study_registry,
            "candidate-registry.json": self.candidate_registry,
            "seen-data-register.json": self.seen_data_register,
        }

    def _write_json(self, filename: str, value: dict[str, Any]) -> None:
        (self.program_directory / filename).write_text(
            json.dumps(
                value,
                allow_nan=False,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )

    @staticmethod
    def _requirements_fixture() -> dict[str, Any]:
        return ProgramContractTest._load_program_fixture("requirements.json")

    @staticmethod
    def _traceability_fixture() -> dict[str, Any]:
        return ProgramContractTest._load_program_fixture("traceability.json")

    @staticmethod
    def _study_registry_fixture() -> dict[str, Any]:
        return ProgramContractTest._load_program_fixture("study-registry.json")

    @staticmethod
    def _candidate_registry_fixture() -> dict[str, Any]:
        return ProgramContractTest._load_program_fixture("candidate-registry.json")

    @staticmethod
    def _seen_data_register_fixture() -> dict[str, Any]:
        return ProgramContractTest._load_program_fixture("seen-data-register.json")

    @staticmethod
    def _program_descriptor_fixture() -> dict[str, Any]:
        return ProgramContractTest._load_program_fixture("object.json")

    @staticmethod
    def _load_program_fixture(filename: str) -> dict[str, Any]:
        value = json.loads(
            (PROGRAM_ARTIFACTS_DIRECTORY / filename).read_text(encoding="utf-8")
        )
        if not isinstance(value, dict):
            raise TypeError(f"fixture must be a JSON object: {filename}")
        return value


if __name__ == "__main__":
    unittest.main()
