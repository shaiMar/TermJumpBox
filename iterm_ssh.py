"""Build SSH shell commands and open them in a new iTerm2 tab via AppleScript."""

from __future__ import annotations

import shlex
import shutil
import subprocess
from pathlib import Path

from storage import KeyEntry, Server


def _applescript_string_literal(s: str) -> str:
    """Escape for use inside AppleScript double-quoted string."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def key_path_for_server(server: Server, keys: list[KeyEntry]) -> str | None:
    if server.auth != "key" or not server.key_id:
        return None
    for k in keys:
        if k.id == server.key_id:
            return k.path
    return None


def build_ssh_shell_line(
    server: Server,
    keys: list[KeyEntry],
) -> tuple[str, str]:
    """Returns (shell_line, error_message). error_message empty on success."""
    ssh_args: list[str] = ["ssh"]

    if server.port != 22:
        ssh_args.extend(["-p", str(server.port)])

    if server.auth == "key":
        kp = key_path_for_server(server, keys)
        if not kp or not kp.strip():
            return "", "No SSH key is selected, or the key entry was removed."
        key = Path(kp).expanduser()
        ssh_args.extend(["-i", str(key), "-o", "IdentitiesOnly=yes"])

    target = f"{server.username}@{server.host}"

    if server.auth == "password":
        password = (server.password or "").strip() or None
        if password and shutil.which("sshpass"):
            ssh_part = " ".join(shlex.quote(a) for a in ssh_args)
            return (
                f"sshpass -p {shlex.quote(password)} {ssh_part} {shlex.quote(target)}",
                "",
            )
        ssh_args.append(target)
        return " ".join(shlex.quote(a) for a in ssh_args), ""

    ssh_args.append(target)
    return " ".join(shlex.quote(a) for a in ssh_args), ""


def open_iterm_with_command(
    command: str,
    *,
    tab_title: str | None = None,
) -> tuple[bool, str]:
    """Tell iTerm2 to open a new tab, optionally set its title, then run `command`.

    Uses \"create tab ... command\" so iTerm runs the shell command directly instead of
    typing into an interactive shell. That avoids racey \"write text\" (duplicate lines,
    broken prompts) and avoids embedding OSC/printf noise in scrollback.
    """
    if not shutil.which("osascript"):
        return False, "osascript not found (expected on macOS)."

    if "\n" in command or "\r" in command:
        return False, "Command contains invalid characters."

    if tab_title is not None:
        t = tab_title.strip()
        if "\n" in t or "\r" in t:
            return False, "Tab title contains invalid characters."

    escaped_cmd = _applescript_string_literal(command)
    title_block = ""
    if tab_title is not None:
        ts = tab_title.strip()
        if ts:
            esc_title = _applescript_string_literal(ts)
            title_block = f"""
    tell current session of current tab
      set name to "{esc_title}"
    end tell"""
    script = f"""
tell application "iTerm2"
  activate
  if (count of windows) = 0 then
    create window with default profile
  end if
  tell current window
    create tab with default profile command "{escaped_cmd}"{title_block}
  end tell
end tell
"""
    try:
        subprocess.run(
            ["osascript", "-e", script],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        err = (e.stderr or e.stdout or "").strip()
        if not err:
            err = str(e)
        return False, f"iTerm2 / AppleScript error: {err}"
    return True, ""


def connect_server(server: Server, keys: list[KeyEntry]) -> tuple[bool, str]:
    line, err = build_ssh_shell_line(server, keys)
    if err:
        return False, err
    return open_iterm_with_command(line, tab_title=server.name)
