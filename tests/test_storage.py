"""The speaker's data store: what it keeps, and that a crash or a bad file can't lose it.

Every test uses a temporary folder. The first group (the "contract") says what any store must
do, so the SQLite store that comes later can be run through the same tests.
"""

import json
import os
import stat
import threading

import pytest

from storage import JsonStore, rules


class Clock:
    """A day we can change, so the daily usage tests don't wait for midnight."""

    def __init__(self, day="2026-10-03"):
        self.day = day

    def __call__(self):
        return self.day


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def path(tmp_path):
    return str(tmp_path / "server_data.json")


@pytest.fixture(params=["json"])
def store(request, path, clock):
    # When the SQLite store exists, add "sqlite" to params and build it here.
    s = JsonStore(path, today=clock)
    s.open()
    return s


def read_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def song_id(store, uri="spotify:track:abc", name="A song"):
    return store.add_song(name, uri)["id"]


# ---------------------------------------------------------------------------
# Start-up
# ---------------------------------------------------------------------------


def test_the_first_start_creates_the_file_with_the_starting_songs(path, clock):
    s = JsonStore(path, today=clock)
    assert s.open() == "new"
    assert os.path.exists(path)
    assert s.chips() == []
    assert [song["id"] for song in s.songs()] == ["song001", "song002"]


def test_data_survives_a_restart(path, clock):
    first = JsonStore(path, today=clock)
    first.open()
    chip = first.register_chip("04A1B2C3", "Bedtime")
    second = JsonStore(path, today=clock)
    assert second.open() == "ok"
    assert [c["id"] for c in second.chips()] == [chip["id"]]


def test_the_defaults_cannot_be_changed_by_accident(store, tmp_path, clock):
    # The old code handed out a shallow copy of one shared dict, so editing a result changed the defaults.
    settings = store.parental_controls()
    settings["quiet_hours"]["start"] = "03:00"
    settings["chip_blacklist"].append("x")
    store.songs()[0]["name"] = "changed"
    other = JsonStore(str(tmp_path / "other.json"), today=clock)
    other.open()
    assert other.parental_controls()["quiet_hours"]["start"] == "21:00"
    assert other.parental_controls()["chip_blacklist"] == []
    assert other.songs()[0]["name"] == "Surprise"
    assert rules.default_data() == rules.default_data()
    assert rules.default_data() is not rules.default_data()


# ---------------------------------------------------------------------------
# Chips
# ---------------------------------------------------------------------------


def test_a_new_chip_gets_an_id_and_a_numbered_name(store):
    first = store.register_chip("AA11")
    second = store.register_chip("BB22")
    assert first["name"] == "Chip 1" and second["name"] == "Chip 2"
    assert first["id"].startswith("chip") and first["id"] != second["id"]
    assert first["song_id"] is None and first["song_name"] is None


def test_registering_the_same_chip_again_returns_the_one_we_have(store):
    first = store.register_chip("AA11", "Mine")
    again = store.register_chip("AA11", "Other name")
    assert again["id"] == first["id"] and again["name"] == "Mine"
    assert len(store.chips()) == 1


def test_chip_numbers_are_not_case_sensitive(store):
    # Older tools wrote the number in lower case.
    first = store.register_chip("e41c9dbb")
    again = store.register_chip("E41C9DBB")
    assert again["id"] == first["id"]
    assert store.find_chip_by_uid("E41c9DbB")["id"] == first["id"]


def test_a_chip_needs_a_number(store):
    for bad in ("", None, 5):
        with pytest.raises(ValueError):
            store.register_chip(bad)


def test_chip_ids_are_unique(store):
    ids = {store.register_chip(f"{n:08X}")["id"] for n in range(100)}
    assert len(ids) == 100


def test_find_chip_by_number(store):
    chip = store.register_chip("AA11")
    assert store.find_chip_by_uid("AA11")["id"] == chip["id"]
    assert store.find_chip_by_uid("ZZ99") is None


def test_assigning_a_song_shows_its_name(store):
    chip = store.register_chip("AA11")
    song = store.add_song("Lullaby", "spotify:track:1")
    updated = store.update_chip(chip["id"], {"song_id": song["id"]})
    assert updated["song_id"] == song["id"] and updated["song_name"] == "Lullaby"
    assert store.get_chip(chip["id"])["song_name"] == "Lullaby"


def test_a_chip_can_be_renamed_without_touching_its_song(store):
    chip = store.register_chip("AA11")
    song = store.add_song("Lullaby", "spotify:track:1")
    store.update_chip(chip["id"], {"song_id": song["id"]})
    store.update_chip(chip["id"], {"name": "Bedtime"})
    result = store.get_chip(chip["id"])
    assert result["name"] == "Bedtime" and result["song_id"] == song["id"]


def test_a_chip_can_be_given_no_song(store):
    chip = store.register_chip("AA11")
    store.update_chip(chip["id"], {"song_id": song_id(store)})
    cleared = store.update_chip(chip["id"], {"song_id": None})
    assert cleared["song_id"] is None and cleared["song_name"] is None


def test_a_song_that_is_not_in_the_library_is_refused(store):
    # The old code stored the dead link and the chip silently played nothing.
    chip = store.register_chip("AA11")
    with pytest.raises(ValueError):
        store.update_chip(chip["id"], {"song_id": "song-nope"})
    assert store.get_chip(chip["id"])["song_id"] is None


def test_updating_a_chip_that_does_not_exist(store):
    assert store.update_chip("chip-nope", {"name": "x"}) is None


def test_a_bad_chip_name_is_refused(store):
    chip = store.register_chip("AA11")
    with pytest.raises(ValueError):
        store.update_chip(chip["id"], {"name": 42})


def test_renaming_a_song_renames_it_on_the_chips_too(store, path):
    chip = store.register_chip("AA11")
    song = store.add_song("Old name", "spotify:track:1")
    store.update_chip(chip["id"], {"song_id": song["id"]})
    store.update_song(song["id"], {"name": "New name"})
    assert store.get_chip(chip["id"])["song_name"] == "New name"
    stored = next(c for c in read_file(path)["chips"] if c["id"] == chip["id"])
    assert stored["song_name"] == "New name"  # the old code, after a rollback, sees it too


def test_a_stale_song_name_in_an_old_file_is_corrected_when_read(path, clock):
    with open(path, "w") as f:
        json.dump({
            "chips": [{"id": "chip1", "uid": "AA11", "name": "C", "song_id": "song1", "song_name": "Stale"}],
            "library": [{"id": "song1", "name": "Fresh", "uri": "spotify:track:1"}],
        }, f)
    s = JsonStore(path, today=clock)
    assert s.chips()[0]["song_name"] == "Fresh"


def test_clearing_a_chips_song(store):
    chip = store.register_chip("AA11")
    store.update_chip(chip["id"], {"song_id": song_id(store)})
    assert store.clear_chip_assignment(chip["id"]) is True
    assert store.get_chip(chip["id"])["song_id"] is None
    assert store.clear_chip_assignment("chip-nope") is False


def test_deleting_a_chip(store):
    chip = store.register_chip("AA11")
    other = store.register_chip("BB22")
    assert store.delete_chip(chip["id"]) is True
    assert [c["id"] for c in store.chips()] == [other["id"]]
    assert store.delete_chip(chip["id"]) is False


# ---------------------------------------------------------------------------
# Songs
# ---------------------------------------------------------------------------


def test_adding_and_listing_songs(store):
    song = store.add_song("Lullaby", "spotify:track:1")
    assert song["id"].startswith("song")
    assert {"id": song["id"], "name": "Lullaby", "uri": "spotify:track:1"} in store.songs()


def test_song_ids_are_unique(store):
    ids = {store.add_song("s", "u")["id"] for _ in range(100)}
    assert len(ids) == 100


def test_a_song_needs_text_for_name_and_link(store):
    with pytest.raises(ValueError):
        store.add_song(None, "x")
    with pytest.raises(ValueError):
        store.add_song("x", 5)


def test_changing_only_the_name_keeps_the_link(store):
    song = store.add_song("A", "spotify:track:1")
    changed = store.update_song(song["id"], {"name": "B"})
    assert changed == {"id": song["id"], "name": "B", "uri": "spotify:track:1"}


def test_changing_a_song_that_does_not_exist(store):
    assert store.update_song("song-nope", {"name": "x"}) is None


def test_deleting_a_song_leaves_its_chips_without_a_song(store):
    chip = store.register_chip("AA11")
    kept = store.register_chip("BB22")
    song = store.add_song("Gone", "spotify:track:1")
    other = store.add_song("Stays", "spotify:track:2")
    store.update_chip(chip["id"], {"song_id": song["id"]})
    store.update_chip(kept["id"], {"song_id": other["id"]})
    assert store.delete_song(song["id"]) is True
    assert store.get_chip(chip["id"])["song_id"] is None
    assert store.get_chip(chip["id"])["song_name"] is None
    assert store.get_chip(kept["id"])["song_id"] == other["id"]
    assert store.delete_song(song["id"]) is False


# ---------------------------------------------------------------------------
# Parental controls
# ---------------------------------------------------------------------------


def test_the_parental_controls_start_switched_off(store):
    pc = store.parental_controls()
    assert pc["enabled"] is False and pc["volume_limit"] == 100
    assert pc["quiet_hours"] == {"enabled": False, "start": "21:00", "end": "07:00"}
    assert pc["daily_limit_minutes"] == 0 and pc["chip_whitelist_mode"] is False


def test_only_the_fields_that_are_sent_change(store):
    store.update_parental_controls({"enabled": True, "volume_limit": 40})
    store.update_parental_controls({"quiet_hours": {"start": "20:30"}})
    pc = store.parental_controls()
    assert pc["enabled"] is True and pc["volume_limit"] == 40
    assert pc["quiet_hours"] == {"enabled": False, "start": "20:30", "end": "07:00"}


def test_the_update_returns_the_new_settings(store):
    assert store.update_parental_controls({"daily_limit_minutes": 90})["daily_limit_minutes"] == 90


@pytest.mark.parametrize("sent, kept", [(150, 100), (-5, 0), (42.9, 42)])
def test_the_volume_limit_stays_between_0_and_100(store, sent, kept):
    assert store.update_parental_controls({"volume_limit": sent})["volume_limit"] == kept


def test_a_negative_daily_limit_becomes_zero(store):
    assert store.update_parental_controls({"daily_limit_minutes": -10})["daily_limit_minutes"] == 0


def test_times_are_written_the_same_way_every_time(store):
    result = store.update_parental_controls({"quiet_hours": {"start": "7:05", "end": "23:59"}})
    assert result["quiet_hours"]["start"] == "07:05" and result["quiet_hours"]["end"] == "23:59"


@pytest.mark.parametrize("changes", [
    {"enabled": "yes"},
    {"enabled": 1},
    {"volume_limit": "loud"},
    {"volume_limit": True},
    {"daily_limit_minutes": None},
    {"quiet_hours": "21:00-07:00"},
    {"quiet_hours": {"start": "25:00"}},
    {"quiet_hours": {"end": "7"}},
    {"quiet_hours": {"enabled": "no"}},
    {"chip_blacklist": "AA11"},
    {"chip_whitelist": [1, 2]},
    {"chip_whitelist_mode": 0},
    "not an object",
])
def test_a_bad_setting_is_refused_and_nothing_is_saved(store, path, changes):
    store.update_parental_controls({"volume_limit": 60})
    before = open(path).read()
    with pytest.raises(ValueError):
        store.update_parental_controls(changes)
    assert open(path).read() == before
    assert store.parental_controls()["volume_limit"] == 60


def test_one_bad_field_stops_the_whole_update(store):
    with pytest.raises(ValueError):
        store.update_parental_controls({"volume_limit": 10, "enabled": "yes"})
    assert store.parental_controls()["volume_limit"] == 100


def test_the_whitelist_and_blacklist_are_stored(store):
    store.update_parental_controls({"chip_whitelist_mode": True, "chip_whitelist": ["A"], "chip_blacklist": ["B"]})
    pc = store.parental_controls()
    assert pc["chip_whitelist_mode"] is True and pc["chip_whitelist"] == ["A"] and pc["chip_blacklist"] == ["B"]


def test_an_old_file_without_parental_controls_gets_the_defaults(path, clock):
    with open(path, "w") as f:
        json.dump({"chips": [], "library": []}, f)
    s = JsonStore(path, today=clock)
    assert s.parental_controls() == rules.DEFAULT_PARENTAL_CONTROLS


def test_an_old_file_with_some_quiet_hours_fields_missing(path, clock):
    with open(path, "w") as f:
        json.dump({"chips": [], "library": [], "parental_controls": {"enabled": True, "quiet_hours": {"start": "22:00"}}}, f)
    pc = JsonStore(path, today=clock).parental_controls()
    assert pc["enabled"] is True
    assert pc["quiet_hours"] == {"enabled": False, "start": "22:00", "end": "07:00"}
    assert pc["volume_limit"] == 100


# ---------------------------------------------------------------------------
# Daily usage
# ---------------------------------------------------------------------------


def test_usage_starts_at_zero_today(store):
    assert store.daily_usage() == {"date": "2026-10-03", "seconds": 0}


def test_usage_adds_up(store):
    store.add_daily_usage(60)
    assert store.add_daily_usage(30) == {"date": "2026-10-03", "seconds": 90}
    assert store.daily_usage()["seconds"] == 90


def test_a_new_day_starts_again_at_zero(store, clock):
    store.add_daily_usage(500)
    clock.day = "2026-10-04"
    assert store.daily_usage() == {"date": "2026-10-04", "seconds": 0}
    assert store.add_daily_usage(5) == {"date": "2026-10-04", "seconds": 5}


def test_usage_never_goes_down(store):
    store.add_daily_usage(100)
    assert store.add_daily_usage(-50)["seconds"] == 100


def test_usage_needs_a_number(store):
    for bad in ("5", None, True):
        with pytest.raises(ValueError):
            store.add_daily_usage(bad)


def test_looking_at_the_usage_writes_nothing(store, path, clock):
    # The old code rewrote the whole file when it noticed a new day, just because someone asked.
    store.add_daily_usage(10)
    before = open(path).read()
    mtime = os.stat(path).st_mtime_ns
    clock.day = "2026-10-05"
    store.daily_usage()
    assert open(path).read() == before
    assert os.stat(path).st_mtime_ns == mtime


# ---------------------------------------------------------------------------
# Chips from the old tags.json
# ---------------------------------------------------------------------------

TAGS = {
    "E41C9DBB": {"name": "MyFirstChip", "uri": "spotify:track:1"},
    "9903EEB9": {"name": "MySecondChip", "uri": "spotify:track:2"},
    "AAAA0000": {"name": "NoSong"},
}


def test_old_tags_become_chips_and_songs(store):
    assert store.import_legacy_tags(TAGS) == 3
    chips = {c["uid"]: c for c in store.chips()}
    assert set(chips) == set(TAGS)
    assert chips["E41C9DBB"]["song_name"] == "MyFirstChip"
    assert chips["AAAA0000"]["song_id"] is None
    uris = {s["uri"] for s in store.songs()}
    assert {"spotify:track:1", "spotify:track:2"} <= uris


def test_old_tags_are_not_added_twice(store):
    store.import_legacy_tags(TAGS)
    assert store.import_legacy_tags(TAGS) == 0
    assert len(store.chips()) == 3


def test_an_old_tag_whose_song_is_already_in_the_library_reuses_it(store):
    existing = store.add_song("Mine", "spotify:track:1")
    store.import_legacy_tags({"E41C9DBB": {"name": "x", "uri": "spotify:track:1"}})
    assert store.find_chip_by_uid("E41C9DBB")["song_id"] == existing["id"]


def test_nothing_to_import(store):
    for nothing in ({}, None, []):
        assert store.import_legacy_tags(nothing) == 0


# ---------------------------------------------------------------------------
# The file: format, backup, crashes, damage
# ---------------------------------------------------------------------------


def test_the_file_keeps_the_format_the_app_and_the_old_code_read(store, path):
    chip = store.register_chip("AA11")
    store.update_chip(chip["id"], {"song_id": store.add_song("S", "u")["id"]})
    store.add_daily_usage(5)
    data = read_file(path)
    assert set(data) >= {"chips", "library", "parental_controls", "daily_usage"}
    assert set(data["chips"][0]) == {"id", "uid", "name", "song_id", "song_name"}
    assert set(data["library"][0]) == {"id", "name", "uri"}
    assert data["daily_usage"] == {"date": "2026-10-03", "seconds": 5}


def test_a_file_in_the_old_format_is_read(path, clock):
    # Shaped like the one on the speaker: only spotify track links, no usage yet.
    with open(path, "w") as f:
        json.dump({
            "chips": [{"id": "chipaaaaaa", "uid": "E41C9DBB", "name": "MyFirstChip", "song_id": "song1", "song_name": "Surprise"}],
            "library": [{"id": "song1", "name": "Surprise", "uri": "spotify:track:4PTG3Z6ehGkBFwjybzWkR8"}],
            "parental_controls": {"enabled": False, "volume_limit": 100,
                                  "quiet_hours": {"enabled": False, "start": "21:00", "end": "07:00"},
                                  "daily_limit_minutes": 0, "chip_blacklist": [], "chip_whitelist_mode": False,
                                  "chip_whitelist": []},
        }, f, indent=2)
    s = JsonStore(path, today=clock)
    assert s.open() == "ok"
    assert s.chips()[0]["name"] == "MyFirstChip"
    assert s.daily_usage()["seconds"] == 0


def test_the_previous_version_is_kept_as_a_backup(store, path):
    store.register_chip("AA11")
    store.register_chip("BB22")
    backup = read_file(path + ".bak")
    assert [c["uid"] for c in backup["chips"]] == ["AA11"]
    assert [c["uid"] for c in read_file(path)["chips"]] == ["AA11", "BB22"]


def test_saving_leaves_no_temporary_files(store, path):
    for n in range(5):
        store.register_chip(f"{n:04X}")
    leftovers = [n for n in os.listdir(os.path.dirname(path)) if n not in ("server_data.json", "server_data.json.bak")]
    assert leftovers == []


def test_a_crash_while_saving_keeps_the_old_data(store, path, monkeypatch):
    store.register_chip("AA11")
    before = open(path).read()

    def power_cut(src, dst):
        raise OSError("power cut")

    monkeypatch.setattr(os, "replace", power_cut)
    with pytest.raises(OSError):
        store.register_chip("BB22")
    monkeypatch.undo()
    assert open(path).read() == before
    assert not os.path.exists(path + ".tmp") and not os.path.exists(path + ".bak.new")
    assert [c["uid"] for c in store.chips()] == ["AA11"]
    store.register_chip("CC33")  # and it works again afterwards
    assert [c["uid"] for c in store.chips()] == ["AA11", "CC33"]


def test_a_crash_between_the_backup_and_the_rename_loses_nothing(store, path, monkeypatch):
    store.register_chip("AA11")
    real_replace = os.replace
    calls = []

    def second_replace_fails(src, dst):
        calls.append(dst)
        if dst == path:  # the final swap, after the backup has been made
            raise OSError("power cut")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", second_replace_fails)
    with pytest.raises(OSError):
        store.register_chip("BB22")
    monkeypatch.undo()
    assert path + ".bak" in calls
    assert [c["uid"] for c in read_file(path)["chips"]] == ["AA11"]
    assert [c["uid"] for c in read_file(path + ".bak")["chips"]] == ["AA11"]


def test_a_half_written_temporary_file_is_ignored(store, path):
    store.register_chip("AA11")
    with open(path + ".tmp", "w") as f:
        f.write('{"chips": [{"id": "chip')  # what a power cut during step 1 leaves
    assert [c["uid"] for c in store.chips()] == ["AA11"]
    store.register_chip("BB22")
    assert [c["uid"] for c in store.chips()] == ["AA11", "BB22"]


@pytest.mark.parametrize("damage", [b"", b'{"chips": [{"id": "chip', b"\x00\x00\x00", b"not json at all", b"[]", b'{"chips": "oops"}'])
def test_a_damaged_file_is_replaced_by_the_last_good_copy(store, path, clock, damage):
    store.register_chip("AA11")
    store.register_chip("BB22")  # the backup now holds AA11 only
    with open(path, "wb") as f:
        f.write(damage)
    fresh = JsonStore(path, today=clock)
    assert fresh.open() == "recovered"
    assert [c["uid"] for c in fresh.chips()] == ["AA11"]
    assert [c["uid"] for c in read_file(path)["chips"]] == ["AA11"]  # repaired on disk
    corrupt = [n for n in os.listdir(os.path.dirname(path)) if ".corrupt-" in n]
    assert len(corrupt) == 1
    with open(os.path.join(os.path.dirname(path), corrupt[0]), "rb") as f:
        assert f.read() == damage  # kept, not thrown away
    assert JsonStore(path, today=clock).open() == "ok"  # and it is only reported once


def test_a_missing_file_comes_back_from_the_backup(store, path, clock):
    store.register_chip("AA11")
    store.register_chip("BB22")
    os.remove(path)
    fresh = JsonStore(path, today=clock)
    assert fresh.open() == "recovered"
    assert [c["uid"] for c in fresh.chips()] == ["AA11"]


def test_damage_in_the_middle_of_a_run_is_repaired_once(store, path):
    store.register_chip("AA11")
    store.register_chip("BB22")
    with open(path, "w") as f:
        f.write("garbage")
    assert [c["uid"] for c in store.chips()] == ["AA11"]
    assert [c["uid"] for c in store.chips()] == ["AA11"]
    assert len([n for n in os.listdir(os.path.dirname(path)) if ".corrupt-" in n]) == 1


def test_when_nothing_good_is_left_it_starts_empty_and_keeps_the_damaged_file(path, clock):
    with open(path, "w") as f:
        f.write("garbage")
    with open(path + ".bak", "w") as f:
        f.write("also garbage")
    s = JsonStore(path, today=clock)
    assert s.open() == "damaged"
    assert s.chips() == []
    assert any(".corrupt-" in n for n in os.listdir(os.path.dirname(path)))
    s.register_chip("AA11")
    assert [c["uid"] for c in JsonStore(path, today=clock).chips()] == ["AA11"]


def test_only_the_newest_damaged_copies_are_kept(store, path):
    for n in range(6):
        store.register_chip(f"{n:04X}")
        with open(path, "w") as f:
            f.write(f"garbage {n}")
        store.chips()
    corrupt = [n for n in os.listdir(os.path.dirname(path)) if ".corrupt-" in n]
    assert len(corrupt) == 3


def test_a_damaged_file_never_replaces_the_good_backup(store, path):
    store.register_chip("AA11")
    store.register_chip("BB22")
    with open(path, "w") as f:
        f.write("garbage")
    store.chips()
    store.register_chip("CC33")
    assert "garbage" not in open(path + ".bak").read()
    assert [c["uid"] for c in read_file(path + ".bak")["chips"]] == ["AA11"]


@pytest.mark.skipif(os.name != "posix", reason="file modes")
def test_the_files_permissions_are_kept(store, path):
    store.register_chip("AA11")
    os.chmod(path, 0o640)
    store.register_chip("BB22")
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o640


def test_many_threads_writing_at_once_lose_nothing(store, path):
    errors = []

    def worker(n):
        try:
            for i in range(15):
                store.add_song(f"t{n}-{i}", f"spotify:track:{n}-{i}")
        except Exception as exc:  # pragma: no cover - only on failure
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    songs = read_file(path)["library"]
    assert len(songs) == 2 + 8 * 15
    assert len({s["id"] for s in songs}) == len(songs)


def test_reading_while_writing_never_sees_a_half_written_file(store):
    stop = threading.Event()
    problems = []

    def reader():
        while not stop.is_set():
            try:
                store.chips()
                store.songs()
            except Exception as exc:  # pragma: no cover - only on failure
                problems.append(exc)
                return

    t = threading.Thread(target=reader)
    t.start()
    try:
        for n in range(60):
            store.register_chip(f"{n:06X}")
    finally:
        stop.set()
        t.join()
    assert problems == []
    assert len(store.chips()) == 60
