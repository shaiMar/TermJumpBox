#!/usr/bin/env python3
"""SSH server manager: double-click opens iTerm2 with ssh command."""

from __future__ import annotations

import shutil
import sys
import uuid
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QDropEvent, QIcon, QKeySequence, QPalette, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
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
    QMenu,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QFileDialog,
    QVBoxLayout,
    QWidget,
)

import iterm_ssh
from storage import (
    Folder,
    KeyEntry,
    Server,
    load_app_state,
    new_folder_id,
    new_server_id,
    save_folders,
    save_keys,
    save_servers,
    servers_using_key,
)


def _folder_combo_rows(
    folders: list[Folder],
    *,
    exclude_ids: frozenset[str] | set[str] | None = None,
) -> list[tuple[str, str]]:
    """`(label, folder_id)` for a combo box; empty id means root."""
    ex = exclude_ids or set()
    rows: list[tuple[str, str]] = [("— Root —", "")]
    by_parent: dict[str, list[Folder]] = {}
    for f in folders:
        by_parent.setdefault(f.parent_id, []).append(f)

    def walk(parent_id: str, prefix: str) -> None:
        for f in sorted(by_parent.get(parent_id, []), key=lambda x: x.name.lower()):
            if f.id not in ex:
                rows.append((f"{prefix}{f.name}", f.id))
            walk(f.id, prefix + "    ")

    walk("", "")
    return rows


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


class FolderEditDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None,
        main: "MainWindow",
        *,
        title: str,
        folder: Folder | None = None,
        default_parent_id: str = "",
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self._main = main
        self.result_folder: Folder | None = None
        self._existing = folder
        self._folder_id = folder.id if folder else new_folder_id()

        self._name = QLineEdit(folder.name if folder else "")

        self._parent_combo: QComboBox | None = None
        form = QFormLayout()
        form.addRow("Name", self._name)
        if folder is None:
            self._parent_combo = QComboBox()
            for label, fid in _folder_combo_rows(main.folders):
                self._parent_combo.addItem(label, fid)
            sel = default_parent_id or ""
            for i in range(self._parent_combo.count()):
                if self._parent_combo.itemData(i) == sel:
                    self._parent_combo.setCurrentIndex(i)
                    break
            form.addRow("Parent folder", self._parent_combo)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.accepted.connect(self._try_accept)
        buttons.rejected.connect(self.reject)

        outer = QVBoxLayout(self)
        outer.addLayout(form)
        outer.addWidget(buttons)

    def _try_accept(self) -> None:
        name = self._name.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation", "Folder name is required.")
            return
        parent_id = ""
        if self._existing is None and self._parent_combo is not None:
            i = self._parent_combo.currentIndex()
            if i >= 0:
                d = self._parent_combo.itemData(i)
                parent_id = str(d) if d is not None else ""
        elif self._existing is not None:
            parent_id = self._existing.parent_id
        self.result_folder = Folder(id=self._folder_id, name=name, parent_id=parent_id)
        self.accept()


def run_folder_dialog(
    parent: QWidget | None,
    main: "MainWindow",
    *,
    title: str,
    folder: Folder | None = None,
    default_parent_id: str = "",
) -> Folder | None:
    dlg = FolderEditDialog(
        parent,
        main,
        title=title,
        folder=folder,
        default_parent_id=default_parent_id,
    )
    if dlg.exec() == QDialog.DialogCode.Accepted:
        return dlg.result_folder
    return None


class ServerDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None,
        main: "MainWindow",
        *,
        title: str,
        server: Server | None = None,
        default_folder_id: str = "",
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

        self._folder_combo = QComboBox()
        for label, fid in _folder_combo_rows(self._main.folders):
            self._folder_combo.addItem(label, fid)
        target_fid = (server.folder_id if server else default_folder_id) or ""
        for i in range(self._folder_combo.count()):
            if self._folder_combo.itemData(i) == target_fid:
                self._folder_combo.setCurrentIndex(i)
                break

        form = QFormLayout()
        form.addRow("Name", self._name)
        form.addRow("Host", self._host)
        form.addRow("Port", self._port)
        form.addRow("Username", self._user)
        form.addRow("Folder", self._folder_combo)
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

        fi = self._folder_combo.currentIndex()
        folder_id = ""
        if fi >= 0:
            d = self._folder_combo.itemData(fi)
            folder_id = str(d) if d is not None else ""

        server = Server(
            id=sid,
            name=name,
            host=host,
            port=port,
            username=user,
            auth=auth,  # type: ignore[arg-type]
            key_id=key_id if auth == "key" else "",
            password=password_field,
            folder_id=folder_id,
        )

        self.result_server = server
        self.accept()


def run_server_dialog(
    parent: QWidget | None,
    main: "MainWindow",
    *,
    title: str,
    server: Server | None = None,
    default_folder_id: str = "",
) -> Server | None:
    dlg = ServerDialog(
        parent,
        main,
        title=title,
        server=server,
        default_folder_id=default_folder_id,
    )
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


class ServerTreeWidget(QTreeWidget):
    """Tree with internal drag-and-drop to reparent servers into folders."""

    def __init__(self, main: "MainWindow"):
        super().__init__()
        self._main = main
        self._drag_sources: list[QTreeWidgetItem] = []

    def startDrag(self, supportedActions: Qt.DropAction) -> None:
        self._drag_sources = list(self.selectedItems())
        super().startDrag(supportedActions)

    def dropEvent(self, event: QDropEvent) -> None:
        if event.source() is not self:
            super().dropEvent(event)
            return
        sources = self._drag_sources
        self._drag_sources = []
        if not sources:
            event.ignore()
            return
        pt = event.position().toPoint()
        target = self.itemAt(pt)
        new_fid = self._main._folder_id_for_tree_drop(target)
        changed = False
        for src in sources:
            d = src.data(0, MainWindow._TREE_ROLE)
            if not d or d[0] != "server":
                continue
            sid = d[1]
            for i, srv in enumerate(self._main.servers):
                if srv.id == sid:
                    if srv.folder_id != new_fid:
                        self._main.servers[i] = replace(srv, folder_id=new_fid)
                        changed = True
                    break
        if changed:
            save_servers(self._main.servers)
            self._main._populate_tree()
        event.acceptProposedAction()


class MainWindow(QMainWindow):
    _TREE_ROLE = Qt.ItemDataRole.UserRole

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("SSH Term")
        self.resize(780, 440)
        self.servers, self.keys, self.folders = load_app_state()

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        top = QHBoxLayout()
        top.addWidget(self._btn("Add server…", self._add_server))
        top.addWidget(self._btn("Add folder…", self._add_folder))
        top.addWidget(self._btn("Edit…", self._edit_selection))
        top.addWidget(self._btn("Duplicate…", self._duplicate_server))
        top.addWidget(self._btn("Delete…", self._delete_selection))
        top.addWidget(self._btn("Connect", self._connect_selected))
        top.addSpacing(16)
        top.addWidget(self._btn("SSH keys…", self._open_keys))
        top.addStretch(1)
        hint = QLabel("Double-click a server to open iTerm2 and connect.")
        hint.setStyleSheet("color: #aaa;")
        top.addWidget(hint)
        root.addLayout(top)

        if not shutil.which("osascript"):
            warn = QLabel("Warning: osascript not found — iTerm integration needs macOS.")
            warn.setStyleSheet("color: #a30;")
            root.addWidget(warn)

        self._tree = ServerTreeWidget(self)
        self._tree.setColumnCount(3)
        self._tree.setHeaderLabels(["Name", "User @ Host", "Auth"])
        self._tree.header().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self._tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._tree.header().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._tree.setDragEnabled(True)
        self._tree.setAcceptDrops(True)
        self._tree.setDropIndicatorShown(True)
        self._tree.setDefaultDropAction(Qt.DropAction.MoveAction)
        self._tree.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._tree_context_menu)
        self._tree.itemDoubleClicked.connect(self._on_tree_double_click)
        QShortcut(QKeySequence(Qt.Key.Key_Return), self._tree, self._connect_selected)
        QShortcut(QKeySequence(Qt.Key.Key_Enter), self._tree, self._connect_selected)
        root.addWidget(self._tree, 1)

        self._populate_tree()

    @staticmethod
    def _btn(text: str, slot) -> QPushButton:
        b = QPushButton(text)
        b.clicked.connect(slot)
        return b

    def _open_keys(self) -> None:
        KeysManagerDialog(self, self).exec()

    def _tree_context_menu(self, pos: QPoint) -> None:
        item = self._tree.itemAt(pos)
        menu = QMenu(self)
        gpos = self._tree.viewport().mapToGlobal(pos)

        def add_keys() -> None:
            menu.addSeparator()
            menu.addAction("SSH keys…", self._open_keys)

        if item is None:
            menu.addAction("New folder…", lambda: self._add_folder_at_parent(""))
            menu.addAction("Add server…", lambda: self._add_server_at_folder(""))
            add_keys()
            menu.exec(gpos)
            return

        self._tree.setCurrentItem(item)
        row = item.data(0, MainWindow._TREE_ROLE)
        if not row or not isinstance(row, (list, tuple)) or len(row) != 2:
            menu.addAction("New folder…", lambda: self._add_folder_at_parent(""))
            menu.addAction("Add server…", lambda: self._add_server_at_folder(""))
            add_keys()
            menu.exec(gpos)
            return

        kind, iid = row[0], row[1]
        if kind == "folder":
            menu.addAction("New subfolder…", lambda: self._add_folder_at_parent(iid))
            menu.addAction("Add server…", lambda: self._add_server_at_folder(iid))
            menu.addSeparator()
            menu.addAction("Edit folder…", self._edit_selection)
            menu.addAction("Delete folder…", self._delete_selection)
            add_keys()
        else:
            menu.addAction("Connect", self._connect_selected)
            menu.addSeparator()
            menu.addAction("Edit server…", self._edit_selection)
            menu.addAction("Duplicate…", self._duplicate_server)
            menu.addAction("Delete server…", self._delete_selection)
            menu.addSeparator()
            s = self._server_by_id(iid)
            parent_fid = s.folder_id if s else ""
            menu.addAction(
                "New folder (same level)…",
                lambda: self._add_folder_at_parent(parent_fid),
            )
            menu.addAction(
                "Add server (same level)…",
                lambda: self._add_server_at_folder(parent_fid),
            )
            add_keys()
        menu.exec(gpos)

    def _tree_selection(self) -> tuple[str, str] | None:
        items = self._tree.selectedItems()
        if not items:
            return None
        d = items[0].data(0, MainWindow._TREE_ROLE)
        if not d or not isinstance(d, (list, tuple)) or len(d) != 2:
            return None
        kind, iid = d[0], d[1]
        if kind in ("folder", "server") and isinstance(iid, str):
            return kind, iid
        return None

    def _default_folder_id_for_new_server(self) -> str:
        sel = self._tree_selection()
        if not sel:
            return ""
        kind, iid = sel
        if kind == "folder":
            return iid
        s = self._server_by_id(iid)
        return s.folder_id if s else ""

    def _default_parent_id_for_new_folder(self) -> str:
        sel = self._tree_selection()
        if not sel:
            return ""
        kind, iid = sel
        if kind == "folder":
            return iid
        s = self._server_by_id(iid)
        return s.folder_id if s else ""

    def _populate_tree(self) -> None:
        self._tree.clear()

        def add_under(parent: QTreeWidgetItem, parent_folder_id: str) -> None:
            for f in sorted(
                [x for x in self.folders if x.parent_id == parent_folder_id],
                key=lambda x: x.name.lower(),
            ):
                fi = QTreeWidgetItem(parent)
                fi.setText(0, f.name)
                fi.setText(1, "")
                fi.setText(2, "Folder")
                fi.setData(0, MainWindow._TREE_ROLE, ("folder", f.id))
                fi.setFlags(
                    (fi.flags() | Qt.ItemFlag.ItemIsDropEnabled)
                    & ~Qt.ItemFlag.ItemIsDragEnabled
                )
                add_under(fi, f.id)
            for s in sorted(
                [x for x in self.servers if x.folder_id == parent_folder_id],
                key=lambda x: x.name.lower(),
            ):
                si = QTreeWidgetItem(parent)
                auth_label = "Key" if s.auth == "key" else "Password"
                si.setText(0, s.name)
                si.setText(1, f"{s.username}@{s.display_host()}")
                si.setText(2, auth_label)
                si.setData(0, MainWindow._TREE_ROLE, ("server", s.id))
                si.setFlags(
                    si.flags()
                    | Qt.ItemFlag.ItemIsDragEnabled
                    | Qt.ItemFlag.ItemIsDropEnabled
                )

        add_under(self._tree.invisibleRootItem(), "")
        self._tree.expandAll()

    def _server_by_id(self, sid: str) -> Server | None:
        return next((s for s in self.servers if s.id == sid), None)

    def _folder_by_id(self, fid: str) -> Folder | None:
        return next((f for f in self.folders if f.id == fid), None)

    def _folder_id_for_tree_drop(self, target: QTreeWidgetItem | None) -> str:
        """Resolve target folder id when dropping a server onto the tree."""
        if target is None:
            return ""
        d = target.data(0, MainWindow._TREE_ROLE)
        if not d or not isinstance(d, (list, tuple)) or len(d) != 2:
            return ""
        kind, iid = d[0], d[1]
        if kind == "folder":
            return iid
        if kind == "server":
            s = self._server_by_id(iid)
            return s.folder_id if s else ""
        return ""

    def _duplicate_server(self) -> None:
        sel = self._tree_selection()
        if not sel or sel[0] != "server":
            QMessageBox.information(
                self,
                "Duplicate",
                "Select a server to duplicate.",
            )
            return
        s = self._server_by_id(sel[1])
        if not s:
            return
        dup = replace(
            s,
            id=new_server_id(),
            name=f"{s.name} copy",
        )
        self.servers.append(dup)
        save_servers(self.servers)
        self._populate_tree()

    def _add_server_at_folder(self, folder_id: str) -> None:
        created = run_server_dialog(
            self,
            self,
            title="Add server",
            server=None,
            default_folder_id=folder_id,
        )
        if created:
            self.servers.append(created)
            save_servers(self.servers)
            self._populate_tree()

    def _add_server(self) -> None:
        self._add_server_at_folder(self._default_folder_id_for_new_server())

    def _add_folder_at_parent(self, parent_id: str) -> None:
        created = run_folder_dialog(
            self,
            self,
            title="New folder",
            folder=None,
            default_parent_id=parent_id,
        )
        if created:
            self.folders.append(created)
            save_folders(self.folders)
            self._populate_tree()

    def _add_folder(self) -> None:
        self._add_folder_at_parent(self._default_parent_id_for_new_folder())

    def _edit_selection(self) -> None:
        sel = self._tree_selection()
        if not sel:
            QMessageBox.information(self, "Edit", "Select a folder or server first.")
            return
        kind, iid = sel
        if kind == "server":
            s = self._server_by_id(iid)
            if not s:
                return
            updated = run_server_dialog(self, self, title="Edit server", server=s)
            if updated:
                for i, x in enumerate(self.servers):
                    if x.id == updated.id:
                        self.servers[i] = updated
                        break
                save_servers(self.servers)
                self._populate_tree()
            return
        f = self._folder_by_id(iid)
        if not f:
            return
        updated = run_folder_dialog(
            self,
            self,
            title="Rename folder",
            folder=f,
        )
        if updated:
            for i, x in enumerate(self.folders):
                if x.id == updated.id:
                    self.folders[i] = updated
                    break
            save_folders(self.folders)
            self._populate_tree()

    def _delete_selection(self) -> None:
        sel = self._tree_selection()
        if not sel:
            QMessageBox.information(self, "Delete", "Select a folder or server first.")
            return
        kind, iid = sel
        if kind == "server":
            self._delete_server_by_id(iid)
        else:
            self._delete_folder_by_id(iid)

    def _delete_server_by_id(self, sid: str) -> None:
        s = self._server_by_id(sid)
        if not s:
            return
        r = QMessageBox.question(
            self,
            "Delete",
            f"Remove server “{s.name}”?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if r != QMessageBox.StandardButton.Yes:
            return
        self.servers = [x for x in self.servers if x.id != s.id]
        save_servers(self.servers)
        self._populate_tree()

    def _delete_folder_by_id(self, fid: str) -> None:
        f = self._folder_by_id(fid)
        if not f:
            return
        if any(s.folder_id == fid for s in self.servers):
            QMessageBox.warning(
                self,
                "Cannot delete",
                "This folder still contains servers. Move or delete them first.",
            )
            return
        if any(ch.parent_id == fid for ch in self.folders):
            QMessageBox.warning(
                self,
                "Cannot delete",
                "This folder still contains subfolders. Delete or move them first.",
            )
            return
        r = QMessageBox.question(
            self,
            "Delete",
            f"Remove folder “{f.name}”?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if r != QMessageBox.StandardButton.Yes:
            return
        self.folders = [x for x in self.folders if x.id != fid]
        save_folders(self.folders)
        self._populate_tree()

    def _on_tree_double_click(self, item: QTreeWidgetItem, _column: int) -> None:
        d = item.data(0, MainWindow._TREE_ROLE)
        if d and isinstance(d, (list, tuple)) and len(d) == 2 and d[0] == "server":
            self._connect_selected()

    def _connect_selected(self) -> None:
        sel = self._tree_selection()
        if not sel or sel[0] != "server":
            QMessageBox.information(self, "Connect", "Select a server row first.")
            return
        s = self._server_by_id(sel[1])
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


def _application_icon() -> QIcon:
    path = Path(__file__).resolve().parent / "assets" / "app_icon.png"
    if path.is_file():
        return QIcon(str(path))
    return QIcon()


def apply_dark_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
    p.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
    p.setColor(QPalette.ColorRole.Base, QColor(35, 35, 35))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor(66, 66, 66))
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor(35, 35, 35))
    p.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)
    p.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
    p.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
    p.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
    p.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
    p.setColor(QPalette.ColorRole.Link, QColor(66, 156, 255))
    p.setColor(QPalette.ColorRole.Highlight, QColor(72, 118, 184))
    p.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.white)
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor(200, 200, 200))
    app.setPalette(p)


def main() -> None:
    app = QApplication(sys.argv)
    icon = _application_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)
    apply_dark_theme(app)
    w = MainWindow()
    if not icon.isNull():
        w.setWindowIcon(icon)
    w.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
