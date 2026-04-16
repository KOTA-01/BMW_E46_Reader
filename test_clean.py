"""Clean test: fresh connection, longer waits between reads, track all changing bytes.
Also try KWP2000 fast init for standard OBD-II PIDs."""
import serial
import time

port = '/dev/ttyUSB0'
DELAY = 0.010

def xor_cs(data):
    r = 0
    for b in data: r ^= b
    return r

def ds2_send(ser, addr, cmd, delay=DELAY, read_timeout=1.5):
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
    
    # Read echo - exact same number of bytes we sent
    old_timeout = ser.timeout
    ser.timeout = read_timeout
    echo = ser.read(len(full))
    
    # Wait for response
    time.sleep(0.20)
    
    # Read response
    ab = ser.read(1)
    if not ab:
        ser.timeout = old_timeout
        return None
    lb = ser.read(1)
    if not lb:
        ser.timeout = old_timeout
        return None
    rlen = lb[0] - 2
    if rlen > 0:
        rest = ser.read(rlen)
    else:
        rest = b''
    ser.timeout = old_timeout
    return ab + lb + rest

def extract(resp):
    if resp and len(resp) > 4:
        return resp[3:-1]
    elif resp and len(resp) > 3:
        return resp[3:]
    return b''

def open_port():
    ser = serial.Serial(port=port, baudrate=9600, bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_EVEN, stopbits=serial.STOPBITS_ONE, timeout=2.0)
    ser.dtr = False
    ser.rts = False
    time.sleep(0.2)
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    return ser


# ══════════════════════════════════════════════════════════════
# PART 1: Fresh connection, 10 reads of 0x14 0x01, 2s apart
# Check consistency and find ANY bytes that change
# ══════════════════════════════════════════════════════════════
print("=" * 60)
print("PART 1: Fresh connection, 10 reads of RAM blk1, 2s gaps")
print("=" * 60)
ser = open_port()
all_reads = []
for i in range(10):
    resp = ds2_send(ser, 0x12, [0x14, 0x01])
    if resp:
        full_hex = resp.hex()
        d = extract(resp)
        all_reads.append(d)
        print(f"  Read {i}: resp_len={len(resp):3d}B data_len={len(d):3d}B "
              f"status=0x{resp[2]:02X} first8={d[:8].hex() if len(d)>=8 else d.hex()}")
    else:
        all_reads.append(None)
        print(f"  Read {i}: NO RESPONSE")
    time.sleep(2.0)

valid = [r for r in all_reads if r is not None]
if len(valid) >= 2:
    ref = valid[0]
    changed = {}
    for ridx, r in enumerate(valid[1:], 1):
        for j in range(min(len(ref), len(r))):
            if ref[j] != r[j]:
                if j not in changed:
                    changed[j] = []
                changed[j].append((ridx, r[j]))
    
    if changed:
        print(f"\n  CHANGING bytes: {sorted(changed.keys())}")
        for off in sorted(changed.keys()):
            base_val = ref[off]
            all_vals = [f"{base_val:3d}"] + [f"{v:3d}" for _, v in changed[off]]
            print(f"    offset[{off:3d}]: {' '.join(all_vals)}")
    else:
        print("\n  ALL BYTES IDENTICAL across 10 reads")
        
    # Show parsed sensor values from first valid read
    d = valid[0]
    print(f"\n  Parsed from first read ({len(d)}B):")
    print(f"    byte[0] (counter): {d[0]}")
    print(f"    byte[1] (voltage): {d[1]} -> {d[1]/10.0:.1f}V")
    print(f"    byte[2] (intake):  {d[2]} -> {d[2]-40}°C")
    print(f"    byte[9] (oil):     {d[9]} -> {d[9]-40}°C")
    if len(d) > 25:
        print(f"    byte[25] (coolant): {d[25]} -> {d[25]*0.75:.1f}°C")
    if len(d) > 78:
        rpm = (d[77] << 8) | d[78]
        print(f"    byte[77:78] (RPM): {d[77]:02x}{d[78]:02x} -> {rpm}")
    else:
        print(f"    byte[77:78] (RPM): data too short ({len(d)}B)")

ser.close()
print()


# ══════════════════════════════════════════════════════════════
# PART 2: Fresh connection each read (close + reopen + 3s wait)
# ══════════════════════════════════════════════════════════════
print("=" * 60)
print("PART 2: Fully fresh connection each read, 3s between")
print("=" * 60)
all_reads2 = []
for i in range(5):
    ser = open_port()
    time.sleep(0.5)
    resp = ds2_send(ser, 0x12, [0x14, 0x01])
    if resp:
        d = extract(resp)
        all_reads2.append(d)
        print(f"  Read {i}: {len(resp)}B resp, {len(d)}B data, "
              f"first12={d[:12].hex() if len(d)>=12 else d.hex()}")
    else:
        all_reads2.append(None) 
        print(f"  Read {i}: NO RESPONSE")
    ser.close()
    time.sleep(3.0)

valid2 = [r for r in all_reads2 if r is not None]
if len(valid2) >= 2:
    ref = valid2[0]
    changed2 = set()
    for r in valid2[1:]:
        for j in range(min(len(ref), len(r))):
            if ref[j] != r[j]:
                changed2.add(j)
    if changed2:
        print(f"\n  Bytes that changed: {sorted(changed2)}")
        for off in sorted(changed2):
            vals = [f"{r[off]:3d}" for r in valid2 if len(r) > off]
            sep = " -> "
            print(f"    [{off:3d}]: {sep.join(vals)}")
    else:
        print("\n  ALL IDENTICAL even with full reconnection")
print()


# ══════════════════════════════════════════════════════════════
# PART 3: KWP2000 Fast Init for OBD-II PIDs
# ══════════════════════════════════════════════════════════════
print("=" * 60)
print("PART 3: KWP2000 fast init at 10400 baud")
print("=" * 60)

def kwp_fast_init(baudrate=10400):
    """KWP2000 fast initialization - 25ms low + 25ms high wakeup pattern."""
    ser = serial.Serial(port=port, baudrate=baudrate, bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, timeout=2.0)
    ser.dtr = False
    ser.rts = False
    time.sleep(0.3)
    ser.reset_input_buffer()
    
    # Fast init: 25ms TiniL (break), 25ms TiniH (mark)
    ser.break_condition = True
    time.sleep(0.025)
    ser.break_condition = False
    time.sleep(0.025)
    
    # Send StartCommunication request
    # Format: [Format/Length] [Target] [Source] [Service] [Checksum]
    # C1 = Format byte (physical addressing, 1 data byte follows)
    # 33 = Target (OBD gateway / functional)
    # F1 = Source (tester)
    # 81 = StartCommunication service
    msg = bytes([0xC1, 0x33, 0xF1, 0x81])
    cs = sum(msg) & 0xFF
    msg = msg + bytes([cs])
    
    ser.write(msg)
    ser.flush()
    time.sleep(0.3)
    
    resp = ser.read(20)
    if resp:
        print(f"  Fast init response at {baudrate}: {resp.hex()}")
        # Check if it's just echo or actual response
        if len(resp) > len(msg):
            print(f"  Echo({len(msg)}B) + Response({len(resp)-len(msg)}B)")
            echo_part = resp[:len(msg)]
            resp_part = resp[len(msg):]
            print(f"  Echo: {echo_part.hex()}")
            print(f"  Resp: {resp_part.hex()}")
    else:
        print(f"  No response at {baudrate}")
    
    return ser, resp

# Try fast init at different baud rates
for baud in [10400, 9600, 4800]:
    ser, resp = kwp_fast_init(baud)
    
    if resp and len(resp) > 5:
        # Try sending an OBD-II PID request
        print(f"  Trying RPM PID at {baud} baud...")
        time.sleep(0.1)
        ser.reset_input_buffer()
        
        # KWP2000 format for OBD-II service $01 PID $0C
        pid_msg = bytes([0xC2, 0x33, 0xF1, 0x01, 0x0C])
        cs = sum(pid_msg) & 0xFF
        pid_msg = pid_msg + bytes([cs])
        ser.write(pid_msg)
        ser.flush()
        time.sleep(0.5)
        pid_resp = ser.read(30)
        if pid_resp:
            print(f"  PID response: {pid_resp.hex()}")
    
    ser.close()
    time.sleep(1.0)

print()


# ══════════════════════════════════════════════════════════════  
# PART 4: Try DS2 at 10400 baud (some MSS54 variants use this)
# ══════════════════════════════════════════════════════════════
print("=" * 60)
print("PART 4: DS2 at alternate baud rates")
print("=" * 60)

for baud in [10400, 4800, 19200]:
    try:
        ser = serial.Serial(port=port, baudrate=baud, bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_EVEN, stopbits=serial.STOPBITS_ONE, timeout=1.5)
        ser.dtr = False
        ser.rts = False
        time.sleep(0.2)
        ser.reset_input_buffer()
        
        resp = ds2_send(ser, 0x12, [0x00], delay=DELAY)  # IDENT
        if resp and len(resp) > 3 and resp[2] == 0xA0:
            print(f"  {baud} baud: IDENT OK! ({len(resp)}B)")
            # Try RAM read at this baud
            resp2 = ds2_send(ser, 0x12, [0x14, 0x01])
            if resp2:
                d = extract(resp2)
                print(f"    RAM blk1: {len(d)}B, status=0x{resp2[2]:02X}")
        else:
            indicator = resp.hex()[:20] if resp else "no response"
            print(f"  {baud} baud: {indicator}")
        ser.close()
    except Exception as e:
        print(f"  {baud} baud: error - {e}")
    time.sleep(0.5)

print()
print("Done.")
