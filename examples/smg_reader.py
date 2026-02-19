#!/usr/bin/env python3
"""
SMG Data Reader Example

Read Sequential Manual Gearbox data including gear position,
clutch wear, hydraulic pressure, and shift mode.
"""

import time
from bmw_e46_reader import E46Connection, get_smg_data


def main():
    PORT = '/dev/ttyUSB0'
    
    print("BMW E46 M3 SMG II - Data Reader")
    print("=" * 50)
    
    try:
        with E46Connection(PORT) as car:
            print("Reading SMG data...\n")
            
            # Single read
            smg = get_smg_data(car)
            
            # Display gear
            gear_display = {
                0: 'N (Neutral)',
                1: '1st',
                2: '2nd', 
                3: '3rd',
                4: '4th',
                5: '5th',
                6: '6th',
                7: 'R (Reverse)',
                -1: 'Unknown'
            }
            
            print(f"Current Gear:      {gear_display.get(smg.gear.value, 'Unknown')}")
            print(f"Shift Mode:        {smg.shift_mode.name}")
            print()
            
            # Clutch info
            print("Clutch Status:")
            if smg.clutch_position is not None:
                print(f"  Position:        {smg.clutch_position:.1f}%")
            if smg.clutch_wear is not None:
                print(f"  Wear Estimate:   {smg.clutch_wear:.1f}%")
                if smg.clutch_wear > 80:
                    print("  ⚠ WARNING: High clutch wear - consider inspection")
            print()
            
            # Hydraulic system
            print("Hydraulic System:")
            if smg.hydraulic_pressure is not None:
                print(f"  Pressure:        {smg.hydraulic_pressure:.1f} bar")
                if smg.hydraulic_pressure < 40:
                    print("  ⚠ WARNING: Low pressure - check pump/accumulator")
            print(f"  Pump Running:    {'Yes' if smg.pump_running else 'No'}")
            print()
            
            # Temperature
            if smg.gearbox_temp is not None:
                print(f"Gearbox Temp:      {smg.gearbox_temp:.1f}°C")
                if smg.gearbox_temp > 100:
                    print("  ⚠ WARNING: High gearbox temperature")
            
            # Shift performance
            if smg.last_shift_time is not None:
                print(f"Last Shift Time:   {smg.last_shift_time:.0f} ms")
            
            print()
            
            # Continuous monitoring option
            monitor = input("Monitor SMG in real-time? (yes/no): ")
            
            if monitor.lower() == 'yes':
                print("\nMonitoring SMG (Ctrl+C to stop)...\n")
                try:
                    while True:
                        smg = get_smg_data(car)
                        gear = gear_display.get(smg.gear.value, '?')
                        print(f"\rGear: {gear:<12} Mode: {smg.shift_mode.name:<4} Clutch: {smg.clutch_position or 0:>5.1f}% Pressure: {smg.hydraulic_pressure or 0:>5.1f} bar", end='')
                        time.sleep(0.2)
                except KeyboardInterrupt:
                    print("\n\nMonitoring stopped.")
                    
    except ConnectionError as e:
        print(f"Connection failed: {e}")
        print("\nNote: SMG data requires the SMG ECU to be accessible.")
        print("If you have a manual transmission, SMG data won't be available.")


if __name__ == '__main__':
    main()
