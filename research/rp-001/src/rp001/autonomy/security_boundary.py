"""Fail-closed filesystem boundaries independent of Codex hooks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rp001.autonomy.model import ProgramSnapshot


class SecurityBoundaryError(ValueError):
    """Raised when autonomous research crosses a protected data boundary."""


@dataclass(frozen=True)
class ResearchFilesystemBoundary:
    repository_root: Path
    preset_output_root: Path
    live_collection_roots: tuple[Path, ...]
    confirmation_release_root: Path

    def __post_init__(self) -> None:
        roots = (
            self.repository_root,
            self.preset_output_root,
            self.confirmation_release_root,
            *self.live_collection_roots,
        )
        if any(not path.is_absolute() for path in roots):
            raise SecurityBoundaryError("boundary_root_invalid")
        if not _is_within(self.preset_output_root, self.repository_root):
            raise SecurityBoundaryError("boundary_root_invalid")
        protected_roots = (
            self.confirmation_release_root,
            *self.live_collection_roots,
        )
        if any(
            _paths_overlap(self.preset_output_root, root)
            for root in protected_roots
        ) or any(
            _paths_overlap(self.confirmation_release_root, root)
            for root in self.live_collection_roots
        ):
            raise SecurityBoundaryError("boundary_root_overlap")

    def require_write_path(self, path: Path) -> Path:
        """Allow writes only inside the dedicated autonomous run directory."""
        candidate = _absolute_without_symlink(path)
        if any(_is_within(candidate, root) for root in self.live_collection_roots):
            raise SecurityBoundaryError("write_path_denied")
        if not _is_within(candidate, self.preset_output_root):
            raise SecurityBoundaryError("write_path_denied")
        return candidate

    def require_confirmation_release(
        self,
        path: Path,
        snapshot: ProgramSnapshot,
    ) -> Path:
        """Expose a real confirmation file only after formula freeze."""
        if not snapshot.confirmation_frozen:
            raise SecurityBoundaryError("confirmation_not_frozen")
        if path.is_symlink():
            raise SecurityBoundaryError("confirmation_path_invalid")
        try:
            candidate = path.resolve(strict=True)
        except OSError:
            raise SecurityBoundaryError("confirmation_path_invalid") from None
        if (
            not candidate.is_file()
            or not _is_within(candidate, self.confirmation_release_root)
            or any(_is_within(candidate, root) for root in self.live_collection_roots)
        ):
            raise SecurityBoundaryError("confirmation_path_invalid")
        return candidate


def _absolute_without_symlink(path: Path) -> Path:
    try:
        candidate = path.resolve(strict=False)
    except OSError:
        raise SecurityBoundaryError("write_path_denied") from None
    return candidate


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root.resolve(strict=False))
    except ValueError:
        return False
    return True


def _paths_overlap(left: Path, right: Path) -> bool:
    return _is_within(left, right) or _is_within(right, left)
