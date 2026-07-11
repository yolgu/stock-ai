from __future__ import annotations

import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType

from rp001.local_evidence import canonical_json_bytes, sha256_bytes
from rp001.program_completion import ProgramCompletionError


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
FINALIZE_PROGRAM_PATH = REPOSITORY_ROOT / "research/rp-001/finalize_program.py"
SOURCE_DIRECTORY = REPOSITORY_ROOT / "research/rp-001/src"


def _load_cli_module() -> ModuleType:
    specification = importlib.util.spec_from_file_location(
        "rp001_finalize_program_cli_test_target",
        FINALIZE_PROGRAM_PATH,
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("failed to load finalize_program.py")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


CLI = _load_cli_module()


class _Summary:
    def __init__(self, value: Mapping[str, object]) -> None:
        self._value = dict(value)

    def to_canonical_dict(self) -> dict[str, object]:
        return dict(self._value)


class _RecordingCompletionService:
    def __init__(self, summary: _Summary) -> None:
        self.summary = summary
        self.finalized_at: list[str] = []
        self.verify_count = 0

    def finalize(self, completed_at: str) -> _Summary:
        self.finalized_at.append(completed_at)
        return self.summary

    def verify(self) -> _Summary:
        self.verify_count += 1
        return self.summary


class _RecordingServiceFactory:
    def __init__(self, service: _RecordingCompletionService) -> None:
        self.service = service
        self.repository_roots: list[Path] = []

    def __call__(self, repository_root: Path) -> _RecordingCompletionService:
        self.repository_roots.append(repository_root)
        return self.service


class _UnexpectedFailureService(_RecordingCompletionService):
    def finalize(self, completed_at: str) -> _Summary:
        del completed_at
        raise RuntimeError("SyntheticCliSecret_123456789")


class _CodedCompletionFailure(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__("SyntheticCliSecret_123456789")


class _CodedFailureService(_RecordingCompletionService):
    def verify(self) -> _Summary:
        raise ProgramCompletionError(
            "PUBLICATION_NOT_FOUND",
            "SyntheticCliSecret_123456789",
        )


class _UnknownCodedFailureService(_RecordingCompletionService):
    def verify(self) -> _Summary:
        raise _CodedCompletionFailure("NOT_A_PUBLIC_COMPLETION_CODE")


class _UnsafeProgramCompletionFailureService(_RecordingCompletionService):
    def verify(self) -> _Summary:
        failure = ProgramCompletionError(
            "PUBLICATION_NOT_FOUND",
            "completion publication is unavailable",
        )
        failure.code = "PUBLICATION_NOT_FOUND\nSyntheticCliSecret_123456789"
        raise failure


class FinalizeProgramCliBoundaryTest(unittest.TestCase):
    def test_finalize_emits_canonical_service_summary(self) -> None:
        completed_at = "2026-07-11T04:00:00Z"
        repository_root = Path("/tmp/rp001-cli-fixture")
        service = _RecordingCompletionService(
            _Summary(
                {
                    "decision": "no_adoptable_formula",
                    "artifactCount": 5,
                    "completionId": "PC-001",
                }
            )
        )
        factory = _RecordingServiceFactory(service)
        stdout = io.StringIO()
        stderr = io.StringIO()

        return_code = CLI.main(
            [
                "--finalize",
                "--completed-at",
                completed_at,
                "--repository-root",
                str(repository_root),
            ],
            service_factory=factory,
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(0, return_code)
        self.assertEqual(
            '{"artifactCount":5,"completionId":"PC-001",'
            '"decision":"no_adoptable_formula"}\n',
            stdout.getvalue(),
        )
        self.assertEqual("", stderr.getvalue())
        self.assertEqual([completed_at], service.finalized_at)
        self.assertEqual([repository_root], factory.repository_roots)

    def test_verify_uses_default_repository_root_and_emits_canonical_summary(
        self,
    ) -> None:
        service = _RecordingCompletionService(
            _Summary(
                {
                    "artifactCount": 5,
                    "completionId": "PC-001",
                    "decisionId": "DR-002",
                }
            )
        )
        factory = _RecordingServiceFactory(service)
        stdout = io.StringIO()
        stderr = io.StringIO()

        return_code = CLI.main(
            ["--verify"],
            service_factory=factory,
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(0, return_code)
        self.assertEqual(
            '{"artifactCount":5,"completionId":"PC-001",'
            '"decisionId":"DR-002"}\n',
            stdout.getvalue(),
        )
        self.assertEqual("", stderr.getvalue())
        self.assertEqual(1, service.verify_count)
        self.assertEqual([], service.finalized_at)
        self.assertEqual([REPOSITORY_ROOT], factory.repository_roots)

    def test_unexpected_failure_is_reduced_to_stable_internal_code(self) -> None:
        service = _UnexpectedFailureService(_Summary({"unused": True}))
        factory = _RecordingServiceFactory(service)
        stdout = io.StringIO()
        stderr = io.StringIO()

        return_code = CLI.main(
            ["--finalize", "--completed-at", "2026-07-11T04:00:00Z"],
            service_factory=factory,
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(1, return_code)
        self.assertEqual("", stdout.getvalue())
        self.assertEqual(
            "INVALID INTERNAL_COMPLETION_ERROR\n",
            stderr.getvalue(),
        )
        self.assertNotIn("SyntheticCliSecret_123456789", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_completion_failure_preserves_only_its_stable_code(self) -> None:
        service = _CodedFailureService(_Summary({"unused": True}))
        factory = _RecordingServiceFactory(service)
        stdout = io.StringIO()
        stderr = io.StringIO()

        return_code = CLI.main(
            ["--verify"],
            service_factory=factory,
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(1, return_code)
        self.assertEqual("", stdout.getvalue())
        self.assertEqual("INVALID PUBLICATION_NOT_FOUND\n", stderr.getvalue())
        self.assertNotIn("SyntheticCliSecret_123456789", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_unknown_exception_code_is_not_exposed(self) -> None:
        service = _UnknownCodedFailureService(_Summary({"unused": True}))
        factory = _RecordingServiceFactory(service)
        stdout = io.StringIO()
        stderr = io.StringIO()

        return_code = CLI.main(
            ["--verify"],
            service_factory=factory,
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(1, return_code)
        self.assertEqual("", stdout.getvalue())
        self.assertEqual(
            "INVALID INTERNAL_COMPLETION_ERROR\n",
            stderr.getvalue(),
        )
        self.assertNotIn("NOT_A_PUBLIC_COMPLETION_CODE", stderr.getvalue())

    def test_unregistered_program_completion_code_is_not_exposed(self) -> None:
        service = _UnsafeProgramCompletionFailureService(
            _Summary({"unused": True})
        )
        factory = _RecordingServiceFactory(service)
        stdout = io.StringIO()
        stderr = io.StringIO()

        return_code = CLI.main(
            ["--verify"],
            service_factory=factory,
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(1, return_code)
        self.assertEqual("", stdout.getvalue())
        self.assertEqual(
            "INVALID INTERNAL_COMPLETION_ERROR\n",
            stderr.getvalue(),
        )
        self.assertNotIn("SyntheticCliSecret_123456789", stderr.getvalue())

    def test_mode_and_completed_at_combinations_are_exact(self) -> None:
        invalid_argument_sets = (
            (),
            ("--finalize",),
            ("--verify", "--completed-at", "2026-07-11T04:00:00Z"),
            (
                "--finalize",
                "--verify",
                "--completed-at",
                "2026-07-11T04:00:00Z",
            ),
        )

        for arguments in invalid_argument_sets:
            with self.subTest(arguments=arguments):
                service = _RecordingCompletionService(_Summary({"unused": True}))
                factory = _RecordingServiceFactory(service)
                stdout = io.StringIO()
                stderr = io.StringIO()

                return_code = CLI.main(
                    arguments,
                    service_factory=factory,
                    stdout=stdout,
                    stderr=stderr,
                )

                self.assertEqual(1, return_code)
                self.assertEqual("", stdout.getvalue())
                self.assertEqual("INVALID INVALID_ARGUMENTS\n", stderr.getvalue())
                self.assertEqual([], factory.repository_roots)

    def test_invalid_arguments_are_sanitized_without_traceback(self) -> None:
        synthetic_secret = "SyntheticCliSecret_123456789"
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(SOURCE_DIRECTORY)

        result = subprocess.run(
            [
                sys.executable,
                str(FINALIZE_PROGRAM_PATH),
                "--unknown-option",
                synthetic_secret,
            ],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )

        self.assertEqual(1, result.returncode)
        self.assertEqual("", result.stdout)
        self.assertEqual("INVALID INVALID_ARGUMENTS\n", result.stderr)
        self.assertNotIn(synthetic_secret, result.stderr)
        self.assertNotIn("Traceback", result.stderr)


class FinalizeProgramCliIntegrationTest(unittest.TestCase):
    completed_at = "2026-07-11T04:00:00Z"

    def test_symlink_repository_root_is_rejected_without_publication(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temporary_root = Path(directory).resolve()
            repository_root = self._copy_repository_fixture(temporary_root)
            repository_alias = temporary_root / "repository-alias"
            repository_alias.symlink_to(
                repository_root,
                target_is_directory=True,
            )

            result = self._run_cli(
                repository_alias,
                "--finalize",
                "--completed-at",
                self.completed_at,
            )

            self.assertEqual(1, result.returncode)
            self.assertEqual("", result.stdout)
            self.assertEqual("INVALID UNSAFE_PUBLICATION_PATH\n", result.stderr)
            self.assertFalse(
                (
                    repository_root
                    / "research/rp-001/final/"
                    "PC-001-program-completion.json"
                ).exists()
            )
            self.assertFalse(
                (
                    repository_root
                    / "research/rp-001/local-ledgers/"
                    "interim-program/events/000019.json"
                ).exists()
            )

    def test_finalize_then_verify_is_canonical_and_verify_is_read_only(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository_root = self._copy_repository_fixture(Path(directory))

            for invalid_value in (
                "not-an-iso-timestamp",
                "2026-99-99T99:99:99Z",
            ):
                with self.subTest(invalid_value=invalid_value):
                    before_invalid_timestamp = self._file_snapshot(repository_root)
                    invalid_timestamp = self._run_cli(
                        repository_root,
                        "--finalize",
                        "--completed-at",
                        invalid_value,
                    )
                    after_invalid_timestamp = self._file_snapshot(repository_root)
                    self.assertEqual(1, invalid_timestamp.returncode)
                    self.assertEqual("", invalid_timestamp.stdout)
                    self.assertEqual(
                        "INVALID INVALID_COMPLETION_TIMESTAMP\n",
                        invalid_timestamp.stderr,
                    )
                    self.assertEqual(
                        before_invalid_timestamp,
                        after_invalid_timestamp,
                    )

            absent = self._run_cli(repository_root, "--verify")
            self.assertEqual(1, absent.returncode)
            self.assertEqual("", absent.stdout)
            self.assertEqual("INVALID PUBLICATION_NOT_FOUND\n", absent.stderr)

            finalized = self._run_cli(
                repository_root,
                "--finalize",
                "--completed-at",
                self.completed_at,
            )
            self.assertEqual(0, finalized.returncode, finalized.stderr)
            self.assertEqual("", finalized.stderr)
            finalized_summary = self._canonical_stdout(finalized.stdout)
            self.assertEqual("finalized", finalized_summary["mode"])
            self.assertEqual(5, finalized_summary["artifactCount"])
            self.assertEqual(
                [
                    "research/rp-001/final/"
                    "EB-002-program-terminal-evidence.json",
                    "research/rp-001/final/completion-traceability.json",
                    "research/rp-001/final/"
                    "DR-002-no-adoptable-formula.json",
                    "research/rp-001/reports/"
                    "RP001-20260711-final-research-report.md",
                    "research/rp-001/final/PC-001-program-completion.json",
                ],
                finalized_summary["artifactPaths"],
            )
            self.assertEqual(
                "research/rp-001/local-ledgers/interim-program/events/000019.json",
                finalized_summary["ledgerEventPath"],
            )

            before_verify = self._file_snapshot(repository_root)
            verified = self._run_cli(repository_root, "--verify")
            after_verify = self._file_snapshot(repository_root)

            self.assertEqual(0, verified.returncode, verified.stderr)
            self.assertEqual("", verified.stderr)
            verified_summary = self._canonical_stdout(verified.stdout)
            self.assertEqual("verified", verified_summary["mode"])
            self.assertEqual(
                {
                    key: value
                    for key, value in finalized_summary.items()
                    if key != "mode"
                },
                {
                    key: value
                    for key, value in verified_summary.items()
                    if key != "mode"
                },
            )
            self.assertEqual(before_verify, after_verify)

    def test_verify_reports_body_sidecar_and_ledger_tampering(self) -> None:
        cases = (
            (
                Path(
                    "research/rp-001/final/"
                    "EB-002-program-terminal-evidence.json"
                ),
                b"\n",
                "PUBLICATION_DRIFT",
            ),
            (
                Path(
                    "research/rp-001/final/"
                    "EB-002-program-terminal-evidence.json.sha256"
                ),
                b"0" * 64 + b"\n",
                "PUBLICATION_DRIFT",
            ),
            (
                Path(
                    "research/rp-001/local-ledgers/interim-program/"
                    "events/000019.json"
                ),
                b"\n",
                "LEDGER_BINDING_INVALID",
            ),
        )

        for relative_path, suffix, expected_code in cases:
            with self.subTest(relative_path=relative_path):
                with tempfile.TemporaryDirectory() as directory:
                    repository_root = self._copy_repository_fixture(
                        Path(directory)
                    )
                    finalized = self._run_cli(
                        repository_root,
                        "--finalize",
                        "--completed-at",
                        self.completed_at,
                    )
                    self.assertEqual(0, finalized.returncode, finalized.stderr)
                    tampered_path = repository_root / relative_path
                    tampered_path.write_bytes(tampered_path.read_bytes() + suffix)

                    before_verify = self._file_snapshot(repository_root)
                    verified = self._run_cli(repository_root, "--verify")
                    after_verify = self._file_snapshot(repository_root)

                    self.assertEqual(1, verified.returncode)
                    self.assertEqual("", verified.stdout)
                    self.assertEqual(
                        f"INVALID {expected_code}\n",
                        verified.stderr,
                    )
                    self.assertNotIn("Traceback", verified.stderr)
                    self.assertEqual(before_verify, after_verify)

    def test_verify_rejects_self_consistent_final_artifact_rehash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository_root = self._copy_repository_fixture(Path(directory))
            finalized = self._run_cli(
                repository_root,
                "--finalize",
                "--completed-at",
                self.completed_at,
            )
            self.assertEqual(0, finalized.returncode, finalized.stderr)
            body_path = (
                repository_root
                / "research/rp-001/final/PC-001-program-completion.json"
            )
            tampered_source = body_path.read_bytes() + b"\n"
            body_path.write_bytes(tampered_source)
            Path(f"{body_path}.sha256").write_bytes(
                f"{sha256_bytes(tampered_source)}\n".encode("ascii")
            )

            before_verify = self._file_snapshot(repository_root)
            verified = self._run_cli(repository_root, "--verify")
            after_verify = self._file_snapshot(repository_root)

            self.assertEqual(1, verified.returncode)
            self.assertEqual("", verified.stdout)
            self.assertEqual("INVALID PUBLICATION_DRIFT\n", verified.stderr)
            self.assertEqual(before_verify, after_verify)

    def test_verify_rejects_self_consistent_immutable_input_rehash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository_root = self._copy_repository_fixture(Path(directory))
            finalized = self._run_cli(
                repository_root,
                "--finalize",
                "--completed-at",
                self.completed_at,
            )
            self.assertEqual(0, finalized.returncode, finalized.stderr)
            body_path = (
                repository_root
                / "research/rp-001/contracts/goal-lineage-v1.2.json"
            )
            tampered_source = body_path.read_bytes() + b"\n"
            body_path.write_bytes(tampered_source)
            Path(f"{body_path}.sha256").write_bytes(
                f"{sha256_bytes(tampered_source)}\n".encode("ascii")
            )

            before_verify = self._file_snapshot(repository_root)
            verified = self._run_cli(repository_root, "--verify")
            after_verify = self._file_snapshot(repository_root)

            self.assertEqual(1, verified.returncode)
            self.assertEqual("", verified.stdout)
            self.assertEqual("INVALID IMMUTABLE_HASH_MISMATCH\n", verified.stderr)
            self.assertEqual(before_verify, after_verify)

    def test_verify_rejects_self_consistent_ledger_binding_tamper(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository_root = self._copy_repository_fixture(Path(directory))
            finalized = self._run_cli(
                repository_root,
                "--finalize",
                "--completed-at",
                self.completed_at,
            )
            self.assertEqual(0, finalized.returncode, finalized.stderr)
            body_path = (
                repository_root
                / "research/rp-001/local-ledgers/interim-program/"
                "events/000019.json"
            )
            event = json.loads(body_path.read_text(encoding="utf-8"))
            event["payload"]["artifactBindings"][0]["sha256"] = "0" * 64
            tampered_source = canonical_json_bytes(event)
            body_path.write_bytes(tampered_source)
            Path(f"{body_path}.sha256").write_bytes(
                f"{sha256_bytes(tampered_source)}\n".encode("ascii")
            )

            before_verify = self._file_snapshot(repository_root)
            verified = self._run_cli(repository_root, "--verify")
            after_verify = self._file_snapshot(repository_root)

            self.assertEqual(1, verified.returncode)
            self.assertEqual("", verified.stdout)
            self.assertEqual("INVALID LEDGER_BINDING_INVALID\n", verified.stderr)
            self.assertEqual(before_verify, after_verify)

    def test_verify_does_not_write_python_bytecode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temporary_root = Path(directory)
            repository_root = self._copy_repository_fixture(temporary_root)
            finalized = self._run_cli(
                repository_root,
                "--finalize",
                "--completed-at",
                self.completed_at,
            )
            self.assertEqual(0, finalized.returncode, finalized.stderr)
            isolated_source_directory = temporary_root / "python-source"
            shutil.copytree(
                SOURCE_DIRECTORY,
                isolated_source_directory,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
            before_verify = self._file_snapshot(isolated_source_directory)

            verified = self._run_cli(
                repository_root,
                "--verify",
                source_directory=isolated_source_directory,
            )
            after_verify = self._file_snapshot(isolated_source_directory)

            self.assertEqual(0, verified.returncode, verified.stderr)
            self.assertEqual(before_verify, after_verify)

    @staticmethod
    def _copy_repository_fixture(temporary_root: Path) -> Path:
        repository_root = temporary_root / "repository"
        research_root = repository_root / "research"
        research_root.mkdir(parents=True)
        for directory_name in ("meta-research", "rp-001"):
            shutil.copytree(
                REPOSITORY_ROOT / "research" / directory_name,
                research_root / directory_name,
            )
        final_directory = research_root / "rp-001/final"
        if final_directory.exists():
            shutil.rmtree(final_directory)
        final_report_path = (
            research_root
            / "rp-001/reports/RP001-20260711-final-research-report.md"
        )
        final_report_path.unlink(missing_ok=True)
        Path(f"{final_report_path}.sha256").unlink(missing_ok=True)
        events_directory = (
            research_root / "rp-001/local-ledgers/interim-program/events"
        )
        for path in events_directory.glob("*.json*"):
            sequence_text = path.name[:6]
            if sequence_text.isdigit() and int(sequence_text) >= 19:
                path.unlink()
        return repository_root.resolve()

    @staticmethod
    def _run_cli(
        repository_root: Path,
        *arguments: str,
        source_directory: Path = SOURCE_DIRECTORY,
    ) -> subprocess.CompletedProcess[str]:
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(source_directory)
        return subprocess.run(
            [
                sys.executable,
                str(FINALIZE_PROGRAM_PATH),
                *arguments,
                "--repository-root",
                str(repository_root),
            ],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )

    @staticmethod
    def _canonical_stdout(source: str) -> dict[str, object]:
        value = json.loads(source)
        if not isinstance(value, dict):
            raise AssertionError("CLI summary must be a JSON object")
        expected = canonical_json_bytes(value).decode("utf-8") + "\n"
        if source != expected:
            raise AssertionError("CLI summary is not canonical JSON")
        return value

    @staticmethod
    def _file_snapshot(repository_root: Path) -> dict[str, bytes]:
        return {
            path.relative_to(repository_root).as_posix(): path.read_bytes()
            for path in sorted(repository_root.rglob("*"))
            if path.is_file()
        }


if __name__ == "__main__":
    unittest.main()
