"""Scan for RPM: try 0x0B with sub-commands, 0x14 with more blocks,
and 0x12 ReadMemoryByAddress at known MSS54 locations."""
import serial
import time

port = '/dev/ttyUSB0'
DELAY = 0.010

def xor_cs(data):
    r = 0
    for b in data: r ^= b
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
    if not ab: return None
    lb = ser.read(1)
    if not lb: return None
    rlen = lb[0] - 2
    rest = ser.read(rlen) if rlen > 0 else b''
    return ab + lb + rest

def extract(resp):
    if resp and len(resp) > 4: return resp[3:-1]
    elif resp and len(resp) > 3: return resp[3:]
    return b''

def open_port():
    ser = serial.Serial(port=port, baudrate=9600, bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_EVEN, stopbits=serial.STOPBITS_ONE, timeout=2.0)
    ser.dtr = False
    ser.rts = False
    time.sleep(0.2)
    ser.reset_input_buffer()
    return ser


# ══════════════════════════════════════════════════════════════
# SCAN 1: 0x0B (STATUS) with sub-commands 0x00-0x20
# ══════════════════════════════════════════════════════════════
print("=" * 60)
print("SCAN 1: STATUS (0x0B) with sub-commands")
print("=" * 60)
ser = open_port()
for sub in range(0x00, 0x21):
    resp = ds2_send(ser, 0x12, [0x0B, sub])
    if resp and len(resp) > 3:
        status = resp[2]
        d = extract(resp)
        st = {0xA0:'OK', 0xA1:'BUSY', 0xA2:'INV', 0xB0:'REJ', 0xFF:'BAD'}.get(status, f'0x{status:02X}')
        if status == 0xA0:
            print(f"  0x0B 0x{sub:02X}: {st} ({len(d)}B) {d.hex()[:60]}")
        elif status not in (0xA2, 0xFF):
            print(f"  0x0B 0x{sub:02X}: {st} ({len(resp)}B)")
    time.sleep(0.02)
ser.close()
print()


# ══════════════════════════════════════════════════════════════
# SCAN 2: 0x14 (RAM) with sub-commands 0x00-0x20
# ══════════════════════════════════════════════════════════════
print("=" * 60)
print("SCAN 2: RAM read (0x14) with sub-commands 0x00-0x20")
print("=" * 60)
ser = open_port()
for sub in range(0x00, 0x21):
    resp = ds2_send(ser, 0x12, [0x14, sub])
    if resp and len(resp) > 3:
        status = resp[2]
        d = extract(resp)
        st = {0xA0:'OK', 0xA2:'INV', 0xB0:'REJ', 0xFF:'BAD'}.get(status, f'0x{status:02X}')
        if status == 0xA0:
            print(f"  0x14 0x{sub:02X}: {st} ({len(d):3d}B) first16={d[:16].hex()}")
    time.sleep(0.03)
ser.close()
print()


# ══════════════════════════════════════════════════════════════
# SCAN 3: 2-byte sub-command variants for 0x0B and 0x14
# ══════════════════════════════════════════════════════════════
print("=" * 60)
print("SCAN 3: Extended sub-commands (cmd + 2 bytes)")
print("=" * 60)
ser = open_port()

# 0x0B with 2-byte arguments
for a, b in [(0x00, 0x01), (0x01, 0x00), (0x01, 0x01), (0x02, 0x00), 
             (0x00, 0x10), (0x00, 0xFF), (0x01, 0xFF), (0xFF, 0x00)]:
    resp = ds2_send(ser, 0x12, [0x0B, a, b])
    if resp and len(resp) > 3:
        status = resp[2]
        d = extract(resp)
        if status == 0xA0:
            print(f"  0x0B {a:02X} {b:02X}: OK ({len(d)}B) {d.hex()[:60]}")
        elif status == 0xB0:
            print(f"  0x0B {a:02X} {b:02X}: REJECT")
    time.sleep(0.02)

# 0x14 with offset/length style: [0x14, block, offset_hi, offset_lo, count]
for block, off, cnt in [(0x01, 0x00, 0x7A), (0x01, 0x00, 0xFF),
                         (0x00, 0x00, 0xFF), (0x02, 0x00, 0xFF)]:
    resp = ds2_send(ser, 0x12, [0x14, block, off, cnt])
    if resp and len(resp) > 3:
        status = resp[2]
        d = extract(resp)
        st = {0xA0:'OK', 0xA2:'INV', 0xB0:'REJ', 0xFF:'BAD'}.get(status, f'0x{status:02X}')
        print(f"  0x14 {block:02X} {off:02X} {cnt:02X}: {st} ({len(d)}B) {d.hex()[:40]}")
    time.sleep(0.02)

ser.close()
print()


# ══════════════════════════════════════════════════════════════
# SCAN 4: FULL command+sub sweep: 0x00-0x20, each with 0x00-0x05
# ══════════════════════════════════════════════════════════════
print("=" * 60)
print("SCAN 4: All commands 0x00-0x20 with sub-bytes 0x00-0x05")
print("=" * 60)
ser = open_port()
for cmd in range(0x00, 0x21):
    for sub in range(0x00, 0x06):
        resp = ds2_send(ser, 0x12, [cmd, sub])
        if resp and len(resp) > 3:
            status = resp[2]
            d = extract(resp)
            if status == 0xA0 and len(d) > 1:
                print(f"  0x{cmd:02X} 0x{sub:02X}: OK ({len(d):3d}B) {d.hex()[:50]}")
        time.sleep(0.015)
ser.close()
print()


# ══════════════════════════════════════════════════════════════
# SCAN 5: Read SMG for RPM (SMG knows engine RPM too)
# ══════════════════════════════════════════════════════════════
print("=" * 60)
print("SCAN 5: SMG (0x32) data — does it have RPM?")
print("=" * 60)
ser = open_port()

# SMG status
for sub in range(0x00, 0x06):
    resp = ds2_send(ser, 0x32, [0x0B, sub])
    if resp and len(resp) > 3 and resp[2] == 0xA0:
        d = extract(resp)
        print(f"  SMG STATUS 0x{sub:02X}: OK ({len(d):3d}B) {d.hex()[:60]}")
    time.sleep(0.02)

# SMG analog (already works - gear, gearbox temp etc.)
resp = ds2_send(ser, 0x32, [0x0D])
if resp and resp[2] == 0xA0:
    d = extract(resp)
    print(f"  SMG ANALOG: OK ({len(d):3d}B) {d.hex()[:60]}")

# SMG block reads
for sub in range(0x00, 0x06):
    resp = ds2_send(ser, 0x32, [0x14, sub])
    if resp and len(resp) > 3 and resp[2] == 0xA0:
        d = extract(resp)
        print(f"  SMG RAM 0x{sub:02X}: OK ({len(d):3d}B) {d.hex()[:60]}")
    time.sleep(0.02)

# Check if SMG data has RPM (read 3 times)
print("\n  SMG analog 3 reads (checking for RPM/speed changes):")
for i in range(3):
    resp = ds2_send(ser, 0x32, [0x0D])
    if resp and resp[2] == 0xA0:
        d = extract(resp)
        # Scan for 16-bit values in plausible RPM range
        rpms = []
        for j in range(len(d) - 1):
            v = (d[j] << 8) | d[j+1]
            if 500 < v < 2000:
                rpms.append(f"[{j}:{j+1}]={v}")
        print(f"  Read {i}: {len(d)}B, RPM candidates: {rpms[:5]}")
    time.sleep(1.0)

ser.close()
print()
print("Done.")
