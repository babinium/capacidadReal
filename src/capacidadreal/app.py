#!/usr/bin/python3
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk

from capacidadreal import __version__
from capacidadreal.devices import descendants, human_size, inventory, serial_details, usable
from capacidadreal.engine import GRID_SAMPLES, positions

HELPER = "/usr/lib/capacidadreal/capacidadreal/helper.py"
PHASES = {"saving": (0, "Guardando los bloques originales"),
          "writing": (1, "Escribiendo pequeñas muestras"),
          "checking": (2, "Comprobando las muestras"),
          "restoring": (3, "Restaurando los datos originales"),
          "verifying_restore": (4, "Verificando la restauración")}
CSS = b"""
window { background: #0f141b; color: #e6edf5; }
.hero { background: #080c12; border-bottom: 1px solid #1f2935; padding: 20px 28px; }
.hero label { color: #f4f8fd; }
.brand { font-size: 26px; font-weight: 800; }
.hero-subtitle { color: #9fb0c3; font-size: 13px; }
.content { padding: 22px 28px; }
.card { background: #161e29; border: 1px solid #27313f; border-radius: 12px; padding: 16px; }
.section { font-size: 11px; font-weight: 700; color: #8ea1b6; }
.headline { font-size: 23px; font-weight: 700; }
.muted { color: #93a4b8; font-size: 12px; }
.body { font-size: 13px; }
.primary { background: #3b82f6; color: #ffffff; border: 0; border-radius: 8px; padding: 11px 20px; font-weight: 700; }
.primary label { color: #ffffff; }
.primary:disabled { background: #27313f; color: #6f7f92; }
.primary:disabled label { color: #6f7f92; }
.secondary { background: #232e3b; color: #dbe5f0; border: 1px solid #33404f; border-radius: 8px; padding: 9px 13px; }
.success { color: #34d399; }
.warning { color: #fbbf24; }
progressbar trough { min-height: 6px; border: 0; background: #243040; border-radius: 4px; }
progressbar progress { background: #3b82f6; border: 0; border-radius: 4px; }
combobox button { padding: 8px; border-radius: 7px; }
.ready { background: #10352a; color: #4ade80; border: 1px solid #1f6f57; border-radius: 8px; padding: 9px 12px; font-weight: 700; }
"""


def label(text, style=None, wrap=False):
    obj = Gtk.Label(label=text, xalign=0)
    obj.set_line_wrap(wrap)
    if style:
        obj.get_style_context().add_class(style)
    return obj


class Window(Gtk.ApplicationWindow):
    def __init__(self, app, demo=False):
        super().__init__(application=app, title="capacidadReal")
        self.set_default_size(760, 690)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.demo = demo
        self.busy = False
        self.worker = None
        self.devices = []
        self.cells = ["pending"] * GRID_SAMPLES
        self.started = None
        self.last_progress = None
        self.last_phase = None
        self.terminal_event = False
        self.refreshing = False
        self.active_item = None
        self.result_report = ""
        self.cancel_requested = False
        self.pending_recovery = False
        self.using_sudo = False
        self.display_identity = None
        self.connect("delete-event", self.on_close)
        settings = Gtk.Settings.get_default()
        if settings:
            settings.set_property("gtk-application-prefer-dark-theme", True)
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(outer)
        hero = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        hero.get_style_context().add_class("hero")
        heading = Gtk.Box(spacing=12)
        heading.pack_start(label("capacidadReal", "brand"), True, True, 0)
        self.version_label = label(f"Versión {__version__}", "muted")
        heading.pack_end(self.version_label, False, False, 0)
        hero.pack_start(heading, False, False, 0)
        hero.pack_start(label("Comprobá rápido si tu pendrive o SD tiene el espacio que promete.", "hero-subtitle"), False, False, 0)
        outer.pack_start(hero, False, False, 0)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.get_style_context().add_class("content")
        outer.pack_start(content, True, True, 0)
        select = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        select.get_style_context().add_class("card")
        select.pack_start(label("1  ·  ELEGÍ TU PENDRIVE O TARJETA SD", "section"), False, False, 0)
        row = Gtk.Box(spacing=10)
        self.combo = Gtk.ComboBoxText()
        self.combo.connect("changed", self.selection_changed)
        row.pack_start(self.combo, True, True, 0)
        self.refresh_button = Gtk.Button(label="Actualizar")
        self.refresh_button.get_style_context().add_class("secondary")
        self.refresh_button.connect("clicked", lambda *_: self.refresh())
        row.pack_start(self.refresh_button, False, False, 0)
        select.pack_start(row, False, False, 0)
        self.device_detail = label("Buscando unidades USB…", "muted", True)
        select.pack_start(self.device_detail, False, False, 0)
        serial_row = Gtk.Box(spacing=10)
        self.serial_label = label("Número de serie: —", "body", True)
        self.serial_label.set_selectable(True)
        self.serial_label.set_max_width_chars(60)
        serial_row.pack_start(self.serial_label, True, True, 0)
        self.copy_serial_button = Gtk.Button(label="Copiar")
        self.copy_serial_button.get_style_context().add_class("secondary")
        self.copy_serial_button.set_tooltip_text("Copiar el número de serie")
        self.copy_serial_button.connect("clicked", self.copy_serial)
        self.copy_serial_button.set_sensitive(False)
        serial_row.pack_start(self.copy_serial_button, False, False, 0)
        select.pack_start(serial_row, False, False, 0)
        self.serial_note = label("", "muted", True)
        self.serial_note.set_max_width_chars(82)
        select.pack_start(self.serial_note, False, False, 0)
        content.pack_start(select, False, False, 0)

        test = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        test.get_style_context().add_class("card")
        test.pack_start(label("2  ·  COMPROBÁ SU CAPACIDAD", "section"), False, False, 0)
        self.title_label = label("Una prueba breve, un resultado claro", "headline")
        test.pack_start(self.title_label, False, False, 0)
        self.description = label("Se prueban pequeñas muestras a lo largo del espacio anunciado. Los bloques originales se guardan y se restauran al terminar.", "body", True)
        self.description.set_max_width_chars(75)
        test.pack_start(self.description, False, False, 0)
        self.grid = Gtk.DrawingArea()
        self.grid.set_size_request(-1, 72)
        self.grid.connect("draw", self.draw_grid)
        test.pack_start(self.grid, False, False, 0)
        self.progress = Gtk.ProgressBar()
        test.pack_start(self.progress, False, False, 0)
        status_row = Gtk.Box()
        self.status = label("Listo para comenzar", "muted")
        self.elapsed = label("", "muted")
        status_row.pack_start(self.status, True, True, 0)
        status_row.pack_start(self.elapsed, False, False, 0)
        test.pack_start(status_row, False, False, 0)
        self.ready = label("", "ready", True)
        self.ready.set_no_show_all(True)
        test.pack_start(self.ready, False, False, 0)
        self.ready.hide()
        button_row = Gtk.Box(spacing=10)
        self.start_button = Gtk.Button(label="Comprobar capacidad")
        self.start_button.get_style_context().add_class("primary")
        self.start_button.connect("clicked", self.start_clicked)
        self.start_button.set_sensitive(False)
        button_row.pack_start(self.start_button, True, True, 0)
        self.copy_result_button = Gtk.Button(label="Copiar resultado")
        self.copy_result_button.get_style_context().add_class("secondary")
        self.copy_result_button.set_tooltip_text("Copiar modelo, serie, capacidad, resultado y duración")
        self.copy_result_button.set_sensitive(False)
        self.copy_result_button.connect("clicked", self.copy_result)
        button_row.pack_start(self.copy_result_button, False, False, 0)
        self.cancel_button = Gtk.Button(label="Cancelar")
        self.cancel_button.get_style_context().add_class("secondary")
        self.cancel_button.connect("clicked", self.cancel)
        self.cancel_button.set_no_show_all(True)
        button_row.pack_start(self.cancel_button, False, False, 0)
        test.pack_start(button_row, False, False, 0)
        content.pack_start(test, True, True, 0)
        footer = label("Prueba por muestreo: detecta capacidad falsa común, pero no certifica cada sector.\nGuardá una copia de tus archivos importantes y no retires el USB durante la prueba.", "muted", True)
        content.pack_start(footer, False, False, 0)
        self.show_all()
        self.refresh()
        GLib.timeout_add_seconds(1, self.tick)
        GLib.timeout_add_seconds(4, self.periodic_refresh)

    def draw_grid(self, widget, cr):
        width, height = widget.get_allocated_width(), widget.get_allocated_height()
        colors = {"pending": (0.15, 0.19, 0.24), "ok": (0.20, 0.83, 0.60),
                  "mismatch": (0.97, 0.44, 0.44), "error": (0.98, 0.75, 0.14)}
        columns = 16
        rows = max(1, (len(self.cells) + columns - 1) // columns)
        for i, value in enumerate(self.cells):
            x, y = i % columns, i // columns
            cr.set_source_rgb(*colors.get(value, colors["pending"]))
            cr.rectangle(x * width / columns, y * height / rows, max(1, width / columns - 2), max(1, height / rows - 2))
            cr.fill()

    def refresh(self):
        if self.busy or self.refreshing:
            return
        if self.demo:
            self.set_devices([{"name": "/dev/demo", "model": "Pendrive de ejemplo", "serial": "DEMO", "size": 32_000_000_000, "type": "disk", "tran": "usb"}])
            return
        self.refreshing = True
        def task():
            try:
                items = [d for d in inventory() if usable(d)]
                GLib.idle_add(self.set_devices, items)
            except Exception as exc:
                GLib.idle_add(self.refresh_error, str(exc))
        threading.Thread(target=task, daemon=True).start()

    def refresh_error(self, text):
        self.refreshing = False
        self.device_detail.set_text("No se pudieron consultar las unidades USB: " + text)

    def set_devices(self, items):
        self.refreshing = False
        if self.busy:
            return
        selected = self.combo.get_active_id()
        same = [(d["name"], d.get("serial"), d.get("size")) for d in items] == [(d["name"], d.get("serial"), d.get("size")) for d in self.devices]
        self.devices = items
        if not same or not self.combo.get_active_id():
            self.combo.remove_all()
            for d in items:
                self.combo.append(d["name"], f'{(d.get("model") or "Memoria USB").strip()}  ·  {human_size(d.get("size") or 0)}')
            if not selected or not self.combo.set_active_id(selected):
                self.combo.set_active(0 if items else -1)
        self.selection_changed()

    def selection_changed(self, *_):
        item = next((d for d in self.devices if d["name"] == self.combo.get_active_id()), None)
        identity = (item["name"], item.get("serial"), item.get("size")) if item else None
        if not self.busy and identity != self.display_identity:
            self.display_identity = identity
            self.clear_report()
            self.title_label.set_text("Una prueba breve, un resultado claro")
            self.description.set_text("Se prueban pequeñas muestras a lo largo del espacio anunciado. Los bloques originales se guardan y se restauran al terminar.")
            self.cells = ["pending"] * GRID_SAMPLES
            self.grid.queue_draw()
            self.progress.set_fraction(0)
            self.status.set_text("Listo para comenzar" if item else "Conectá un pendrive")
            self.elapsed.set_text("")
            self.ready.hide()
        self.start_button.set_sensitive(bool(item and item.get("size") and not self.busy))
        serial, note, available = serial_details(item or {})
        self.serial_label.set_text("Número de serie: " + (serial if item else "—"))
        self.serial_note.set_text(note if item else "")
        self.copy_serial_button.set_sensitive(bool(item and available))
        if not item:
            self.device_detail.set_text("Conectá un pendrive o una tarjeta SD extraíble para comenzar.")
        else:
            size = int(item.get("size") or 0)
            self.device_detail.set_text(f'{item["name"]}  ·  {size / 1_000_000_000:.2f} GB anunciados')
            if not size:
                self.device_detail.set_text("El USB informa 0 bytes. Reconectalo o comprobá la tarjeta del lector.")

    def copy_serial(self, *_):
        item = next((d for d in self.devices if d["name"] == self.combo.get_active_id()), None)
        if item:
            serial, _, available = serial_details(item)
            if available:
                clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
                clipboard.set_text(serial, -1)
                clipboard.store()

    def clear_report(self):
        self.result_report = ""
        self.copy_result_button.set_sensitive(False)

    def save_report(self, event):
        # Freeze the tested device and terminal result, never the live selection
        # or the running timer when the user later presses Copy.
        item = self.active_item
        if item is None:
            return
        serial, note, _ = serial_details(item)
        model = " ".join((item.get("model") or "Memoria").split())
        duration = event.get("elapsed")
        if duration is None and self.started is not None:
            duration = max(0, time.monotonic() - self.started)
        elapsed = f"{duration:.1f} s" if duration is not None else "No disponible"
        lines = [f"capacidadReal {__version__}"]
        if self.demo:
            lines.append("Demostración: dispositivo ficticio")
        lines.extend([
            f"Modelo: {model}",
            f'Número de serie: {" ".join(serial.split())}',
            f"Serie: {note}",
            f'Capacidad anunciada: {int(item.get("size") or 0) / 1_000_000_000:.2f} GB',
            f"Resultado: {self.title_label.get_text()}",
            self.description.get_text(),
            f"Duración: {elapsed}",
        ])
        if event.get("type") == "result":
            lines.append(f'Muestras correctas: {event["passed"]}/{event["samples"]}')
        if event.get("restored") or event.get("type") == "recovered":
            lines.append("Restauración de las zonas probadas: confirmada")
        lines.append("Prueba por muestreo: no certifica todos los sectores.")
        self.result_report = "\n".join(lines)
        self.copy_result_button.set_sensitive(True)

    def copy_result(self, *_):
        if self.result_report:
            clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
            clipboard.set_text(self.result_report, -1)
            clipboard.store()

    def periodic_refresh(self):
        self.refresh()
        return True

    def tick(self):
        if self.busy and self.started is not None and not self.terminal_event:
            seconds = int(time.monotonic() - self.started)
            self.elapsed.set_text(f"{seconds // 60:02d}:{seconds % 60:02d}")
            if self.last_progress is not None:
                waiting = int(time.monotonic() - self.last_progress)
                if waiting >= 4:
                    if self.cancel_requested or self.last_phase in ("restoring", "verifying_restore"):
                        text = f"Restauración: esperando respuesta del dispositivo · {waiting} s"
                    else:
                        text = f"Esperando al dispositivo · {waiting} s de espera"
                    self.status.set_text(text)
        return True

    def question(self, title, text, accept):
        dialog = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.QUESTION, text=title)
        dialog.format_secondary_text(text)
        dialog.add_button("Cancelar", Gtk.ResponseType.CANCEL)
        dialog.add_button(accept, Gtk.ResponseType.OK)
        result = dialog.run() == Gtk.ResponseType.OK
        dialog.destroy()
        return result

    def start_clicked(self, *_):
        item = next((d for d in self.devices if d["name"] == self.combo.get_active_id()), None)
        if not item:
            return
        if self.demo:
            self.active_item = dict(item)
            samples = len(positions(item["size"])[0])
            self.on_event({"type": "result", "status": "compatible", "announced": item["size"], "samples": samples, "passed": samples, "grid": ["ok"] * GRID_SAMPLES, "elapsed": 8.4})
            return
        if not self.question("Comprobar esta memoria", f'{item.get("model") or "Memoria"} · {human_size(item["size"])} · {item["name"]}\nSerie: {item.get("serial") or "No disponible"}\n\nSe cerrará el acceso a sus archivos durante la prueba. Se escribirán pequeñas muestras y luego se restaurarán los datos originales de esas zonas. Una interrupción o una falla de la memoria puede dañar datos: conservá una copia de lo importante.', "Comprobar"):
            return
        self.active_item = dict(item)
        self.begin()
        threading.Thread(target=self.prepare, daemon=True).start()

    def begin(self):
        self.clear_report()
        self.busy = True
        self.started = time.monotonic()
        self.last_progress = None
        self.last_phase = None
        self.terminal_event = False
        self.cancel_requested = False
        self.pending_recovery = False
        self.cells = ["pending"] * GRID_SAMPLES
        self.grid.queue_draw()
        self.progress.set_fraction(0)
        self.title_label.set_text("Comprobando tu memoria…")
        self.description.set_text("Mantenelo conectado hasta que termine la restauración de los datos.")
        self.start_button.set_sensitive(False)
        self.combo.set_sensitive(False)
        self.refresh_button.set_sensitive(False)
        self.cancel_button.show()
        self.cancel_button.set_sensitive(True)
        self.status.set_text("Preparando la unidad y los permisos")
        self.ready.hide()

    def prepare(self):
        try:
            current = next(d for d in inventory() if d["name"] == self.active_item["name"])
            if current.get("serial") != self.active_item.get("serial") or current["size"] != self.active_item["size"]:
                raise ValueError("El dispositivo cambió. Seleccionalo de nuevo.")
            for node in descendants(current):
                mounts = [p for p in (node.get("mountpoints") or []) if p]
                if any(p in ("/", "/home", "/boot", "/boot/efi", "/usr", "/var", "[SWAP]") for p in mounts):
                    raise ValueError("Esta unidad contiene un sistema en uso y no se puede probar.")
                if mounts:
                    proc = subprocess.run(["/usr/bin/udisksctl", "unmount", "--block-device", node["name"]], capture_output=True, text=True, timeout=40)
                    if proc.returncode:
                        raise ValueError("No se pudo desmontar el USB. Cerrá los archivos o aplicaciones que lo estén usando y volvé a intentar.")
            if self.cancel_requested:
                GLib.idle_add(self.on_event, {"type": "cancelled"})
                GLib.idle_add(self.finish)
                return
            self.launch("scan", False)
        except Exception as exc:
            GLib.idle_add(self.on_event, {"type": "error", "message": str(exc)})
            GLib.idle_add(self.finish)

    def launch(self, action, use_sudo):
        self.using_sudo = use_sudo
        item = self.active_item
        command = (["/usr/bin/sudo", "-n", "--"] if use_sudo else ["/usr/bin/pkexec", "--disable-internal-agent"])
        command += [HELPER, action, item["name"], str(item["size"]), item.get("serial") or ""]
        try:
            self.worker = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            if self.cancel_requested:
                self.worker.stdin.write("cancel\n")
                self.worker.stdin.flush()
            saw_event = False
            messages = []
            for line in self.worker.stdout:
                try:
                    event = json.loads(line)
                except ValueError:
                    messages.append(line.strip())
                    continue
                saw_event = True
                GLib.idle_add(self.on_event, event)
            code = self.worker.wait()
            self.worker = None
            if not saw_event and not use_sudo and code == 126:
                GLib.idle_add(self.on_event, {"type": "cancelled"})
                GLib.idle_add(self.finish)
                return
            if not saw_event and not use_sudo and code == 127:
                GLib.idle_add(self.ask_password, action)
                return
            if not saw_event:
                GLib.idle_add(self.on_event, {"type": "error", "message": "No se pudo iniciar la comprobación. " + " ".join(messages)[-600:]})
            elif code not in (0, 3):
                GLib.idle_add(self.unexpected_exit)
        except Exception as exc:
            self.worker = None
            GLib.idle_add(self.on_event, {"type": "error", "message": str(exc)})
        GLib.idle_add(self.finish)

    def ask_password(self, action):
        if self.cancel_requested:
            self.on_event({"type": "cancelled"})
            self.finish()
            return
        dialog = Gtk.Dialog(title="Permisos de Linux", transient_for=self, modal=True)
        dialog.add_button("Cancelar", Gtk.ResponseType.CANCEL)
        dialog.add_button("Continuar", Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.set_border_width(20)
        box.set_spacing(12)
        box.add(label("Linux requiere permisos de administrador para comprobar el USB.\nLa contraseña se entrega a sudo y no se guarda.", "body", True))
        entry = Gtk.Entry()
        entry.set_visibility(False)
        entry.set_input_purpose(Gtk.InputPurpose.PASSWORD)
        entry.set_activates_default(True)
        box.add(entry)
        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.show_all()
        response = dialog.run()
        password = entry.get_text()
        entry.set_text("")
        dialog.destroy()
        if response != Gtk.ResponseType.OK:
            self.on_event({"type": "cancelled"})
            self.finish()
            return
        def authorize(secret):
            try:
                result = subprocess.run(["/usr/bin/sudo", "-S", "-p", "", "-v"], input=secret + "\n", capture_output=True, text=True, timeout=30)
                secret = None
                if result.returncode:
                    raise ValueError("No se pudo autorizar. Comprobá tu contraseña y que tu usuario tenga permiso para usar sudo.")
                if self.cancel_requested:
                    GLib.idle_add(self.on_event, {"type": "cancelled"})
                    GLib.idle_add(self.finish)
                    return
                self.launch(action, True)
            except Exception as exc:
                GLib.idle_add(self.on_event, {"type": "error", "message": str(exc)})
                GLib.idle_add(self.finish)
        threading.Thread(target=authorize, args=(password,), daemon=True).start()
        password = None

    def unexpected_exit(self):
        if not self.terminal_event:
            self.on_event({"type": "error", "message": "La prueba se interrumpió. No uses el USB hasta recuperar sus bloques desde esta aplicación."})

    def on_event(self, event):
        kind = event.get("type")
        if kind == "progress":
            step, name = PHASES[event["phase"]]
            self.last_progress = time.monotonic()
            self.last_phase = event["phase"]
            self.ready.hide()
            self.status.set_text(f'{name} · {event["done"]}/{event["total"]}')
            self.progress.set_fraction(min(0.99, (step + event["done"] / event["total"]) / len(PHASES)))
            if event["phase"] in ("restoring", "verifying_restore"):
                self.cancel_button.set_sensitive(False)
            return
        self.terminal_event = True
        if kind == "result":
            self.progress.set_fraction(1)
            self.cells = event["grid"]
            self.grid.queue_draw()
            state = event["status"]
            if state == "compatible":
                self.title_label.set_text(human_size(event["announced"]) + " · capacidad compatible")
                self.description.set_text("Todas las muestras conservaron los datos escritos. No se detectó capacidad falsa en esta prueba por muestreo.")
            elif state == "aliased":
                self.title_label.set_text("Capacidad falsa detectada")
                self.description.set_text(f'Anuncia {human_size(event["announced"])}. Se detectaron direcciones repetidas: capacidad estimada de {human_size(event["estimated"])}. No confíes archivos a esta unidad.')
            elif state == "limited":
                self.title_label.set_text("El espacio anunciado no se verifica")
                self.description.set_text(f'Anuncia {human_size(event["announced"])}. La transición observada está entre {human_size(event["estimated"])} y {human_size(event["upper_bound"])}; puede indicar capacidad falsa o una falla de memoria.')
            else:
                self.title_label.set_text("Se detectaron datos incorrectos")
                self.description.set_text("Algunas muestras no coinciden. La unidad puede tener capacidad falsa o memoria dañada; no se puede estimar una capacidad útil confiable.")
            self.status.set_text(f'{event["passed"]}/{event["samples"]} muestras correctas · originales restaurados')
            self.elapsed.set_text(f'{event["elapsed"]:.1f} s')
            self.show_ready()
        elif kind == "cancelled":
            self.title_label.set_text("Prueba cancelada")
            self.description.set_text("No se determinó la capacidad. Los bloques modificados, si los hubo, se restauraron.")
            self.status.set_text("Podés volver a intentarlo")
            self.show_ready()
        elif kind == "recovered":
            self.title_label.set_text("Bloques originales recuperados")
            self.description.set_text("La restauración fue verificada. Ya podés iniciar una nueva comprobación.")
            self.progress.set_fraction(1)
            self.status.set_text("Recuperación terminada")
            self.show_ready()
        elif kind == "recovery_needed":
            self.pending_recovery = True
        elif kind == "error":
            self.title_label.set_text("No se pudo completar la prueba")
            self.description.set_text(event["message"])
            self.status.set_text("Sin resultado de capacidad")
            self.ready.hide()
        if kind in ("result", "cancelled", "recovered", "error"):
            self.save_report(event)

    def show_ready(self):
        self.ready.set_text("✓  Dispositivo listo para desenchufar")
        self.ready.show()

    def finish(self):
        if not self.terminal_event:
            self.unexpected_exit()
        self.busy = False
        self.worker = None
        self.cancel_button.hide()
        self.combo.set_sensitive(True)
        self.refresh_button.set_sensitive(True)
        self.selection_changed()
        if self.pending_recovery:
            self.pending_recovery = False
            if self.question("Hay una prueba interrumpida", "Se conservó una copia de los bloques originales de esta unidad. Restaurarlos permite terminar la recuperación. Si guardaste archivos nuevos después de la interrupción, la restauración puede sobrescribirlos. Verificá que sea el mismo pendrive.", "Restaurar bloques"):
                use_sudo = self.using_sudo
                self.begin()
                threading.Thread(target=self.launch, args=("recover", use_sudo), daemon=True).start()
            else:
                self.on_event({"type": "error", "message": "Recuperación pendiente. La copia original se conserva; no inicies otra prueba ni uses el USB hasta resolverla."})

    def cancel(self, *_):
        self.cancel_requested = True
        self.cancel_button.set_sensitive(False)
        self.status.set_text("Cancelando; se restaurarán los bloques originales")
        if self.worker and self.worker.stdin:
            try:
                self.worker.stdin.write("cancel\n")
                self.worker.stdin.flush()
            except (BrokenPipeError, OSError):
                pass

    def on_close(self, *_):
        if self.busy:
            if self.question("La prueba sigue en curso", "Para proteger los datos, la ventana debe permanecer abierta hasta completar la restauración.", "Cancelar y restaurar"):
                self.cancel()
            return True
        return False


def main():
    demo = "--demo" in sys.argv
    screenshot = None
    if "--screenshot" in sys.argv:
        screenshot = sys.argv[sys.argv.index("--screenshot") + 1]
        demo = True  # Never touch a device in the visual test path.
    app = Gtk.Application(application_id="io.github.babinium.capacidadReal")
    def activate(application):
        window = Window(application, demo)
        if demo and "--result" in sys.argv:
            window.start_clicked()
        if screenshot:
            def capture():
                image = Gdk.pixbuf_get_from_window(window.get_window(), 0, 0, window.get_allocated_width(), window.get_allocated_height())
                image.savev(screenshot, "png", [], [])
                application.quit()
                return False
            GLib.timeout_add(700, capture)
    app.connect("activate", activate)
    return app.run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
