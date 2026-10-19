#!/bin/bash
set -euo pipefail
mkdir -p artifacts
export PYTHONPATH="$PWD/src"
python3 -m compileall -q src
python3 -m unittest discover -s tests -v 2>&1 | tee artifacts/pruebas.txt
bash packaging/build-deb.sh
dpkg-deb --info artifacts/capacidadreal_0.1.0_all.deb > artifacts/paquete.txt
dpkg-deb --contents artifacts/capacidadreal_0.1.0_all.deb >> artifacts/paquete.txt
dpkg -i artifacts/capacidadreal_0.1.0_all.deb
desktop-file-validate /usr/share/applications/io.github.babinium.capacidadReal.desktop
unset PYTHONPATH
xvfb-run -a dbus-run-session -- capacidadreal --screenshot "$PWD/artifacts/interfaz.png"
xvfb-run -a dbus-run-session -- capacidadreal --result --screenshot "$PWD/artifacts/resultado-ejemplo.png"
test -s artifacts/interfaz.png
test -s artifacts/resultado-ejemplo.png
python3 -I -c 'import sys; sys.path.insert(0,"/usr/lib/capacidadreal"); import capacidadreal.app, capacidadreal.helper; print("Importaciones instaladas: OK")'
if /usr/lib/capacidadreal/capacidadreal/helper.py scan /dev/null 67108864 test > artifacts/rechazo-dispositivo.txt; then
  echo 'ERROR: el ayudante aceptó un destino que no es USB'
  exit 1
fi
grep -q 'error' artifacts/rechazo-dispositivo.txt
printf 'Paquete Python Architecture: all. Sin extensiones nativas propias ni requisitos AVX.\nVerificado en Debian 13 amd64; dependencias GTK/Python de Debian.\n' > artifacts/compatibilidad.txt
