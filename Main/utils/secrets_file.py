"""Reading, and (for the API token only) writing, the SECRETS file at the top of the program folder.

SECRETS is a shell-style file of KEY="value" lines (see SECRETS.template) and is never put in git.
The server creates its own API token here the first time it runs, so there is nothing to install
or generate by hand: look at the file on the speaker to read it and type it into the app.
"""

import os
import secrets

TOKEN_KEY = "DEBUG_TOKEN"
MIN_TOKEN_LENGTH = 8  # shorter than this counts as "not set"
NEW_TOKEN_BYTES = 12  # 16 characters, 96 bits: easy to type once on a phone, impossible to guess


def read_secret(path: str, key: str) -> str:
    """One value from the file, or '' if the file or the key is missing."""
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                if k.strip() == key:
                    v = v.strip()
                    if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
                        v = v[1:-1]
                    return v
    except OSError:
        pass
    return ""


def ensure_token(path: str, key: str = TOKEN_KEY):
    """The API token, made and saved if there is none. Returns (token, created, problem).

    `problem` is None, or a sentence saying the new token could not be saved. In that case the
    token is good for this run only, and nobody can read it: remote changes are simply refused.
    """
    current = read_secret(path, key)
    if len(current) >= MIN_TOKEN_LENGTH:
        return current, False, None
    token = secrets.token_urlsafe(NEW_TOKEN_BYTES)
    try:
        _write_secret(path, key, token)
    except OSError as exc:
        return token, True, f"could not save the new token in {path}: {exc}"
    return token, True, None


def _write_secret(path: str, key: str, value: str):
    """Set key="value", keeping every other line, the file's owner and its permissions."""
    line = f'{key}="{value}"\n'
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines(keepends=True)
        info = os.stat(path)
    except FileNotFoundError:
        lines, info = [], None

    replaced = False
    for i, existing in enumerate(lines):
        stripped = existing.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped and stripped.partition("=")[0].strip() == key:
            lines[i] = line
            replaced = True
            break
    if not replaced:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines.append(line)

    directory = os.path.dirname(os.path.abspath(path))
    tmp = f"{path}.tmp.{os.getpid()}"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("".join(lines))
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, (info.st_mode & 0o777) if info else 0o600)
        if hasattr(os, "chown") and os.geteuid() == 0:
            owner = info or os.stat(directory)  # the server runs as root: the file belongs to the speaker's user
            os.chown(tmp, owner.st_uid, owner.st_gid)
        os.replace(tmp, path)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
