# Monitorian for Linux

A small GNOME/Ubuntu clone of the Windows app [Monitorian](https://github.com/emoacht/Monitorian):
a tray icon that pops up a brightness slider for each DDC/CI-capable external
monitor. It talks to monitors via [`ddcutil`](https://www.ddcutil.com/) — no
direct I2C/C bindings, just subprocess calls.

## Install dependencies

```sh
sudo apt install ddcutil python3-gi gir1.2-gtk-3.0 gir1.2-ayatanaappindicator3-0.1
```

If `gir1.2-ayatanaappindicator3-0.1` isn't available on your distro/version,
the app also supports the older `gir1.2-appindicator3-0.1` package.

## Tray icon support (GNOME)

Stock GNOME Shell does not render AppIndicator tray icons. Install the
**"AppIndicator and KStatusNotifierItem Support"** extension from
[extensions.gnome.org](https://extensions.gnome.org/extension/615/appindicator-support/)
and enable it. Without this extension, the app still works — it falls back
to an always-on-top window instead of a tray popup.

## Enable DDC/CI access (no sudo required at runtime)

1. Load the `i2c-dev` kernel module:

   ```sh
   sudo modprobe i2c-dev
   ```

   Persist it across reboots:

   ```sh
   echo i2c-dev | sudo tee -a /etc/modules
   ```

2. Add your user to the `i2c` group so you don't need root to talk to the
   monitor:

   ```sh
   sudo usermod -aG i2c "$USER"
   ```

   Log out and back in (or reboot) for the group change to take effect.

3. Add a udev rule so `/dev/i2c-*` devices are group-readable/writable by
   `i2c` on creation:

   ```sh
   echo 'KERNEL=="i2c-[0-9]*", GROUP="i2c", MODE="0660"' | sudo tee /etc/udev/rules.d/45-ddcutil-i2c.rules
   sudo udevadm control --reload-rules
   sudo udevadm trigger
   ```

## Test before running the app

Confirm `ddcutil` can see your monitor(s) first:

```sh
ddcutil detect
```

You should see one or more `Display N` entries with a description (make and
model). If it reports no displays, check that:

- The monitor is connected via a DDC/CI-capable input (many docks/hubs and
  some HDMI switches block DDC/CI).
- DDC/CI is enabled in the monitor's on-screen menu (often under an
  "Other Settings" or "PC/DDC-CI" option).
- The `i2c-dev` module is loaded (`lsmod | grep i2c_dev`) and your user is
  in the `i2c` group (`groups`).

## Run

```sh
python3 main.py
```

- If a tray indicator library is available (and the GNOME extension above
  is enabled), the app runs as a tray icon with a popup panel.
- Otherwise it falls back to a small always-on-top window.
- If `ddcutil` isn't installed or doesn't run, a dialog explains what to
  install.
- If no DDC/CI monitors are detected, the panel shows a message instead of
  crashing.

## Install as a desktop app

A `monitorian.desktop` launcher is included so the app shows up in the
GNOME app grid/search like any other installed app, instead of needing a
terminal.

```sh
mkdir -p ~/.local/share/applications
cp monitorian.desktop ~/.local/share/applications/
update-desktop-database ~/.local/share/applications 2>/dev/null
```

Then search for "Monitorian" in the GNOME Activities overview.

The launcher's `Exec` line points at this project's absolute path
(`/run/media/gamal/WorkData/Projects/brightness/main.py`). If you move the
project, edit `Exec=` in `monitorian.desktop` (and re-copy it) to match the
new location.

## Files

- `ddc_backend.py` — all `ddcutil` subprocess calls: detecting monitors,
  reading/setting brightness.
- `main.py` — GTK UI: sliders, tray icon / fallback window, debounced
  brightness updates (~400ms after you stop dragging).
- `monitorian.desktop` — desktop launcher entry (see "Install as a desktop
  app" above).
