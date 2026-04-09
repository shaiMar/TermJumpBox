# SSH Term

Small macOS-friendly desktop app to keep a list of SSH servers, shared private key entries, and optional password auth. Double-click a server (or press Enter) to open a new **iTerm2** tab and run `ssh` with the right user, port, key, or password helper.

## Requirements

- **macOS** (uses AppleScript to drive iTerm2)
- **Python 3.10+**
- **[iTerm2](https://iterm2.com/)** installed
- **PySide6** (Qt) for the UI — see `requirements.txt`

## Quick start

```bash
cd /path/to/sshTerm
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
./launch.sh
```

Or run `python main.py` after activating the venv.

## Data files

Configuration lives under **`~/.config/ssh-term/`**:

| File         | Contents |
|-------------|----------|
| `servers.json` | Server entries (host, user, port, auth type, key id, obfuscated password if used) |
| `keys.json`    | Named SSH private key paths (many servers can share one key id) |

Passwords are stored with a **fixed in-app obfuscation** (XOR + base64, prefix `enc1:`). That is not strong encryption; anyone with this repo can decode them. It only reduces casual exposure in the JSON file.

## SSH keys vs passwords

- **Key auth**: pick a key from the shared list or add one (label + path to private key). The app runs `ssh -i … -o IdentitiesOnly=yes`.
- **Password auth**: stored obfuscated in `servers.json`. For non-interactive login, **`sshpass`** must be installed (for example `brew install hudochenkov/sshpass/sshpass`). Otherwise iTerm opens plain `ssh user@host` and you type the password when prompted.

## Permissions

The first time you connect, macOS may ask to allow **Automation** so the app (or the terminal you launched it from) can control **iTerm2**.

## Project layout

- `main.py` — Qt UI
- `storage.py` — JSON load/save, password encode/decode
- `iterm_ssh.py` — builds the `ssh` command and runs AppleScript against iTerm2
- `launch.sh` — runs `main.py` with the local venv if present

## License

No license is bundled here; add one if you redistribute the project.
