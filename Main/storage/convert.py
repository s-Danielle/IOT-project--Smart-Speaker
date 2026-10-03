"""Moving the speaker's data between the JSON file and the SQLite database, in either direction.

The rule that keeps this safe: there is exactly one live copy of the data.

    JSON -> SQLite   build the database next to the real one, check every row against the JSON,
                     and only then put it in place. The JSON file is kept as
                     server_data.json.migrated-<date>.
    SQLite -> JSON   write the JSON file, read it back and compare. The database is kept as
                     server_data.db.exported-<date>.

A conversion that doesn't check out is undone: nothing in place is changed, and the caller carries
on with the copy it already had.
"""

import hashlib
import json
import os
import sqlite3
import time

from . import rules
from .json_store import JsonStore
from .sqlite_store import (
    SELECT_CHIPS, create_schema, get_parental_controls, set_parental_controls,
)


class ConversionFailed(Exception):
    """The data could not be moved. Nothing in place was changed."""


# ---------------------------------------------------------------------------
# JSON -> SQLite
# ---------------------------------------------------------------------------


def normalize_json_data(data):
    """Clean what is in a JSON data file so that it can go into the database.

    Returns (clean, notes). `clean` has 'songs', 'chips', 'parental_controls' and 'usage'. Anything
    the database could not hold is adjusted or left out, and each case is listed in `notes`:
    a chip or song with no id gets one, a repeated id or chip number keeps the first one, a chip
    pointing at a song that is not there is left with no song.
    """
    if not isinstance(data, dict):
        raise ConversionFailed("the JSON file does not hold an object")
    notes = []

    songs, song_ids = [], set()
    for entry in _entries(data.get("library"), "library", notes):
        song_id = entry.get("id")
        if not isinstance(song_id, str) or not song_id:
            song_id = rules.new_song_id(song_ids)
            notes.append(f"a song had no id: it was given {song_id}")
        if song_id in song_ids:
            notes.append(f"song id {song_id} appears twice: kept the first")
            continue
        song_ids.add(song_id)
        songs.append({"id": song_id, "name": _text(entry.get("name")), "uri": _text(entry.get("uri"))})

    chips, chip_ids, uids = [], set(), set()
    for entry in _entries(data.get("chips"), "chips", notes):
        uid = entry.get("uid")
        if not isinstance(uid, str) or not uid:
            notes.append(f"a chip with no number was left out: {entry.get('name')!r}")
            continue
        if uid.casefold() in uids:
            notes.append(f"chip number {uid} appears twice: kept the first")
            continue
        chip_id = entry.get("id")
        if not isinstance(chip_id, str) or not chip_id:
            chip_id = rules.new_chip_id(chip_ids)
            notes.append(f"chip {uid} had no id: it was given {chip_id}")
        if chip_id in chip_ids:
            notes.append(f"chip id {chip_id} appears twice: the later one ({uid}) was given a new id")
            chip_id = rules.new_chip_id(chip_ids)
        song_id = entry.get("song_id")
        if song_id is not None and song_id not in song_ids:
            notes.append(f"chip {uid} pointed at song {song_id!r}, which is not in the library: left with no song")
            song_id = None
        uids.add(uid.casefold())
        chip_ids.add(chip_id)
        name = entry.get("name") if isinstance(entry.get("name"), str) else f"Chip {len(chips) + 1}"
        chips.append({"id": chip_id, "uid": uid, "name": name, "song_id": song_id})

    usage = data.get("daily_usage")
    clean_usage = None
    if isinstance(usage, dict) and isinstance(usage.get("date"), str) and usage["date"]:
        seconds = usage.get("seconds", 0)
        if isinstance(seconds, (int, float)) and not isinstance(seconds, bool) and seconds >= 0:
            clean_usage = {"date": usage["date"], "seconds": int(seconds)}

    return {
        "songs": songs,
        "chips": chips,
        "parental_controls": rules.complete_parental_controls(data.get("parental_controls")),
        "usage": clean_usage,
    }, notes


def build_database_from_json(json_path, db_path):
    """Make db_path from the JSON file, checked row by row. Returns notes about anything adjusted.

    The database is built under another name and moved into place only when it checks out, so a
    crash half-way leaves no half-built database. The JSON file itself is not touched here.
    """
    try:
        with open(json_path, "rb") as f:
            raw = f.read()
        clean, notes = normalize_json_data(json.loads(raw.decode("utf-8")))
    except (OSError, ValueError) as exc:  # includes json.JSONDecodeError and bad UTF-8
        raise ConversionFailed(f"cannot read {json_path}: {exc}") from exc

    building = db_path + ".importing"
    _remove_database_files(building)
    conn = None
    try:
        conn = sqlite3.connect(building, isolation_level=None)
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("BEGIN")
        create_schema(conn)
        conn.executemany("INSERT INTO songs (id, name, uri) VALUES (:id, :name, :uri)", clean["songs"])
        conn.executemany("INSERT INTO chips (id, uid, name, song_id) VALUES (:id, :uid, :name, :song_id)", clean["chips"])
        set_parental_controls(conn, clean["parental_controls"])
        if clean["usage"]:
            conn.execute("INSERT INTO daily_usage (date, seconds) VALUES (:date, :seconds)", clean["usage"])
        conn.execute("INSERT INTO meta (key, value) VALUES ('imported_from_sha256', ?)", (hashlib.sha256(raw).hexdigest(),))
        conn.execute("INSERT INTO meta (key, value) VALUES ('imported_at', ?)", (time.strftime("%Y-%m-%d %H:%M:%S"),))
        _verify(conn, clean)
        conn.execute("COMMIT")
        problems = [row[0] for row in conn.execute("PRAGMA integrity_check")]
        if problems != ["ok"]:
            raise ConversionFailed("the new database failed its integrity check: " + "; ".join(problems[:3]))
        conn.execute("PRAGMA journal_mode=WAL")  # stays set in the file
        conn.close()
        conn = None
        _remove_database_files(building, keep_main=True)
        _fsync_file(building)
        os.replace(building, db_path)
        _sync_directory(os.path.dirname(db_path) or ".")
    except ConversionFailed:
        _discard(conn, building)
        raise
    except (sqlite3.Error, OSError, ValueError) as exc:
        _discard(conn, building)
        raise ConversionFailed(f"building the database failed: {exc}") from exc
    return notes


def retire_json(json_path, label=None):
    """Keep the old JSON file under a dated name, so it is never read again by accident. Returns the new name."""
    return _move_aside(json_path, f".migrated-{label or time.strftime('%Y-%m-%d')}")


# ---------------------------------------------------------------------------
# SQLite -> JSON
# ---------------------------------------------------------------------------


def export_database_to_json(db_path, json_path):
    """Write the database out as a JSON file the old code can read, and check it. Returns notes."""
    try:
        conn = sqlite3.connect(db_path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            data = {
                "chips": [dict(id=r["id"], uid=r["uid"], name=r["name"], song_id=r["song_id"], song_name=r["song_name"])
                          for r in conn.execute(SELECT_CHIPS + " ORDER BY c.rowid")],
                "library": [dict(id=r["id"], name=r["name"], uri=r["uri"])
                            for r in conn.execute("SELECT id, name, uri FROM songs ORDER BY rowid")],
                "parental_controls": get_parental_controls(conn),
                "daily_usage": {},
            }
            latest = conn.execute("SELECT date, seconds FROM daily_usage ORDER BY date DESC LIMIT 1").fetchone()
            if latest:
                data["daily_usage"] = {"date": latest["date"], "seconds": latest["seconds"]}
        finally:
            conn.close()
    except sqlite3.Error as exc:
        raise ConversionFailed(f"cannot read {db_path}: {exc}") from exc

    try:
        store = JsonStore(json_path)
        store.write_all(data)
        written = JsonStore(json_path)
        again = {"chips": written.chips(), "library": written.songs(), "parental_controls": written.parental_controls()}
    except (OSError, ValueError) as exc:
        raise ConversionFailed(f"cannot write {json_path}: {exc}") from exc
    for key in ("chips", "library", "parental_controls"):
        if again[key] != data[key]:
            raise ConversionFailed(f"the JSON file does not match the database ({key}); the database was not changed")
    return []


def retire_database(db_path, label=None):
    """Keep the database (and its copy) under dated names. Returns the new name of the main file."""
    try:  # fold the write-ahead log into the main file first, or its newest changes would be left behind
        conn = sqlite3.connect(db_path, isolation_level=None)
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            conn.close()
    except sqlite3.Error as exc:
        raise ConversionFailed(f"cannot close {db_path} cleanly: {exc}") from exc
    suffix = f".exported-{label or time.strftime('%Y-%m-%d')}"
    new_main = _move_aside(db_path, suffix)
    final_suffix = new_main[len(db_path):]
    for extra in ("-wal", "-shm", ".bak"):
        if os.path.exists(db_path + extra):
            os.replace(db_path + extra, db_path + final_suffix + extra)
    return new_main


# ---------------------------------------------------------------------------
# Checks and small helpers
# ---------------------------------------------------------------------------


def _verify(conn, clean):
    """Read everything back from the new database and compare it with what was meant to go in."""
    conn.row_factory = sqlite3.Row
    try:
        songs = [dict(r) for r in conn.execute("SELECT id, name, uri FROM songs ORDER BY rowid")]
        chips = [dict(r) for r in conn.execute("SELECT id, uid, name, song_id FROM chips ORDER BY rowid")]
        parental = get_parental_controls(conn)
        usage = [dict(r) for r in conn.execute("SELECT date, seconds FROM daily_usage")]
    finally:
        conn.row_factory = None
    problems = []
    if songs != clean["songs"]:
        problems.append(f"songs: {len(songs)} in the database, {len(clean['songs'])} expected, or their contents differ")
    if chips != clean["chips"]:
        problems.append(f"chips: {len(chips)} in the database, {len(clean['chips'])} expected, or their contents differ")
    if parental != clean["parental_controls"]:
        problems.append("the parental controls differ")
    if usage != ([clean["usage"]] if clean["usage"] else []):
        problems.append("the daily usage differs")
    if problems:
        raise ConversionFailed("the new database does not match the JSON file: " + "; ".join(problems))


def _entries(value, name, notes):
    if value is None:
        return []
    if not isinstance(value, list):
        raise ConversionFailed(f"'{name}' in the JSON file is not a list")
    entries = []
    for item in value:
        if isinstance(item, dict):
            entries.append(item)
        else:
            notes.append(f"an entry in '{name}' is not an object and was left out: {str(item)[:40]!r}")
    return entries


def _text(value):
    if isinstance(value, str):
        return value
    return "" if value is None else str(value)


def _move_aside(path, suffix):
    target, n = path + suffix, 1
    while os.path.exists(target):
        n += 1
        target = f"{path}{suffix}-{n}"
    os.replace(path, target)
    return target


def _remove_database_files(path, keep_main=False):
    for extra in (("-wal", "-shm", "-journal") if keep_main else ("", "-wal", "-shm", "-journal")):
        try:
            os.remove(path + extra)
        except FileNotFoundError:
            pass


def _discard(conn, building):
    if conn is not None:
        try:
            conn.close()
        except sqlite3.Error:
            pass
    _remove_database_files(building)


def _fsync_file(path):
    with open(path, "rb") as f:
        os.fsync(f.fileno())


def _sync_directory(directory):
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
