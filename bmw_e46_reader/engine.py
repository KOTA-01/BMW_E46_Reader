"""
BMW E46 Engine Data Module
~~~~~~~~~~~~~~~~~~~~~~~~~~

Hybrid approach: reads engine parameters via BOTH DS2 protocol (BMW-specific)
and standard OBD-II PIDs (via ISO 9141-2 gateway) to get the most complete
data set possible.

DS2 Protocol commands for DME (0x12):
    0x00 - ECU Identification (part number, SW version)
    0x04 + block - Read block data (stored/static)
    0x0B - Status data (may contain real-time RPM, speed, load)
    0x0D - Read analog data (stored calibration values)
    0x14 - Read RAM data (LIVE sensor values - temps, voltage)
    0x07 - Read fault codes

OBD-II PIDs via gateway (ISO 9141-2 init to 0x33):
    Mode 01 PID 0x0C - Engine RPM (real-time tachometer)
    Mode 01 PID 0x0D - Vehicle Speed
    Mode 01 PID 0x04 - Engine Load
    Mode 01 PID 0x11 - Throttle Position
    Mode 01 PID 0x10 - MAF
    Mode 01 PID 0x0E - Timing Advance
    Mode 01 PID 0x06-0x09 - Fuel Trims

Strategy:
    1. DS2 0x0B (status) - try for RPM, speed, load, throttle
    2. DS2 0x14 (RAM) - confirmed for temps, voltage
    3. DS2 0x0D (analog) - try for additional BMW-specific data
    4. OBD-II PIDs - fallback/supplement for anything DS2 missed
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Tuple, TYPE_CHECKING, Union
from datetime import datetime
from loguru import logger

from .config import ECU_ADDRESSES, STANDARD_PIDS

if TYPE_CHECKING:
    from .ds2 import DS2Connection
    from .connection import E46Connection


@dataclass
class EngineData:
    """
    Container for engine sensor data.
    
    All temperatures are in Celsius, pressures in kPa unless noted.
    """
    timestamp: datetime = field(default_factory=datetime.now)
    
    # Basic engine parameters
    rpm: Optional[float] = None
    speed: Optional[float] = None  # km/h
    engine_load: Optional[float] = None  # %
    throttle_position: Optional[float] = None  # %
    
    # Temperatures
    coolant_temp: Optional[float] = None  # °C
    oil_temp: Optional[float] = None  # °C
    intake_temp: Optional[float] = None  # °C
    
    # Fuel system
    maf: Optional[float] = None  # Mass Air Flow (g/s)
    intake_pressure: Optional[float] = None  # kPa
    short_fuel_trim_1: Optional[float] = None  # %
    long_fuel_trim_1: Optional[float] = None  # %
    short_fuel_trim_2: Optional[float] = None  # %
    long_fuel_trim_2: Optional[float] = None  # %
    
    # Ignition
    timing_advance: Optional[float] = None  # degrees
    
    # Electrical
    battery_voltage: Optional[float] = None  # V
    
    # BMW-specific (MSS54)
    vanos_intake: Optional[float] = None  # degrees
    vanos_exhaust: Optional[float] = None  # degrees
    knock_sensor_1: Optional[float] = None  # degrees retard
    knock_sensor_2: Optional[float] = None  # degrees retard
    lambda_sensor_1: Optional[float] = None  # lambda
    lambda_sensor_2: Optional[float] = None  # lambda
    fuel_injector_time: Optional[float] = None  # ms
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/export"""
        return {
            'timestamp': self.timestamp.isoformat(),
            'rpm': self.rpm,
            'speed': self.speed,
            'engine_load': self.engine_load,
            'throttle_position': self.throttle_position,
            'coolant_temp': self.coolant_temp,
            'oil_temp': self.oil_temp,
            'intake_temp': self.intake_temp,
            'maf': self.maf,
            'intake_pressure': self.intake_pressure,
            'short_fuel_trim_1': self.short_fuel_trim_1,
            'long_fuel_trim_1': self.long_fuel_trim_1,
            'short_fuel_trim_2': self.short_fuel_trim_2,
            'long_fuel_trim_2': self.long_fuel_trim_2,
            'timing_advance': self.timing_advance,
            'battery_voltage': self.battery_voltage,
            'vanos_intake': self.vanos_intake,
            'vanos_exhaust': self.vanos_exhaust,
            'knock_sensor_1': self.knock_sensor_1,
            'knock_sensor_2': self.knock_sensor_2,
            'lambda_sensor_1': self.lambda_sensor_1,
            'lambda_sensor_2': self.lambda_sensor_2,
            'fuel_injector_time': self.fuel_injector_time,
        }
    
    def __str__(self) -> str:
        """Human-readable string representation"""
        lines = [
            f"Engine Data @ {self.timestamp.strftime('%H:%M:%S.%f')[:-3]}",
            "-" * 40,
        ]
        
        if self.rpm is not None:
            lines.append(f"RPM:              {self.rpm:.0f}")
        if self.speed is not None:
            lines.append(f"Speed:            {self.speed:.0f} km/h")
        if self.engine_load is not None:
            lines.append(f"Engine Load:      {self.engine_load:.1f}%")
        if self.throttle_position is not None:
            lines.append(f"Throttle:         {self.throttle_position:.1f}%")
        if self.coolant_temp is not None:
            lines.append(f"Coolant Temp:     {self.coolant_temp:.1f}°C")
        if self.oil_temp is not None:
            lines.append(f"Oil Temp:         {self.oil_temp:.1f}°C")
        if self.intake_temp is not None:
            lines.append(f"Intake Temp:      {self.intake_temp:.1f}°C")
        if self.maf is not None:
            lines.append(f"MAF:              {self.maf:.2f} g/s")
        if self.battery_voltage is not None:
            lines.append(f"Battery:          {self.battery_voltage:.2f}V")
        if self.timing_advance is not None:
            lines.append(f"Timing Advance:   {self.timing_advance:.1f}°")
        if self.vanos_intake is not None:
            lines.append(f"VANOS Intake:     {self.vanos_intake:.1f}°")
        if self.vanos_exhaust is not None:
            lines.append(f"VANOS Exhaust:    {self.vanos_exhaust:.1f}°")
            
        return "\n".join(lines)


def _parse_pid_value(response: bytes, formula: str) -> Optional[float]:
    """
    Parse raw PID response bytes using formula.
    
    Args:
        response: Raw response bytes
        formula: Formula string (uses A, B, C, D for bytes)
        
    Returns:
        Calculated value or None
    """
    if not response or len(response) < 1:
        return None
    
    try:
        # Set up byte variables
        A = response[0] if len(response) > 0 else 0
        B = response[1] if len(response) > 1 else 0
        C = response[2] if len(response) > 2 else 0
        D = response[3] if len(response) > 3 else 0
        
        # Evaluate formula
        result = eval(formula)
        return float(result)
    except Exception as e:
        logger.warning(f"Failed to parse value: {e}")
        return None


# DS2 command constants for DME
DS2_CMD_IDENT = 0x00      # ECU identification
DS2_CMD_BLOCK = 0x04      # Block read (stored data)
DS2_CMD_FAULTS = 0x07     # Read fault codes
DS2_CMD_STATUS = 0x0B     # Status data — REQUIRES group sub-command!
DS2_CMD_ANALOG = 0x0D     # Analog data (static/calibration)
DS2_CMD_EXT = 0x0E        # Extended data
DS2_CMD_RAM = 0x14        # RAM data - snapshot values (temps, voltage)

# ── MSS54 STATUS group 0x02: REAL-TIME live data (updates every read) ──
# Command: 0x0B 0x02 → 64 bytes of live sensor data
# CONFIRMED live on MSS54 (S54 engine) by polling during idle.
MSS54_STATUS_GROUP2 = {
    'rpm':           (12, 13),  # 16-bit big-endian, direct RPM. 849-851 at idle. CONFIRMED LIVE.
    'rpm_filtered':  (26, 27),  # 16-bit, filtered/averaged RPM. 838-839 at idle.
    'rpm_target':    (34, 35),  # 16-bit, target RPM or duplicate. ~850 at idle.
    'oil_temp_raw':  (18, 19),  # 16-bit, 139-140 at idle -> raw oil sensor
    'coolant_raw':   (16, 17),  # 16-bit, 82 at idle -> raw coolant sensor
    'lambda_1':      (54, 55),  # 16-bit, 737-740 at idle -> lambda bank 1
    'lambda_2':      (56, 57),  # 16-bit, 736-739 at idle -> lambda bank 2
    'load_raw':      (6, 7),    # 16-bit, 226-236 at idle -> engine load
}

# ── MSS54 STATUS group 0x03: additional live data ──
# Command: 0x0B 0x03 → 35 bytes
MSS54_STATUS_GROUP3 = {
    'rpm':           (0, 1),    # 16-bit RPM, 858-902 at idle (matches group 2)
    'rpm_target':    (2, 3),    # 16-bit target idle RPM = 870 (constant)
    'sensor_a':      (4, 5),    # 78-81 at idle (oil-related?)
    'sensor_b':      (6, 7),    # 993-1032 at idle (fuel-related?)
    'sensor_c':      (8, 9),    # 204-212 at idle
}

# ── MSS54 RAM block 1 (0x14 0x01): snapshot data (updates slowly) ──
# This data updates between sessions but NOT between rapid polls.
# Good for temps and voltage which don't need 10Hz refresh.
MSS54_RAM_MAP = {
    'counter': 0,          # Counter/status byte
    'voltage': 1,          # Battery voltage: raw / 10.0 -> 14.3V CONFIRMED
    'intake_temp': 2,      # Intake air temp: raw - 40 -> 28°C CONFIRMED
    'intake_temp_2': 3,    # Intake temp mirror (same value)
    'oil_temp': 9,         # Oil temperature: raw - 40 -> 94°C CONFIRMED
    'coolant_temp': 25,    # Coolant temp: raw * 0.75 -> 74°C CONFIRMED
    'live_counter': 27,    # Timing counter (changes each read)
}


def _safe_ds2_send(connection: 'DS2Connection', address: int, command: int,
                    data: bytes = b'', label: str = '') -> Optional[Any]:
    """
    Safely send a DS2 command with error handling.
    
    Returns the response object or None on any error.
    """
    try:
        response = connection.send(address, command, data)
        if response and response.valid:
            logger.debug(f"DS2 {label or f'0x{command:02X}'}: "
                         f"{len(response.data)} bytes -> {response.data.hex()}")
            return response
        elif response:
            logger.debug(f"DS2 {label or f'0x{command:02X}'}: "
                         f"invalid response (status 0x{response.status:02X})")
        else:
            logger.debug(f"DS2 {label or f'0x{command:02X}'}: no response")
    except Exception as e:
        logger.warning(f"DS2 {label or f'0x{command:02X}'} error: {e}")
    return None


def _read16(raw: bytes, hi: int, lo: int) -> int:
    """Read a 16-bit big-endian value from raw bytes at given indices."""
    return (raw[hi] << 8) | raw[lo]


def get_engine_data_ds2(connection: 'DS2Connection', fast: bool = False) -> EngineData:
    """
    Read engine parameters from MSS54 DME via DS2 protocol.
    
    Uses two complementary commands:
      1. 0x0B 0x02 (STATUS group 2) — REAL-TIME RPM, load, lambda
         Updates every single read at full polling speed.
      2. 0x14 0x01 (RAM block 1) — temps, voltage (snapshot)
         Updates slowly but contains confirmed temp/voltage data.
    
    Args:
        connection: Active DS2Connection
        fast: If True, only read STATUS_G2 for RPM (skip temps/voltage).
              Use for high-frequency RPM polling.
        
    Returns:
        EngineData object with current values
    """
    data = EngineData()
    
    # ── 1. STATUS group 0x02: REAL-TIME RPM + live data ──
    # This is the primary live data source. Updates every single read.
    try:
        response = _safe_ds2_send(connection, 0x12, DS2_CMD_STATUS,
                                   bytes([0x02]), label='STATUS_G2')
        if response and len(response.data) >= 28:
            # DS2 response.data includes leading ack byte (0xA0) — skip it.
            # The actual sensor payload starts at data[1].
            raw = response.data[1:]
            
            # RPM at bytes [12:13] — direct 16-bit, ~850 at idle. CONFIRMED LIVE.
            hi, lo = MSS54_STATUS_GROUP2['rpm']
            rpm_raw = _read16(raw, hi, lo)
            if 0 < rpm_raw < 10000:
                data.rpm = float(rpm_raw)
                logger.debug(f"RPM = {data.rpm:.0f}")
            
            # Engine load from [6:7]
            hi, lo = MSS54_STATUS_GROUP2['load_raw']
            load_raw = _read16(raw, hi, lo)
            if load_raw > 0:
                data.engine_load = load_raw / 10.0  # tentative scaling
                logger.debug(f"Load raw = {load_raw}")
            
            # Lambda sensors from [54:55] and [56:57]
            if len(raw) >= 58:
                hi, lo = MSS54_STATUS_GROUP2['lambda_1']
                lam1 = _read16(raw, hi, lo)
                if lam1 > 0:
                    data.lambda_sensor_1 = lam1 / 1000.0
                    logger.debug(f"Lambda 1 = {data.lambda_sensor_1:.3f}")
                hi, lo = MSS54_STATUS_GROUP2['lambda_2']
                lam2 = _read16(raw, hi, lo)
                if lam2 > 0:
                    data.lambda_sensor_2 = lam2 / 1000.0
                    logger.debug(f"Lambda 2 = {data.lambda_sensor_2:.3f}")
    except Exception as e:
        logger.warning(f"DS2 STATUS_G2 error: {e}")
    
    # ── 2. STATUS group 0x03: RPM fallback + target idle ──
    if data.rpm is None and not fast:
        try:
            response = _safe_ds2_send(connection, 0x12, DS2_CMD_STATUS,
                                       bytes([0x03]), label='STATUS_G3')
            if response and len(response.data) >= 4:
                raw = response.data[1:]  # skip ack byte
                hi, lo = MSS54_STATUS_GROUP3['rpm']
                rpm_raw = _read16(raw, hi, lo)
                if 0 < rpm_raw < 10000:
                    data.rpm = float(rpm_raw)
                    logger.debug(f"RPM (G3 fallback) = {data.rpm:.0f}")
        except Exception as e:
            logger.debug(f"DS2 STATUS_G3 error: {e}")
    
    # ── 3. RAM block 1 (0x14 0x01): temps + voltage (snapshot) ──
    # These update between sessions/slowly, not every poll.
    # Still the best source for calibrated temps and battery voltage.
    # Skip in fast mode — temps don't need high-frequency updates.
    if not fast:
        try:
            response = _safe_ds2_send(connection, 0x12, DS2_CMD_RAM, bytes([0x01]),
                                       label='RAM_BLK1')
            if response and len(response.data) >= 27:
                raw = response.data[1:]  # skip ack byte
                
                # Battery voltage at byte 1: raw / 10.0
                if raw[MSS54_RAM_MAP['voltage']] != 0xFF:
                    data.battery_voltage = raw[MSS54_RAM_MAP['voltage']] / 10.0
                    logger.debug(f"Battery = {data.battery_voltage:.1f}V")
                
                # Intake temp at byte 2: raw - 40
                if raw[MSS54_RAM_MAP['intake_temp']] != 0xFF:
                    data.intake_temp = raw[MSS54_RAM_MAP['intake_temp']] - 40
                    logger.debug(f"Intake = {data.intake_temp}°C")
                
                # Oil temp at byte 9: raw - 40
                if raw[MSS54_RAM_MAP['oil_temp']] != 0xFF:
                    data.oil_temp = raw[MSS54_RAM_MAP['oil_temp']] - 40
                    logger.debug(f"Oil = {data.oil_temp}°C")
                
                # Coolant at byte 25: raw * 0.75
                if raw[MSS54_RAM_MAP['coolant_temp']] != 0xFF:
                    data.coolant_temp = raw[MSS54_RAM_MAP['coolant_temp']] * 0.75
                    logger.debug(f"Coolant = {data.coolant_temp:.1f}°C")
        except Exception as e:
            logger.warning(f"DS2 RAM error: {e}")
    
    return data


def get_engine_data_obd(connection: 'E46Connection') -> EngineData:
    """
    Read engine parameters using standard OBD-II PIDs via ISO 9141-2 gateway.
    
    This goes through the OBD-II gateway (address 0x33) using KWP2000 protocol.
    Provides standard parameters including real-time RPM and vehicle speed that
    may not be available via direct DS2 protocol.
    
    Args:
        connection: Active E46Connection (ISO 9141-2 / KWP2000)
        
    Returns:
        EngineData object with current values
    """
    data = EngineData()
    
    # Map of PID config key -> EngineData attribute name
    pid_to_attr = {
        'RPM': 'rpm',
        'SPEED': 'speed',
        'ENGINE_LOAD': 'engine_load',
        'THROTTLE_POS': 'throttle_position',
        'COOLANT_TEMP': 'coolant_temp',
        'INTAKE_TEMP': 'intake_temp',
        'OIL_TEMP': 'oil_temp',
        'MAF': 'maf',
        'INTAKE_PRESSURE': 'intake_pressure',
        'TIMING_ADVANCE': 'timing_advance',
        'BATTERY_VOLTAGE': 'battery_voltage',
        'SHORT_FUEL_TRIM_1': 'short_fuel_trim_1',
        'LONG_FUEL_TRIM_1': 'long_fuel_trim_1',
        'SHORT_FUEL_TRIM_2': 'short_fuel_trim_2',
        'LONG_FUEL_TRIM_2': 'long_fuel_trim_2',
    }
    
    for pid_name, attr_name in pid_to_attr.items():
        if pid_name not in STANDARD_PIDS:
            continue
        
        pid_def = STANDARD_PIDS[pid_name]
        try:
            response = connection.query_pid(pid_def.pid, mode=0x01)
            if response and len(response) >= 1:
                # OBD-II response: first byte is PID echo, then data bytes
                # Strip the PID echo byte if present
                if len(response) >= 2 and response[0] == pid_def.pid:
                    resp_data = response[1:]
                else:
                    resp_data = response
                
                value = _parse_pid_value(resp_data, pid_def.formula)
                if value is not None:
                    # Sanity check the value against known min/max
                    if pid_def.min_value <= value <= pid_def.max_value:
                        setattr(data, attr_name, value)
                        logger.debug(f"OBD-II {pid_name} (0x{pid_def.pid:02X}): "
                                     f"{value:.2f} {pid_def.unit}")
                    else:
                        logger.debug(f"OBD-II {pid_name}: value {value:.2f} "
                                     f"out of range [{pid_def.min_value}, "
                                     f"{pid_def.max_value}]")
                else:
                    logger.debug(f"OBD-II {pid_name}: parse returned None")
            else:
                logger.debug(f"OBD-II {pid_name} (0x{pid_def.pid:02X}): no response")
        except Exception as e:
            logger.debug(f"OBD-II {pid_name} error: {e}")
    
    return data


def get_engine_data_hybrid(
    ds2_connection: Optional['DS2Connection'] = None,
    obd_connection: Optional['E46Connection'] = None,
    prefer_obd_for: Optional[List[str]] = None
) -> EngineData:
    """
    Hybrid engine data reader: combines DS2 and OBD-II for maximum coverage.
    
    Strategy:
      1. Read DS2 data first (fast, no init overhead, BMW-specific params)
      2. Read OBD-II data for anything DS2 didn't provide
      3. For params in 'prefer_obd_for', use OBD-II value even if DS2 provided one
         (because DS2 0x14 RPM is idle target, not real-time)
    
    Args:
        ds2_connection: Optional DS2Connection for BMW-specific data
        obd_connection: Optional E46Connection for OBD-II PIDs
        prefer_obd_for: List of attribute names where OBD-II value takes priority
                        Default: ['rpm', 'speed', 'engine_load', 'throttle_position']
    
    Returns:
        EngineData with best available values from both protocols
    """
    if prefer_obd_for is None:
        prefer_obd_for = ['rpm', 'speed', 'engine_load', 'throttle_position',
                          'maf', 'timing_advance']
    
    ds2_data = None
    obd_data = None
    
    # ── Phase 1: DS2 protocol (BMW-specific, no init needed) ──
    if ds2_connection is not None:
        try:
            ds2_data = get_engine_data_ds2(ds2_connection)
            _log_data_source('DS2', ds2_data)
        except Exception as e:
            logger.error(f"DS2 phase failed: {e}")
    
    # ── Phase 2: OBD-II PIDs via gateway ──
    if obd_connection is not None:
        try:
            obd_data = get_engine_data_obd(obd_connection)
            _log_data_source('OBD', obd_data)
        except Exception as e:
            logger.error(f"OBD-II phase failed: {e}")
    
    # ── Phase 3: Merge results ──
    if ds2_data is None and obd_data is None:
        logger.error("No data from either DS2 or OBD-II")
        return EngineData()
    
    if ds2_data is None:
        return obd_data
    if obd_data is None:
        return ds2_data
    
    # Merge: start with DS2 as base, overlay OBD-II where appropriate
    merged = EngineData()
    
    # All data attributes to merge
    attrs = [
        'rpm', 'speed', 'engine_load', 'throttle_position',
        'coolant_temp', 'oil_temp', 'intake_temp',
        'maf', 'intake_pressure',
        'short_fuel_trim_1', 'long_fuel_trim_1',
        'short_fuel_trim_2', 'long_fuel_trim_2',
        'timing_advance', 'battery_voltage',
        'vanos_intake', 'vanos_exhaust',
        'knock_sensor_1', 'knock_sensor_2',
        'lambda_sensor_1', 'lambda_sensor_2',
        'fuel_injector_time',
    ]
    
    for attr in attrs:
        ds2_val = getattr(ds2_data, attr, None)
        obd_val = getattr(obd_data, attr, None)
        
        if attr in prefer_obd_for:
            # OBD-II takes priority for these params
            if obd_val is not None:
                setattr(merged, attr, obd_val)
                if ds2_val is not None and ds2_val != obd_val:
                    logger.debug(f"  {attr}: using OBD-II={obd_val:.2f} "
                                 f"(DS2 had {ds2_val:.2f})")
            elif ds2_val is not None:
                setattr(merged, attr, ds2_val)
                logger.debug(f"  {attr}: OBD-II unavailable, falling back to DS2={ds2_val:.2f}")
        else:
            # DS2 takes priority (BMW-specific params)
            if ds2_val is not None:
                setattr(merged, attr, ds2_val)
            elif obd_val is not None:
                setattr(merged, attr, obd_val)
                logger.debug(f"  {attr}: DS2 unavailable, using OBD-II={obd_val:.2f}")
    
    return merged


def _log_data_source(source: str, data: EngineData) -> None:
    """Log which parameters a data source provided."""
    available = []
    missing = []
    key_attrs = ['rpm', 'speed', 'engine_load', 'throttle_position',
                 'coolant_temp', 'oil_temp', 'intake_temp', 'battery_voltage']
    for attr in key_attrs:
        val = getattr(data, attr, None)
        if val is not None:
            available.append(f"{attr}={val:.1f}")
        else:
            missing.append(attr)
    
    logger.info(f"{source} provided: {', '.join(available) if available else 'nothing'}")
    if missing:
        logger.debug(f"{source} missing: {', '.join(missing)}")


def get_engine_identification(connection: 'DS2Connection') -> Dict[str, str]:
    """
    Get DME identification info.
    
    Returns:
        Dict with part_number, sw_version, hw_version
    """
    result = {
        'part_number': '',
        'sw_version': '',
        'hw_version': '',
        'raw_data': ''
    }
    
    try:
        response = connection.send(0x12, DS2_CMD_IDENT)
        if response and response.valid:
            data = response.data
            result['raw_data'] = data.hex()
            
            # Try to extract ASCII part number
            # Format varies by ECU, but often contains ASCII text
            if len(data) >= 10:
                # Try to find ASCII sequences
                ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data)
                result['part_number'] = ascii_str.strip('.')
                
    except Exception as e:
        logger.error(f"Error reading DME identification: {e}")
        
    return result


def probe_ds2_commands(connection: 'DS2Connection') -> Dict[str, Any]:
    """
    Probe all DS2 commands on the DME to discover available data.
    
    Sends every known command (and some unknown ones) to the DME and
    logs the responses. Use this to map out what your specific DME variant
    supports and which bytes contain live-updating data.
    
    Args:
        connection: Active DS2Connection
    
    Returns:
        Dict mapping command name -> response data (hex) or None
    """
    results = {}
    
    # All known commands + some probes
    commands_to_try = [
        (0x00, b'', 'IDENT'),
        (0x04, b'\x00', 'BLOCK_0'),
        (0x04, b'\x01', 'BLOCK_1'),
        (0x04, b'\x02', 'BLOCK_2'),
        (0x04, b'\x03', 'BLOCK_3'),
        (0x04, b'\x04', 'BLOCK_4'),
        (0x05, b'', 'CMD_05'),
        (0x06, b'', 'CMD_06'),
        (0x07, b'', 'FAULTS'),
        (0x08, b'', 'CMD_08'),
        (0x09, b'', 'IO_STATUS'),
        (0x0A, b'', 'CMD_0A'),
        (0x0B, b'', 'STATUS'),
        (0x0C, b'', 'CMD_0C'),
        (0x0D, b'', 'ANALOG'),
        (0x0E, b'', 'EXTENDED'),
        (0x0F, b'', 'CMD_0F'),
        (0x10, b'', 'CMD_10'),
        (0x11, b'', 'CMD_11'),
        (0x12, b'', 'CMD_12'),
        (0x13, b'', 'CMD_13'),
        (0x14, b'\x00', 'RAM_00'),
        (0x14, b'\x01', 'RAM_01'),
        (0x14, b'\x02', 'RAM_02'),
        (0x14, b'\x03', 'RAM_03'),
        (0x14, b'\x04', 'RAM_04'),
    ]
    
    for cmd, data, name in commands_to_try:
        response = _safe_ds2_send(connection, 0x12, cmd, data, label=name)
        if response and len(response.data) > 0:
            results[name] = {
                'command': f'0x{cmd:02X}',
                'sub_data': data.hex() if data else '',
                'response_len': len(response.data),
                'response_hex': response.data.hex(),
                'response_dec': list(response.data),
            }
            logger.info(f"  {name}: {len(response.data)} bytes")
        else:
            results[name] = None
            logger.debug(f"  {name}: no response")
    
    return results
