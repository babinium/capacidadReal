#!/usr/bin/python3 -I
"""Privileged worker: whole, unmounted USB disks or removable native SD cards."""
import base64
import fcntl
import hashlib
import json
import mmap
import os
from pathlib import Path
import signal
import stat
import struct
import sys
import tempfile
import threading

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from capacidadreal.devices import inventory, validate
from capacidadreal.engine import Cancelled, MAX_WRITE_BYTES, run

STOP = threading.Event()


def emit(event):
    try:
        print(json.dumps(event, ensure_ascii=False), flush=True)
    except (BrokenPipeError, OSError):
        STOP.set()


class RawDevice:
    def __init__(self, item):
        self.fd = os.open(item["name"], os.O_RDWR | os.O_EXCL | os.O_CLOEXEC | os.O_DIRECT)
        try:
            info = os.fstat(self.fd)
            number = f"{os.major(info.st_rdev)}:{os.minor(info.st_rdev)}"
            if not stat.S_ISBLK(info.st_mode) or number != item["maj:min"]:
                raise ValueError("La identidad del dispositivo cambió al abrirlo.")
            self.size = struct.unpack("Q", fcntl.ioctl(self.fd, 0x80081272, bytes(8)))[0]
            logical = struct.unpack("I", fcntl.ioctl(self.fd, 0x1268, bytes(4)))[0]
            self.block = max(4096, logical)
            if self.size != item["size"] or self.block > 65536:
                raise ValueError("La geometría del dispositivo cambió o no es compatible.")
            self.buffer = mmap.mmap(-1, MAX_WRITE_BYTES)
        except BaseException:
            os.close(self.fd)
            raise

    def read(self, offset):
        with memoryview(self.buffer) as view:
            got = os.preadv(self.fd, [view[:self.block]], offset)
        if got != self.block:
            raise OSError("Lectura incompleta del dispositivo.")
        return self.buffer[:self.block]

    def write(self, offset, data):
        if (not data or len(data) % self.block or len(data) > MAX_WRITE_BYTES
                or offset % self.block or offset < 0 or offset + len(data) > self.size):
            raise ValueError("Bloque de prueba inválido.")
        self.buffer[:len(data)] = data
        with memoryview(self.buffer) as view:
            written = os.pwritev(self.fd, [view[:len(data)]], offset)
        if written != len(data):
            raise OSError("Escritura incompleta del dispositivo.")

    def flush(self):
        os.fsync(self.fd)
        fcntl.ioctl(self.fd, 0x1261)  # BLKFLSBUF: invalidate Linux block cache.

    def close(self):
        self.buffer.close()
        os.close(self.fd)


class Journal:
    def __init__(self, item, block, root=Path("/var/lib/capacidadreal")):
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.identity = {k: item.get(k) for k in ("serial", "model", "size")}
        key = hashlib.sha256(json.dumps(self.identity, sort_keys=True).encode()).hexdigest()
        self.path = root / (key + ".json")
        self.block = block

    def save(self, originals):
        payload = {"identity": self.identity, "block": self.block,
                   "blocks": {str(p): base64.b64encode(b).decode() for p, b in originals.items()}}
        fd, temp_name = tempfile.mkstemp(prefix="backup-", suffix=".tmp", dir=self.path.parent)
        temp = Path(temp_name)
        try:
            with os.fdopen(fd, "w") as handle:
                json.dump(payload, handle)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, self.path)
            self._sync_dir()
        finally:
            temp.unlink(missing_ok=True)

    def _sync_dir(self):
        fd = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def clear(self):
        self.path.unlink(missing_ok=True)
        self._sync_dir()

    def recover(self, device):
        if self.path.stat().st_size > 80 * 1024 * 1024:
            raise ValueError("El archivo de recuperación tiene un tamaño inválido.")
        payload = json.loads(self.path.read_text())
        if payload["identity"] != self.identity or payload["block"] != self.block:
            raise ValueError("La copia de recuperación no corresponde a esta unidad.")
        blocks = {}
        for pos, encoded in payload["blocks"].items():
            offset = int(pos)
            data = base64.b64decode(encoded, validate=True)
            if offset < 0 or offset % device.block or offset + device.block > device.size or len(data) != device.block:
                raise ValueError("La copia de recuperación contiene bloques inválidos.")
            blocks[offset] = data
        for index, (offset, data) in enumerate(blocks.items()):
            device.write(offset, data)
            emit({"type": "progress", "phase": "restoring", "done": index + 1, "total": len(blocks)})
        device.flush()
        if any(device.read(p) != b for p, b in blocks.items()):
            raise OSError("No se pudo verificar la restauración. La copia se conserva.")
        self.clear()


def listen():
    # EOF means the GUI disappeared: stop probing and recover, never kill mid-write.
    try:
        sys.stdin.readline()
    finally:
        STOP.set()


def main():
    if os.geteuid() != 0:
        emit({"type": "error", "message": "Se necesitan permisos de administrador para comprobar el USB."})
        return 1
    if len(sys.argv) != 5 or sys.argv[1] not in ("scan", "recover"):
        return 2
    _, action, requested, size, serial = sys.argv
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, lambda *_: STOP.set())
    device = None
    try:
        target = os.path.realpath(requested)
        item = next((d for d in inventory() if d["name"] == target), None)
        if item is None:
            raise ValueError("El pendrive ya no está conectado.")
        validate(item, int(size), serial)
        device = RawDevice(item)
        journal = Journal(item, device.block)
        if journal.path.exists():
            if action != "recover":
                emit({"type": "recovery_needed"})
                return 3
            journal.recover(device)
            emit({"type": "recovered"})
            return 0
        if action == "recover":
            raise ValueError("No hay una recuperación pendiente para este dispositivo.")
        threading.Thread(target=listen, daemon=True).start()
        run(device, journal, emit, STOP.is_set)
        return 0
    except Cancelled:
        emit({"type": "cancelled", "restored": True})
        return 0
    except Exception as exc:
        emit({"type": "error", "message": str(exc)})
        return 1
    finally:
        if device:
            device.close()


if __name__ == "__main__":
    sys.exit(main())
