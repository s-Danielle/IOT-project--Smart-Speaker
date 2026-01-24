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

def test_vosk_availability():
    """Test if Vosk is installed and model is available."""
    print("\n=== Testing Vosk Availability ===")
    
    try:
        import vosk
        print(f"✓ Vosk installed (version: {vosk.__version__ if hasattr(vosk, '__version__') else 'unknown'})")
    except ImportError:
        print("✗ Vosk not installed")
        print("  Install with: pip install vosk")
        return False
    
    model_path = os.path.join(main_dir, 'models', 'vosk-model-small-en-us')
    if os.path.exists(model_path):
        print(f"✓ Model found at: {model_path}")
    else:
        print(f"✗ Model not found at: {model_path}")
        print("  Download with: ./scripts/download-vosk-model.sh")
        return False
    
    return True


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
            print(f"✗ Recording failed: {result.stderr.decode()}")
            return False
        
        size = os.path.getsize(temp_path)
        print(f"✓ Recording successful ({size} bytes)")
        
        if size < 1000:
            print("⚠ Recording seems very small - check microphone")
            return False
        
        return True
        
    except FileNotFoundError:
        print("✗ arecord not found - install alsa-utils")
        return False
    except subprocess.TimeoutExpired:
        print("✗ Recording timed out")
        return False
    finally:
        try:
            os.unlink(temp_path)
        except:
            pass


def test_voice_command():
    """Test the voice command processor."""
    print("\n=== Testing Voice Command Processor ===")
    
    try:
        from hardware.voice_command import VoiceCommand
        
        vc = VoiceCommand()
        print("✓ VoiceCommand initialized")
        
        if vc.is_available():
            print("✓ Voice commands are available")
        else:
            print("✗ Voice commands not available (check Vosk/model)")
            return False
        
        return True
        
    except Exception as e:
        print(f"✗ Failed to initialize VoiceCommand: {e}")
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
        ("hi speaker play music", "play"),  # Extra words after command
        ("play", None),  # Missing wake phrase
        ("hello speaker play", None),  # Wrong wake phrase
        ("hi speaker volume up", None),  # Unsupported command
        ("", None),
    ]
    
    all_passed = True
    for text, expected in test_cases:
        result = vc._parse_command(text)
        status = "✓" if result == expected else "✗"
        if result != expected:
            all_passed = False
        print(f"  {status} '{text}' -> {result} (expected: {expected})")
    
    return all_passed


def test_live_recognition():
    """Test live voice recognition."""
    print("\n=== Testing Live Voice Recognition ===")
    print("Say 'hi speaker play' (or another command) when prompted...")
    print("Press Ctrl+C to skip this test.\n")
    
    try:
        from hardware.voice_command import VoiceCommand
        
        vc = VoiceCommand()
        
        input("Press Enter when ready to speak...")
        print("Listening for 3 seconds...")
        
        command = vc.listen_and_parse(duration=3.0)
        
        if command:
            print(f"✓ Recognized command: {command}")
            return True
        else:
            print("✗ No command recognized")
            print("  Make sure you said 'hi speaker' followed by a command")
            return False
            
    except KeyboardInterrupt:
        print("\nSkipped live recognition test")
        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def main():
    print("=" * 50)
    print("PTT Voice Command Test Suite")
    print("=" * 50)
    
    results = {}
    
    # Run tests
    results['vosk'] = test_vosk_availability()
    results['microphone'] = test_microphone()
    results['voice_command'] = test_voice_command()
    results['parse_command'] = test_parse_command()
    
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
