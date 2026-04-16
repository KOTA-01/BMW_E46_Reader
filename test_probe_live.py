"""Probe MSS54 DME for truly live data: try session init, different commands,
and reconnect between reads to find what actually updates in real-time."""
import serial
import time
import sys

port = '/dev/ttyUSB0'
DELAY = 0.010

def xor_cs(data):
    r = 0
    for b in data:
        r ^= b
    return r

def ds2_send(ser, addr, cmd, delay=DELAY):
    ser.reset_input_buffer()
    payload = bytes(cmd)
    length = 2 + len(payload) + 1
    msg = bytes([addr, length]) + payload
    full = msg + bytes([xor_cs(msg)])
    for b in full:
        ser.write(bytes([b]))
        time.sleep(delay)
    ser.flush()
    time.sleep(0.05)
    echo = ser.read(len(full))
    time.sleep(0.20)
    ab = ser.read(1)
    if not ab:
        return None
    lb = ser.read(1)
    if not lb:
        return None
    rlen = lb[0] - 2
    rest = ser.read(rlen) if rlen > 0 else b''
    return ab + lb + rest

def open_port():
    ser = serial.Serial(port=port, baudrate=9600, bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_EVEN, stopbits=serial.STOPBITS_ONE, timeout=1.5)
    ser.dtr = False
    ser.rts = False
    time.sleep(0.1)
    ser.reset_input_buffer()
    return ser

def extract_data(resp):
    """Extract payload from DS2 response (skip addr, len, status, checksum)."""
    if resp and len(resp) > 4:
        return resp[3:-1]
    elif resp and len(resp) > 3:
        return resp[3:]
    return b''

# ──────── TEST 1: Reconnect between reads ────────
print("=" * 60)
print("TEST 1: Does reconnecting the port refresh the snapshot?")
print("=" * 60)
for i in range(3):
    ser = open_port()
    resp = ds2_send(ser, 0x12, [0x14, 0x01])
    ser.close()
    if resp and len(resp) > 78:
        d = extract_data(resp)
        if len(d) > 78:
            rpm = (d[77] << 8) | d[78]
            print(f"  Read {i}: counter={d[0]:3d} RPM={rpm:4d} V={d[1]/10.0:.1f} "
                  f"oil={d[9]-40}C coolant={d[25]*0.75:.1f}C")
    else:
        print(f"  Read {i}: no response")
    time.sleep(1.0)
print()

# ──────── TEST 2: Try diagnostic session first ────────
print("=" * 60)
print("TEST 2: Enter diagnostic session, then read")
print("=" * 60)
ser = open_port()

session_cmds = [
    ([0x10, 0x00], "StartDiag default"),
    ([0x10, 0x01], "StartDiag standard"),
    ([0x10, 0x02], "StartDiag extended"),
    ([0x10, 0x03], "StartDiag programming"),
    ([0x10, 0x85], "StartDiag 0x85"),
    ([0x10, 0x86], "StartDiag 0x86"),
    ([0x10, 0x89], "StartDiag BMW mode"),
]
for cmd, label in session_cmds:
    resp = ds2_send(ser, 0x12, cmd)
    if resp:
        status = resp[2] if len(resp) > 2 else 0
        st = {0xA0:'OK', 0xA1:'BUSY', 0xA2:'INVALID', 0xB0:'REJECT', 0xFF:'BAD'}.get(status, f'0x{status:02X}')
        print(f"  {label:25s} -> {st:7s} ({len(resp)}B) {resp.hex()}")
    else:
        print(f"  {label:25s} -> no response")
    time.sleep(0.05)

# After session init, read RAM again
resp_after = ds2_send(ser, 0x12, [0x14, 0x01])
if resp_after:
    d = extract_data(resp_after)
    if len(d) > 78:
        rpm = (d[77] << 8) | d[78]
        print(f"  -> After session: counter={d[0]:3d} RPM={rpm:4d}")
ser.close()
print()

# ──────── TEST 3: ReadDataByLocalIdentifier (0x21) ────────
print("=" * 60)
print("TEST 3: ReadDataByLocalIdentifier (0x21 + sub-ID)")
print("=" * 60)
ser = open_port()
for sub_id in range(0x00, 0x30):
    resp = ds2_send(ser, 0x12, [0x21, sub_id])
    if resp and len(resp) > 3:
        status = resp[2] if len(resp) > 2 else 0
        if status == 0xA0:  # Only show OK responses
            d = extract_data(resp)
            print(f"  0x21 0x{sub_id:02X}: OK ({len(resp)}B) data={d.hex()}")
    time.sleep(0.02)
# Also try high range
for sub_id in [0x40, 0x60, 0x80, 0xA0, 0xC0, 0xE0, 0xF0, 0xFE, 0xFF]:
    resp = ds2_send(ser, 0x12, [0x21, sub_id])
    if resp and len(resp) > 3:
        status = resp[2] if len(resp) > 2 else 0
        if status == 0xA0:
            d = extract_data(resp)
            print(f"  0x21 0x{sub_id:02X}: OK ({len(resp)}B) data={d.hex()}")
    time.sleep(0.02)
ser.close()
print()

# ──────── TEST 4: ReadMemoryByAddress (0x23) & misc commands ────────
print("=" * 60)
print("TEST 4: Misc commands (0x12, 0x1A, 0x22, 0x23, 0x2F, 0x30, 0x31)")
print("=" * 60)
ser = open_port()
misc_cmds = [
    ([0x01],                "ReadECUReset"),
    ([0x1A, 0x80],          "ReadECUId 0x80"),
    ([0x1A, 0x87],          "ReadECUId 0x87"),
    ([0x1A, 0x91],          "ReadECUId VIN"),
    ([0x1A, 0x9B],          "ReadECUId ECU"),
    ([0x22, 0x00, 0x01],    "ReadDataByCommonId 0x0001"),
    ([0x22, 0xF1, 0x90],    "ReadDataByCommonId VIN"),
    ([0x23, 0x00, 0x38, 0x00, 0x10], "ReadMemByAddr 0x3800 16B"),
    ([0x2C, 0x01],          "DynDefDataId"),
    ([0x2F, 0x00],          "IOControlById"),
    ([0x30, 0x00],          "IOControlByLocalId"),
    ([0x04, 0x00],          "ReadDataByBlock 0"),
    ([0x04, 0x01],          "ReadDataByBlock 1"),
    ([0x04, 0x02],          "ReadDataByBlock 2"),
]
for cmd, label in misc_cmds:
    resp = ds2_send(ser, 0x12, cmd)
    if resp and len(resp) > 3:
        status = resp[2] if len(resp) > 2 else 0
        st = {0xA0:'OK', 0xA1:'BUSY', 0xA2:'INVALID', 0xB0:'REJECT', 0xFF:'BAD'}.get(status, f'0x{status:02X}')
        d = extract_data(resp)
        dh = d.hex()[:60]
        print(f"  {label:30s} -> {st:7s} ({len(resp)}B) {dh}")
    else:
        print(f"  {label:30s} -> no response")
    time.sleep(0.05)
ser.close()
print()

# ──────── TEST 5: Full command byte scan (0x00-0x30) ────────
print("=" * 60)
print("TEST 5: Full scan of single-byte commands 0x00-0x3F")
print("=" * 60)
ser = open_port()
for cmd_byte in range(0x00, 0x40):
    resp = ds2_send(ser, 0x12, [cmd_byte])
    if resp and len(resp) > 3:
        status = resp[2] if len(resp) > 2 else 0
        if status not in (0xA2, 0xFF):  # Skip invalid/bad
            st = {0xA0:'OK', 0xA1:'BUSY', 0xB0:'REJECT'}.get(status, f'0x{status:02X}')
            d = extract_data(resp)
            dh = d.hex()[:40]
            print(f"  0x{cmd_byte:02X} -> {st:7s} ({len(resp):3d}B) {dh}")
    time.sleep(0.02)
ser.close()
print()
print("Done.")
