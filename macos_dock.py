"""Toggle macOS Dock presence via NSApplication activation policy."""

from __future__ import annotations

import sys


def dock_toggle_available() -> bool:
    if sys.platform != "darwin":
        return False
    try:
        import AppKit  # noqa: F401
    except ImportError:
        return False
    return True


def set_hide_dock_icon(hide: bool) -> bool:
    """If ``hide`` is True, remove the app from the Dock (accessory policy).

    Returns whether AppKit reports success. No-op (returns False) when not on
    macOS or PyObjC is missing.
    """
    if sys.platform != "darwin":
        return False
    try:
        from AppKit import (
            NSApplication,
            NSApplicationActivationPolicyAccessory,
            NSApplicationActivationPolicyRegular,
        )
    except ImportError:
        return False
    pol = (
        NSApplicationActivationPolicyAccessory
        if hide
        else NSApplicationActivationPolicyRegular
    )
    ns_app = NSApplication.sharedApplication()
    return bool(ns_app.setActivationPolicy_(pol))
