#!/usr/bin/env python3
"""
Tag setup script for PN532 NFC reader on I2C (address 0x24).

- Waits for NFC tags.
- For each UID, prompts for:
  - friendly name
  - Spotify/Mopidy URI
- Saves/updates tags.json with:
  {
    "uidhex": {
      "name": "...",
      "uri": "...",
      "added_at": "ISO_TIMESTAMP"
    }
  }
"""

import json
import os
from datetime import datetime
import time

import board
import busio
from adafruit_pn532.i2c import PN532_I2C

CONFIG_PATH = "tags.json"
PN532_I2C_ADDRESS = 0x24


# ---------- NFC READER SETUP ----------

def init_pn532():
    # I²C bus on Raspberry Pi (SCL/SDA pins)
    i2c = busio.I2C(board.SCL, board.SDA)
    pn532 = PN532_I2C(i2c, debug=False, address=PN532_I2C_ADDRESS)
    # Configure board to read RFID tags
    pn532.SAM_configuration()
    return pn532


def read_uid_blocking(pn532):
    """
    Block until a tag is present and return its UID (as bytes).
    """
    while True:
        uid = pn532.read_passive_target(timeout=0.5)
        if uid is not None:
            return uid
        # small sleep to avoid busy loop
        time.sleep(0.1)


def uid_to_str(uid):
    """
    Normalize UID to a hex string, e.g. '04a2243bcf2280'.
    Works if uid is bytes or list of ints.
    """
    if isinstance(uid, bytes):
        return uid.hex()
    if isinstance(uid, (list, tuple)):
        return "".join(f"{b:02x}" for b in uid)
    return str(uid)


# ---------- CONFIG HELPERS ----------

def load_config(path=CONFIG_PATH):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(config, path=CONFIG_PATH):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


# ---------- MAIN LOOP ----------

def main():
    print("📻 Tag setup for PN532 @ 0x24")
    print("Scanning for tags. Press Ctrl+C to exit.\n")

    pn532 = init_pn532()
    config = load_config()

    try:
        while True:
            print("Waiting for tag...")
            uid = read_uid_blocking(pn532)
            uid_str = uid_to_str(uid)
            print(f"\nDetected tag UID: {uid_str}")

            existing = config.get(uid_str)
            if existing:
                print(f"Already configured as: '{existing['name']}' → {existing['uri']}")
                choice = input("Update this entry? [y/N]: ").strip().lower()
                if choice != "y":
                    print("Skipping.\n")
                    # wait for tag removal before continuing to avoid instant re-read
                    _wait_for_tag_removed(pn532, uid)
                    continue

            # Get info from user
            name = input("Enter chip name (friendly name): ").strip()
            uri = input("Enter Spotify/Mopidy URI: ").strip()

            if not name or not uri:
                print("Name and URI are required, not saving.\n")
                _wait_for_tag_removed(pn532, uid)
                continue

            config[uid_str] = {
                "name": name,
                "uri": uri,
                "added_at": datetime.now().isoformat(timespec="seconds"),
            }

            save_config(config)
            print("✅ Saved.\n")

            # Wait for tag to be removed so we don't immediately read the same one again
            _wait_for_tag_removed(pn532, uid)

    except KeyboardInterrupt:
        print("\nExiting tag setup. Bye 👋")


def _wait_for_tag_removed(pn532, last_uid, timeout=10.0):
    """
    Optional helper: wait until the current tag is removed
    so we don't instantly detect the same UID again.
    """
    start = time.time()
    while time.time() - start < timeout:
        uid = pn532.read_passive_target(timeout=0.3)
        if uid is None:
            return
        # if it's a different tag, we also break – next loop will handle it
        if uid_to_str(uid) != uid_to_str(last_uid):
            return


if __name__ == "__main__":
    main()

