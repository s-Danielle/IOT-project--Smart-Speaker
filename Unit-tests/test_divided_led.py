#!/usr/bin/env python3
"""
Divided LED Pin Identification Test

This test helps identify which pin is R, G, and B for a new LED that's split across
two I2C expanders:
  - 2 pins on PCF8574 @ 0x21 (LED expander) - P6 and P7
  - 1 pin on PCF8574 @ 0x20 (Button expander) - P6 or P7

Run this test and observe which color lights up for each pin.
"""

from smbus2 import SMBus
import time
import sys

# I2C Configuration
I2C_BUS = 1
LED_EXPANDER_ADDRESS = 0x21    # LED expander
BUTTON_EXPANDER_ADDRESS = 0x20  # Button expander

# Candidate pins for the new divided LED
LED_EXPANDER_PINS = [6, 7]     # P6, P7 on 0x21
BUTTON_EXPANDER_PINS = [6, 7]  # P6, P7 on 0x20


class DividedLedTester:
    """Test individual pins across both expanders"""
    
    def __init__(self):
        self.bus = SMBus(I2C_BUS)
        
        # Read current states to preserve existing LED states
        try:
            self.led_state = self.bus.read_byte(LED_EXPANDER_ADDRESS)
        except:
            self.led_state = 0x00
            
        try:
            # Button expander needs high bits for input (buttons are active-low)
            # We only want to modify P6/P7, keep P0-P5 high for button inputs
            self.button_state = self.bus.read_byte(BUTTON_EXPANDER_ADDRESS)
        except:
            self.button_state = 0x3F  # P0-P5 high (for buttons), P6-P7 low
    
    def set_pin(self, address: int, pin: int, on: bool):
        """Set a single pin on/off"""
        if address == LED_EXPANDER_ADDRESS:
            if on:
                self.led_state |= (1 << pin)
            else:
                self.led_state &= ~(1 << pin)
            self.bus.write_byte(address, self.led_state)
        else:  # Button expander
            if on:
                self.button_state |= (1 << pin)
            else:
                self.button_state &= ~(1 << pin)
            self.bus.write_byte(address, self.button_state)
    
    def clear_all_test_pins(self):
        """Turn off all test pins (P6, P7 on both expanders)"""
        for pin in LED_EXPANDER_PINS:
            self.set_pin(LED_EXPANDER_ADDRESS, pin, False)
        for pin in BUTTON_EXPANDER_PINS:
            self.set_pin(BUTTON_EXPANDER_ADDRESS, pin, False)
    
    def test_single_pin(self, address: int, pin: int):
        """Turn on a single pin for testing"""
        self.clear_all_test_pins()
        self.set_pin(address, pin, True)
    
    def close(self):
        """Clean up"""
        self.clear_all_test_pins()
        self.bus.close()


def get_pin_description(address, pin):
    """Get human-readable pin description"""
    if address == LED_EXPANDER_ADDRESS:
        return f"LED Expander (0x21) P{pin}"
    else:
        return f"Button Expander (0x20) P{pin}"


def interactive_test():
    """Interactive pin-by-pin testing"""
    print("=" * 50)
    print("Divided LED Pin Identification Test")
    print("=" * 50)
    print()
    print("This test will light up individual pins to help")
    print("identify which is R, G, and B on the new LED.")
    print()
    print("Candidate pins:")
    print("  - LED Expander (0x21): P6, P7")
    print("  - Button Expander (0x20): P6, P7")
    print()
    
    try:
        tester = DividedLedTester()
        print("Connected to both expanders successfully!")
    except Exception as e:
        print(f"Error connecting to expanders: {e}")
        print("\nMake sure:")
        print("  1. I2C is enabled (sudo raspi-config)")
        print("  2. Devices are connected properly")
        print("  3. Run: i2cdetect -y 1")
        sys.exit(1)
    
    # Build list of all test pins
    test_pins = []
    for pin in LED_EXPANDER_PINS:
        test_pins.append((LED_EXPANDER_ADDRESS, pin))
    for pin in BUTTON_EXPANDER_PINS:
        test_pins.append((BUTTON_EXPANDER_ADDRESS, pin))
    
    try:
        while True:
            print("\n" + "=" * 50)
            print("Select a pin to test:")
            print("=" * 50)
            
            for i, (addr, pin) in enumerate(test_pins, 1):
                print(f"  {i}. {get_pin_description(addr, pin)}")
            
            print()
            print("  a. Auto-cycle through all pins (2s each)")
            print("  c. Combination test (light 2 or 3 pins together)")
            print("  0. Turn all test pins OFF")
            print("  q. Quit")
            
            choice = input("\nEnter choice: ").strip().lower()
            
            if choice == 'q':
                break
            
            if choice == '0':
                tester.clear_all_test_pins()
                print("All test pins turned OFF")
                continue
            
            if choice == 'a':
                print("\nAuto-cycling through all pins (press Ctrl+C to stop)...")
                try:
                    for addr, pin in test_pins:
                        desc = get_pin_description(addr, pin)
                        print(f"  Testing: {desc}")
                        tester.test_single_pin(addr, pin)
                        time.sleep(2)
                    tester.clear_all_test_pins()
                    print("Auto-cycle complete")
                except KeyboardInterrupt:
                    tester.clear_all_test_pins()
                    print("\nStopped")
                continue
            
            if choice == 'c':
                combination_test(tester, test_pins)
                continue
            
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(test_pins):
                    addr, pin = test_pins[idx]
                    desc = get_pin_description(addr, pin)
                    tester.test_single_pin(addr, pin)
                    print(f"\n>>> {desc} is now ON <<<")
                    print("What color do you see? (Note it down)")
                else:
                    print("Invalid choice")
            except ValueError:
                print("Please enter a number or valid option")
    
    except KeyboardInterrupt:
        print("\n\nInterrupted")
    
    finally:
        print("\nTurning off all test pins...")
        tester.close()
        print("Done!")


def combination_test(tester, test_pins):
    """Test combinations of pins"""
    print("\n" + "-" * 40)
    print("Combination Test")
    print("-" * 40)
    print("Enter pin numbers separated by spaces to light them together")
    print("Example: '1 2' to light pins 1 and 2 together")
    print("Press Enter with no input to go back")
    
    while True:
        print("\nAvailable pins:")
        for i, (addr, pin) in enumerate(test_pins, 1):
            print(f"  {i}. {get_pin_description(addr, pin)}")
        
        choice = input("\nPins to light (e.g., '1 2 3'): ").strip()
        
        if not choice:
            return
        
        try:
            indices = [int(x) - 1 for x in choice.split()]
            
            # Clear first
            tester.clear_all_test_pins()
            
            # Light selected pins
            for idx in indices:
                if 0 <= idx < len(test_pins):
                    addr, pin = test_pins[idx]
                    tester.set_pin(addr, pin, True)
            
            print("\nLighting pins:", end=" ")
            for idx in indices:
                if 0 <= idx < len(test_pins):
                    addr, pin = test_pins[idx]
                    print(get_pin_description(addr, pin), end=", ")
            print()
            
        except ValueError:
            print("Invalid input. Use numbers separated by spaces.")


def quick_scan():
    """Quick automatic scan - cycles through each pin"""
    print("=" * 50)
    print("Quick Pin Scan - Each pin lights for 3 seconds")
    print("=" * 50)
    
    try:
        tester = DividedLedTester()
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
    
    test_pins = [
        (LED_EXPANDER_ADDRESS, 6),
        (LED_EXPANDER_ADDRESS, 7),
        (BUTTON_EXPANDER_ADDRESS, 6),
        (BUTTON_EXPANDER_ADDRESS, 7),
    ]
    
    try:
        for addr, pin in test_pins:
            desc = get_pin_description(addr, pin)
            print(f"\nTesting: {desc}")
            print("  What color do you see?")
            tester.test_single_pin(addr, pin)
            time.sleep(3)
        
        tester.clear_all_test_pins()
        print("\n" + "=" * 50)
        print("Scan complete! Based on colors observed:")
        print("  - Note which pin showed RED")
        print("  - Note which pin showed GREEN") 
        print("  - Note which pin showed BLUE")
        print("=" * 50)
    
    except KeyboardInterrupt:
        print("\nStopped")
    
    finally:
        tester.close()


def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--quick':
        quick_scan()
    else:
        interactive_test()


if __name__ == "__main__":
    main()
