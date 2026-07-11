from __future__ import annotations

import base64
import hashlib
import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import zstandard

from rp001.toss_research_collector import RawHttpCapture
from rp001_s2.instrument_directory_storage import (
    ImmutableInstrumentDirectoryStorage,
    InstrumentDirectoryStorageError,
)
from rp001_s2.us_instrument_directory import (
    CollectedUsInstrumentDirectory,
    parse_us_instrument_directory,
)


_AVAILABLE_BYTES = 60 * 1024**3
_CAPACITY_THRESHOLD = 50 * 1024**3
_NASDAQ = (
    "Symbol|Security Name|Market Category|Test Issue|Financial Status|"
    "Round Lot Size|ETF|NextShares\r\n"
    "AAPL|Apple Inc. - Common Stock|Q|N|N|40|N|N\r\n"
    "QQQ|Invesco QQQ Trust ETF|G|N|N|100|Y|N\r\n"
    "TEST|Test Common Stock|S|Y|N|100|N|N\r\n"
    "File Creation Time: 0711202621:00|||||||\r\n"
).encode("utf-8")
_OTHER = (
    "ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|"
    "Test Issue|NASDAQ Symbol\r\n"
    "TSLA|Tesla, Inc. - Common Stock|N|TSLA|N|100|N|TSLA\r\n"
    "SPY|SPDR S&P 500 ETF Trust|P|SPY|Y|100|N|SPY\r\n"
    "File Creation Time: 0711202621:01||||||\r\n"
).encode("utf-8")


def _capture(
    endpoint_id: str,
    url: str,
    body: bytes,
    received_at: str,
) -> RawHttpCapture:
    return RawHttpCapture(
        endpoint_id=endpoint_id,
        method="GET",
        sanitized_url=url,
        query=(),
        status=200,
        headers=(("content-type", "text/plain"),),
        received_at=received_at,
        body_base64=base64.b64encode(body).decode("ascii"),
        body_sha256=hashlib.sha256(body).hexdigest(),
    )


def _collected() -> CollectedUsInstrumentDirectory:
    return CollectedUsInstrumentDirectory(
        directory=parse_us_instrument_directory(_NASDAQ, _OTHER),
        captures=(
            _capture(
                "nasdaq_listed_symbol_directory",
                "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
                _NASDAQ,
                "2026-07-11T07:00:00Z",
            ),
            _capture(
                "other_listed_symbol_directory",
                "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt",
                _OTHER,
                "2026-07-11T07:00:01Z",
            ),
        ),
    )


class InstrumentDirectoryStorageWriteTest(unittest.TestCase):
    def test_writes_exact_raw_master_and_manifest_lineage(self) -> None:
        collected = _collected()
        with tempfile.TemporaryDirectory() as temporary_directory:
            storage = ImmutableInstrumentDirectoryStorage(
                Path(temporary_directory),
                free_bytes=lambda _path: _AVAILABLE_BYTES,
            )

            stored = storage.write_collection(collected)

            self.assertEqual(
                zstandard.ZstdDecompressor().decompress(
                    stored.nasdaq_raw_path.read_bytes()
                ),
                _NASDAQ,
            )
            self.assertEqual(
                zstandard.ZstdDecompressor().decompress(
                    stored.other_raw_path.read_bytes()
                ),
                _OTHER,
            )
            self.assertEqual(
                stored.nasdaq_raw_path.relative_to(stored.archive_directory).as_posix(),
                "raw/nasdaqlisted.txt.zst",
            )
            self.assertEqual(
                stored.other_raw_path.relative_to(stored.archive_directory).as_posix(),
                "raw/otherlisted.txt.zst",
            )
            master_bytes = stored.master_path.read_bytes()
            master = json.loads(master_bytes)
            self.assertEqual(
                master_bytes,
                json.dumps(
                    master,
                    allow_nan=False,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8"),
            )
            self.assertEqual(len(master["records"]), len(collected.directory.records))
            self.assertEqual(
                master["eligibleSymbols"],
                list(collected.directory.eligible_symbols),
            )
            self.assertEqual(
                master["fileCreationTimes"],
                {
                    "nasdaqlisted": "0711202621:00",
                    "otherlisted": "0711202621:01",
                },
            )
            self.assertEqual(
                master["etfAssetClassStatus"],
                "not_identifiable_from_directory",
            )
            lineage = master["rawLineage"]
            self.assertEqual(
                lineage["nasdaqlisted"]["bodySha256"],
                hashlib.sha256(_NASDAQ).hexdigest(),
            )
            self.assertEqual(
                lineage["otherlisted"]["bodySha256"],
                hashlib.sha256(_OTHER).hexdigest(),
            )
            by_symbol = {record["symbol"]: record for record in master["records"]}
            self.assertEqual(
                by_symbol["AAPL"]["rawBodySha256"],
                hashlib.sha256(_NASDAQ).hexdigest(),
            )
            self.assertEqual(
                by_symbol["TSLA"]["rawBodySha256"],
                hashlib.sha256(_OTHER).hexdigest(),
            )
            manifest = json.loads(stored.manifest_path.read_bytes())
            self.assertEqual(manifest["contentIdentity"], stored.content_identity)
            self.assertEqual(
                manifest["rawArtifacts"][0]["receivedAt"],
                "2026-07-11T07:00:00Z",
            )
            self.assertNotIn("masterSha256", master)
            self.assertNotIn("manifestSha256", manifest)
            self.assertEqual(
                stored.master_sha256_path.read_text(encoding="ascii"),
                f"{hashlib.sha256(master_bytes).hexdigest()}\n",
            )
            manifest_bytes = stored.manifest_path.read_bytes()
            self.assertEqual(
                stored.manifest_sha256_path.read_text(encoding="ascii"),
                f"{hashlib.sha256(manifest_bytes).hexdigest()}\n",
            )

    def test_identical_inputs_have_one_content_identity_and_canonical_bytes(self) -> None:
        artifacts: list[tuple[str, bytes, bytes]] = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as temporary_directory:
                stored = ImmutableInstrumentDirectoryStorage(
                    Path(temporary_directory),
                    free_bytes=lambda _path: _AVAILABLE_BYTES,
                ).write_collection(_collected())
                artifacts.append(
                    (
                        stored.content_identity,
                        stored.master_path.read_bytes(),
                        stored.manifest_path.read_bytes(),
                    )
                )

        self.assertEqual(artifacts[0], artifacts[1])

    def test_existing_content_identity_is_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            storage = ImmutableInstrumentDirectoryStorage(
                root,
                free_bytes=lambda _path: _AVAILABLE_BYTES,
            )
            stored = storage.write_collection(_collected())
            before = {
                path.relative_to(stored.archive_directory): hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
                for path in stored.archive_directory.rglob("*")
                if path.is_file()
            }

            with self.assertRaises(InstrumentDirectoryStorageError) as raised:
                storage.write_collection(_collected())

            self.assertEqual(raised.exception.code, "directory_archive_already_exists")
            after = {
                path.relative_to(stored.archive_directory): hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
                for path in stored.archive_directory.rglob("*")
                if path.is_file()
            }
            self.assertEqual(after, before)

    def test_capacity_guard_runs_before_each_write_without_cleanup(self) -> None:
        for blocked_call in range(6):
            with self.subTest(blocked_call=blocked_call):
                with tempfile.TemporaryDirectory() as temporary_directory:
                    root = Path(temporary_directory)
                    calls: list[Path] = []

                    def free_bytes(path: Path) -> int:
                        calls.append(path)
                        if len(calls) - 1 == blocked_call:
                            return _CAPACITY_THRESHOLD - 1
                        return _CAPACITY_THRESHOLD

                    storage = ImmutableInstrumentDirectoryStorage(
                        root,
                        free_bytes=free_bytes,
                    )

                    with self.assertRaises(InstrumentDirectoryStorageError) as raised:
                        storage.write_collection(_collected())

                    self.assertEqual(raised.exception.code, "blocked_storage_capacity")
                    self.assertEqual(len(calls), blocked_call + 1)
                    written = tuple(
                        path
                        for path in root.rglob("*")
                        if path.is_file()
                    )
                    self.assertEqual(len(written), blocked_call)


class InstrumentDirectoryStorageBoundaryTest(unittest.TestCase):
    def test_root_must_exist_be_real_private_and_owned(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            missing = parent / "missing"
            with self.assertRaisesRegex(
                InstrumentDirectoryStorageError,
                "directory_storage_root_invalid",
            ):
                ImmutableInstrumentDirectoryStorage(missing)

            public = parent / "public"
            public.mkdir(mode=0o755)
            public.chmod(0o755)
            with self.assertRaisesRegex(
                InstrumentDirectoryStorageError,
                "directory_storage_root_invalid",
            ):
                ImmutableInstrumentDirectoryStorage(public)

            private = parent / "private"
            private.mkdir(mode=0o700)
            link = parent / "link"
            link.symlink_to(private, target_is_directory=True)
            with self.assertRaisesRegex(
                InstrumentDirectoryStorageError,
                "directory_storage_root_invalid",
            ):
                ImmutableInstrumentDirectoryStorage(link)

            storage = ImmutableInstrumentDirectoryStorage(
                private,
                free_bytes=lambda _path: _AVAILABLE_BYTES,
            )
            self.assertIsInstance(storage, ImmutableInstrumentDirectoryStorage)

    def test_input_must_bind_exact_two_raw_bodies_to_parsed_directory(self) -> None:
        collected = _collected()
        invalid_values = (
            replace(collected, captures=collected.captures[:1]),
            replace(
                collected,
                captures=(collected.captures[1], collected.captures[0]),
            ),
            replace(
                collected,
                directory=replace(
                    collected.directory,
                    eligible_symbols=collected.directory.eligible_symbols[:-1],
                ),
            ),
        )

        for invalid in invalid_values:
            with self.subTest(capture_count=len(invalid.captures)):
                with tempfile.TemporaryDirectory() as temporary_directory:
                    storage = ImmutableInstrumentDirectoryStorage(
                        Path(temporary_directory),
                        free_bytes=lambda _path: _AVAILABLE_BYTES,
                    )
                    with self.assertRaisesRegex(
                        InstrumentDirectoryStorageError,
                        "directory_collection_invalid",
                    ):
                        storage.write_collection(invalid)


class InstrumentDirectoryStorageVerificationTest(unittest.TestCase):
    def test_verification_detects_every_artifact_modification(self) -> None:
        artifact_names = (
            "nasdaq_raw_path",
            "other_raw_path",
            "master_path",
            "master_sha256_path",
            "manifest_path",
            "manifest_sha256_path",
        )
        for artifact_name in artifact_names:
            with self.subTest(artifact_name=artifact_name):
                with tempfile.TemporaryDirectory() as temporary_directory:
                    storage = ImmutableInstrumentDirectoryStorage(
                        Path(temporary_directory),
                        free_bytes=lambda _path: _AVAILABLE_BYTES,
                    )
                    stored = storage.write_collection(_collected())
                    storage.verify_archive(stored)
                    artifact = getattr(stored, artifact_name)
                    source = artifact.read_bytes()
                    artifact.write_bytes(source[:-1] + bytes((source[-1] ^ 1,)))

                    with self.assertRaises(InstrumentDirectoryStorageError) as raised:
                        storage.verify_archive(stored)

                    self.assertEqual(
                        raised.exception.code,
                        "directory_archive_verification_failed",
                    )


if __name__ == "__main__":
    unittest.main()
