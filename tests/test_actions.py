"""The state changes in core/actions.py, one action at a time, with fake audio, recorder and lights.

Each test says which state it starts in, calls the action and checks the new state, what was sent
to the player and which light or sound the user gets. (test_controller_*.py test the same actions
through the buttons; these pin down each one on its own.)
"""

import fakes
import pytest
from core import actions
from core.state import ChipData, DeviceState, State

SONG = "spotify:track:abc"


def chip(uri=SONG, name="Bedtime", chip_id="chip-1"):
    return ChipData(uid="AA", name=name, uri=uri, metadata={"id": chip_id, "uri": uri, "name": name, "uid": "AA"})


def device(state=State.IDLE_CHIP_LOADED, loaded=True, uri=SONG, **extra):
    return DeviceState(state=state, loaded_chip=chip(uri) if loaded else None, **extra)


@pytest.fixture
def audio():
    return fakes.FakeAudio()


@pytest.fixture
def ui():
    return fakes.FakeUI()


@pytest.fixture
def recorder():
    return fakes.FakeRecorder()


# ---------------------------------------------------------------------------
# Loading a chip
# ---------------------------------------------------------------------------


def test_loading_a_chip_from_nothing(audio, ui):
    state = actions.action_load_chip(DeviceState(), {"uid": "AA", "name": "Bedtime", "uri": SONG, "id": "c1"}, audio, ui)
    assert state.state == State.IDLE_CHIP_LOADED
    assert (state.loaded_chip.uid, state.loaded_chip.name, state.loaded_chip.uri) == ("AA", "Bedtime", SONG)
    assert state.loaded_chip.metadata["id"] == "c1"  # voice "clear" needs it
    assert ui.names() == ["on_chip_loaded"] and audio.names() == []  # nothing was playing: nothing to stop


@pytest.mark.parametrize("before", [State.PLAYING, State.PAUSED])
def test_loading_a_chip_while_music_is_active_stops_the_music(audio, ui, before):
    state = actions.action_load_chip(device(before), {"uid": "BB", "name": "Other", "uri": "x"}, audio, ui)
    assert state.state == State.IDLE_CHIP_LOADED and state.loaded_chip.uid == "BB"
    assert audio.names() == ["stop"]


def test_loading_a_chip_forgets_that_music_was_playing_before_a_recording(audio, ui):
    state = actions.action_load_chip(device(was_playing_before_recording=True), {"uid": "BB"}, audio, ui)
    assert state.was_playing_before_recording is False


def test_a_chip_the_server_knows_little_about_still_loads(audio, ui):
    state = actions.action_load_chip(DeviceState(), {"uid": "ZZ"}, audio, ui)
    assert state.loaded_chip.name == "Unknown" and state.loaded_chip.uri == ""


# ---------------------------------------------------------------------------
# Play, pause, resume, stop
# ---------------------------------------------------------------------------


def test_play_starts_the_loaded_song(audio, ui):
    state = actions.action_play(device(), audio, ui)
    assert state.state == State.PLAYING
    assert audio.calls == [("play_uri", SONG)] and ui.names() == ["on_play"]


def test_play_with_no_chip_is_blocked(audio, ui):
    state = actions.action_play(device(loaded=False, state=State.IDLE_NO_CHIP), audio, ui)
    assert state.state == State.IDLE_NO_CHIP
    assert audio.calls == [] and ui.names() == ["on_blocked_action"]


def test_play_with_a_chip_that_has_no_song_is_blocked(audio, ui):
    state = actions.action_play(device(uri=""), audio, ui)
    assert state.state == State.IDLE_CHIP_LOADED
    assert audio.calls == [] and ui.names() == ["on_blocked_action"]


def test_play_uses_the_song_the_app_assigned_a_moment_ago(audio, ui):
    class Store:
        def lookup(self, uid):
            return {"uid": uid, "name": "Bedtime", "uri": "spotify:track:fresh", "id": "chip-1"}

    state = actions.action_play(device(), audio, ui, chip_store=Store())
    assert audio.calls == [("play_uri", "spotify:track:fresh")]
    assert state.loaded_chip.uri == "spotify:track:fresh"


def test_play_keeps_the_old_song_if_the_server_cannot_say(audio, ui):
    class Store:
        def lookup(self, uid):
            return None

    actions.action_play(device(), audio, ui, chip_store=Store())
    assert audio.calls == [("play_uri", SONG)]


def test_play_that_mopidy_refuses_shows_an_error_and_does_not_say_playing(audio, ui):
    audio.play_ok = False
    state = actions.action_play(device(), audio, ui)
    assert state.state == State.IDLE_CHIP_LOADED
    assert ui.names() == ["on_error"]


def test_pause(audio, ui):
    state = actions.action_pause(device(State.PLAYING), audio, ui)
    assert state.state == State.PAUSED
    assert audio.names() == ["pause"] and ui.names() == ["on_pause"]


def test_resume(audio, ui):
    state = actions.action_resume(device(State.PAUSED), audio, ui)
    assert state.state == State.PLAYING
    assert audio.names() == ["resume"] and ui.names() == ["on_play"]


def test_resume_that_cannot_reach_mopidy_stays_paused_and_shows_an_error(audio, ui):
    audio.resume = lambda: False
    state = actions.action_resume(device(State.PAUSED), audio, ui)
    assert state.state == State.PAUSED and ui.names() == ["on_error"]


@pytest.mark.parametrize("loaded, expected", [(True, State.IDLE_CHIP_LOADED), (False, State.IDLE_NO_CHIP)])
def test_stop_goes_back_to_the_right_idle_state(audio, ui, loaded, expected):
    # Playing the latest recording has no chip: stopping must not pretend there is one.
    state = actions.action_stop(device(State.PLAYING, loaded=loaded), audio, ui)
    assert state.state == expected
    assert audio.names() == ["stop"] and ui.names() == ["on_stop"]


# ---------------------------------------------------------------------------
# Clearing the chip
# ---------------------------------------------------------------------------


def test_a_short_press_clear_unloads_the_chip_with_the_stop_sound(audio, ui):
    state = actions.action_clear_chip(device(State.PLAYING, was_playing_before_recording=True), audio, ui)
    assert state.state == State.IDLE_NO_CHIP and state.loaded_chip is None
    assert state.was_playing_before_recording is False
    assert audio.names() == ["stop"] and ui.names() == ["on_stop"]


def test_a_long_press_clear_uses_the_reset_sound(audio, ui):
    state = actions.action_clear_chip(device(), audio, ui, long_press=True)
    assert state.state == State.IDLE_NO_CHIP and ui.names() == ["on_clear_chip"]


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------


def test_recording_needs_a_chip(recorder, ui):
    state = actions.action_start_recording(device(loaded=False, state=State.IDLE_NO_CHIP), recorder, ui)
    assert state.state == State.IDLE_NO_CHIP
    assert recorder.calls == [] and ui.names() == ["on_blocked_action"]


@pytest.mark.parametrize("before, music_active", [
    (State.IDLE_CHIP_LOADED, False), (State.PLAYING, True), (State.PAUSED, True),
])
def test_recording_remembers_whether_music_was_active(recorder, ui, before, music_active):
    state = actions.action_start_recording(device(before), recorder, ui)
    assert state.state == State.RECORDING
    assert state.was_playing_before_recording is music_active
    assert state.previous_state == before
    assert recorder.calls == [("start", "Bedtime")] and ui.names() == ["on_recording"]  # the red light


def test_a_recording_that_cannot_start_leaves_things_as_they_were(recorder, ui):
    recorder.start = lambda name="x": False
    state = actions.action_start_recording(device(State.PLAYING), recorder, ui)
    assert state.state == State.PLAYING  # not RECORDING
    assert state.was_playing_before_recording is False and state.previous_state is None
    assert ui.names() == ["on_error"]


@pytest.fixture
def library(monkeypatch):
    """Records what a saved recording adds to the library, instead of calling the server."""
    added = []
    monkeypatch.setattr(actions, "_add_recording_to_library_via_http", lambda path, name: added.append((path, name)) or True)
    return added


def test_saving_a_recording_adds_it_to_the_library_under_the_chips_name(recorder, ui, library, tmp_path):
    wav = tmp_path / "recording_20261003_120000.wav"
    wav.write_bytes(b"RIFF")
    recorder.saved_path = str(wav)
    state = actions.action_save_recording(device(State.RECORDING), recorder, ui)
    assert library == [(str(wav), "[RECORDING] Bedtime")]
    assert state.state == State.IDLE_CHIP_LOADED and ui.names() == ["on_record_saved"]


def test_saving_names_a_recording_made_without_a_chip_after_its_file(recorder, ui, library, tmp_path):
    wav = tmp_path / "recording_20261003_120000.wav"
    wav.write_bytes(b"RIFF")
    recorder.saved_path = str(wav)
    actions.action_save_recording(device(State.RECORDING, loaded=False), recorder, ui)
    assert library == [(str(wav), "[RECORDING] 20261003_120000")]


def test_saving_after_music_was_playing_returns_to_paused(recorder, ui, library):
    state = actions.action_save_recording(device(State.RECORDING, was_playing_before_recording=True), recorder, ui)
    assert state.state == State.PAUSED and state.was_playing_before_recording is False


def test_saving_when_nothing_was_written_still_ends_the_recording(recorder, ui, library):
    recorder.saved_path = None  # the recorder had nothing
    state = actions.action_save_recording(device(State.RECORDING), recorder, ui)
    assert library == [] and state.state == State.IDLE_CHIP_LOADED


def test_saving_when_the_file_is_missing_adds_nothing(recorder, ui, library, tmp_path):
    recorder.saved_path = str(tmp_path / "gone.wav")
    state = actions.action_save_recording(device(State.RECORDING), recorder, ui)
    assert library == [] and state.state == State.IDLE_CHIP_LOADED


def test_a_library_that_does_not_answer_does_not_lose_the_recording_state(recorder, ui, monkeypatch, tmp_path):
    def broken(path, name):
        raise OSError("server down")

    monkeypatch.setattr(actions, "_add_recording_to_library_via_http", broken)
    wav = tmp_path / "recording_1.wav"
    wav.write_bytes(b"RIFF")
    recorder.saved_path = str(wav)
    state = actions.action_save_recording(device(State.RECORDING), recorder, ui)
    assert state.state == State.IDLE_CHIP_LOADED and ui.names() == ["on_record_saved"]


@pytest.mark.parametrize("previous, expected", [
    (State.PLAYING, State.PLAYING), (State.PAUSED, State.PAUSED),
    (State.IDLE_CHIP_LOADED, State.IDLE_CHIP_LOADED), (None, State.IDLE_CHIP_LOADED),
])
def test_cancelling_a_recording_returns_to_exactly_where_it_was(recorder, ui, previous, expected):
    start = device(State.RECORDING, previous_state=previous, was_playing_before_recording=True)
    state = actions.action_cancel_recording(start, recorder, ui)
    assert state.state == expected
    assert state.previous_state is None and state.was_playing_before_recording is False
    assert recorder.calls == [("cancel", True)] and ui.names() == ["on_record_canceled"]


def test_cancelling_and_clearing_unloads_the_chip_and_stops_the_music(recorder, audio, ui):
    state = actions.action_cancel_recording_and_clear(device(State.RECORDING, was_playing_before_recording=True), recorder, audio, ui)
    assert state.state == State.IDLE_NO_CHIP and state.loaded_chip is None
    assert state.was_playing_before_recording is False
    assert recorder.calls == [("cancel", False)]  # the music must not come back
    assert audio.names() == ["stop"] and ui.names() == ["on_clear_chip"]
