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


MAX_WRITE_BYTES = 128 * 1024
GRID_SAMPLES = 64


def write_batches(offsets, block):
    """Join adjacent samples only: never write the gaps between samples."""
    batch = []
    for offset in offsets:
        if batch and (offset != batch[-1] + block or
                      (len(batch) + 1) * block > MAX_WRITE_BYTES):
            yield batch
            batch = []
        batch.append(offset)
    if batch:
        yield batch


def positions(size, block=4096, count=GRID_SAMPLES):
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
    # Full-length pseudorandom data avoids trivially compressible repetition.
    return hashlib.shake_256(nonce + offset.to_bytes(8, "big")).digest(block)


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


def run(device, journal, emit=lambda event: None, cancelled=lambda: False,
        clock=time.monotonic):
    start = clock()
    offsets, grid = positions(device.size, device.block)
    nonce = os.urandom(32)
    originals = {}
    checks = {}
    aliases = []
    attempted = []
    scan_error = None
    restoration_errors = []

    def progress(phase, index, total):
        emit({"type": "progress", "phase": phase, "done": index, "total": total})

    def check_cancelled():
        if cancelled():
            raise Cancelled()

    # Failure/cancellation here cannot alter the device.
    progress("saving", 0, len(offsets))
    for i, offset in enumerate(offsets):
        check_cancelled()
        originals[offset] = device.read(offset)
        progress("saving", i + 1, len(offsets))
        check_cancelled()
    journal.save(originals)
    expected = {p: pattern(p, device.block, nonce) for p in offsets}
    reverse = {value: key for key, value in expected.items()}
    batches = list(write_batches(offsets, device.block))
    try:
        done = 0
        progress("writing", 0, len(offsets))
        for batch in batches:
            check_cancelled()
            # Record BEFORE issuing I/O: partial writes also need recovery.
            attempted.append(batch)
            device.write(batch[0], b"".join(expected[p] for p in batch))
            done += len(batch)
            progress("writing", done, len(offsets))
            check_cancelled()
        device.flush()
        check_cancelled()
        # All distinct patterns remain on the medium together, so aliases
        # still collide even though writes now follow ascending addresses.
        order = offsets.copy()
        random.SystemRandom().shuffle(order)
        progress("checking", 0, len(offsets))
        for i, offset in enumerate(order):
            check_cancelled()
            actual = device.read(offset)
            checks[offset] = "ok" if actual == expected[offset] else "mismatch"
            if actual != expected[offset] and actual in reverse:
                aliases.append((offset, reverse[actual]))
            progress("checking", i + 1, len(offsets))
            check_cancelled()
    except Exception as exc:
        scan_error = exc
    finally:
        if attempted:
            # Ignore cancellation during recovery. Restore every
            # attempted address, including partial writes. Aliases return the
            # same original; verify ALL saved samples afterward as well.
            done = 0
            restore_total = sum(len(batch) for batch in attempted)
            progress("restoring", 0, restore_total)
            for batch in attempted:
                try:
                    device.write(batch[0], b"".join(originals[p] for p in batch))
                except Exception:
                    # A partial batch must not prevent the remaining originals
                    # from being restored. Retry each constituent sample once.
                    for offset in batch:
                        try:
                            device.write(offset, originals[offset])
                        except Exception:
                            restoration_errors.append(offset)
                done += len(batch)
                progress("restoring", done, restore_total)
            try:
                device.flush()
                progress("verifying_restore", 0, len(offsets))
                for i, offset in enumerate(offsets):
                    if device.read(offset) != originals[offset]:
                        restoration_errors.append(offset)
                    progress("verifying_restore", i + 1, len(offsets))
            except Exception:
                restoration_errors.append(-1)
        if not restoration_errors:
            journal.clear()
    if restoration_errors:
        raise OSError("No se pudo confirmar la restauración. Se conservó la copia de recuperación. No uses la unidad hasta recuperarla.")
    if scan_error:
        raise scan_error
    result = summarize(device.size, device.block, grid, checks, aliases)
    result.update(type="result", elapsed=round(clock() - start, 1), restored=True)
    emit(result)
    return result
