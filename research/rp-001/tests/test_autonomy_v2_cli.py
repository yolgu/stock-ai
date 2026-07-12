from __future__ import annotations

import json
import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PYTHON = Path(
    "/Users/jik/.cache/codex-runtimes/codex-primary-runtime/"
    "dependencies/python/bin/python3"
)
CLI = REPOSITORY_ROOT / "research" / "rp-001" / "quant_autonomous_research.py"


class QuantAutonomyCliTest(unittest.TestCase):
    def test_bootstrap_status_and_next_are_canonical(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            goal = root / "goal.md"
            goal.write_text(
                "[QUANT_RESEARCH_GOAL]\n시장 과열 수식을 연구한다.\n",
                encoding="utf-8",
            )
            bootstrapped = self._run(
                root,
                "bootstrap-campaign",
                "--goal",
                str(goal),
                "--occurred-at",
                "2026-07-12T13:00:00Z",
            )
            body = json.loads(bootstrapped.stdout)
            campaign_id = body["campaignId"]

            status = self._run(root, "status", "--campaign-id", campaign_id)
            action = self._run(root, "next", "--campaign-id", campaign_id)

            self.assertEqual(0, bootstrapped.returncode, bootstrapped.stderr)
            self.assertEqual("DEFINE_RESEARCH_QUESTION", body["state"])
            self.assertEqual(body, json.loads(status.stdout))
            self.assertEqual(
                "DEFINE_RESEARCH_QUESTION",
                json.loads(action.stdout)["actionKind"],
            )

            action_value = json.loads(action.stdout)
            result_directory = root / action_value["allowedWriteDirectory"]
            result_directory.mkdir(parents=True, exist_ok=True)
            result = result_directory / "action-result.json"
            result.write_text(
                json.dumps(
                    {
                        "actionId": action_value["actionId"],
                        "actionKind": action_value["actionKind"],
                        "facts": {"questionId": "RQ-PRED"},
                        "fromState": "DEFINE_RESEARCH_QUESTION",
                        "schemaVersion": "quant-research-action-result.v2",
                        "toState": "REGISTER_DATA_CONTRACT",
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            Path(f"{result}.sha256").write_text(
                f"{hashlib.sha256(result.read_bytes()).hexdigest()}\n",
                encoding="ascii",
            )
            committed = self._run(
                root,
                "commit-action",
                "--campaign-id",
                campaign_id,
                "--result",
                str(result),
                "--occurred-at",
                "2026-07-12T13:01:00Z",
            )
            self.assertEqual(
                "REGISTER_DATA_CONTRACT",
                json.loads(committed.stdout)["state"],
            )

    def _run(
        self,
        repository_root: Path,
        *arguments: str,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                str(PYTHON),
                "-B",
                str(CLI),
                *arguments,
                "--repository-root",
                str(repository_root),
            ],
            text=True,
            capture_output=True,
            check=False,
            env={"PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(REPOSITORY_ROOT / "research" / "rp-001" / "src")},
        )


if __name__ == "__main__":
    unittest.main()
