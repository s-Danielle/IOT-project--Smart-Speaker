#!/usr/bin/env python3
"""
Simple LED Identification Script
Turns each LED red one at a time so you can identify which is which.
"""

from smbus2 import SMBus
import time

I2C_BUS = 1
LED_EXPANDER = 0x21      # Main LED expander
BUTTON_EXPANDER = 0x20   # Button expander (has divided LED pin)

def main():
    bus = SMBus(I2C_BUS)
    
    # Read current states
    try:
        led_state = bus.read_byte(LED_EXPANDER)
    except:
        led_state = 0x00
    
    try:
        btn_state = bus.read_byte(BUTTON_EXPANDER)
    except:
        btn_state = 0x3F  # Keep button inputs high
    
    print("=" * 50)
    print("LED IDENTIFICATION - Each LED turns RED")
    print("=" * 50)
    print()
    
    # Turn all off first
    bus.write_byte(LED_EXPANDER, 0x00)
    
    # -------------------------------------------------------------------------
    # LIGHT 1: P0=R, P1=G, P2=B (Health LED)
    # -------------------------------------------------------------------------
    input("Press Enter to turn LIGHT 1 (Health) RED...")
    bus.write_byte(LED_EXPANDER, 0b00000001)  # P0 = RED
    print(">>> LIGHT 1 is now RED - Which LED lit up?")
    print("    (This should be the HEALTH LED)")
    print()
    
    # -------------------------------------------------------------------------
    # LIGHT 2: P3=R, P4=G, P5=B (Speaker LED)
    # -------------------------------------------------------------------------
    input("Press Enter to turn LIGHT 2 (Speaker) RED...")
    bus.write_byte(LED_EXPANDER, 0b00001000)  # P3 = RED
    print(">>> LIGHT 2 is now RED - Which LED lit up?")
    print("    (This should be the SPEAKER LED)")
    print()
    
    # -------------------------------------------------------------------------
    # DIVIDED LED: P6, P7 on 0x21 + P6 or P7 on 0x20
    # -------------------------------------------------------------------------
    print("-" * 50)
    print("Now testing DIVIDED LED pins (for PTT)")
    print("-" * 50)
    
    input("Press Enter to test P6 on LED expander (0x21)...")
    bus.write_byte(LED_EXPANDER, 0b01000000)  # P6
    print(">>> P6 (0x21) ON - What color/LED?")
    print()
    
    input("Press Enter to test P7 on LED expander (0x21)...")
    bus.write_byte(LED_EXPANDER, 0b10000000)  # P7
    print(">>> P7 (0x21) ON - What color/LED?")
    print()
    
    input("Press Enter to test P6 on BUTTON expander (0x20)...")
    bus.write_byte(LED_EXPANDER, 0x00)  # Clear LED expander
    btn_state = (btn_state & 0x3F) | 0b01000000  # Set P6
    bus.write_byte(BUTTON_EXPANDER, btn_state)
    print(">>> P6 (0x20) ON - What color/LED?")
    print()
    
    input("Press Enter to test P7 on BUTTON expander (0x20)...")
    btn_state = (btn_state & 0x3F) | 0b10000000  # Set P7
    bus.write_byte(BUTTON_EXPANDER, btn_state)
    print(">>> P7 (0x20) ON - What color/LED?")
    print()
    
    # -------------------------------------------------------------------------
    # Cleanup
    # -------------------------------------------------------------------------
    input("Press Enter to turn all OFF and exit...")
    bus.write_byte(LED_EXPANDER, 0x00)
    bus.write_byte(BUTTON_EXPANDER, 0x3F)  # Restore button inputs
    bus.close()
    
    print()
    print("=" * 50)
    print("Done! Note which physical LED lit up for each test.")
    print("=" * 50)

if __name__ == "__main__":
    main()
