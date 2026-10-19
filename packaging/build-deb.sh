#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
stage=build/package
mkdir -p "$stage/DEBIAN" "$stage/usr/lib/capacidadreal/capacidadreal" "$stage/usr/bin"
mkdir -p "$stage/usr/share/applications" "$stage/usr/share/polkit-1/actions"
mkdir -p "$stage/usr/share/icons/hicolor/scalable/apps" "$stage/usr/share/doc/capacidadreal"
install -m 644 packaging/control "$stage/DEBIAN/control"
install -m 644 src/capacidadreal/*.py "$stage/usr/lib/capacidadreal/capacidadreal/"
chmod 755 "$stage/usr/lib/capacidadreal/capacidadreal/helper.py"
install -m 755 packaging/capacidadreal "$stage/usr/bin/capacidadreal"
install -m 644 packaging/*.desktop "$stage/usr/share/applications/"
install -m 644 packaging/*.policy "$stage/usr/share/polkit-1/actions/"
install -m 644 packaging/*.svg "$stage/usr/share/icons/hicolor/scalable/apps/"
install -m 644 README.md "$stage/usr/share/doc/capacidadreal/README.md"
mkdir -p "$stage/usr/share/doc/capacidadreal/docs"
install -m 644 docs/DETALLES.md "$stage/usr/share/doc/capacidadreal/docs/DETALLES.md"
install -m 644 LICENSE "$stage/usr/share/doc/capacidadreal/copyright"
mkdir -p artifacts
dpkg-deb --root-owner-group --build "$stage" artifacts/capacidadreal_0.2.5_all.deb
