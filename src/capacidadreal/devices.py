import json
import os
import subprocess


def inventory():
    raw = subprocess.check_output([
        "/usr/bin/lsblk", "--json", "--bytes", "--paths", "--output",
        "NAME,TYPE,SIZE,MODEL,SERIAL,TRAN,RO,RM,MOUNTPOINTS,MAJ:MIN"], text=True)
    return json.loads(raw)["blockdevices"]


def descendants(item):
    yield item
    for child in item.get("children", []):
        yield from descendants(child)


def usable(item):
    return item.get("type") == "disk" and item.get("tran") == "usb" and not item.get("ro")


def validate(item, expected_size, expected_serial):
    if not usable(item) or int(item.get("size") or 0) != expected_size:
        raise ValueError("La unidad cambió o no es un disco USB escribible.")
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
