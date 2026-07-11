from __future__ import annotations

import hashlib
import json
import re
import unittest
from pathlib import Path, PurePosixPath
from typing import cast

from rp001.sensitive_value_policy import find_sensitive_values


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_BUNDLE_DIRECTORY = (
    REPOSITORY_ROOT
    / "research/meta-research/objects/evidence-bundles/EB-001-rb001-integrity-audit"
)
DECISION_RECORD_DIRECTORY = (
    REPOSITORY_ROOT
    / "research/meta-research/objects/decision-records/DR-001-rb001-boundary"
)
EVIDENCE_OBJECT_PATH = EVIDENCE_BUNDLE_DIRECTORY / "object.json"
EVIDENCE_PATH = EVIDENCE_BUNDLE_DIRECTORY / "evidence.md"
OBSERVATIONS_PATH = EVIDENCE_BUNDLE_DIRECTORY / "integrity-observations.json"
INPUT_BINDINGS_PATH = EVIDENCE_BUNDLE_DIRECTORY / "current-input-bindings.json"
DECISION_OBJECT_PATH = DECISION_RECORD_DIRECTORY / "object.json"
DECISION_PATH = DECISION_RECORD_DIRECTORY / "decision.md"
BOUNDARY_CONTRACT_PATH = DECISION_RECORD_DIRECTORY / "boundary-contract.json"
RUN_MANIFEST_PATH = (
    REPOSITORY_ROOT / "research/indicator-validation/results/run-manifest.json"
)
BOUND_RUNNER_PATH = (
    REPOSITORY_ROOT / "research/indicator-validation/run_validation.py"
)
EXPECTED_OUTPUT_IDS = (
    "data-quality",
    "events",
    "frozen-calibrators",
    "metrics",
    "predictions",
    "selection",
    "trial-results",
    "verification",
)

EXPECTED_EVIDENCE_DESCRIPTOR: dict[str, object] = {
    "schemaVersion": "research-object.v1",
    "id": "EB-001",
    "type": "EvidenceBundle",
    "title": "RB-001 무결성 관찰 감사",
    "version": "1.0.0",
    "lifecycleState": "completed",
    "evidenceLevel": "exploratory",
    "purpose": (
        "RB-001에서 관찰된 manifest·runner 변이를 append-only 근거로 보존하고 "
        "사용 한계를 고정한다."
    ),
    "dependsOn": ["RB-001"],
    "artifacts": [
        "research/meta-research/objects/evidence-bundles/"
        "EB-001-rb001-integrity-audit/evidence.md",
        "research/meta-research/objects/evidence-bundles/"
        "EB-001-rb001-integrity-audit/integrity-observations.json",
        "research/meta-research/objects/evidence-bundles/"
        "EB-001-rb001-integrity-audit/current-input-bindings.json",
    ],
}
EXPECTED_DECISION_DESCRIPTOR: dict[str, object] = {
    "schemaVersion": "research-object.v1",
    "id": "DR-001",
    "type": "DecisionRecord",
    "title": "RB-001 연구 사용 경계",
    "version": "1.0.0",
    "lifecycleState": "completed",
    "evidenceLevel": "exploratory",
    "purpose": (
        "RB-001의 허용된 연구 용도와 금지된 성능·재현성·운영 주장을 "
        "고정한다."
    ),
    "dependsOn": ["EB-001", "RB-001"],
    "artifacts": [
        "research/meta-research/objects/decision-records/"
        "DR-001-rb001-boundary/decision.md",
        "research/meta-research/objects/decision-records/"
        "DR-001-rb001-boundary/boundary-contract.json",
    ],
}
EXPECTED_BOUNDARY_CONTRACT: dict[str, object] = {
    "schemaVersion": "rb001-research-boundary.v1",
    "decisionId": "DR-001",
    "baselineId": "RB-001",
    "evidenceId": "EB-001",
    "decisionStatus": "research_only",
    "operationalUseAllowed": False,
    "allowedUses": [
        "failure_reproduction_descriptive_defect_evidence",
        "prohibited_condition_design",
        "seen_development_data_boundary_identification",
    ],
    "prohibitedEvidenceRoles": [
        "performance_or_adoption_evidence",
        "independent_reproducibility_or_replicability_evidence",
        "proof_of_frozen_generation_provenance",
    ],
    "gateLimits": {
        "G0": "not_passed",
        "G9": "not_passed",
    },
    "reopenConditions": [
        "new_separately_versioned_baseline",
        "immutable_pre_run_code_and_inputs",
        "witnessed_manifest_generation",
        "same_team_repeat",
        "independent_artifact_reproduction",
        "external_replication_as_applicable",
    ],
}
EXPECTED_INPUT_BINDINGS: dict[str, object] = {
    "schemaVersion": "rb001-current-input-bindings.v1",
    "baselineId": "RB-001",
    "runManifestSha256": (
        "b4ebe5e41c8f8ca536a80fa05bddfe868e1669832555d6c00daffc21c4e0038e"
    ),
    "bindings": [
        {
            "id": "amendment:volume-unit-integrity",
            "manifestPath": "amendments/data-quality-amendment.v1.json",
            "repositoryRelativePath": (
                "research/indicator-validation/data-quality-amendment.v1.json"
            ),
        },
        {
            "id": "artifact:formula-ledger",
            "manifestPath": "analysis/formula-ledger.json",
            "repositoryRelativePath": "research/indicator-validation/formula-ledger.json",
        },
        {
            "id": "audit:formula-equivalence",
            "manifestPath": "audit/formula-ledger-and-equivalence.md",
            "repositoryRelativePath": (
                "docs/codex/research/"
                "2026-07-10-formula-ledger-and-equivalence.md"
            ),
        },
        {
            "id": "audit:formula-mathematics",
            "manifestPath": "audit/formula-mathematical-audit.md",
            "repositoryRelativePath": (
                "docs/codex/research/2026-07-10-formula-mathematical-audit.md"
            ),
        },
        {
            "id": "code:artifact-store",
            "manifestPath": "analysis/artifact_store.py",
            "repositoryRelativePath": "research/indicator-validation/artifact_store.py",
        },
        {
            "id": "code:event-catalog",
            "manifestPath": "analysis/event_catalog.py",
            "repositoryRelativePath": "research/indicator-validation/event_catalog.py",
        },
        {
            "id": "code:formula-ledger",
            "manifestPath": "analysis/formula_ledger.py",
            "repositoryRelativePath": "research/indicator-validation/formula_ledger.py",
        },
        {
            "id": "code:formula-reference",
            "manifestPath": "analysis/formula_reference.py",
            "repositoryRelativePath": (
                "research/indicator-validation/formula_reference.py"
            ),
        },
        {
            "id": "code:research-pipeline",
            "manifestPath": "analysis/research_pipeline.py",
            "repositoryRelativePath": (
                "research/indicator-validation/research_pipeline.py"
            ),
        },
        {
            "id": "code:run-validation",
            "manifestPath": "analysis/run_validation.py",
            "repositoryRelativePath": "research/indicator-validation/run_validation.py",
        },
        {
            "id": "code:study-runner",
            "manifestPath": "analysis/study_runner.py",
            "repositoryRelativePath": "research/indicator-validation/study_runner.py",
        },
        {
            "id": "code:validation",
            "manifestPath": "analysis/validation.py",
            "repositoryRelativePath": "research/indicator-validation/validation.py",
        },
        {
            "id": "data-manifest",
            "manifestPath": "data/manifest.json",
            "repositoryRelativePath": "research/indicator-validation/data/manifest.json",
        },
        {
            "id": "dependency:python-lock",
            "manifestPath": "dependencies/requirements.lock.txt",
            "repositoryRelativePath": (
                "research/indicator-validation/requirements.lock.txt"
            ),
        },
        {
            "id": "formula:fomo",
            "manifestPath": "formula/포모.md",
            "repositoryRelativePath": "docs/codex/지표/포모.md",
        },
        {
            "id": "formula:panic",
            "manifestPath": "formula/패닉.md",
            "repositoryRelativePath": "docs/codex/지표/패닉.md",
        },
        {
            "id": "formula:profit-taking",
            "manifestPath": "formula/차익실현.md",
            "repositoryRelativePath": "docs/codex/지표/차익실현.md",
        },
        {
            "id": "preregistration",
            "manifestPath": "preregistration.json",
            "repositoryRelativePath": "research/indicator-validation/preregistration.json",
        },
        {
            "id": "production:quant-indicators",
            "manifestPath": "production/quant-indicators.cjs",
            "repositoryRelativePath": "extensions/app/quant-indicators.cjs",
        },
        {
            "id": "raw:000660",
            "manifestPath": "data/raw/000660.json",
            "repositoryRelativePath": (
                "research/indicator-validation/data/raw/000660.json"
            ),
        },
        {
            "id": "raw:MU",
            "manifestPath": "data/raw/MU.json",
            "repositoryRelativePath": "research/indicator-validation/data/raw/MU.json",
        },
        {
            "id": "raw:NVDA",
            "manifestPath": "data/raw/NVDA.json",
            "repositoryRelativePath": "research/indicator-validation/data/raw/NVDA.json",
        },
        {
            "id": "raw:TSLA",
            "manifestPath": "data/raw/TSLA.json",
            "repositoryRelativePath": "research/indicator-validation/data/raw/TSLA.json",
        },
        {
            "id": "trial-ledger",
            "manifestPath": "trial-ledger.json",
            "repositoryRelativePath": "research/indicator-validation/trial-ledger.json",
        },
    ],
}
EXPECTED_OBSERVATIONS: dict[str, object] = {
    "schemaVersion": "rb001-integrity-observations.v1",
    "baselineId": "RB-001",
    "observations": [
        {
            "phase": "initial_audit",
            "runManifestSha256": (
                "09e2ddf1e9acb3dbf54336ea5265a737ebba4a702dce61cdd194f4827a260eda"
            ),
            "manifestPayloadSha256": (
                "6874c351cd5efe3f061c05af134ae569c0d0227e225340dd0f85d52b27e59356"
            ),
            "boundRunnerSha256": (
                "1e6d5d4053f61fdb4d3af17848658c8a0942880774c8c7f33d7e5f6f0bd12d2a"
            ),
            "boundRunnerSizeBytes": 42115,
            "verifyStatus": "failed_input_hash_mismatch",
        },
        {
            "phase": "first_rebind_observed",
            "runManifestSha256": (
                "90e6e3ac59bf408b609fc5a5422a763a090e47c5578f9b0419a957814b93415f"
            ),
            "manifestPayloadSha256": (
                "3b4957020bdea2f060eab7e8f2cd784c5a0acc98ef6d57cd83fe3916a5bb0ae2"
            ),
            "boundRunnerSha256": (
                "b625d724d8363b2d5d74a25b698e7911787d01dfcb5b7b5c41c392b3a748851b"
            ),
            "boundRunnerSizeBytes": 50585,
            "verifyStatus": "self_consistent_after_rebind",
        },
        {
            "phase": "later_deterministic_rerun_observed",
            "runManifestSha256": (
                "b4ebe5e41c8f8ca536a80fa05bddfe868e1669832555d6c00daffc21c4e0038e"
            ),
            "manifestPayloadSha256": (
                "b6f3b49372b60c608692a233bd0abba790af58a3604204084d670cd802325b7f"
            ),
            "boundRunnerSha256": (
                "f906fd61b9b55e2e264adae032517151f9ee7ed24b8804ab878e102944736708"
            ),
            "boundRunnerSizeBytes": 52600,
            "verifyStatus": "current_snapshot_self_consistent",
        },
    ],
    "generationLineageVerified": False,
}


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_bytes(source: bytes) -> str:
    return hashlib.sha256(source).hexdigest()


class Rb001BoundaryContractTest(unittest.TestCase):
    def _read_required_bytes(self, path: Path) -> bytes:
        self.assertTrue(
            path.is_file(),
            f"missing RB-001 boundary artifact: {path.relative_to(REPOSITORY_ROOT)}",
        )
        return path.read_bytes()

    def _read_required_text(self, path: Path) -> str:
        return self._read_required_bytes(path).decode("utf-8")

    def _read_required_json_object(self, path: Path) -> dict[str, object]:
        value = json.loads(self._read_required_text(path))
        self.assertIsInstance(value, dict)
        return cast(dict[str, object], value)

    def _literal_bullets(self, document: str, heading: str) -> tuple[str, ...]:
        section = self._section(document, heading)
        bullets: list[str] = []
        for line in section.splitlines():
            if not line.startswith("- "):
                continue
            match = re.fullmatch(r"- `([^`]+)`(?: — .+)?", line)
            self.assertIsNotNone(match, f"non-literal bullet in {heading}: {line}")
            bullets.append(cast(re.Match[str], match).group(1))
        return tuple(bullets)

    def _section(self, document: str, heading: str) -> str:
        marker = f"## {heading}\n"
        self.assertIn(marker, document)
        return document.split(marker, maxsplit=1)[1].split(
            "\n## ",
            maxsplit=1,
        )[0].strip()

    def _safe_portable_path(self, value: object, role: str) -> PurePosixPath:
        self.assertIsInstance(value, str, f"{role} must be a string")
        path_text = cast(str, value)
        portable_path = PurePosixPath(path_text)
        self.assertTrue(portable_path.parts, f"{role} must not be empty")
        self.assertFalse(portable_path.is_absolute(), f"{role} must be relative")
        self.assertNotIn("..", portable_path.parts, f"{role} must not traverse")
        self.assertNotIn("\\", path_text, f"{role} must use POSIX separators")
        self.assertEqual(portable_path.as_posix(), path_text, f"{role} must normalize")
        return portable_path

    def _safe_repository_file(self, path: Path, role: str) -> Path:
        self.assertFalse(REPOSITORY_ROOT.is_symlink())
        relative_path = path.relative_to(REPOSITORY_ROOT)
        current_path = REPOSITORY_ROOT
        for part in relative_path.parts:
            current_path = current_path / part
            self.assertFalse(current_path.is_symlink(), f"{role} must not use symlinks")
        self.assertTrue(path.is_file(), f"missing {role}")
        resolved_path = path.resolve(strict=True)
        self.assertTrue(
            resolved_path.is_relative_to(REPOSITORY_ROOT.resolve(strict=True)),
            f"{role} must stay within the repository",
        )
        return resolved_path

    def test_requires_all_boundary_artifacts(self) -> None:
        required_paths = (
            EVIDENCE_OBJECT_PATH,
            EVIDENCE_PATH,
            OBSERVATIONS_PATH,
            INPUT_BINDINGS_PATH,
            DECISION_OBJECT_PATH,
            DECISION_PATH,
            BOUNDARY_CONTRACT_PATH,
        )

        for path in required_paths:
            with self.subTest(path=path.relative_to(REPOSITORY_ROOT)):
                self._read_required_bytes(path)

    def test_descriptors_have_exact_identity_status_and_local_artifacts(self) -> None:
        self.assertEqual(
            self._read_required_json_object(EVIDENCE_OBJECT_PATH),
            EXPECTED_EVIDENCE_DESCRIPTOR,
        )
        self.assertEqual(
            self._read_required_json_object(DECISION_OBJECT_PATH),
            EXPECTED_DECISION_DESCRIPTOR,
        )

    def test_integrity_observations_are_exact_append_only_canonical_json(self) -> None:
        source = self._read_required_bytes(OBSERVATIONS_PATH)

        self.assertFalse(source.endswith(b"\n"))
        self.assertEqual(source, canonical_json_bytes(EXPECTED_OBSERVATIONS))
        observations_document = cast(dict[str, object], json.loads(source))
        self.assertEqual(observations_document, EXPECTED_OBSERVATIONS)
        observations = cast(list[object], observations_document["observations"])
        self.assertEqual(len(observations), 3)
        self.assertEqual(
            [cast(dict[str, object], value)["phase"] for value in observations],
            [
                "initial_audit",
                "first_rebind_observed",
                "later_deterministic_rerun_observed",
            ],
        )
        self.assertIs(observations_document["generationLineageVerified"], False)

    def test_boundary_contract_is_exact_canonical_json_ssot(self) -> None:
        source = self._read_required_bytes(BOUNDARY_CONTRACT_PATH)

        self.assertFalse(source.endswith(b"\n"))
        self.assertEqual(source, canonical_json_bytes(EXPECTED_BOUNDARY_CONTRACT))
        self.assertEqual(json.loads(source), EXPECTED_BOUNDARY_CONTRACT)

    def test_current_input_bindings_are_exact_canonical_json(self) -> None:
        source = self._read_required_bytes(INPUT_BINDINGS_PATH)

        self.assertFalse(source.endswith(b"\n"))
        self.assertEqual(source, canonical_json_bytes(EXPECTED_INPUT_BINDINGS))
        self.assertEqual(json.loads(source), EXPECTED_INPUT_BINDINGS)

    def test_current_input_bindings_match_all_manifest_inputs_read_only(
        self,
    ) -> None:
        manifest_path = self._safe_repository_file(RUN_MANIFEST_PATH, "run manifest")
        manifest_source = manifest_path.read_bytes()
        manifest = cast(dict[str, object], json.loads(manifest_source))
        bindings_document = self._read_required_json_object(INPUT_BINDINGS_PATH)

        self.assertEqual(
            bindings_document["runManifestSha256"],
            sha256_bytes(manifest_source),
        )
        manifest_inputs = cast(list[object], manifest["inputs"])
        input_bindings = cast(list[object], bindings_document["bindings"])
        self.assertEqual(len(manifest_inputs), 24)
        self.assertEqual(len(input_bindings), 24)
        manifest_records = [cast(dict[str, object], value) for value in manifest_inputs]
        binding_records = [cast(dict[str, object], value) for value in input_bindings]
        manifest_ids = tuple(cast(str, record["id"]) for record in manifest_records)
        binding_ids = tuple(cast(str, record["id"]) for record in binding_records)
        self.assertEqual(manifest_ids, tuple(sorted(manifest_ids)))
        self.assertEqual(binding_ids, manifest_ids)

        for manifest_record, binding in zip(
            manifest_records,
            binding_records,
        ):
            identifier = cast(str, manifest_record["id"])
            self.assertEqual(binding["manifestPath"], manifest_record["path"])
            self._safe_portable_path(
                binding["manifestPath"],
                f"{identifier} manifestPath",
            )
            repository_path = self._safe_portable_path(
                binding["repositoryRelativePath"],
                f"{identifier} repositoryRelativePath",
            )
            actual_path = REPOSITORY_ROOT.joinpath(*repository_path.parts)
            resolved_path = self._safe_repository_file(actual_path, identifier)
            actual_source = resolved_path.read_bytes()
            self.assertEqual(manifest_record["sizeBytes"], len(actual_source))
            self.assertEqual(manifest_record["sha256"], sha256_bytes(actual_source))

    def test_current_rb001_manifest_and_bound_runner_match_recorded_snapshot(
        self,
    ) -> None:
        manifest_path = self._safe_repository_file(RUN_MANIFEST_PATH, "run manifest")
        runner_path = self._safe_repository_file(BOUND_RUNNER_PATH, "bound runner")
        manifest_source = manifest_path.read_bytes()
        runner_source = runner_path.read_bytes()

        self.assertEqual(len(manifest_source), 5064)
        self.assertEqual(
            sha256_bytes(manifest_source),
            "b4ebe5e41c8f8ca536a80fa05bddfe868e1669832555d6c00daffc21c4e0038e",
        )
        self.assertEqual(len(runner_source), 52600)
        self.assertEqual(
            sha256_bytes(runner_source),
            "f906fd61b9b55e2e264adae032517151f9ee7ed24b8804ab878e102944736708",
        )

        manifest = json.loads(manifest_source)
        self.assertIsInstance(manifest, dict)
        manifest_object = cast(dict[str, object], manifest)
        self.assertEqual(manifest_source, canonical_json_bytes(manifest_object))
        recorded_payload_sha256 = manifest_object["manifestPayloadSha256"]
        manifest_payload = {
            key: value
            for key, value in manifest_object.items()
            if key != "manifestPayloadSha256"
        }
        self.assertEqual(
            sha256_bytes(canonical_json_bytes(manifest_payload)),
            "b6f3b49372b60c608692a233bd0abba790af58a3604204084d670cd802325b7f",
        )
        self.assertEqual(
            recorded_payload_sha256,
            "b6f3b49372b60c608692a233bd0abba790af58a3604204084d670cd802325b7f",
        )

        inputs = manifest_object["inputs"]
        self.assertIsInstance(inputs, list)
        input_records = cast(list[object], inputs)
        bound_runner = next(
            (
                cast(dict[str, object], value)
                for value in input_records
                if isinstance(value, dict)
                and value.get("id") == "code:run-validation"
            ),
            None,
        )
        self.assertEqual(
            bound_runner,
            {
                "id": "code:run-validation",
                "path": "analysis/run_validation.py",
                "sha256": sha256_bytes(runner_source),
                "sizeBytes": len(runner_source),
            },
        )

        outputs = manifest_object["outputs"]
        self.assertIsInstance(outputs, list)
        output_values = cast(list[object], outputs)
        self.assertEqual(len(output_values), 8)
        output_bindings: list[dict[str, object]] = []
        for value in output_values:
            self.assertIsInstance(value, dict)
            output_bindings.append(cast(dict[str, object], value))
        self.assertEqual(
            tuple(binding.get("id") for binding in output_bindings),
            EXPECTED_OUTPUT_IDS,
        )

        results_directory = RUN_MANIFEST_PATH.parent.resolve()
        for binding in output_bindings:
            identifier = binding["id"]
            relative_path_value = binding["path"]
            self.assertIsInstance(identifier, str)
            self.assertIsInstance(relative_path_value, str)
            relative_path_text = cast(str, relative_path_value)
            relative_path = self._safe_portable_path(
                relative_path_text,
                f"{identifier} output path",
            )

            output_path = RUN_MANIFEST_PATH.parent.joinpath(*relative_path.parts)
            resolved_output_path = self._safe_repository_file(
                output_path,
                f"{identifier} output",
            )
            self.assertTrue(resolved_output_path.is_relative_to(results_directory))
            output_source = resolved_output_path.read_bytes()
            self.assertEqual(
                binding,
                {
                    "id": identifier,
                    "path": relative_path_text,
                    "sha256": sha256_bytes(output_source),
                    "sizeBytes": len(output_source),
                },
            )

    def test_evidence_preserves_observations_and_limits_claims(self) -> None:
        evidence = self._read_required_text(EVIDENCE_PATH)
        required_fragments = (
            "`initial_audit`",
            "`first_rebind_observed`",
            "`later_deterministic_rerun_observed`",
            "`2026-07-10T07:56:52+09:00`",
            "`2026-07-10T08:02:27+09:00`",
            "`2026-07-10T08:09:33+09:00`",
            "`2026-07-10T08:09:56+09:00`",
            "`2026-07-10T08:12:21+09:00`",
            "`2026-07-10T08:16:31+09:00`",
            "`2026-07-10T08:16:58+09:00`",
            "`2026-07-10T08:17:10+09:00`",
            "docs/codex/plans/2026-07-10-rp-001-sg0-sg2-foundation.md",
            (
                "docs/codex/research/"
                "2026-07-10-mania-panic-fomo-formula-final-report.md"
            ),
            "docs/codex/research/2026-07-10-verification-log.md",
            "`generationLineageVerified=false`",
            "세 phase transition의 실행 주체와 명령은 알려져 있지 않다.",
            (
                "현재 snapshot의 self-consistency는 원래 동결 생성 계보 또는 "
                "G9 재현을 입증하지 않는다."
            ),
            (
                "보고된 두 결정적 실행은 이 감사가 독립적으로 목격하거나 "
                "재실행한 사실이 아니다."
            ),
            (
                "보고된 두 실행은 동일 실행자 또는 동일 팀이 수행했는지 알 수 "
                "없으므로 same-team repeatability로도 분류할 수 없다."
            ),
            (
                "이 감사가 확인한 independent reproducibility 또는 replicability "
                "증거도 아니다."
            ),
            (
                "manifest에 결박된 output 8개 모두의 경로·크기·SHA-256을 읽기 "
                "전용으로 재계산해 각 binding과 일치함을 확인했다."
            ),
            (
                "현재 manifest 입력 24/24의 repository path·크기·SHA-256을 읽기 "
                "전용으로 재계산해 각 binding과 일치함을 확인했다."
            ),
        )
        for fragment in required_fragments:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, evidence)

        self.assertEqual(
            evidence.count(
                "역사적 byte는 더 이상 확보되어 있지 않아 독립적으로 재계산할 수 없다."
            ),
            2,
        )
        for prohibited_actor_claim in (
            "same-team repeatability에 관한 문서상 주장",
            "same-team repeatability를 확인했다",
            "same-team repeatability를 입증했다",
            "동일 실행자가 수행했다",
            "동일 팀이 수행했다",
        ):
            with self.subTest(prohibited_actor_claim=prohibited_actor_claim):
                self.assertNotIn(prohibited_actor_claim, evidence)

    def test_decision_enforces_exact_research_only_boundary(self) -> None:
        decision = self._read_required_text(DECISION_PATH)
        boundary_contract = self._read_required_json_object(BOUNDARY_CONTRACT_PATH)
        decision_status = cast(str, boundary_contract["decisionStatus"])
        operational_use_allowed = cast(
            bool,
            boundary_contract["operationalUseAllowed"],
        )
        allowed_uses = cast(list[str], boundary_contract["allowedUses"])
        prohibited_roles = cast(
            list[str],
            boundary_contract["prohibitedEvidenceRoles"],
        )
        reopen_conditions = cast(
            list[str],
            boundary_contract["reopenConditions"],
        )

        self.assertEqual(decision.count(f"- 상태: `{decision_status}`"), 1)
        operational_label = "YES" if operational_use_allowed else "NO"
        self.assertEqual(
            decision.count(f"- 운영 사용 가능 여부: `{operational_label}`"),
            1,
        )
        self.assertEqual(
            self._literal_bullets(decision, "허용 범위"),
            tuple(allowed_uses),
        )
        self.assertEqual(
            self._literal_bullets(decision, "금지 범위"),
            tuple(prohibited_roles),
        )
        self.assertIn(
            "G0: 원래 동결 생성 계보가 입증되지 않아 기존 RB-001의 경계 통과 "
            "근거로 사용할 수 없다.",
            decision,
        )
        self.assertIn(
            "G9: 현재 self-consistency와 보고된 반복 실행은 독립 artifact "
            "reproduction이 아니므로 독립재현 통과 근거가 아니다.",
            decision,
        )
        self.assertEqual(
            self._literal_bullets(decision, "재개 조건"),
            tuple(reopen_conditions),
        )
        self.assertIn(
            "`boundary-contract.json`은 권위 있는 경계 SSOT다.",
            decision,
        )
        self.assertIn(
            "`boundary-contract.json`과 충돌하는 prose는 허용 범위를 넓힐 수 없다.",
            decision,
        )
        for contradiction in (
            "- 상태: `adopt`",
            "- 상태: `conditional_adopt`",
            "- 운영 사용 가능 여부: `YES`",
            "G0: `passed`",
            "G9: `passed`",
        ):
            with self.subTest(contradiction=contradiction):
                self.assertNotIn(contradiction, decision)

    def test_security_claims_report_registered_scope_and_zero_matches(self) -> None:
        required_statements = (
            (
                "등록된 민감값 패턴 정책으로 이 aggregate의 artifact를 검사한 "
                "결과 match는 0건이다."
            ),
            (
                "이 결과는 등록 패턴 범위에 한정되며 모든 가능한 민감값 부재를 "
                "증명하지 않는다."
            ),
        )
        documents = {
            "evidence": self._read_required_text(EVIDENCE_PATH),
            "decision": self._read_required_text(DECISION_PATH),
        }

        for role, document in documents.items():
            with self.subTest(role=role):
                for statement in required_statements:
                    self.assertIn(statement, document)
                self.assertNotIn(
                    "API key, access token, 계좌정보 또는 사용자 secret 값을 포함하지 않는다.",
                    document,
                )

    def test_boundary_artifacts_contain_no_placeholders_or_secret_values(self) -> None:
        artifact_paths = (
            EVIDENCE_OBJECT_PATH,
            EVIDENCE_PATH,
            OBSERVATIONS_PATH,
            INPUT_BINDINGS_PATH,
            DECISION_OBJECT_PATH,
            DECISION_PATH,
            BOUNDARY_CONTRACT_PATH,
        )
        placeholder_pattern = re.compile(
            r"<[A-Z][A-Z0-9_-]*>|\b(?:TODO|TBD|FIXME|REPLACE_ME)\b"
        )

        for path in artifact_paths:
            with self.subTest(path=path.relative_to(REPOSITORY_ROOT)):
                source = self._read_required_text(path)
                self.assertIsNone(placeholder_pattern.search(source))
                self.assertEqual(find_sensitive_values(source), ())


if __name__ == "__main__":
    unittest.main()
