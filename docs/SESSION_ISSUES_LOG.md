# BMW E46 Reader — Session Issue Log

**Date:** 12 March 2026  
**Vehicle:** BMW E46 M3 (S54 engine, MSS54 DME, SMG II)  
**Interface:** K+DCAN USB cable (FTDI) on `/dev/ttyUSB0`

---

## Issue 1: SMG Gear Parsing Bug

**Symptom:** Gear display showed wrong values or overrode correct neutral reading.  
**Root Cause:** `smg.py` block 0 parser used a lower-nibble heuristic on ASCII status data (`"-N-N"`) which produced false gear reads (e.g. neutral misread as gear 1). This overwrote the correct gear value already read from the analog command (0x0D byte 0).  
**Fix:** Removed the block 0 gear heuristic. Gear position is now read exclusively from `0x0D` analog command byte 0, which is the verified source.  
**File:** `bmw_e46_reader/smg.py`

---

## Issue 2: DME Not Responding (Burst Write Rejection)

**Symptom:** SMG module responded but DME (0x12) returned nothing — no response, no error.  
**Root Cause:** MSS54 DME requires ~10ms inter-byte delay on incoming serial data. The original code wrote entire messages as a burst, which the DME silently ignored.  
**Fix:** Added `INTER_BYTE_TIME = 0.010` (10ms) delay between each byte in `DS2Connection.send()`. Bytes are now written one at a time with `time.sleep(0.010)` between each.  
**File:** `bmw_e46_reader/connection.py`, `bmw_e46_reader/ds2.py`

---

## Issue 3: Frozen Live Data (Wrong DS2 Command)

**Symptom:** Connected to DME successfully, received data, but sensor values (RPM, temps) never changed between rapid polls. Only a counter byte changed.  
**Root Cause:** `0x14 0x01` (RAM block read) returns a **snapshot** of data that only updates between diagnostic sessions, not between individual polls. It was being used as the primary live data source.  
**Fix:** Discovered that `0x0B 0x02` (STATUS group 2) returns 64 bytes of truly **real-time** data that updates every single read. RPM at bytes [12:13] confirmed fluctuating at idle (848–863). Rewrote `engine.py` to use STATUS as the primary live source and RAM only for slow-changing values (temps, voltage).  
**File:** `bmw_e46_reader/engine.py`

---

## Issue 4: DS2 Length Byte Encoding Error

**Symptom:** DME silently rejected packets even with correct inter-byte delay.  
**Root Cause:** The DS2 message length byte was calculated as `payload + 1` but the protocol requires it to be the **total message size**: `payload + 3` (address byte + length byte + payload + checksum byte). Malformed packets were silently dropped by the DME.  
**Fix:** Changed length calculation from `len(payload) + 1` to `len(payload) + 3`.  
**File:** `bmw_e46_reader/ds2.py`

---

## Issue 5: K-Line Echo Not Consumed

**Symptom:** Responses appeared corrupted or misaligned. First bytes of "response" matched the sent command.  
**Root Cause:** K-line is half-duplex — the USB cable echoes back every byte sent. `_receive_response()` was reading the cable echo as if it were the ECU's response, causing all data to be offset/corrupted.  
**Fix:** Added explicit echo read-and-discard step after `write()` and before `_receive_response()`. Reads exactly `len(msg)` bytes of echo and throws them away.  
**File:** `bmw_e46_reader/ds2.py`

---

## Issue 6: DS2 Ack Byte Not Stripped

**Symptom:** Parsed sensor values were wrong — offsets shifted by 1 byte.  
**Root Cause:** DS2 responses from both DME and SMG include a leading `0xA0` acknowledgment byte before the actual data payload. The parsers were reading from byte 0 (the ack) instead of byte 1 (start of real data).  
**Fix:** Added `data[1:]` skip in both `engine.py` and `smg.py` (3 locations in smg.py: analog, block 0, status parsers).  
**Files:** `bmw_e46_reader/engine.py`, `bmw_e46_reader/smg.py`

---

## Issue 7: `connect()` Corrupted Serial Settings

**Symptom:** Intermittent communication failures after `connect()` — worked sometimes, failed other times.  
**Root Cause:** `DS2Connection.connect()` probed alternate parity (ODD) and DTR/RTS settings during auto-detection but did not restore the correct values (EVEN parity, DTR=False, RTS=False) if the probe failed. Subsequent commands used wrong serial settings.  
**Fix:** `connect()` now always restores EVEN parity, DTR=False, RTS=False after any probe attempt, regardless of success/failure.  
**File:** `bmw_e46_reader/ds2.py`

---

## Issue 8: Extremely Slow RPM Refresh Rate (~0.5 Hz)

**Symptom:** Dashboard RPM display did not respond to acceleration. User held RPM above 1000 for 10 seconds with no change on dashboard.  
**Root Cause:** Multiple compounding delays:
1. **Fixed 200ms sleep** before reading ECU response in `ds2.py send()` — unnecessary, ECU responds faster
2. **Fixed 50ms sleep** before reading echo — echo arrives at wire speed (<5ms)
3. **6 serial commands per poll cycle**: STATUS_G2 + STATUS_G3 (fallback) + RAM_BLK1 + SMG_ANALOG + SMG_BLOCK0 + SMG_STATUS
4. **100ms `time.sleep(0.1)`** between poll cycles in dashboard
5. Each command cost ~420ms (50ms echo wait + 200ms response wait + ~100ms TX + ~70ms RX) = **~2.5 seconds per full cycle = 0.4 Hz**

**Fix (applied):**
- Removed fixed `time.sleep(0.20)` and `time.sleep(0.05)` in `ds2.py send()`. Echo is now read with a short serial timeout (50ms). Response is read immediately by `_receive_response()` which has its own timeout handling.
- Reduced `RESPONSE_TIMEOUT` from 1.5s to 0.5s
- Reduced `INTER_MSG_TIME` from 50ms to 10ms
- Added `fast=True` mode to `get_engine_data_ds2()` — sends only STATUS_G2 (1 command instead of 3), skips G3 fallback and RAM block read
- Trimmed SMG reads from 3 commands (analog + block0 + status) to 1 command (analog only — has gear, mode, temp)
- Dashboard `_poll_loop()` now uses fast/slow cycling: RPM-only fast poll 9 out of 10 cycles, full data (temps + SMG) every 10th cycle
- Removed `time.sleep(0.1)` between poll cycles — serial I/O is the natural rate limiter
- Cached last-known temp/SMG values so they're always available for WebSocket broadcast even on fast cycles

**Expected improvement:** From ~0.4 Hz to ~3-5 Hz RPM updates.  
**Files:** `bmw_e46_reader/ds2.py`, `bmw_e46_reader/engine.py`, `bmw_e46_reader/smg.py`, `bmw_e46_reader/dashboard/__init__.py`

---

## Confirmed Live Data Map (MSS54 / S54 Engine)

### STATUS Group 2 (`0x0B 0x02`) — 64 bytes, REAL-TIME
| Offset | Size | Parameter | Idle Value | Notes |
|--------|------|-----------|------------|-------|
| 12–13 | 16-bit | RPM | 848–863 | Direct RPM, confirmed live |
| 26–27 | 16-bit | RPM (filtered) | 838–839 | Averaged/smoothed |
| 6–7 | 16-bit | Engine load | 226–236 | Raw value |
| 54–55 | 16-bit | Lambda bank 1 | 737–1023 | ÷1000 for lambda |
| 56–57 | 16-bit | Lambda bank 2 | 736–1023 | ÷1000 for lambda |

### RAM Block 1 (`0x14 0x01`) — 73 bytes, SNAPSHOT (updates slowly)
| Offset | Size | Parameter | Conversion | Confirmed Value |
|--------|------|-----------|------------|-----------------|
| 1 | 8-bit | Battery voltage | raw ÷ 10.0 | 14.3V |
| 2 | 8-bit | Intake air temp | raw − 40 | 28°C |
| 9 | 8-bit | Oil temp | raw − 40 | 96°C |
| 25 | 8-bit | Coolant temp | raw × 0.75 | 74.2°C |

### SMG Analog (`0x0D`) — 72 bytes
| Offset | Size | Parameter | Conversion | Confirmed Value |
|--------|------|-----------|------------|-----------------|
| 0 | 8-bit | Gear | Direct (0=N, 1-6, 7=R) | 0 (Neutral) |
| 45 | 8-bit | Shift mode | Direct (1-6=S1-S6, 0=A) | 3 (S3) |
| 46 | 8-bit | Gearbox temp | raw − 40 | 87°C |

---

## Key Protocol Learnings

- **DS2 is NOT ISO 9141-2** — no 5-baud init, messages sent directly at 9600 8E1
- **MSS54 requires 10ms inter-byte delay** — burst writes are silently ignored
- **K-line echo must be consumed** — half-duplex bus echoes all TX bytes
- **`0x0B` STATUS requires a group sub-command** — bare `0x0B` gets rejected; use `0x0B 0x02` for live data
- **`0x14` RAM is a snapshot** — not suitable for real-time polling; use STATUS instead
- **Response includes 0xA0 ack byte** — must skip data[0] before parsing sensor bytes
- **Length byte = total message size** — not just payload length
