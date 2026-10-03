"""What the controller's ChipStore does when a chip is tapped, against a real server on this computer."""

import io
import urllib.error
import urllib.request

import pytest

from hardware import chip_store as chip_store_module
from hardware.chip_store import ChipStore


@pytest.fixture
def chips(api, monkeypatch):
    """A ChipStore pointed at the test server."""
    monkeypatch.setattr(chip_store_module, "SERVER_BASE_URL", api.base)
    return ChipStore()


@pytest.fixture
def requests_made(monkeypatch):
    """Count the requests the controller sends to the server."""
    seen = []
    real = urllib.request.urlopen

    def counting(request, *args, **kwargs):
        seen.append((request.get_method(), request.full_url))
        return real(request, *args, **kwargs)

    monkeypatch.setattr(chip_store_module.urllib.request, "urlopen", counting)
    return seen


def test_a_known_chip_comes_back_with_its_id_and_its_songs_link(api, chips):
    # The chip's id has to survive the lookup, or the voice command "clear" cannot name the chip.
    chip = api.post("/chips", {"uid": "04A1B2C3", "name": "Bedtime"})[1]
    api.put("/chips/" + chip["id"], {"song_id": "song001"})
    result = chips.lookup("04A1B2C3")
    assert result == {
        "id": chip["id"], "uid": "04A1B2C3", "name": "Bedtime",
        "uri": "spotify:track:4PTG3Z6ehGkBFwjybzWkR8", "song_id": "song001", "song_name": "Surprise",
    }


def test_one_tap_is_one_request(api, chips, requests_made):
    # It used to fetch the whole chip list and then the whole library on every tap.
    chip = api.post("/chips", {"uid": "04A1B2C3"})[1]
    api.put("/chips/" + chip["id"], {"song_id": "song001"})
    del requests_made[:]
    chips.lookup("04A1B2C3")
    assert len(requests_made) == 1
    assert "/chips/lookup?uid=04A1B2C3" in requests_made[0][1]


def test_a_chip_with_no_song_has_an_empty_link(api, chips):
    api.post("/chips", {"uid": "AA11"})
    assert chips.lookup("AA11")["uri"] == ""


def test_a_chip_number_in_the_other_case_is_the_same_chip(api, chips):
    chip = api.post("/chips", {"uid": "e41c9dbb"})[1]
    result = chips.lookup("E41C9DBB")
    assert result["id"] == chip["id"] and "is_new" not in result
    assert len(api.get("/chips")[1]) == 1


def test_a_chip_number_with_odd_characters_is_sent_safely(api, chips):
    api.post("/chips", {"uid": "04:A1 B2&C3=D"})
    result = chips.lookup("04:A1 B2&C3=D")
    assert result["name"] == "Chip 1" and "is_new" not in result


def test_a_new_chip_is_registered_with_its_id(api, chips):
    result = chips.lookup("ZZ99")
    assert result["is_new"] is True and result["uri"] == ""
    assert result["id"] == api.get("/chips")[1][0]["id"]  # the id that voice "clear" will use
    again = chips.lookup("ZZ99")
    assert "is_new" not in again and again["id"] == result["id"]
    assert len(api.get("/chips")[1]) == 1


def test_a_server_that_cannot_be_reached_is_an_error_and_registers_nothing(api, monkeypatch):
    monkeypatch.setattr(chip_store_module, "SERVER_BASE_URL", "http://127.0.0.1:1")  # nothing listens here
    posted = []
    store = ChipStore()
    store._http_post = lambda endpoint, data: posted.append(endpoint)
    assert store.lookup("AA11") is None
    assert posted == []


def test_a_server_without_the_lookup_route_is_an_error_not_a_new_chip(chips, monkeypatch):
    # An older server answers a plain 404. That must not be mistaken for "unknown chip".
    def plain_404(request, *args, **kwargs):
        raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, io.BytesIO(b"Not found"))

    monkeypatch.setattr(chip_store_module.urllib.request, "urlopen", plain_404)
    posted = []
    chips._http_post = lambda endpoint, data: posted.append(endpoint)
    assert chips.lookup("AA11") is None
    assert posted == []
