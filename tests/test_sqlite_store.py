"""What is particular to the SQLite database: the rules it enforces itself, its self-check and backup,
moving the data in and out of the JSON file, and choosing between the two.

The things both stores must do are in test_storage.py. All files are in temporary folders.
"""

import json
import os
import sqlite3
import threading
import time

import pytest

from storage import DEFAULT_STORAGE, JsonStore, SqliteStore, StorageError, convert, open_store
from storage import sqlite_store


class Clock:
    def __init__(self, day="2026-10-03"):
        self.day = day

    def __call__(self):
        return self.day


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def path(tmp_path):
    return str(tmp_path / "server_data.db")


@pytest.fixture
def store(path, clock):
    s = SqliteStore(path, today=clock)
    s.open()
    yield s
    s.close()


def raw(path):
    """A plain connection to the database file, to look at it the way a different program would."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def names_in(directory):
    return sorted(os.listdir(directory))


# ---------------------------------------------------------------------------
# What the database enforces by itself
# ---------------------------------------------------------------------------


def test_the_database_uses_the_safe_settings(store, path):
    conn = store._conn()
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("PRAGMA synchronous").fetchone()[0] == 2  # FULL: every save is forced out to the card
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert conn.execute("PRAGMA busy_timeout").fetchone()[0] >= 5000
    assert raw(path).execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()[0] == "1"


def test_a_chip_cannot_point_at_a_song_that_is_not_there(store):
    store.register_chip("AA11")
    with pytest.raises(sqlite3.IntegrityError):
        store._conn().execute("UPDATE chips SET song_id = 'song-nope' WHERE uid = 'AA11'")


def test_the_database_clears_the_chips_when_a_song_goes(store):
    chip = store.register_chip("AA11")
    song = store.add_song("S", "u")
    store.update_chip(chip["id"], {"song_id": song["id"]})
    store._conn().execute("DELETE FROM songs WHERE id = ?", (song["id"],))  # not through our code
    assert store.get_chip(chip["id"])["song_id"] is None


def test_a_chip_number_can_be_in_there_only_once_whatever_its_case(store):
    store.register_chip("e41c9dbb")
    with pytest.raises(sqlite3.IntegrityError):
        store._conn().execute("INSERT INTO chips (id, uid, name) VALUES ('x', 'E41C9DBB', 'n')")


def test_usage_cannot_be_negative(store):
    with pytest.raises(sqlite3.IntegrityError):
        store._conn().execute("INSERT INTO daily_usage (date, seconds) VALUES ('2026-01-01', -5)")


def test_lists_keep_the_order_things_were_added(store):
    a, b, c = (store.register_chip(uid)["id"] for uid in ("A1", "B2", "C3"))
    store.delete_chip(b)
    d = store.register_chip("D4")["id"]
    assert [x["id"] for x in store.chips()] == [a, c, d]
    s1 = store.add_song("one", "u1")["id"]
    s2 = store.add_song("two", "u2")["id"]
    store.update_song(s1, {"name": "one!"})  # changing a song does not move it
    assert [s["id"] for s in store.songs()][-2:] == [s1, s2]


def test_old_days_of_usage_are_kept(store, clock):
    store.add_daily_usage(100)
    clock.day = "2026-10-04"
    store.add_daily_usage(7)
    rows = {r["date"]: r["seconds"] for r in store._conn().execute("SELECT date, seconds FROM daily_usage")}
    assert rows == {"2026-10-03": 100, "2026-10-04": 7}


def test_looking_at_the_usage_writes_nothing(store, path, clock):
    store.add_daily_usage(10)
    before = raw(path).execute("SELECT COUNT(*) FROM daily_usage").fetchone()[0]
    clock.day = "2026-10-05"
    assert store.daily_usage() == {"date": "2026-10-05", "seconds": 0}
    assert raw(path).execute("SELECT COUNT(*) FROM daily_usage").fetchone()[0] == before


def test_unicode_names_survive(store):
    chip = store.register_chip("AA11", "שלום 🎵 Ünïcode")
    song = store.add_song("Dr. Dré — Ç’est la vie 🎶", "spotify:track:1")
    store.update_chip(chip["id"], {"song_id": song["id"]})
    assert store.get_chip(chip["id"])["name"] == "שלום 🎵 Ünïcode"
    assert store.lookup_chip("AA11")["song_name"] == "Dr. Dré — Ç’est la vie 🎶"


# ---------------------------------------------------------------------------
# Threads
# ---------------------------------------------------------------------------


def test_each_thread_has_its_own_connection(store):
    seen = []
    threading.Thread(target=lambda: seen.append(store._conn())).start()
    time.sleep(0.2)
    assert seen and seen[0] is not store._conn()


def test_many_threads_writing_at_once_lose_nothing_and_never_hit_a_lock_error(store):
    errors = []

    def worker(n):
        try:
            for i in range(20):
                store.add_song(f"t{n}-{i}", f"u{n}-{i}")
                store.add_daily_usage(1)
        except Exception as exc:  # pragma: no cover - only on failure
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert len(store.songs()) == 2 + 8 * 20
    assert store.daily_usage()["seconds"] == 8 * 20


def test_a_busy_database_makes_a_save_wait_instead_of_fail(store, path):
    other = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
    other.execute("BEGIN IMMEDIATE")  # holds the write lock, like another program in the middle of a save
    releaser = threading.Timer(0.4, lambda: other.execute("COMMIT"))
    releaser.start()
    started = time.monotonic()
    store.add_song("waited", "u")
    waited = time.monotonic() - started
    releaser.join()
    other.close()
    assert 0.3 < waited < 4.0
    assert any(s["name"] == "waited" for s in store.songs())


# ---------------------------------------------------------------------------
# The self-check, the backup and repairs
# ---------------------------------------------------------------------------


def test_a_backup_copy_is_made_at_start(path, clock):
    s = SqliteStore(path, today=clock)
    s.open()
    s.register_chip("AA11")
    s.close()
    assert os.path.exists(path + ".bak")
    s = SqliteStore(path, today=clock)
    s.open()  # a restart makes a fresh copy that includes AA11
    s.close()
    assert [r["uid"] for r in raw(path + ".bak").execute("SELECT uid FROM chips")] == ["AA11"]


def test_the_backup_is_a_real_database_that_passes_its_check(store, path):
    conn = raw(path + ".bak")
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_the_backup_is_refreshed_once_a_day_while_it_runs(path, clock):
    now = [1000.0]
    s = SqliteStore(path, today=clock, clock=lambda: now[0])
    s.open()
    s.register_chip("AA11")
    assert [r["uid"] for r in raw(path + ".bak").execute("SELECT uid FROM chips")] == []  # not yet due
    now[0] += 24 * 3600 + 1
    s.register_chip("BB22")  # this save finds the copy a day old
    assert sorted(r["uid"] for r in raw(path + ".bak").execute("SELECT uid FROM chips")) == ["AA11", "BB22"]
    s.close()


def test_no_temporary_files_are_left_behind(store, path):
    store.register_chip("AA11")
    leftovers = [n for n in names_in(os.path.dirname(path)) if n.endswith((".new", ".restoring", ".importing"))]
    assert leftovers == []


def damage(path, how):
    if how == "garbage":
        with open(path, "wb") as f:
            f.write(b"this is not a database" * 100)
    elif how == "empty":
        open(path, "wb").close()
    elif how == "truncated":
        size = os.path.getsize(path)
        with open(path, "r+b") as f:
            f.truncate(size // 2)
    elif how == "overwritten-middle":
        with open(path, "r+b") as f:
            f.seek(0)
            f.write(b"\x00" * 100)  # destroys the header


@pytest.mark.parametrize("how", ["garbage", "empty", "truncated", "overwritten-middle"])
def test_a_damaged_database_is_replaced_by_the_backup_and_kept_aside(path, clock, how):
    first = SqliteStore(path, today=clock)
    first.open()
    for n in range(40):  # enough rows that "truncated" really cuts something off
        first.add_song(f"song {n}", f"spotify:track:{n}")
    first.register_chip("AA11")
    first.close()
    second = SqliteStore(path, today=clock)
    second.open()  # makes the backup, which now holds AA11 and the songs
    second.close()
    for extra in ("-wal", "-shm"):
        if os.path.exists(path + extra):
            os.remove(path + extra)
    damage(path, how)

    fresh = SqliteStore(path, today=clock)
    assert fresh.open() == "recovered"
    assert [c["uid"] for c in fresh.chips()] == ["AA11"]
    assert len(fresh.songs()) == 42
    assert any(".corrupt-" in n for n in names_in(os.path.dirname(path)))
    fresh.close()
    again = SqliteStore(path, today=clock)
    assert again.open() == "ok"  # reported once
    again.close()


def test_a_missing_database_comes_back_from_the_backup(path, clock):
    first = SqliteStore(path, today=clock)
    first.open()
    first.register_chip("AA11")
    first.close()
    second = SqliteStore(path, today=clock)
    second.open()
    second.close()
    for extra in ("", "-wal", "-shm"):
        if os.path.exists(path + extra):
            os.remove(path + extra)
    third = SqliteStore(path, today=clock)
    assert third.open() == "recovered"
    assert [c["uid"] for c in third.chips()] == ["AA11"]
    third.close()


def test_with_no_good_copy_it_starts_empty_and_keeps_the_damaged_files(path, clock):
    with open(path, "wb") as f:
        f.write(b"garbage" * 50)
    with open(path + ".bak", "wb") as f:
        f.write(b"also garbage" * 50)
    s = SqliteStore(path, today=clock)
    assert s.open() == "damaged"
    assert s.chips() == [] and len(s.songs()) == 2
    assert any(".corrupt-" in n for n in names_in(os.path.dirname(path)))
    s.register_chip("AA11")
    s.close()


def test_a_chip_pointing_at_a_missing_song_counts_as_damage(path, clock):
    first = SqliteStore(path, today=clock)
    first.open()
    first.close()
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys=OFF")
    conn.execute("INSERT INTO chips (id, uid, name, song_id) VALUES ('c1', 'AA11', 'n', 'song-nope')")
    conn.commit()
    conn.close()
    s = SqliteStore(path, today=clock)
    assert s.open() == "recovered"  # the backup made at the first start is clean
    assert s.chips() == []
    s.close()


def test_a_database_from_a_newer_version_is_not_touched(path, clock):
    first = SqliteStore(path, today=clock)
    first.open()
    first.close()
    conn = sqlite3.connect(path)
    conn.execute("UPDATE meta SET value = '99' WHERE key = 'schema_version'")
    conn.commit()
    conn.close()
    before = open(path, "rb").read()
    with pytest.raises(StorageError):
        SqliteStore(path, today=clock).open()
    assert open(path, "rb").read() == before
    assert not any(".corrupt-" in n for n in names_in(os.path.dirname(path)))


def test_only_the_newest_damaged_copies_are_kept(path, clock):
    for n in range(6):
        s = SqliteStore(path, today=clock)
        s.open()
        s.close()
        for extra in ("-wal", "-shm"):
            if os.path.exists(path + extra):
                os.remove(path + extra)
        with open(path, "wb") as f:
            f.write(f"garbage {n}".encode() * 20)
        time.sleep(0.01)
    SqliteStore(path, today=clock).open()
    corrupt = [n for n in names_in(os.path.dirname(path)) if ".corrupt-" in n and not n.endswith(("-wal", "-shm"))]
    assert len(corrupt) == 3


def test_the_store_opens_itself_if_nobody_called_open(path, clock):
    s = SqliteStore(path, today=clock)
    assert s.chips() == []  # the first use opens (and creates) the database
    assert os.path.exists(path)
    s.close()


def test_closing_and_reopening(path, clock):
    s = SqliteStore(path, today=clock)
    s.open()
    s.register_chip("AA11")
    s.close()
    s.open()
    assert [c["uid"] for c in s.chips()] == ["AA11"]
    s.close()


# ---------------------------------------------------------------------------
# JSON -> SQLite
# ---------------------------------------------------------------------------

# Shaped like the data on the speaker: a few chips, spotify tracks, no usage yet.
CLEAN_JSON = {
    "chips": [
        {"id": "chip99adc2", "uid": "E41C9DBB", "name": "MyFirstChip", "song_id": "songc39e02", "song_name": "funerapopoli"},
        {"id": "chip952980", "uid": "9903EEB9", "name": "MySecondChip", "song_id": "song1e0bc3", "song_name": "bitthday"},
        {"id": "chip3ae53f", "uid": "595661BB", "name": "Chip 3", "song_id": None, "song_name": None},
    ],
    "library": [
        {"id": "song001", "name": "Surprise", "uri": "spotify:track:4PTG3Z6ehGkBFwjybzWkR8"},
        {"id": "songc39e02", "name": "funerapopoli", "uri": "spotify:track:5hnyJvgoWiQUYZttV4wXy6"},
        {"id": "song1e0bc3", "name": "bitthday", "uri": "spotify:track:0ntQJM78wzOLVeCUAW7Y45"},
    ],
    "parental_controls": {
        "enabled": True, "volume_limit": 40,
        "quiet_hours": {"enabled": True, "start": "20:00", "end": "07:30"},
        "daily_limit_minutes": 90, "chip_blacklist": ["x"], "chip_whitelist_mode": True, "chip_whitelist": ["E41C9DBB"],
    },
    "daily_usage": {"date": "2026-10-03", "seconds": 8},
}


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


@pytest.fixture
def folder(tmp_path):
    return str(tmp_path)


def test_a_json_file_becomes_a_database_with_the_same_content(folder, clock):
    write_json(os.path.join(folder, "server_data.json"), CLEAN_JSON)
    notes = convert.build_database_from_json(os.path.join(folder, "server_data.json"), os.path.join(folder, "server_data.db"))
    assert notes == []
    s = SqliteStore(os.path.join(folder, "server_data.db"), today=clock)
    assert s.open() == "ok"
    assert s.chips() == CLEAN_JSON["chips"]
    assert s.songs() == CLEAN_JSON["library"]
    assert s.parental_controls() == CLEAN_JSON["parental_controls"]
    assert s.daily_usage() == {"date": "2026-10-03", "seconds": 8}
    s.close()


def test_json_to_sqlite_and_back_gives_the_same_file(folder, clock):
    json_path, db_path = os.path.join(folder, "server_data.json"), os.path.join(folder, "server_data.db")
    write_json(json_path, CLEAN_JSON)
    convert.build_database_from_json(json_path, db_path)
    out = os.path.join(folder, "back.json")
    convert.export_database_to_json(db_path, out)
    assert json.load(open(out)) == CLEAN_JSON


def test_unicode_and_odd_but_valid_data_survive_the_round_trip(folder):
    data = {
        "chips": [{"id": "c1", "uid": "04:A1", "name": "שלום 🎵", "song_id": "s1", "song_name": "Ünï"}],
        "library": [{"id": "s1", "name": "Ünï", "uri": "file:///home/iot-proj/My Songs/ü ö.mp3"}],
        "parental_controls": CLEAN_JSON["parental_controls"],
        "daily_usage": {},
    }
    json_path, db_path = os.path.join(folder, "a.json"), os.path.join(folder, "a.db")
    write_json(json_path, data)
    convert.build_database_from_json(json_path, db_path)
    out = os.path.join(folder, "b.json")
    convert.export_database_to_json(db_path, out)
    assert json.load(open(out)) == data


def test_the_old_files_odd_cases_are_cleaned_up_and_listed(folder, clock):
    data = {
        "chips": [
            {"id": "c1", "uid": "AA11", "name": "First", "song_id": "s1"},
            {"id": "c2", "uid": "aa11", "name": "Same number, other case", "song_id": None},   # repeated number
            {"id": "c1", "uid": "BB22", "name": "Repeated id", "song_id": None},               # repeated id
            {"uid": "CC33", "name": "No id", "song_id": None},                                  # no id
            {"id": "c5", "uid": "DD44", "name": "Dead link", "song_id": "song-gone"},           # song not in library
            {"id": "c6", "name": "No number"},                                                  # no number
            "junk",                                                                             # not an object
            {"id": "c7", "uid": "EE55"},                                                        # no name, no song_id key
        ],
        "library": [
            {"id": "s1", "name": "Song", "uri": "spotify:track:1"},
            {"id": "s1", "name": "Repeated song id", "uri": "spotify:track:2"},
            {"name": "No id", "uri": "spotify:track:3"},
            {"id": "s4", "name": 12, "uri": None},                                              # wrong kinds
        ],
    }
    json_path, db_path = os.path.join(folder, "server_data.json"), os.path.join(folder, "server_data.db")
    write_json(json_path, data)
    notes = convert.build_database_from_json(json_path, db_path)
    assert len(notes) >= 7
    s = SqliteStore(db_path, today=clock)
    s.open()
    chips = {c["uid"]: c for c in s.chips()}
    assert set(chips) == {"AA11", "BB22", "CC33", "DD44", "EE55"}
    assert chips["AA11"]["song_id"] == "s1"
    assert chips["DD44"]["song_id"] is None
    assert len({c["id"] for c in s.chips()}) == 5  # every chip has its own id
    songs = {x["id"]: x for x in s.songs()}
    assert songs["s1"]["name"] == "Song"  # the first one wins
    assert songs["s4"] == {"id": "s4", "name": "12", "uri": ""}
    assert len(songs) == 3
    assert s.parental_controls()["volume_limit"] == 100  # the file had none: the defaults
    s.close()


def test_a_json_file_with_only_some_keys(folder, clock):
    json_path, db_path = os.path.join(folder, "server_data.json"), os.path.join(folder, "server_data.db")
    write_json(json_path, {"chips": []})
    convert.build_database_from_json(json_path, db_path)
    s = SqliteStore(db_path, today=clock)
    s.open()
    assert s.songs() == [] and s.chips() == []
    s.close()


@pytest.mark.parametrize("content", [b"", b"{not json", b"[1, 2]", b'{"chips": "oops"}', b"\xff\xfe\x00bad"])
def test_a_json_file_that_cannot_be_used_is_refused_and_leaves_nothing_behind(folder, content):
    json_path, db_path = os.path.join(folder, "server_data.json"), os.path.join(folder, "server_data.db")
    with open(json_path, "wb") as f:
        f.write(content)
    with pytest.raises(convert.ConversionFailed):
        convert.build_database_from_json(json_path, db_path)
    assert names_in(folder) == ["server_data.json"]
    assert open(json_path, "rb").read() == content


def test_a_database_that_does_not_match_is_never_put_in_place(folder, monkeypatch):
    json_path, db_path = os.path.join(folder, "server_data.json"), os.path.join(folder, "server_data.db")
    write_json(json_path, CLEAN_JSON)
    real = convert.set_parental_controls
    monkeypatch.setattr(convert, "set_parental_controls", lambda conn, settings: real(conn, dict(settings, volume_limit=1)))
    with pytest.raises(convert.ConversionFailed, match="parental"):
        convert.build_database_from_json(json_path, db_path)
    assert names_in(folder) == ["server_data.json"]


def test_a_crash_while_putting_the_database_in_place_leaves_no_half_database(folder, monkeypatch):
    json_path, db_path = os.path.join(folder, "server_data.json"), os.path.join(folder, "server_data.db")
    write_json(json_path, CLEAN_JSON)

    def power_cut(src, dst):
        raise OSError("power cut")

    monkeypatch.setattr(os, "replace", power_cut)
    with pytest.raises(convert.ConversionFailed):
        convert.build_database_from_json(json_path, db_path)
    monkeypatch.undo()
    assert names_in(folder) == ["server_data.json"]


# ---------------------------------------------------------------------------
# SQLite -> JSON
# ---------------------------------------------------------------------------


def test_the_database_is_written_back_out_with_everything_in_it(folder, clock):
    db_path = os.path.join(folder, "server_data.db")
    s = SqliteStore(db_path, today=clock)
    s.open()
    chip = s.register_chip("AA11", "Bedtime")
    song = s.add_song("Lullaby", "spotify:track:1")
    s.update_chip(chip["id"], {"song_id": song["id"]})
    s.update_parental_controls({"volume_limit": 55})
    s.add_daily_usage(42)
    out = os.path.join(folder, "out.json")
    convert.export_database_to_json(db_path, out)
    data = json.load(open(out))
    assert data["chips"] == [{"id": chip["id"], "uid": "AA11", "name": "Bedtime", "song_id": song["id"], "song_name": "Lullaby"}]
    assert song in data["library"]
    assert data["parental_controls"]["volume_limit"] == 55
    assert data["daily_usage"] == {"date": "2026-10-03", "seconds": 42}
    s.close()


def test_exporting_does_not_change_the_database(folder, clock):
    db_path = os.path.join(folder, "server_data.db")
    s = SqliteStore(db_path, today=clock)
    s.open()
    s.register_chip("AA11")
    before = s.chips()
    s.close()
    convert.export_database_to_json(db_path, os.path.join(folder, "out.json"))
    s = SqliteStore(db_path, today=clock)
    s.open()
    assert s.chips() == before
    s.close()


def test_exporting_over_an_existing_file_keeps_that_file_as_a_backup(folder, clock):
    db_path, out = os.path.join(folder, "server_data.db"), os.path.join(folder, "out.json")
    s = SqliteStore(db_path, today=clock)
    s.open()
    s.close()
    write_json(out, {"chips": [{"id": "old", "uid": "OLD", "name": "n", "song_id": None}], "library": []})
    convert.export_database_to_json(db_path, out)
    assert json.load(open(out + ".bak"))["chips"][0]["uid"] == "OLD"


def test_an_export_that_cannot_be_written_is_refused(folder, clock, monkeypatch):
    db_path = os.path.join(folder, "server_data.db")
    s = SqliteStore(db_path, today=clock)
    s.open()
    s.close()

    def refuse(self, data):
        raise OSError("disk full")

    monkeypatch.setattr(JsonStore, "write_all", refuse)
    with pytest.raises(convert.ConversionFailed):
        convert.export_database_to_json(db_path, os.path.join(folder, "out.json"))


def test_putting_the_database_aside_takes_its_newest_changes_with_it(folder, clock):
    db_path = os.path.join(folder, "server_data.db")
    s = SqliteStore(db_path, today=clock)
    s.open()
    s.register_chip("AA11")  # lives in the write-ahead log until a checkpoint
    s.close()
    kept = convert.retire_database(db_path, "2026-10-03")
    assert kept.endswith(".exported-2026-10-03")
    assert not [n for n in names_in(folder) if n in ("server_data.db", "server_data.db-wal", "server_data.db-shm", "server_data.db.bak")]
    assert [r["uid"] for r in raw(kept).execute("SELECT uid FROM chips")] == ["AA11"]


# ---------------------------------------------------------------------------
# Choosing between the two, and moving across when the choice changes
# ---------------------------------------------------------------------------


def files_of(folder):
    return [n for n in names_in(folder) if n.startswith("server_data")]


def messages(notes, level=None):
    return [m for lvl, m in notes if level is None or lvl == level]


def test_json_is_what_is_used_until_sqlite_is_asked_for(folder, monkeypatch):
    monkeypatch.delenv("SPEAKER_STORAGE", raising=False)
    assert DEFAULT_STORAGE == "json"
    store, status, notes = open_store(folder)
    assert store.kind == "json" and status == "new"
    assert files_of(folder) == ["server_data.json"]


def test_the_setting_comes_from_the_environment(folder, monkeypatch):
    monkeypatch.setenv("SPEAKER_STORAGE", "SQLite")
    store, status, notes = open_store(folder)
    assert store.kind == "sqlite" and status == "new"
    store.close()


def test_a_setting_that_makes_no_sense_falls_back_loudly(folder, monkeypatch):
    monkeypatch.setenv("SPEAKER_STORAGE", "postgres")
    store, status, notes = open_store(folder)
    assert store.kind == "json"
    assert any("postgres" in m for m in messages(notes, "error"))


def test_the_first_sqlite_start_moves_the_json_data_across_and_keeps_the_old_file(folder, clock):
    write_json(os.path.join(folder, "server_data.json"), CLEAN_JSON)
    store, status, notes = open_store(folder, mode="sqlite", today=clock)
    assert store.kind == "sqlite" and status == "imported"
    assert store.chips() == CLEAN_JSON["chips"]
    names = files_of(folder)
    assert "server_data.json" not in names  # so nobody reads a stale copy by accident
    assert any(n.startswith("server_data.json.migrated-") for n in names)
    assert "server_data.db" in names
    assert not messages(notes, "error")
    store.close()


def test_the_second_start_does_not_import_again(folder, clock):
    write_json(os.path.join(folder, "server_data.json"), CLEAN_JSON)
    store, _, _ = open_store(folder, mode="sqlite", today=clock)
    store.register_chip("NEW1")
    store.close()
    store, status, notes = open_store(folder, mode="sqlite", today=clock)
    assert status == "ok" and len(store.chips()) == 4
    assert not messages(notes, "error")
    store.close()


def test_switching_back_to_json_brings_the_changes_made_in_sqlite(folder, clock):
    write_json(os.path.join(folder, "server_data.json"), CLEAN_JSON)
    store, _, _ = open_store(folder, mode="sqlite", today=clock)
    new_chip = store.register_chip("NEW1", "Made in SQLite")
    store.update_parental_controls({"volume_limit": 33})
    store.close()

    store, status, notes = open_store(folder, mode="json", today=clock)
    assert store.kind == "json" and status == "exported"
    assert [c["uid"] for c in store.chips()] == ["E41C9DBB", "9903EEB9", "595661BB", "NEW1"]
    assert store.get_chip(new_chip["id"])["name"] == "Made in SQLite"
    assert store.parental_controls()["volume_limit"] == 33
    names = files_of(folder)
    assert "server_data.db" not in names and "server_data.db.bak" not in names
    assert any(n.startswith("server_data.db.exported-") for n in names)
    assert "server_data.json" in names
    assert not messages(notes, "error")


def test_the_full_cycle_json_sqlite_json_sqlite_loses_nothing(folder, clock):
    write_json(os.path.join(folder, "server_data.json"), CLEAN_JSON)
    expected = []

    s, _, _ = open_store(folder, mode="json", today=clock)
    expected.append(s.register_chip("J1")["uid"])
    s, status, _ = open_store(folder, mode="sqlite", today=clock)
    assert status == "imported"
    expected.append(s.register_chip("S1")["uid"])
    s.close()
    s, status, _ = open_store(folder, mode="json", today=clock)
    assert status == "exported"
    expected.append(s.register_chip("J2")["uid"])
    s, status, _ = open_store(folder, mode="sqlite", today=clock)
    assert status == "imported"
    expected.append(s.register_chip("S2")["uid"])
    uids = [c["uid"] for c in s.chips()]
    assert uids == ["E41C9DBB", "9903EEB9", "595661BB"] + expected
    assert s.songs() == CLEAN_JSON["library"]
    assert s.parental_controls() == CLEAN_JSON["parental_controls"]
    s.close()


def test_a_json_file_that_cannot_be_imported_leaves_everything_as_it_was(folder, clock):
    json_path = os.path.join(folder, "server_data.json")
    write_json(json_path, CLEAN_JSON)
    with open(json_path, "a") as f:
        f.write("{{{ not valid anymore")
    before = open(json_path, "rb").read()
    store, status, notes = open_store(folder, mode="sqlite", today=clock)
    assert store.kind == "json"  # it went on with the file it had
    assert any("could not be moved into SQLite" in m for m in messages(notes, "error"))
    assert not os.path.exists(os.path.join(folder, "server_data.db"))
    # The JSON store then found the file damaged and set it aside, whole: nothing was lost.
    kept = [n for n in names_in(folder) if n.startswith("server_data.json.corrupt-")]
    assert len(kept) == 1
    assert open(os.path.join(folder, kept[0]), "rb").read() == before


def test_with_both_files_present_sqlite_mode_uses_the_database_and_warns(folder, clock):
    write_json(os.path.join(folder, "server_data.json"), CLEAN_JSON)
    store, _, _ = open_store(folder, mode="sqlite", today=clock)
    store.register_chip("ONLY-IN-DB")
    store.close()
    write_json(os.path.join(folder, "server_data.json"), CLEAN_JSON)  # someone put a JSON file back
    store, status, notes = open_store(folder, mode="sqlite", today=clock)
    assert status == "ok" and "ONLY-IN-DB" in [c["uid"] for c in store.chips()]
    assert any("next to the database" in m for m in messages(notes, "error"))
    assert os.path.exists(os.path.join(folder, "server_data.json"))  # not touched
    store.close()


def test_with_both_files_present_json_mode_uses_the_json_and_warns(folder, clock):
    store, _, _ = open_store(folder, mode="sqlite", today=clock)
    store.close()
    write_json(os.path.join(folder, "server_data.json"), CLEAN_JSON)
    store, status, notes = open_store(folder, mode="json", today=clock)
    assert store.kind == "json" and store.chips() == CLEAN_JSON["chips"]
    assert any("next to the JSON file" in m for m in messages(notes, "error"))
    assert os.path.exists(os.path.join(folder, "server_data.db"))  # not touched


def test_if_the_data_cannot_be_moved_out_of_sqlite_it_carries_on_with_sqlite(folder, clock, monkeypatch):
    store, _, _ = open_store(folder, mode="sqlite", today=clock)
    store.register_chip("AA11")
    store.close()

    def refuse(self, data):
        raise OSError("disk full")

    monkeypatch.setattr(JsonStore, "write_all", refuse)
    store, status, notes = open_store(folder, mode="json", today=clock)
    assert store.kind == "sqlite"  # the data is still reachable
    assert [c["uid"] for c in store.chips()] == ["AA11"]
    assert any("could not be moved out of SQLite" in m for m in messages(notes, "error"))
    store.close()


def test_the_first_ever_sqlite_start_without_any_file(folder, clock):
    store, status, notes = open_store(folder, mode="sqlite", today=clock)
    assert status == "new" and len(store.songs()) == 2
    store.close()
