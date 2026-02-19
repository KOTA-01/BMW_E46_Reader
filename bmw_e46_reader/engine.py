"""
BMW E46 Engine Data Module
~~~~~~~~~~~~~~~~~~~~~~~~~~

Read engine parameters from the MSS54 ECU.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, TYPE_CHECKING
from datetime import datetime
from loguru import logger

from .config import STANDARD_PIDS, MSS54_PIDS

if TYPE_CHECKING:
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


def get_engine_data(connection: 'E46Connection') -> EngineData:
    """
    Read all available engine parameters.
    
    Args:
        connection: Active E46Connection
        
    Returns:
        EngineData object with current values
    """
    data = EngineData()
    
    # Query standard OBD-II PIDs
    pid_map = [
        ('rpm', 'RPM'),
        ('speed', 'SPEED'),
        ('engine_load', 'ENGINE_LOAD'),
        ('throttle_position', 'THROTTLE_POS'),
        ('coolant_temp', 'COOLANT_TEMP'),
        ('oil_temp', 'OIL_TEMP'),
        ('intake_temp', 'INTAKE_TEMP'),
        ('maf', 'MAF'),
        ('intake_pressure', 'INTAKE_PRESSURE'),
        ('short_fuel_trim_1', 'SHORT_FUEL_TRIM_1'),
        ('long_fuel_trim_1', 'LONG_FUEL_TRIM_1'),
        ('short_fuel_trim_2', 'SHORT_FUEL_TRIM_2'),
        ('long_fuel_trim_2', 'LONG_FUEL_TRIM_2'),
        ('timing_advance', 'TIMING_ADVANCE'),
        ('battery_voltage', 'BATTERY_VOLTAGE'),
    ]
    
    for attr, pid_name in pid_map:
        if pid_name in STANDARD_PIDS:
            pid_info = STANDARD_PIDS[pid_name]
            response = connection.query_pid(pid_info.pid)
            
            if response and len(response) > 2:
                # Skip service ID and PID echo in response
                value = _parse_pid_value(response[2:], pid_info.formula)
                if value is not None:
                    setattr(data, attr, value)
                    logger.debug(f"{pid_name}: {value}")
    
    # Query BMW-specific PIDs for VANOS, knock, etc.
    bmw_pid_map = [
        ('vanos_intake', 'VANOS_INTAKE'),
        ('vanos_exhaust', 'VANOS_EXHAUST'),
        ('knock_sensor_1', 'KNOCK_SENSOR_1'),
        ('knock_sensor_2', 'KNOCK_SENSOR_2'),
        ('lambda_sensor_1', 'LAMBDA_SENSOR_1'),
        ('lambda_sensor_2', 'LAMBDA_SENSOR_2'),
        ('fuel_injector_time', 'FUEL_INJECTOR_TIME'),
    ]
    
    for attr, pid_name in bmw_pid_map:
        if pid_name in MSS54_PIDS:
            pid_info = MSS54_PIDS[pid_name]
            # Use BMW-specific read request (service 0x21)
            response = connection.send_command(0x21, bytes([pid_info.address]))
            
            if response and len(response) > 1:
                value = _parse_pid_value(response[1:], pid_info.formula)
                if value is not None:
                    setattr(data, attr, value)
                    logger.debug(f"{pid_name}: {value}")
    
    return data


def get_single_value(connection: 'E46Connection', parameter: str) -> Optional[float]:
    """
    Read a single engine parameter.
    
    Args:
        connection: Active E46Connection
        parameter: Parameter name (e.g., 'RPM', 'COOLANT_TEMP')
        
    Returns:
        Parameter value or None if not available
    """
    parameter = parameter.upper()
    
    if parameter in STANDARD_PIDS:
        pid_info = STANDARD_PIDS[parameter]
        response = connection.query_pid(pid_info.pid)
        
        if response and len(response) > 2:
            return _parse_pid_value(response[2:], pid_info.formula)
    
    elif parameter in MSS54_PIDS:
        pid_info = MSS54_PIDS[parameter]
        response = connection.send_command(0x21, bytes([pid_info.address]))
        
        if response and len(response) > 1:
            return _parse_pid_value(response[1:], pid_info.formula)
    
    return None


def get_supported_pids(connection: 'E46Connection') -> list:
    """
    Query which PIDs are supported by the ECU.
    
    Returns:
        List of supported PID numbers
    """
    supported = []
    
    # Query supported PIDs in groups of 32
    for base_pid in [0x00, 0x20, 0x40, 0x60, 0x80, 0xA0, 0xC0]:
        response = connection.query_pid(base_pid)
        
        if response and len(response) >= 6:
            # Parse 4 bytes of PID support bitmap
            bitmap = response[2:6]
            
            for i, byte in enumerate(bitmap):
                for bit in range(8):
                    if byte & (0x80 >> bit):
                        pid_num = base_pid + (i * 8) + bit + 1
                        supported.append(pid_num)
        else:
            # Stop if ECU doesn't respond
            break
    
    return supported
