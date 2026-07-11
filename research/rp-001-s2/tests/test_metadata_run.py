from __future__ import annotations

import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from rp001.local_evidence import (
    AppendOnlyLocalLedger,
    LocalArtifactStore,
    canonical_json_bytes,
    sha256_bytes,
)
from rp001_s2.metadata_run import (
    MetadataRunArguments,
    MetadataRunError,
    run_metadata_collection,
)
from rp001_s2.sample_design import CANDIDATE_POOL


class _Response:
    def __init__(self, body: bytes) -> None:
        self.status = 200
        self.headers = {"Content-Type": "application/json"}
        self._stream = io.BytesIO(body)

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)

    def close(self) -> None:
        self._stream.close()


class _Opener:
    def __init__(self, responses: tuple[_Response, ...]) -> None:
        self.responses = list(responses)

    def open(self, request: object, timeout: float) -> _Response:
        del request, timeout
        return self.responses.pop(0)


class MetadataRunEvidenceTest(unittest.TestCase):
    def test_success_publishes_hashed_artifacts_and_one_ledger_event(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            contract_path = root / (
                "research/rp-001-s2/contracts/read-only-source-contract-v1.json"
            )
            contract_path.parent.mkdir(parents=True)
            binding_keys = (
                "formulaSource",
                "formulaTests",
                "sampleSource",
                "sampleTests",
                "tossBoundarySource",
                "tossBoundaryTests",
                "metadataRunSource",
                "metadataRunTests",
                "metadataCli",
                "evaluationSource",
                "evaluationTests",
                "collectorSource",
                "collectorTests",
                "sensitivePolicySource",
                "sensitivePolicyTests",
                "localEvidenceSource",
                "localEvidenceTests",
            )
            bound_paths: list[Path] = []
            for name in ("merc.json", "sample.json", *binding_keys):
                bound = contract_path.parent / name
                bound.write_text(f"bound:{name}")
                bound_paths.append(bound)
            bindings = [
                {
                    "path": path.relative_to(root).as_posix(),
                    "sha256": sha256_bytes(path.read_bytes()),
                }
                for path in bound_paths
            ]
            contract = {
                "allowedRequests": [
                    {"method": "POST", "path": "/oauth2/token"},
                    {"method": "GET", "path": "/api/v1/stocks"},
                ],
                "candidatePool": list(CANDIDATE_POOL),
                "credentialBoundary": {
                    "input": "one_shot_process_environment",
                    "variableNames": ["TOSS_CLIENT_ID", "TOSS_CLIENT_SECRET"],
                    "consumeImmediately": True,
                    "commandLineValues": "forbidden",
                    "persistenceInArtifactsLogsOrManifest": "forbidden",
                    "oauthTokenPersistence": "forbidden",
                },
                "cycleId": "RP-001-S2-CYCLE-001",
                "implementationBindings": {
                    key: binding
                    for key, binding in zip(binding_keys, bindings[2:], strict=True)
                },
                "merc": bindings[0],
                "metadataSampleDesign": bindings[1],
                "ordersAccountsAssetsAllowed": False,
                "programId": "RP-001-S2",
                "schemaVersion": "rp001-s2-read-only-source-contract.v1",
                "status": "metadata_only_authorized_price_unopened",
            }
            contract_source = canonical_json_bytes(contract)
            contract_hash = sha256_bytes(contract_source)
            contract_path.write_bytes(contract_source)
            Path(f"{contract_path}.sha256").write_text(f"{contract_hash}\n")
            ledger_parent = root / "research/rp-001-s2/local-ledgers"
            LocalArtifactStore(root).ensure_directory(ledger_parent)
            AppendOnlyLocalLedger(ledger_parent / "program").append(
                "rp001_s2_cycle_001_merc_frozen",
                {
                    "programId": "RP-001-S2",
                    "cycleId": "RP-001-S2-CYCLE-001",
                    "merc": bindings[0],
                    "metadataSampleDesign": bindings[1],
                    "readOnlySourceContract": {
                        "path": contract_path.relative_to(root).as_posix(),
                        "sha256": contract_hash,
                    },
                    "predecessorArtifactsRemainImmutable": True,
                    "priceVolumeOpened": False,
                    "ordersAccountsAssetsAllowed": False,
                },
                "2026-07-11T00:00:00Z",
            )
            records = [
                {
                    "symbol": symbol,
                    "name": symbol,
                    "englishName": symbol,
                    "isinCode": f"US{symbol:0<10}"[:12],
                    "market": "NYSE",
                    "securityType": "STOCK",
                    "isCommonShare": True,
                    "status": "ACTIVE",
                    "currency": "USD",
                    "sharesOutstanding": "1000000",
                }
                for symbol in CANDIDATE_POOL
            ]
            opener = _Opener(
                (
                    _Response(b'{"access_token":"ephemeral-token"}'),
                    _Response(
                        json.dumps({"result": records}, separators=(",", ":")).encode()
                    ),
                )
            )

            summary = run_metadata_collection(
                MetadataRunArguments(
                    repository_root=root,
                    contract_path=contract_path,
                    contract_sha256=contract_hash,
                    run_id="S2-META-TEST-001",
                ),
                opener=opener,
                clock=lambda: datetime(2026, 7, 11, tzinfo=timezone.utc),
                environment={
                    "TOSS_CLIENT_ID": "identifier",
                    "TOSS_CLIENT_SECRET": "credential",
                },
            )

            self.assertEqual(summary.status, "succeeded")
            run = root / "research/rp-001-s2/metadata-runs/S2-META-TEST-001"
            self.assertEqual(len(tuple(run.glob("*.json"))), 5)
            self.assertEqual(len(tuple(run.glob("*.json.sha256"))), 5)
            events = root / "research/rp-001-s2/local-ledgers/program/events"
            self.assertEqual(len(tuple(events.glob("*.json"))), 2)
            published = "".join(path.read_text() for path in run.glob("*.json"))
            self.assertNotIn("identifier", published)
            self.assertNotIn("credential", published)
            self.assertNotIn("ephemeral-token", published)

            failing_opener = _Opener(
                (
                    _Response(b'{"access_token":"second-ephemeral-token"}'),
                    _Response(b'{"result":[]}'),
                )
            )
            with self.assertRaisesRegex(MetadataRunError, "MISSING_METADATA_SYMBOLS"):
                run_metadata_collection(
                    MetadataRunArguments(
                        repository_root=root,
                        contract_path=contract_path,
                        contract_sha256=contract_hash,
                        run_id="S2-META-TEST-002",
                    ),
                    opener=failing_opener,
                    clock=lambda: datetime(2026, 7, 11, tzinfo=timezone.utc),
                    environment={
                        "TOSS_CLIENT_ID": "identifier",
                        "TOSS_CLIENT_SECRET": "credential",
                    },
                )
            failure_run = root / "research/rp-001-s2/metadata-runs/S2-META-TEST-002"
            capture_body = json.loads(
                (failure_run / "failure-captures.json").read_text()
            )
            self.assertEqual(capture_body["captureCount"], 1)
            self.assertIn("bodyBase64", capture_body["captures"][0])
            self.assertIn("bodySha256", capture_body["captures"][0])
            self.assertEqual(
                capture_body["captures"][0]["receivedAt"],
                "2026-07-11T00:00:00Z",
            )

            bound_paths[2].write_text("tampered-after-freeze")
            with self.assertRaisesRegex(MetadataRunError, "contract_binding_invalid"):
                run_metadata_collection(
                    MetadataRunArguments(
                        repository_root=root,
                        contract_path=contract_path,
                        contract_sha256=contract_hash,
                        run_id="S2-META-TEST-003",
                    ),
                    opener=_Opener(()),
                    clock=lambda: datetime(2026, 7, 11, tzinfo=timezone.utc),
                    environment={
                        "TOSS_CLIENT_ID": "identifier",
                        "TOSS_CLIENT_SECRET": "credential",
                    },
                )


if __name__ == "__main__":
    unittest.main()
