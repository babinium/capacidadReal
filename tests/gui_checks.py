"""Run under Xvfb. No real device access or privileged process is allowed."""
from unittest.mock import patch
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from capacidadreal.app import Window

app = Gtk.Application(application_id="io.github.babinium.capacidadReal.Tests")
app.register(None)
with patch("subprocess.Popen", side_effect=AssertionError("GUI demo attempted process launch")):
    window = Window(app, demo=True)
    assert Gtk.Settings.get_default().get_property("gtk-application-prefer-dark-theme")
    assert window.start_button.get_sensitive()
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
    # Refreshing the same drive preserves the result.
    window.set_devices(list(window.devices))
    assert "compatible" in window.title_label.get_text()
    # Selecting another drive must never display the previous drive's result.
    other = dict(window.devices[0], name="/dev/demo2", serial="OTHER", size=8_000_000_000)
    window.set_devices([other])
    assert "compatible" not in window.title_label.get_text()
    assert not window.ready.get_visible()
    assert all(c == "pending" for c in window.cells)
    assert window.progress.get_fraction() == 0
    assert window.serial_label.get_text() == "Número de serie: OTHER"
    missing = dict(other, serial=None)
    window.set_devices([missing])
    assert "No disponible" in window.serial_label.get_text()
    assert not window.copy_serial_button.get_sensitive()
    sd = dict(other, serial="0x1234abcd", serial_source="sd")
    window.set_devices([sd])
    assert "tarjeta SD" in window.serial_note.get_text()
    window.set_devices([])
    assert not window.start_button.get_sensitive()
    assert not window.copy_serial_button.get_sensitive()
    window.destroy()
print("Interfaz: selección, resultado, serie copiable, serie SD, serie ausente y desconexión verificados.")
