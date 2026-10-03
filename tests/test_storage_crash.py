"""Kill a program that is saving data, at random moments, again and again.

Each round starts a child Python process that adds songs to a store in a loop and says "ACK n"
after each one has been saved. The test kills it (SIGKILL: no clean-up, no chance to finish
anything) at a random moment, then opens the store and checks that

  - it opens and passes its own check,
  - every song that was acknowledged is there,
  - no song is there twice, and nothing but the acknowledged songs plus at most the one that was
    being saved at the moment of the kill.

A second test does the same with saves of 40 chips and songs at once, to check a save is all or
nothing.

What this does and does not show:
  - It does show that the JSON file is replaced atomically. Changing the code to write the file in
    place makes this test fail within a few rounds.
  - It does NOT show SQLite's power-cut safety. A killed program leaves the operating system's
    cache intact, so even a database with its safety settings switched off survives (tried:
    journal_mode=OFF, synchronous=OFF, 200 rounds, still passed). The settings themselves are
    checked by test_the_database_uses_the_safe_settings in test_sqlite_store.py, and the real
    proof is the power-pull test on the speaker.

The number of rounds is SPEAKER_CRASH_RUNS (default 20 per test; 250 for a thorough run).
"""

import os
import random
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

from storage import JsonStore, SqliteStore

MAIN = str(Path(__file__).resolve().parent.parent / "Main")
RUNS = int(os.environ.get("SPEAKER_CRASH_RUNS", "20"))

CHILD = r"""
import sys
sys.dont_write_bytecode = True
sys.path.insert(0, sys.argv[3])
from storage import JsonStore, SqliteStore
kind, path, prefix = sys.argv[1], sys.argv[2], sys.argv[4]
store = (JsonStore if kind == "json" else SqliteStore)(path)
store.open()
print("READY", flush=True)
mode = sys.argv[5]
n = 0
while True:
    if mode == "batch":
        # 40 chips and 40 songs in one save: a program killed half-way must leave all 40 or none
        store.import_legacy_tags({"%s%d-%d" % (prefix, n, i): {"name": "c%d-%d" % (n, i), "uri": "spotify:track:%d-%d" % (n, i)} for i in range(40)})
    else:
        store.add_song("%s%d" % (prefix, n), "spotify:track:%d" % n)
    print("ACK %d" % n, flush=True)
    n += 1
"""


def one_round(kind, path, seed, prefix, mode):
    rng = random.Random(seed)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    child = subprocess.Popen(
        [sys.executable, "-c", CHILD, kind, path, MAIN, prefix, mode],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env, text=True,
    )
    try:
        assert child.stdout.readline().strip() == "READY"
        time.sleep(rng.uniform(0.0, 0.12))  # somewhere in the middle of a stream of saves
    finally:
        child.kill()
        output = child.stdout.read()
        child.wait()
    acked = [int(line.split()[1]) for line in output.splitlines() if line.startswith("ACK ")]
    return acked


@pytest.mark.parametrize("kind", ["json", "sqlite"])
def test_a_store_survives_being_killed_in_the_middle_of_a_save(kind, tmp_path):
    path = str(tmp_path / ("server_data.json" if kind == "json" else "server_data.db"))
    Store = JsonStore if kind == "json" else SqliteStore
    total_acked = 0

    for round_number in range(RUNS):
        prefix = f"r{round_number}-"
        acked = one_round(kind, path, round_number * 7919 + 13, prefix, "one")
        assert acked == list(range(len(acked)))

        store = Store(path)
        status = store.open()
        assert status == "ok", f"round {round_number}: the store needed repair after a kill ({status})"
        every_song = store.songs()
        songs = [s["name"] for s in every_song if s["name"].startswith(prefix)]
        # every acknowledged song is there, in order, with no gaps and no repeats ...
        assert songs[:len(acked)] == [f"{prefix}{i}" for i in range(len(acked))]
        # ... and the only other thing that can be there is the one being saved when the kill came
        assert len(songs) in (len(acked), len(acked) + 1)
        assert songs == [f"{prefix}{i}" for i in range(len(songs))]
        assert len({s["id"] for s in every_song}) == len(every_song)
        total_acked += len(acked)
        check_database(kind, path, store)

    assert total_acked > 0, "the child never saved anything: the test did not test anything"


@pytest.mark.parametrize("kind", ["json", "sqlite"])
def test_a_save_of_many_rows_is_all_or_nothing(kind, tmp_path):
    path = str(tmp_path / ("server_data.json" if kind == "json" else "server_data.db"))
    Store = JsonStore if kind == "json" else SqliteStore
    total_acked = 0

    for round_number in range(RUNS):
        prefix = f"b{round_number}-"
        acked = one_round(kind, path, round_number * 104729 + 7, prefix, "batch")
        assert acked == list(range(len(acked)))

        store = Store(path)
        status = store.open()
        assert status == "ok", f"round {round_number}: the store needed repair after a kill ({status})"
        chips = [c for c in store.chips() if c["uid"].startswith(prefix)]
        songs = [s for s in store.songs() if s["uri"].startswith("spotify:track:") and s["name"].startswith("c")]
        batches = {}
        for chip in chips:
            batches.setdefault(chip["uid"].split("-")[1], []).append(chip)
        # every batch that is there is there whole (40 chips, each with its song) ...
        assert all(len(group) == 40 for group in batches.values()), \
            f"round {round_number}: a batch was half saved: {[len(g) for g in batches.values()]}"
        assert all(c["song_id"] and c["uri"] if "uri" in c else c["song_id"] for c in chips)
        # ... every acknowledged batch is there, and at most one more (the one being saved)
        assert len(batches) in (len(acked), len(acked) + 1)
        total_acked += len(acked)
        check_database(kind, path, store)

    assert total_acked > 0


def check_database(kind, path, store):
    if hasattr(store, "close"):
        store.close()
    if kind == "sqlite":
        conn = sqlite3.connect(path)
        try:
            assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        finally:
            conn.close()
