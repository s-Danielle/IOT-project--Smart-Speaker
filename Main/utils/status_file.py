"""The controller's status file: proof that it is alive, and what it is doing.

The controller (smart_speaker.service) writes /run/smart_speaker/status.json about once a second.
The server shows it at /status and /health, and the health monitor lights the health LED from it.
Before this, "the controller is running" meant only "systemd says the process exists": a controller
stuck in its loop looked fine.

The proof of life is `monotonic`, the controller's clock reading when it wrote the file. That clock
only counts up and is shared by every program on the machine, so it cannot be fooled by the
speaker's wall clock being wrong (the Pi has no battery clock and starts with the wrong date).
/run is emptied at every boot, so a file is always from this boot.

The file is replaced by renaming a finished temporary file over it, so a reader never sees half of
it. Nothing in here uses the speaker's hardware, so the server and the tests can import it.
"""

import json
import os
import subprocess
import time

DEFAULT_PATH = "/run/smart_speaker/status.json"
STATUS_STALE_AFTER = 20.0  # seconds without a new write before the controller counts as stuck or dead
SCHEMA = 1


def status_path() -> str:
    return os.environ.get("SPEAKER_STATUS_FILE", DEFAULT_PATH)


def write_status(content: dict, path=None) -> bool:
    """Write the status. Returns False if it could not be written (for example the folder is missing)."""
    path = path or status_path()
    data = dict(content, schema=SCHEMA, monotonic=time.monotonic())
    tmp = f"{path}.tmp.{os.getpid()}"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.chmod(tmp, 0o644)  # the server and the health monitor run as other users
        os.replace(tmp, path)
        return True
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False


def read_status(path=None, now=None) -> dict:
    """The controller's status plus `alive` (is it running its loop?) and `age_seconds`.

    When it is not alive, `problem` says why in a sentence. Never raises.
    """
    path = path or status_path()
    now = time.monotonic() if now is None else now
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = json.load(f)
        if not isinstance(content, dict):
            raise ValueError("not an object")
    except FileNotFoundError:
        return {"alive": False, "age_seconds": None, "problem": "the controller is not running (it has not written a status file)"}
    except (OSError, ValueError) as exc:
        return {"alive": False, "age_seconds": None, "problem": f"the controller's status file cannot be read ({exc})"}

    written = content.get("monotonic")
    if isinstance(written, bool) or not isinstance(written, (int, float)):
        return dict(content, alive=False, age_seconds=None, problem="the controller's status file has no timestamp")
    age = now - written
    if age < -1.0:
        return dict(content, alive=False, age_seconds=None, problem="the controller's status file is from another boot")
    age = max(0.0, age)
    result = dict(content, age_seconds=round(age, 1))
    if age > STATUS_STALE_AFTER:
        result.update(alive=False, problem=f"the controller has not updated its status for {int(age)} seconds (it may be stuck)")
    else:
        result.update(alive=True, problem=None)
    return result


def git_version(folder) -> str:
    """The short git commit of the program folder, for the status ('unknown' if it can't be found)."""
    try:
        result = subprocess.run(["git", "-C", folder, "rev-parse", "--short", "HEAD"],
                                capture_output=True, text=True, timeout=3)
        return result.stdout.strip() or "unknown" if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"
