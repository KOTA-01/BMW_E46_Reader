"""Rapid poll of STATUS groups to confirm real-time updates and identify RPM/sensors.
Read groups 0x02, 0x03, 0x06 ten times each and track all changing values."""
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

def analyze_group(ser, group, num_reads=10, interval=0.5):
    """Read a STATUS group multiple times and show which bytes change."""
    print(f"\n--- STATUS GROUP 0x{group:02X} ({num_reads} reads, {interval}s apart) ---")
    
    reads = []
    for i in range(num_reads):
        resp = ds2_send(ser, 0x12, [0x0B, group])
        if resp and len(resp) > 3 and resp[2] == 0xA0:
            d = extract(resp)
            reads.append(d)
        else:
            reads.append(None)
        time.sleep(interval)
    
    valid = [r for r in reads if r is not None]
    if len(valid) < 2:
        print(f"  Only {len(valid)} valid reads")
        return
    
    print(f"  {len(valid)} valid reads, {len(valid[0])} bytes each")
    
    # Find changing bytes
    ref = valid[0]
    changing = {}
    for ridx, r in enumerate(valid):
        for j in range(min(len(ref), len(r))):
            if ref[j] != r[j]:
                if j not in changing:
                    changing[j] = set()
                changing[j].add(r[j])
                changing[j].add(ref[j])
    
    if not changing:
        print("  ALL STATIC — no bytes changed")
        # Still show 16-bit pairs for analysis
        print(f"  16-bit pairs:")
        for j in range(0, len(ref) - 1, 2):
            v = (ref[j] << 8) | ref[j+1]
            print(f"    [{j:2d}:{j+1:2d}] = 0x{v:04X} = {v:5d}", end="")
            if 500 < v < 2000:
                print(f"  <-- RPM range?", end="")
            if 40 <= v <= 150:
                print(f"  <-- temp range?", end="")
            print()
        return
    
    print(f"  LIVE bytes at offsets: {sorted(changing.keys())}")
    print()
    
    # Show ALL 16-bit pairs with values across reads
    print(f"  16-bit pair analysis (reads 0..{len(valid)-1}):")
    sep = "  "
    for j in range(0, min(len(ref), len(valid[-1])) - 1, 2):
        vals = []
        for r in valid:
            if len(r) > j + 1:
                v = (r[j] << 8) | r[j+1]
                vals.append(v)
        
        is_changing = (j in changing) or (j+1 in changing)
        vmin, vmax = min(vals), max(vals)
        delta = vmax - vmin
        
        marker = ""
        if is_changing:
            marker = " [LIVE]"
            if 400 < vmin < 2000 and 400 < vmax < 2000 and delta < 200:
                marker = " [LIVE] <== RPM?"
            elif 0 < delta < 30:
                marker = " [LIVE] <== sensor?"
        elif 500 < vmin < 2000:
            marker = "  (RPM range but static)"
        
        val_strs = [f"{v:5d}" for v in vals[:5]]  # Show first 5
        extra = f"...+{len(vals)-5}" if len(vals) > 5 else ""
        print(f"    [{j:2d}:{j+1:2d}] {sep.join(val_strs)}{extra}{marker}")


# ══════════════════════════════════════════════════════════════
ser = open_port()

# Analyze each working STATUS group
for group in [0x02, 0x03, 0x04, 0x05, 0x06, 0x13, 0x15, 0x16]:
    analyze_group(ser, group, num_reads=8, interval=0.8)

# Also check SMG STATUS groups
print("\n\n=== SMG STATUS GROUPS ===")
for group in [0x03, 0x05]:
    print(f"\n--- SMG STATUS GROUP 0x{group:02X} ---")
    reads = []
    for i in range(5):
        resp = ds2_send(ser, 0x32, [0x0B, group])
        if resp and len(resp) > 3 and resp[2] == 0xA0:
            d = extract(resp)
            reads.append(d)
        time.sleep(0.8)
    
    valid = [r for r in reads if r is not None]
    if len(valid) >= 2:
        ref = valid[0]
        changing = set()
        for r in valid[1:]:
            for j in range(min(len(ref), len(r))):
                if ref[j] != r[j]:
                    changing.add(j)
        
        print(f"  {len(valid[0])}B, changing bytes: {sorted(changing) if changing else 'NONE'}")
        
        # Show interesting 16-bit values
        for j in range(0, min(16, len(ref) - 1), 2):
            vals = [(r[j] << 8) | r[j+1] for r in valid if len(r) > j + 1]
            is_live = j in changing or (j+1) in changing
            vrange = f"{min(vals)}-{max(vals)}" if len(vals) > 1 else str(vals[0])
            tag = " [LIVE]" if is_live else ""
            print(f"    [{j:2d}:{j+1:2d}] = {vrange}{tag}")

ser.close()
print("\nDone.")
