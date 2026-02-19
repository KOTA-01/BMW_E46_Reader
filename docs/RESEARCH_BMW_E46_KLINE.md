# BMW E46 K-Line Communication Research

## Executive Summary - The Critical Issue

**Your problem is likely that you're using the wrong protocol initialization sequence.**

The 5-baud init to address 0x33 (which returns sync 0x55, keywords 0x08 0x08) is **ISO 9141-2 OBD-II standard initialization**. This talks to the OBD-II gateway for generic/emissions diagnostics, NOT directly to BMW-specific ECUs like DME or SMG.

BMW E46 ECUs (DME, SMG, ABS, etc.) use **DS2 protocol**, which:
- Does NOT use 5-baud initialization
- Communicates directly at 9600 baud, 8N1 or 8E1
- Uses a simple message format: `[Address] [Length] [Data...] [XOR Checksum]`

## Working Open Source Projects

### 1. EdiabasLib (RECOMMENDED)
- **URL**: https://github.com/uholeschak/ediabaslib
- **Status**: Active, 821+ stars, 45 releases
- **Languages**: C# (.NET), works on Linux via Mono
- **Protocols**: DS2, DS1, KWP2000, BMW-FAST, ISO9141, D-CAN
- **Key File**: `EdiabasLib/EdiabasLib/EdInterfaceObd.cs` (5734 lines - full protocol implementation)

### 2. Deep OBD for BMW (Android App based on EdiabasLib)
- **URL**: https://play.google.com/store/apps/details?id=de.holeschak.bmw_deep_obd
- Works with "INPA compatible" FTDI USB D-CAN/K-Line adapters
- Supports E36, E38, E39, E46, E52, E53, E83, E85, E86

### 3. node-bmw-interface
- **URL**: https://github.com/kmalinich/node-bmw-interface
- **Status**: Active, Node.js based
- **Focus**: DBUS, IBUS, KBUS, CAN bus communication

## BMW Protocol Hierarchy (from EdiabasLib source)

```
Concept 0x0001 = Concept 1 (very old BMW)
Concept 0x0002 = KWP1281 (VAG-style, 5-baud wake)
Concept 0x0003 = Concept 3 (5-baud wake, 9600 baud)
Concept 0x0005 = DS2 - BMW E46/E39/E38/etc. (NO init sequence!)
Concept 0x0006 = DS2 variant
Concept 0x010C = KWP2000 BMW (fast init)
Concept 0x010D = KWP2000* (standard)
Concept 0x010F = BMW-FAST
Concept 0x0110 = D-CAN (newer BMW, 115200 baud)
```

## DS2 Protocol (for E46 DME/SMG)

### Message Format
```
+----------+--------+-------------+----------+
| Address  | Length | Data        | Checksum |
| 1 byte   | 1 byte | n bytes     | 1 byte   |
+----------+--------+-------------+----------+
```

### Key Characteristics
- **Baud Rate**: 9600
- **Parity**: Even (some modules) or None
- **Data Bits**: 8
- **Stop Bits**: 1
- **Checksum**: XOR of all preceding bytes
- **No initialization sequence required** - just send the message directly

### Common ECU Addresses (DS2)
```
0x12 = DME (Engine Control - MS43/MS45)
0x18 = EGS (Gearbox) 
0x32 = SMG (Sequential Manual Gearbox)
0x00 = ZKE (Body Electronics)
0x08 = IKE (Instrument Cluster)
0x60 = PDC (Parking Distance Control)
0x44 = EWS (Immobilizer)
```

### Example DS2 Message - Read DME Identification
```python
# Send: [Target] [Length] [Service ID] [Checksum]
# Request IDENT from DME (0x12)
send = [0x12, 0x02, 0x00, 0x10]  # 0x12 XOR 0x02 XOR 0x00 = 0x10

# Response format:
# [Source] [Length] [Data...] [Checksum]
```

### DS2 Python Implementation (from EdiabasLib logic)
```python
import serial
import time

def calc_checksum_xor(data):
    """XOR checksum for DS2"""
    checksum = 0
    for byte in data:
        checksum ^= byte
    return checksum

def ds2_send(ser, address, data):
    """Send DS2 message"""
    msg = [address, len(data)] + list(data)
    msg.append(calc_checksum_xor(msg))
    ser.write(bytes(msg))
    return msg

def ds2_receive(ser, timeout=1.0):
    """Receive DS2 response"""
    # Wait for address byte
    ser.timeout = timeout
    addr = ser.read(1)
    if not addr:
        return None
    
    # Read length
    length = ser.read(1)
    if not length:
        return None
    
    length = length[0]
    
    # Read data + checksum
    data = ser.read(length)
    if len(data) != length:
        return None
    
    # Verify checksum
    msg = bytes([addr[0], length]) + data[:-1]
    if calc_checksum_xor(msg) != data[-1]:
        print("Checksum error!")
        return None
    
    return {
        'address': addr[0],
        'length': length,
        'data': data[:-1],
        'checksum': data[-1]
    }

# Example usage
ser = serial.Serial('/dev/ttyUSB0', 9600, parity=serial.PARITY_EVEN, timeout=0.5)
ser.dtr = False  # Important for raw FTDI adapter
ser.rts = False

# Read DME identification (service 0x00 = IDENT)
ds2_send(ser, 0x12, [0x00])
response = ds2_receive(ser)
```

## Why ISO 9141-2 Init (0x33) Doesn't Work for ECUs

1. **ISO 9141-2 init (5-baud to 0x33)** is the standard OBD-II protocol
2. The gateway at 0x33 responds because it handles OBD-II compliance requests
3. After init, the gateway expects **standard OBD-II PIDs** (01 00, 01 0C, etc.)
4. BMW ECUs (DME, SMG) are NOT on this OBD-II communication path
5. BMW ECUs use **DS2 directly on Pin 7+8** without init sequence

## Physical Connection Requirements

### OBD-II Connector Pinout for E46
```
Pin 4  = Chassis Ground
Pin 5  = Signal Ground
Pin 7  = K-Line (ISO9141/DS2) **CRITICAL**
Pin 8  = K-Line 2 (connected to Pin 7 for some ECUs) **CRITICAL**
Pin 16 = Battery +12V

BMW-specific DS2 communication requires Pin 7+8!
Standard OBD-II K-line is just Pin 7.
```

### Adapter Requirements
- Must support Pin 7+8 connection (not just Pin 7 alone)
- Raw FTDI passthrough (NOT ELM327)
- DTR/RTS control may be needed for line direction

## INPA Working But Your Code Doesn't?

If INPA works on Windows with the same cable:
1. **INPA uses DS2 directly** - no ISO 9141-2 init
2. INPA reads `.PRG` files that define exact protocol/addresses
3. The `.PRG` files specify "Concept 5" (DS2) for E46 ECUs
4. Your 5-baud init is taking you down the wrong communication path

## Recommended Approach

### Step 1: Try DS2 Directly
```python
# Don't do any 5-baud init! Just send DS2 directly:
ser = serial.Serial('/dev/ttyUSB0', 9600, parity=serial.PARITY_EVEN, timeout=1.0)
time.sleep(0.1)

# Request DME IDENT
request = [0x12, 0x02, 0x00]  # Address 0x12, Length 2, Service 0x00
request.append(calc_checksum_xor(request))
ser.write(bytes(request))

# Wait for response
response = ser.read(100)
print(response.hex())
```

### Step 2: If No Response
Try these variations:
- Parity: None vs Even
- DTR line: True vs False
- Timing: Add delays between bytes
- Different addresses: 0x12 (DME), 0x32 (SMG)

### Step 3: Use EdiabasLib on Mono
```bash
# Install Mono on Linux
sudo apt install mono-complete

# Clone EdiabasLib
git clone https://github.com/uholeschak/ediabaslib

# Build and run EdiabasTest
cd ediabaslib/EdiabasLib
msbuild EdiabasLib.sln
mono EdiabasTest.exe -c /dev/ttyUSB0 -p D12.prg -j IDENT
```

## Technical References

### ISO Standards
- ISO 9141-2: OBD-II K-line (generic diagnostics)
- ISO 14230 (KWP2000): Keyword Protocol 2000
- ISO 14229 (UDS): Unified Diagnostic Services

### BMW Documentation
- DS2 is BMW's proprietary protocol predating KWP2000
- Used in E36, E38, E39, E46, E52, E53
- BMW-FAST is the successor, used in later E-series

### Key Source Code References
- EdiabasLib TransDs2(): Lines ~2800-2900 in EdInterfaceObd.cs
- DS2 checksum: `CalcChecksumXor()` 
- DS2 message parsing: `TelLengthDs2()`

## SMG-Specific Information

SMG II (E46 M3) uses address **0x32**:
```python
# SMG Status Request
smg_status = [0x32, 0x02, 0x0B]  # Get SMG status
smg_status.append(calc_checksum_xor(smg_status))

# Common SMG services:
# 0x00 = IDENT
# 0x0B = STATUS
# 0x04 = READ_FAULT_CODES
```

## Debugging Tips

1. **Logic analyzer**: Capture what INPA sends vs what you send
2. **FTDI bit-bang mode**: Some timing-critical operations need this
3. **Check DTR/RTS**: The adapter may need specific signal states
4. **Try 10400 baud**: Some E46 ECUs use 10.4kbaud instead of 9600
5. **Inter-byte timing**: DS2 may need ~5ms between bytes

## Links and Resources

- EdiabasLib: https://github.com/uholeschak/ediabaslib
- Deep OBD Docs: https://github.com/uholeschak/ediabaslib/blob/master/docs/Deep_OBD_for_BMW_and_VAG.md
- Adapter Types: https://github.com/uholeschak/ediabaslib/blob/master/docs/AdapterTypes.md
- Build Custom Adapter: https://github.com/uholeschak/ediabaslib/blob/master/docs/Build_Bluetooth_D-CAN_adapter.md

## Conclusion

**The fundamental issue is protocol mismatch:**
- ISO 9141-2 init (0x33) → OBD-II gateway (responds with 0x55, 0x08, 0x08)
- This is NOT the same as BMW DS2 protocol
- DME/SMG need direct DS2 communication WITHOUT initialization sequence
- Try sending DS2 messages directly at 9600 baud, 8E1, with XOR checksum
