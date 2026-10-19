import json
import os
from pathlib import Path
import re
import subprocess


def inventory():
    raw = subprocess.check_output([
        "/usr/bin/lsblk", "--json", "--bytes", "--paths", "--output",
        "NAME,TYPE,SIZE,MODEL,SERIAL,TRAN,RO,RM,MOUNTPOINTS,MAJ:MIN"], text=True)
    return [identify(item) for item in json.loads(raw)["blockdevices"]]


def identify(item, sysfs=Path("/sys/class/block")):
    item = dict(item)
    item["native_sd"] = False
    # Keep the raw USB identity stable for recovery files from earlier versions.
    # Only the displayed/copyable value is normalized by serial_details().
    item["serial"] = item.get("serial")
    item["serial_source"] = "usb" if item.get("tran") == "usb" else "unknown"
    name = os.path.basename(item["name"])
    if re.fullmatch(r"mmcblk\d+", name):
        try:
            card_type = (sysfs / name / "device/type").read_text().strip()
        except OSError:
            card_type = ""
        # eMMC is embedded storage: never widen the supported targets to it.
        if card_type == "SD" and item.get("rm"):
            item["native_sd"] = True
            item["serial_source"] = "sd"
            try:
                item["serial"] = (sysfs / name / "device/serial").read_text().strip()
            except OSError:
                pass
    return item


def serial_details(item):
    serial = (item.get("serial") or "").strip()
    if not serial:
        return "No disponible", "La unidad o su lector no informa un número de serie.", False
    if item.get("serial_source") == "sd":
        return serial, "Número de serie de la tarjeta SD, informado por Linux.", True
    return serial, "Serie informada por USB. En tarjetas SD puede corresponder al lector, no a la tarjeta.", True


def descendants(item):
    yield item
    for child in item.get("children", []):
        yield from descendants(child)


def usable(item):
    return (item.get("type") == "disk" and not item.get("ro")
            and (item.get("tran") == "usb" or item.get("native_sd") is True))


def validate(item, expected_size, expected_serial):
    if not usable(item) or int(item.get("size") or 0) != expected_size:
        raise ValueError("La unidad cambió o no es un USB o una tarjeta SD extraíble compatible.")
    if (item.get("serial") or "") != expected_serial:
        raise ValueError("La identidad del dispositivo cambió.")
    if expected_size < 65536:
        raise ValueError("El USB no informa una capacidad utilizable.")
    for node in descendants(item):
        if any(node.get("mountpoints") or []):
            raise ValueError("La unidad está montada o en uso. Cerrá sus archivos y volvé a intentar.")
        name = os.path.basename(node["name"])
        holder = f"/sys/class/block/{name}/holders"
        if os.path.isdir(holder) and os.listdir(holder):
            raise ValueError("La unidad está siendo utilizada por otro dispositivo.")


def human_size(value):
    return f"{value / 1_000_000_000:.2f} GB" if value >= 1_000_000_000 else f"{value / 1_000_000:.1f} MB"
