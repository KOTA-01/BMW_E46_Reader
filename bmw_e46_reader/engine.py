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
DS2_CMD_STATUS = 0x0B     # Status data - likely has RPM, speed, load
DS2_CMD_ANALOG = 0x0D     # Analog data (static/calibration)
DS2_CMD_EXT = 0x0E        # Extended data
DS2_CMD_RAM = 0x14        # RAM data - LIVE sensor values (temps, voltage)

# MSS54 RAM data byte offsets (from command 0x14 0x01 response)
# Verified by live testing with key on
# Response: 73 bytes of live sensor data
MSS54_RAM_MAP = {
    'counter': 0,          # Counter/status byte (increments)
    'voltage': 1,          # Battery voltage (raw / 10) = 14.3V CONFIRMED
    'intake_temp': 2,      # Intake temp (raw - 40) = 28°C CONFIRMED
    'intake_temp_2': 3,    # Intake temp mirror
    'oil_temp': 9,         # Oil temperature (raw - 40) = 89°C CONFIRMED
    'coolant_temp': 25,    # Coolant temperature (raw * 0.75) = 74°C CONFIRMED
    'live_counter': 27,    # Changes each read (timing counter)
    'live_counter_2': 51,  # Another live counter
}

# DS2 status data (0x0B) candidate byte offsets for RPM/speed/load
# These need to be verified on a live vehicle - offsets vary by DME variant.
# MS43 vs MSS54 vs MSS54HP may differ.
# Common layout from EdiabasLib / INPA research:
MSS54_STATUS_MAP_CANDIDATES = {
    # (offset, name, formula_desc) - multiple candidates to probe
    'rpm_candidates': [
        (0, 1, '(raw[0] << 8 | raw[1]) * 0.15625'),   # Common: 16-bit, factor 6.4 or /6.4
        (0, 1, '(raw[0] << 8 | raw[1])'),               # Raw big-endian
        (2, 3, '(raw[2] << 8 | raw[3])'),               # Alternate position
        (4, 5, '(raw[4] << 8 | raw[5])'),               # Another candidate
    ],
    'speed_candidates': [
        (6, 'raw[6]'),           # Single byte km/h
        (6, 7, '(raw[6] << 8 | raw[7]) / 100'),  # 16-bit with divisor
    ],
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
                         f"invalid response (status issue)")
        else:
            logger.debug(f"DS2 {label or f'0x{command:02X}'}: no response")
    except Exception as e:
        logger.warning(f"DS2 {label or f'0x{command:02X}'} error: {e}")
    return None


def _try_parse_rpm_from_status(raw: bytes) -> Optional[float]:
    """
    Try to extract real-time RPM from DS2 status (0x0B) response.
    
    Tries multiple known byte offset / formula combinations used by
    different MSS54 variants. Returns the first plausible value.
    """
    if len(raw) < 2:
        return None
    
    # Strategy: try known formulas at known offsets.
    # Accept a value if it falls in a sane RPM range (0-9000 for S54).
    attempts = [
        # (hi_byte_idx, lo_byte_idx, divisor, description)
        (0, 1, 1.0, 'bytes 0-1 raw'),
        (0, 1, 4.0, 'bytes 0-1 / 4 (OBD-II style)'),
        (0, 1, 6.4, 'bytes 0-1 / 6.4 (INPA style)'),
        (2, 3, 1.0, 'bytes 2-3 raw'),
        (2, 3, 4.0, 'bytes 2-3 / 4'),
        (2, 3, 6.4, 'bytes 2-3 / 6.4'),
        (4, 5, 1.0, 'bytes 4-5 raw'),
        (4, 5, 4.0, 'bytes 4-5 / 4'),
    ]
    
    results = []
    for hi, lo, div, desc in attempts:
        if len(raw) <= max(hi, lo):
            continue
        val = ((raw[hi] << 8) | raw[lo]) / div
        if 100 < val < 9000:  # plausible RPM range (above cranking, below redline)
            results.append((val, desc))
            logger.debug(f"  Status RPM candidate: {val:.0f} via {desc}")
    
    if results:
        # Prefer the value closest to a typical idle (~700-900) if engine is idling,
        # otherwise just return the first plausible result
        return results[0][0]
    return None


def _try_parse_speed_from_status(raw: bytes) -> Optional[float]:
    """Try to extract vehicle speed from DS2 status response."""
    if len(raw) < 7:
        return None
    
    # Single byte at various offsets
    for idx in [6, 7, 8, 10, 12]:
        if len(raw) > idx and 0 < raw[idx] <= 255:
            # This is tricky - we can't easily distinguish speed from other values
            # Only return if clearly in a speed-like range (needs live verification)
            pass
    
    # 16-bit speed at common offsets
    for hi, lo, div in [(6, 7, 100.0), (8, 9, 100.0)]:
        if len(raw) > max(hi, lo):
            val = ((raw[hi] << 8) | raw[lo]) / div
            if 0 < val < 300:  # plausible speed range km/h
                logger.debug(f"  Status speed candidate: {val:.1f} km/h @ bytes {hi}-{lo}")
                return val
    return None


def get_engine_data_ds2(connection: 'DS2Connection') -> EngineData:
    """
    Read all available engine parameters using DS2 protocol.
    
    Tries multiple DS2 commands in priority order:
      1. 0x0B (status) - most likely to have real-time RPM, speed, load
      2. 0x14 (RAM) - confirmed live temps, voltage
      3. 0x0D (analog) - additional sensor data
      4. 0x0E (extended) - probe for more data
      5. 0x14 with sub-commands 0x00..0x03 - alternate RAM blocks
    
    Args:
        connection: Active DS2Connection
        
    Returns:
        EngineData object with current values
    """
    data = EngineData()
    
    # ── 1. DS2 Status (0x0B) ── likely has real-time RPM / speed / load ──
    try:
        response = _safe_ds2_send(connection, 0x12, DS2_CMD_STATUS, label='STATUS')
        if response and len(response.data) >= 2:
            raw = response.data
            logger.info(f"DME STATUS data ({len(raw)} bytes): {raw.hex()}")
            
            # Try to extract RPM from status
            rpm = _try_parse_rpm_from_status(raw)
            if rpm is not None:
                data.rpm = rpm
                logger.info(f"Got RPM from DS2 status: {rpm:.0f}")
            
            # Try to extract speed from status
            speed = _try_parse_speed_from_status(raw)
            if speed is not None:
                data.speed = speed
                logger.info(f"Got speed from DS2 status: {speed:.1f} km/h")
    except Exception as e:
        logger.warning(f"DS2 STATUS error: {e}")
    
    # ── 2. DS2 RAM (0x14 0x01) ── confirmed for temps + voltage ──
    try:
        response = _safe_ds2_send(connection, 0x12, DS2_CMD_RAM, bytes([0x01]),
                                   label='RAM 0x01')
        if response and len(response.data) >= 30:
            raw = response.data
            logger.debug(f"DME RAM data ({len(raw)} bytes): {raw.hex()}")
            
            # RPM from RAM bytes 0-1 (idle target RPM, fallback only)
            if data.rpm is None:
                rpm_raw = (raw[0] << 8) | raw[1]
                if 0 < rpm_raw < 10000:
                    data.rpm = rpm_raw
                    logger.debug(f"RPM (idle target fallback) = {rpm_raw}")
            
            # Coolant temp at byte 25 (raw * 0.75 formula for MSS54)
            if len(raw) > 25 and raw[25] != 0xFF:
                data.coolant_temp = raw[25] * 0.75
                logger.debug(f"Coolant temp = {data.coolant_temp}°C")
            
            # Intake temp at byte 2 (raw - 40)
            if raw[2] != 0xFF:
                data.intake_temp = raw[2] - 40
                logger.debug(f"Intake temp = {data.intake_temp}°C")
            
            # Oil temp at byte 9 (raw - 40)
            if raw[9] != 0xFF:
                data.oil_temp = raw[9] - 40
                logger.debug(f"Oil temp = {data.oil_temp}°C")
            
            # Battery voltage at byte 1 (raw / 10)
            if raw[1] != 0xFF:
                data.battery_voltage = raw[1] / 10.0
                logger.debug(f"Battery voltage = {data.battery_voltage}V")
    except Exception as e:
        logger.warning(f"DS2 RAM error: {e}")
    
    # ── 3. DS2 RAM alternate sub-commands (0x00, 0x02, 0x03) ──
    # Some DME variants expose different data in different RAM blocks
    for sub_cmd in [0x00, 0x02, 0x03]:
        # Only query additional blocks if we're still missing key data
        if data.rpm is not None and data.coolant_temp is not None:
            break
        try:
            response = _safe_ds2_send(connection, 0x12, DS2_CMD_RAM,
                                       bytes([sub_cmd]),
                                       label=f'RAM 0x{sub_cmd:02X}')
            if response and len(response.data) >= 10:
                raw = response.data
                logger.info(f"DME RAM 0x{sub_cmd:02X} ({len(raw)} bytes): {raw.hex()}")
                
                # Try RPM extraction if still missing
                if data.rpm is None and len(raw) >= 2:
                    rpm_raw = (raw[0] << 8) | raw[1]
                    if 100 < rpm_raw < 10000:
                        data.rpm = rpm_raw
                        logger.info(f"RPM from RAM 0x{sub_cmd:02X}: {rpm_raw}")
        except Exception as e:
            logger.debug(f"DS2 RAM 0x{sub_cmd:02X} error: {e}")
    
    # ── 4. DS2 Analog (0x0D) ── may have additional sensor data ──
    try:
        response = _safe_ds2_send(connection, 0x12, DS2_CMD_ANALOG, label='ANALOG')
        if response and len(response.data) >= 10:
            raw = response.data
            logger.debug(f"DME ANALOG data ({len(raw)} bytes): {raw.hex()}")
            # Analog data is typically calibration/static, but log for discovery
    except Exception as e:
        logger.debug(f"DS2 ANALOG error: {e}")
    
    # ── 5. DS2 Extended (0x0E) ── probe for more data ──
    try:
        response = _safe_ds2_send(connection, 0x12, DS2_CMD_EXT, label='EXTENDED')
        if response and len(response.data) >= 4:
            raw = response.data
            logger.debug(f"DME EXT data ({len(raw)} bytes): {raw.hex()}")
    except Exception as e:
        logger.debug(f"DS2 EXT error: {e}")
    
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
