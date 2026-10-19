# capacidadReal

**Comprobá rápido si tu pendrive o tarjeta SD tiene el espacio que promete.**

capacidadReal es una aplicación para Linux con una ventana sencilla, en modo oscuro: elegís la
memoria, pulsás **Comprobar capacidad** y ves el resultado. También muestra el
número de serie, cuando está disponible, y permite copiarlo.

## ¿Qué problema resuelve?

Algunas memorias falsificadas anuncian más espacio del que realmente tienen.
Por ejemplo, un pendrive puede aparecer como de **256 GB** en la computadora
aunque solo tenga **32 GB**. Al superar su capacidad real, los archivos pueden
perderse o sobrescribirse sin que el sistema lo advierta claramente.

Esta aplicación busca detectar ese engaño antes de que confíes tus archivos
importantes a la memoria. Si encuentra espacio que no guarda los datos o zonas
que se repiten, lo indica y muestra una estimación cuando es posible.

## Una comprobación rápida

La prioridad del proyecto es **una única función: comprobar rápidamente la
capacidad por muestreo, desde una interfaz gráfica**.

El programa prueba pequeñas zonas repartidas por toda la capacidad anunciada.
En memorias habituales, esas zonas suman aproximadamente **2–3 MB**. No llena
el pendrive ni lee todos sus gigabytes. El tiempo real depende de la velocidad
y del estado de la memoria; todavía no publicamos tiempos medidos en hardware.

Desde la versión 0.2.3, las escrituras siguen un orden y agrupan zonas contiguas
para reducir operaciones en pendrives. Se comprueban las mismas muestras y se
verifica la restauración. Esto no elimina las esperas de una memoria que deja
de responder; la mejora de tiempo depende del dispositivo.

### ¿Qué significa «restaurar los datos»?

Para saber si una zona guarda información de verdad, hay que escribir algo y
leerlo después. El programa hace lo siguiente:

1. Guarda lo que había en las pequeñas zonas que va a probar.
2. Escribe datos de prueba y comprueba que se puedan leer correctamente.
3. Vuelve a colocar los datos originales **solo en esas mismas zonas** y verifica
   que quedaron como estaban.

Esto no es una copia ni una restauración de todo el pendrive. Las pruebas
automáticas del desarrollo usan, además, un archivo temporal para comprobar
que el programa restaura correctamente lo que modifica; ese archivo no es tu USB.

## Descargar e instalar

**[Descargar el instalador .deb 0.2.3](https://github.com/babinium/capacidadReal/releases/download/v0.2.3/capacidadreal_0.2.3_all.deb)**
· [Página de la versión](https://github.com/babinium/capacidadReal/releases/tag/v0.2.3)

Probado en **Debian 13 con entorno gráfico**. Otras distribuciones basadas en
Debian pueden funcionar si tienen las dependencias necesarias; no se han verificado.

1. Abrí el `.deb` con el instalador de paquetes de tu escritorio.
2. Buscá **capacidadReal** en el menú de aplicaciones.
3. Conectá y elegí el pendrive o la tarjeta SD.
4. Pulsá **Comprobar capacidad** y autorizá los permisos de Linux.
5. Esperá el aviso verde **«Dispositivo listo para desenchufar»** antes de
   desconectar la memoria.

Si tu escritorio no tiene instalador gráfico, abrí una terminal en la carpeta
donde descargaste el archivo y ejecutá:

```bash
sudo apt install ./capacidadreal_0.2.3_all.deb
```

La aplicación cierra el acceso a los archivos de la memoria durante la prueba.
Al terminar, podés volver a abrirla desde tu administrador de archivos.

## Número de serie del pendrive o SD

- **Pendrive:** muestra la serie que el dispositivo informa a Linux.
- **SD en un lector nativo compatible:** muestra la serie de la tarjeta cuando
  Linux la expone. Se admiten tarjetas SD extraíbles; la memoria eMMC interna se excluye.
- **SD en un lector USB:** el número disponible puede ser el del lector. La
  aplicación lo aclara; no lo presenta como si necesariamente fuera el de la tarjeta.
- Si no se puede obtener un número, aparece **«No disponible»**.

El botón **Copiar** copia únicamente el número de serie. Este dato ayuda a
identificar la unidad, pero por sí solo no demuestra que sea original.

## Cómo interpretar el resultado

| Resultado | Qué significa |
| --- | --- |
| **Capacidad compatible** | Todas las muestras pasaron. No se detectó capacidad falsa en esta prueba. |
| **Capacidad falsa detectada** | Diferentes posiciones están reutilizando la misma memoria. Se muestra una estimación. |
| **El espacio anunciado no se verifica** | Parte del espacio no conserva correctamente las muestras. Puede ser capacidad falsa o memoria dañada. |
| **No se pudo completar la prueba** | Hubo un problema de acceso o del dispositivo; no hay un resultado confiable. |

## Antes de usarla

**Es una versión inicial.** Pasó pruebas automáticas con dispositivos simulados,
lectura y escritura directa sobre un archivo temporal, e interfaz gráfica.
Todavía necesita validación con distintos pendrives y lectores físicos.

Usá una memoria vacía o conservá una copia de tus archivos importantes. La prueba
escribe pequeñas muestras y restaura los originales, pero un fallo del dispositivo
o una desconexión puede impedir la restauración. Si hay una interrupción, conserva
una copia de recuperación y ofrece restaurarla antes de otra prueba.

Una comprobación rápida **no garantiza que cada rincón de la memoria esté sano**.
Algunos engaños sofisticados o problemas entre las muestras pueden pasar
inadvertidos. La aplicación muestra este alcance y no convierte una estimación
en una garantía de capacidad exacta.

## Para quienes quieran conocer el código

Está hecha con Python y GTK, es liviana y no instala servicios permanentes.
No guarda contraseñas. Está inspirada en la sencillez de ValiDrive, con una
implementación independiente y sin relación con GRC. No ejecuta F3.

[Detalles técnicos, recuperación y pruebas](docs/DETALLES.md).
El flujo de GitHub Actions genera el `.deb` y ejecuta las verificaciones en Debian 13.

Licencia MIT.
