# Spotify on the speaker

How it works, what has broken, and what we tried. We keep this up to date for the whole project, so there is something to show even if the cause turns out to be outside our code.

**Where things stand today:** on Oct 3 a Spotify song played fine on the Pi, on the old code, the first time we tried it. So streaming works today even though upstream has had two problems (login for streaming since Aug 10, and a Spotify-side error reported on Sep 29). The old logs show what went wrong the last time the speaker was used (Sep 5): every Spotify song failed at the very first step, and our code didn't notice for a minute. What made that first step fail is not proven (see the log below). The full test (`spotify_check.py`) has not been run yet: it is step 2 in the plan, and it will measure how long a song takes to start and which kinds of link work.

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
- Today a failed `add` is ignored, so a Spotify failure looks like 60 seconds of silent "PLAYING". The Sep 5 logs show exactly this (see the log below). The plan has a fix: say so quickly when a song can't start.

Where things live:
- Live settings, with secrets (never in git): `/etc/mopidy/mopidy.conf`
- Example settings without secrets: `services/audio/mopidy.conf`
- Streaming credentials folder, as reported in mopidy-spotify #437 for a service install: `/var/lib/mopidy/spotify/credentials-cache/` (the first report from the Pi shows where Mopidy really looks)
- Mopidy's log: `journalctl -u mopidy -b`. On this Pi it holds almost nothing, and it is lost at every reboot (the system log is kept in memory). See the 2026-10-03 entry below.
- Our controller's log: `/var/log/smart_speaker.log` on the old code, `/var/log/smart_speaker/controller.log` on newer code. This is where the useful lines are: `Playing URI`, `MPD command error`, and `Playback timeout` or `Playback confirmed`.
- The test: `scripts/pi/spotify_check.py`

## Error message, what it means, what to do

| What we see | What it probably means | What to do |
|---|---|---|
| Controller log: `MPD command error: [50@0] {add} directory or file not found`, right after `Playing URI: spotify:…` | Mopidy found nothing for that link. If the answer comes in a few hundredths of a second (as on Sep 5), Mopidy didn't ask Spotify at all: the Pi has no internet (check whether it is in its own setup hotspot), or Mopidy's Spotify part isn't logged in or isn't running. A normal lookup takes about 2 seconds today. A link that doesn't exist may give the same message. | Check that the Pi has internet and is not in hotspot mode. Restart Mopidy (`sudo systemctl restart mopidy`) and tap again. `spotify_check.py` also tries a made-up link, so we can compare. |
| Controller log: `Playback timeout after … - Mopidy never started playing`, with **no** `add` error before it | The link was found, but streaming never started: the streaming login problem (this is what Aug 13 looked like) | See the next row and the workaround section. |
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

**What the old logs say about it:** on Aug 13 the controller log shows four tries where the link was found but playback never started (how the streaming login problem looks from our side), and good plays from 14:22 that afternoon. The Spotify packages date from Jul 23 and 24 and Mopidy's settings file from Jul 23, so none of them changed that day. The `credentials.json` we made on the development computer is dated Aug 13. So this workaround probably worked on this Pi. That is not proven: `pi_report.sh` prints the date of the credentials file on the Pi (never its contents), which will settle it.

Never paste `credentials.json` anywhere. The Mopidy-Spotify README also says a manual `credentials.json` has to be removed before re-doing the Web API login.

## How to check Spotify

- `sudo python3 /tmp/pi/spotify_check.py --label "what this run is" > /tmp/spotify.txt` tries several links and prints a log entry you can paste below. It makes sound, so turn the volume down first.
- `grep -E "Playing URI|MPD command error|Playback (timeout|confirmed)" /var/log/smart_speaker.log | tail -20` is the controller's own record of every try. On newer code the file is `/var/log/smart_speaker/controller.log`.
- `journalctl -u mopidy -b --no-pager | grep -iE "login5|spotify|error"` (use `-b`, not `--since`: the Pi's clock is wrong for the first minute after boot)
- `gst-inspect-1.0 spotifyaudiosrc | grep -i version`
- `systemctl status mopidy`

## Upstream status (last checked 2026-10-02)

- **Feb 2026:** Spotify changed its developer rules. The owner of a developer app needs an active Premium account. Playlist tracks are only returned for playlists you own or collaborate on. Some endpoints were removed. [Migration guide](https://developer.spotify.com/documentation/web-api/tutorials/february-2026-migration-guide).
- **Aug 10, 2026:** Mopidy-Spotify 5.0.0a3 with gst-plugin-spotify 0.15.0-alpha.1 (librespot 0.8.0) stopped playing on installs that had worked. [mopidy-spotify #437](https://github.com/mopidy/mopidy-spotify/issues/437). The maintainer acknowledged it on Aug 18.
- **Aug 13, 2026:** the Phoniebox project reports the same break and says logging in again doesn't help. [RPi-Jukebox-RFID #2703](https://github.com/MiczFlor/RPi-Jukebox-RFID/issues/2703). It also says Mopidy-Spotify 5.0.0a5 and newer need Python 3.13. We have not verified that. This Pi runs Debian 13 (trixie), a newer system than Bookworm, so it probably has Python 3.13 already; the first report shows the exact version.
- **Sep 29, 2026, 13:47 UTC:** librespot users report `login5` returning 503 Service Unavailable, with no fix yet. [librespot #1771](https://github.com/librespot-org/librespot/issues/1771).
- Mopidy-Spotify's own page: [README](https://github.com/mopidy/mopidy-spotify).

## Log

Newest entry first. Each entry says what we saw, what we tried and what happened. `spotify_check.py` prints a ready-made entry to paste here.

### 2026-10-03: what the old logs say about Sep 5 (and Aug 13)

A short read-only look at the Pi's old logs, over SSH with no sudo. Nothing was changed. The evidence is in the controller's log (`/var/log/smart_speaker.log`). Mopidy's own log from those days doesn't exist: the Pi keeps the system log in memory, so only today's boot is there, and even that holds just the start lines.

**What the logs show about Sep 5** (a session from about 20:31 to 20:47):
- All 4 Spotify taps (on 3 chips) failed at the very first step, within 14 to 63 milliseconds. Mopidy answered the request to add the song with "directory or file not found":
  ```
  [2026-09-05 20:33:19.097] Playing URI: spotify:track:578b...
  [2026-09-05 20:33:19.160] [ERROR] MPD command error: [50@0] {add} directory or file not found
  ```
- Beeps from local files worked at the same time, so the sound card and our audio path were fine.
- Our controller ignored the error, showed PLAYING, and gave up about a minute later: `[2026-09-05 20:44:34.551] Playback timeout after 61.8s - Mopidy never started playing`. The daily-usage counter counted this silent time as listening (about 7 seconds that day).
- The speaker's services restarted together at about 20:34 and again at about 20:44 (three controller starts in ten minutes). Each time the Pi failed to join the home WiFi within 30 seconds and opened its own setup hotspot (`[WiFi] No connection, starting AP mode...`). The LED and button chips also logged `Connection timed out` errors from 20:43:54 to about 20:47.

**What we suspect, but the logs don't show:**
- At 20:43 the Pi had been in its hotspot since about 20:35, so it had no internet. That is enough to explain those taps.
- For the 20:33 taps we don't know. The internet clock had been corrected about 50 seconds earlier, so the internet worked then. What stands out is the speed: today the same step took 2.05 seconds (a real request to Spotify). Failing in 14 to 63 milliseconds means Mopidy probably didn't ask Spotify at all, for example because its Spotify part wasn't logged in or wasn't running at that moment.
- Unlikely: an expired Web API login (it was set up in late July and lasts about 6 months), the Aug 10 streaming bug (it fails after the add step, as on Aug 13), and the Sep 29 bug (it hadn't happened yet).
- Possible hardware cause: a power dip would explain the WiFi and the chip errors together, and a loose wire would explain the chip errors. The health log of Jul 24 also had chip errors (`Input/output error`), so two different days show them. Step 4 checks this.

**Aug 13 was a different fault.** Four tries ended with "never started playing" even though the add worked (which matches how the Aug 10 streaming-login problem looks from our side), then plays were good from 14:22 that afternoon. The Spotify packages date from Jul 23 and 24, Mopidy's settings file from Jul 23, and the code was unchanged, so none of that changed that day. The `credentials.json` we made on the development computer is dated Aug 13, so the reported workaround probably is what fixed it. Not proven: `pi_report.sh` prints the date of the credentials file on the Pi (never its contents), which will settle it.

**Today (Oct 3):** no add error, and `Playback confirmed by Mopidy` about 5.5 seconds after Play was pressed (the add itself took 2.05 seconds). Mopidy's log shows only its start lines, with nothing about the Spotify login. Nothing changed on the Pi between Sep 5 and today (the last package change was an apt run on Aug 13 that installed build tools), so today's success isn't down to an upgrade. This boot's clock was also corrected about 75 seconds after boot, after Mopidy had started, the same as on Sep 5.

**What this means for our code** (all ours to fix, all in step 5 of the plan):
1. Say so quickly when a song can't start. On Sep 5 the error was in the log within the first second, but the speaker sat silent for a minute.
2. Don't count silent time as listening, so a failed tap doesn't use up the daily limit.
3. Keep the logs: keep the system log across reboots and make Mopidy log its Spotify problems, so next time the cause is read from a log instead of guessed.
4. WiFi: don't give up on the home network after 30 seconds and stay in hotspot mode. Keep retrying saved networks, as already planned.

**What we could not check:** Mopidy's and the kernel's logs from Sep 5 (gone); whether the restarts at 20:34 and 20:44 were reboots, restarts by hand or crashes; where the other 4 seconds of the 11 seconds in the usage record went; Mopidy's settings and the credentials folder (only root can read them, and we never read secrets).

**Next:** step 2: `pi_report.sh` (versions, credentials file date, this boot's log), then `spotify_check.py` for the baseline.

### 2026-10-03: first play after power-on: it worked

- **What happened:** the Pi was turned on and a Spotify song played on the speaker. This was on the old code (commit `45a4eae`), with nothing changed on the Pi since it was last used.
- **What it tells us:** Mopidy can log in for streaming today. The Pi has Mopidy-Spotify 5.0.0 and the same gst-plugin-spotify build (`3aab047`) that the mopidy-spotify #437 report names, so that upstream break is not stopping us today.
- **What we don't know yet:** whether it was a track, an album or a playlist, whether it was started from a chip or from the app, how long it took to start, and whether it keeps playing for a long time. `spotify_check.py` will measure these.
- **Next:** the entry above (what the old logs say about Sep 5), then `spotify_check.py` as the baseline.

### 2026-10-03: a read-only look at the Pi (nothing was changed)

Done over SSH with no sudo. It only read things.

- **The Pi:** Raspberry Pi Zero 2 W with Debian 13 (trixie), kernel 6.18, 64-bit. Booted about 10:56 on Oct 3 and is on WiFi.
- **The Spotify stack on it:**
  - Mopidy 4.0.1, mopidy-mpd 4.0.0 and Mopidy-Spotify 5.0.0, all installed with pip. An older Mopidy 3.4.2 from apt is installed too.
  - gst-plugin-spotify `0.15.0-alpha.1+spotify-logging.3aab047` from apt. The mopidy-spotify #437 report names the same plugin build (`3aab047`, librespot 0.8.0).
- **What we could not see:**
  - `/etc/mopidy/mopidy.conf` (792 bytes, last changed Jul 23) can only be read by `mopidy` and root, so its settings weren't seen.
  - The folders under `/var/lib/mopidy` where a `credentials.json` would live can't be opened without sudo, so we don't know if one is there. The Pi's checkout has no `spotify-auth/` folder.
  - Mopidy's log showed nothing for "the last 14 days". That doesn't mean it logged nothing. When the services started this boot, the Pi's clock said Sep 5, and the internet clock corrected it to Oct 3 a little later. So this boot's lines carry the wrong date. `pi_report.sh` now also scans "this boot".
- **Right now:** Mopidy is idle with an empty queue. Its web port (6680, this machine only) is on.
- **The speaker's data:** 3 chips and 4 songs, all `spotify:track:` links. The last recorded playback was 11 seconds on Sep 5.
- **Sound:** card 0 is `seeed2micvoicec` with a `PCM` volume control (at 85%). There is no `/etc/asound.conf`.
- **Still unknown:** whether Spotify plays at all today.
- **Next:** `pi_report.sh` with sudo and `spotify_check.py` (step 2 of the plan).

### 2026-10-03: before any test on the Pi

- **What we know:** everything above, from the upstream issues. Nothing has been tested on the Pi yet.
- **Known about our setup:** `services/audio/mopidy.conf` still had `username` and `password` fields from the libspotify days. They stopped working in Mopidy-Spotify 5, and we replaced them with `client_id` and `client_secret`. The folder `spotify-auth/` in the repo folder on the development computer (ignored by git) holds a `credentials.json` dated Aug 13. Its contents were not read. We don't know whether it was ever copied to the Pi, or whether it worked.
- **Next:** the first test on the Pi (step 2 of the plan): `pi_report.sh` for the versions, then `spotify_check.py`.
