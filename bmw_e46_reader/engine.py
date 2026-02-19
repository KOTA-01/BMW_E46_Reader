"""
BMW E46 Engine Data Module
~~~~~~~~~~~~~~~~~~~~~~~~~~

Read engine parameters from the MSS54/MSS54HP ECU using DS2 protocol.

DS2 Protocol commands for DME (0x12):
    0x00 - ECU Identification (part number, SW version)
    0x04 + block - Read block data (0x00=temps, etc.)
    0x0D - Read analog channel data (RPM, temps, load, etc.)
    0x07 - Read fault codes

MSS54 Analog Data Format (command 0x0D response):
    Based on EdiabasLib/pBmwScanner documentation
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
DS2_CMD_BLOCK = 0x04      # Block read (temperature data etc.)
DS2_CMD_ANALOG = 0x0D     # Analog data (main live data)
DS2_CMD_STATUS = 0x0B     # Status data
DS2_CMD_FAULTS = 0x07     # Read fault codes

# MSS54 analog data byte offsets (from command 0x0D response)
# These are empirical values based on testing and EdiabasLib
MSS54_ANALOG_MAP = {
    'status': 0,           # Status byte
    'rpm_high': 1,         # RPM high byte
    'rpm_low': 2,          # RPM low byte  
    'coolant_temp': 3,     # Coolant temperature (raw-40)
    'intake_temp': 4,      # Intake air temperature (raw-40)
    'load': 5,             # Engine load %
    'throttle': 6,         # Throttle position %
    'maf_high': 7,         # MAF high byte
    'maf_low': 8,          # MAF low byte
    'vanos_intake': 9,     # VANOS intake position
    'vanos_exhaust': 10,   # VANOS exhaust position
    'timing_advance': 11,  # Timing advance
    'o2_volts_1': 12,      # O2 sensor 1 voltage
    'o2_volts_2': 13,      # O2 sensor 2 voltage
    'supply_voltage': 14,  # Supply voltage x10
    'fuel_trim_1': 15,     # Short term fuel trim bank 1
    'fuel_trim_2': 16,     # Short term fuel trim bank 2
    'oil_temp': 17,        # Oil temperature (if available)
    'speed': 18,           # Vehicle speed (km/h)
}


def get_engine_data_ds2(connection: 'DS2Connection') -> EngineData:
    """
    Read all available engine parameters using DS2 protocol.
    
    Args:
        connection: Active DS2Connection
        
    Returns:
        EngineData object with current values
    """
    data = EngineData()
    
    try:
        # PRIMARY: Read temperature block (command 0x04, block 0)
        # This reliably gives us temperatures
        response = connection.send(0x12, DS2_CMD_BLOCK, bytes([0x00]))
        
        if response and response.valid and len(response.data) > 4:
            raw = response.data
            logger.debug(f"DME block 0 data: {raw.hex()}")
            
            # Block 0 format: [block_echo] [coolant] [?] [intake] [?] ...
            # Byte 1 = coolant temp (raw - 40)
            if len(raw) > 1 and raw[1] != 0xFF:
                data.coolant_temp = raw[1] - 40
                
            # Byte 3 = intake temp (raw - 40)  
            if len(raw) > 3 and raw[3] != 0xFF:
                data.intake_temp = raw[3] - 40
        
        # Read block 1 for additional data
        response = connection.send(0x12, DS2_CMD_BLOCK, bytes([0x01]))
        
        if response and response.valid and len(response.data) > 10:
            raw = response.data
            logger.debug(f"DME block 1 data: {raw.hex()}")
            
            # Block 1 contains various engine parameters
            # Format varies but typically has RPM, load, etc.
            # Skip first byte (block echo)
            
            # Try to find RPM - often at bytes 1-2 as 16-bit value
            if len(raw) > 2:
                rpm_b1 = raw[1]
                rpm_b2 = raw[2]
                # RPM typically 0-8000 range, so 16-bit value would be reasonable
                rpm_raw = (rpm_b1 << 8) | rpm_b2
                # If engine is off, we might get 0 or small values
                if rpm_raw < 10000 and rpm_raw > 0:
                    data.rpm = rpm_raw
                    
            # Engine load might be at byte 3
            if len(raw) > 3:
                load = raw[3]
                if load != 0xFF and load != 0x00:
                    data.engine_load = load * 100.0 / 255.0
                    
            # Throttle might be at byte 4 or 5
            if len(raw) > 5:
                throttle = raw[5]
                if throttle != 0xFF and throttle != 0x00:
                    data.throttle_position = throttle * 100.0 / 255.0
        
        # SECONDARY: Try analog command 0x0D for runtime data
        # This has more complete data when engine is running
        response = connection.send(0x12, DS2_CMD_ANALOG)
        
        if response and response.valid and len(response.data) > 45:
            raw = response.data
            logger.debug(f"DME analog data ({len(raw)} bytes): {raw.hex()}")
            
            # The analog response has a header section with job info
            # Actual data starts after the 0xFF padding section
            # Looking for non-FF values after byte ~40
            
            # Find the start of actual data (first non-FF after padding)
            data_start = 40  # Skip header and FF padding
            
            if len(raw) > data_start + 10:
                # RPM might be at bytes 42-43 (showing 0x0000 when engine off)
                if raw[data_start] != 0xFF and raw[data_start + 1] != 0xFF:
                    rpm_raw = (raw[data_start] << 8) | raw[data_start + 1]
                    if 0 < rpm_raw < 10000:
                        data.rpm = rpm_raw
                        
                # Battery voltage often in later bytes
                # Look for reasonable voltage value (100-160 = 10.0-16.0V)
                for i in range(data_start, min(len(raw), data_start + 30)):
                    v = raw[i]
                    if 100 <= v <= 160:
                        data.battery_voltage = v / 10.0
                        break
                        
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
