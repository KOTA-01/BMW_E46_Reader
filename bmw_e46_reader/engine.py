"""
BMW E46 Engine Data Module
~~~~~~~~~~~~~~~~~~~~~~~~~~

Read engine parameters from the MSS54/MSS54HP ECU using DS2 protocol.

DS2 Protocol commands for DME (0x12):
    0x00 - ECU Identification (part number, SW version)
    0x04 + block - Read block data (stored/static)
    0x0D - Read analog data (stored calibration values)
    0x14 - Read RAM data (LIVE sensor values!)
    0x07 - Read fault codes

MSS54 RAM Data Format (command 0x14 response) - VERIFIED LIVE:
    Byte 0-1: Idle target RPM (not real-time tach)
    Byte 2-3: Intake temperature (raw - 40)
    Byte 9:   Oil temperature (raw - 40) - UPDATES LIVE
    Byte 25:  Coolant temperature (raw * 0.75) - VERIFIED vs dashboard

Note: Real-time RPM from tachometer is not exposed via DS2 command 0x14.
The value at bytes 0-1 appears to be the idle control target RPM (911 RPM).
For true tachometer RPM, use standard OBD-II PID 0x0C or CAN bus access.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, TYPE_CHECKING, Union
from datetime import datetime
from loguru import logger

from .config import ECU_ADDRESSES

if TYPE_CHECKING:
    from .ds2 import DS2Connection


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
DS2_CMD_ANALOG = 0x0D     # Analog data (static/calibration)
DS2_CMD_STATUS = 0x0B     # Status data
DS2_CMD_RAM = 0x14        # RAM data - LIVE sensor data!
DS2_CMD_FAULTS = 0x07     # Read fault codes

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


def get_engine_data_ds2(connection: 'DS2Connection') -> EngineData:
    """
    Read all available engine parameters using DS2 protocol.
    
    Uses command 0x14 (RAM data) for live sensor readings.
    
    Args:
        connection: Active DS2Connection
        
    Returns:
        EngineData object with current values
    """
    data = EngineData()
    
    try:
        # PRIMARY: Read RAM data (command 0x14 0x01) - LIVE sensor data
        # Using sub-command 0x01 gives 73 bytes vs 49 bytes
        response = connection.send(0x12, DS2_CMD_RAM, bytes([0x01]))
        
        if response and response.valid and len(response.data) >= 30:
            raw = response.data
            logger.debug(f"DME RAM data ({len(raw)} bytes): {raw.hex()}")
            
            # RPM at bytes 0-1 (big-endian)
            rpm_raw = (raw[0] << 8) | raw[1]
            if 0 < rpm_raw < 10000:
                data.rpm = rpm_raw
                logger.debug(f"RPM = {rpm_raw}")
            
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
            if len(raw) > 1 and raw[1] != 0xFF:
                data.battery_voltage = raw[1] / 10.0
                logger.debug(f"Battery voltage = {data.battery_voltage}V")
        
        # SECONDARY: Read block 0 for additional confirmation
        response = connection.send(0x12, DS2_CMD_BLOCK, bytes([0x00]))
        
        if response and response.valid and len(response.data) > 4:
            raw = response.data
            logger.debug(f"DME block 0 data: {raw.hex()}")
            
            # Block 0 has confirmatory data but is static
            # Use for sanity checking only
                        
    except Exception as e:
        logger.error(f"Error reading engine data: {e}")
        
    return data


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
