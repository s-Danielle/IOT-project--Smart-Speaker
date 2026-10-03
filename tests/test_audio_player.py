"""AudioPlayer against a fake Mopidy: it must say whether the link was accepted."""

import fakes
from hardware.audio_player import AudioPlayer


def client():
    return fakes.FakeMPDClient.instances[-1]


def test_play_uri_says_true_when_mopidy_accepts_the_link():
    player = AudioPlayer()
    assert player.play_uri("spotify:track:x") is True
    assert client().calls == [("clear",), ("add", "spotify:track:x"), ("play",)]
    assert player.last_error is None


def test_play_uri_says_false_when_mopidy_refuses_the_link():
    # This is what happened on Sep 5: Mopidy answered "directory or file not found" and the
    # old code carried on as if all was well, showing PLAYING over silence for a minute.
    fakes.FakeMPDClient.add_error = "[50@0] {add} directory or file not found"
    player = AudioPlayer()
    assert player.play_uri("spotify:track:x") is False
    assert "directory or file not found" in player.last_error
    assert ("play",) not in client().calls  # no point playing an empty queue


def test_a_refused_link_does_not_throw_the_connection_away():
    fakes.FakeMPDClient.add_error = "[50@0] {add} directory or file not found"
    player = AudioPlayer()
    player.play_uri("spotify:track:x")
    assert client().connects == 1  # no needless reconnect
    fakes.FakeMPDClient.add_error = None
    assert player.play_uri("spotify:track:y") is True
    assert client().connects == 1


def test_play_uri_says_false_when_mopidy_cannot_be_reached():
    fakes.FakeMPDClient.down = True
    player = AudioPlayer()
    assert player.play_uri("spotify:track:x") is False
    assert player.last_error == "Mopidy could not be reached"


def test_a_failed_play_does_not_look_like_playing():
    fakes.FakeMPDClient.add_error = "[50@0] {add} directory or file not found"
    player = AudioPlayer()
    player.play_uri("spotify:track:x")
    assert player.is_playing() is False


def test_resume_says_whether_mopidy_answered():
    player = AudioPlayer()
    assert player.resume() is True
    fakes.FakeMPDClient.down = True
    player2 = AudioPlayer()
    assert player2.resume() is False
