from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from pathlib import PurePosixPath
from typing import Iterable, Mapping, TypeAlias, cast


JsonScalar: TypeAlias = None | bool | int | float | str
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
RUN_MANIFEST_SCHEMA = "research-run-artifact-manifest.v1"


class ArtifactIntegrityError(ValueError):
    """Raised when an artifact no longer matches its frozen integrity contract."""


@dataclass(frozen=True)
class InputArtifact:
    identifier: str
    path: Path
    expected_sha256: str
    manifest_path: str


@dataclass(frozen=True)
class ArtifactRecord:
    identifier: str
    manifest_path: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class VerificationReport:
    manifest_sha256: str
    manifest_payload_sha256: str
    input_count: int
    output_count: int


class ArtifactStore:
    def __init__(self, root_directory: Path) -> None:
        if not isinstance(root_directory, Path):
            raise ArtifactIntegrityError("artifact store root must be pathlib.Path")
        self._root_directory = root_directory.resolve()

    def write_json(
        self,
        *,
        identifier: str,
        relative_path: str,
        value: JsonValue,
    ) -> ArtifactRecord:
        normalized_path = _require_safe_relative_path(relative_path, identifier)
        _require_identifier(identifier, role="output")
        target = self._resolve_output_path(normalized_path, identifier)
        atomic_write_json(target, value)
        return self._record_output(identifier, normalized_path)

    def write_run_manifest(
        self,
        *,
        inputs: Iterable[InputArtifact],
        outputs: Iterable[ArtifactRecord],
        manifest_relative_path: str = "run-manifest.json",
    ) -> ArtifactRecord:
        manifest_path = _require_safe_relative_path(
            manifest_relative_path,
            "run-manifest",
        )
        input_records = verify_input_artifacts(inputs)
        output_records = tuple(sorted(outputs, key=lambda record: record.identifier))
        self._verify_declared_outputs(output_records, manifest_path)
        if {record.identifier for record in input_records}.intersection(
            record.identifier for record in output_records
        ):
            raise ArtifactIntegrityError("input and output identifiers must be disjoint")

        manifest_body: dict[str, JsonValue] = {
            "schemaVersion": RUN_MANIFEST_SCHEMA,
            "inputs": [_record_to_json(record) for record in input_records],
            "outputs": [_record_to_json(record) for record in output_records],
        }
        payload_sha256 = hashlib.sha256(
            canonical_json_bytes(manifest_body)
        ).hexdigest()
        manifest: dict[str, JsonValue] = {
            **manifest_body,
            "manifestPayloadSha256": payload_sha256,
        }
        target = self._resolve_output_path(manifest_path, "run-manifest")
        atomic_write_json(target, manifest)
        return self._record_output("run-manifest", manifest_path)

    def verify_run_manifest(
        self,
        *,
        input_bindings: Mapping[str, Path],
        manifest_relative_path: str = "run-manifest.json",
    ) -> VerificationReport:
        normalized_path = _require_safe_relative_path(
            manifest_relative_path,
            "run-manifest",
        )
        manifest_path = self._resolve_output_path(normalized_path, "run-manifest")
        try:
            source = manifest_path.read_bytes()
        except OSError as error:
            raise ArtifactIntegrityError(f"cannot read run-manifest: {error}") from error
        manifest_value = _load_strict_json_bytes(source, "run-manifest")
        if canonical_json_bytes(manifest_value) != source:
            raise ArtifactIntegrityError("run-manifest is not canonical JSON")
        if not isinstance(manifest_value, dict):
            raise ArtifactIntegrityError("run-manifest must be a JSON object")

        payload_sha256 = _verify_manifest_payload_hash(manifest_value)
        if set(manifest_value) != {
            "schemaVersion",
            "inputs",
            "outputs",
            "manifestPayloadSha256",
        }:
            raise ArtifactIntegrityError("run-manifest has unexpected fields")
        if manifest_value.get("schemaVersion") != RUN_MANIFEST_SCHEMA:
            raise ArtifactIntegrityError("unsupported run-manifest schemaVersion")
        input_records = _read_manifest_records(manifest_value.get("inputs"), "input")
        output_records = _read_manifest_records(manifest_value.get("outputs"), "output")
        if {record.identifier for record in input_records}.intersection(
            record.identifier for record in output_records
        ):
            raise ArtifactIntegrityError("input and output identifiers must be disjoint")
        _verify_input_bindings(input_records, input_bindings)
        self._verify_declared_outputs(output_records, normalized_path)
        return VerificationReport(
            manifest_sha256=hashlib.sha256(source).hexdigest(),
            manifest_payload_sha256=payload_sha256,
            input_count=len(input_records),
            output_count=len(output_records),
        )

    def _verify_declared_outputs(
        self,
        records: tuple[ArtifactRecord, ...],
        manifest_path: str,
    ) -> None:
        _validate_records(records, role="output")
        for record in records:
            if record.manifest_path == manifest_path:
                raise ArtifactIntegrityError("run-manifest cannot list itself as an output")
            current = self._record_output(record.identifier, record.manifest_path)
            if current != record:
                raise ArtifactIntegrityError(
                    f"SHA-256 or size mismatch for output {record.identifier}"
                )

    def _record_output(self, identifier: str, relative_path: str) -> ArtifactRecord:
        target = self._resolve_output_path(relative_path, identifier)
        try:
            size_bytes = target.stat().st_size
            digest = sha256_file(target)
        except OSError as error:
            raise ArtifactIntegrityError(
                f"cannot read output {identifier}: {error}"
            ) from error
        return ArtifactRecord(
            identifier=identifier,
            manifest_path=relative_path,
            sha256=digest,
            size_bytes=size_bytes,
        )

    def _resolve_output_path(self, relative_path: str, identifier: str) -> Path:
        parts = PurePosixPath(relative_path).parts
        target = (self._root_directory / Path(*parts)).resolve()
        if not target.is_relative_to(self._root_directory):
            raise ArtifactIntegrityError(
                f"{identifier} must use a safe relative path within the run directory"
            )
        return target


def canonical_json_bytes(value: JsonValue) -> bytes:
    """Serialize a strict JSON value using the research canonicalization contract."""
    _validate_json_value(value, location="$")
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def atomic_write_json(target: Path, value: JsonValue) -> None:
    payload = canonical_json_bytes(value)
    _atomic_write_bytes(target, payload)


def sha256_file(file_path: Path) -> str:
    digest = hashlib.sha256()
    with file_path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_input_artifacts(
    artifacts: Iterable[InputArtifact],
) -> tuple[ArtifactRecord, ...]:
    ordered = tuple(sorted(artifacts, key=lambda artifact: artifact.identifier))
    _validate_input_declarations(ordered)
    return tuple(_verify_input_artifact(artifact) for artifact in ordered)


def resolve_and_verify_research_inputs(
    *,
    preregistration: InputArtifact,
    trial_ledger: InputArtifact,
    data_manifest: InputArtifact,
) -> tuple[InputArtifact, ...]:
    primary_inputs = (preregistration, trial_ledger, data_manifest)
    verify_input_artifacts(primary_inputs)
    archive_manifest = _load_strict_json(data_manifest.path, data_manifest.identifier)
    raw_inputs = _read_raw_input_declarations(data_manifest, archive_manifest)
    resolved = tuple(
        sorted((*primary_inputs, *raw_inputs), key=lambda artifact: artifact.identifier)
    )
    verify_input_artifacts(resolved)
    return resolved


def _validate_input_declarations(artifacts: tuple[InputArtifact, ...]) -> None:
    identifiers: set[str] = set()
    manifest_paths: set[str] = set()
    for artifact in artifacts:
        if not isinstance(artifact.identifier, str) or (
            not artifact.identifier or artifact.identifier.strip() != artifact.identifier
        ):
            raise ArtifactIntegrityError("input artifact identifier must be non-empty")
        if artifact.identifier in identifiers:
            raise ArtifactIntegrityError(
                f"duplicate input artifact identifier: {artifact.identifier}"
            )
        if not isinstance(artifact.path, Path):
            raise ArtifactIntegrityError(
                f"input path for {artifact.identifier} must be pathlib.Path"
            )
        _require_sha256(artifact.expected_sha256, artifact.identifier)
        normalized_path = _require_safe_relative_path(
            artifact.manifest_path,
            artifact.identifier,
        )
        if normalized_path in manifest_paths:
            raise ArtifactIntegrityError(
                f"duplicate input manifest path: {normalized_path}"
            )
        identifiers.add(artifact.identifier)
        manifest_paths.add(normalized_path)


def _verify_input_artifact(artifact: InputArtifact) -> ArtifactRecord:
    try:
        size_bytes = artifact.path.stat().st_size
        actual_sha256 = sha256_file(artifact.path)
    except OSError as error:
        raise ArtifactIntegrityError(
            f"cannot read input {artifact.identifier}: {error}"
        ) from error
    if actual_sha256 != artifact.expected_sha256:
        raise ArtifactIntegrityError(
            f"SHA-256 mismatch for input {artifact.identifier}: "
            f"expected {artifact.expected_sha256}, got {actual_sha256}"
        )
    return ArtifactRecord(
        identifier=artifact.identifier,
        manifest_path=artifact.manifest_path,
        sha256=actual_sha256,
        size_bytes=size_bytes,
    )


def _read_raw_input_declarations(
    data_manifest: InputArtifact,
    manifest_value: JsonValue,
) -> tuple[InputArtifact, ...]:
    if not isinstance(manifest_value, dict):
        raise ArtifactIntegrityError("data-manifest must be a JSON object")
    archives = manifest_value.get("archives")
    if not isinstance(archives, list):
        raise ArtifactIntegrityError("data-manifest.archives must be an array")

    manifest_directory = data_manifest.path.parent.resolve()
    portable_directory = PurePosixPath(data_manifest.manifest_path).parent
    raw_inputs: list[InputArtifact] = []
    for index, archive in enumerate(archives):
        if not isinstance(archive, dict):
            raise ArtifactIntegrityError(
                f"data-manifest archive {index} must be an object"
            )
        symbol = archive.get("symbol")
        raw_file = archive.get("rawFile")
        raw_sha256 = archive.get("rawFileSha256")
        if not isinstance(symbol, str) or not symbol or symbol.strip() != symbol:
            raise ArtifactIntegrityError(
                f"data-manifest archive {index} has an invalid symbol"
            )
        if not isinstance(raw_file, str):
            raise ArtifactIntegrityError(
                f"data-manifest archive {symbol} has an invalid rawFile"
            )
        portable_raw_file = _require_safe_relative_path(raw_file, f"raw:{symbol}")
        _require_sha256(raw_sha256, f"raw:{symbol}")
        raw_path = (manifest_directory / Path(*PurePosixPath(portable_raw_file).parts)).resolve()
        if not raw_path.is_relative_to(manifest_directory):
            raise ArtifactIntegrityError(
                f"raw:{symbol} must use a safe relative path within the data directory"
            )
        raw_inputs.append(
            InputArtifact(
                identifier=f"raw:{symbol}",
                path=raw_path,
                expected_sha256=raw_sha256,
                manifest_path=(portable_directory / PurePosixPath(portable_raw_file)).as_posix(),
            )
        )
    return tuple(raw_inputs)


def _load_strict_json(file_path: Path, identifier: str) -> JsonValue:
    try:
        source = file_path.read_bytes()
    except OSError as error:
        raise ArtifactIntegrityError(
            f"{identifier} is not strict JSON: {error}"
        ) from error
    return _load_strict_json_bytes(source, identifier)


def _load_strict_json_bytes(source: bytes, identifier: str) -> JsonValue:
    try:
        parsed = json.loads(
            source.decode("utf-8"),
            object_pairs_hook=_object_from_pairs,
            parse_constant=_reject_json_constant,
        )
        _validate_json_value(parsed, location="$")
    except (UnicodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise ArtifactIntegrityError(
            f"{identifier} is not strict JSON: {error}"
        ) from error
    return cast(JsonValue, parsed)


def _verify_manifest_payload_hash(manifest: dict[str, JsonValue]) -> str:
    declared_sha256 = _require_sha256(
        manifest.get("manifestPayloadSha256"),
        "run-manifest manifestPayloadSha256",
    )
    body = {
        key: value
        for key, value in manifest.items()
        if key != "manifestPayloadSha256"
    }
    actual_sha256 = hashlib.sha256(canonical_json_bytes(body)).hexdigest()
    if actual_sha256 != declared_sha256:
        raise ArtifactIntegrityError(
            "manifest payload SHA-256 mismatch: "
            f"expected {declared_sha256}, got {actual_sha256}"
        )
    return actual_sha256


def _record_to_json(record: ArtifactRecord) -> dict[str, JsonValue]:
    return {
        "id": record.identifier,
        "path": record.manifest_path,
        "sha256": record.sha256,
        "sizeBytes": record.size_bytes,
    }


def _read_manifest_records(value: JsonValue | None, role: str) -> tuple[ArtifactRecord, ...]:
    if not isinstance(value, list):
        raise ArtifactIntegrityError(f"run-manifest {role}s must be an array")
    records: list[ArtifactRecord] = []
    for index, entry in enumerate(value):
        if not isinstance(entry, dict) or set(entry) != {
            "id",
            "path",
            "sha256",
            "sizeBytes",
        }:
            raise ArtifactIntegrityError(
                f"run-manifest {role} record {index} is malformed"
            )
        identifier = entry.get("id")
        manifest_path = entry.get("path")
        size_bytes = entry.get("sizeBytes")
        if not isinstance(identifier, str):
            raise ArtifactIntegrityError(
                f"run-manifest {role} record {index} has an invalid id"
            )
        _require_identifier(identifier, role=role)
        normalized_path = _require_safe_relative_path(manifest_path, identifier)
        digest = _require_sha256(entry.get("sha256"), identifier)
        if (
            not isinstance(size_bytes, int)
            or isinstance(size_bytes, bool)
            or size_bytes < 0
        ):
            raise ArtifactIntegrityError(
                f"run-manifest {role} {identifier} has an invalid sizeBytes"
            )
        records.append(
            ArtifactRecord(
                identifier=identifier,
                manifest_path=normalized_path,
                sha256=digest,
                size_bytes=size_bytes,
            )
        )
    result = tuple(records)
    _validate_records(result, role=role)
    if [record.identifier for record in result] != sorted(
        record.identifier for record in result
    ):
        raise ArtifactIntegrityError(
            f"run-manifest {role} records must be code-point sorted by id"
        )
    return result


def _validate_records(records: tuple[ArtifactRecord, ...], role: str) -> None:
    identifiers: set[str] = set()
    paths: set[str] = set()
    for record in records:
        _require_identifier(record.identifier, role=role)
        normalized_path = _require_safe_relative_path(
            record.manifest_path,
            record.identifier,
        )
        _require_sha256(record.sha256, record.identifier)
        if (
            not isinstance(record.size_bytes, int)
            or isinstance(record.size_bytes, bool)
            or record.size_bytes < 0
        ):
            raise ArtifactIntegrityError(
                f"{role} {record.identifier} has an invalid size"
            )
        if record.identifier in identifiers:
            raise ArtifactIntegrityError(
                f"duplicate {role} artifact identifier: {record.identifier}"
            )
        if normalized_path in paths:
            raise ArtifactIntegrityError(
                f"duplicate {role} artifact path: {normalized_path}"
            )
        identifiers.add(record.identifier)
        paths.add(normalized_path)


def _verify_input_bindings(
    records: tuple[ArtifactRecord, ...],
    input_bindings: Mapping[str, Path],
) -> None:
    expected_identifiers = {record.identifier for record in records}
    if set(input_bindings) != expected_identifiers:
        raise ArtifactIntegrityError(
            "input bindings must exactly match run-manifest input identifiers"
        )
    for record in records:
        file_path = input_bindings[record.identifier]
        if not isinstance(file_path, Path):
            raise ArtifactIntegrityError(
                f"input binding for {record.identifier} must be pathlib.Path"
            )
        try:
            size_bytes = file_path.stat().st_size
            digest = sha256_file(file_path)
        except OSError as error:
            raise ArtifactIntegrityError(
                f"cannot read input {record.identifier}: {error}"
            ) from error
        if size_bytes != record.size_bytes or digest != record.sha256:
            raise ArtifactIntegrityError(
                f"SHA-256 or size mismatch for input {record.identifier}"
            )


def _require_identifier(value: object, role: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ArtifactIntegrityError(f"{role} artifact identifier must be non-empty")
    return value


def _object_from_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"non-finite JSON number: {value}")


def _require_sha256(value: object, identifier: str) -> str:
    if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
        raise ArtifactIntegrityError(
            f"{identifier} must declare a lowercase hexadecimal SHA-256"
        )
    return value


def _require_safe_relative_path(value: object, identifier: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ArtifactIntegrityError(
            f"{identifier} must use a safe relative path"
        )
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in value.split("/")):
        raise ArtifactIntegrityError(
            f"{identifier} must use a safe relative path"
        )
    return path.as_posix()


def _atomic_write_bytes(target: Path, payload: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as temporary_file:
            temporary_file.write(payload)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, target)
        _sync_directory(target.parent)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def _sync_directory(directory: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(directory, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _validate_json_value(value: object, location: str) -> None:
    if value is None or isinstance(value, (bool, int, str)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"non-finite number at {location}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_value(item, f"{location}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"JSON object key at {location} must be a string")
            _validate_json_value(item, f"{location}.{key}")
        return
    raise TypeError(f"unsupported JSON value at {location}: {type(value).__name__}")
