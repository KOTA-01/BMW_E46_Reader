"""
BMW E46 M3 Data Discovery Tool
Scans all ECUs, captures all data, identifies live/changing variables
"""

import time
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from collections import defaultdict
from .connection import DS2Connection


# Known E46 ECU addresses
ECU_ADDRESSES = {
    0x12: "DME (Engine)",
    0x32: "SMG (Transmission)", 
    0x44: "EWS (Immobilizer)",
    0x00: "IKE (Instrument Cluster)",
    0x18: "ZKE (Body Module)",
    0x60: "PDC (Park Distance)",
    0x80: "ABS/DSC",
    0xA0: "Airbag",
    0xB0: "LCM (Light Module)",
    0xD0: "Navigation",
}

# DS2 commands to try
DS2_COMMANDS = {
    "ident": bytes([0x00]),           # Identity
    "status": bytes([0x0B]),          # Status
    "analog": bytes([0x0D]),          # Analog values
    "ext": bytes([0x0E]),             # Extended values
    "block0": bytes([0x04, 0x00]),    # Read block 0
    "block1": bytes([0x04, 0x01]),    # Read block 1
    "block2": bytes([0x04, 0x02]),    # Read block 2
    "block3": bytes([0x04, 0x03]),    # Read block 3
    "ram": bytes([0x14]),             # RAM data (DME live)
    "io": bytes([0x09]),              # I/O status
    "dtc": bytes([0x05]),             # Read DTCs
}


@dataclass
class ECUData:
    """Stores data from one ECU"""
    address: int
    name: str
    responses: Dict[str, bytes] = field(default_factory=dict)
    available_commands: List[str] = field(default_factory=list)


@dataclass  
class VariableChange:
    """Tracks a changing variable"""
    ecu_addr: int
    ecu_name: str
    command: str
    byte_offset: int
    values_seen: List[int] = field(default_factory=list)
    timestamps: List[float] = field(default_factory=list)


class DataDiscovery:
    """Discovers and monitors all ECU data"""
    
    def __init__(self, port: str = '/dev/ttyUSB0'):
        self.port = port
        self.ecus: Dict[int, ECUData] = {}
        self.baseline: Dict[Tuple[int, str], List[int]] = {}
        self.changes: Dict[Tuple[int, str, int], VariableChange] = {}
        
    def scan_all_ecus(self) -> Dict[int, ECUData]:
        """Scan all known ECU addresses"""
        print("=" * 60)
        print("PHASE 1: Scanning all ECUs")
        print("=" * 60)
        
        with DS2Connection(self.port) as ds2:
            for addr, name in ECU_ADDRESSES.items():
                print(f"\nTrying {name} (0x{addr:02X})...")
                
                # Try identity command first
                resp = ds2.execute(addr, bytes([0x00]))
                if resp and len(resp) > 4:
                    ecu = ECUData(address=addr, name=name)
                    self.ecus[addr] = ecu
                    print(f"  ✓ FOUND! Response: {len(resp)} bytes")
                    
                    # Now try all commands
                    for cmd_name, cmd_bytes in DS2_COMMANDS.items():
                        try:
                            resp = ds2.execute(addr, cmd_bytes)
                            if resp and len(resp) > 4:
                                data = resp[3:-1]  # Strip header/checksum
                                ecu.responses[cmd_name] = data
                                ecu.available_commands.append(cmd_name)
                        except:
                            pass
                    
                    print(f"  Commands available: {ecu.available_commands}")
                else:
                    print(f"  ✗ No response")
                    
        return self.ecus
    
    def capture_baseline(self) -> Dict[Tuple[int, str], List[int]]:
        """Capture baseline readings from all responding ECUs"""
        print("\n" + "=" * 60)
        print("PHASE 2: Capturing baseline data")
        print("=" * 60)
        
        with DS2Connection(self.port) as ds2:
            for addr, ecu in self.ecus.items():
                print(f"\n{ecu.name} (0x{addr:02X}):")
                
                for cmd_name in ecu.available_commands:
                    cmd_bytes = DS2_COMMANDS[cmd_name]
                    resp = ds2.execute(addr, cmd_bytes)
                    
                    if resp and len(resp) > 4:
                        data = list(resp[3:-1])
                        self.baseline[(addr, cmd_name)] = data
                        
                        # Print first 20 bytes
                        preview = data[:20]
                        suffix = "..." if len(data) > 20 else ""
                        print(f"  {cmd_name:10}: [{', '.join(f'{b:3d}' for b in preview)}{suffix}] ({len(data)} bytes)")
                        
        return self.baseline
    
    def monitor_changes(self, duration: int = 30, interval: float = 0.5) -> Dict:
        """Monitor for changing values"""
        print("\n" + "=" * 60)
        print(f"PHASE 3: Monitoring for changes ({duration}s)")
        print("=" * 60)
        print(">>> SHIFT GEARS, REV ENGINE, MOVE CONTROLS NOW! <<<\n")
        
        start_time = time.time()
        samples = 0
        
        with DS2Connection(self.port) as ds2:
            while time.time() - start_time < duration:
                samples += 1
                now = time.time()
                
                for (addr, cmd_name), baseline_data in self.baseline.items():
                    cmd_bytes = DS2_COMMANDS[cmd_name]
                    resp = ds2.execute(addr, cmd_bytes)
                    
                    if resp and len(resp) > 4:
                        current_data = list(resp[3:-1])
                        
                        # Compare each byte
                        for i, (baseline_val, current_val) in enumerate(zip(baseline_data, current_data)):
                            if baseline_val != current_val:
                                key = (addr, cmd_name, i)
                                
                                if key not in self.changes:
                                    ecu = self.ecus[addr]
                                    self.changes[key] = VariableChange(
                                        ecu_addr=addr,
                                        ecu_name=ecu.name,
                                        command=cmd_name,
                                        byte_offset=i
                                    )
                                    print(f"  NEW CHANGE: {ecu.name} {cmd_name}[{i}]: {baseline_val} -> {current_val}")
                                
                                change = self.changes[key]
                                if current_val not in change.values_seen:
                                    change.values_seen.append(current_val)
                                    change.timestamps.append(now - start_time)
                
                elapsed = time.time() - start_time
                print(f"\r  Sample {samples}, {elapsed:.1f}s elapsed, {len(self.changes)} variables changed", end="", flush=True)
                time.sleep(interval)
        
        print(f"\n\nMonitoring complete. Found {len(self.changes)} changing variables.")
        return self.changes
    
    def print_full_report(self):
        """Print comprehensive report of all findings"""
        print("\n" + "=" * 60)
        print("FULL DATA REPORT")
        print("=" * 60)
        
        # ECU Summary
        print(f"\n--- ECUs Found: {len(self.ecus)} ---")
        for addr, ecu in self.ecus.items():
            print(f"  0x{addr:02X}: {ecu.name}")
            print(f"         Commands: {', '.join(ecu.available_commands)}")
        
        # All baseline data
        print(f"\n--- All Captured Data ---")
        for (addr, cmd_name), data in sorted(self.baseline.items()):
            ecu = self.ecus[addr]
            print(f"\n{ecu.name} / {cmd_name} ({len(data)} bytes):")
            
            # Print in rows of 16
            for row_start in range(0, len(data), 16):
                row_end = min(row_start + 16, len(data))
                row = data[row_start:row_end]
                hex_str = ' '.join(f'{b:02X}' for b in row)
                dec_str = ' '.join(f'{b:3d}' for b in row)
                print(f"  [{row_start:3d}] {hex_str}")
                print(f"        {dec_str}")
        
        # Changing variables
        if self.changes:
            print(f"\n--- Live/Changing Variables: {len(self.changes)} ---")
            for key, change in sorted(self.changes.items()):
                print(f"  {change.ecu_name} / {change.command}[{change.byte_offset}]")
                print(f"    Values seen: {change.values_seen}")
        
        # Interpretation hints
        print("\n--- Interpretation Guide ---")
        print("  Temperature: (raw - 40) or (raw * 0.75) for °C")
        print("  Voltage: (raw * 0.1) for V")
        print("  RPM: (byte[n] << 8 | byte[n+1]) for big-endian")
        print("  Gear: 0=N, 1-6=gear, 7=R (check specific byte)")
    
    def find_specific_values(self):
        """Look for specific requested values"""
        print("\n" + "=" * 60)
        print("SEARCHING FOR SPECIFIC VALUES")
        print("=" * 60)
        
        results = {}
        
        # SMG specific searches
        if 0x32 in self.ecus:
            smg_data = {}
            for cmd_name in self.ecus[0x32].available_commands:
                key = (0x32, cmd_name)
                if key in self.baseline:
                    smg_data[cmd_name] = self.baseline[key]
            
            print("\n--- SMG Data Analysis ---")
            for cmd_name, data in smg_data.items():
                print(f"\n{cmd_name} ({len(data)} bytes):")
                
                # Look for potential gear values (0-7)
                gear_candidates = [(i, v) for i, v in enumerate(data) if 0 <= v <= 7]
                if gear_candidates:
                    print(f"  Potential gear bytes (0-7): {gear_candidates[:10]}")
                
                # Look for temperature values (40-140 range = 0-100°C after -40)
                temp_candidates = [(i, v, v-40) for i, v in enumerate(data) if 60 <= v <= 160]
                if temp_candidates:
                    print(f"  Potential temps (raw, °C): {[(i, f'{c}°C') for i, v, c in temp_candidates[:5]]}")
                
                # Look for voltage (100-150 range = 10-15V)
                volt_candidates = [(i, v, v/10) for i, v in enumerate(data) if 100 <= v <= 160]
                if volt_candidates:
                    print(f"  Potential voltage: {[(i, f'{c:.1f}V') for i, v, c in volt_candidates[:5]]}")
        
        # DME specific searches  
        if 0x12 in self.ecus:
            dme_data = {}
            for cmd_name in self.ecus[0x12].available_commands:
                key = (0x12, cmd_name)
                if key in self.baseline:
                    dme_data[cmd_name] = self.baseline[key]
            
            print("\n--- DME Data Analysis ---")
            if 'ram' in dme_data:
                data = dme_data['ram']
                print(f"\nRAM data ({len(data)} bytes) - Known values:")
                
                if len(data) > 25:
                    # Known from earlier work
                    coolant = data[25] * 0.75
                    print(f"  Byte 25: Coolant temp = {coolant:.1f}°C")
                
                if len(data) > 9:
                    oil = data[9] - 40
                    print(f"  Byte 9: Oil temp = {oil}°C")
                
                if len(data) > 2:
                    intake = data[2] - 40
                    print(f"  Byte 2: Intake temp = {intake}°C")
                
                # Look for ECU temp and voltage
                print("\n  Searching for ECU temp and voltage...")
                for i, v in enumerate(data):
                    # ECU temp usually 20-60°C (raw 60-100)
                    if 60 <= v <= 100:
                        print(f"    Byte {i}: {v} (if temp: {v-40}°C)")
                    # Voltage 12-14.5V (raw 120-145)
                    if 120 <= v <= 150:
                        print(f"    Byte {i}: {v} (if voltage: {v/10:.1f}V)")


def run_full_discovery(port: str = '/dev/ttyUSB0', monitor_time: int = 30):
    """Run complete discovery process"""
    disc = DataDiscovery(port)
    
    # Phase 1: Find all ECUs
    disc.scan_all_ecus()
    
    if not disc.ecus:
        print("\nNo ECUs found! Check connection.")
        return None
    
    # Phase 2: Capture baseline
    disc.capture_baseline()
    
    # Phase 3: Monitor for changes
    disc.monitor_changes(duration=monitor_time)
    
    # Phase 4: Analysis
    disc.find_specific_values()
    
    # Phase 5: Full report
    disc.print_full_report()
    
    return disc


if __name__ == "__main__":
    run_full_discovery()
