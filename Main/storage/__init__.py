"""Where the speaker keeps its chips, songs, parental controls and daily usage.

Two stores do the same job: a JSON file (JsonStore) and a SQLite database (SqliteStore). Which one
is used is the setting SPEAKER_STORAGE ("json" or "sqlite"). open_store() picks it, and moves the
data across when the setting has changed since the last start (see convert.py).
"""

import os
import sqlite3
import time

from . import convert
from .json_store import JsonStore
from .sqlite_store import SqliteStore, StorageError

__all__ = ["JsonStore", "SqliteStore", "StorageError", "open_store", "DEFAULT_STORAGE"]

# The setting to use when SPEAKER_STORAGE is not set. SQLite has been proven on the speaker (switched
# on, rebooted, switched back and on again with the data identical each time).
DEFAULT_STORAGE = "sqlite"

JSON_NAME = "server_data.json"
DB_NAME = "server_data.db"


def open_store(directory, mode=None, today=None):
    """Open the data store in `directory`. Returns (store, status, notes).

    `status` is what happened to the data: 'ok', 'new', 'recovered', 'damaged', 'imported' (moved
    from JSON into SQLite) or 'exported' (moved from SQLite back into JSON). `notes` is a list of
    (level, message) pairs, level 'info' or 'error', for the server to log.
    """
    chosen = (mode if mode is not None else os.environ.get("SPEAKER_STORAGE", DEFAULT_STORAGE)).strip().lower()
    notes = []
    if chosen not in ("json", "sqlite"):
        notes.append(("error", f"[STORAGE] SPEAKER_STORAGE={chosen!r} is not 'json' or 'sqlite': using {DEFAULT_STORAGE!r}"))
        chosen = DEFAULT_STORAGE
    json_path = os.path.join(directory, JSON_NAME)
    db_path = os.path.join(directory, DB_NAME)

    if chosen == "sqlite":
        opened = _open_sqlite(json_path, db_path, today, notes)
        if opened:
            return opened[0], opened[1], notes
        notes.append(("error", "[STORAGE] the data could not be moved into SQLite, so the JSON file is used as before (nothing was lost)"))
    return _open_json(json_path, db_path, today, notes)


def _open_sqlite(json_path, db_path, today, notes):
    have_database = os.path.exists(db_path) or os.path.exists(db_path + ".bak")
    imported = False
    if not have_database and os.path.exists(json_path):
        try:
            for message in convert.build_database_from_json(json_path, db_path):
                notes.append(("info", f"[STORAGE] import: {message}"))
            imported = True
        except convert.ConversionFailed as exc:
            notes.append(("error", f"[STORAGE] the data could not be moved into SQLite: {exc}"))
            return None
    store = SqliteStore(db_path, today=today)
    try:
        status = store.open()
    except (StorageError, sqlite3.Error, OSError) as exc:
        store.close()
        if not imported:
            # A database that was in use cannot be opened (a newer version made it, the disk fails...).
            # The JSON file, if there is one, is out of date, and moving the data out of a database we
            # cannot trust would hide the problem. Stop, loudly: the owner decides.
            raise StorageError(
                f"the SQLite database {db_path} exists but cannot be opened ({exc}). Not falling back to the "
                "JSON file, which may be out of date. Fix the cause, or set SPEAKER_STORAGE=json to move the "
                "data out of SQLite on purpose.") from exc
        # The database we have just built is no good: drop it, and keep using the JSON file (untouched)
        notes.append(("error", f"[STORAGE] the new SQLite database cannot be opened: {exc}"))
        convert._remove_database_files(db_path)
        convert._remove_database_files(db_path + ".bak")
        return None
    if imported:
        status = "imported"
        kept = convert.retire_json(json_path)
        notes.append(("info", f"[STORAGE] the data was moved into SQLite and checked; the old JSON file was kept as {kept}"))
    elif os.path.exists(json_path):
        notes.append(("error", f"[STORAGE] {json_path} exists next to the database. The database is what is used. "
                               "If you used JSON mode since the database was last used, move the database aside to import the JSON again"))
    return store, status


def _open_json(json_path, db_path, today, notes):
    status_override = None
    if not os.path.exists(json_path) and os.path.exists(db_path):
        # SQLite was used before. Bring its data across, then put the database aside.
        try:
            convert.export_database_to_json(db_path, json_path)
            try:
                kept = convert.retire_database(db_path)
            except convert.ConversionFailed:
                # Two live copies must never exist: take the JSON file we just wrote away again
                for leftover in (json_path, json_path + ".bak"):
                    try:
                        os.remove(leftover)
                    except OSError:
                        pass
                raise
            notes.append(("info", f"[STORAGE] the data was moved from SQLite into the JSON file and checked; the database was kept as {kept}"))
            status_override = "exported"
        except convert.ConversionFailed as exc:
            notes.append(("error", f"[STORAGE] the data could not be moved out of SQLite: {exc}. Carrying on with SQLite"))
            store = SqliteStore(db_path, today=today)
            return store, store.open(), notes
    elif os.path.exists(json_path) and os.path.exists(db_path):
        notes.append(("error", f"[STORAGE] {db_path} exists next to the JSON file. The JSON file is what is used. "
                               "If you used SQLite mode since the JSON file was last used, move the JSON file aside to bring the database across again"))
    store = JsonStore(json_path, today=today)
    status = store.open()
    return store, status_override or status, notes
