"""macOS: show the main window when the app becomes active (Dock click, ⌘Tab, etc.)."""

from __future__ import annotations

import sys
from typing import Any


def install_dock_click_show_window(main_window: Any, app: Any) -> None:
    """After startup, when the app activates and the window is hidden/minimized, bring it forward.

    Qt-only (no NSApplication delegate) so we do not override Qt's Cocoa integration.
    """
    if sys.platform != "darwin":
        return

    from PySide6.QtCore import QEvent, QObject, QTimer, Qt

    armed: dict[str, bool] = {"ok": False}

    def on_state(state: Qt.ApplicationState) -> None:
        if state != Qt.ApplicationState.ApplicationActive:
            return
        if not armed["ok"]:
            return
        if not main_window.isVisible() or main_window.isMinimized():
            main_window.bring_to_front()

    class _ActivateFilter(QObject):
        def eventFilter(self, obj: Any, event: Any) -> bool:
            if event.type() == QEvent.Type.ApplicationActivate:
                if armed["ok"] and (
                    not main_window.isVisible() or main_window.isMinimized()
                ):
                    main_window.bring_to_front()
            return False

    app.applicationStateChanged.connect(on_state)
    filt = _ActivateFilter(app)
    app.installEventFilter(filt)
    app._ssh_term_activation_filter = filt  # noqa: SLF001 — retain
    QTimer.singleShot(500, lambda: armed.update(ok=True))
