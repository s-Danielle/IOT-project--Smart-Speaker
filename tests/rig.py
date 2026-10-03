"""A controller wired to fake hardware, with helpers that read like using the speaker."""

import fakes
import core.controller as controller_module
from core.controller import Controller
from core.state import State
from hardware.buttons import ButtonID

NO_LIMITS = {
    "enabled": False,
    "volume_limit": 100,
    "quiet_hours": {"enabled": False, "start": "21:00", "end": "07:00"},
    "daily_limit_minutes": 0,
    "chip_blacklist": [],
    "chip_whitelist_mode": False,
    "chip_whitelist": [],
}

SONG = "spotify:track:abc"


def chip(uid, name="Chip", uri=SONG, chip_id="chip-1"):
    """What ChipStore.lookup returns for a known chip."""
    return {"uid": uid, "name": name, "uri": uri, "id": chip_id}


class Rig:
    """Build with Rig(monkeypatch). Parental controls are off until set_parental()."""

    def __init__(self, monkeypatch, chips=None, voice_command=None, ptt_leds=None, volume=50, parental=None):
        self.nfc = fakes.FakeNFC()
        self.chip_store = fakes.FakeChipStore(chips if chips is not None else {"AA": chip("AA"), "BB": chip("BB", "Other", chip_id="chip-2")})
        self.buttons = fakes.FakeButtons()
        self.audio = fakes.FakeAudio()
        self.mixer = fakes.FakeMixer(volume=volume)
        self.ui = fakes.FakeUI()
        self.mic = fakes.FakeMic()
        self.recorder = fakes.FakeRecorder()
        self.parental = dict(parental) if parental is not None else dict(NO_LIMITS)
        self.usage_today = 0
        self.usage_added = []
        monkeypatch.setattr(controller_module, "get_parental_controls", lambda: self.parental)
        monkeypatch.setattr(controller_module, "get_daily_usage", lambda: self.usage_today)
        monkeypatch.setattr(controller_module, "add_daily_usage", self._add_usage)
        self.controller = Controller(
            nfc=self.nfc,
            chip_store=self.chip_store,
            buttons=self.buttons,
            audio=self.audio,
            mixer=self.mixer,
            ui=self.ui,
            mic=self.mic,
            recorder=self.recorder,
            voice_command=voice_command,
            ptt_leds=ptt_leds,
        )

    def _add_usage(self, seconds):
        self.usage_added.append(seconds)
        return True

    # --- reading the speaker -------------------------------------------------

    @property
    def state(self):
        return self.controller.device_state.state

    def ui_calls(self):
        return self.ui.names()

    # --- using the speaker ---------------------------------------------------

    def step(self, times=1):
        for _ in range(times):
            self.controller.step()

    def tap_chip(self, uid):
        """Put a chip on the reader, then take it away again."""
        self.nfc.uid = uid
        self.step()
        self.nfc.uid = None
        self.step()

    def press(self, button, held=0.0):
        """Press a button and keep it down for `held` seconds."""
        self.buttons.press(button)
        self.step()
        if held:
            self.buttons.hold(button, held)
            self.step()

    def release(self, button):
        self.buttons.release(button)
        self.step()

    def click(self, button, held=0.2):
        self.press(button, held)
        self.release(button)

    def say(self, command):
        """Hold PTT, "say" a command, let go. Needs the rig to be built with voice_command=FakeVoice()."""
        self.controller._voice_command.command = command
        self.press(ButtonID.PTT)
        self.release(ButtonID.PTT)

    def play(self):
        self.click(ButtonID.PLAY_PAUSE)

    def load_and_play(self, uid="AA"):
        self.tap_chip(uid)
        self.play()
        assert self.state == State.PLAYING
