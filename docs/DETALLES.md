# Detalles técnicos y límites

## Qué comprueba y qué significa el resultado

Se prueban 64 posiciones distribuidas por el espacio anunciado, más pares de
direcciones separados por potencias de dos con anclas 0, 1 y 7 para descubrir
controladores que reutilizan memoria. Son 128 muestras de 4 KiB en la geometría
de 15.728.640.000 bytes y 149 en la simulación de 2 TB. La rejilla de la interfaz
muestra únicamente las posiciones distribuidas. La reducción frente a 576
posiciones más anclas prioriza la rapidez; reduce la cobertura de defectos
localizados y la precisión del intervalo observado en una transición.

Todos los originales se leen y se guardan antes de escribir. Después se escriben
patrones distintos en orden ascendente, se sincroniza y se leen en orden aleatorio.
Se utiliza E/S directa y se invalida la caché del kernel. Finalmente se restauran
las direcciones cuya escritura se intentó, incluidas las escrituras parciales,
y se vuelven a leer **todas** las muestras originales guardadas. No se escriben
muestras aún no intentadas al cancelar. Las direcciones que se repiten en el
modelo de fraude modular comparten el mismo original; también se verifican
las muestras que puedan coincidir con ellas.

## Rapidez y unidades lentas (0.2.5)

Se agrupan solo muestras estrictamente contiguas, hasta 128 KiB; nunca se
escriben los huecos entre muestras. En la geometría de 15.728.640.000 bytes,
las escrituras de prueba más restauración pasan de 1228 (0.2.3) a 204 si la
prueba termina normalmente. Se informa el número de comandos calculado,
no una aceleración en segundos: aún no hay una medición comparativa en hardware.

La prueba no tiene un límite automático de tiempo por operación ni de duración
total. La versión 0.2.5 elimina los cortes de 2 y 15 segundos introducidos en
0.2.4: la lentitud por sí sola no impide completar la comprobación. El motor
continúa hasta completar las muestras, recibir cancelación o encontrar un
error real. La interfaz muestra la espera mientras Linux procesa una operación;
cuando llega la respuesta, continúa mostrando el avance normal.

Al cancelar, se espera que la operación pendiente devuelva el control y se
restauran solo los lotes cuya escritura se intentó. Se verifican todos los
originales guardados. Si falla un lote durante la restauración, se reintenta
cada bloque por separado y se conserva la copia si no se confirma la recuperación.
La recuperación acepta las copias de versiones anteriores: lee cada original
guardado y solo lo reescribe si difiere, para no repetir cientos de escrituras
innecesarias en una unidad lenta. El aviso para retirar se muestra únicamente
tras la restauración verificada o cuando no hubo escrituras.

Todas las muestras quedan escritas simultáneamente antes de verificarlas para
seguir detectando direcciones que reutilizan la misma memoria. Se mantienen
la sincronización, E/S directa y la lectura posterior de originales.

## Resultados

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

Python 3 + GTK 3; sin Electron, sin servicios permanentes y sin compilación local
necesaria para usarlo. El ayudante privilegiado acepta únicamente operaciones
de comprobación y recuperación sobre un disco USB o una tarjeta SD extraíble validados. La interfaz corre
como usuario normal. El paquete usa dependencias de Debian y arquitectura `all`;
se comprueba en Debian 13 amd64, sin requisitos AVX propios.

El workflow manual `.github/workflows/compilar-debian.yml` ejecuta pruebas del
motor y de seguridad, construye e instala el `.deb` en Debian 13 y captura la
interfaz con Xvfb usando una unidad ficticia. Los artefactos incluyen el paquete,
capturas, pruebas y comprobantes SHA-256. No se hacen pruebas sobre discos reales
desde CI. La compilación no publica releases ni cambia la visibilidad del repo.

Para desarrollar: `PYTHONPATH=src python3 -m capacidadreal.app --demo`.
Para probar: `PYTHONPATH=src python3 -m unittest discover -s tests -v`.
Para empaquetar en el entorno de compilación: `bash packaging/build-deb.sh`.

Versión actual: **0.2.7**. Licencia MIT.
