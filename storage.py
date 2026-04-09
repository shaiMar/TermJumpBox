"""Persist server list and SSH keys (JSON) under ~/.config/ssh-term/."""

from __future__ import annotations

import base64
import hashlib
import json
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

CONFIG_DIR = Path.home() / ".config" / "ssh-term"
SERVERS_FILE = CONFIG_DIR / "servers.json"
KEYS_FILE = CONFIG_DIR / "keys.json"
FOLDERS_FILE = CONFIG_DIR / "folders.json"
PREFERENCES_FILE = CONFIG_DIR / "preferences.json"

# Fixed app seed — only hides passwords from casual file viewers; not real security.
_PW_SEED = b"sshTerm.v1.password-obfuscation\x00"
_ENC_PREFIX = "enc1:"


def _stream_key() -> bytes:
    return hashlib.sha256(_PW_SEED).digest()


def _xor_stream(data: bytes) -> bytes:
    key = _stream_key()
    return bytes(data[i] ^ key[i % len(key)] for i in range(len(data)))


def _password_encode_for_storage(plain: str) -> str:
    if not plain:
        return ""
    blob = _xor_stream(plain.encode("utf-8"))
    return _ENC_PREFIX + base64.urlsafe_b64encode(blob).decode("ascii")


def _password_decode_from_storage(stored: str) -> str:
    if not stored:
        return ""
    if stored.startswith(_ENC_PREFIX):
        try:
            blob = base64.urlsafe_b64decode(stored[len(_ENC_PREFIX) :].encode("ascii"))
            return _xor_stream(blob).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return ""
    # Legacy: written as plain text before encoding existed
    return stored


@dataclass
class KeyEntry:
    id: str
    name: str
    path: str


@dataclass
class Folder:
    """Logical group for servers; `parent_id` empty means top level."""

    id: str
    name: str
    parent_id: str = ""


@dataclass
class Server:
    id: str
    name: str
    host: str
    port: int
    username: str
    auth: Literal["key", "password"]
    key_id: str
    password: str = ""
    folder_id: str = ""

    def display_host(self) -> str:
        if self.port == 22:
            return self.host
        return f"{self.host}:{self.port}"


def ensure_config() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def _norm_path(p: str) -> str:
    try:
        return str(Path(p).expanduser().resolve())
    except OSError:
        return str(Path(p).expanduser())


def load_keys() -> list[KeyEntry]:
    ensure_config()
    if not KEYS_FILE.is_file():
        return []
    raw = json.loads(KEYS_FILE.read_text(encoding="utf-8"))
    return [KeyEntry(**item) for item in raw]


def save_keys(keys: list[KeyEntry]) -> None:
    ensure_config()
    KEYS_FILE.write_text(
        json.dumps([asdict(k) for k in keys], indent=2),
        encoding="utf-8",
    )


def _migrate_server_dict(d: dict, keys: list[KeyEntry]) -> tuple[dict, bool]:
    """Normalize legacy key_path → key_id; returns (dict, changed)."""
    changed = False
    out = dict(d)
    if "key_path" in out:
        legacy = (out.pop("key_path") or "").strip()
        if out.get("auth") == "key" and legacy and not (out.get("key_id") or "").strip():
            np = _norm_path(legacy)
            found = next(
                (k for k in keys if _norm_path(k.path) == np),
                None,
            )
            if found:
                out["key_id"] = found.id
            else:
                kid = str(uuid.uuid4())
                label = Path(legacy).name or "Key"
                keys.append(KeyEntry(id=kid, name=label, path=legacy))
                out["key_id"] = kid
            changed = True
        else:
            changed = True
    if "key_id" not in out:
        out["key_id"] = ""
        if out.get("auth") == "key":
            changed = True
    if "password" not in out:
        out["password"] = ""
        if out.get("auth") == "password":
            changed = True
    if "folder_id" not in out:
        out["folder_id"] = ""
        changed = True
    return out, changed


def load_preferences() -> dict:
    """App UI prefs; keys include ``hide_dock_icon`` (bool, macOS Dock)."""
    defaults: dict = {"hide_dock_icon": False}
    ensure_config()
    if not PREFERENCES_FILE.is_file():
        return dict(defaults)
    try:
        raw = json.loads(PREFERENCES_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(defaults)
    if not isinstance(raw, dict):
        return dict(defaults)
    out = dict(defaults)
    out["hide_dock_icon"] = bool(raw.get("hide_dock_icon", False))
    return out


def save_preferences(updates: dict) -> None:
    cur = load_preferences()
    cur.update(updates)
    ensure_config()
    PREFERENCES_FILE.write_text(
        json.dumps(cur, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def load_folders() -> list[Folder]:
    ensure_config()
    if not FOLDERS_FILE.is_file():
        return []
    raw = json.loads(FOLDERS_FILE.read_text(encoding="utf-8"))
    return [Folder(**item) for item in raw]


def save_folders(folders: list[Folder]) -> None:
    ensure_config()
    FOLDERS_FILE.write_text(
        json.dumps([asdict(f) for f in folders], indent=2),
        encoding="utf-8",
    )


def load_app_state() -> tuple[list[Server], list[KeyEntry], list[Folder]]:
    """Load servers, keys, and folders; migrate legacy JSON and persist if needed."""
    keys = load_keys()
    folders = load_folders()
    ensure_config()
    if not SERVERS_FILE.is_file():
        return [], keys, folders
    raw_list = json.loads(SERVERS_FILE.read_text(encoding="utf-8"))
    migrated = False
    legacy_plain_password = False
    servers: list[Server] = []
    for raw in raw_list:
        if not isinstance(raw, dict):
            continue
        d, ch = _migrate_server_dict(raw, keys)
        migrated = migrated or ch
        pw_raw = d.get("password") or ""
        if pw_raw and not str(pw_raw).startswith(_ENC_PREFIX):
            legacy_plain_password = True
        try:
            servers.append(
                Server(
                    id=d["id"],
                    name=d["name"],
                    host=d["host"],
                    port=int(d["port"]),
                    username=d["username"],
                    auth=d["auth"],  # type: ignore[arg-type]
                    key_id=(d.get("key_id") or "").strip(),
                    password=_password_decode_from_storage(pw_raw),
                    folder_id=(d.get("folder_id") or "").strip(),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    if migrated:
        save_keys(keys)
        save_servers(servers)
    elif legacy_plain_password:
        save_servers(servers)
    return servers, keys, folders


def save_servers(servers: list[Server]) -> None:
    ensure_config()
    data = []
    for s in servers:
        row = asdict(s)
        row["password"] = _password_encode_for_storage(row.get("password") or "")
        data.append(row)
    SERVERS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def new_server_id() -> str:
    return str(uuid.uuid4())


def new_folder_id() -> str:
    return str(uuid.uuid4())


def servers_using_key(servers: list[Server], key_id: str) -> list[Server]:
    return [s for s in servers if s.auth == "key" and s.key_id == key_id]
