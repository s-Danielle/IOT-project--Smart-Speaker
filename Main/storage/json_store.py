"""The speaker's data (chips, songs, parental controls, daily usage) in one JSON file.

Same file format as before, so the Flutter app and the old code still read it. What is new is
how it is saved: a power cut or a crash can no longer leave a half-written file.

    1. The new content goes into server_data.json.tmp, and is forced out to the SD card.
    2. The current file is kept as server_data.json.bak (a hard link, so there is never a moment
       without a good copy).
    3. The .tmp file is renamed over the real one. A rename either happens or it doesn't.

If the file is damaged anyway (for example by hand editing), the last good copy in .bak is used,
and the damaged file is kept as server_data.json.corrupt-<time> so nothing is lost.
"""

import copy
import json
import os
import shutil
import threading
import time
from datetime import date

from utils.logger import log, log_error

from . import rules

CORRUPT_COPIES_KEPT = 3


class JsonStore:
    kind = "json"

    def __init__(self, path, today=None):
        self.path = path
        self.backup_path = path + ".bak"
        self._today = today or (lambda: date.today().isoformat())
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Start-up
    # ------------------------------------------------------------------

    def open(self) -> str:
        """Call once at start-up. Creates the file on first run and repairs a damaged one.

        Returns 'ok', 'new', 'recovered' (from the backup) or 'damaged' (nothing usable was
        left, so it started empty). The server logs it.
        """
        with self._lock:
            data, status = self._load()
            if status == "new":
                self._save(data)
            return status

    def write_all(self, data):
        """Replace everything (used when the data is moved here from the SQLite database)."""
        with self._lock:
            self._load()  # a damaged file already there is set aside first, so it can't become the .bak
            self._save(self._complete(data))

    def import_legacy_tags(self, tags) -> int:
        """Add chips from the old tags.json format ({uid: {name, uri}}). Returns how many were added.

        The server calls this only on the very first run. It used to run on every start, which
        brought back chips that had been deleted in the app.
        """
        if not isinstance(tags, dict):
            return 0

        def change(data):
            known = {c.get("uid") for c in data["chips"]}
            added = 0
            for uid, tag in tags.items():
                if uid in known or not isinstance(tag, dict):
                    continue
                song_id = None
                uri = tag.get("uri", "")
                if uri:
                    song_id = next((s["id"] for s in data["library"] if s.get("uri") == uri), None)
                    if song_id is None:
                        song_id = rules.new_song_id({s["id"] for s in data["library"]})
                        data["library"].append({"id": song_id, "name": tag.get("name", "Migrated Song"), "uri": uri})
                name = tag.get("name", f"Chip {len(data['chips']) + 1}")
                data["chips"].append({
                    "id": rules.new_chip_id({c["id"] for c in data["chips"]}),
                    "uid": uid,
                    "name": name,
                    "song_id": song_id,
                    "song_name": name if song_id else None,
                })
                added += 1
            return added, added > 0

        added = self._change(change)
        if added:
            log(f"Imported {added} chips from the old tags.json")
        return added

    # ------------------------------------------------------------------
    # Chips
    # ------------------------------------------------------------------

    def chips(self) -> list:
        data, _ = self._load()
        names = {s["id"]: s.get("name") for s in data["library"]}
        return [self._chip_view(c, names) for c in data["chips"]]

    def get_chip(self, chip_id):
        return next((c for c in self.chips() if c.get("id") == chip_id), None)

    def find_chip_by_uid(self, uid):
        return next((c for c in self.chips() if rules.same_uid(c.get("uid"), uid)), None)

    def lookup_chip(self, uid):
        """What the speaker needs when a chip is tapped: the chip plus the link of its song.

        One read, so the chip and its song always belong together. 'uri' is '' when the chip has
        no song. Returns None for a chip we have not seen.
        """
        data, _ = self._load()
        uris = {s["id"]: s.get("uri", "") for s in data["library"]}
        names = {s["id"]: s.get("name") for s in data["library"]}
        for chip in data["chips"]:
            if rules.same_uid(chip.get("uid"), uid):
                result = self._chip_view(chip, names)
                result["uri"] = uris.get(chip.get("song_id"), "") if chip.get("song_id") else ""
                return result
        return None

    def register_chip(self, uid, name=None) -> dict:
        """Add a chip that was scanned for the first time. A chip that is already known is returned as it is."""
        if not isinstance(uid, str) or not uid:
            raise ValueError("uid is required")
        if name is not None and not isinstance(name, str):
            raise ValueError("name must be text")

        def change(data):
            for chip in data["chips"]:
                if rules.same_uid(chip.get("uid"), uid):
                    return chip, False
            chip = {
                "id": rules.new_chip_id({c["id"] for c in data["chips"]}),
                "uid": uid,
                "name": name or f"Chip {len(data['chips']) + 1}",
                "song_id": None,
                "song_name": None,
            }
            data["chips"].append(chip)
            return chip, True

        chip = self._change(change)
        log(f"Registered new chip: {chip['name']} (UID: {uid[:20]}...)")
        return self._chip_view(chip, {})

    def update_chip(self, chip_id, changes):
        """Change a chip's name and/or song. Returns the chip, or None if there is no such chip.

        Raises ValueError for a bad value, including a song_id that is not in the library.
        """
        if not isinstance(changes, dict):
            raise ValueError("changes must be an object")
        if "name" in changes and not isinstance(changes["name"], str):
            raise ValueError("name must be text")

        def change(data):
            chip = next((c for c in data["chips"] if c.get("id") == chip_id), None)
            if chip is None:
                return None, False
            if "name" in changes:
                chip["name"] = changes["name"]
            if "song_id" in changes:
                song_id = changes["song_id"]
                if song_id is None:
                    chip["song_id"], chip["song_name"] = None, None
                else:
                    song = next((s for s in data["library"] if s.get("id") == song_id), None)
                    if song is None:
                        raise ValueError(f"there is no song {song_id!r} in the library")
                    chip["song_id"], chip["song_name"] = song["id"], song.get("name")
            return self._chip_view(chip, {s["id"]: s.get("name") for s in data["library"]}), True

        chip = self._change(change)
        if chip is not None:
            log(f"Updated chip {chip_id}: {chip}")
        return chip

    def clear_chip_assignment(self, chip_id) -> bool:
        def change(data):
            chip = next((c for c in data["chips"] if c.get("id") == chip_id), None)
            if chip is None:
                return False, False
            chip["song_id"], chip["song_name"] = None, None
            return True, True

        found = self._change(change)
        if found:
            log(f"Reset assignment for chip {chip_id}")
        return found

    def delete_chip(self, chip_id) -> bool:
        def change(data):
            kept = [c for c in data["chips"] if c.get("id") != chip_id]
            found = len(kept) != len(data["chips"])
            data["chips"] = kept
            return found, found

        found = self._change(change)
        if found:
            log(f"Deleted chip {chip_id}")
        return found

    # ------------------------------------------------------------------
    # Songs
    # ------------------------------------------------------------------

    def songs(self) -> list:
        data, _ = self._load()
        return data["library"]

    def add_song(self, name, uri) -> dict:
        if not isinstance(name, str) or not isinstance(uri, str):
            raise ValueError("name and uri must be text")

        def change(data):
            song = {"id": rules.new_song_id({s["id"] for s in data["library"]}), "name": name, "uri": uri}
            data["library"].append(song)
            return song, True

        song = self._change(change)
        log(f"Added to library: {name} ({uri})")
        return song

    def update_song(self, song_id, changes):
        """Rename a song or change its link. Chips that use it show the new name. None if there is no such song."""
        if not isinstance(changes, dict):
            raise ValueError("changes must be an object")
        for field in ("name", "uri"):
            if field in changes and not isinstance(changes[field], str):
                raise ValueError(f"{field} must be text")

        def change(data):
            song = next((s for s in data["library"] if s.get("id") == song_id), None)
            if song is None:
                return None, False
            song["name"] = changes.get("name", song.get("name", ""))
            song["uri"] = changes.get("uri", song.get("uri", ""))
            for chip in data["chips"]:
                if chip.get("song_id") == song_id:
                    chip["song_name"] = song["name"]
            return dict(song), True

        song = self._change(change)
        if song is not None:
            log(f"Updated song {song_id}: {song}")
        return song

    def delete_song(self, song_id) -> bool:
        """Delete a song. Chips that used it are left with no song."""
        def change(data):
            kept = [s for s in data["library"] if s.get("id") != song_id]
            if len(kept) == len(data["library"]):
                return False, False
            data["library"] = kept
            for chip in data["chips"]:
                if chip.get("song_id") == song_id:
                    chip["song_id"], chip["song_name"] = None, None
                    log(f"Cleared song {song_id} from chip {chip.get('id')}")
            return True, True

        found = self._change(change)
        if found:
            log(f"Deleted song {song_id}")
        return found

    # ------------------------------------------------------------------
    # Parental controls and usage
    # ------------------------------------------------------------------

    def parental_controls(self) -> dict:
        data, _ = self._load()
        return rules.complete_parental_controls(data["parental_controls"])

    def update_parental_controls(self, changes) -> dict:
        def change(data):
            data["parental_controls"] = rules.apply_parental_changes(data["parental_controls"], changes)
            return copy.deepcopy(data["parental_controls"]), True

        updated = self._change(change)
        log(f"Updated parental controls: {updated}")
        return updated

    def daily_usage(self) -> dict:
        """Today's playing time. A new day starts at zero (nothing is written for that)."""
        data, _ = self._load()
        usage = data["daily_usage"]
        today = self._today()
        if usage.get("date") != today:
            return {"date": today, "seconds": 0}
        return {"date": today, "seconds": int(usage.get("seconds", 0))}

    def add_daily_usage(self, seconds) -> dict:
        add = max(0, rules.whole_number(seconds, "seconds"))

        def change(data):
            today = self._today()
            usage = data["daily_usage"]
            if usage.get("date") != today:
                usage = {"date": today, "seconds": 0}
            usage["seconds"] = int(usage.get("seconds", 0)) + add
            data["daily_usage"] = usage
            return dict(usage), True

        usage = self._change(change)
        log(f"Daily usage updated: {usage['seconds']} seconds")
        return usage

    # ------------------------------------------------------------------
    # Reading and saving the file
    # ------------------------------------------------------------------

    @staticmethod
    def _chip_view(chip, song_names) -> dict:
        """The chip as the app sees it. The song name always comes from the song itself."""
        view = dict(chip)
        song_id = view.get("song_id")
        view["song_name"] = song_names.get(song_id) if song_id else None
        return view

    def _change(self, change):
        """Read the file, let `change(data)` edit it, save. `change` returns (result, changed)."""
        with self._lock:
            data, _ = self._load()
            result, changed = change(data)
            if changed:
                self._save(data)
            return result

    def _load(self):
        """Return (data, status). Never fails because of a bad file; see open() for the statuses.

        A damaged or missing file is repaired on the spot (the good copy is written back as the
        real file), so the repair is logged once and not on every read.
        """
        with self._lock:
            main = self._try_read(self.path)
            if main is not None:
                return main, "ok"
            main_exists = os.path.exists(self.path)
            if main_exists:
                self._set_aside_damaged_file()
            backup = self._try_read(self.backup_path)
            if backup is not None:
                log_error(f"[STORAGE] {self.path} was {'damaged' if main_exists else 'missing'}; using the last good copy ({self.backup_path})")
                self._save(backup)
                return backup, "recovered"
            if main_exists:
                log_error(f"[STORAGE] {self.path} was damaged and there is no good backup: starting empty (the damaged file was kept)")
                empty = rules.default_data()
                self._save(empty)
                return empty, "damaged"
            return rules.default_data(), "new"

    def _try_read(self, path):
        """The file's content as a complete data dict, or None if it is missing or unusable."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return self._complete(data)
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as exc:  # a bad file, or json.JSONDecodeError (a ValueError)
            log_error(f"[STORAGE] cannot use {path}: {exc}")
            return None

    @staticmethod
    def _complete(data) -> dict:
        """Fill in keys that older files lack, and refuse content of the wrong shape."""
        if not isinstance(data, dict):
            raise ValueError("the file does not hold an object")
        for key in ("chips", "library"):
            data.setdefault(key, [])
            if not isinstance(data[key], list) or not all(isinstance(item, dict) for item in data[key]):
                raise ValueError(f"'{key}' is not a list of objects")
        if not isinstance(data.get("parental_controls"), dict):
            data["parental_controls"] = rules.complete_parental_controls(None)
        if not isinstance(data.get("daily_usage"), dict):
            data["daily_usage"] = {}
        return data

    def _set_aside_damaged_file(self):
        stamp = time.strftime("%Y%m%d-%H%M%S")
        target, n = f"{self.path}.corrupt-{stamp}", 1
        while os.path.exists(target):
            n += 1
            target = f"{self.path}.corrupt-{stamp}-{n}"
        try:
            os.replace(self.path, target)
            log_error(f"[STORAGE] the damaged file was kept as {target}")
        except OSError as exc:
            log_error(f"[STORAGE] could not move the damaged file aside: {exc}")
            return
        directory = os.path.dirname(self.path) or "."
        prefix = os.path.basename(self.path) + ".corrupt-"
        old = sorted(
            (os.path.join(directory, name) for name in os.listdir(directory) if name.startswith(prefix)),
            key=os.path.getmtime,
        )
        for path in old[:-CORRUPT_COPIES_KEPT]:
            try:
                os.remove(path)
            except OSError:
                pass

    def _save(self, data):
        directory = os.path.dirname(self.path) or "."
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            self._copy_owner(self.path, tmp)
            if os.path.exists(self.path):
                self._keep_backup()
            os.replace(tmp, self.path)
        except BaseException:
            for leftover in (tmp, self.backup_path + ".new"):
                try:
                    os.remove(leftover)
                except OSError:
                    pass
            raise
        self._sync_directory(directory)

    def _keep_backup(self):
        """Make the current file the .bak copy, without ever leaving the real file missing."""
        staging = self.backup_path + ".new"
        try:
            os.remove(staging)
        except FileNotFoundError:
            pass
        try:
            os.link(self.path, staging)
        except OSError:  # a file system without hard links
            shutil.copy2(self.path, staging)
        os.replace(staging, self.backup_path)

    @staticmethod
    def _copy_owner(source, target):
        """The server runs as root; keep the file's owner and permissions as they were."""
        try:
            info = os.stat(source)
        except FileNotFoundError:
            return
        try:
            os.chmod(target, info.st_mode & 0o777)
            os.chown(target, info.st_uid, info.st_gid)
        except (PermissionError, OSError):
            pass

    @staticmethod
    def _sync_directory(directory):
        """Make the rename itself survive a power cut."""
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
