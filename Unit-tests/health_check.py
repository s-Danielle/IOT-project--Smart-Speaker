#!/usr/bin/env python3
from smbus2 import SMBus
import subprocess
import sys

I2C_BUS_ID = 1

I2C_DEVICES = {
    0x24: "NFC Reader (0x24)",
    0x27: "PCF8574 IO Expander (0x27)",
}

def check_i2c_device(bus, addr):
    try:
        bus.read_byte(addr)
        return True
    except OSError:
        return False

def check_respeaker_alsa():
    try:
        out = subprocess.check_output(["aplay", "-l"], text=True)
    except Exception:
        return False

    # ReSpeaker usually shows as seeed / voicecard / respeaker
    text = out.lower()
    return any(k in text for k in ["seeed", "voicecard", "respeaker"])

def main():
    ok = True

    print("=== I2C devices ===")
    with SMBus(I2C_BUS_ID) as bus:
        for addr, name in I2C_DEVICES.items():
            present = check_i2c_device(bus, addr)
            status = "OK ✅" if present else "MISSING ❌"
            print(f"{name}: {status}")
            if not present:
                ok = False

    print("\n=== ReSpeaker ALSA card ===")
    respeaker_ok = check_respeaker_alsa()
    print(f"ReSpeaker ALSA device: {'OK ✅' if respeaker_ok else 'MISSING ❌'}")
    if not respeaker_ok:
        ok = False

    print("\nOverall:", "✅ HEALTHY" if ok else "❌ PROBLEM DETECTED")
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()

