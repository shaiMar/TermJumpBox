# SSH Term

Small macOS-friendly desktop app to keep a list of SSH servers, shared private key entries, and optional password auth. Organize entries in **folders and subfolders** in the sidebar tree. Double-click a server (or press Enter) to open a new **iTerm2** tab and run `ssh` with the right user, port, key, or password helper. **Open https** (toolbar or server context menu) opens the default browser at **`https://`** plus the same **host** you use for SSH (IPv6 addresses are bracketed automatically). The tab title is set to the **server name** (as shown in the app).

## Requirements

- **macOS** (uses AppleScript to drive iTerm2)
- **Python 3.10+**
- **[iTerm2](https://iterm2.com/)** installed
- **PySide6** (Qt) for the UI — see `requirements.txt`
- **PyObjC** (`pyobjc-framework-Cocoa` on macOS) for **View → Hide Dock icon** and **native ⌘E** (AppKit `NSEvent` global + local monitors)
- **pynput** (macOS only, optional) — **fallback** for ⌘E if the native path is unavailable

## Quick start

```bash
cd /path/to/sshTerm
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
./launch.sh
```

Or run `python main.py` after activating the venv.

### `launch.sh` (detached from the terminal)

By default, `./launch.sh` does **not** use `exec`: it starts `main.py` under **`nohup`** in the background and **`disown`**s the job so that:

- Your **shell returns a prompt immediately** (the terminal is not “held” until you quit the app).
- The process is **not tied to that shell session**, so it usually **keeps running** if you close the terminal tab/window.
- **Stdout and stderr** are appended to **`~/.config/ssh-term/launch.log`** (the config directory is created if needed).

For **foreground** mode (blocks the terminal, useful for debugging, same as running `python main.py` directly):

```bash
SSH_TERM_FG=1 ./launch.sh
```

The script prefers **`.venv/bin/python`** when the venv exists; otherwise **`python3`** on `PATH`.

### Desktop shortcut (Finder)

The installer builds a **real `SSH Term.app`** on your Desktop: it **`exec`s Python → `main.py`** inside the bundle (same as a normal GUI app). That gives a valid **WindowServer** session so the window, **Dock**, and **global ⌘E** behave; it does **not** use AppleScript `do shell script` + `nohup` (that path often breaks the UI and hotkeys).

```bash
./scripts/install-desktop-launcher.sh
```

Run it again if you **move the repo** (the app embeds the clone path). It removes any legacy **`SSH Term.command`**.

**⌘E / privacy (Desktop app):** allow **`SSH Term`** under **Accessibility** so ⌘E works while other apps are focused. macOS may also show **Input Monitoring**; enable it if prompted. Permissions are **per app** — the Desktop **`SSH Term.app`** is separate from **Terminal** / **Python** when you run from a venv. **Quit and reopen** once after changing toggles.

Delete **`SSH Term.app`** from the Desktop to remove the shortcut. If Gatekeeper blocks it the first time, use **right‑click → Open**.

## Data files

Configuration lives under **`~/.config/ssh-term/`**:

| File         | Contents |
|-------------|----------|
| `servers.json` | Server entries (host, user, port, auth type, key id, folder id, obfuscated password if used) |
| `keys.json`    | Named SSH private key paths (many servers can share one key id) |
| `folders.json` | Folder tree (`name`, `parent_id`; empty parent means top level) |
| `preferences.json` | UI prefs (`hide_dock_icon`, `window_geometry_b64`, `tree_column_widths`) |
| `launch.log` | Output from **`./launch.sh`** when not using `SSH_TERM_FG=1` |

Use **Add folder…** / **Add server…** with a row selected to create a subfolder or server inside that folder (or choose **Folder** in the server dialog). A folder must be empty (no servers, no subfolders) before you delete it.

**Right-click** the tree for the same actions in a context menu: on empty space you get **New folder** and **Add server** at the root (plus **SSH keys…**). On a folder or server row you get connect / edit / duplicate / delete and folder creation options appropriate to that row.

**Drag and drop**: drag a **server** onto a **folder** to move it into that folder; onto another **server** to share that server’s folder; onto **empty tree space** to move it to the **root**. Folders are not draggable.

Passwords are stored with a **fixed in-app obfuscation** (XOR + base64, prefix `enc1:`). That is not strong encryption; anyone with this repo can decode them. It only reduces casual exposure in the JSON file.

## SSH keys vs passwords

- **Key auth**: pick a key from the shared list or add one (label + path to private key). The app runs `ssh -i … -o IdentitiesOnly=yes`.
- **Password auth**: stored obfuscated in `servers.json`. For non-interactive login, **`sshpass`** must be installed (for example `brew install hudochenkov/sshpass/sshpass`). Otherwise iTerm opens plain `ssh user@host` and you type the password when prompted.

## Dark theme

The app uses Qt’s **Fusion** style with a built-in **dark palette** (no extra packages).

## Permissions

The first time you connect, macOS may ask to allow **Automation** so the app (or the terminal you launched it from) can control **iTerm2**.

**Hide Dock icon**: Use **View → Hide Dock icon** to run as an accessory app (no Dock tile). The choice is saved in `preferences.json`. Toggle off to show the app in the Dock again.

**Background launcher**: On macOS, if **⌘E registration** succeeds (native `NSEvent` and/or **pynput**), the app starts with **no open window**; **⌘E** or **View → Show window** brings it forward. The close box only **hides** the window; the process keeps running until **View → Quit** or **⌘Q** while the app is focused. If **both** hotkey paths fail, the main window **opens on launch** so the UI is still reachable.

**Global ⌘E**: The app uses **NSEvent** (PyObjC) for ⌘E when possible. Allow **SSH Term** under **Accessibility** so keystrokes can be observed while you use other apps; macOS may also list **Input Monitoring**. Enable **Python** or **Terminal** too when you run `main.py` from a shell. Other focused apps may consume ⌘E before the OS delivers it.

## macOS .pkg installer

From a clone of this repo on a Mac:

```bash
./scripts/build-macos-pkg.sh 0.1.0
```

This creates **`dist/SSH Term.app`** and **`dist/SSH-Term-0.1.0.pkg`**. The package installs the app into **`/Applications`**. It is **not** code-signed or notarized; users may need to **right-click → Open** the app or installer the first time. For distribution outside the App Store, use your own Apple Developer ID signing and notarization workflow.

## Project layout

- `assets/app_icon.png` — window / app icon (replace to customize)
- `main.py` — Qt UI
- `global_hotkey.py` — system-wide ⌘E on macOS (**NSEvent** via PyObjC, **pynput** fallback)
- `macos_dock.py` — optional Dock visibility (macOS / PyObjC)
- `macos_reopen.py` — Dock / activate: show main window when the app is brought forward (macOS / Qt)
- `storage.py` — JSON load/save, password encode/decode
- `iterm_ssh.py` — builds the `ssh` command and runs AppleScript against iTerm2
- `launch.sh` — starts `main.py` in the **background** by default (see **Quick start**); uses venv python when available
- `scripts/build-macos-pkg.sh` — PyInstaller + `pkgbuild` for `.app` / `.pkg`
- `scripts/install-desktop-launcher.sh` — builds `~/Desktop/SSH Term.app` that **`exec`s venv/system `python` → `main.py`** (no Terminal; not the same as `launch.sh`)

## License

No license is bundled here; add one if you redistribute the project.
