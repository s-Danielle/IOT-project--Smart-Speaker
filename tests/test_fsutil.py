"""The shared file helpers used by both stores and the converter."""

import os

from storage import fsutil


def touch(folder, name, age):
    path = folder / name
    path.write_text(name)
    os.utime(path, (1_000_000 + age, 1_000_000 + age))
    return path


def test_only_the_newest_copies_are_kept(tmp_path):
    for n in range(6):
        touch(tmp_path, f"data.corrupt-{n}", n)
    touch(tmp_path, "data", 99)  # not a copy: never touched
    touch(tmp_path, "other.corrupt-1", 0)
    fsutil.keep_newest(str(tmp_path), "data.corrupt-", 3)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["data", "data.corrupt-3", "data.corrupt-4", "data.corrupt-5", "other.corrupt-1"]


def test_companion_files_go_with_their_copy_and_are_not_counted_alone(tmp_path):
    for n in range(4):
        touch(tmp_path, f"db.corrupt-{n}", n)
        touch(tmp_path, f"db.corrupt-{n}-wal", n)
        touch(tmp_path, f"db.corrupt-{n}-shm", n)
    fsutil.keep_newest(str(tmp_path), "db.corrupt-", 2, companions=("-wal", "-shm"))
    left = sorted(p.name for p in tmp_path.iterdir())
    assert left == ["db.corrupt-2", "db.corrupt-2-shm", "db.corrupt-2-wal", "db.corrupt-3", "db.corrupt-3-shm", "db.corrupt-3-wal"]


def test_fewer_copies_than_the_limit_are_all_kept(tmp_path):
    touch(tmp_path, "x.corrupt-1", 1)
    fsutil.keep_newest(str(tmp_path), "x.corrupt-", 3)
    assert [p.name for p in tmp_path.iterdir()] == ["x.corrupt-1"]


def test_syncing_a_folder_that_does_not_exist_is_harmless(tmp_path):
    fsutil.sync_directory(str(tmp_path / "nowhere"))
    fsutil.sync_directory(str(tmp_path))
