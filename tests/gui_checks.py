"""Run under Xvfb. No real device access or privileged process is allowed."""
from unittest.mock import patch
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk
from capacidadreal.app import Window

app = Gtk.Application(application_id="io.github.babinium.capacidadReal.Tests")
app.register(None)
with patch("subprocess.Popen", side_effect=AssertionError("GUI demo attempted process launch")):
    window = Window(app, demo=True)
    assert Gtk.Settings.get_default().get_property("gtk-application-prefer-dark-theme")
    assert window.start_button.get_sensitive()
    assert not window.copy_result_button.get_sensitive()
    assert window.result_report == ""
    assert not window.ready.get_visible()
    assert window.serial_label.get_text() == "Número de serie: DEMO"
    assert window.serial_label.get_selectable()
    assert window.copy_serial_button.get_sensitive()
    with patch("capacidadreal.app.Gtk.Clipboard.get") as clipboard:
        window.copy_serial()
        clipboard.return_value.set_text.assert_called_once_with("DEMO", -1)
    window.start_clicked()
    assert "compatible" in window.title_label.get_text()
    assert window.ready.get_visible()
    assert "desenchufar" in window.ready.get_text()
    assert window.copy_result_button.get_sensitive()
    report = window.result_report
    for value in ("Modelo: Pendrive de ejemplo", "Número de serie: DEMO",
                  "Capacidad anunciada: 32.00 GB", "capacidad compatible", "Duración: 8.4 s",
                  "Demostración: dispositivo ficticio", "Prueba por muestreo"):
        assert value in report
    # Copy a frozen result, even after the source dictionary and clock change.
    window.active_item["serial"] = "CHANGED_AFTER_TEST"
    with patch("capacidadreal.app.Gtk.Clipboard.get") as clipboard:
        window.copy_result()
        clipboard.return_value.set_text.assert_called_once_with(report, -1)
        clipboard.return_value.store.assert_called_once()
        # Keep a visual artifact of the actual copied confirmation under Xvfb.
        draw_loop = GLib.MainLoop()
        GLib.timeout_add(150, draw_loop.quit)
        draw_loop.run()
        capture = Gdk.pixbuf_get_from_window(window.get_window(), 0, 0,
                                            window.get_allocated_width(), window.get_allocated_height())
        capture.savev("artifacts/informe-copiado.png", "png", [], [])
    # Refreshing the same drive preserves the result.
    window.set_devices(list(window.devices))
    assert "compatible" in window.title_label.get_text()
    assert window.result_report == report
    # Selecting another drive must never display the previous drive's result.
    other = dict(window.devices[0], name="/dev/demo2", serial="OTHER", size=8_000_000_000)
    window.set_devices([other])
    assert "compatible" not in window.title_label.get_text()
    assert not window.ready.get_visible()
    assert all(c == "pending" for c in window.cells)
    assert window.progress.get_fraction() == 0
    assert window.serial_label.get_text() == "Número de serie: OTHER"
    assert window.result_report == ""
    assert not window.copy_result_button.get_sensitive()
    missing = dict(other, serial=None)
    window.set_devices([missing])
    assert "No disponible" in window.serial_label.get_text()
    assert not window.copy_serial_button.get_sensitive()
    sd = dict(other, serial="0x1234abcd", serial_source="sd")
    window.set_devices([sd])
    assert "tarjeta SD" in window.serial_note.get_text()
    # Report the completed test's device, including an estimated fake capacity.
    window.active_item = dict(sd)
    window.begin()
    assert not window.copy_result_button.get_sensitive()
    window.on_event({"type": "result", "status": "aliased", "announced": sd["size"],
                     "estimated": 4_000_000_000, "samples": 128, "passed": 64,
                     "grid": ["mismatch"] * 64, "elapsed": 12.6, "restored": True})
    assert "Número de serie: 0x1234abcd" in window.result_report
    assert "de la tarjeta SD" in window.result_report
    assert "Capacidad anunciada: 8.00 GB" in window.result_report
    assert "Capacidad falsa detectada" in window.result_report
    assert "4.00 GB" in window.result_report
    assert "Duración: 12.6 s" in window.result_report
    assert "Restauración de las zonas probadas: confirmada" in window.result_report
    # A new test clears the prior report before any I/O or permission request.
    window.begin()
    assert window.result_report == ""
    assert not window.copy_result_button.get_sensitive()
    # A slow response keeps the test active until completion or user cancellation.
    window.busy = True
    window.started = 10
    window.terminal_event = False
    with patch("capacidadreal.app.time.monotonic", return_value=10):
        window.on_event({"type": "progress", "phase": "writing", "done": 1, "total": 128})
    with patch("capacidadreal.app.time.monotonic", return_value=16):
        window.tick()
    assert "6 s de espera" in window.status.get_text()
    assert not window.ready.get_visible()
    assert window.busy
    assert not window.terminal_event
    assert window.worker is None  # demo must not launch real helpers
    with patch("capacidadreal.app.time.monotonic", return_value=1000):
        window.tick()
    assert "990 s de espera" in window.status.get_text()
    assert window.busy
    assert not window.cancel_requested
    assert not window.terminal_event
    # A later response resumes normal progress, then a result can be shown.
    window.on_event({"type": "progress", "phase": "checking", "done": 128, "total": 128})
    assert "Comprobando" in window.status.get_text()
    assert "128/128" in window.status.get_text()
    assert not window.terminal_event
    window.cancel_requested = True
    window.last_progress = 10
    with patch("capacidadreal.app.time.monotonic", return_value=17):
        window.tick()
    assert "Restauración" in window.status.get_text()
    with patch("capacidadreal.app.time.monotonic", return_value=17):
        window.on_event({"type": "cancelled", "restored": True})
    assert "Resultado: Prueba cancelada" in window.result_report
    assert "Duración: 7.0 s" in window.result_report
    assert window.copy_result_button.get_sensitive()
    assert window.ready.get_visible()
    # Failed recovery must not copy an old success or claim verified originals.
    window.begin()
    window.on_event({"type": "error", "message": "No se pudo confirmar la restauración."})
    assert "No se pudo confirmar la restauración." in window.result_report
    assert "Prueba cancelada" not in window.result_report
    assert "Restauración de las zonas probadas: confirmada" not in window.result_report
    assert not window.ready.get_visible()
    assert "compatible" not in window.title_label.get_text()
    window.busy = False
    window.set_devices([])
    assert not window.start_button.get_sensitive()
    assert not window.copy_serial_button.get_sensitive()
    assert not window.copy_result_button.get_sensitive()
    window.destroy()
print("Interfaz: selección, resultado, serie copiable, serie SD, serie ausente desconexión, espera sin corte automático, cancelación e informe copiable con identidad y duración verificados.")
