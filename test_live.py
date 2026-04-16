"""Test which DME data bytes actually change between reads (live vs static)."""
import serial
import time

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
    time.sleep(0.05)
    echo = ser.read(len(full))
    time.sleep(0.15)
    ab = ser.read(1)
    if not ab:
        return None
    lb = ser.read(1)
    if not lb:
        return None
    rest = ser.read(lb[0] - 2) if lb[0] > 2 else b''
    return ab + lb + rest

ser = serial.Serial(port=port, baudrate=9600, bytesize=serial.EIGHTBITS,
    parity=serial.PARITY_EVEN, stopbits=serial.STOPBITS_ONE, timeout=1.5)
ser.dtr = False
ser.rts = False
time.sleep(0.15)

print("=== Reading ALL commands 5x each, tracking changes ===")
print()

commands = [
    ([0x14, 0x01], "RAM blk1"),
    ([0x14, 0x00], "RAM blk0"),
    ([0x14, 0x02], "RAM blk2"),
    ([0x14, 0x03], "RAM blk3"),
    ([0x0B],       "STATUS"),
    ([0x0D],       "ANALOG"),
    ([0x0E],       "EXTENDED"),
]

SEP = " -> "

for cmd, label in commands:
    reads = []
    for i in range(5):
        resp = ds2_send(ser, 0x12, cmd)
        if resp and len(resp) > 3:
            data = resp[3:-1] if len(resp) > 4 else resp[3:]
            reads.append(data)
        else:
            reads.append(None)
        time.sleep(0.05)
    
    valid = [r for r in reads if r is not None]
    if len(valid) < 2:
        print(f"{label}: fewer than 2 valid reads ({len(valid)})")
        continue
    
    # Find which bytes changed
    ref = valid[0]
    changed_bytes = set()
    for r in valid[1:]:
        minlen = min(len(ref), len(r))
        for j in range(minlen):
            if ref[j] != r[j]:
                changed_bytes.add(j)
    
    print(f"{label} ({len(ref)}B): ", end="")
    if changed_bytes:
        print(f"CHANGED at offsets {sorted(changed_bytes)}")
        for idx in sorted(changed_bytes):
            vals = [f"{r[idx]:3d}" for r in valid if len(r) > idx]
            print(f"  [{idx:3d}] values: {SEP.join(vals)}")
    else:
        print("ALL IDENTICAL across 5 reads")
    
    # Print first read hex
    print(f"  hex: {valid[0].hex()[:80]}...")
    print()

# Now do a longer test on RAM blk1 specifically - 10 reads over 10 seconds
print("=== RAM blk1: 10 reads over ~20 seconds (watch for temp/RPM drift) ===")
print()
all_reads = []
for i in range(10):
    resp = ds2_send(ser, 0x12, [0x14, 0x01])
    if resp and len(resp) > 3:
        data = resp[3:-1] if len(resp) > 4 else resp[3:]
        all_reads.append(data)
        
        # Show key values each read
        if len(data) > 78:
            rpm = (data[77] << 8) | data[78]
            volt = data[1] / 10.0
            intake = data[2] - 40
            oil = data[9] - 40
            coolant = data[25] * 0.75
            counter = data[0]
            counter2 = data[27]
            print(f"  Read {i}: counter={counter:3d} RPM={rpm:4d} V={volt:.1f} "
                  f"intake={intake}C oil={oil}C coolant={coolant:.1f}C counter2={counter2:3d}")
    else:
        print(f"  Read {i}: no response")
        all_reads.append(None)
    time.sleep(1.5)

# Final diff
valid2 = [r for r in all_reads if r is not None]
if len(valid2) >= 2:
    ref = valid2[0]
    changed = set()
    for r in valid2[1:]:
        for j in range(min(len(ref), len(r))):
            if ref[j] != r[j]:
                changed.add(j)
    print()
    if changed:
        print(f"Bytes that changed over 10 reads: {sorted(changed)}")
    else:
        print("NO BYTES CHANGED over 10 reads — data is STATIC/FROZEN")

ser.close()
print()
print("Done.")
