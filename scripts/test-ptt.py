#!/usr/bin/env python3
"""
Test script for PTT (Push-to-Talk) voice command feature.
Run this on the Raspberry Pi to test the voice command system.

Usage:
    cd /path/to/IOT-project--Smart-Speaker/Main
    python3 ../scripts/test-ptt.py
"""

import sys
import os

# Add Main directory to path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
main_dir = os.path.join(project_root, 'Main')
sys.path.insert(0, main_dir)
os.chdir(main_dir)


def test_speech_recognition():
    """Test if SpeechRecognition library is installed."""
    print("\n=== Testing Speech Recognition Library ===")
    
    try:
        import speech_recognition as sr
        print(f"[OK] SpeechRecognition installed (version: {sr.__version__})")
        return True
    except ImportError:
        print("[FAIL] SpeechRecognition not installed")
        print("  Install with: pip install SpeechRecognition")
        return False


def test_internet():
    """Test internet connectivity (required for Google Speech API)."""
    print("\n=== Testing Internet Connectivity ===")
    
    import subprocess
    try:
        result = subprocess.run(
            ['ping', '-c', '1', '-W', '3', '8.8.8.8'],
            capture_output=True,
            timeout=5
        )
        if result.returncode == 0:
            print("[OK] Internet connection available")
            return True
        else:
            print("[FAIL] No internet connection")
            print("  Google Speech API requires internet")
            return False
    except Exception as e:
        print(f"[FAIL] Connection test failed: {e}")
        return False


def test_microphone():
    """Test if microphone is working."""
    print("\n=== Testing Microphone ===")
    
    import subprocess
    import tempfile
    
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
        temp_path = f.name
    
    try:
        print("Recording 2 seconds of audio...")
        result = subprocess.run(
            ['arecord', '-f', 'S16_LE', '-r', '16000', '-c', '1', '-d', '2', '-q', temp_path],
            capture_output=True,
            timeout=10
        )
        
        if result.returncode != 0:
            print(f"[FAIL] Recording failed: {result.stderr.decode()}")
            return False
        
        size = os.path.getsize(temp_path)
        print(f"[OK] Recording successful ({size} bytes)")
        
        if size < 1000:
            print("[WARN] Recording seems very small - check microphone")
            return False
        
        return True
        
    except FileNotFoundError:
        print("[FAIL] arecord not found - install alsa-utils")
        return False
    except subprocess.TimeoutExpired:
        print("[FAIL] Recording timed out")
        return False
    finally:
        try:
            os.unlink(temp_path)
        except:
            pass


def test_voice_command_init():
    """Test the voice command processor initialization."""
    print("\n=== Testing Voice Command Processor ===")
    
    try:
        from hardware.voice_command import VoiceCommand
        
        vc = VoiceCommand()
        print("[OK] VoiceCommand initialized")
        
        if vc.is_available():
            print("[OK] Voice commands are available")
        else:
            print("[FAIL] Voice commands not available")
            return False
        
        return True
        
    except Exception as e:
        print(f"[FAIL] Failed to initialize VoiceCommand: {e}")
        return False


def test_parse_command():
    """Test command parsing logic."""
    print("\n=== Testing Command Parsing ===")
    
    from hardware.voice_command import VoiceCommand
    vc = VoiceCommand()
    
    test_cases = [
        ("hi speaker play", "play"),
        ("hi speaker pause", "pause"),
        ("hi speaker stop", "stop"),
        ("hi speaker clear", "clear"),
        ("hi speaker play music", "play"),
        ("play", None),
        ("hello speaker play", None),
        ("hi speaker volume up", None),
        ("", None),
    ]
    
    all_passed = True
    for text, expected in test_cases:
        result = vc._parse_command(text)
        status = "[OK]" if result == expected else "[FAIL]"
        if result != expected:
            all_passed = False
        print(f"  {status} '{text}' -> {result} (expected: {expected})")
    
    return all_passed


def test_live_recognition():
    """Test live voice recognition with Google Speech API."""
    print("\n=== Testing Live Voice Recognition ===")
    print("Say 'hi speaker play' (or another command) when prompted...")
    print("NOTE: Requires internet connection for Google Speech API")
    print("Press Ctrl+C to skip this test.\n")
    
    try:
        from hardware.voice_command import VoiceCommand
        
        vc = VoiceCommand()
        
        input("Press Enter when ready to speak...")
        print("Listening for 3 seconds...")
        
        command = vc.listen_and_parse(duration=3.0)
        
        if command:
            print(f"[OK] Recognized command: {command}")
            return True
        else:
            print("[FAIL] No command recognized")
            print("  Make sure you said 'hi speaker' followed by a command")
            return False
            
    except KeyboardInterrupt:
        print("\nSkipped live recognition test")
        return True
    except Exception as e:
        print(f"[FAIL] Error: {e}")
        return False


def main():
    print("=" * 50)
    print("PTT Voice Command Test Suite")
    print("(Uses Google Speech API - requires internet)")
    print("=" * 50)
    
    results = {}
    
    # Run tests
    results['speech_lib'] = test_speech_recognition()
    results['internet'] = test_internet()
    results['microphone'] = test_microphone()
    results['voice_init'] = test_voice_command_init()
    results['parse'] = test_parse_command()
    
    # Optional live test
    if all(results.values()):
        results['live'] = test_live_recognition()
    
    # Summary
    print("\n" + "=" * 50)
    print("Test Summary")
    print("=" * 50)
    
    for test, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {test}: {status}")
    
    all_passed = all(results.values())
    print("\n" + ("All tests passed!" if all_passed else "Some tests failed."))
    
    return 0 if all_passed else 1


if __name__ == '__main__':
    sys.exit(main())
