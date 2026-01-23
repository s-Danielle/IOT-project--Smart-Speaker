#!/usr/bin/env python3
"""
RGB Lights Test - Interactive test for PCF8574 RGB LEDs
Address: 0x21
Light 1: P0 (R), P1 (G), P2 (B)
Light 2: P3 (R), P4 (G), P5 (B)

LEDs are common-cathode (connected to GND): write 1 to turn LED ON, write 0 to turn LED OFF
"""

from smbus2 import SMBus
import sys

# I2C Configuration
I2C_BUS = 1
RGB_ADDRESS = 0x21

# Pin mappings for each light (R, G, B)
LIGHT1_PINS = (0, 1, 2)  # P0, P1, P2
LIGHT2_PINS = (3, 4, 5)  # P3, P4, P5

# Color definitions (R, G, B) - True = ON, False = OFF
COLORS = {
    1: ("Red",     (True,  False, False)),
    2: ("Green",   (False, True,  False)),
    3: ("Blue",    (False, False, True)),
    4: ("Yellow",  (True,  True,  False)),
    5: ("Cyan",    (False, True,  True)),
    6: ("Magenta", (True,  False, True)),
}


class RGBLightController:
    """Controller for two RGB LEDs on PCF8574"""
    
    def __init__(self, bus_num=I2C_BUS, address=RGB_ADDRESS):
        self.address = address
        self.bus = SMBus(bus_num)
        # Start with all LEDs OFF (all bits LOW for active-high)
        self._state = 0x00
        self._write_state()
    
    def _write_state(self):
        """Write current state to PCF8574"""
        self.bus.write_byte(self.address, self._state)
    
    def set_light(self, light_num: int, r: bool, g: bool, b: bool):
        """
        Set RGB values for a specific light
        
        Args:
            light_num: 1 or 2
            r, g, b: True = ON, False = OFF
        """
        if light_num == 1:
            pins = LIGHT1_PINS
        elif light_num == 2:
            pins = LIGHT2_PINS
        else:
            raise ValueError("light_num must be 1 or 2")
        
        # LEDs are active-high: set bit to turn ON, clear bit to turn OFF
        for pin, is_on in zip(pins, (r, g, b)):
            if is_on:
                self._state |= (1 << pin)   # Set bit (LED ON)
            else:
                self._state &= ~(1 << pin)  # Clear bit (LED OFF)
        
        self._write_state()
    
    def set_color(self, light_num: int, color_num: int):
        """Set a predefined color on a light"""
        if color_num not in COLORS:
            raise ValueError(f"Invalid color number: {color_num}")
        
        _, (r, g, b) = COLORS[color_num]
        self.set_light(light_num, r, g, b)
    
    def turn_off(self, light_num: int):
        """Turn off a specific light"""
        self.set_light(light_num, False, False, False)
    
    def turn_off_all(self):
        """Turn off all lights"""
        self._state = 0x00
        self._write_state()
    
    def close(self):
        """Clean up - turn off all lights and close bus"""
        self.turn_off_all()
        self.bus.close()


def print_menu():
    """Print the color selection menu"""
    print("\n--- Color Options ---")
    for num, (name, _) in COLORS.items():
        print(f"  {num}. {name}")
    print("  0. Turn OFF")
    print("  q. Quit")


def select_light():
    """Prompt user to select a light"""
    while True:
        print("\n=== Select Light ===")
        print("  1. Light 1 (P0-P2)")
        print("  2. Light 2 (P3-P5)")
        print("  q. Quit")
        
        choice = input("\nEnter choice: ").strip().lower()
        
        if choice == 'q':
            return None
        if choice in ('1', '2'):
            return int(choice)
        
        print("Invalid choice. Please enter 1, 2, or q.")


def select_color(controller: RGBLightController, light_num: int):
    """Color selection loop for a specific light"""
    while True:
        print_menu()
        choice = input(f"\nSelect color for Light {light_num} (Enter to apply): ").strip().lower()
        
        if choice == 'q':
            return False  # Signal to quit entirely
        
        if choice == '0':
            controller.turn_off(light_num)
            print(f"Light {light_num} turned OFF")
            continue
        
        if choice == '':
            # Empty input - go back to light selection
            return True
        
        try:
            color_num = int(choice)
            if color_num in COLORS:
                controller.set_color(light_num, color_num)
                color_name = COLORS[color_num][0]
                print(f"Light {light_num} set to {color_name}")
            else:
                print(f"Invalid color number. Choose 1-{len(COLORS)} or 0 for OFF.")
        except ValueError:
            print("Please enter a number or 'q' to quit.")


def main():
    print("=" * 40)
    print("RGB Lights Test")
    print(f"I2C Address: 0x{RGB_ADDRESS:02X}")
    print("=" * 40)
    
    try:
        controller = RGBLightController()
        print("Connected to PCF8574 successfully!")
    except Exception as e:
        print(f"Error: Could not connect to PCF8574 at 0x{RGB_ADDRESS:02X}")
        print(f"Details: {e}")
        print("\nMake sure:")
        print("  1. I2C is enabled (sudo raspi-config)")
        print("  2. Device is connected properly")
        print("  3. Run: i2cdetect -y 1")
        sys.exit(1)
    
    try:
        while True:
            light_num = select_light()
            
            if light_num is None:
                break
            
            if not select_color(controller, light_num):
                break
    
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    
    finally:
        print("\nTurning off all lights...")
        controller.close()
        print("Done!")


if __name__ == "__main__":
    main()
