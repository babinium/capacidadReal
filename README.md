# capacidadReal

**capacidadReal detecta memorias USB y tarjetas que anuncian más capacidad de la
que realmente tienen.** Es una aplicación gráfica liviana, en español, para Linux,
con interfaz oscura.

Las unidades falsificadas o de mala calidad son frecuentes: el sistema muestra,
por ejemplo, 64 GB, pero la memoria real puede ser de solo 8 GB. Al copiar
archivos grandes, estos se corrompen o desaparecen sin aviso. capacidadReal hace
una prueba rápida por muestreo: escribe, lee y restaura unos cientos de bloques
para descubrir si el controlador repite direcciones o si el espacio anunciado no
existe.

Sirve para revisar un pendrive recién comprado, una unidad usada o una memoria
de dudosa procedencia antes de confiarle datos. Inspirada en la sencillez de
ValiDrive; implementación independiente, sin relación con GRC. No ejecuta F3.

> **La prueba escribe en el dispositivo**, aunque después restaura los bloques
> originales. Usá una unidad vacía o conservá una copia de los archivos
> importantes. Leé «Cuidado de datos y recuperación» antes de empezar.

## Descarga e instalación

El paquete `.deb` se publica en la sección **Releases** de este repositorio.
También podés generarlo vos mismo con `bash packaging/build-deb.sh`.

Requisitos: Linux con GTK 3 y Python 3.11 o posterior, UDisks2 y Polkit
(`pkexec`), o `sudo` como alternativa. Se comprueba en Debian 13 amd64 y está
pensado para Debian y derivados como Ubuntu.

1. Descargá `capacidadreal_0.2.0_all.deb` desde Releases y abrilo con el
   instalador de paquetes de tu escritorio.
   Si tu escritorio no tiene uno: `sudo apt install ./capacidadreal_0.2.0_all.deb`.
2. Abrí **capacidadReal** en el menú de aplicaciones.
3. Seleccioná el pendrive y pulsá **Comprobar capacidad**.
4. Autorizá el acceso de administrador cuando Linux lo solicite.
5. Esperá el resultado y la restauración de los bloques antes de desconectarlo.

La aplicación desmonta las particiones con UDisks y rechaza discos internos,
particiones montadas, swap y dispositivos en uso. La unidad queda desmontada
al terminar; podés abrirla de nuevo desde el administrador de archivos.
En escritorios sin agente de Polkit (por ejemplo, algunas instalaciones de i3),
la autorización se solicita en un diálogo GTK y se envía a `sudo` por una tubería.
Las contraseñas no se guardan ni forman parte del paquete o del repositorio.

## Qué comprueba y qué significa el resultado

Se prueban 576 posiciones distribuidas por el espacio anunciado, más pares de
direcciones separadas por potencias de dos para descubrir controladores que
reutilizan la misma memoria. Son aproximadamente 600–750 bloques de 4 KiB en
unidades habituales. El volumen de datos probado es pequeño y acotado; la
duración depende especialmente de la latencia y del estado del USB. No se promete
un tiempo máximo: el kernel puede esperar a un dispositivo que falla.

Todos los originales se leen y se guardan antes de escribir. Después se escriben
patrones distintos, se sincroniza y se leen en otro orden. Se utiliza E/S directa
y se invalida la caché del kernel. Finalmente se restauran y se vuelven a leer los
originales. La salida solo indica restauración correcta si esa lectura coincide.

- **Capacidad compatible:** todas las muestras pasan; no se detectó capacidad falsa.
- **Capacidad falsa detectada:** direcciones distintas devuelven el patrón escrito
  en otra dirección. Se estima el período de repetición mediante sus diferencias.
  Este período no certifica que toda esa cantidad de memoria esté sana.
- **El espacio anunciado no se verifica:** las muestras iniciales pasan y las
  posteriores fallan. Se muestra el intervalo de transición observado, sin
  confundir una estimación con una capacidad exacta al sector.
- **Datos incorrectos / sin resultado:** no se puede determinar una capacidad
  útil confiable. Un fallo físico también puede causar diferencias.

**Límite fundamental:** una prueba por muestreo no verifica cada sector. Un
controlador que conserve todas las muestras en una caché persistente, una
traducción de direcciones no cubierta por los pares, o daños entre muestras
pueden pasar inadvertidos. Para una certificación completa se necesita escribir
y leer todo el espacio (por ejemplo, F3 sobre una unidad vacía). Este programa
prioriza la prueba rápida solicitada y muestra explícitamente ese alcance.

## Cuidado de datos y recuperación

La prueba **escribe en el dispositivo**, aunque restaura los bloques originales.
Usá una unidad vacía o conservá una copia de los archivos importantes. Un fallo
eléctrico, desconexión, memoria defectuosa o controlador engañoso puede impedir
la restauración. Esta aplicación inicial se prueba automáticamente con unidades
simuladas; aún necesita validación adicional con hardware diverso.

Antes de la primera escritura se sincroniza una copia de los bloques originales
en `/var/lib/capacidadreal/`, accesible solo para root. Se elimina solo tras
restaurar y verificar. Cancelar solicita recuperación; no mata el proceso.
Si desaparece la interfaz, el ayudante deja de probar y restaura. Si se corta
la energía o desaparece el USB, la copia permanece: al volver a seleccionar
la misma unidad, la aplicación ofrece recuperar los bloques antes de otra prueba.
No escribas archivos nuevos mientras haya una recuperación pendiente. Verificá
que sea el mismo dispositivo: algunos USB no tienen número de serie único.

## Desarrollo y paquete

Python 3 + GTK 3; sin Electron, sin servicios permanentes y sin compilación
necesaria para usarlo. El ayudante privilegiado acepta únicamente operaciones
de comprobación y recuperación sobre un disco USB validado. La interfaz corre
como usuario normal. El paquete usa dependencias de Debian y arquitectura `all`;
se comprueba en Debian 13 amd64, incluido el destino Celeron B820 sin AVX.

El workflow manual `.github/workflows/compilar-debian.yml` ejecuta pruebas del
motor y de seguridad, construye e instala el `.deb` en Debian 13 y captura la
interfaz con Xvfb usando una unidad ficticia. Los artefactos incluyen el paquete,
capturas, pruebas y comprobantes SHA-256. No se hacen pruebas sobre discos reales
desde CI. El workflow no publica releases automáticamente.

Para desarrollar: `PYTHONPATH=src python3 -m capacidadreal.app --demo`.
Para probar: `PYTHONPATH=src python3 -m unittest discover -s tests -v`.
Para empaquetar en el entorno de compilación: `bash packaging/build-deb.sh`.

Versión actual: **0.2.0**. Licencia MIT.
