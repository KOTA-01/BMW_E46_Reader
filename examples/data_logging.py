#!/usr/bin/env python3
"""
Data Logging Example

Log engine and SMG data to a CSV file for later analysis.
Useful for tracking performance, diagnosing issues, or 
recording acceleration runs.
"""

import time
from datetime import datetime
from bmw_e46_reader import E46Connection, DataLogger


def main():
    PORT = '/dev/ttyUSB0'
    
    # Create output filename with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = f'e46_log_{timestamp}.csv'
    
    print("BMW E46 M3 - Data Logger")
    print("=" * 50)
    print(f"Output file: {output_file}")
    print()
    
    # Configuration
    log_interval = 0.1  # 100ms = 10 Hz logging rate
    duration = 0  # 0 = unlimited, or set to number of seconds
    
    try:
        with E46Connection(PORT) as car:
            print("Connected! Starting data logger...")
            print(f"Logging at {1/log_interval:.0f} Hz")
            print("Press Ctrl+C to stop logging\n")
            
            # Create logger
            logger = DataLogger(
                connection=car,
                output_file=output_file,
                log_engine=True,
                log_smg=True
            )
            
            # Optional: Add a callback to display live data
            def live_display(data):
                rpm = data.get('rpm', 0) or 0
                speed = data.get('speed', 0) or 0
                gear = data.get('gear', '-')
                print(f"\rSamples: {logger.sample_count:>6} | RPM: {rpm:>5.0f} | Speed: {speed:>3.0f} km/h | Gear: {gear}", end='')
            
            logger.add_callback(live_display)
            
            # Start logging
            logger.start(interval=log_interval)
            
            try:
                if duration > 0:
                    print(f"Logging for {duration} seconds...")
                    time.sleep(duration)
                else:
                    # Run until Ctrl+C
                    while True:
                        time.sleep(1)
            except KeyboardInterrupt:
                pass
            
            # Stop and get statistics
            stats = logger.stop()
            
            print("\n\n" + "=" * 50)
            print("Logging Complete!")
            print(f"  Total samples:  {stats.get('samples', 0)}")
            print(f"  Duration:       {stats.get('duration_seconds', 0):.1f} seconds")
            print(f"  Average rate:   {stats.get('average_rate_hz', 0):.1f} Hz")
            print(f"  Output file:    {stats.get('output_file', output_file)}")
            print()
            print("You can open the CSV file in Excel or analyze with pandas.")
            
    except ConnectionError as e:
        print(f"Connection failed: {e}")


if __name__ == '__main__':
    main()
