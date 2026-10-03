"""The web routes for chips, songs, settings and usage, run against a real server on this computer.

The server listens on 127.0.0.1 on a free port for the length of each test, and keeps its data in
a temporary folder. Nothing on the speaker's own folders or network is touched.
"""

import json
import os

from storage import JsonStore


# ---------------------------------------------------------------------------
# Chips
# ---------------------------------------------------------------------------


def test_a_new_speaker_lists_no_chips_and_the_starting_songs(api):
    assert api.get("/chips") == (200, [])
    status, songs = api.get("/library")
    assert status == 200 and [s["id"] for s in songs] == ["song001", "song002"]


def test_the_player_registers_a_chip_it_has_not_seen(api):
    status, chip = api.post("/chips", {"uid": "04A1B2C3"})
    assert status == 201
    assert chip["uid"] == "04A1B2C3" and chip["name"] == "Chip 1" and chip["song_id"] is None
    assert api.get("/chips")[1] == [chip]


def test_registering_a_known_chip_again_gives_the_same_chip(api):
    first = api.post("/chips", {"uid": "04A1B2C3", "name": "Mine"})[1]
    again = api.post("/chips", {"uid": "04a1b2c3"})[1]
    assert again["id"] == first["id"] and len(api.get("/chips")[1]) == 1


def test_a_chip_without_a_number_is_a_bad_request(api):
    status, body = api.post("/chips", {"name": "x"})
    assert status == 400 and "uid" in body["error"]


def test_lookup_by_number_gives_the_chip_and_its_songs_link(api):
    chip = api.post("/chips", {"uid": "04A1B2C3", "name": "Bedtime"})[1]
    api.put("/chips/" + chip["id"], {"song_id": "song001"})
    status, found = api.get("/chips/lookup?uid=04A1B2C3")
    assert status == 200
    assert found["id"] == chip["id"] and found["name"] == "Bedtime" and found["song_name"] == "Surprise"
    assert found["uri"] == "spotify:track:4PTG3Z6ehGkBFwjybzWkR8"


def test_lookup_of_a_chip_with_no_song(api):
    api.post("/chips", {"uid": "AA11"})
    assert api.get("/chips/lookup?uid=AA11")[1]["uri"] == ""


def test_lookup_ignores_case_and_url_escapes(api):
    api.post("/chips", {"uid": "04:A1 B2&C3"})
    assert api.get("/chips/lookup?uid=04%3Aa1+b2%26c3")[0] == 200


def test_lookup_of_an_unknown_chip_is_a_404_and_registers_nothing(api):
    status, body = api.get("/chips/lookup?uid=ZZ99")
    assert status == 404 and body == {"error": "unknown chip"}
    assert api.get("/chips") == (200, [])


def test_lookup_needs_a_number(api):
    assert api.get("/chips/lookup")[0] == 400
    assert api.get("/chips/lookup?uid=")[0] == 400


def test_giving_a_chip_a_song_and_a_name(api):
    chip = api.post("/chips", {"uid": "AA11"})[1]
    status, updated = api.put("/chips/" + chip["id"], {"name": "Bedtime", "song_id": "song001"})
    assert status == 200
    assert updated["name"] == "Bedtime" and updated["song_id"] == "song001" and updated["song_name"] == "Surprise"
    assert api.get("/chips")[1][0] == updated


def test_a_song_that_is_not_in_the_library_is_a_bad_request(api):
    chip = api.post("/chips", {"uid": "AA11"})[1]
    status, body = api.put("/chips/" + chip["id"], {"song_id": "song-nope"})
    assert status == 400 and "song-nope" in body["error"]
    assert api.get("/chips")[1][0]["song_id"] is None


def test_changing_a_chip_that_is_not_there(api):
    assert api.put("/chips/chip-nope", {"name": "x"})[0] == 404


def test_a_body_that_is_not_json_is_a_bad_request_not_a_crash(api):
    chip = api.post("/chips", {"uid": "AA11"})[1]
    assert api.put("/chips/" + chip["id"], raw=b"{not json")[0] == 400
    assert api.get("/chips")[0] == 200  # the server is still fine


def test_clearing_a_chips_song(api):
    chip = api.post("/chips", {"uid": "AA11"})[1]
    api.put("/chips/" + chip["id"], {"song_id": "song001"})
    assert api.delete("/chips/%s/assignment" % chip["id"])[0] == 204
    assert api.get("/chips")[1][0]["song_id"] is None
    assert api.delete("/chips/chip-nope/assignment")[0] == 404


def test_deleting_a_chip(api):
    chip = api.post("/chips", {"uid": "AA11"})[1]
    assert api.delete("/chips/" + chip["id"])[0] == 204
    assert api.get("/chips")[1] == []
    assert api.delete("/chips/" + chip["id"])[0] == 404


# ---------------------------------------------------------------------------
# Songs
# ---------------------------------------------------------------------------


def test_adding_renaming_and_deleting_a_song(api):
    status, song = api.post("/library", {"name": "Lullaby", "uri": "spotify:track:1"})
    assert status == 201 and song["name"] == "Lullaby"
    assert song in api.get("/library")[1]
    status, renamed = api.put("/library/" + song["id"], {"name": "Lullaby 2"})
    assert status == 200 and renamed == {"id": song["id"], "name": "Lullaby 2", "uri": "spotify:track:1"}
    assert api.delete("/library/" + song["id"])[0] == 204
    assert song["id"] not in [s["id"] for s in api.get("/library")[1]]
    assert api.delete("/library/" + song["id"])[0] == 404
    assert api.put("/library/" + song["id"], {"name": "x"})[0] == 404


def test_a_song_body_that_is_not_an_object_is_a_bad_request(api):
    assert api.post("/library", ["not", "an", "object"])[0] == 400
    assert api.post("/library", {"name": 5, "uri": "x"})[0] == 400


def test_renaming_a_song_changes_the_name_the_chip_shows(api):
    song = api.post("/library", {"name": "Old", "uri": "spotify:track:1"})[1]
    chip = api.post("/chips", {"uid": "AA11"})[1]
    api.put("/chips/" + chip["id"], {"song_id": song["id"]})
    api.put("/library/" + song["id"], {"name": "New"})
    assert api.get("/chips")[1][0]["song_name"] == "New"


def test_deleting_a_song_leaves_its_chips_without_one(api):
    song = api.post("/library", {"name": "Gone", "uri": "spotify:track:1"})[1]
    chip = api.post("/chips", {"uid": "AA11"})[1]
    api.put("/chips/" + chip["id"], {"song_id": song["id"]})
    api.delete("/library/" + song["id"])
    assert api.get("/chips")[1][0]["song_id"] is None


def test_an_uploaded_file_is_saved_and_listed_once(api):
    boundary = "xBOUNDARYx"
    body = (
        ("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"My Song.mp3\"\r\n"
         "Content-Type: audio/mpeg\r\n\r\n" % boundary).encode()
        + b"ID3-fake-audio"
        + ("\r\n--%s--\r\n" % boundary).encode()
    )
    status, result = api.post("/files", raw=body, headers={"Content-Type": "multipart/form-data; boundary=" + boundary})
    assert status == 201 and result["name"] == "[UPLOAD] My Song"
    path = result["uri"][len("file://"):]
    assert os.path.dirname(path) == str(api.tmp / "uploads")
    with open(path, "rb") as f:
        assert f.read() == b"ID3-fake-audio"
    uploads = [s for s in api.get("/library")[1] if s["uri"] == result["uri"]]
    assert len(uploads) == 1 and uploads[0]["name"] == "[UPLOAD] My Song"


# ---------------------------------------------------------------------------
# Parental controls and usage
# ---------------------------------------------------------------------------


def test_the_parental_controls_can_be_read_and_changed(api):
    status, pc = api.get("/settings/parental")
    assert status == 200 and pc["enabled"] is False and pc["volume_limit"] == 100
    status, pc = api.put("/settings/parental", {"enabled": True, "volume_limit": 40, "quiet_hours": {"enabled": True, "start": "20:00"}})
    assert status == 200
    assert pc["enabled"] is True and pc["volume_limit"] == 40
    assert pc["quiet_hours"] == {"enabled": True, "start": "20:00", "end": "07:00"}
    assert api.get("/settings/parental")[1] == pc


def test_a_bad_setting_is_a_bad_request_and_changes_nothing(api):
    api.put("/settings/parental", {"volume_limit": 40})
    status, body = api.put("/settings/parental", {"volume_limit": "loud"})
    assert status == 400 and "volume_limit" in body["error"]
    assert api.get("/settings/parental")[1]["volume_limit"] == 40


def test_the_daily_usage_adds_up(api):
    assert api.get("/usage/today") == (200, {"date": "2026-10-03", "seconds": 0})
    assert api.post("/usage/add", {"seconds": 60})[1]["seconds"] == 60
    assert api.post("/usage/add", {"seconds": 15})[1]["seconds"] == 75
    assert api.get("/usage/today")[1]["seconds"] == 75


def test_a_bad_usage_amount_is_a_bad_request(api):
    assert api.post("/usage/add", {"seconds": "lots"})[0] == 400
    assert api.get("/usage/today")[1]["seconds"] == 0


# ---------------------------------------------------------------------------
# Starting the server
# ---------------------------------------------------------------------------

OLD_TAGS = {"E41C9DBB": {"name": "MyFirstChip", "uri": "spotify:track:1"}}


def restart(api):
    """What a service restart does: a new store on the same file, then start_storage()."""
    new_store = JsonStore(api.store.path, today=lambda: "2026-10-03")
    api.module.store = new_store
    api.module.start_storage()
    return new_store


def test_the_first_start_imports_the_old_tags_file(api):
    (api.tmp / "tags.json").write_text(json.dumps(OLD_TAGS))
    restart(api)
    assert [c["uid"] for c in api.get("/chips")[1]] == ["E41C9DBB"]


def test_a_chip_deleted_in_the_app_stays_deleted_after_a_restart(api):
    # The old code re-imported tags.json at every start and brought deleted chips back.
    (api.tmp / "tags.json").write_text(json.dumps(OLD_TAGS))
    restart(api)
    chip = api.get("/chips")[1][0]
    assert api.delete("/chips/" + chip["id"])[0] == 204
    restart(api)
    assert api.get("/chips")[1] == []


def test_a_start_without_an_old_tags_file(api):
    restart(api)
    assert api.get("/chips")[1] == []
    assert os.path.exists(api.store.path)


def test_a_damaged_data_file_is_repaired_at_start(api):
    api.post("/chips", {"uid": "AA11"})
    api.post("/chips", {"uid": "BB22"})
    with open(api.store.path, "w") as f:
        f.write("garbage")
    restart(api)
    assert [c["uid"] for c in api.get("/chips")[1]] == ["AA11"]  # the last good copy
