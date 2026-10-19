import base64
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from capacidadreal.devices import validate
from capacidadreal.helper import Journal
from test_engine import MemoryDevice


def device(**overrides):
    value = {"name": "/dev/test", "type": "disk", "tran": "usb", "ro": False,
             "size": 64 * 1024 * 1024, "serial": "test", "model": "test", "mountpoints": [None]}
    value.update(overrides)
    return value


class SafetyTests(unittest.TestCase):
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
