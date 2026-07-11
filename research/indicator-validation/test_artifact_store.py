import hashlib
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


RESEARCH_DIRECTORY = Path(__file__).resolve().parent
sys.path.insert(0, str(RESEARCH_DIRECTORY))

from artifact_store import (  # noqa: E402
    ArtifactStore,
    ArtifactIntegrityError,
    InputArtifact,
    atomic_write_json,
    canonical_json_bytes,
    resolve_and_verify_research_inputs,
    sha256_file,
    verify_input_artifacts,
)


class CanonicalJsonTest(unittest.TestCase):
    def test_sorts_object_keys_by_unicode_code_point_and_preserves_array_order(self) -> None:
        value = {
            "": 4,
            "z": 3,
            "a": {"한": 2, "A": 1},
            "array": [{"b": 2, "a": 1}, "second", "first"],
            "한": 5,
        }

        serialized = canonical_json_bytes(value)

        self.assertEqual(
            serialized,
            '{"a":{"A":1,"한":2},"array":[{"a":1,"b":2},"second","first"],'
            '"z":3,"한":5,"":4}'.encode(),
        )

    def test_rejects_every_non_finite_float(self) -> None:
        for value in (math.nan, math.inf, -math.inf):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    canonical_json_bytes({"invalid": value})


class AtomicJsonWriteTest(unittest.TestCase):
    def test_replaces_target_with_canonical_bytes_and_leaves_no_temporary_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "nested" / "result.json"
            target.parent.mkdir()
            target.write_bytes(b"old content")

            atomic_write_json(target, {"z": 2, "a": [3, 1]})

            self.assertEqual(target.read_bytes(), b'{"a":[3,1],"z":2}')
            self.assertEqual([path.name for path in target.parent.iterdir()], ["result.json"])

    def test_serialization_failure_preserves_the_existing_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "result.json"
            target.write_bytes(b"known-good")

            with self.assertRaises(ValueError):
                atomic_write_json(target, {"score": math.nan})

            self.assertEqual(target.read_bytes(), b"known-good")
            self.assertEqual([path.name for path in target.parent.iterdir()], ["result.json"])

    def test_replace_failure_preserves_the_existing_target_and_cleans_the_temp_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "result.json"
            target.write_bytes(b"known-good")

            with patch("artifact_store.os.replace", side_effect=OSError("replace failed")):
                with self.assertRaisesRegex(OSError, "replace failed"):
                    atomic_write_json(target, {"score": 1})

            self.assertEqual(target.read_bytes(), b"known-good")
            self.assertEqual([path.name for path in target.parent.iterdir()], ["result.json"])


class FileHashTest(unittest.TestCase):
    def test_hashes_the_exact_file_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "fixture.bin"
            target.write_bytes(b"abc")

            digest = sha256_file(target)

        self.assertEqual(
            digest,
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        )


def independent_sha256(file_path: Path) -> str:
    return hashlib.sha256(file_path.read_bytes()).hexdigest()


def write_json_fixture(file_path: Path, value: object) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def create_research_input_fixture(root: Path) -> tuple[InputArtifact, InputArtifact, InputArtifact]:
    preregistration_path = root / "preregistration.json"
    ledger_path = root / "trial-ledger.json"
    data_manifest_path = root / "data" / "manifest.json"
    raw_path = root / "data" / "raw" / "FIXTURE.json"
    write_json_fixture(preregistration_path, {"version": "fixture-1", "rules": [2, 1]})
    write_json_fixture(ledger_path, {"trials": [{"id": "fixture"}]})
    write_json_fixture(raw_path, [{"timestamp": "2026-01-02", "close": "100"}])
    write_json_fixture(
        data_manifest_path,
        {
            "archives": [
                {
                    "symbol": "FIXTURE",
                    "rawFile": "raw/FIXTURE.json",
                    "rawFileSha256": independent_sha256(raw_path),
                }
            ]
        },
    )
    return (
        InputArtifact(
            identifier="preregistration",
            path=preregistration_path,
            expected_sha256=independent_sha256(preregistration_path),
            manifest_path="preregistration.json",
        ),
        InputArtifact(
            identifier="trial-ledger",
            path=ledger_path,
            expected_sha256=independent_sha256(ledger_path),
            manifest_path="trial-ledger.json",
        ),
        InputArtifact(
            identifier="data-manifest",
            path=data_manifest_path,
            expected_sha256=independent_sha256(data_manifest_path),
            manifest_path="data/manifest.json",
        ),
    )


class ResearchInputVerificationTest(unittest.TestCase):
    def test_verifies_preregistration_ledger_data_manifest_and_declared_raw_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            inputs = create_research_input_fixture(Path(directory))

            resolved = resolve_and_verify_research_inputs(
                preregistration=inputs[0],
                trial_ledger=inputs[1],
                data_manifest=inputs[2],
            )
            records = verify_input_artifacts(resolved)

        self.assertEqual(
            [record.identifier for record in records],
            ["data-manifest", "preregistration", "raw:FIXTURE", "trial-ledger"],
        )
        self.assertEqual(
            next(record for record in records if record.identifier == "raw:FIXTURE").manifest_path,
            "data/raw/FIXTURE.json",
        )

    def test_detects_one_byte_mutation_in_each_research_input_role(self) -> None:
        for mutated_identifier in (
            "preregistration",
            "trial-ledger",
            "data-manifest",
            "raw:FIXTURE",
        ):
            with self.subTest(mutated_identifier=mutated_identifier):
                with tempfile.TemporaryDirectory() as directory:
                    inputs = create_research_input_fixture(Path(directory))
                    paths = {
                        "preregistration": inputs[0].path,
                        "trial-ledger": inputs[1].path,
                        "data-manifest": inputs[2].path,
                        "raw:FIXTURE": Path(directory) / "data" / "raw" / "FIXTURE.json",
                    }
                    original = paths[mutated_identifier].read_bytes()
                    paths[mutated_identifier].write_bytes(
                        bytes([original[0] ^ 1]) + original[1:]
                    )

                    with self.assertRaisesRegex(
                        ArtifactIntegrityError,
                        mutated_identifier,
                    ):
                        resolve_and_verify_research_inputs(
                            preregistration=inputs[0],
                            trial_ledger=inputs[1],
                            data_manifest=inputs[2],
                        )

    def test_rejects_a_raw_path_that_escapes_the_data_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = create_research_input_fixture(root)
            escaped_path = root / "escaped.json"
            escaped_path.write_bytes(b"[]")
            write_json_fixture(
                inputs[2].path,
                {
                    "archives": [
                        {
                            "symbol": "ESCAPE",
                            "rawFile": "../escaped.json",
                            "rawFileSha256": independent_sha256(escaped_path),
                        }
                    ]
                },
            )
            mutated_manifest = InputArtifact(
                identifier="data-manifest",
                path=inputs[2].path,
                expected_sha256=independent_sha256(inputs[2].path),
                manifest_path="data/manifest.json",
            )

            with self.assertRaisesRegex(ArtifactIntegrityError, "safe relative path"):
                resolve_and_verify_research_inputs(
                    preregistration=inputs[0],
                    trial_ledger=inputs[1],
                    data_manifest=mutated_manifest,
                )


class RunArtifactManifestTest(unittest.TestCase):
    def test_writes_and_verifies_a_deterministic_self_hashed_run_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = resolve_and_verify_research_inputs(
                preregistration=(fixture_inputs := create_research_input_fixture(root))[0],
                trial_ledger=fixture_inputs[1],
                data_manifest=fixture_inputs[2],
            )
            store = ArtifactStore(root / "run")
            events = store.write_json(
                identifier="events",
                relative_path="events.json",
                value={"events": ["second", "first"]},
            )
            metrics = store.write_json(
                identifier="metrics",
                relative_path="metrics.json",
                value={"z": 2, "a": 1},
            )

            manifest_record = store.write_run_manifest(
                inputs=inputs,
                outputs=(metrics, events),
            )
            manifest_bytes = (root / "run" / "run-manifest.json").read_bytes()
            manifest = json.loads(manifest_bytes)
            payload_sha256 = manifest.pop("manifestPayloadSha256")
            independent_payload = json.dumps(
                manifest,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            report = store.verify_run_manifest(
                input_bindings={artifact.identifier: artifact.path for artifact in inputs}
            )

        self.assertEqual(
            payload_sha256,
            hashlib.sha256(independent_payload).hexdigest(),
        )
        self.assertEqual([entry["id"] for entry in manifest["outputs"]], ["events", "metrics"])
        self.assertEqual([entry["id"] for entry in manifest["inputs"]], sorted(entry["id"] for entry in manifest["inputs"]))
        self.assertEqual(manifest_record.sha256, hashlib.sha256(manifest_bytes).hexdigest())
        self.assertEqual(report.input_count, 4)
        self.assertEqual(report.output_count, 2)
        self.assertEqual(report.manifest_sha256, manifest_record.sha256)

    def test_detects_a_one_byte_output_mutation_after_manifest_creation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture_inputs = create_research_input_fixture(root)
            inputs = resolve_and_verify_research_inputs(
                preregistration=fixture_inputs[0],
                trial_ledger=fixture_inputs[1],
                data_manifest=fixture_inputs[2],
            )
            store = ArtifactStore(root / "run")
            output = store.write_json(
                identifier="metrics",
                relative_path="metrics.json",
                value={"score": 1},
            )
            store.write_run_manifest(inputs=inputs, outputs=(output,))
            output_path = root / "run" / "metrics.json"
            original = output_path.read_bytes()
            mutation_position = original.index(b"1")
            output_path.write_bytes(
                original[:mutation_position] + b"2" + original[mutation_position + 1 :]
            )

            with self.assertRaisesRegex(ArtifactIntegrityError, "output metrics"):
                store.verify_run_manifest(
                    input_bindings={artifact.identifier: artifact.path for artifact in inputs}
                )

    def test_detects_one_byte_mutation_in_every_input_after_manifest_creation(self) -> None:
        for mutated_identifier in (
            "preregistration",
            "trial-ledger",
            "data-manifest",
            "raw:FIXTURE",
        ):
            with self.subTest(mutated_identifier=mutated_identifier):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    fixture_inputs = create_research_input_fixture(root)
                    inputs = resolve_and_verify_research_inputs(
                        preregistration=fixture_inputs[0],
                        trial_ledger=fixture_inputs[1],
                        data_manifest=fixture_inputs[2],
                    )
                    store = ArtifactStore(root / "run")
                    output = store.write_json(
                        identifier="metrics",
                        relative_path="metrics.json",
                        value={"score": 1},
                    )
                    store.write_run_manifest(inputs=inputs, outputs=(output,))
                    mutated_input = next(
                        artifact
                        for artifact in inputs
                        if artifact.identifier == mutated_identifier
                    )
                    original = mutated_input.path.read_bytes()
                    mutated_input.path.write_bytes(
                        bytes([original[0] ^ 1]) + original[1:]
                    )

                    with self.assertRaisesRegex(
                        ArtifactIntegrityError,
                        f"input {mutated_identifier}",
                    ):
                        store.verify_run_manifest(
                            input_bindings={
                                artifact.identifier: artifact.path
                                for artifact in inputs
                            }
                        )

    def test_detects_a_one_byte_manifest_payload_mutation_using_the_self_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture_inputs = create_research_input_fixture(root)
            inputs = resolve_and_verify_research_inputs(
                preregistration=fixture_inputs[0],
                trial_ledger=fixture_inputs[1],
                data_manifest=fixture_inputs[2],
            )
            store = ArtifactStore(root / "run")
            output = store.write_json(
                identifier="metrics",
                relative_path="metrics.json",
                value={"score": 1},
            )
            store.write_run_manifest(inputs=inputs, outputs=(output,))
            manifest_path = root / "run" / "run-manifest.json"
            original = manifest_path.read_bytes()
            marker = b"research-run-artifact-manifest.v1"
            marker_position = original.index(marker)
            manifest_path.write_bytes(
                original[:marker_position]
                + b"s"
                + original[marker_position + 1 :]
            )

            with self.assertRaisesRegex(ArtifactIntegrityError, "manifest payload SHA-256"):
                store.verify_run_manifest(
                    input_bindings={artifact.identifier: artifact.path for artifact in inputs}
                )

    def test_rejects_output_paths_outside_the_run_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = ArtifactStore(root / "run")

            for unsafe_path in (
                "../escape.json",
                str(root / "absolute.json"),
                "nested\\escape.json",
            ):
                with self.subTest(unsafe_path=unsafe_path):
                    with self.assertRaisesRegex(
                        ArtifactIntegrityError,
                        "safe relative path",
                    ):
                        store.write_json(
                            identifier="escape",
                            relative_path=unsafe_path,
                            value={"forbidden": True},
                        )

    def test_rejects_an_output_symlink_that_escapes_the_run_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outside = root / "outside"
            outside.mkdir()
            run_directory = root / "run"
            run_directory.mkdir()
            (run_directory / "linked").symlink_to(outside, target_is_directory=True)
            store = ArtifactStore(run_directory)

            with self.assertRaisesRegex(ArtifactIntegrityError, "within the run directory"):
                store.write_json(
                    identifier="escape",
                    relative_path="linked/escape.json",
                    value={"forbidden": True},
                )


if __name__ == "__main__":
    unittest.main()
