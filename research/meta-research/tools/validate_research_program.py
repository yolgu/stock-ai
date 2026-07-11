from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping, NoReturn


class ResearchProgramValidationError(ValueError):
    """Raised when a research-program structural invariant is violated."""


@dataclass(frozen=True)
class ValidationReport:
    object_count: int
    object_ids: tuple[str, ...]
    dependency_count: int
    artifact_count: int
    catalog_coverage: float


@dataclass(frozen=True)
class ResearchObjectSchema:
    descriptor_schema_version: str
    required_fields: frozenset[str]
    property_names: frozenset[str]
    additional_properties: bool
    property_constraints: Mapping[str, ResearchObjectPropertyConstraints]
    identifier_pattern: re.Pattern[str]
    version_pattern: re.Pattern[str]
    object_types: frozenset[str]
    lifecycle_states: frozenset[str]
    evidence_levels: frozenset[str]


@dataclass(frozen=True)
class ResearchObjectPropertyConstraints:
    expected_types: frozenset[str] | None
    has_constant: bool
    constant: Any
    enum_values: tuple[Any, ...] | None
    pattern: re.Pattern[str] | None


@dataclass(frozen=True)
class ResearchObjectDescriptor:
    identifier: str
    depends_on: tuple[str, ...]
    artifact_paths: tuple[Path, ...]

    @property
    def artifact_count(self) -> int:
        return len(self.artifact_paths)


class ResearchProgramValidator:
    _CATALOG_SCHEMA_VERSION = "research-object-catalog.v1"
    _SUPPORTED_JSON_TYPES = frozenset(
        {
            "array",
            "boolean",
            "integer",
            "null",
            "number",
            "object",
            "string",
        }
    )
    _REQUIRED_DIRECTORIES = (
        "governance",
        "catalog",
        "objects",
        "templates",
        "archive",
        "tools",
    )

    def __init__(self, repository_root: Path, program_root: Path) -> None:
        self._repository_root = repository_root.resolve()
        self._program_root = program_root.resolve()

    def validate(self) -> ValidationReport:
        self._validate_program_boundary()
        catalog = self._load_json(
            self._program_root / "catalog" / "research-objects.json"
        )
        research_object_schema = self._read_research_object_schema(
            self._load_json(
                self._program_root / "catalog" / "research-object.schema.json"
            )
        )
        descriptor_paths = self._read_catalog(catalog)
        self._validate_catalog_coverage(descriptor_paths)
        descriptors = tuple(
            self._read_descriptor(path, research_object_schema)
            for path in descriptor_paths
        )
        descriptor_by_id = self._index_descriptors(descriptors)
        self._validate_identifier_order(descriptors)
        self._validate_unique_artifact_ownership(descriptors)
        self._validate_dependencies(descriptor_by_id)
        self._validate_acyclic_dependencies(descriptor_by_id)
        return ValidationReport(
            object_count=len(descriptors),
            object_ids=tuple(sorted(descriptor_by_id)),
            dependency_count=sum(
                len(descriptor.depends_on)
                for descriptor in descriptors
            ),
            artifact_count=sum(
                descriptor.artifact_count
                for descriptor in descriptors
            ),
            catalog_coverage=1.0,
        )

    def _validate_program_boundary(self) -> None:
        if not self._program_root.is_relative_to(self._repository_root):
            raise ResearchProgramValidationError(
                "program root must be inside repository root"
            )
        if not (self._program_root / "README.md").is_file():
            raise ResearchProgramValidationError("missing program README.md")
        for directory in self._REQUIRED_DIRECTORIES:
            if not (self._program_root / directory).is_dir():
                raise ResearchProgramValidationError(
                    f"missing required directory: {directory}"
                )

    def _read_research_object_schema(self, value: Any) -> ResearchObjectSchema:
        if not isinstance(value, dict):
            raise self._invalid_schema("schema must be an object")
        required_fields = self._read_schema_string_set(
            value.get("required"),
            "required",
        )
        properties = value.get("properties")
        if not isinstance(properties, dict):
            raise self._invalid_schema("properties must be an object")
        property_names = frozenset(properties)
        undefined_required_fields = required_fields - property_names
        if undefined_required_fields:
            raise self._invalid_schema(
                "required contains undefined properties: "
                f"{', '.join(sorted(undefined_required_fields))}"
            )
        additional_properties = value.get("additionalProperties")
        if not isinstance(additional_properties, bool):
            raise self._invalid_schema("additionalProperties must be a boolean")
        property_constraints = self._read_property_constraints(properties)
        return ResearchObjectSchema(
            descriptor_schema_version=self._read_schema_const(
                properties,
                "schemaVersion",
            ),
            required_fields=required_fields,
            property_names=property_names,
            additional_properties=additional_properties,
            property_constraints=property_constraints,
            identifier_pattern=self._read_schema_pattern(properties, "id"),
            version_pattern=self._read_schema_pattern(properties, "version"),
            object_types=self._read_schema_enum(properties, "type"),
            lifecycle_states=self._read_schema_enum(properties, "lifecycleState"),
            evidence_levels=self._read_schema_enum(properties, "evidenceLevel"),
        )

    def _read_property_constraints(
        self,
        properties: dict[str, Any],
    ) -> Mapping[str, ResearchObjectPropertyConstraints]:
        constraints = {
            property_name: self._read_property_constraint(property_name, definition)
            for property_name, definition in properties.items()
        }
        return MappingProxyType(constraints)

    def _read_property_constraint(
        self,
        property_name: str,
        definition: Any,
    ) -> ResearchObjectPropertyConstraints:
        if not isinstance(definition, dict):
            raise self._invalid_schema(
                f"properties.{property_name} must be an object"
            )
        enum_values = definition.get("enum")
        if enum_values is not None and (
            not isinstance(enum_values, list) or not enum_values
        ):
            raise self._invalid_schema(
                f"properties.{property_name}.enum must be a non-empty array"
            )
        return ResearchObjectPropertyConstraints(
            expected_types=self._read_property_types(
                definition.get("type"),
                f"properties.{property_name}.type",
            ),
            has_constant="const" in definition,
            constant=definition.get("const"),
            enum_values=(
                None if enum_values is None else tuple(enum_values)
            ),
            pattern=self._read_optional_schema_pattern(
                definition.get("pattern"),
                f"properties.{property_name}.pattern",
            ),
        )

    def _read_property_types(
        self,
        value: Any,
        label: str,
    ) -> frozenset[str] | None:
        if value is None:
            return None
        if isinstance(value, str):
            declared_types = (value,)
        elif isinstance(value, list):
            if not value:
                raise self._invalid_schema(f"{label} must not be empty")
            if any(
                not isinstance(declared_type, str) or not declared_type.strip()
                for declared_type in value
            ):
                raise self._invalid_schema(
                    f"{label} must contain only non-blank strings"
                )
            if len(set(value)) != len(value):
                raise self._invalid_schema(f"{label} must not contain duplicates")
            declared_types = tuple(value)
        else:
            raise self._invalid_schema(
                f"{label} must be a string or non-empty array of strings"
            )
        unsupported_types = set(declared_types) - self._SUPPORTED_JSON_TYPES
        if unsupported_types:
            raise self._invalid_schema(
                f"{label} contains unsupported types: "
                f"{', '.join(sorted(unsupported_types))}"
            )
        return frozenset(declared_types)

    def _read_optional_schema_pattern(
        self,
        value: Any,
        label: str,
    ) -> re.Pattern[str] | None:
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise self._invalid_schema(f"{label} must be non-blank text")
        try:
            return re.compile(value)
        except re.error as error:
            raise self._invalid_schema(f"{label} is invalid: {error}") from error

    def _read_schema_const(
        self,
        properties: dict[str, Any],
        property_name: str,
    ) -> str:
        definition = self._read_schema_property(properties, property_name)
        constant = definition.get("const")
        if not isinstance(constant, str) or not constant.strip():
            raise self._invalid_schema(
                f"properties.{property_name}.const must be non-blank text"
            )
        return constant

    def _read_schema_pattern(
        self,
        properties: dict[str, Any],
        property_name: str,
    ) -> re.Pattern[str]:
        definition = self._read_schema_property(properties, property_name)
        pattern = definition.get("pattern")
        if not isinstance(pattern, str) or not pattern.strip():
            raise self._invalid_schema(
                f"properties.{property_name}.pattern must be non-blank text"
            )
        try:
            return re.compile(pattern)
        except re.error as error:
            raise self._invalid_schema(
                f"properties.{property_name}.pattern is invalid: {error}"
            ) from error

    def _read_schema_enum(
        self,
        properties: dict[str, Any],
        property_name: str,
    ) -> frozenset[str]:
        definition = self._read_schema_property(properties, property_name)
        return self._read_schema_string_set(
            definition.get("enum"),
            f"properties.{property_name}.enum",
        )

    def _read_schema_property(
        self,
        properties: dict[str, Any],
        property_name: str,
    ) -> dict[str, Any]:
        definition = properties.get(property_name)
        if not isinstance(definition, dict):
            raise self._invalid_schema(
                f"properties.{property_name} must be an object"
            )
        return definition

    def _read_schema_string_set(
        self,
        value: Any,
        label: str,
    ) -> frozenset[str]:
        if (
            not isinstance(value, list)
            or not value
            or any(not isinstance(item, str) or not item.strip() for item in value)
        ):
            raise self._invalid_schema(
                f"{label} must be a non-empty array of non-blank strings"
            )
        if len(set(value)) != len(value):
            raise self._invalid_schema(f"{label} must not contain duplicates")
        return frozenset(value)

    @staticmethod
    def _invalid_schema(detail: str) -> ResearchProgramValidationError:
        return ResearchProgramValidationError(
            f"invalid research object schema: {detail}"
        )

    def _read_catalog(self, catalog: Any) -> tuple[Path, ...]:
        if not isinstance(catalog, dict):
            raise ResearchProgramValidationError("catalog must be an object")
        if catalog.get("schemaVersion") != self._CATALOG_SCHEMA_VERSION:
            raise ResearchProgramValidationError("unsupported catalog schemaVersion")
        entries = catalog.get("objects")
        if not isinstance(entries, list) or not entries:
            raise ResearchProgramValidationError("catalog objects must be non-empty")
        descriptor_paths: list[Path] = []
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict) or set(entry) != {"descriptor"}:
                raise ResearchProgramValidationError(
                    f"catalog object {index} must contain only descriptor"
                )
            descriptor_paths.append(
                self._resolve_repository_path(
                    entry["descriptor"],
                    f"catalog object {index} descriptor",
                )
            )
        if len(set(descriptor_paths)) != len(descriptor_paths):
            raise ResearchProgramValidationError("duplicate descriptor path")
        return tuple(descriptor_paths)

    def _validate_catalog_coverage(self, catalog_paths: tuple[Path, ...]) -> None:
        discovered_paths = tuple(
            sorted((self._program_root / "objects").glob("**/object.json"))
        )
        catalog_set = set(catalog_paths)
        discovered_set = {path.resolve() for path in discovered_paths}
        if catalog_set != discovered_set:
            missing = sorted(discovered_set - catalog_set)
            extra = sorted(catalog_set - discovered_set)
            raise ResearchProgramValidationError(
                "catalog coverage mismatch: "
                f"unregistered={self._relative_paths(missing)} "
                f"missing={self._relative_paths(extra)}"
            )

    def _read_descriptor(
        self,
        descriptor_path: Path,
        schema: ResearchObjectSchema,
    ) -> ResearchObjectDescriptor:
        value = self._load_json(descriptor_path)
        if not isinstance(value, dict):
            raise ResearchProgramValidationError(
                f"descriptor must be an object: {self._relative_path(descriptor_path)}"
            )
        descriptor_fields = set(value)
        missing_fields = schema.required_fields - descriptor_fields
        if missing_fields:
            raise ResearchProgramValidationError(
                "missing required descriptor fields: "
                f"{self._relative_path(descriptor_path)}: "
                f"{', '.join(sorted(missing_fields))}"
            )
        unknown_fields = descriptor_fields - schema.property_names
        if unknown_fields and not schema.additional_properties:
            raise ResearchProgramValidationError(
                "unknown descriptor fields: "
                f"{self._relative_path(descriptor_path)}: "
                f"{', '.join(sorted(unknown_fields))}"
            )
        identifier = self._require_identifier(
            value.get("id"),
            "descriptor id",
            schema.identifier_pattern,
        )
        if value.get("schemaVersion") != schema.descriptor_schema_version:
            raise ResearchProgramValidationError(
                f"unsupported descriptor schemaVersion: {identifier}"
            )
        if value.get("type") not in schema.object_types:
            raise ResearchProgramValidationError(
                f"invalid object type: {identifier}"
            )
        self._require_non_blank_text(value.get("title"), f"{identifier} title")
        version = self._require_non_blank_text(
            value.get("version"),
            f"{identifier} version",
        )
        if not schema.version_pattern.fullmatch(version):
            raise ResearchProgramValidationError(
                f"invalid semantic version: {identifier}"
            )
        if value.get("lifecycleState") not in schema.lifecycle_states:
            raise ResearchProgramValidationError(
                f"invalid lifecycle state: {identifier}"
            )
        if value.get("evidenceLevel") not in schema.evidence_levels:
            raise ResearchProgramValidationError(
                f"invalid evidence level: {identifier}"
            )
        self._require_non_blank_text(value.get("purpose"), f"{identifier} purpose")
        depends_on = self._read_identifier_list(
            value.get("dependsOn"),
            f"{identifier} dependsOn",
            schema.identifier_pattern,
        )
        artifacts = self._read_artifacts(identifier, value.get("artifacts"))
        self._validate_declared_properties(identifier, value, schema)
        return ResearchObjectDescriptor(
            identifier=identifier,
            depends_on=depends_on,
            artifact_paths=artifacts,
        )

    def _validate_declared_properties(
        self,
        identifier: str,
        descriptor: dict[str, Any],
        schema: ResearchObjectSchema,
    ) -> None:
        for property_name in sorted(set(descriptor) & schema.property_names):
            self._validate_declared_property(
                identifier,
                property_name,
                descriptor[property_name],
                schema.property_constraints[property_name],
            )

    def _validate_declared_property(
        self,
        identifier: str,
        property_name: str,
        value: Any,
        constraints: ResearchObjectPropertyConstraints,
    ) -> None:
        label = f"{identifier}.{property_name}"
        if (
            constraints.expected_types is not None
            and not any(
                self._matches_json_type(value, expected_type)
                for expected_type in constraints.expected_types
            )
        ):
            raise ResearchProgramValidationError(
                f"invalid descriptor property type: {label}"
            )
        if (
            constraints.has_constant
            and not self._json_values_equal(value, constraints.constant)
        ):
            raise ResearchProgramValidationError(
                f"invalid descriptor property const: {label}"
            )
        if (
            constraints.enum_values is not None
            and not any(
                self._json_values_equal(value, enum_value)
                for enum_value in constraints.enum_values
            )
        ):
            raise ResearchProgramValidationError(
                f"invalid descriptor property enum: {label}"
            )
        if (
            constraints.pattern is not None
            and isinstance(value, str)
            and constraints.pattern.search(value) is None
        ):
            raise ResearchProgramValidationError(
                f"invalid descriptor property pattern: {label}"
            )

    @classmethod
    def _json_values_equal(cls, left: Any, right: Any) -> bool:
        if isinstance(left, bool) or isinstance(right, bool):
            return isinstance(left, bool) and isinstance(right, bool) and left == right
        if left is None or right is None:
            return left is None and right is None
        left_is_number = isinstance(left, (int, float))
        right_is_number = isinstance(right, (int, float))
        if left_is_number or right_is_number:
            return left_is_number and right_is_number and left == right
        if isinstance(left, str) or isinstance(right, str):
            return isinstance(left, str) and isinstance(right, str) and left == right
        if isinstance(left, list) or isinstance(right, list):
            return (
                isinstance(left, list)
                and isinstance(right, list)
                and len(left) == len(right)
                and all(
                    cls._json_values_equal(left_item, right_item)
                    for left_item, right_item in zip(left, right)
                )
            )
        if isinstance(left, dict) or isinstance(right, dict):
            return (
                isinstance(left, dict)
                and isinstance(right, dict)
                and left.keys() == right.keys()
                and all(
                    cls._json_values_equal(left[key], right[key])
                    for key in left
                )
            )
        return False

    @staticmethod
    def _matches_json_type(value: Any, expected_type: str) -> bool:
        if expected_type == "array":
            return isinstance(value, list)
        if expected_type == "boolean":
            return isinstance(value, bool)
        if expected_type == "integer":
            return isinstance(value, int) and not isinstance(value, bool)
        if expected_type == "null":
            return value is None
        if expected_type == "number":
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        if expected_type == "object":
            return isinstance(value, dict)
        return isinstance(value, str)

    def _read_artifacts(self, identifier: str, value: Any) -> tuple[Path, ...]:
        if not isinstance(value, list) or not value:
            raise ResearchProgramValidationError(
                f"{identifier} artifacts must be non-empty"
            )
        paths = tuple(
            self._resolve_repository_path(path, f"{identifier} artifact")
            for path in value
        )
        if len(set(paths)) != len(paths):
            raise ResearchProgramValidationError(
                f"duplicate artifact path: {identifier}"
            )
        for path in paths:
            if not path.exists():
                raise ResearchProgramValidationError(
                    f"missing artifact: {self._relative_path(path)}"
                )
        return paths

    def _index_descriptors(
        self,
        descriptors: tuple[ResearchObjectDescriptor, ...],
    ) -> dict[str, ResearchObjectDescriptor]:
        descriptor_by_id: dict[str, ResearchObjectDescriptor] = {}
        for descriptor in descriptors:
            if descriptor.identifier in descriptor_by_id:
                raise ResearchProgramValidationError(
                    f"duplicate object id: {descriptor.identifier}"
                )
            descriptor_by_id[descriptor.identifier] = descriptor
        return descriptor_by_id

    @staticmethod
    def _validate_identifier_order(
        descriptors: tuple[ResearchObjectDescriptor, ...],
    ) -> None:
        identifiers = [descriptor.identifier for descriptor in descriptors]
        if identifiers != sorted(identifiers):
            raise ResearchProgramValidationError(
                "catalog objects must be sorted by object id"
            )

    def _validate_unique_artifact_ownership(
        self,
        descriptors: tuple[ResearchObjectDescriptor, ...],
    ) -> None:
        owner_by_artifact_path: dict[Path, str] = {}
        for descriptor in descriptors:
            for artifact_path in descriptor.artifact_paths:
                existing_owner = owner_by_artifact_path.get(artifact_path)
                if existing_owner is not None:
                    raise ResearchProgramValidationError(
                        "artifact path has multiple owners: "
                        f"{self._relative_path(artifact_path)}: "
                        f"{existing_owner}, {descriptor.identifier}"
                    )
                owner_by_artifact_path[artifact_path] = descriptor.identifier

    @staticmethod
    def _validate_dependencies(
        descriptor_by_id: dict[str, ResearchObjectDescriptor],
    ) -> None:
        for descriptor in descriptor_by_id.values():
            for dependency in descriptor.depends_on:
                if dependency not in descriptor_by_id:
                    raise ResearchProgramValidationError(
                        "unknown dependency: "
                        f"{descriptor.identifier} -> {dependency}"
                    )

    @staticmethod
    def _validate_acyclic_dependencies(
        descriptor_by_id: dict[str, ResearchObjectDescriptor],
    ) -> None:
        visiting: list[str] = []
        visited: set[str] = set()

        def visit(identifier: str) -> None:
            if identifier in visiting:
                cycle_start = visiting.index(identifier)
                cycle = visiting[cycle_start:] + [identifier]
                raise ResearchProgramValidationError(
                    f"dependency cycle: {' -> '.join(cycle)}"
                )
            if identifier in visited:
                return
            visiting.append(identifier)
            for dependency in descriptor_by_id[identifier].depends_on:
                visit(dependency)
            visiting.pop()
            visited.add(identifier)

        for identifier in descriptor_by_id:
            visit(identifier)

    def _resolve_repository_path(self, value: Any, label: str) -> Path:
        text = self._require_non_blank_text(value, label)
        path = (self._repository_root / text).resolve()
        if not path.is_relative_to(self._repository_root):
            raise ResearchProgramValidationError(
                f"{label} must stay inside repository root"
            )
        return path

    def _read_identifier_list(
        self,
        value: Any,
        label: str,
        identifier_pattern: re.Pattern[str],
    ) -> tuple[str, ...]:
        if not isinstance(value, list):
            raise ResearchProgramValidationError(f"{label} must be an array")
        identifiers = tuple(
            self._require_identifier(identifier, label, identifier_pattern)
            for identifier in value
        )
        if len(set(identifiers)) != len(identifiers):
            raise ResearchProgramValidationError(f"{label} contains duplicates")
        if list(identifiers) != sorted(identifiers):
            raise ResearchProgramValidationError(f"{label} must be sorted")
        return identifiers

    def _require_identifier(
        self,
        value: Any,
        label: str,
        identifier_pattern: re.Pattern[str],
    ) -> str:
        text = self._require_non_blank_text(value, label)
        if not identifier_pattern.fullmatch(text):
            raise ResearchProgramValidationError(f"invalid {label}: {text}")
        return text

    @staticmethod
    def _require_non_blank_text(value: Any, label: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ResearchProgramValidationError(f"{label} must be non-blank text")
        return value

    @staticmethod
    def _load_json(path: Path) -> Any:
        if not path.is_file():
            raise ResearchProgramValidationError(f"missing JSON file: {path}")
        try:
            return json.loads(
                path.read_text(encoding="utf-8"),
                object_pairs_hook=ResearchProgramValidator._reject_duplicate_keys,
                parse_constant=ResearchProgramValidator._reject_json_constant,
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ResearchProgramValidationError(
                f"invalid JSON file: {path}: {error}"
            ) from error

    @staticmethod
    def _reject_json_constant(value: str) -> NoReturn:
        raise ResearchProgramValidationError(f"invalid JSON constant: {value}")

    @staticmethod
    def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ResearchProgramValidationError(
                    f"duplicate JSON key: {key}"
                )
            value[key] = item
        return value

    def _relative_path(self, path: Path) -> str:
        return path.relative_to(self._repository_root).as_posix()

    def _relative_paths(self, paths: Iterable[Path]) -> list[str]:
        return [self._relative_path(path) for path in paths]


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate the research meta-program object graph."
    )
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--program-root", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    validator = ResearchProgramValidator(
        repository_root=arguments.repository_root,
        program_root=arguments.program_root,
    )
    try:
        report = validator.validate()
    except ResearchProgramValidationError as error:
        print(f"INVALID {error}")
        return 1
    print(
        "VALID "
        f"objects={report.object_count} "
        f"dependencies={report.dependency_count} "
        f"artifacts={report.artifact_count} "
        f"catalogCoverage={report.catalog_coverage:.2f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
