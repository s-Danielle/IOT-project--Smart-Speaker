"""The speaker's data in a SQLite database (server_data.db).

It does the same job as JsonStore, with the same methods, so the server doesn't care which one it
has. What the database adds:

  - A chip points at its song, and the database clears that link by itself when the song is
    deleted. No hand-written clean-up, and a chip can never point at a song that isn't there.
  - A chip number can only be in there once, whatever the case it was written in.
  - A power cut in the middle of a save leaves either the old data or the new data, never half.
    (WAL mode with synchronous=FULL: every save is forced out to the SD card before it counts.)
  - When it starts it checks itself (integrity_check), and keeps a copy of itself in
    server_data.db.bak (made at start-up and then once a day). If the database is damaged, the
    damaged files are kept aside and the copy is put back.

Each thread gets its own connection. A save that finds the database busy waits a few seconds
instead of failing.
"""

import json
import os
import shutil
import sqlite3
import threading
import time
from datetime import date

from utils.logger import log, log_error

from . import rules

SCHEMA_VERSION = 1
BUSY_SECONDS = 5.0
BACKUP_EVERY_SECONDS = 24 * 60 * 60
CORRUPT_COPIES_KEPT = 3

SCHEMA = """
CREATE TABLE meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE songs (
    id   TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    uri  TEXT NOT NULL
);
CREATE TABLE chips (
    id      TEXT PRIMARY KEY,
    uid     TEXT NOT NULL UNIQUE COLLATE NOCASE,
    name    TEXT NOT NULL,
    song_id TEXT REFERENCES songs(id) ON DELETE SET NULL ON UPDATE CASCADE
);
CREATE TABLE settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE daily_usage (
    date    TEXT PRIMARY KEY,
    seconds INTEGER NOT NULL CHECK (seconds >= 0)
);
"""

# The order of the lists in the app is the order things were added, which is the row order.
SELECT_CHIPS = """
    SELECT c.id AS id, c.uid AS uid, c.name AS name, c.song_id AS song_id, s.name AS song_name, s.uri AS uri
    FROM chips c LEFT JOIN songs s ON s.id = c.song_id
"""


class StorageError(Exception):
    """The database cannot be used, and not because of ordinary damage (for example it is from a newer version)."""


class SqliteStore:
    kind = "sqlite"

    def __init__(self, path, today=None, backup_every=BACKUP_EVERY_SECONDS, clock=time.monotonic):
        self.path = path
        self.backup_path = path + ".bak"
        self._today = today or (lambda: date.today().isoformat())
        self._backup_every = backup_every
        self._clock = clock
        self._last_backup = clock()
        self._local = threading.local()
        self._connections = []
        self._connections_lock = threading.Lock()
        self._open_lock = threading.RLock()
        self._backup_lock = threading.Lock()
        self._opened = False

    # ------------------------------------------------------------------
    # Start-up
    # ------------------------------------------------------------------

    def open(self) -> str:
        """Check the database, repair it if needed, make the first backup. Returns 'ok', 'new',
        'recovered' (from the .bak copy) or 'damaged' (nothing usable was left, so it started empty)."""
        with self._open_lock:
            status = self._open_database()
            self._opened = True
            self._backup()
            return status

    def close(self):
        with self._connections_lock:
            connections, self._connections = self._connections, []
        for conn in connections:
            try:
                conn.close()
            except sqlite3.Error:
                pass
        self._local = threading.local()
        self._opened = False

    def _open_database(self) -> str:
        if os.path.exists(self.path):
            try:
                self._check(self.path)
            except StorageError:
                raise
            except (sqlite3.Error, ValueError) as exc:
                log_error(f"[STORAGE] {self.path} failed its check: {exc}")
                return self._recover(damaged=True)
            return "ok"
        return self._recover(damaged=False)

    def _check(self, path):
        """Raise if the file at `path` is not a sound database of a version we can read."""
        conn = sqlite3.connect(path, timeout=BUSY_SECONDS, isolation_level=None)
        try:
            problems = [row[0] for row in conn.execute("PRAGMA integrity_check")]
            if problems != ["ok"]:
                raise ValueError("integrity check: " + "; ".join(problems[:3]))
            broken = conn.execute("PRAGMA foreign_key_check").fetchall()
            if broken:
                raise ValueError(f"{len(broken)} chip(s) point at a song that is not there")
            row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
            if row is None:
                raise ValueError("no schema version")
            version = int(row[0])
        finally:
            conn.close()
        if version > SCHEMA_VERSION:
            raise StorageError(f"{path} was made by a newer version of the speaker software (schema {version})")
        return version

    def _recover(self, damaged: bool) -> str:
        if damaged:
            self._set_aside_damaged_files()
        if os.path.exists(self.backup_path):
            try:
                self._check(self.backup_path)
                staging = self.path + ".restoring"
                shutil.copy2(self.backup_path, staging)
                os.replace(staging, self.path)
                _sync_directory(os.path.dirname(self.path) or ".")
                log_error(f"[STORAGE] the database was {'damaged' if damaged else 'missing'}; the last good copy ({self.backup_path}) was put back")
                return "recovered"
            except (sqlite3.Error, ValueError, OSError) as exc:
                log_error(f"[STORAGE] the backup copy cannot be used either: {exc}")
        self._create_new()
        if damaged:
            log_error("[STORAGE] the database was damaged and there is no good copy: started empty (the damaged files were kept)")
            return "damaged"
        return "new"

    def _create_new(self):
        conn = sqlite3.connect(self.path, timeout=BUSY_SECONDS, isolation_level=None)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=FULL")
            conn.execute("BEGIN IMMEDIATE")
            create_schema(conn)
            conn.executemany("INSERT INTO songs (id, name, uri) VALUES (?, ?, ?)",
                             [(s["id"], s["name"], s["uri"]) for s in rules.DEFAULT_LIBRARY])
            set_parental_controls(conn, rules.complete_parental_controls(None))
            conn.execute("COMMIT")
        except BaseException:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        finally:
            conn.close()

    def _set_aside_damaged_files(self):
        stamp = time.strftime("%Y%m%d-%H%M%S")
        suffix, n = f".corrupt-{stamp}", 1
        while os.path.exists(self.path + suffix):
            n += 1
            suffix = f".corrupt-{stamp}-{n}"
        for extra in ("", "-wal", "-shm"):
            source = self.path + extra
            if os.path.exists(source):
                try:
                    os.replace(source, source + suffix)
                except OSError as exc:
                    log_error(f"[STORAGE] could not move {source} aside: {exc}")
        log_error(f"[STORAGE] the damaged database was kept as {self.path}{suffix}")
        directory = os.path.dirname(self.path) or "."
        prefix = os.path.basename(self.path) + ".corrupt-"
        copies = [
            os.path.join(directory, name) for name in os.listdir(directory)
            if name.startswith(prefix) and not name.endswith(("-wal", "-shm"))
        ]
        for copy in sorted(copies, key=os.path.getmtime)[:-CORRUPT_COPIES_KEPT]:
            for extra in ("", "-wal", "-shm"):
                try:
                    os.remove(copy + extra)
                except OSError:
                    pass

    # ------------------------------------------------------------------
    # Backup copy
    # ------------------------------------------------------------------

    def _backup(self):
        """Copy the database (a consistent copy, made by SQLite itself) to server_data.db.bak."""
        with self._backup_lock:
            staging = self.backup_path + ".new"
            try:
                os.remove(staging)
            except FileNotFoundError:
                pass
            try:
                source = self._connect()
                try:
                    target = sqlite3.connect(staging, isolation_level=None)
                    try:
                        source.backup(target)
                    finally:
                        target.close()
                finally:
                    source.close()
                with open(staging, "rb") as f:
                    os.fsync(f.fileno())
                os.replace(staging, self.backup_path)
                _sync_directory(os.path.dirname(self.path) or ".")
                self._last_backup = self._clock()
            except (sqlite3.Error, OSError) as exc:
                log_error(f"[STORAGE] could not make the backup copy: {exc}")
                try:
                    os.remove(staging)
                except OSError:
                    pass

    def _maybe_backup(self):
        if self._clock() - self._last_backup >= self._backup_every:
            self._backup()

    # ------------------------------------------------------------------
    # Connections and transactions
    # ------------------------------------------------------------------

    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=BUSY_SECONDS, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(f"PRAGMA busy_timeout={int(BUSY_SECONDS * 1000)}")
        return conn

    def _conn(self):
        conn = getattr(self._local, "conn", None)
        if conn is None:
            if not self._opened:
                with self._open_lock:
                    if not self._opened:
                        self.open()
            conn = self._connect()
            self._local.conn = conn
            with self._connections_lock:
                self._connections.append(conn)
        return conn

    def _write(self, change):
        """Run change(conn) as one all-or-nothing save. It may raise (ValueError for bad input): nothing is kept."""
        conn = self._conn()
        conn.execute("BEGIN IMMEDIATE")
        try:
            result = change(conn)
            conn.execute("COMMIT")
        except BaseException:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        self._maybe_backup()
        return result

    # ------------------------------------------------------------------
    # Chips
    # ------------------------------------------------------------------

    def chips(self) -> list:
        rows = self._conn().execute(SELECT_CHIPS + " ORDER BY c.rowid").fetchall()
        return [_chip_view(row) for row in rows]

    def get_chip(self, chip_id):
        row = self._conn().execute(SELECT_CHIPS + " WHERE c.id = ?", (chip_id,)).fetchone()
        return _chip_view(row) if row else None

    def find_chip_by_uid(self, uid):
        row = self._conn().execute(SELECT_CHIPS + " WHERE c.uid = ?", (uid,)).fetchone() if isinstance(uid, str) else None
        return _chip_view(row) if row else None

    def lookup_chip(self, uid):
        """The chip plus the link of its song, from one query. 'uri' is '' when it has no song."""
        row = self._conn().execute(SELECT_CHIPS + " WHERE c.uid = ?", (uid,)).fetchone() if isinstance(uid, str) else None
        if row is None:
            return None
        result = _chip_view(row)
        result["uri"] = row["uri"] or ""
        return result

    def register_chip(self, uid, name=None) -> dict:
        if not isinstance(uid, str) or not uid:
            raise ValueError("uid is required")
        if name is not None and not isinstance(name, str):
            raise ValueError("name must be text")

        def change(conn):
            row = conn.execute(SELECT_CHIPS + " WHERE c.uid = ?", (uid,)).fetchone()
            if row:
                return _chip_view(row), False
            taken = {r[0] for r in conn.execute("SELECT id FROM chips")}
            chip_id = rules.new_chip_id(taken)
            chip_name = name or f"Chip {len(taken) + 1}"
            conn.execute("INSERT INTO chips (id, uid, name, song_id) VALUES (?, ?, ?, NULL)", (chip_id, uid, chip_name))
            return {"id": chip_id, "uid": uid, "name": chip_name, "song_id": None, "song_name": None}, True

        chip, created = self._write(change)
        if created:
            log(f"Registered new chip: {chip['name']} (UID: {uid[:20]}...)")
        return chip

    def update_chip(self, chip_id, changes):
        if not isinstance(changes, dict):
            raise ValueError("changes must be an object")
        if "name" in changes and not isinstance(changes["name"], str):
            raise ValueError("name must be text")

        def change(conn):
            if conn.execute("SELECT 1 FROM chips WHERE id = ?", (chip_id,)).fetchone() is None:
                return None
            if "name" in changes:
                conn.execute("UPDATE chips SET name = ? WHERE id = ?", (changes["name"], chip_id))
            if "song_id" in changes:
                song_id = changes["song_id"]
                if song_id is not None and conn.execute("SELECT 1 FROM songs WHERE id = ?", (song_id,)).fetchone() is None:
                    raise ValueError(f"there is no song {song_id!r} in the library")
                conn.execute("UPDATE chips SET song_id = ? WHERE id = ?", (song_id, chip_id))
            return _chip_view(conn.execute(SELECT_CHIPS + " WHERE c.id = ?", (chip_id,)).fetchone())

        chip = self._write(change)
        if chip is not None:
            log(f"Updated chip {chip_id}: {chip}")
        return chip

    def clear_chip_assignment(self, chip_id) -> bool:
        found = self._write(lambda conn: conn.execute("UPDATE chips SET song_id = NULL WHERE id = ?", (chip_id,)).rowcount > 0)
        if found:
            log(f"Reset assignment for chip {chip_id}")
        return found

    def delete_chip(self, chip_id) -> bool:
        found = self._write(lambda conn: conn.execute("DELETE FROM chips WHERE id = ?", (chip_id,)).rowcount > 0)
        if found:
            log(f"Deleted chip {chip_id}")
        return found

    # ------------------------------------------------------------------
    # Songs
    # ------------------------------------------------------------------

    def songs(self) -> list:
        return [{"id": r["id"], "name": r["name"], "uri": r["uri"]}
                for r in self._conn().execute("SELECT id, name, uri FROM songs ORDER BY rowid")]

    def add_song(self, name, uri) -> dict:
        if not isinstance(name, str) or not isinstance(uri, str):
            raise ValueError("name and uri must be text")

        def change(conn):
            song_id = rules.new_song_id({r[0] for r in conn.execute("SELECT id FROM songs")})
            conn.execute("INSERT INTO songs (id, name, uri) VALUES (?, ?, ?)", (song_id, name, uri))
            return {"id": song_id, "name": name, "uri": uri}

        song = self._write(change)
        log(f"Added to library: {name} ({uri})")
        return song

    def update_song(self, song_id, changes):
        if not isinstance(changes, dict):
            raise ValueError("changes must be an object")
        for field in ("name", "uri"):
            if field in changes and not isinstance(changes[field], str):
                raise ValueError(f"{field} must be text")

        def change(conn):
            row = conn.execute("SELECT name, uri FROM songs WHERE id = ?", (song_id,)).fetchone()
            if row is None:
                return None
            name, uri = changes.get("name", row["name"]), changes.get("uri", row["uri"])
            conn.execute("UPDATE songs SET name = ?, uri = ? WHERE id = ?", (name, uri, song_id))
            return {"id": song_id, "name": name, "uri": uri}

        song = self._write(change)
        if song is not None:
            log(f"Updated song {song_id}: {song}")
        return song

    def delete_song(self, song_id) -> bool:
        """Delete a song. The database leaves the chips that used it with no song."""
        def change(conn):
            users = [r[0] for r in conn.execute("SELECT id FROM chips WHERE song_id = ?", (song_id,))]
            if conn.execute("DELETE FROM songs WHERE id = ?", (song_id,)).rowcount == 0:
                return None
            return users

        users = self._write(change)
        if users is None:
            return False
        for chip_id in users:
            log(f"Cleared song {song_id} from chip {chip_id}")
        log(f"Deleted song {song_id}")
        return True

    # ------------------------------------------------------------------
    # Parental controls and usage
    # ------------------------------------------------------------------

    def parental_controls(self) -> dict:
        return get_parental_controls(self._conn())

    def update_parental_controls(self, changes) -> dict:
        def change(conn):
            updated = rules.apply_parental_changes(get_parental_controls(conn), changes)
            set_parental_controls(conn, updated)
            return updated

        updated = self._write(change)
        log(f"Updated parental controls: {updated}")
        return updated

    def daily_usage(self) -> dict:
        today = self._today()
        row = self._conn().execute("SELECT seconds FROM daily_usage WHERE date = ?", (today,)).fetchone()
        return {"date": today, "seconds": row["seconds"] if row else 0}

    def add_daily_usage(self, seconds) -> dict:
        add = max(0, rules.whole_number(seconds, "seconds"))
        today = self._today()

        def change(conn):
            conn.execute(
                "INSERT INTO daily_usage (date, seconds) VALUES (?, ?) "
                "ON CONFLICT(date) DO UPDATE SET seconds = seconds + excluded.seconds",
                (today, add),
            )
            return conn.execute("SELECT seconds FROM daily_usage WHERE date = ?", (today,)).fetchone()["seconds"]

        total = self._write(change)
        log(f"Daily usage updated: {total} seconds")
        return {"date": today, "seconds": total}

    # ------------------------------------------------------------------
    # Chips from the old tags.json
    # ------------------------------------------------------------------

    def import_legacy_tags(self, tags) -> int:
        """Add chips from the old tags.json format ({uid: {name, uri}}). Returns how many were added."""
        if not isinstance(tags, dict):
            return 0

        def change(conn):
            added = 0
            for uid, tag in tags.items():
                if not isinstance(tag, dict) or conn.execute("SELECT 1 FROM chips WHERE uid = ?", (uid,)).fetchone():
                    continue
                song_id = None
                uri = tag.get("uri", "")
                if uri:
                    row = conn.execute("SELECT id FROM songs WHERE uri = ? ORDER BY rowid LIMIT 1", (uri,)).fetchone()
                    if row:
                        song_id = row["id"]
                    else:
                        song_id = rules.new_song_id({r[0] for r in conn.execute("SELECT id FROM songs")})
                        conn.execute("INSERT INTO songs (id, name, uri) VALUES (?, ?, ?)",
                                     (song_id, tag.get("name", "Migrated Song"), uri))
                count = conn.execute("SELECT COUNT(*) FROM chips").fetchone()[0]
                chip_id = rules.new_chip_id({r[0] for r in conn.execute("SELECT id FROM chips")})
                conn.execute("INSERT INTO chips (id, uid, name, song_id) VALUES (?, ?, ?, ?)",
                             (chip_id, uid, tag.get("name", f"Chip {count + 1}"), song_id))
                added += 1
            return added

        added = self._write(change)
        if added:
            log(f"Imported {added} chips from the old tags.json")
        return added


# ---------------------------------------------------------------------------
# Pieces the converter uses too
# ---------------------------------------------------------------------------


def create_schema(conn):
    """Create the empty tables inside the caller's transaction."""
    for statement in SCHEMA.split(";"):
        if statement.strip():
            conn.execute(statement)
    conn.execute("INSERT INTO meta (key, value) VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
    conn.execute("INSERT INTO meta (key, value) VALUES ('created_at', ?)", (time.strftime("%Y-%m-%d %H:%M:%S"),))


def get_parental_controls(conn) -> dict:
    row = conn.execute("SELECT value FROM settings WHERE key = 'parental_controls'").fetchone()
    try:
        stored = json.loads(row[0]) if row else None
    except ValueError:
        stored = None
    return rules.complete_parental_controls(stored)


def set_parental_controls(conn, settings: dict):
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('parental_controls', ?)", (json.dumps(settings),))


def _chip_view(row) -> dict:
    return {"id": row["id"], "uid": row["uid"], "name": row["name"], "song_id": row["song_id"], "song_name": row["song_name"]}


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
