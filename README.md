# BMW E46 M3 Reader

A Python library for reading diagnostic data from a 2006 BMW E46 M3 using a K+DCAN cable.

## ⚠️ Current Status

**K-Line communication is partially working.** The cable successfully initializes with the car's gateway module (ISO 9141-2 init responds with sync byte and keywords), but the gateway doesn't forward commands to individual ECUs. This is a known limitation of BMW's gateway architecture.

### Working Linux Solutions

Based on community research, these are confirmed working options on Linux:

| Solution | Link | Notes |
|----------|------|-------|
| **Deep OBD (Android)** | [Play Store](https://play.google.com/store/apps/details?id=de.holeschak.bmw_deep_obd) | Works with INPA cables via USB-OTG, full EDIABAS support |
| **EdiabasLib (.NET/Mono)** | [GitHub](https://github.com/uholeschak/ediabaslib) | .NET library that runs on Mono, supports DS2/KWP2000 |
| **pBmwScanner (Python)** | [GitHub](https://github.com/gigijoe/pBmwScanner) | Python DS2/KWP2000 for E38/E39, uses **20-pin connector** |

### Why This Project Has Issues

The E46 has a **gateway module** (in the instrument cluster) that sits between the OBD-II port and the ECUs. This gateway:
- Responds to ISO 9141-2 5-baud initialization ✓
- Requires proper BMW DS2 message format to forward commands ✗
- Uses proprietary EDIABAS protocol layer that we haven't fully implemented

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

### BMW E46 Communication Architecture

```
                    ┌─────────────────────────────────────────┐
                    │           E46 M3 Architecture           │
                    └─────────────────────────────────────────┘
                    
  OBD-II Port (Pin 7 K-Line)                 20-Pin Connector
         │                                         │
         ▼                                         ▼
  ┌─────────────┐                           Direct ECU Access
  │   Gateway   │                           (no gateway)
  │   (IKE)     │
  │   0x33      │
  └──────┬──────┘
         │
    ┌────┴────────────────────────────────┐
    │         K-Bus/Diag-Bus              │
    └────┬──────┬──────┬──────┬──────────┘
         │      │      │      │
         ▼      ▼      ▼      ▼
      ┌─────┐┌─────┐┌─────┐┌─────┐
      │ DME ││ SMG ││ DSC ││ LCM │
      │0x12 ││0x32 ││0x56 ││0xD0 │
      └─────┘└─────┘└─────┘└─────┘
```

### DS2 Protocol (Correct Format)

From [pBmwScanner](https://github.com/gigijoe/pBmwScanner) and [Diolum's gateway analysis](http://www.diolum.fr/analyse-gateway-e46):

**Serial Settings:**
- **Baud Rate:** 9600
- **Data Bits:** 8
- **Parity:** EVEN ⚠️
- **Stop Bits:** 1

**Message Format:**
```
[DEST][LEN][CMD/DATA...][XOR_CHECKSUM]

DEST      = Target ECU address (1 byte)
LEN       = Total message length including checksum (1 byte)
CMD/DATA  = Command and data bytes (variable)
CHECKSUM  = XOR of all preceding bytes (1 byte)
```

**Example - Read DME Identity:**
```
TX: 12 04 00 16
    │  │  │  └─ Checksum (0x12 XOR 0x04 XOR 0x00 = 0x16)
    │  │  └──── Command: 0x00 (Identity Request)
    │  └─────── Length: 4 bytes total
    └────────── Dest: 0x12 (DME)
```

### KWP2000-BMW Protocol

For ECUs using KWP2000 (like ME7.2):

**Message Format:**
```
[0xB8][DEST][SRC][LEN][SID][DATA...][CHECKSUM]

0xB8      = Header byte (fixed)
DEST      = Target ECU address
SRC       = Source address (usually 0xF1 = diagnostic tool)
LEN       = Payload length
SID       = Service ID
DATA      = Service-specific data
CHECKSUM  = XOR of all bytes
```

### Gateway Routing (via OBD-II)

When using OBD-II port, messages go through gateway (0x33):

**DiagBus → KBus Translation:**
```
DiagBus:  [DEST][LEN][CMD][DATA...][XOR]
     ↓    Gateway (IKE) translates
KBus:     [SRC=0x3F][LEN][DEST][CMD][DATA...][XOR]
```

**Important:** The gateway only forwards messages if properly formatted for BMW's protocol layer.

### ECU Addresses

| Module | Address | Protocol | Via OBD-II |
|--------|---------|----------|------------|
| Gateway/IKE | 0x33 | ISO 9141-2 | Yes (direct) |
| DME (Engine) | 0x12 | DS2/KWP2000 | Via gateway |
| EGS/SMG | 0x32 | DS2 | Via gateway |
| Instrument Cluster | 0x80 | DS2 | Via gateway |
| ABS/DSC | 0x56 | DS2 | Via gateway |
| LCM (Lights) | 0xD0 | DS2 | Via gateway |
| RLS (Rain/Light) | 0xE8 | DS2 | Via gateway |
| IHKA (Climate) | 0x5B | DS2 | Via gateway |

### INPA Cable Hardware

Standard "INPA compatible" K+DCAN cables contain:
- FTDI FT232RL USB-Serial chip
- ATF16V8B PLD (programmable logic)
- ATmega microcontroller
- K-Line transceiver

**Important:** These are NOT simple FTDI pass-through! The onboard MCU handles:
- K-Line TX/RX switching
- Echo management
- DTR/RTS line control

**Line Control:**
- **RTS LOW** = K-Line mode (9600 baud)
- **RTS HIGH** = D-CAN mode (500kbps CAN)
- **DTR** = May control L-Line or TX enable

### Differences from Standard OBD-II

| Feature | Standard OBD-II | BMW E46 |
|---------|-----------------|---------|
| Protocol | ISO 9141-2 / KWP2000 | DS2 / KWP2000-BMW |
| Baud | 10400 | 9600 |
| Parity | None | Even |
| Gateway | None | Required on OBD-II |
| Header | ISO format | BMW format (0xB8) |

### Known Working Code

**pBmwScanner** (Python, E38/E39):
```python
# From k_line.py - proven working settings
self._device = serial.Serial("/dev/ttyUSB0", 9600, parity=serial.PARITY_EVEN, timeout=0.5)

# From ds2.py - DS2 message format
def _write(self, address, payload):
    size = 2 + len(payload) + 1  # addr + size + payload + checksum
    p = bytearray([address, size])
    p.extend(payload)
    p.append(self._checksum(p))  # XOR checksum
    self._device.write(p)
```

### For Developers

## Alternative Tools

If this tool doesn't work with your setup:

1. **Deep OBD (Android)** - Download from Play Store, works with INPA cables
2. **INPA/EDIABAS (Windows)** - Search for "BMW Standard Tools" 
3. **BMW Scanner 1.4.0** - Windows, older but simpler
4. **Carly for BMW** - Commercial app/ELM327

## References & Resources

### Working Projects (Confirmed on Linux)

| Project | Language | Description |
|---------|----------|-------------|
| [EdiabasLib](https://github.com/uholeschak/ediabaslib) | C#/.NET | Full EDIABAS replacement, runs on Mono |
| [pBmwScanner](https://github.com/gigijoe/pBmwScanner) | Python | DS2/KWP2000 for E38/E39, **20-pin connector** |
| [pyBus](https://github.com/ezeakeal/pyBus) | Python | iBus interface for E46 (radio, cluster, etc.) |
| [node-bmw-ref](https://github.com/kmalinich/node-bmw-ref) | C/JS | BMW bus reference and examples |

### Protocol Documentation

| Resource | Description |
|----------|-------------|
| [Diolum E46 Gateway Analysis](http://www.diolum.fr/analyse-gateway-e46) | Detailed E46 gateway reverse engineering (French) |
| [BMW Gateway Emulator](https://github.com/Diolum/BMW_gateway_emulator) | Arduino gateway emulator code |
| [DiagTrx Library](https://github.com/Diolum/arduino-diagtrx) | Arduino library for BMW DiagBus |

### Key Insights from Research

1. **Serial Settings Matter**: BMW uses 9600 baud with EVEN parity, not 10400/no parity like standard OBD-II

2. **20-Pin vs OBD-II**: The 20-pin round connector in the engine bay provides direct ECU access without gateway routing. pBmwScanner uses this approach.

3. **Gateway Translation**: The IKE (instrument cluster) acts as a gateway, translating between DiagBus and KBus formats

4. **EdiabasLib is the Reference**: The most complete open-source implementation of BMW protocols

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
