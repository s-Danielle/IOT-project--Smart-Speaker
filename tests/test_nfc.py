"""The NFC reader: a missing reader must not stop the speaker from starting."""

import threading
import time

import pytest

import fakes
import hardware.nfc_scanner as nfc_scanner
from hardware.nfc_scanner import NFCScanner
from hardware.nfc_service import NFCService


@pytest.fixture(autouse=True)
def quick_timing(monkeypatch):
    monkeypatch.setattr(nfc_scanner, "NFC_TIMEOUT", 0.02)
    monkeypatch.setattr(nfc_scanner, "NFC_INIT_RETRY_DELAY", 0.2)


def build_in_background(seconds=2.0):
    """Build a scanner on a thread. Returns (scanner or None, whether it finished in time)."""
    holder = {}
    worker = threading.Thread(target=lambda: holder.update(scanner=NFCScanner()), daemon=True)
    worker.start()
    worker.join(seconds)
    return holder.get("scanner"), not worker.is_alive()


def test_the_speaker_starts_even_without_a_reader():
    # A loose NFC wire used to trap the controller in an endless retry loop inside its constructor,
    # so the buttons never worked and nothing started.
    fakes.FakePN532.init_fails = True
    scanner, finished = build_in_background()
    assert finished, "NFCScanner() kept retrying instead of returning"
    assert scanner.read_uid() is None


def test_with_no_reader_the_nfc_thread_does_not_spin():
    fakes.FakePN532.init_fails = True
    scanner = NFCScanner()
    started = time.monotonic()
    scanner.read_uid()
    assert time.monotonic() - started >= 0.015  # paused like a normal read


def test_a_reader_plugged_in_later_is_picked_up(monkeypatch):
    fakes.FakePN532.init_fails = True
    scanner = NFCScanner()
    assert scanner._pn532 is None
    fakes.FakePN532.init_fails = False
    fakes.FakePN532.next_uid = bytes([0x99, 0x03, 0xEE, 0xB9])
    time.sleep(0.25)  # longer than the retry delay
    scanner.read_uid()  # reconnects
    assert scanner._pn532 is not None
    assert scanner.read_uid() == "9903EEB9"


def test_a_missing_reader_is_not_hammered():
    fakes.FakePN532.init_fails = True
    scanner = NFCScanner()
    for _ in range(5):
        scanner.read_uid()
    assert fakes.FakePN532.attempts == 1  # not once per read


def test_the_missing_reader_is_logged_rarely(monkeypatch):
    errors = []
    monkeypatch.setattr(nfc_scanner, "log_error", errors.append)
    monkeypatch.setattr(nfc_scanner, "NFC_INIT_RETRY_DELAY", 0.0)
    fakes.FakePN532.init_fails = True
    scanner = NFCScanner()
    for _ in range(20):
        scanner.read_uid()
    assert len([e for e in errors if "not available" in e]) == 1


def test_a_working_reader_reads_uids_as_before():
    fakes.FakePN532.next_uid = bytes([0x04, 0xA1, 0xB2, 0xC3])
    scanner = NFCScanner()
    assert scanner._pn532 is not None
    assert scanner.read_uid() == "04A1B2C3"
    fakes.FakePN532.next_uid = None
    assert scanner.read_uid() is None


def test_missing_nfc_libraries_do_not_stop_the_speaker(monkeypatch):
    monkeypatch.setattr(nfc_scanner, "HAS_HARDWARE", False)
    scanner = NFCScanner()
    assert scanner.read_uid() is None


def test_the_service_runs_and_stops_cleanly_without_a_reader():
    fakes.FakePN532.init_fails = True
    service = NFCService()
    service.start()
    time.sleep(0.1)
    assert service.get_current_uid() is None
    started = time.monotonic()
    service.close()
    assert time.monotonic() - started < 2
