# BMW E46 M3 Reader

A Python library for reading diagnostic data from a 2006 BMW E46 M3 using a K+DCAN cable.

## ⚠️ Current Status

**K-Line communication is partially working.** The cable successfully initializes with the car's gateway module (ISO 9141-2 init responds with sync byte and keywords), but the gateway doesn't forward commands to individual ECUs. This is a known limitation of BMW's gateway architecture.

**For full functionality, consider:**
- **Deep OBD** - Android app that works with INPA cables ([Play Store](https://play.google.com/store/apps/details?id=de.holeschak.bmw_deep_obd))
- **INPA/EDIABAS** - Official BMW diagnostic software (Windows)
- **BMW Standard Tools** - Community-patched version of BMW tools

The diagnostic command can help identify what's working on your specific setup.

## Features

- **Engine Data**: Read real-time engine parameters (RPM, coolant temp, oil temp, throttle position, etc.)
- **Fault Codes**: Read and clear Diagnostic Trouble Codes (DTCs)
- **SMG Data**: Read Sequential Manual Gearbox data (gear position, clutch wear, hydraulic pressure)
- **Real-time Logging**: Log data to CSV files for analysis
- **Diagnostic Mode**: Test K-line communication and identify issues
- **GUI Dashboard**: Live data visualization (tkinter-based)

## Requirements

- Python 3.8+
- BMW K+DCAN USB cable (INPA/EDIABAS compatible)
- BMW E46 M3 (2001-2006)

## Installation

1. Clone this repository:
```bash
git clone https://github.com/yourusername/BMW_E46_Reader.git
cd BMW_E46_Reader
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Connect your K+DCAN cable to the OBD-II port (located under the dashboard on driver's side)

## K+DCAN Cable Setup

### Linux
The cable should appear as `/dev/ttyUSB0`. You may need to add your user to the `dialout` group:
```bash
sudo usermod -a -G dialout $USER
```

### Windows
Install the FTDI drivers and note the COM port number.

### macOS
The cable should appear as `/dev/tty.usbserial-*`

## Usage

### Quick Start
```python
from bmw_e46_reader import E46Connection

# Connect to the car
with E46Connection('/dev/ttyUSB0') as car:
    # Read engine data
    engine = car.get_engine_data()
    print(f"RPM: {engine.rpm}")
    print(f"Coolant Temp: {engine.coolant_temp}°C")
    print(f"Oil Temp: {engine.oil_temp}°C")
    
    # Read fault codes
    dtcs = car.get_fault_codes()
    for dtc in dtcs:
        print(f"DTC: {dtc.code} - {dtc.description}")
    
    # Read SMG data
    smg = car.get_smg_data()
    print(f"Current Gear: {smg.gear}")
    print(f"Clutch Wear: {smg.clutch_wear}%")
```

### Real-time Logging
```python
from bmw_e46_reader import E46Connection, DataLogger

with E46Connection('/dev/ttyUSB0') as car:
    logger = DataLogger(car, 'output.csv')
    logger.start(interval=0.1)  # Log every 100ms
    
    # Log for 60 seconds
    import time
    time.sleep(60)
    
    logger.stop()
```

### Command Line Interface
```bash
# Scan for serial ports
python -m bmw_e46_reader scan

# Test connection
python -m bmw_e46_reader connect

# Run diagnostics (helpful for debugging)
python -m bmw_e46_reader diagnose

# Read current engine data
python -m bmw_e46_reader engine

# Read fault codes
python -m bmw_e46_reader dtc

# Read SMG data  
python -m bmw_e46_reader smg

# Launch GUI dashboard
python -m bmw_e46_reader gui

# Start real-time logging
python -m bmw_e46_reader log --output data.csv --interval 0.1
```

### Diagnostic Mode

Run `diagnose` to test your cable and car communication:

```bash
python -m bmw_e46_reader diagnose
```

This will test:
1. **K-Line Echo** - Verifies cable TX/RX works
2. **ISO 9141-2 Init** - Tests 5-baud initialization
3. **KWP2000 Fast Init** - Tests fast initialization
4. **OBD-II Mode 01** - Tests if ECU responds to commands

Example output:
```
==================================================
DIAGNOSTIC RESULTS
==================================================

1. K-Line Echo Test: ✓ PASS
   Sent: aa, Received: aa

2. ISO 9141-2 Slow Init: ✓ PASS
   Keywords: 0x08 0x08

3. KWP2000 Fast Init: ✓ PASS

4. OBD-II Mode 01 Response: ✗ FAIL
   Raw: 686af10100c4

==================================================
SUMMARY
==================================================
  echo_working: Yes
  init_working: Yes
  ecu_responding: No

NOTES:
  • K-line init works but ECU doesn't respond to commands.
  • This is common with BMW gateway modules.
  • Try: Deep OBD app (Android) or INPA on Windows.
```

## E46 M3 Specific Information

### Engine (S54B32)
The S54 inline-6 engine uses the MSS54 ECU (or MSS54HP on later models).

| Parameter | PID/Address | Unit |
|-----------|-------------|------|
| Engine RPM | 0x0C | RPM |
| Coolant Temp | 0x05 | °C |
| Oil Temp | 0x5C | °C |
| Throttle Position | 0x11 | % |
| Intake Air Temp | 0x0F | °C |
| Mass Air Flow | 0x10 | g/s |
| Engine Load | 0x04 | % |
| Battery Voltage | 0x42 | V |

### SMG II Transmission
The SMG II uses a separate control unit accessible via K-Line.

| Parameter | Description |
|-----------|-------------|
| Gear Position | Current gear (N, 1-6) |
| Clutch Wear | Estimated clutch wear percentage |
| Hydraulic Pressure | SMG pump pressure |
| Shift Mode | Current shift program (S1-S6) |

## Troubleshooting

### Connection Issues
1. Ensure the ignition is ON (position 2)
2. Check cable connection at OBD port
3. Verify correct serial port (`python -m bmw_e46_reader scan`)
4. Run diagnostics to check what's working: `python -m bmw_e46_reader diagnose`

### "Init works but no ECU response"
This is common on BMW E46. The OBD-II port connects to a gateway module (ZKE) that responds to initialization but doesn't forward commands to individual ECUs like the DME or SMG.

**Solutions:**
- Use **Deep OBD** app (Android) - Works with INPA cables via the EDIABAS protocol
- Use **INPA/EDIABAS** on Windows - BMW's official diagnostic software
- Connect directly to ECU via 20-pin connector in engine bay (requires different cable)

### "No Data" Responses
- Some PIDs may not be supported by your specific ECU variant
- Engine must be running for some live data
- BMW uses proprietary protocols beyond standard OBD-II

## Protocol Details

### What We Know About E46 M3

The E46 M3 OBD-II port connects to:
- **K-Line (Pin 7)**: ISO 9141-2 / KWP2000
- **D-CAN (Pin 6)**: Not used on most E46 models

**Protocol Findings:**
- 5-baud init to address 0x33 returns sync byte (0x55) and keywords (0x08 0x08)
- Gateway completes initialization but doesn't forward messages
- BMW's EDIABAS layer handles gateway routing (not standard OBD-II)

### ECU Addresses

| Module | Address | Protocol |
|--------|---------|----------|
| Gateway/ZKE | 0x33 | K-Line |
| DME (Engine) | 0x12 | DS2/KWP2000 |
| EGS/SMG | 0x32 | DS2/KWP2000 |
| Instrument Cluster | 0x80 | DS2 |
| ABS/DSC | 0x56 | DS2 |

### For Developers

INPA cables are raw FTDI serial adapters:
- **RTS LOW** = K-Line mode
- **RTS HIGH** = D-CAN mode
- **DTR** = May control L-Line on some cables

The cable echoes all transmitted data on receive (half-duplex K-line).

## Alternative Tools

If this tool doesn't work with your setup:

1. **Deep OBD (Android)** - Download from Play Store, works with INPA cables
2. **INPA/EDIABAS (Windows)** - Search for "BMW Standard Tools" 
3. **BMW Scanner 1.4.0** - Windows, older but simpler
4. **Carly for BMW** - Commercial app/ELM327

## License

MIT License - See LICENSE file

## Disclaimer

This software is provided for educational and personal use only. Use at your own risk. The authors are not responsible for any damage to your vehicle or voided warranties.

## Contributing

Contributions welcome! Please submit pull requests for:
- Additional PID mappings
- Bug fixes
- Documentation improvements
- New features
