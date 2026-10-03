#!/usr/bin/env python3
"""Check the speaker's SQLite database and write a copy of its data as a JSON file.

Run it ON THE PI. It only READS the database (the speaker can stay running):

    python3 /tmp/pi/db_export_json.py                 # check the database and say what is in it
    python3 /tmp/pi/db_export_json.py --write         # also write /tmp/speaker_data_export.json
    python3 /tmp/pi/db_export_json.py --write --out ~/my-copy.json

What this is for: a copy you can read, keep or hand to someone, and a way to get your chips and
songs out if the speaker will not start. It is NOT how you switch the speaker back to JSON. For
that, set SPEAKER_STORAGE=json and restart the server: it moves the data across by itself, checks
it, and keeps the database as server_data.db.exported-<date> (see BRINGUP.md, step 5).

By default the copy is written to /tmp, not next to the database, because a JSON file next to a
live database makes the server warn at every start.
"""

import argparse
import os
import sqlite3
import sys

sys.dont_write_bytecode = True  # a root run must not leave root-owned .pyc files in /tmp/pi

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REPO = "/home/iot-proj/IOT-project--Smart-Speaker"
DEFAULT_OUT = "/tmp/speaker_data_export.json"


def find_repo(explicit=None):
    """The folder that holds Main/storage. /tmp/pi has only the scripts, so this is usually the Pi's checkout."""
    candidates = [explicit] if explicit else [os.path.dirname(os.path.dirname(HERE)), DEFAULT_REPO]
    for folder in candidates:
        if folder and os.path.isfile(os.path.join(folder, "Main", "storage", "convert.py")):
            return folder
    return None


def look_inside(db_path):
    """(problems, counts). Opens the database read-only and runs its own check."""
    uri = "file:%s?mode=ro" % db_path
    conn = sqlite3.connect(uri, uri=True, timeout=5)
    try:
        problems = [row[0] for row in conn.execute("PRAGMA integrity_check")]
        problems = [] if problems == ["ok"] else problems
        broken = conn.execute("PRAGMA foreign_key_check").fetchall()
        if broken:
            problems.append("%d chip(s) point at a song that is not there" % len(broken))
        counts = {
            "chips": conn.execute("SELECT COUNT(*) FROM chips").fetchone()[0],
            "songs": conn.execute("SELECT COUNT(*) FROM songs").fetchone()[0],
            "days of usage": conn.execute("SELECT COUNT(*) FROM daily_usage").fetchone()[0],
        }
        version = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
        counts["schema version"] = version[0] if version else "?"
    finally:
        conn.close()
    return problems, counts


def main(argv=None):
    parser = argparse.ArgumentParser(description="Check the speaker's SQLite database and optionally write its data as JSON.")
    parser.add_argument("--repo", help="the speaker's program folder (default: found automatically)")
    parser.add_argument("--db", help="the database file (default: Main/server_data.db in the program folder)")
    parser.add_argument("--write", action="store_true", help="write the JSON copy (otherwise only check)")
    parser.add_argument("--out", default=DEFAULT_OUT, help="where to write it (default: %(default)s)")
    parser.add_argument("--overwrite", action="store_true", help="replace the output file if it exists (the old one is kept next to it)")
    args = parser.parse_args(argv)

    repo = find_repo(args.repo)
    if repo is None:
        print("I cannot find the speaker's program folder (Main/storage). Say where it is with --repo.")
        return 2
    db_path = args.db or os.path.join(repo, "Main", "server_data.db")
    if not os.path.isfile(db_path):
        print("There is no database at %s." % db_path)
        print("(If the speaker is using the JSON file, there is nothing to export: the data is already in %s.)" % os.path.join(repo, "Main", "server_data.json"))
        return 1

    sys.path.insert(0, os.path.join(repo, "Main"))
    from storage import convert  # noqa: E402

    try:
        problems, counts = look_inside(db_path)
    except sqlite3.Error as exc:
        print("The database cannot be read: %s" % exc)
        return 1
    print("Database: %s" % db_path)
    for name, value in counts.items():
        print("  %s: %s" % (name, value))
    if problems:
        print("PROBLEM: the database failed its own check:")
        for line in problems[:5]:
            print("  " + line)
        return 1
    print("The database passes its own check.")

    if not args.write:
        print("Nothing was written. Add --write to make a JSON copy at %s." % args.out)
        return 0
    if os.path.exists(args.out) and not args.overwrite:
        print("%s already exists. Choose another name with --out, or add --overwrite (the old file is kept next to it)." % args.out)
        return 1
    live_json = os.path.join(os.path.dirname(db_path), "server_data.json")
    if os.path.abspath(args.out) == os.path.abspath(live_json):
        print("Not writing to %s: that is the file the speaker uses in JSON mode, and a JSON file next to a live" % live_json)
        print("database makes it warn at every start. To switch the speaker to JSON, follow BRINGUP.md step 5 (SPEAKER_STORAGE=json).")
        return 1
    try:
        convert.export_database_to_json(db_path, args.out)
    except convert.ConversionFailed as exc:
        print("The export failed, and the database was not changed: %s" % exc)
        return 1
    print("Wrote %s and checked it against the database: it matches." % args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
