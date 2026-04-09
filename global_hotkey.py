"""System-wide hotkey (macOS) to bring the SSH Term window forward."""

from __future__ import annotations

import sys
import threading
from typing import Any


def start_global_hotkey_macos(bridge: Any) -> bool:
    """Start **⌘D** → ``bridge.show_requested.emit()`` on a background thread.

    ``bridge`` must be a Qt ``QObject`` with a ``show_requested`` signal. Emits
    from the listener thread are queued to the GUI thread when the connection
    uses ``Qt.ConnectionType.QueuedConnection``.

    On macOS, grant **Input Monitoring** to Terminal / Python (dev) or to
    **SSH Term.app** (frozen) under *System Settings → Privacy & Security*.

    Returns ``False`` when not on macOS or *pynput* is not installed.
    """
    if sys.platform != "darwin":
        return False
    try:
        from pynput import keyboard
    except ImportError:
        return False

    def on_hotkey() -> None:
        bridge.show_requested.emit()

    def run_listener() -> None:
        with keyboard.GlobalHotKeys({"<cmd>+d": on_hotkey}) as hotkeys:
            hotkeys.join()

    threading.Thread(
        target=run_listener,
        daemon=True,
        name="ssh-term-global-hotkey",
    ).start()
    return True
