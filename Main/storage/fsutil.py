"""Small file-system helpers shared by the JSON store, the SQLite store and the converter."""

import os


def sync_directory(directory):
    """Make a rename inside `directory` survive a power cut (the rename itself is data too)."""
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def keep_newest(directory, prefix, keep, companions=()):
    """Delete all but the `keep` newest files in `directory` whose name starts with `prefix`.

    `companions` are suffixes of files that belong to one of those (a database's "-wal" and "-shm"):
    they are not counted on their own, and are deleted together with the file they belong to.
    """
    names = [n for n in os.listdir(directory) if n.startswith(prefix) and not n.endswith(tuple(companions))]
    paths = sorted((os.path.join(directory, n) for n in names), key=os.path.getmtime)
    for path in paths[:-keep] if keep > 0 else paths:
        for suffix in ("",) + tuple(companions):
            try:
                os.remove(path + suffix)
            except OSError:
                pass
