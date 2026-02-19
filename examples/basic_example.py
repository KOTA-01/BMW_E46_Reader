#!/usr/bin/env python3
"""
Basic Example - Read engine data from E46 M3

This example shows how to connect to the vehicle and read
basic engine parameters.
"""

from bmw_e46_reader import E46Connection


def main():
    # Update this to match your serial port
    # Linux: typically /dev/ttyUSB0
    # macOS: /dev/tty.usbserial-XXXXX
    # Windows: COM3, COM4, etc.
    PORT = '/dev/ttyUSB0'
    
    print("BMW E46 M3 Reader - Basic Example")
    print("=" * 40)
    
    # Connect to the vehicle
    # Make sure ignition is ON (position 2)
    try:
        with E46Connection(PORT) as car:
            print("Connected!")
            
            # Read engine data
            engine = car.get_engine_data()
            
            print("\nEngine Data:")
            print(f"  RPM:          {engine.rpm:.0f}" if engine.rpm else "  RPM:          N/A")
            print(f"  Speed:        {engine.speed:.0f} km/h" if engine.speed else "  Speed:        N/A")
            print(f"  Coolant Temp: {engine.coolant_temp:.1f}°C" if engine.coolant_temp else "  Coolant Temp: N/A")
            print(f"  Oil Temp:     {engine.oil_temp:.1f}°C" if engine.oil_temp else "  Oil Temp:     N/A")
            print(f"  Throttle:     {engine.throttle_position:.1f}%" if engine.throttle_position else "  Throttle:     N/A")
            print(f"  Engine Load:  {engine.engine_load:.1f}%" if engine.engine_load else "  Engine Load:  N/A")
            
    except ConnectionError as e:
        print(f"Connection failed: {e}")
        print("\nTroubleshooting:")
        print("1. Is the K+DCAN cable connected to the OBD port?")
        print("2. Is the ignition ON (position 2)?")
        print(f"3. Is the correct port specified? (currently: {PORT})")


if __name__ == '__main__':
    main()
