"""DDC/CI monitor control via the ddcutil CLI."""

import re
import subprocess
from dataclasses import dataclass

VCP_BRIGHTNESS = "10"


@dataclass
class Monitor:
    display_num: int
    description: str
    brightness: int = 50
    max_brightness: int = 100


def ddcutil_available() -> bool:
    try:
        result = subprocess.run(
            ["ddcutil", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def detect_monitors() -> list[Monitor]:
    try:
        result = subprocess.run(
            ["ddcutil", "detect", "--brief"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return []

    monitors = []
    display_num = None
    monitor_line = None

    def flush():
        if display_num is not None:
            monitors.append(_finish_monitor(display_num, monitor_line))

    for line in result.stdout.splitlines():
        display_match = re.match(r"^Display (\d+)", line)
        if display_match:
            flush()
            display_num = int(display_match.group(1))
            monitor_line = None
            continue

        if re.match(r"^Invalid display", line):
            # e.g. a laptop's built-in eDP panel, which has no DDC/CI support.
            flush()
            display_num = None
            monitor_line = None
            continue

        if display_num is None:
            continue

        stripped = line.strip()
        match = re.match(r"^Monitor:\s*(.*)$", stripped)
        if match:
            monitor_line = match.group(1)

    flush()

    return monitors


def _finish_monitor(display_num: int, monitor_line: str | None) -> Monitor:
    monitor = Monitor(
        display_num=display_num,
        description=_describe(monitor_line) or f"Display {display_num}",
    )
    current, maximum = get_brightness(monitor)
    if current is not None:
        monitor.brightness = current
    if maximum is not None:
        monitor.max_brightness = maximum
    return monitor


def _describe(monitor_line: str | None) -> str | None:
    """monitor_line looks like 'MFG:Model:Serial' — prefer the model name."""
    if not monitor_line:
        return None
    parts = monitor_line.split(":")
    if len(parts) >= 2:
        mfg, model = parts[0].strip(), parts[1].strip()
        return model or mfg or None
    return monitor_line.strip() or None


def get_brightness(monitor: Monitor) -> tuple[int | None, int | None]:
    try:
        result = subprocess.run(
            ["ddcutil", "getvcp", VCP_BRIGHTNESS, "--terse", "--display", str(monitor.display_num)],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None, None

    if result.returncode != 0:
        return None, None

    # Typical line: "VCP 10 C 37 100"
    match = re.search(r"VCP\s+\S+\s+[A-Z]\s+(\d+)\s+(\d+)", result.stdout)
    if not match:
        return None, None

    return int(match.group(1)), int(match.group(2))


def set_brightness(monitor: Monitor, value: int) -> bool:
    value = max(0, min(100, value))
    try:
        result = subprocess.run(
            ["ddcutil", "setvcp", VCP_BRIGHTNESS, str(value), "--display", str(monitor.display_num)],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False

    return result.returncode == 0
