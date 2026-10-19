import hashlib
import unittest

from capacidadreal.engine import Cancelled, pattern, positions, run


class MemoryDevice:
    block = 4096

    def __init__(self, size=64 * 1024 * 1024, real=None, wrap=False):
        self.size = size
        self.real = real if real is not None else size
        self.wrap = wrap
        self.data = {}
        self.writes = 0
        self.write_spans = []
        self.reads = 0
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
        self.reads += 1
        if self.fail_read_after_writes and self.writes and not self.failed_once:
            self.failed_once = True
            raise OSError("simulated read failure")
        address = self.physical(offset)
        return self.data.get(address, self.original(address))

    def write(self, offset, data):
        self.writes += 1
        self.write_spans.append((offset, len(data)))
        for start in range(0, len(data), self.block):
            address = self.physical(offset + start)
            value = data[start:start + self.block]
            if address is not None:
                if self.fail_restore and value == self.original(address):
                    raise OSError("disconnected")
                self.data[address] = value
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
    def test_large_drive_still_uses_a_small_bounded_sample(self):
        dev = MemoryDevice(size=2_000_000_000_000)
        result = run(dev, MemoryJournal())
        self.assertEqual(result["status"], "compatible")
        self.assertLess(result["samples"], 800)
        self.assertLess(dev.writes * dev.block, 7 * 1024 * 1024)
        self.assertLess(dev.reads * dev.block, 10 * 1024 * 1024)
        self.assertTrue(dev.restored())

    def test_writes_are_ordered_and_coalesced_without_changing_coverage(self):
        dev = MemoryDevice(size=15_728_640_000)
        result = run(dev, MemoryJournal())
        probes, grid = positions(dev.size)
        self.assertEqual(result["samples"], len(probes))
        self.assertEqual(len(result["grid"]), len(grid))
        # Each sampled byte is written once for the test and once to restore.
        # Contiguous samples share a command; gaps must never be overwritten.
        half = len(dev.write_spans) // 2
        for phase in (dev.write_spans[:half], dev.write_spans[half:]):
            covered = [offset + i for offset, length in phase
                       for i in range(0, length, dev.block)]
            self.assertEqual(covered, probes)
            self.assertLess(len(phase), len(probes))
            self.assertTrue(all(length <= 128 * 1024 for _, length in phase))
        self.assertTrue(dev.restored())

    def test_partial_batch_failure_restores_and_does_not_touch_gaps(self):
        class PartialDevice(MemoryDevice):
            def write(self, offset, data):
                if len(data) > self.block and not self.failed_once:
                    self.failed_once = True
                    super().write(offset, data[:self.block])
                    raise OSError("partial batch")
                super().write(offset, data)
        dev, journal = PartialDevice(), MemoryJournal()
        with self.assertRaisesRegex(OSError, "partial batch"):
            run(dev, journal)
        self.assertTrue(dev.failed_once)
        self.assertTrue(dev.restored())
        self.assertTrue(journal.cleared)
        probes, _ = positions(dev.size)
        self.assertTrue(set(dev.data).issubset(probes))

    def test_patterns_are_distinct_and_not_repeated_short_chunks(self):
        data = pattern(0, 4096, b"test nonce")
        self.assertEqual(len(data), 4096)
        self.assertEqual(len({data[i:i + 64] for i in range(0, 4096, 64)}), 64)
        self.assertNotEqual(data, pattern(4096, 4096, b"test nonce"))
        self.assertNotEqual(data, pattern(0, 4096, b"different nonce"))

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
        for real in (4096, 8192, 16384, 65536, 1024 * 1024, 8 * 1024 * 1024, 32 * 1024 * 1024):
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

    def test_failed_batch_restore_retries_each_original(self):
        class RestoreDevice(MemoryDevice):
            def write(self, offset, data):
                if (len(data) > self.block and not self.failed_once
                        and data[:self.block] == self.original(offset)):
                    self.failed_once = True
                    super().write(offset, data[:self.block])
                    raise OSError("partial restoration")
                super().write(offset, data)
        dev, journal = RestoreDevice(), MemoryJournal()
        run(dev, journal)
        self.assertTrue(dev.failed_once)
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
