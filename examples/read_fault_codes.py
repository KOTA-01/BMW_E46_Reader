#!/usr/bin/env python3
"""
Read Fault Codes Example

This example shows how to read and optionally clear
diagnostic trouble codes (DTCs) from the vehicle.
"""

from bmw_e46_reader import E46Connection, get_fault_codes, clear_fault_codes


def main():
    PORT = '/dev/ttyUSB0'
    
    print("BMW E46 M3 - Fault Code Reader")
    print("=" * 50)
    
    try:
        with E46Connection(PORT) as car:
            print("Reading fault codes...\n")
            
            # Get all fault codes
            codes = get_fault_codes(car)
            
            if not codes:
                print("✓ No fault codes stored!")
            else:
                print(f"Found {len(codes)} fault code(s):\n")
                
                for code in codes:
                    print(f"Code:        {code.code}")
                    print(f"Description: {code.description}")
                    print(f"Status:      {code.status.value}")
                    print(f"ECU:         {code.ecu}")
                    print("-" * 40)
                
                # Ask if user wants to clear codes
                print()
                clear = input("Do you want to clear these fault codes? (yes/no): ")
                
                if clear.lower() == 'yes':
                    print("\nClearing fault codes...")
                    if clear_fault_codes(car):
                        print("✓ Fault codes cleared successfully!")
                        print("Note: If the issue persists, codes will return.")
                    else:
                        print("✗ Failed to clear fault codes")
                        
    except ConnectionError as e:
        print(f"Connection failed: {e}")


if __name__ == '__main__':
    main()
