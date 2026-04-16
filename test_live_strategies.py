"""Find a way to get TRULY live data from MSS54.
Strategy:
  A) Try 0x05 (reset/clear) before each 0x14 to force snapshot refresh
  B) Try OBD-II PIDs via ISO 9141-2 5-baud init to gateway 0x33
  C) Try 0x04 (ReadDataByBlock) and check if it updates
  D) Try toggling DTR between reads
"""
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
    if resp and len(resp) > 4:
        return resp[3:-1]
    elif resp and len(resp) > 3:
        return resp[3:]
    return b''

def open_port():
    ser = serial.Serial(port=port, baudrate=9600, bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_EVEN, stopbits=serial.STOPBITS_ONE, timeout=1.5)
    ser.dtr = False
    ser.rts = False
    time.sleep(0.1)
    ser.reset_input_buffer()
    return ser

def show_key_values(d, label=""):
    if len(d) > 78:
        rpm = (d[77] << 8) | d[78]
        print(f"  {label}ctr={d[0]:3d} RPM={rpm:4d} V={d[1]/10:.1f} "
              f"intake={d[2]-40}C oil={d[9]-40}C coolant={d[25]*0.75:.1f}C")
    elif len(d) > 2:
        print(f"  {label}{len(d)}B: {d.hex()[:60]}")
    else:
        print(f"  {label}(empty)")


# ══════════════════════════════════════════════════════════════
# TEST A: Send 0x05 (clear/reset) before each 0x14 read
# ══════════════════════════════════════════════════════════════
print("=" * 60)
print("TEST A: Send reset cmd (0x05) before each RAM read")
print("=" * 60)
ser = open_port()
for i in range(5):
    ds2_send(ser, 0x12, [0x05])   # clear/reset
    time.sleep(0.1)
    resp = ds2_send(ser, 0x12, [0x14, 0x01])
    d = extract(resp)
    show_key_values(d, f"Read {i}: ")
    time.sleep(1.0)
ser.close()
print()


# ══════════════════════════════════════════════════════════════
# TEST B: Send IDENT between reads (re-announce ourselves)
# ══════════════════════════════════════════════════════════════
print("=" * 60)
print("TEST B: IDENT (0x00) before each RAM read")
print("=" * 60)
ser = open_port()
for i in range(5):
    ds2_send(ser, 0x12, [0x00])   # ident
    time.sleep(0.1)
    resp = ds2_send(ser, 0x12, [0x14, 0x01])
    d = extract(resp)
    show_key_values(d, f"Read {i}: ")
    time.sleep(1.0)
ser.close()
print()


# ══════════════════════════════════════════════════════════════
# TEST C: Toggle DTR between reads
# ══════════════════════════════════════════════════════════════
print("=" * 60)
print("TEST C: Toggle DTR/RTS between reads")
print("=" * 60)
ser = open_port()
for i in range(5):
    ser.dtr = True
    time.sleep(0.05)
    ser.dtr = False
    time.sleep(0.1)
    ser.reset_input_buffer()
    resp = ds2_send(ser, 0x12, [0x14, 0x01])
    d = extract(resp)
    show_key_values(d, f"Read {i}: ")
    time.sleep(1.0)
ser.close()
print()


# ══════════════════════════════════════════════════════════════
# TEST D: Send 0x0A (which returned OK) between reads
# ══════════════════════════════════════════════════════════════
print("=" * 60)
print("TEST D: Send 0x0A between reads")
print("=" * 60)
ser = open_port()
for i in range(5):
    ds2_send(ser, 0x12, [0x0A])   # mystery OK cmd
    time.sleep(0.1)
    resp = ds2_send(ser, 0x12, [0x14, 0x01])
    d = extract(resp)
    show_key_values(d, f"Read {i}: ")
    time.sleep(1.0)
ser.close()
print()


# ══════════════════════════════════════════════════════════════
# TEST E: Read 0x04 blocks multiple times, check for changes
# ══════════════════════════════════════════════════════════════
print("=" * 60)
print("TEST E: ReadDataByBlock (0x04) — do these update?")
print("=" * 60)
ser = open_port()
for block in [0x00, 0x01, 0x02]:
    reads = []
    for i in range(3):
        resp = ds2_send(ser, 0x12, [0x04, block])
        d = extract(resp)
        reads.append(d)
        time.sleep(1.0)
    changed = any(reads[0] != r for r in reads[1:] if r)
    status = "CHANGED" if changed else "STATIC"
    print(f"  Block 0x{block:02X}: {len(reads[0])}B => {status}")
    if changed:
        for j, r in enumerate(reads):
            print(f"    Read {j}: {r.hex()[:60]}")
ser.close()
print()


# ══════════════════════════════════════════════════════════════
# TEST F: ISO 9141-2 5-baud init (OBD-II standard approach)
# ══════════════════════════════════════════════════════════════
print("=" * 60)
print("TEST F: ISO 9141-2 5-baud init for OBD-II PIDs")
print("=" * 60)

def iso_5baud_init(ser, target_addr=0x33):
    """
    Send ISO 9141-2 5-baud initialization sequence.
    Sends target address at 5 baud, then waits for sync patterns.
    """
    # Close and reopen at special settings for 5-baud init
    ser.close()
    time.sleep(0.5)
    
    # Open at 5 baud for address byte - use break-based approach
    # Actually, we simulate 5 baud by bit-banging with break signals
    ser = serial.Serial(port=port, baudrate=9600, bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, timeout=3.0)
    ser.dtr = False
    ser.rts = False
    time.sleep(0.3)
    
    # 5-baud = 200ms per bit. 10 bits total (start + 8 data + stop)
    # We drive the K-line low for start bit, then each data bit
    BIT_TIME = 0.200  # 200ms per bit at 5 baud
    
    # Start bit (low)
    ser.break_condition = True
    time.sleep(BIT_TIME)
    
    # Send address byte LSB first
    for bit_pos in range(8):
        bit = (target_addr >> bit_pos) & 1
        if bit:
            ser.break_condition = False  # High = mark
        else:
            ser.break_condition = True   # Low = space
        time.sleep(BIT_TIME)
    
    # Stop bit (high)
    ser.break_condition = False
    time.sleep(BIT_TIME)
    
    # Now switch to 10400 baud and wait for response
    ser.close()
    time.sleep(0.1)
    
    ser = serial.Serial(port=port, baudrate=10400, bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, timeout=3.0)
    ser.dtr = False
    ser.rts = False
    
    # Wait for sync byte 0x55
    time.sleep(0.3)
    sync = ser.read(1)
    if sync and sync[0] == 0x55:
        print(f"  Got sync byte: 0x{sync[0]:02X}")
    elif sync:
        print(f"  Unexpected byte: 0x{sync[0]:02X}")
    else:
        print("  No sync byte received")
        return None, ser
    
    # Read key bytes
    kb1 = ser.read(1)
    kb2 = ser.read(1)
    if kb1 and kb2:
        print(f"  Key bytes: 0x{kb1[0]:02X} 0x{kb2[0]:02X}")
        # Send inverted key byte 2 back
        time.sleep(0.025)  # 25ms W4 timing
        inv_kb2 = (~kb2[0]) & 0xFF
        ser.write(bytes([inv_kb2]))
        time.sleep(0.025)
        
        # Read ECU address confirmation
        addr_conf = ser.read(1)
        if addr_conf:
            print(f"  ECU confirmed: 0x{addr_conf[0]:02X}")
            return True, ser
        else:
            print("  No ECU address confirmation")
    else:
        print("  No key bytes received")
    
    return None, ser

# Try slow init
ser = open_port()
result, ser = iso_5baud_init(ser, 0x33)

if result:
    print("  ISO 9141-2 init SUCCESS! Trying OBD-II PIDs...")
    
    # Send Mode 01 PID 0x0C (RPM)
    # OBD format: [0x68, 0x6A, 0x33, 0x01, 0x0C, checksum]
    # Or simple: header + mode + pid + checksum
    for pid_name, pid_byte in [("RPM", 0x0C), ("Speed", 0x0D), ("Coolant", 0x05), 
                                 ("Load", 0x04), ("Throttle", 0x11)]:
        msg = bytes([0x68, 0x6A, 0xF1, 0x01, pid_byte])
        cs = sum(msg) & 0xFF
        msg = msg + bytes([cs])
        ser.write(msg)
        time.sleep(0.3)
        resp = ser.read(20)
        if resp:
            print(f"  {pid_name} (PID 0x{pid_byte:02X}): {resp.hex()}")
        else:
            print(f"  {pid_name}: no response")
else:
    print("  ISO 9141-2 init failed — trying alternate baud/address...")
    ser.close()
    
    # Try direct OBD at 10400 baud without init (some gateways)
    ser = serial.Serial(port=port, baudrate=10400, bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, timeout=2.0)
    ser.dtr = False
    ser.rts = False
    time.sleep(0.2)
    ser.reset_input_buffer()
    
    # Try sending OBD request directly
    msg = bytes([0x68, 0x6A, 0xF1, 0x01, 0x0C])
    cs = sum(msg) & 0xFF
    msg = msg + bytes([cs])
    ser.write(msg)
    time.sleep(0.5)
    resp = ser.read(20)
    if resp:
        print(f"  Direct OBD response: {resp.hex()}")
    else:
        print("  No response at 10400 baud either")

ser.close()
print()
print("Done.")
