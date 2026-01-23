#!/usr/bin/env python3
"""
Debug script for RGB LEDs on PCF8574
Tests both active-high and active-low logic
"""

from smbus2 import SMBus
import time

I2C_BUS = 1
RGB_ADDRESS = 0x21

def main():
    bus = SMBus(I2C_BUS)
    
    print(f"Connected to 0x{RGB_ADDRESS:02X}")
    print("\n" + "="*50)
    
    # First, let's see current state
    current = bus.read_byte(RGB_ADDRESS)
    print(f"Current state: 0x{current:02X} = {current:08b}")
    
    print("\n" + "="*50)
    print("TEST 1: Active-HIGH (write 1 = LED ON)")
    print("="*50)
    
    # Test Light 1 Red (P0) with active-high
    print("\nTurning ON Light 1 RED (P0) - writing 0x01...")
    bus.write_byte(RGB_ADDRESS, 0x01)  # Only P0 high
    input("Press Enter to continue...")
    
    print("Turning ON Light 1 GREEN (P1) - writing 0x02...")
    bus.write_byte(RGB_ADDRESS, 0x02)  # Only P1 high
    input("Press Enter to continue...")
    
    print("Turning ON Light 1 BLUE (P2) - writing 0x04...")
    bus.write_byte(RGB_ADDRESS, 0x04)  # Only P2 high
    input("Press Enter to continue...")
    
    print("Turning ON ALL Light 1 (P0-P2) WHITE - writing 0x07...")
    bus.write_byte(RGB_ADDRESS, 0x07)  # P0, P1, P2 high
    input("Press Enter to continue...")
    
    print("\n" + "="*50)
    print("TEST 2: Active-LOW (write 0 = LED ON)")
    print("="*50)
    
    # Test Light 1 Red (P0) with active-low
    print("\nTurning ON Light 1 RED (P0) - writing 0xFE...")
    bus.write_byte(RGB_ADDRESS, 0xFE)  # Only P0 low
    input("Press Enter to continue...")
    
    print("Turning ON Light 1 GREEN (P1) - writing 0xFD...")
    bus.write_byte(RGB_ADDRESS, 0xFD)  # Only P1 low
    input("Press Enter to continue...")
    
    print("Turning ON Light 1 BLUE (P2) - writing 0xFB...")
    bus.write_byte(RGB_ADDRESS, 0xFB)  # Only P2 low
    input("Press Enter to continue...")
    
    print("Turning ON ALL Light 1 (P0-P2) WHITE - writing 0xF8...")
    bus.write_byte(RGB_ADDRESS, 0xF8)  # P0, P1, P2 low
    input("Press Enter to continue...")
    
    print("\n" + "="*50)
    print("Turning all OFF (0xFF)...")
    bus.write_byte(RGB_ADDRESS, 0xFF)
    
    print("\nWhich test worked?")
    print("  1 = Active-HIGH worked (Test 1)")
    print("  2 = Active-LOW worked (Test 2)")
    print("  0 = Neither worked")
    
    bus.close()

if __name__ == "__main__":
    main()
