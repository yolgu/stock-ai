"""Cross-process singleton lease for Toss OpenAPI research sessions."""

from __future__ import annotations

import fcntl
import os
import stat
import threading
from pathlib import Path


_SINGLE_SESSION_LOCK_NAME = ".toss-openapi-single-session.lock"
_ACTIVE_SESSION_LOCK = threading.Lock()
_ACTIVE_SESSION_KEYS: set[str] = set()


class TossSessionLeaseError(ValueError):
    """Stable failure to acquire the singleton session lease."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class ExclusiveTossSessionLease:
    """Reject concurrent research processes before authentication."""

    def __init__(self, descriptor: int, session_key: str) -> None:
        self._descriptor = descriptor
        self._session_key = session_key
        self._closed = False

    @classmethod
    def acquire(cls, credential_file: Path) -> ExclusiveTossSessionLease:
        lock_path = credential_file.parent / _SINGLE_SESSION_LOCK_NAME
        session_key = str(lock_path.resolve())
        descriptor = -1
        with _ACTIVE_SESSION_LOCK:
            if session_key in _ACTIVE_SESSION_KEYS:
                raise TossSessionLeaseError("session_already_active")
            try:
                descriptor = os.open(
                    lock_path,
                    os.O_RDWR
                    | os.O_CREAT
                    | getattr(os, "O_CLOEXEC", 0)
                    | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                )
                metadata = os.fstat(descriptor)
                if (
                    not stat.S_ISREG(metadata.st_mode)
                    or metadata.st_uid != os.getuid()
                ):
                    raise OSError
                os.fchmod(descriptor, 0o600)
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                if descriptor >= 0:
                    os.close(descriptor)
                raise TossSessionLeaseError("session_already_active") from None
            except OSError:
                if descriptor >= 0:
                    os.close(descriptor)
                raise TossSessionLeaseError("session_lock_unavailable") from None
            _ACTIVE_SESSION_KEYS.add(session_key)
        return cls(descriptor, session_key)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        with _ACTIVE_SESSION_LOCK:
            _ACTIVE_SESSION_KEYS.discard(self._session_key)
            try:
                fcntl.flock(self._descriptor, fcntl.LOCK_UN)
            finally:
                os.close(self._descriptor)
