# BMW E46 M3 Reader

A Python library for reading diagnostic data from a 2006 BMW E46 M3 using a K+DCAN cable.

## Features

- **Engine Data**: Read real-time engine parameters (RPM, coolant temp, oil temp, throttle position, etc.)
- **Fault Codes**: Read and clear Diagnostic Trouble Codes (DTCs)
- **SMG Data**: Read Sequential Manual Gearbox data (gear position, clutch wear, hydraulic pressure)
- **Real-time Logging**: Log data to CSV files for analysis

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
# Read current engine data
python -m bmw_e46_reader engine

# Read fault codes
python -m bmw_e46_reader dtc

# Read SMG data
python -m bmw_e46_reader smg

# Start real-time logging
python -m bmw_e46_reader log --output data.csv --interval 0.1
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
3. Verify correct serial port
4. Try lower baud rates if connection fails

### "No Data" Responses
- Some PIDs may not be supported by your specific ECU variant
- Engine must be running for some live data

## Protocol Details

The E46 M3 uses:
- **K-Line (ISO 9141-2)**: Primary diagnostic protocol for most modules
- **D-CAN (ISO 15765-4)**: Used for some newer modules in late E46s

The K+DCAN cable handles both protocols automatically.

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
