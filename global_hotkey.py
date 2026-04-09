"""System-wide ⌘E (macOS) to bring the SSH Term window forward."""

from __future__ import annotations

import sys
import threading
from typing import Any


def start_native_cmd_e_hotkey(bridge: Any, qapp: Any) -> bool:
    """Register **NSEvent** global + local key monitors for ⌘E.

    - **Local** monitor: keystrokes while this app is active (global monitors do not
      receive those). Needed when the window is hidden but SSH Term still has focus.
    - **Global** monitor: keystrokes while another app is focused. Requires
      **Accessibility** under *System Settings → Privacy & Security*.

    Retains monitor objects on ``qapp`` so they are not garbage-collected.
    """
    if sys.platform != "darwin":
        return False
    try:
        from AppKit import (
            NSEvent,
            NSEventMaskKeyDown,
            NSEventModifierFlagCommand,
        )
    except ImportError:
        return False

    def is_cmd_e(event: Any) -> bool:
        try:
            if int(event.modifierFlags()) & NSEventModifierFlagCommand == 0:
                return False
            chars = (event.charactersIgnoringModifiers() or "").lower()
            if chars == "e":
                return True
            if not chars.strip():
                return int(event.keyCode()) == 14  # US QWERTY if chars missing
            return False
        except (AttributeError, TypeError, ValueError):
            return False

    def on_global(event: Any) -> None:
        if is_cmd_e(event):
            bridge.show_requested.emit()

    def on_local(event: Any) -> Any:
        if is_cmd_e(event):
            bridge.show_requested.emit()
        return event

    any_ok = False
    gmon = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
        NSEventMaskKeyDown,
        on_global,
    )
    if gmon is not None:
        any_ok = True
    lmon = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
        NSEventMaskKeyDown,
        on_local,
    )
    if lmon is not None:
        any_ok = True

    if any_ok:
        qapp._ssh_term_nsevent_cmd_e = (gmon, lmon)  # noqa: SLF001 — retain monitors
    return any_ok


def start_pynput_cmd_e_hotkey(bridge: Any) -> bool:
    """Fallback ⌘E using **pynput** (often flaky for .app bundles)."""
    if sys.platform != "darwin":
        return False
    try:
        from pynput import keyboard
    except ImportError:
        return False

    def on_hotkey() -> None:
        bridge.show_requested.emit()

    def run_listener() -> None:
        with keyboard.GlobalHotKeys({"<cmd>+e": on_hotkey}) as hotkeys:
            hotkeys.join()

    threading.Thread(
        target=run_listener,
        daemon=True,
        name="ssh-term-pynput-hotkey",
    ).start()
    return True


def start_global_hotkey_macos(bridge: Any, qapp: Any | None = None) -> bool:
    """Prefer **NSEvent** + ``qapp``; if unavailable, try **pynput**."""
    if sys.platform != "darwin":
        return False
    if qapp is not None and start_native_cmd_e_hotkey(bridge, qapp):
        return True
    return start_pynput_cmd_e_hotkey(bridge)
