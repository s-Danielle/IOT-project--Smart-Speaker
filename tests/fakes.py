"""Stand-ins for the hardware libraries and for the controller's parts.

They let the speaker's logic run on any computer. Nothing here touches real
hardware, the network, the sound card or a system command.
"""

import sys
import types


# ---------------------------------------------------------------------------
# Hardware libraries (smbus2, alsaaudio, mpd, board/busio/adafruit_pn532)
# ---------------------------------------------------------------------------


class FakeSMBus:
    """smbus2.SMBus. `values` is what read_byte returns per I2C address; writes are recorded."""

    values = {}
    fail = False
    instances = []

    def __init__(self, bus=1):
        self.bus = bus
        self.writes = []  # (address, byte)
        self.closed = False
        FakeSMBus.instances.append(self)

    def read_byte(self, address):
        if FakeSMBus.fail:
            raise OSError(5, "Input/output error")
        return FakeSMBus.values.get(address, 0xFF)

    def write_byte(self, address, value):
        if FakeSMBus.fail:
            raise OSError(5, "Input/output error")
        self.writes.append((address, value))
        FakeSMBus.values[address] = value

    def close(self):
        self.closed = True

    @classmethod
    def reset(cls):
        cls.values = {}
        cls.fail = False
        cls.instances = []


class FakeALSAAudioError(Exception):
    pass


class FakeAlsaMixer:
    """alsaaudio.Mixer on the card's PCM control."""

    fail_open = False
    volumes = [85, 85]

    def __init__(self, control="PCM", cardindex=0):
        if FakeAlsaMixer.fail_open:
            raise FakeALSAAudioError("Unable to find mixer control %s" % control)
        self.control = control

    def getvolume(self):
        return list(FakeAlsaMixer.volumes)

    def setvolume(self, volume):
        FakeAlsaMixer.volumes = [volume, volume]

    @classmethod
    def reset(cls):
        cls.fail_open = False
        cls.volumes = [85, 85]


class FakeMPDConnectionError(Exception):
    pass


class FakeMPDCommandError(Exception):
    """mpd.base.CommandError: Mopidy answered with an ACK."""


class FakeMPDClient:
    """mpd.MPDClient. Set `add_error`/`play_error`/`down` to make Mopidy misbehave."""

    add_error = None
    play_error = None
    down = False  # connect() fails
    state = "stop"
    instances = []

    def __init__(self):
        self.timeout = None
        self.calls = []
        self.connects = 0
        FakeMPDClient.instances.append(self)

    def connect(self, host, port):
        self.connects += 1
        if FakeMPDClient.down:
            raise FakeMPDConnectionError("Connection refused")

    def disconnect(self):
        pass

    def clear(self):
        self.calls.append(("clear",))

    def add(self, uri):
        self.calls.append(("add", uri))
        if FakeMPDClient.add_error:
            raise FakeMPDCommandError(FakeMPDClient.add_error)

    def play(self):
        self.calls.append(("play",))
        if FakeMPDClient.play_error:
            raise FakeMPDCommandError(FakeMPDClient.play_error)

    def pause(self, flag):
        self.calls.append(("pause", flag))

    def stop(self):
        self.calls.append(("stop",))

    def status(self):
        return {"state": FakeMPDClient.state}

    def currentsong(self):
        return {}

    @classmethod
    def reset(cls):
        cls.add_error = None
        cls.play_error = None
        cls.down = False
        cls.state = "stop"
        cls.instances = []


class FakePN532:
    """adafruit_pn532.i2c.PN532_I2C. Set `init_fails` to simulate a reader that is not wired up."""

    init_fails = False
    attempts = 0
    next_uid = None  # bytes returned by read_passive_target

    def __init__(self, i2c, address=0x24, debug=False):
        FakePN532.attempts += 1
        if FakePN532.init_fails:
            raise RuntimeError("Failed to detect PN532")

    def SAM_configuration(self):
        pass

    @property
    def firmware_version(self):
        return (50, 1, 6, 7)

    def read_passive_target(self, timeout=0.3):
        return FakePN532.next_uid

    @classmethod
    def reset(cls):
        cls.init_fails = False
        cls.attempts = 0
        cls.next_uid = None


def _module(name, **attrs):
    module = types.ModuleType(name)
    module.__dict__.update(attrs)
    sys.modules[name] = module
    return module


def install_hardware_stubs():
    """Put the fake libraries in place of the Pi-only ones."""
    _module("smbus2", SMBus=FakeSMBus)
    _module("alsaaudio", Mixer=FakeAlsaMixer, ALSAAudioError=FakeALSAAudioError)
    base = _module("mpd.base", ConnectionError=FakeMPDConnectionError, CommandError=FakeMPDCommandError)
    _module("mpd", MPDClient=FakeMPDClient, base=base)
    _module("board", SCL=3, SDA=2)
    _module("busio", I2C=lambda scl, sda: object())
    i2c = _module("adafruit_pn532.i2c", PN532_I2C=FakePN532)
    _module("adafruit_pn532", i2c=i2c)


def reset_hardware_stubs():
    FakeSMBus.reset()
    FakeAlsaMixer.reset()
    FakeMPDClient.reset()
    FakePN532.reset()


# ---------------------------------------------------------------------------
# The controller's parts
# ---------------------------------------------------------------------------


class CallLog:
    """Records every method called on it as (name, *args). Returns None."""

    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)

        def method(*args, **kwargs):
            self.calls.append((name,) + args)

        return method

    def names(self):
        return [call[0] for call in self.calls]

    def clear(self):
        self.calls.clear()


class FakeUI(CallLog):
    """UIController. `_sounds` records the sound calls the controller makes directly."""

    def __init__(self):
        super().__init__()
        self._sounds = CallLog()


class FakeButtons:
    """hardware.buttons.Buttons. Call press()/release(), then controller.step()."""

    def __init__(self):
        from hardware.buttons import ButtonID

        self.ids = list(ButtonID)
        self._down = {b: False for b in self.ids}
        self._is = {b: False for b in self.ids}
        self._was = {b: False for b in self.ids}
        self._held = {}

    def press(self, button):
        self._down[button] = True

    def release(self, button):
        self._down[button] = False

    def hold(self, button, seconds):
        """Pretend the button has been held that long."""
        self._held[button] = seconds

    def update(self):
        for b in self.ids:
            self._was[b] = self._is[b]
            self._is[b] = self._down[b]

    def is_pressed(self, button):
        return self._is[button]

    def just_pressed(self, button):
        return self._is[button] and not self._was[button]

    def just_released(self, button):
        return not self._is[button] and self._was[button]

    def hold_duration(self, button):
        return self._held.get(button, 0.0) if self._is[button] else 0.0

    def get_release_duration(self, button):
        return self._held.get(button, 0.0) if self.just_released(button) else 0.0

    def close(self):
        pass


class FakeAudio:
    """AudioPlayer.

    `play_ok`: what play_uri returns (False = Mopidy refused the link).
    `confirms`: whether Mopidy ever says "play" afterwards (False = the song never starts).
    `playing`: what Mopidy says right now.
    """

    def __init__(self):
        self.calls = []
        self.play_ok = True
        self.confirms = True
        self.playing = False
        self.last_error = None

    def play_uri(self, uri):
        self.calls.append(("play_uri", uri))
        if self.play_ok:
            self.last_error = None
            self.playing = self.confirms
        else:
            self.last_error = "[50@0] {add} directory or file not found"
        return self.play_ok

    def pause(self):
        self.calls.append(("pause",))
        self.playing = False

    def resume(self):
        self.calls.append(("resume",))
        self.playing = self.confirms
        return True

    def stop(self):
        self.calls.append(("stop",))
        self.playing = False

    def is_playing(self, force_refresh=False):
        return self.playing

    def close(self):
        pass

    def names(self):
        return [c[0] for c in self.calls]


class FakeMixer:
    def __init__(self, volume=50):
        self.volume = volume
        self.set_calls = []

    def get_volume(self):
        return self.volume

    def set_volume(self, volume):
        self.set_calls.append(volume)
        self.volume = volume
        return True

    def volume_up(self):
        self.volume = min(100, self.volume + 10)
        return self.volume

    def volume_down(self):
        self.volume = max(0, self.volume - 10)
        return self.volume


class FakeNFC:
    def __init__(self):
        self.uid = None

    def get_current_uid(self):
        return self.uid

    def start(self):
        pass

    def close(self):
        pass


class FakeChipStore:
    """ChipStore. `chips` maps a UID to the dict lookup() should return."""

    def __init__(self, chips=None):
        self.chips = chips or {}
        self.lookups = []

    def lookup(self, uid):
        self.lookups.append(uid)
        return self.chips.get(uid)


class FakeMic:
    def __init__(self):
        self.owner = None
        self.released = []

    def acquire(self, owner):
        if self.owner:
            return False
        self.owner = owner
        return True

    def release(self, restore=True):
        self.released.append(restore)
        self.owner = None

    def is_held(self):
        return self.owner is not None


class FakeVoice:
    """VoiceCommand. Set `command` to what the speaker "hears" when PTT is released."""

    def __init__(self, command=None):
        self.command = command
        self._recording = False

    def start_recording(self):
        self._recording = True
        return True

    def is_recording(self):
        return self._recording

    def stop_and_parse(self):
        self._recording = False
        return self.command

    def cancel_recording(self):
        self._recording = False

    def get_easter_config(self):
        return {}


class FakeRecorder:
    def __init__(self):
        self.calls = []
        self.saved_path = None  # what stop() returns

    def start(self, name="unknown"):
        self.calls.append(("start", name))
        return True

    def stop(self):
        self.calls.append(("stop",))
        return self.saved_path

    def cancel(self, restore=True):
        self.calls.append(("cancel", restore))

    def is_recording(self):
        return False

    def close(self):
        pass
