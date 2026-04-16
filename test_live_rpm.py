#!/usr/bin/env python3
"""Quick test: verify RPM updates in real-time via the rewritten engine reader."""
import sys
import time
sys.path.insert(0, '.')

from bmw_e46_reader.ds2 import DS2Connection
from bmw_e46_reader.engine import get_engine_data_ds2

PORT = '/dev/ttyUSB0'

def main():
    conn = DS2Connection(PORT, baud_rate=9600, timeout=1.5)
    conn.connect()
    print("Connected. Reading live engine data 10 times (1s apart)...\n")
    print(f"{'#':>3}  {'RPM':>6}  {'Load':>6}  {'Lambda1':>8}  {'Lambda2':>8}  {'Batt':>5}  {'Intake':>6}  {'Oil':>5}  {'Coolant':>7}")
    print("-" * 72)
    
    for i in range(10):
        data = get_engine_data_ds2(conn)
        rpm_s = f"{data.rpm:.0f}" if data.rpm is not None else "---"
        load_s = f"{data.engine_load:.1f}" if data.engine_load is not None else "---"
        lam1_s = f"{data.lambda_sensor_1:.3f}" if data.lambda_sensor_1 is not None else "---"
        lam2_s = f"{data.lambda_sensor_2:.3f}" if data.lambda_sensor_2 is not None else "---"
        batt_s = f"{data.battery_voltage:.1f}" if data.battery_voltage is not None else "---"
        intake_s = f"{data.intake_temp:.0f}" if data.intake_temp is not None else "---"
        oil_s = f"{data.oil_temp:.0f}" if data.oil_temp is not None else "---"
        cool_s = f"{data.coolant_temp:.1f}" if data.coolant_temp is not None else "---"
        print(f"{i+1:3}  {rpm_s:>6}  {load_s:>6}  {lam1_s:>8}  {lam2_s:>8}  {batt_s:>5}  {intake_s:>6}  {oil_s:>5}  {cool_s:>7}")
        time.sleep(1.0)
    
    conn.disconnect()
    print("\nDone! If RPM values fluctuate above, live data is working.")

if __name__ == '__main__':
    main()
