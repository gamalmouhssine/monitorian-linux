#!/usr/bin/env python3
"""Monitorian for Linux — DDC/CI brightness control from a tray icon."""

import sys
from typing import Callable

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk

import ddc_backend as ddc

DEBOUNCE_MS = 400
APP_ID = "monitorian-linux"


class BrightnessPanel(Gtk.Box):
    """A vertical stack of one labeled brightness slider per monitor."""

    def __init__(self, monitors: list[ddc.Monitor]):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.set_border_width(12)
        self._timeout_ids: dict[int, int] = {}

        if not monitors:
            label = Gtk.Label(label="No DDC/CI monitors detected.")
            label.set_line_wrap(True)
            self.pack_start(label, False, False, 0)
            return

        for monitor in monitors:
            self._add_monitor_row(monitor)

    def _add_monitor_row(self, monitor: ddc.Monitor):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        label = Gtk.Label(label=monitor.description, xalign=0)
        box.pack_start(label, False, False, 0)

        adjustment = Gtk.Adjustment(
            value=monitor.brightness,
            lower=0,
            upper=100,
            step_increment=1,
            page_increment=10,
        )
        scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=adjustment)
        scale.set_digits(0)
        scale.set_value_pos(Gtk.PositionType.RIGHT)
        scale.set_size_request(220, -1)
        scale.connect("value-changed", self._on_value_changed, monitor)
        box.pack_start(scale, False, False, 0)

        self.pack_start(box, False, False, 0)

    def _on_value_changed(self, scale: Gtk.Scale, monitor: ddc.Monitor):
        value = int(scale.get_value())

        existing_id = self._timeout_ids.get(monitor.display_num)
        if existing_id is not None:
            GLib.source_remove(existing_id)

        def apply():
            ddc.set_brightness(monitor, value)
            monitor.brightness = value
            self._timeout_ids.pop(monitor.display_num, None)
            return False

        self._timeout_ids[monitor.display_num] = GLib.timeout_add(DEBOUNCE_MS, apply)


def build_panel_window(monitors: list[ddc.Monitor]) -> Gtk.Window:
    window = Gtk.Window(title="Monitorian")
    window.set_keep_above(True)
    window.set_resizable(False)
    window.set_default_size(260, -1)
    window.connect("destroy", Gtk.main_quit)

    panel = BrightnessPanel(monitors)
    window.add(panel)
    panel.show_all()

    return window


# AppIndicator menus are exported to GNOME Shell over the dbusmenu D-Bus
# protocol, which only understands plain menu items/separators/submenus —
# an embedded Gtk.Scale is silently dropped. So the tray menu uses a
# submenu of clickable levels per monitor instead of a live slider.
BRIGHTNESS_PRESETS = (100, 75, 50, 25, 0)
BRIGHTNESS_STEP = 5


def _build_monitor_menu_item(monitor: ddc.Monitor) -> tuple[Gtk.MenuItem, Callable[[], None]]:
    top_item = Gtk.MenuItem(label=f"{monitor.description}: {monitor.brightness}%")
    submenu = Gtk.Menu()

    def refresh_label():
        top_item.set_label(f"{monitor.description}: {monitor.brightness}%")

    def set_level(_item, value):
        value = max(0, min(100, value))
        ddc.set_brightness(monitor, value)
        monitor.brightness = value
        refresh_label()

    for pct in BRIGHTNESS_PRESETS:
        item = Gtk.MenuItem(label=f"{pct}%")
        item.connect("activate", set_level, pct)
        submenu.append(item)

    submenu.append(Gtk.SeparatorMenuItem())

    plus_item = Gtk.MenuItem(label=f"+{BRIGHTNESS_STEP}%")
    plus_item.connect("activate", lambda item: set_level(item, monitor.brightness + BRIGHTNESS_STEP))
    submenu.append(plus_item)

    minus_item = Gtk.MenuItem(label=f"-{BRIGHTNESS_STEP}%")
    minus_item.connect("activate", lambda item: set_level(item, monitor.brightness - BRIGHTNESS_STEP))
    submenu.append(minus_item)

    submenu.show_all()
    top_item.set_submenu(submenu)
    return top_item, refresh_label


def _build_slider_popup(monitors: list[ddc.Monitor]) -> Gtk.Window:
    """A small popup window with real Gtk.Scale sliders, for use from the
    tray menu (where dbusmenu can't render a live slider — see above)."""
    window = Gtk.Window(title="Monitorian")
    window.set_keep_above(True)
    window.set_resizable(False)
    window.set_default_size(260, -1)
    window.set_position(Gtk.WindowPosition.MOUSE)
    # Hide rather than quit the whole app when the popup is dismissed.
    window.connect("delete-event", lambda w, _e: (w.hide(), True)[1])

    panel = BrightnessPanel(monitors)
    window.add(panel)
    panel.show_all()

    return window


def try_build_tray(monitors: list[ddc.Monitor]) -> bool:
    indicator_module = None
    try:
        gi.require_version("AyatanaAppIndicator3", "0.1")
        from gi.repository import AyatanaAppIndicator3 as AppIndicator3

        indicator_module = AppIndicator3
    except (ValueError, ImportError):
        try:
            gi.require_version("AppIndicator3", "0.1")
            from gi.repository import AppIndicator3

            indicator_module = AppIndicator3
        except (ValueError, ImportError):
            return False

    indicator = indicator_module.Indicator.new(
        APP_ID,
        "display-brightness-symbolic",
        indicator_module.IndicatorCategory.APPLICATION_STATUS,
    )
    indicator.set_status(indicator_module.IndicatorStatus.ACTIVE)

    menu = Gtk.Menu()

    popup_holder = []

    def show_slider_popup(_item):
        if not popup_holder:
            popup_holder.append(_build_slider_popup(monitors))
        popup_holder[0].present()

    if monitors:
        adjust_item = Gtk.MenuItem(label="Adjust Brightness…")
        adjust_item.connect("activate", show_slider_popup)
        menu.append(adjust_item)
        menu.append(Gtk.SeparatorMenuItem())

    refresh_fns = []

    if not monitors:
        empty_item = Gtk.MenuItem(label="No DDC/CI monitors detected")
        empty_item.set_sensitive(False)
        menu.append(empty_item)
    else:
        for monitor in monitors:
            item, refresh_fn = _build_monitor_menu_item(monitor)
            menu.append(item)
            refresh_fns.append(refresh_fn)

    menu.append(Gtk.SeparatorMenuItem())

    quit_item = Gtk.MenuItem(label="Quit")
    quit_item.connect("activate", lambda _item: Gtk.main_quit())
    menu.append(quit_item)

    def refresh_all(_menu):
        for refresh_fn in refresh_fns:
            refresh_fn()

    menu.connect("show", refresh_all)

    menu.show_all()
    indicator.set_menu(menu)

    # Keep a reference alive for the lifetime of the app.
    global _indicator_ref
    _indicator_ref = indicator

    return True


def _show_error_dialog(message: str):
    dialog = Gtk.MessageDialog(
        transient_for=None,
        flags=0,
        message_type=Gtk.MessageType.ERROR,
        buttons=Gtk.ButtonsType.OK,
        text="Monitorian",
    )
    dialog.format_secondary_text(message)
    dialog.run()
    dialog.destroy()


def main():
    if not ddc.ddcutil_available():
        _show_error_dialog(
            "ddcutil was not found or did not run successfully.\n\n"
            "Install it with: sudo apt install ddcutil\n"
            "See README.md for full setup instructions."
        )
        sys.exit(1)

    monitors = ddc.detect_monitors()

    if not try_build_tray(monitors):
        window = build_panel_window(monitors)
        window.show_all()

    Gtk.main()


if __name__ == "__main__":
    main()
