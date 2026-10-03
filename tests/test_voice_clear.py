"""Voice "clear": take the song off the loaded chip."""

import urllib.request

import pytest

import fakes
from core import actions
from core.state import ChipData, DeviceState, State


class FakeResponse:
    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def loaded(state=State.PLAYING, chip_id="chip-1"):
    metadata = {"id": chip_id} if chip_id else {}
    chip = ChipData(uid="AA", name="Chip", uri="spotify:track:x", metadata=metadata)
    return DeviceState(state=state, loaded_chip=chip)


@pytest.fixture
def server(monkeypatch):
    """Pretend the local server answers with `status`, or fails if `error` is set."""
    box = {"status": 204, "error": None, "requests": []}

    def fake_urlopen(request, timeout=5):
        box["requests"].append((request.get_method(), request.full_url))
        if box["error"]:
            raise box["error"]
        return FakeResponse(box["status"])

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return box


def test_clear_works_when_the_server_answers_204(server):
    # The server answers 204 No Content. The code used to expect 200 and call that a failure.
    audio, ui = fakes.FakeAudio(), fakes.FakeUI()
    state = actions.action_voice_clear_assignment(loaded(), audio, ui)
    assert state.state == State.IDLE_CHIP_LOADED
    assert state.loaded_chip.uri == ""
    assert audio.names() == ["stop"]
    assert "on_clear_chip" in ui.names()
    assert server["requests"] == [("DELETE", "http://localhost:8080/chips/chip-1/assignment")]


def test_clear_also_accepts_200(server):
    server["status"] = 200
    state = actions.action_voice_clear_assignment(loaded(), fakes.FakeAudio(), fakes.FakeUI())
    assert state.loaded_chip.uri == ""


def test_failed_clear_does_not_stop_the_music(server):
    # The music used to be stopped first, so a failure left the speaker silent while it showed PLAYING.
    server["error"] = OSError("server down")
    audio, ui = fakes.FakeAudio(), fakes.FakeUI()
    state = actions.action_voice_clear_assignment(loaded(), audio, ui)
    assert state.state == State.PLAYING
    assert state.loaded_chip.uri == "spotify:track:x"
    assert audio.names() == []
    assert "on_error" in ui.names()


def test_unexpected_http_status_does_not_stop_the_music(server):
    server["status"] = 500
    audio = fakes.FakeAudio()
    state = actions.action_voice_clear_assignment(loaded(), audio, fakes.FakeUI())
    assert state.state == State.PLAYING
    assert audio.names() == []


def test_clear_without_a_chip_id_does_not_stop_the_music(server):
    audio, ui = fakes.FakeAudio(), fakes.FakeUI()
    state = actions.action_voice_clear_assignment(loaded(chip_id=None), audio, ui)
    assert state.state == State.PLAYING
    assert audio.names() == []
    assert server["requests"] == []
    assert "on_error" in ui.names()


def test_clear_while_paused_stops_and_unloads_the_song(server):
    audio = fakes.FakeAudio()
    state = actions.action_voice_clear_assignment(loaded(state=State.PAUSED), audio, fakes.FakeUI())
    assert state.state == State.IDLE_CHIP_LOADED
    assert audio.names() == ["stop"]
