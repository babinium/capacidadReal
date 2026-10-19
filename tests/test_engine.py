import hashlib
import unittest

from capacidadreal.engine import Cancelled, positions, run


class MemoryDevice:
    block = 4096

    def __init__(self, size=64 * 1024 * 1024, real=None, wrap=False):
        self.size = size
        self.real = real if real is not None else size
        self.wrap = wrap
        self.data = {}
        self.writes = 0
        self.failed_once = False
        self.fail_write = None
        self.fail_read_after_writes = False
        self.fail_restore = False

    def physical(self, offset):
        if self.wrap:
            return offset % self.real
        return offset if offset < self.real else None

    def original(self, address):
        if address is None:
            return bytes(self.block)
        return hashlib.sha256(str(address).encode()).digest() * (self.block // 32)

    def read(self, offset):
        if self.fail_read_after_writes and self.writes and not self.failed_once:
            self.failed_once = True
            raise OSError("simulated read failure")
        address = self.physical(offset)
        return self.data.get(address, self.original(address))

    def write(self, offset, data):
        self.writes += 1
        address = self.physical(offset)
        if address is not None:
            if self.fail_restore and data == self.original(address):
                raise OSError("disconnected")
            self.data[address] = data
        if self.writes == self.fail_write:
            raise OSError("simulated partial write failure")

    def flush(self):
        pass

    def restored(self):
        return all(value == self.original(address) for address, value in self.data.items())


class MemoryJournal:
    saved = False
    cleared = False

    def save(self, originals):
        self.saved = True
        self.originals = dict(originals)

    def clear(self):
        self.cleared = True


class EngineTests(unittest.TestCase):
    def test_honest_and_restore(self):
        dev, journal = MemoryDevice(), MemoryJournal()
        result = run(dev, journal)
        self.assertEqual(result["status"], "compatible")
        self.assertTrue(dev.restored())
        self.assertTrue(journal.cleared)

    def test_dropped_storage_bounded_estimate(self):
        real = 8 * 1024 * 1024
        dev = MemoryDevice(real=real)
        result = run(dev, MemoryJournal())
        self.assertEqual(result["status"], "limited")
        self.assertLessEqual(result["estimated"], real)
        self.assertGreaterEqual(result["upper_bound"], real)
        self.assertTrue(dev.restored())

    def test_modulo_fraud_and_original_data(self):
        for real in (1024 * 1024, 8 * 1024 * 1024, 32 * 1024 * 1024):
            with self.subTest(real=real):
                dev = MemoryDevice(real=real, wrap=True)
                result = run(dev, MemoryJournal())
                self.assertEqual(result["status"], "aliased")
                self.assertEqual(result["estimated"], real)
                self.assertTrue(dev.restored())

    def test_failure_during_partial_write_restores(self):
        dev, journal = MemoryDevice(), MemoryJournal()
        dev.fail_write = 5
        with self.assertRaises(OSError):
            run(dev, journal)
        self.assertTrue(dev.restored())
        self.assertTrue(journal.cleared)

    def test_failure_reading_test_data_restores(self):
        dev, journal = MemoryDevice(), MemoryJournal()
        dev.fail_read_after_writes = True
        with self.assertRaises(OSError):
            run(dev, journal)
        self.assertTrue(dev.restored())
        self.assertTrue(journal.cleared)

    def test_cancel_after_writing_restores(self):
        dev, journal = MemoryDevice(), MemoryJournal()
        with self.assertRaises(Cancelled):
            run(dev, journal, cancelled=lambda: dev.writes > 10)
        self.assertTrue(dev.restored())
        self.assertTrue(journal.cleared)

    def test_cancel_before_write_never_changes_device(self):
        dev, journal = MemoryDevice(), MemoryJournal()
        with self.assertRaises(Cancelled):
            run(dev, journal, cancelled=lambda: True)
        self.assertEqual(dev.writes, 0)
        self.assertFalse(journal.saved)

    def test_recovery_failure_keeps_journal(self):
        dev, journal = MemoryDevice(), MemoryJournal()
        dev.fail_restore = True
        with self.assertRaisesRegex(OSError, "restauración"):
            run(dev, journal)
        self.assertTrue(journal.saved)
        self.assertFalse(journal.cleared)

    def test_sample_bounds_and_alignment(self):
        for size in (65536, 7_744_782_336, 2_000_000_000_000):
            probes, grid = positions(size)
            self.assertLess(len(probes), 800)
            self.assertEqual(len(probes), len(set(probes)))
            self.assertTrue(all(p % 4096 == 0 and 0 <= p <= size - 4096 for p in probes))
            self.assertTrue(set(grid).issubset(probes))


if __name__ == "__main__":
    unittest.main()
