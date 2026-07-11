from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, NoReturn

sys.path.insert(0, str(Path(__file__).resolve().parent))

from validate_research_program import (  # noqa: E402
    ResearchProgramValidationError,
    ResearchProgramValidator,
)


EXPECTED_RP001_OBJECT_GRAPH_PROJECTION_SHA256 = (
    "228a4cb3b47b78e926b0a42eef8ac9d5ba5279052785f9280fbb56b59d5eb0a0"
)


def build_repository_object_graph_projection(
    repository_root: Path,
) -> list[dict[str, Any]]:
    resolved_repository_root = repository_root.resolve()
    catalog = _load_strict_json_object(
        resolved_repository_root
        / "research"
        / "meta-research"
        / "catalog"
        / "research-objects.json"
    )
    entries = catalog.get("objects")
    if not isinstance(entries, list):
        raise AssertionError("catalog objects must be an array")

    projection: list[dict[str, Any]] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or set(entry) != {"descriptor"}:
            raise AssertionError(
                f"catalog object {index} must contain only descriptor"
            )
        descriptor_relative_path = entry["descriptor"]
        if not isinstance(descriptor_relative_path, str):
            raise AssertionError(
                f"catalog object {index} descriptor must be text"
            )
        descriptor_path = (
            resolved_repository_root / descriptor_relative_path
        ).resolve()
        if not descriptor_path.is_relative_to(resolved_repository_root):
            raise AssertionError(
                f"catalog object {index} descriptor escapes repository"
            )
        descriptor = _load_strict_json_object(descriptor_path)
        identifier = descriptor.get("id")
        if not isinstance(identifier, str):
            raise AssertionError(f"descriptor {index} id must be text")
        projection.append(
            {
                "descriptorPath": descriptor_relative_path,
                "id": identifier,
                "dependsOn": _require_projection_string_array(
                    descriptor.get("dependsOn"),
                    f"{identifier} dependsOn",
                ),
                "artifacts": _require_projection_string_array(
                    descriptor.get("artifacts"),
                    f"{identifier} artifacts",
                ),
            }
        )
    return projection


def repository_object_graph_projection_sha256(
    projection: list[dict[str, Any]],
) -> str:
    """Hash graph semantics while preserving catalog and array order."""
    canonical_bytes = json.dumps(
        projection,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical_bytes).hexdigest()


def _load_strict_json_object(path: Path) -> dict[str, Any]:
    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise AssertionError(f"duplicate JSON key: {key}")
            value[key] = item
        return value

    def reject_json_constant(value: str) -> NoReturn:
        raise AssertionError(f"invalid JSON constant: {value}")

    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_json_constant,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AssertionError(f"invalid JSON file: {path}: {error}") from error
    if not isinstance(value, dict):
        raise AssertionError(f"JSON root must be an object: {path}")
    return value


def _require_projection_string_array(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) for item in value
    ):
        raise AssertionError(f"{label} must be a string array")
    return list(value)


class ResearchProgramValidatorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repository_root = Path(self.temporary_directory.name)
        self.program_root = self.repository_root / "research" / "meta-research"
        for directory in (
            "governance",
            "catalog",
            "objects",
            "templates",
            "archive",
            "tools",
        ):
            (self.program_root / directory).mkdir(parents=True, exist_ok=True)
        (self.program_root / "README.md").write_text("# Test program\n", encoding="utf-8")
        self.catalog_path = (
            self.program_root / "catalog" / "research-objects.json"
        )
        self.research_object_schema_path = (
            self.program_root / "catalog" / "research-object.schema.json"
        )
        self.research_object_schema: dict[str, Any] = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "additionalProperties": False,
            "required": [
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
            ],
            "properties": {
                "schemaVersion": {
                    "type": "string",
                    "const": "research-object.v1",
                },
                "id": {
                    "type": "string",
                    "pattern": r"^[A-Z]{2,4}-[0-9]{3}$",
                },
                "type": {
                    "type": "string",
                    "enum": ["ResearchBaseline"],
                },
                "title": {"type": "string"},
                "version": {
                    "type": "string",
                    "pattern": r"^[0-9]+\.[0-9]+\.[0-9]+$",
                },
                "lifecycleState": {
                    "type": "string",
                    "enum": ["proposed"],
                },
                "evidenceLevel": {
                    "type": "string",
                    "enum": ["conceptual"],
                },
                "purpose": {"type": "string"},
                "dependsOn": {"type": "array"},
                "artifacts": {"type": "array"},
            },
        }
        self._write_json(
            self.research_object_schema_path,
            self.research_object_schema,
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_accepts_valid_catalog_and_reports_measurable_coverage(self) -> None:
        baseline = self._create_object("RB-001", "ResearchBaseline")
        dependent_baseline = self._create_object(
            "MS-001",
            "ResearchBaseline",
            depends_on=["RB-001"],
        )
        self._write_catalog([baseline, dependent_baseline])

        report = self._validator().validate()

        self.assertEqual(report.object_count, 2)
        self.assertEqual(report.dependency_count, 1)
        self.assertEqual(report.artifact_count, 2)
        self.assertEqual(report.catalog_coverage, 1.0)
        self.assertEqual(
            report.object_ids,
            ("MS-001", "RB-001"),
        )

    def test_rejects_object_type_not_declared_by_schema(self) -> None:
        meta_study = self._create_object("MS-001", "MetaStudy")
        self._write_catalog([meta_study])

        with self.assertRaisesRegex(
            ResearchProgramValidationError,
            "invalid object type: MS-001",
        ):
            self._validator().validate()

    def test_accepts_schema_declared_descriptor_schema_version(self) -> None:
        self.research_object_schema["properties"]["schemaVersion"]["const"] = (
            "research-object.v2"
        )
        self._write_json(
            self.research_object_schema_path,
            self.research_object_schema,
        )
        baseline = self._create_object(
            "RB-001",
            "ResearchBaseline",
            schema_version="research-object.v2",
        )
        self._write_catalog([baseline])

        report = self._validator().validate()

        self.assertEqual(report.object_ids, ("RB-001",))

    def test_rejects_descriptor_schema_version_not_declared_by_schema(self) -> None:
        self.research_object_schema["properties"]["schemaVersion"]["const"] = (
            "research-object.v2"
        )
        self._write_json(
            self.research_object_schema_path,
            self.research_object_schema,
        )
        baseline = self._create_object("RB-001", "ResearchBaseline")
        self._write_catalog([baseline])

        with self.assertRaisesRegex(
            ResearchProgramValidationError,
            "unsupported descriptor schemaVersion: RB-001",
        ):
            self._validator().validate()

    def test_accepts_optional_property_declared_by_schema(self) -> None:
        self.research_object_schema["properties"]["reviewNote"] = {
            "type": "string"
        }
        self._write_json(
            self.research_object_schema_path,
            self.research_object_schema,
        )
        baseline = self._create_object(
            "RB-001",
            "ResearchBaseline",
            extra_fields={"reviewNote": "Reviewed independently."},
        )
        self._write_catalog([baseline])

        report = self._validator().validate()

        self.assertEqual(report.object_ids, ("RB-001",))

    def test_accepts_each_declared_optional_union_type(self) -> None:
        self.research_object_schema["properties"]["reviewNote"] = {
            "type": ["string", "null"]
        }
        self._write_json(
            self.research_object_schema_path,
            self.research_object_schema,
        )
        for case, value in (("string", "Reviewed."), ("null", None)):
            with self.subTest(case=case):
                baseline = self._create_object(
                    "RB-001",
                    "ResearchBaseline",
                    extra_fields={"reviewNote": value},
                )
                self._write_catalog([baseline])

                report = self._validator().validate()

                self.assertEqual(report.object_ids, ("RB-001",))

    def test_rejects_value_outside_declared_optional_union_types(self) -> None:
        self.research_object_schema["properties"]["reviewNote"] = {
            "type": ["string", "null"]
        }
        self._write_json(
            self.research_object_schema_path,
            self.research_object_schema,
        )
        baseline = self._create_object(
            "RB-001",
            "ResearchBaseline",
            extra_fields={"reviewNote": 42},
        )
        self._write_catalog([baseline])

        with self.assertRaisesRegex(
            ResearchProgramValidationError,
            "invalid descriptor property type: RB-001.reviewNote",
        ):
            self._validator().validate()

    def test_rejects_malformed_optional_union_type_declarations(self) -> None:
        cases: tuple[tuple[str, list[Any]], ...] = (
            ("empty", []),
            ("duplicate", ["string", "string"]),
            ("non_string", ["string", 1]),
            ("unsupported", ["string", "date"]),
        )
        for case, declared_types in cases:
            with self.subTest(case=case):
                self.research_object_schema["properties"]["reviewNote"] = {
                    "type": declared_types
                }
                self._write_json(
                    self.research_object_schema_path,
                    self.research_object_schema,
                )
                baseline = self._create_object("RB-001", "ResearchBaseline")
                self._write_catalog([baseline])

                with self.assertRaisesRegex(
                    ResearchProgramValidationError,
                    "invalid research object schema: properties.reviewNote.type",
                ):
                    self._validator().validate()

    def test_accepts_optional_property_satisfying_declared_constraints(self) -> None:
        self.research_object_schema["properties"]["reviewNote"] = {
            "type": "string",
            "const": "approved",
            "enum": ["approved"],
            "pattern": r"^approved$",
        }
        self._write_json(
            self.research_object_schema_path,
            self.research_object_schema,
        )
        baseline = self._create_object(
            "RB-001",
            "ResearchBaseline",
            extra_fields={"reviewNote": "approved"},
        )
        self._write_catalog([baseline])

        report = self._validator().validate()

        self.assertEqual(report.object_ids, ("RB-001",))

    def test_rejects_optional_property_violating_declared_constraints(self) -> None:
        cases: tuple[tuple[str, dict[str, Any], Any], ...] = (
            ("type", {"type": "string"}, 42),
            ("const", {"const": "approved"}, "draft"),
            ("enum", {"enum": ["approved"]}, "draft"),
            ("pattern", {"pattern": r"^approved$"}, "draft"),
        )
        for constraint, definition, value in cases:
            with self.subTest(constraint=constraint):
                self.research_object_schema["properties"]["reviewNote"] = definition
                self._write_json(
                    self.research_object_schema_path,
                    self.research_object_schema,
                )
                baseline = self._create_object(
                    "RB-001",
                    "ResearchBaseline",
                    extra_fields={"reviewNote": value},
                )
                self._write_catalog([baseline])

                with self.assertRaisesRegex(
                    ResearchProgramValidationError,
                    f"invalid descriptor property {constraint}: RB-001.reviewNote",
                ):
                    self._validator().validate()

    def test_rejects_boolean_for_numeric_optional_const(self) -> None:
        self._assert_optional_property_rejected(
            definition={"const": 1},
            value=True,
            constraint="const",
        )

    def test_rejects_boolean_for_numeric_optional_enum(self) -> None:
        self._assert_optional_property_rejected(
            definition={"enum": [1]},
            value=True,
            constraint="enum",
        )

    def test_rejects_number_for_boolean_optional_const(self) -> None:
        self._assert_optional_property_rejected(
            definition={"const": True},
            value=1,
            constraint="const",
        )

    def test_rejects_number_for_boolean_optional_enum(self) -> None:
        self._assert_optional_property_rejected(
            definition={"enum": [True]},
            value=1,
            constraint="enum",
        )

    def test_preserves_json_types_in_nested_const_and_enum_values(self) -> None:
        cases: tuple[tuple[str, dict[str, Any], Any], ...] = (
            (
                "const",
                {"const": {"values": [1, {"flag": True}]}},
                {"values": [True, {"flag": 1}]},
            ),
            (
                "enum",
                {"enum": [[1, {"flag": True}]]},
                [True, {"flag": 1}],
            ),
        )
        for constraint, definition, value in cases:
            with self.subTest(constraint=constraint):
                self._assert_optional_property_rejected(
                    definition=definition,
                    value=value,
                    constraint=constraint,
                )

    def test_rejects_unknown_descriptor_property(self) -> None:
        baseline = self._create_object(
            "RB-001",
            "ResearchBaseline",
            extra_fields={"unknownField": "not declared by schema"},
        )
        self._write_catalog([baseline])

        with self.assertRaisesRegex(
            ResearchProgramValidationError,
            "unknown descriptor fields:.*unknownField",
        ):
            self._validator().validate()

    def test_rejects_missing_required_descriptor_property(self) -> None:
        baseline = self._create_object(
            "RB-001",
            "ResearchBaseline",
            omitted_fields={"title"},
        )
        self._write_catalog([baseline])

        with self.assertRaisesRegex(
            ResearchProgramValidationError,
            "missing required descriptor fields:.*title",
        ):
            self._validator().validate()

    def test_rejects_required_property_missing_from_schema_properties(self) -> None:
        self.research_object_schema["required"].append("reviewNote")
        self._write_json(
            self.research_object_schema_path,
            self.research_object_schema,
        )
        baseline = self._create_object("RB-001", "ResearchBaseline")
        self._write_catalog([baseline])

        with self.assertRaisesRegex(
            ResearchProgramValidationError,
            "invalid research object schema: required contains undefined properties: reviewNote",
        ):
            self._validator().validate()

    def test_rejects_missing_or_non_boolean_additional_properties(self) -> None:
        baseline = self._create_object("RB-001", "ResearchBaseline")
        self._write_catalog([baseline])
        cases: tuple[tuple[str, Any], ...] = (
            ("missing", None),
            ("non_boolean", "false"),
        )
        for case, value in cases:
            with self.subTest(case=case):
                if case == "missing":
                    self.research_object_schema.pop("additionalProperties", None)
                else:
                    self.research_object_schema["additionalProperties"] = value
                self._write_json(
                    self.research_object_schema_path,
                    self.research_object_schema,
                )

                with self.assertRaisesRegex(
                    ResearchProgramValidationError,
                    "invalid research object schema: additionalProperties must be a boolean",
                ):
                    self._validator().validate()

    def test_rejects_non_standard_json_constants(self) -> None:
        baseline = self._create_object("RB-001", "ResearchBaseline")
        self._write_catalog([baseline])
        descriptor_path = self.repository_root / baseline
        valid_descriptor = descriptor_path.read_text(encoding="utf-8")

        for constant in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(constant=constant):
                descriptor_path.write_text(
                    valid_descriptor.replace('"Object RB-001"', constant),
                    encoding="utf-8",
                )

                with self.assertRaisesRegex(
                    ResearchProgramValidationError,
                    f"invalid JSON constant: {constant}",
                ):
                    self._validator().validate()

    def test_rejects_invalid_utf8_schema_as_domain_error(self) -> None:
        baseline = self._create_object("RB-001", "ResearchBaseline")
        self._write_catalog([baseline])
        self.research_object_schema_path.write_bytes(b"{\"type\": \"\xff\"}")

        self._assert_invalid_json_domain_error()

    def test_rejects_invalid_utf8_catalog_as_domain_error(self) -> None:
        self.catalog_path.write_bytes(b"{\"schemaVersion\": \"\xff\"}")

        self._assert_invalid_json_domain_error()

    def test_graph_projection_helper_rejects_duplicate_descriptor_keys(self) -> None:
        baseline = self._create_object("RB-001", "ResearchBaseline")
        self._write_catalog([baseline])
        descriptor_path = self.repository_root / baseline
        descriptor_source = descriptor_path.read_text(encoding="utf-8")
        descriptor_path.write_text(
            descriptor_source.replace(
                '"id": "RB-001",',
                '"id": "RB-001",\n  "id": "RB-999",',
            ),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(AssertionError, "duplicate JSON key: id"):
            build_repository_object_graph_projection(self.repository_root)

    def test_rejects_malformed_research_object_schema(self) -> None:
        baseline = self._create_object("RB-001", "ResearchBaseline")
        self._write_catalog([baseline])
        self._write_json(
            self.research_object_schema_path,
            {"required": [], "properties": {}},
        )

        with self.assertRaisesRegex(
            ResearchProgramValidationError,
            "invalid research object schema:",
        ):
            self._validator().validate()

    def test_rejects_duplicate_object_id(self) -> None:
        first = self._create_object("RB-001", "ResearchBaseline", directory_name="first")
        second = self._create_object("RB-001", "ResearchBaseline", directory_name="second")
        self._write_catalog([first, second])

        with self.assertRaisesRegex(
            ResearchProgramValidationError,
            "duplicate object id: RB-001",
        ):
            self._validator().validate()

    def test_rejects_artifact_path_owned_by_multiple_objects(self) -> None:
        first = self._create_object("MS-001", "ResearchBaseline")
        shared_artifact = (Path(first).parent / "README.md").as_posix()
        second = self._create_object(
            "RB-001",
            "ResearchBaseline",
            extra_fields={"artifacts": [shared_artifact]},
        )
        self._write_catalog([first, second])

        with self.assertRaisesRegex(
            ResearchProgramValidationError,
            (
                "artifact path has multiple owners: "
                ".*objects/MS-001/README.md: MS-001, RB-001"
            ),
        ):
            self._validator().validate()

    def test_rejects_unknown_dependency(self) -> None:
        dependent_baseline = self._create_object(
            "MS-001",
            "ResearchBaseline",
            depends_on=["RB-999"],
        )
        self._write_catalog([dependent_baseline])

        with self.assertRaisesRegex(
            ResearchProgramValidationError,
            "unknown dependency: MS-001 -> RB-999",
        ):
            self._validator().validate()

    def test_rejects_dependency_cycle(self) -> None:
        first = self._create_object(
            "MS-001",
            "ResearchBaseline",
            depends_on=["RP-001"],
        )
        second = self._create_object(
            "RP-001",
            "ResearchBaseline",
            depends_on=["MS-001"],
        )
        self._write_catalog([first, second])

        with self.assertRaisesRegex(
            ResearchProgramValidationError,
            "dependency cycle:",
        ):
            self._validator().validate()

    def _validator(self) -> ResearchProgramValidator:
        return ResearchProgramValidator(
            repository_root=self.repository_root,
            program_root=self.program_root,
        )

    def _assert_optional_property_rejected(
        self,
        *,
        definition: dict[str, Any],
        value: Any,
        constraint: str,
    ) -> None:
        self.research_object_schema["properties"]["reviewNote"] = definition
        self._write_json(
            self.research_object_schema_path,
            self.research_object_schema,
        )
        baseline = self._create_object(
            "RB-001",
            "ResearchBaseline",
            extra_fields={"reviewNote": value},
        )
        self._write_catalog([baseline])

        with self.assertRaisesRegex(
            ResearchProgramValidationError,
            f"invalid descriptor property {constraint}: RB-001.reviewNote",
        ):
            self._validator().validate()

    def _create_object(
        self,
        object_id: str,
        object_type: str,
        *,
        depends_on: list[str] | None = None,
        directory_name: str | None = None,
        schema_version: str = "research-object.v1",
        extra_fields: dict[str, Any] | None = None,
        omitted_fields: set[str] | None = None,
    ) -> str:
        directory = self.program_root / "objects" / (directory_name or object_id)
        directory.mkdir(parents=True, exist_ok=True)
        artifact_path = directory / "README.md"
        artifact_path.write_text(f"# {object_id}\n", encoding="utf-8")
        descriptor_path = directory / "object.json"
        descriptor: dict[str, Any] = {
            "schemaVersion": schema_version,
            "id": object_id,
            "type": object_type,
            "title": f"Object {object_id}",
            "version": "1.0.0",
            "lifecycleState": "proposed",
            "evidenceLevel": "conceptual",
            "purpose": "Validate the research object contract.",
            "dependsOn": depends_on or [],
            "artifacts": [artifact_path.relative_to(self.repository_root).as_posix()],
        }
        descriptor.update(extra_fields or {})
        for field in omitted_fields or set():
            descriptor.pop(field)
        self._write_json(descriptor_path, descriptor)
        return descriptor_path.relative_to(self.repository_root).as_posix()

    def _write_catalog(self, descriptors: list[str]) -> None:
        entries = [
            {"descriptor": descriptor}
            for descriptor in sorted(descriptors)
        ]
        self._write_json(
            self.catalog_path,
            {
                "schemaVersion": "research-object-catalog.v1",
                "objects": entries,
            },
        )

    @staticmethod
    def _write_json(path: Path, value: dict[str, Any]) -> None:
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _assert_invalid_json_domain_error(self) -> None:
        try:
            self._validator().validate()
        except Exception as error:  # Boundary assertion distinguishes domain conversion.
            self.assertIsInstance(error, ResearchProgramValidationError)
            self.assertIn("invalid JSON file:", str(error))
        else:
            self.fail("ResearchProgramValidationError not raised")


class RepositoryResearchProgramStructureTest(unittest.TestCase):
    def test_repository_meta_research_program_is_complete(self) -> None:
        repository_root = Path(__file__).resolve().parents[3]
        validator = ResearchProgramValidator(
            repository_root=repository_root,
            program_root=repository_root / "research" / "meta-research",
        )

        report = validator.validate()

        self.assertEqual(
            report.object_ids,
            (
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
            ),
        )
        self.assertEqual(report.object_count, 30)
        self.assertEqual(report.dependency_count, 46)
        self.assertEqual(report.artifact_count, 70)
        self.assertEqual(report.catalog_coverage, 1.0)

    def test_repository_graph_matches_centralized_traceability_oracle(self) -> None:
        projection = build_repository_object_graph_projection(
            Path(__file__).resolve().parents[3]
        )

        self._assert_matches_traceability_oracle(projection)

    def test_traceability_oracle_rejects_count_preserving_graph_mutations(
        self,
    ) -> None:
        projection = build_repository_object_graph_projection(
            Path(__file__).resolve().parents[3]
        )

        dependency_drift = copy.deepcopy(projection)
        self._record_by_id(dependency_drift, "MC-001")["dependsOn"] = ["MS-001"]
        with self.subTest(mutation="count-preserving dependency drift"):
            with self.assertRaises(AssertionError):
                self._assert_matches_traceability_oracle(dependency_drift)

        artifact_swap = copy.deepcopy(projection)
        model_candidate = self._record_by_id(artifact_swap, "MC-001")
        meta_study = self._record_by_id(artifact_swap, "MS-001")
        model_candidate["artifacts"][0], meta_study["artifacts"][0] = (
            meta_study["artifacts"][0],
            model_candidate["artifacts"][0],
        )
        with self.subTest(mutation="count-preserving artifact swap"):
            with self.assertRaises(AssertionError):
                self._assert_matches_traceability_oracle(artifact_swap)

    def _assert_matches_traceability_oracle(
        self,
        projection: list[dict[str, Any]],
    ) -> None:
        self.assertEqual(
            repository_object_graph_projection_sha256(projection),
            EXPECTED_RP001_OBJECT_GRAPH_PROJECTION_SHA256,
        )

    @staticmethod
    def _record_by_id(
        projection: list[dict[str, Any]],
        identifier: str,
    ) -> dict[str, Any]:
        return next(record for record in projection if record["id"] == identifier)


if __name__ == "__main__":
    unittest.main()
