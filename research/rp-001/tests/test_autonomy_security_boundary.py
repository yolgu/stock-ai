from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from rp001.autonomy.model import ProgramSnapshot
from rp001.autonomy.security_boundary import (
    ResearchFilesystemBoundary,
    SecurityBoundaryError,
)


class AutonomySecurityBoundaryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name).resolve()
        self.output_root = self.root / "research" / "autonomy-runs"
        self.live_collection_root = self.root / ".storage" / "rp001-data"
        self.confirmation_release_root = self.root / "released-confirmation"
        self.output_root.mkdir(parents=True)
        self.live_collection_root.mkdir(parents=True)
        self.confirmation_release_root.mkdir(parents=True)
        self.boundary = ResearchFilesystemBoundary(
            repository_root=self.root,
            preset_output_root=self.output_root,
            live_collection_roots=(self.live_collection_root,),
            confirmation_release_root=self.confirmation_release_root,
        )

    def test_allows_only_preset_output_writes(self) -> None:
        allowed = self.output_root / "PROGRAM-001" / "artifact.json"

        self.assertEqual(allowed, self.boundary.require_write_path(allowed))

        for denied in (
            self.live_collection_root / "raw" / "page.json",
            self.root / "research" / "rp-001" / "contracts" / "frozen.json",
        ):
            with self.subTest(denied=denied):
                with self.assertRaisesRegex(SecurityBoundaryError, "write_path_denied"):
                    self.boundary.require_write_path(denied)

    def test_confirmation_release_is_denied_before_formula_freeze(self) -> None:
        release = self.confirmation_release_root / "confirmation-001.json"
        release.write_text("{}", encoding="utf-8")

        with self.assertRaisesRegex(SecurityBoundaryError, "confirmation_not_frozen"):
            self.boundary.require_confirmation_release(
                release,
                ProgramSnapshot.initial(),
            )

    def test_confirmation_release_is_allowed_only_after_freeze(self) -> None:
        release = self.confirmation_release_root / "confirmation-001.json"
        release.write_text("{}", encoding="utf-8")
        snapshot = replace(ProgramSnapshot.initial(), confirmation_frozen=True)

        self.assertEqual(
            release,
            self.boundary.require_confirmation_release(release, snapshot),
        )

    def test_symlinked_confirmation_release_is_rejected(self) -> None:
        external = self.root / "external.json"
        external.write_text("{}", encoding="utf-8")
        linked = self.confirmation_release_root / "confirmation-link.json"
        linked.symlink_to(external)
        snapshot = replace(ProgramSnapshot.initial(), confirmation_frozen=True)

        with self.assertRaisesRegex(SecurityBoundaryError, "confirmation_path_invalid"):
            self.boundary.require_confirmation_release(linked, snapshot)

    def test_confirmation_and_live_roots_cannot_overlap_output_root(self) -> None:
        cases = (
            {
                "preset_output_root": self.output_root,
                "live_collection_roots": (self.live_collection_root,),
                "confirmation_release_root": self.output_root / "confirmation",
            },
            {
                "preset_output_root": self.live_collection_root / "autonomy-runs",
                "live_collection_roots": (self.live_collection_root,),
                "confirmation_release_root": self.confirmation_release_root,
            },
        )
        for arguments in cases:
            with self.subTest(arguments=arguments):
                with self.assertRaisesRegex(
                    SecurityBoundaryError,
                    "boundary_root_overlap",
                ):
                    ResearchFilesystemBoundary(
                        repository_root=self.root,
                        **arguments,
                    )


if __name__ == "__main__":
    unittest.main()
