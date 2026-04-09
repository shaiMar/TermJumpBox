#!/usr/bin/env python3
"""SSH server manager: double-click opens iTerm2 with ssh command."""

from __future__ import annotations

import shutil
import sys
import uuid

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QFileDialog,
    QVBoxLayout,
    QWidget,
)

import iterm_ssh
from storage import (
    KeyEntry,
    Server,
    load_app_state,
    new_server_id,
    save_keys,
    save_servers,
    servers_using_key,
)


class KeyEditDialog(QDialog):
    """Add or edit a key in the shared registry."""

    def __init__(
        self,
        parent: QWidget | None,
        *,
        title: str,
        entry: KeyEntry | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self._entry_id = entry.id if entry else str(uuid.uuid4())
        self.result_entry: KeyEntry | None = None

        name = entry.name if entry else ""
        path = entry.path if entry else ""

        self._name = QLineEdit(name)
        self._path = QLineEdit(path)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._on_browse)

        path_row = QWidget()
        pl = QHBoxLayout(path_row)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.addWidget(self._path, 1)
        pl.addWidget(browse)

        form = QFormLayout()
        form.addRow("Label", self._name)
        form.addRow("Private key file", path_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.accepted.connect(self._try_accept)
        buttons.rejected.connect(self.reject)

        outer = QVBoxLayout(self)
        outer.addLayout(form)
        outer.addWidget(buttons)

    def _on_browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Private key",
            "",
            "All files (*)",
        )
        if path:
            self._path.setText(path)

    def _try_accept(self) -> None:
        name = self._name.text().strip()
        path = self._path.text().strip()
        if not name or not path:
            QMessageBox.warning(
                self,
                "Validation",
                "Label and key file are required.",
            )
            return
        self.result_entry = KeyEntry(id=self._entry_id, name=name, path=path)
        self.accept()


def run_key_edit(
    parent: QWidget | None,
    *,
    title: str,
    entry: KeyEntry | None = None,
) -> KeyEntry | None:
    dlg = KeyEditDialog(parent, title=title, entry=entry)
    if dlg.exec() == QDialog.DialogCode.Accepted:
        return dlg.result_entry
    return None


class ServerDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None,
        main: "MainWindow",
        *,
        title: str,
        server: Server | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self._main = main
        self._server_id: str | None = server.id if server else None
        self.result_server: Server | None = None

        self._name = QLineEdit(server.name if server else "")
        self._host = QLineEdit(server.host if server else "")
        self._port = QLineEdit(str(server.port) if server else "22")
        self._user = QLineEdit(server.username if server else "")

        self._radio_key = QRadioButton("SSH key")
        self._radio_pw = QRadioButton("Password")
        self._auth_group = QButtonGroup(self)
        self._auth_group.addButton(self._radio_key)
        self._auth_group.addButton(self._radio_pw)

        if server and server.auth == "password":
            self._radio_pw.setChecked(True)
        else:
            self._radio_key.setChecked(True)

        self._combo_keys = QComboBox()
        self._combo_keys.setMinimumWidth(360)
        self._new_key_btn = QPushButton("New key…")
        self._new_key_btn.clicked.connect(self._add_new_key)

        key_row = QWidget()
        kr = QHBoxLayout(key_row)
        kr.setContentsMargins(0, 0, 0, 0)
        kr.addWidget(self._combo_keys, 1)
        kr.addWidget(self._new_key_btn)

        self._existing_password = (server.password if server else "") or ""
        self._pw_label = QLabel(
            "Password (basic XOR+base64 in servers.json — not strong encryption)"
        )
        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        if server and server.auth == "password":
            self._password.setText(self._existing_password)

        self._key_block = QWidget()
        kb = QVBoxLayout(self._key_block)
        kb.setContentsMargins(0, 0, 0, 0)
        kb.addWidget(QLabel("Key"))
        kb.addWidget(key_row)

        auth_box = QGroupBox("Authentication")
        auth_layout = QVBoxLayout(auth_box)
        radio_row = QHBoxLayout()
        radio_row.addWidget(self._radio_key)
        radio_row.addWidget(self._radio_pw)
        radio_row.addStretch(1)
        auth_layout.addLayout(radio_row)
        auth_layout.addWidget(self._key_block)
        auth_layout.addWidget(self._pw_label)
        auth_layout.addWidget(self._password)

        self._radio_key.toggled.connect(lambda _: self._update_auth_visibility())
        self._radio_pw.toggled.connect(lambda _: self._update_auth_visibility())

        form = QFormLayout()
        form.addRow("Name", self._name)
        form.addRow("Host", self._host)
        form.addRow("Port", self._port)
        form.addRow("Username", self._user)
        form.addRow(auth_box)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.accepted.connect(self._try_accept)
        buttons.rejected.connect(self.reject)

        outer = QVBoxLayout(self)
        outer.addLayout(form)
        outer.addWidget(buttons)

        self._initial_key_id = (server.key_id if server else "") or ""
        self._refresh_key_combo(select_id=self._initial_key_id)
        self._update_auth_visibility()

    def _refresh_key_combo(self, *, select_id: str = "") -> None:
        self._combo_keys.clear()
        keys_sorted = sorted(self._main.keys, key=lambda k: k.name.lower())
        for k in keys_sorted:
            self._combo_keys.addItem(f"{k.name} — {k.path}", k.id)
        if select_id:
            for i in range(self._combo_keys.count()):
                if self._combo_keys.itemData(i) == select_id:
                    self._combo_keys.setCurrentIndex(i)
                    return
        if self._combo_keys.count() > 0:
            self._combo_keys.setCurrentIndex(0)

    def _current_key_id(self) -> str:
        i = self._combo_keys.currentIndex()
        if i < 0:
            return ""
        d = self._combo_keys.itemData(i)
        return str(d) if d is not None else ""

    def _add_new_key(self) -> None:
        created = run_key_edit(self, title="New SSH key", entry=None)
        if not created:
            return
        self._main.keys.append(created)
        save_keys(self._main.keys)
        self._refresh_key_combo(select_id=created.id)

    def _update_auth_visibility(self) -> None:
        use_key = self._radio_key.isChecked()
        self._key_block.setVisible(use_key)
        self._combo_keys.setEnabled(use_key)
        self._new_key_btn.setEnabled(use_key)
        self._pw_label.setVisible(not use_key)
        self._password.setVisible(not use_key)

    def _try_accept(self) -> None:
        name = self._name.text().strip()
        host = self._host.text().strip()
        if not name or not host:
            QMessageBox.warning(self, "Validation", "Name and host are required.")
            return
        try:
            port = int(self._port.text().strip() or "22")
            if not (1 <= port <= 65535):
                raise ValueError
        except ValueError:
            QMessageBox.warning(self, "Validation", "Port must be 1–65535.")
            return
        user = self._user.text().strip()
        if not user:
            QMessageBox.warning(self, "Validation", "Username is required.")
            return

        auth: str = "key" if self._radio_key.isChecked() else "password"
        key_id = ""
        if auth == "key":
            key_id = self._current_key_id()
            valid_ids = {k.id for k in self._main.keys}
            if not key_id or key_id not in valid_ids:
                QMessageBox.warning(
                    self,
                    "Validation",
                    "Choose an SSH key, or click “New key…” to add one.",
                )
                return

        sid = self._server_id or new_server_id()
        pw = self._password.text()
        password_field = ""
        if auth == "password":
            if pw:
                password_field = pw
            elif self._server_id:
                password_field = self._existing_password
            else:
                QMessageBox.warning(
                    self,
                    "Validation",
                    "Password is required for new server.",
                )
                return

        server = Server(
            id=sid,
            name=name,
            host=host,
            port=port,
            username=user,
            auth=auth,  # type: ignore[arg-type]
            key_id=key_id if auth == "key" else "",
            password=password_field,
        )

        self.result_server = server
        self.accept()


def run_server_dialog(
    parent: QWidget | None,
    main: "MainWindow",
    *,
    title: str,
    server: Server | None = None,
) -> Server | None:
    dlg = ServerDialog(parent, main, title=title, server=server)
    if dlg.exec() == QDialog.DialogCode.Accepted:
        return dlg.result_server
    return None


class KeysManagerDialog(QDialog):
    def __init__(self, parent: QWidget | None, main: "MainWindow"):
        super().__init__(parent)
        self.setWindowTitle("SSH keys")
        self.resize(680, 360)
        self._main = main

        self._table = QTableWidget(0, 2)
        self._table.setHorizontalHeaderLabels(["Label", "Path"])
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)

        add_b = QPushButton("Add…")
        add_b.clicked.connect(self._add)
        edit_b = QPushButton("Edit…")
        edit_b.clicked.connect(self._edit)
        rm_b = QPushButton("Remove")
        rm_b.clicked.connect(self._remove)
        bar = QHBoxLayout()
        bar.addWidget(add_b)
        bar.addWidget(edit_b)
        bar.addWidget(rm_b)
        bar.addStretch(1)

        outer = QVBoxLayout(self)
        outer.addWidget(self._table)
        outer.addLayout(bar)

        self._refresh()

    def _refresh(self) -> None:
        self._table.setRowCount(0)
        for k in sorted(self._main.keys, key=lambda x: x.name.lower()):
            r = self._table.rowCount()
            self._table.insertRow(r)
            a = QTableWidgetItem(k.name)
            a.setData(Qt.ItemDataRole.UserRole, k.id)
            b = QTableWidgetItem(k.path)
            self._table.setItem(r, 0, a)
            self._table.setItem(r, 1, b)

    def _selected_key_id(self) -> str | None:
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, 0)
        if item is None:
            return None
        d = item.data(Qt.ItemDataRole.UserRole)
        return str(d) if d else None

    def _add(self) -> None:
        created = run_key_edit(self, title="Add SSH key", entry=None)
        if created:
            self._main.keys.append(created)
            save_keys(self._main.keys)
            self._refresh()

    def _edit(self) -> None:
        kid = self._selected_key_id()
        if not kid:
            QMessageBox.information(self, "Keys", "Select a key first.")
            return
        entry = next((k for k in self._main.keys if k.id == kid), None)
        if not entry:
            return
        updated = run_key_edit(self, title="Edit SSH key", entry=entry)
        if not updated:
            return
        for i, k in enumerate(self._main.keys):
            if k.id == updated.id:
                self._main.keys[i] = updated
                break
        save_keys(self._main.keys)
        self._refresh()

    def _remove(self) -> None:
        kid = self._selected_key_id()
        if not kid:
            QMessageBox.information(self, "Keys", "Select a key first.")
            return
        users = servers_using_key(self._main.servers, kid)
        if users:
            names = ", ".join(s.name for s in users[:5])
            more = f" (+{len(users) - 5} more)" if len(users) > 5 else ""
            QMessageBox.critical(
                self,
                "Cannot remove",
                f"This key is used by: {names}{more}. Change those servers first.",
            )
            return
        self._main.keys = [k for k in self._main.keys if k.id != kid]
        save_keys(self._main.keys)
        self._refresh()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("SSH Term")
        self.resize(780, 440)
        self.servers, self.keys = load_app_state()

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        top = QHBoxLayout()
        top.addWidget(self._btn("Add…", self._add_server))
        top.addWidget(self._btn("Edit…", self._edit_server))
        top.addWidget(self._btn("Delete", self._delete_server))
        top.addWidget(self._btn("Connect", self._connect_selected))
        top.addSpacing(16)
        top.addWidget(self._btn("SSH keys…", self._open_keys))
        top.addStretch(1)
        hint = QLabel("Double-click a server to open iTerm2 and connect.")
        hint.setStyleSheet("color: palette(mid);")
        top.addWidget(hint)
        root.addLayout(top)

        if not shutil.which("osascript"):
            warn = QLabel("Warning: osascript not found — iTerm integration needs macOS.")
            warn.setStyleSheet("color: #a30;")
            root.addWidget(warn)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Name", "User @ Host", "Auth"])
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self._table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.itemDoubleClicked.connect(lambda _item: self._connect_selected())
        QShortcut(QKeySequence(Qt.Key.Key_Return), self._table, self._connect_selected)
        QShortcut(QKeySequence(Qt.Key.Key_Enter), self._table, self._connect_selected)
        root.addWidget(self._table, 1)

        self._refresh_server_table()

    @staticmethod
    def _btn(text: str, slot) -> QPushButton:
        b = QPushButton(text)
        b.clicked.connect(slot)
        return b

    def _open_keys(self) -> None:
        KeysManagerDialog(self, self).exec()

    def _selected_server_id(self) -> str | None:
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, 0)
        if item is None:
            return None
        d = item.data(Qt.ItemDataRole.UserRole)
        return str(d) if d else None

    def _server_by_id(self, sid: str) -> Server | None:
        return next((s for s in self.servers if s.id == sid), None)

    def _refresh_server_table(self) -> None:
        self._table.setRowCount(0)
        for s in sorted(self.servers, key=lambda x: x.name.lower()):
            r = self._table.rowCount()
            self._table.insertRow(r)
            auth_label = "Key" if s.auth == "key" else "Password"
            a = QTableWidgetItem(s.name)
            a.setData(Qt.ItemDataRole.UserRole, s.id)
            self._table.setItem(r, 0, a)
            self._table.setItem(
                r,
                1,
                QTableWidgetItem(f"{s.username}@{s.display_host()}"),
            )
            self._table.setItem(r, 2, QTableWidgetItem(auth_label))

    def _add_server(self) -> None:
        created = run_server_dialog(self, self, title="Add server", server=None)
        if created:
            self.servers.append(created)
            save_servers(self.servers)
            self._refresh_server_table()

    def _edit_server(self) -> None:
        sid = self._selected_server_id()
        if not sid:
            QMessageBox.information(self, "Edit", "Select a server first.")
            return
        s = self._server_by_id(sid)
        if not s:
            return
        updated = run_server_dialog(self, self, title="Edit server", server=s)
        if not updated:
            return
        for i, x in enumerate(self.servers):
            if x.id == updated.id:
                self.servers[i] = updated
                break
        save_servers(self.servers)
        self._refresh_server_table()

    def _delete_server(self) -> None:
        sid = self._selected_server_id()
        if not sid:
            QMessageBox.information(self, "Delete", "Select a server first.")
            return
        s = self._server_by_id(sid)
        if not s:
            return
        r = QMessageBox.question(
            self,
            "Delete",
            f"Remove “{s.name}” from the list?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if r != QMessageBox.StandardButton.Yes:
            return
        self.servers = [x for x in self.servers if x.id != s.id]
        save_servers(self.servers)
        self._refresh_server_table()

    def _connect_selected(self) -> None:
        sid = self._selected_server_id()
        if not sid:
            QMessageBox.information(self, "Connect", "Select a server first.")
            return
        s = self._server_by_id(sid)
        if not s:
            return
        ok, msg = iterm_ssh.connect_server(s, self.keys)
        if not ok:
            QMessageBox.critical(self, "Connect failed", msg)
        elif s.auth == "password" and not shutil.which("sshpass"):
            QMessageBox.information(
                self,
                "Password login",
                "Opened in iTerm2. For automatic password entry, install sshpass "
                "(e.g. brew install hudochenkov/sshpass/sshpass); otherwise type the "
                "password when ssh prompts.",
            )


def main() -> None:
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
