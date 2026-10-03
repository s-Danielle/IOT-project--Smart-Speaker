"""
Folders the server creates but other programs write to or read from.
"""

import os

from utils.logger import log, log_error


def ensure_shared_dir(path: str, owner_of: str) -> None:
    """Create `path` if it is missing and, when running as root, hand it to the owner of `owner_of`.

    The server runs as root, so the folders it created were root-owned and the speaker's own
    programs (which run as the normal user) could not write into them: the controller's arecord
    got "permission denied" saving a recording. Mopidy reads the files, so the folder is
    readable by everyone (775).

    Not running as root (a developer's computer, or the tests): the folder is just created.
    """
    os.makedirs(path, exist_ok=True)
    if not hasattr(os, "geteuid") or os.geteuid() != 0:
        return
    try:
        owner = os.stat(owner_of)
        os.chown(path, owner.st_uid, owner.st_gid)
        os.chmod(path, 0o775)
    except OSError as exc:
        log_error(f"Could not give {path} to the speaker's user: {exc}")
    else:
        log(f"Folder ready: {path}")
