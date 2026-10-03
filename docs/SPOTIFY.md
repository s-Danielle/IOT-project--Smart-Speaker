# Spotify on the speaker

How it works, what has broken, and what we tried. We keep this up to date for the whole project, so there is something to show even if the cause turns out to be outside our code.

**Where things stand today:** not tested on the Pi yet. Upstream has had two problems (login for streaming since Aug 10, and a Spotify-side error reported on Sep 29). The first Pi test is step 2 in the plan.

We fix what is ours: our code, our config files and our scripts. We don't patch Spotify, Mopidy or librespot.

## How Spotify playback works here

The path a song takes:

1. You tap a chip and press Play. Our controller (`Main/core/controller.py`) asks Mopidy to play the chip's link.
2. It talks to Mopidy over the MPD protocol on port 6600 (`Main/hardware/audio_player.py`): `clear`, `add <link>`, `play`.
3. Mopidy's Spotify plugin (Mopidy-Spotify) looks the link up.
4. A second plugin, gst-plugin-spotify (built on librespot), streams the audio.
5. The audio goes through ALSA to the speaker.

There are **two separate logins**, and they fail in different ways:

| Login | What it's for | How it's set up | When it breaks |
|---|---|---|---|
| Web API | browsing, search, playlists, looking links up | authorize at https://auth.mopidy.com/spotify/ and paste the `client_id` and `client_secret` it gives you into the `[spotify]` section of `/etc/mopidy/mopidy.conf` | expires about every 6 months and has to be redone (per the Mopidy-Spotify README) |
| Streaming | actually playing the audio | done by the librespot-based plugin | since Aug 2026 Spotify rejects the token Mopidy used here (see the log below) |

Also needed: a **Spotify Premium** account, internet, and a gst-plugin-spotify build that matches the Pi's CPU (check with `gst-inspect-1.0 spotifyaudiosrc`).

Our side of it:
- The app turns `open.spotify.com` links into `spotify:` links (`flutter_app/lib/services/spotify_utils.dart`).
- The controller waits up to `MAX_WAIT_FOR_PLAYBACK` (60 seconds, `Main/config/settings.py`) for Mopidy to confirm that playback started.
- Today a failed `add` is ignored, so a Spotify failure looks like 60 seconds of silent "PLAYING". The plan has a fix: say so quickly when a song can't start.

Where things live:
- Live settings, with secrets (never in git): `/etc/mopidy/mopidy.conf`
- Example settings without secrets: `services/audio/mopidy.conf`
- Streaming credentials folder, as reported in mopidy-spotify #437 for a service install: `/var/lib/mopidy/spotify/credentials-cache/` (the first report from the Pi shows where Mopidy really looks)
- Mopidy's log: `journalctl -u mopidy`
- The test: `scripts/pi/spotify_check.py`

## Error message, what it means, what to do

| What we see | What it probably means | What to do |
|---|---|---|
| `login5` … `INVALID_CREDENTIALS`, or "Unable to load audio item"; browsing works but nothing plays | Spotify no longer accepts Mopidy's login for streaming (since Aug 10, mopidy-spotify #437) | Try the reported workaround below. If it still fails, the cause is upstream: log it. |
| `login5` … `503 Service Unavailable` | A Spotify-side problem reported on Sep 29 (librespot #1771) | Nothing to do locally. Re-test later and log the date. |
| Web API 401, or "re-authorize"; lookups fail but nothing else does | The Web API login expired or was revoked | Re-authorize at https://auth.mopidy.com/spotify/ and update `client_id` and `client_secret`. |
| Web API 403, or everything stopped on a certain date | The Premium of the account that owns the Spotify app lapsed, or Spotify's Feb 2026 limits | Check Premium on the account that owns the app, and the Spotify developer dashboard if you made your own app. |
| A playlist adds or plays nothing, but tracks work | You don't own or collaborate on that playlist (Spotify's Feb 2026 rule) | Use track or album links, or playlists your account owns. |
| `no element "spotifyaudiosrc"` or `Illegal instruction` | The Spotify plugin is missing, or built for the wrong CPU | Install the matching build and check with `gst-inspect-1.0 spotifyaudiosrc`. |
| Stops mid-track and plays somewhere else | Another device started playing on the same account | Use a dedicated account and keep other devices idle. |
| `429` | Spotify's rate limit | Wait, and avoid repeated lookups. |

## The reported workaround for the streaming login

This comes from mopidy-spotify #437. **We have not tried it yet.** Other reports disagree about whether it helps.

1. On a computer that has Rust, build librespot's `get_creds` example and run it, then log in with the Premium account in the browser window it opens. It writes a `credentials.json`. (#437 gives: `cargo install --git https://github.com/librespot-org/librespot --no-default-features --features rustls-tls-native-roots --example get_creds`, then `get_creds <folder>`.) Installing Rust is a heavy step, so we decide together before doing it.
2. Put the file where Mopidy looks (see "Where things live"), owned by `mopidy`, readable only by it (mode 600), then restart Mopidy.
3. Run `scripts/pi/spotify_check.py` and log the result below.

Never paste `credentials.json` anywhere. The Mopidy-Spotify README also says a manual `credentials.json` has to be removed before re-doing the Web API login.

## How to check Spotify

- `sudo python3 /tmp/pi/spotify_check.py --label "what this run is" > /tmp/spotify.txt` tries several links and prints a log entry you can paste below. It makes sound, so turn the volume down first.
- `journalctl -u mopidy --since "1 hour ago" --no-pager | grep -iE "login5|spotify|error"`
- `gst-inspect-1.0 spotifyaudiosrc | grep -i version`
- `systemctl status mopidy`

## Upstream status (last checked 2026-10-02)

- **Feb 2026:** Spotify changed its developer rules. The owner of a developer app needs an active Premium account. Playlist tracks are only returned for playlists you own or collaborate on. Some endpoints were removed. [Migration guide](https://developer.spotify.com/documentation/web-api/tutorials/february-2026-migration-guide).
- **Aug 10, 2026:** Mopidy-Spotify 5.0.0a3 with gst-plugin-spotify 0.15.0-alpha.1 (librespot 0.8.0) stopped playing on installs that had worked. [mopidy-spotify #437](https://github.com/mopidy/mopidy-spotify/issues/437). The maintainer acknowledged it on Aug 18.
- **Aug 13, 2026:** the Phoniebox project reports the same break and says logging in again doesn't help. [RPi-Jukebox-RFID #2703](https://github.com/MiczFlor/RPi-Jukebox-RFID/issues/2703). It also says Mopidy-Spotify 5.0.0a5 and newer need Python 3.13 (Raspberry Pi OS Bookworm has 3.11). We have not verified that.
- **Sep 29, 2026, 13:47 UTC:** librespot users report `login5` returning 503 Service Unavailable, with no fix yet. [librespot #1771](https://github.com/librespot-org/librespot/issues/1771).
- Mopidy-Spotify's own page: [README](https://github.com/mopidy/mopidy-spotify).

## Log

Newest entry first. Each entry says what we saw, what we tried and what happened. `spotify_check.py` prints a ready-made entry to paste here.

### 2026-10-03: before any test on the Pi

- **What we know:** everything above, from the upstream issues. Nothing has been tested on the Pi yet.
- **Known about our setup:** `services/audio/mopidy.conf` still had `username` and `password` fields from the libspotify days. They stopped working in Mopidy-Spotify 5, and we replaced them with `client_id` and `client_secret`. The folder `spotify-auth/` in the repo folder on the development computer (ignored by git) holds a `credentials.json` dated Aug 13. Its contents were not read. We don't know whether it was ever copied to the Pi, or whether it worked.
- **Next:** the first test on the Pi (step 2 of the plan): `pi_report.sh` for the versions, then `spotify_check.py`.
