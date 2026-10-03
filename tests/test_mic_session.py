"""The microphone lock: one owner at a time, the music paused while it is held and restored after."""

import threading

import fakes
import pytest
from hardware.mic_session import MicSession


@pytest.fixture
def audio():
    return fakes.FakeAudio()


@pytest.fixture
def mic(audio):
    return MicSession(audio)


def test_the_mic_is_free_at_first(mic):
    assert mic.is_held() is False and mic.owner is None


def test_acquiring_claims_it(mic):
    assert mic.acquire("ptt") is True
    assert mic.is_held() is True and mic.owner == "ptt"


def test_a_second_claim_is_refused_and_the_first_keeps_it(mic):
    mic.acquire("ptt")
    assert mic.acquire("recording") is False
    assert mic.owner == "ptt"


def test_releasing_frees_it_for_the_next(mic):
    mic.acquire("ptt")
    mic.release()
    assert mic.is_held() is False
    assert mic.acquire("recording") is True and mic.owner == "recording"


def test_releasing_a_mic_nobody_holds_does_nothing(mic, audio):
    mic.release()
    mic.release(restore=False)
    assert audio.calls == []


def test_music_that_was_playing_is_paused_and_comes_back(mic, audio):
    audio.playing = True
    mic.acquire("recording")
    assert audio.names() == ["pause"]
    mic.release()
    assert audio.names() == ["pause", "resume"]


def test_music_that_was_not_playing_is_left_alone(mic, audio):
    mic.acquire("recording")
    mic.release()
    assert audio.names() == []  # nothing to pause, and nothing to restore


def test_release_without_restore_leaves_the_music_paused(mic, audio):
    audio.playing = True
    mic.acquire("recording")
    mic.release(restore=False)  # e.g. cancel-and-clear: the chip is gone, the music must not return
    assert audio.names() == ["pause"]


def test_a_refused_claim_does_not_touch_the_music(mic, audio):
    audio.playing = True
    mic.acquire("ptt")
    calls = list(audio.calls)
    mic.acquire("recording")
    assert audio.calls == calls


def test_only_the_session_that_paused_the_music_resumes_it(mic, audio):
    audio.playing = True
    mic.acquire("ptt")
    mic.release()
    audio.playing = False  # the user stopped it meanwhile
    mic.acquire("recording")  # nothing playing now
    mic.release()
    assert audio.names() == ["pause", "resume"]  # the second session did not resume anything


def test_the_sound_effects_are_silenced_so_they_do_not_leak_into_the_recording(audio):
    silenced = []
    mic = MicSession(audio, silence_feedback=lambda: silenced.append(1))
    mic.acquire("recording")
    assert silenced == [1]
    mic.acquire("ptt")  # refused: no second silencing
    assert silenced == [1]


def test_the_music_state_is_read_fresh_not_from_the_cache(audio):
    asked = []
    audio.is_playing = lambda force_refresh=False: asked.append(force_refresh) or False
    MicSession(audio).acquire("ptt")
    assert asked == [True]  # a cached "stop" would leave the music playing into the microphone


def test_two_threads_racing_for_the_mic_get_exactly_one_winner(mic):
    results = []
    barrier = threading.Barrier(8)

    def grab(n):
        barrier.wait()
        results.append(mic.acquire(f"thread-{n}"))

    threads = [threading.Thread(target=grab, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count(True) == 1 and results.count(False) == 7
