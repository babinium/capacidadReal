"""Pure test engine. All original blocks are saved BEFORE any write.

This is a bounded spot check, not a full media certification. It detects missing
storage and common wraparound controllers; an arbitrary dishonest controller or
a cache large enough to retain every sample can evade it.
"""
import hashlib
import math
import os
import random
import time


class Cancelled(Exception):
    pass


def positions(size, block=4096, count=576):
    blocks = size // block
    if blocks < 16:
        raise ValueError("La unidad es demasiado pequeña para esta prueba.")
    grid = sorted({i * (blocks - 1) // (count - 1) for i in range(count)})
    # Paired anchors separated by powers of two expose common modulo-address
    # fraud, which a regular grid alone can completely miss.
    probes = set(grid)
    distance = 1
    while distance < blocks:
        for anchor in (0, 1, 7):
            if anchor + distance < blocks:
                probes.update((anchor, anchor + distance))
        distance *= 2
    return sorted(p * block for p in probes), [p * block for p in grid]


def pattern(offset, block, nonce):
    digest = hashlib.blake2b(nonce + offset.to_bytes(8, "big")).digest()
    return (digest * ((block + 63) // 64))[:block]


def summarize(size, block, grid, checks, aliases):
    good = [p for p in grid if checks.get(p) == "ok"]
    bad = [p for p in grid if checks.get(p) != "ok"]
    result = {"announced": size, "samples": len(checks),
              "passed": sum(v == "ok" for v in checks.values()),
              "grid": [checks.get(p, "error") for p in grid],
              "estimated": None, "upper_bound": None,
              "status": "compatible" if all(v == "ok" for v in checks.values()) else "inconclusive"}
    if aliases:
        period = math.gcd(*(abs(a - b) for a, b in aliases))
        if block <= period < size:
            result.update(status="aliased", estimated=period)
    elif bad and good and max(good) < min(bad):
        # An initial valid prefix followed by missing samples. This only bounds
        # the transition observed by this test; it is not a sector-accurate size.
        result.update(status="limited", estimated=max(good) + block,
                      upper_bound=min(bad))
    return result


def run(device, journal, emit=lambda event: None, cancelled=lambda: False):
    start = time.monotonic()
    offsets, grid = positions(device.size, device.block)
    nonce = os.urandom(32)
    originals = {}
    checks = {}
    aliases = []
    dirty = False
    scan_error = None
    restoration_errors = []

    def progress(phase, index, total):
        emit({"type": "progress", "phase": phase, "done": index, "total": total})

    # Failure/cancellation here cannot alter the device.
    for i, offset in enumerate(offsets):
        if cancelled():
            raise Cancelled()
        originals[offset] = device.read(offset)
        progress("saving", i + 1, len(offsets))
    journal.save(originals)
    expected = {p: pattern(p, device.block, nonce) for p in offsets}
    reverse = {value: key for key, value in expected.items()}
    order = offsets.copy()
    random.SystemRandom().shuffle(order)
    try:
        for i, offset in enumerate(order):
            if cancelled():
                raise Cancelled()
            dirty = True  # Include partially failed writes in recovery.
            device.write(offset, expected[offset])
            progress("writing", i + 1, len(offsets))
        device.flush()
        random.SystemRandom().shuffle(order)
        for i, offset in enumerate(order):
            if cancelled():
                raise Cancelled()
            actual = device.read(offset)
            checks[offset] = "ok" if actual == expected[offset] else "mismatch"
            if actual != expected[offset] and actual in reverse:
                aliases.append((offset, reverse[actual]))
            progress("checking", i + 1, len(offsets))
    except Exception as exc:
        scan_error = exc
    finally:
        if dirty:
            # Ignore cancellation during recovery. Every potentially touched
            # address is restored, including addresses aliased by fake firmware.
            for i, offset in enumerate(offsets):
                try:
                    device.write(offset, originals[offset])
                except Exception:
                    restoration_errors.append(offset)
                progress("restoring", i + 1, len(offsets))
            try:
                device.flush()
                for offset in offsets:
                    if device.read(offset) != originals[offset]:
                        restoration_errors.append(offset)
            except Exception:
                restoration_errors.append(-1)
        if not restoration_errors:
            journal.clear()
    if restoration_errors:
        raise OSError("No se pudo confirmar la restauración. Se conservó la copia de recuperación. No uses la unidad hasta recuperarla.")
    if scan_error:
        raise scan_error
    result = summarize(device.size, device.block, grid, checks, aliases)
    result.update(type="result", elapsed=round(time.monotonic() - start, 1), restored=True)
    emit(result)
    return result
