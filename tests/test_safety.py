import base64
import json
import mmap
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from capacidadreal.devices import identify, serial_details, usable, validate
from capacidadreal.helper import Journal, RawDevice
from capacidadreal.engine import run
from test_engine import MemoryDevice, MemoryJournal


def device(**overrides):
    value = {"name": "/dev/test", "type": "disk", "tran": "usb", "ro": False,
             "size": 64 * 1024 * 1024, "serial": "test", "model": "test", "mountpoints": [None]}
    value.update(overrides)
    return value


class SafetyTests(unittest.TestCase):
    def test_native_sd_serial_and_embedded_mmc_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            attr = root / "mmcblk0/device"
            attr.mkdir(parents=True)
            (attr / "type").write_text("SD\n")
            (attr / "serial").write_text("0x1234abcd\n")
            info = identify(device(name="/dev/mmcblk0", tran="mmc", rm=True), root)
            self.assertTrue(usable(info))
            self.assertEqual(info["serial"], "0x1234abcd")
            self.assertEqual(serial_details(info)[1], "Número de serie de la tarjeta SD, informado por Linux.")
            validate(info, info["size"], "0x1234abcd")
            (attr / "type").write_text("MMC\n")
            embedded = identify(device(name="/dev/mmcblk0", tran="mmc", rm=True), root)
            self.assertFalse(usable(embedded))
            with self.assertRaises(ValueError):
                validate(embedded, embedded["size"], embedded["serial"])

    def test_nonremovable_sd_is_not_a_test_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            attr = root / "mmcblk0/device"
            attr.mkdir(parents=True)
            (attr / "type").write_text("SD\n")
            info = identify(device(name="/dev/mmcblk0", tran="mmc", rm=False), root)
            self.assertFalse(usable(info))

    def test_usb_serial_source_and_missing_serial(self):
        info = identify(device(serial="  ABC123  "))
        self.assertEqual(info["serial"], "  ABC123  ")
        serial, note, available = serial_details(info)
        self.assertEqual(serial, "ABC123")
        self.assertIn("lector", note)
        self.assertTrue(available)
        serial, note, available = serial_details(identify(device(serial=None)))
        self.assertEqual(serial, "No disponible")
        self.assertFalse(available)
        self.assertIsNone(identify(device(serial=None))["serial"])

    def test_real_direct_io_on_temporary_file_restores_every_byte(self):
        # Exercise production preadv/pwritev and aligned mmap buffers on an
        # ordinary temporary file. Never open a real disk from tests.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "usb-simulation.bin"
            original = os.urandom(2 * 1024 * 1024)
            path.write_bytes(original)
            dev = RawDevice.__new__(RawDevice)
            dev.fd = os.open(path, os.O_RDWR | os.O_DIRECT)
            dev.block = 4096
            dev.size = len(original)
            dev.buffer = mmap.mmap(-1, dev.block)
            dev.flush = lambda: os.fsync(dev.fd)
            try:
                result = run(dev, MemoryJournal())
                self.assertEqual(result["status"], "compatible")
            finally:
                dev.close()
            self.assertEqual(path.read_bytes(), original)

    def test_reject_non_usb(self):
        with self.assertRaises(ValueError):
            validate(device(tran="sata"), 64 * 1024 * 1024, "test")

    def test_reject_changed_identity(self):
        with self.assertRaises(ValueError):
            validate(device(), 64 * 1024 * 1024, "another")

    def test_reject_mounted_child_and_swap(self):
        for mount in ("/", "/media/test", "[SWAP]"):
            with self.subTest(mount=mount), self.assertRaises(ValueError):
                validate(device(children=[device(mountpoints=[mount])]), 64 * 1024 * 1024, "test")

    def test_reject_read_only(self):
        with self.assertRaises(ValueError):
            validate(device(ro=True), 64 * 1024 * 1024, "test")

    def test_journal_roundtrip(self):
        dev = MemoryDevice()
        with tempfile.TemporaryDirectory() as directory:
            journal = Journal(device(), dev.block, Path(directory))
            saved = {0: dev.read(0), 8192: dev.read(8192)}
            journal.save(saved)
            self.assertEqual(journal.path.stat().st_mode & 0o777, 0o600)
            dev.write(0, bytes(dev.block))
            with patch("capacidadreal.helper.emit"):
                journal.recover(dev)
            self.assertTrue(dev.restored())
            self.assertFalse(journal.path.exists())

    def test_bad_recovery_is_rejected_before_writes(self):
        dev = MemoryDevice()
        with tempfile.TemporaryDirectory() as directory:
            journal = Journal(device(), dev.block, Path(directory))
            journal.path.write_text(json.dumps({"identity": journal.identity, "block": dev.block,
                "blocks": {"0": base64.b64encode(dev.read(0)).decode(), "-4096": base64.b64encode(dev.read(0)).decode()}}))
            with self.assertRaises(ValueError):
                journal.recover(dev)
            self.assertEqual(dev.writes, 0)


if __name__ == "__main__":
    unittest.main()
