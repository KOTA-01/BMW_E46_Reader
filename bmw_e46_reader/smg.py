"""
BMW E46 M3 SMG II Module
~~~~~~~~~~~~~~~~~~~~~~~~

Read data from the Sequential Manual Gearbox II transmission.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, TYPE_CHECKING
from datetime import datetime
from enum import Enum
from loguru import logger

from .config import ECU_ADDRESSES, SMG_PARAMETERS

if TYPE_CHECKING:
    from .connection import E46Connection


class GearPosition(Enum):
    """SMG gear positions"""
    NEUTRAL = 0
    FIRST = 1
    SECOND = 2
    THIRD = 3
    FOURTH = 4
    FIFTH = 5
    SIXTH = 6
    REVERSE = 7
    UNKNOWN = -1


class ShiftMode(Enum):
    """SMG shift programs"""
    S1 = 1  # Efficiency/comfort
    S2 = 2
    S3 = 3  # Normal
    S4 = 4
    S5 = 5
    S6 = 6  # Sport/race
    A = 0   # Automatic mode


class SMGStatus(Enum):
    """SMG system status"""
    OK = "ok"
    WARNING = "warning"
    FAULT = "fault"
    LIMP_MODE = "limp_mode"


@dataclass
class SMGData:
    """
    Container for SMG II transmission data.
    
    The E46 M3 SMG II is a 6-speed automated manual transmission
    with paddle shifters and multiple driving programs.
    """
    timestamp: datetime = field(default_factory=datetime.now)
    
    # Gear information
    gear: GearPosition = GearPosition.UNKNOWN
    gear_requested: GearPosition = GearPosition.UNKNOWN
    shift_mode: ShiftMode = ShiftMode.S3
    
    # Clutch data
    clutch_position: Optional[float] = None  # % open (0=engaged, 100=disengaged)
    clutch_wear: Optional[float] = None  # % wear estimate
    
    # Hydraulic system
    hydraulic_pressure: Optional[float] = None  # bar
    pump_running: bool = False
    
    # Temperature
    gearbox_temp: Optional[float] = None  # °C
    
    # Shift performance
    last_shift_time: Optional[float] = None  # ms
    
    # System status
    status: SMGStatus = SMGStatus.OK
    driveability_flag: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/export"""
        return {
            'timestamp': self.timestamp.isoformat(),
            'gear': self.gear.value if self.gear != GearPosition.UNKNOWN else None,
            'gear_requested': self.gear_requested.value if self.gear_requested != GearPosition.UNKNOWN else None,
            'shift_mode': self.shift_mode.name,
            'clutch_position': self.clutch_position,
            'clutch_wear': self.clutch_wear,
            'hydraulic_pressure': self.hydraulic_pressure,
            'pump_running': self.pump_running,
            'gearbox_temp': self.gearbox_temp,
            'last_shift_time': self.last_shift_time,
            'status': self.status.value,
            'driveability_flag': self.driveability_flag,
        }
    
    def __str__(self) -> str:
        """Human-readable string representation"""
        gear_str = 'N' if self.gear == GearPosition.NEUTRAL else \
                   'R' if self.gear == GearPosition.REVERSE else \
                   str(self.gear.value) if self.gear != GearPosition.UNKNOWN else '?'
        
        lines = [
            f"SMG Data @ {self.timestamp.strftime('%H:%M:%S.%f')[:-3]}",
            "-" * 40,
            f"Current Gear:     {gear_str}",
            f"Shift Mode:       {self.shift_mode.name}",
        ]
        
        if self.clutch_position is not None:
            lines.append(f"Clutch Position:  {self.clutch_position:.1f}%")
        if self.clutch_wear is not None:
            lines.append(f"Clutch Wear:      {self.clutch_wear:.1f}%")
        if self.hydraulic_pressure is not None:
            lines.append(f"Hydraulic Press:  {self.hydraulic_pressure:.1f} bar")
        lines.append(f"Pump Running:     {'Yes' if self.pump_running else 'No'}")
        if self.gearbox_temp is not None:
            lines.append(f"Gearbox Temp:     {self.gearbox_temp:.1f}°C")
        if self.last_shift_time is not None:
            lines.append(f"Last Shift Time:  {self.last_shift_time:.0f} ms")
        lines.append(f"Status:           {self.status.value}")
        
        return "\n".join(lines)


def _parse_gear(value: int) -> GearPosition:
    """Convert raw gear value to GearPosition enum"""
    gear_map = {
        0: GearPosition.NEUTRAL,
        1: GearPosition.FIRST,
        2: GearPosition.SECOND,
        3: GearPosition.THIRD,
        4: GearPosition.FOURTH,
        5: GearPosition.FIFTH,
        6: GearPosition.SIXTH,
        7: GearPosition.REVERSE,
        0xFF: GearPosition.UNKNOWN,
    }
    return gear_map.get(value, GearPosition.UNKNOWN)


def _parse_shift_mode(value: int) -> ShiftMode:
    """Convert raw shift mode value to ShiftMode enum"""
    if value == 0:
        return ShiftMode.A
    elif 1 <= value <= 6:
        return ShiftMode(value)
    return ShiftMode.S3  # Default


def get_smg_data(connection: 'E46Connection') -> SMGData:
    """
    Read all available SMG II parameters.
    
    Args:
        connection: Active E46Connection
        
    Returns:
        SMGData object with current values
    """
    data = SMGData()
    ecu_addr = ECU_ADDRESSES.get('EGS', 0x32)
    
    # Start diagnostic session with SMG ECU
    connection.send_command(0x10, bytes([0x89]), ecu_addr)
    
    # Read gear position
    logger.debug("Reading SMG gear position...")
    response = connection.send_command(
        0x21, 
        bytes([SMG_PARAMETERS['GEAR_POSITION'].address]), 
        ecu_addr
    )
    if response and len(response) > 1:
        data.gear = _parse_gear(response[1])
        logger.debug(f"Gear: {data.gear}")
    
    # Read requested gear
    response = connection.send_command(
        0x21,
        bytes([SMG_PARAMETERS['GEAR_REQUESTED'].address]),
        ecu_addr
    )
    if response and len(response) > 1:
        data.gear_requested = _parse_gear(response[1])
    
    # Read shift mode
    response = connection.send_command(
        0x21,
        bytes([SMG_PARAMETERS['SHIFT_MODE'].address]),
        ecu_addr
    )
    if response and len(response) > 1:
        data.shift_mode = _parse_shift_mode(response[1])
        logger.debug(f"Shift mode: {data.shift_mode}")
    
    # Read clutch position
    response = connection.send_command(
        0x21,
        bytes([SMG_PARAMETERS['CLUTCH_POSITION'].address]),
        ecu_addr
    )
    if response and len(response) > 1:
        data.clutch_position = response[1] * 100.0 / 255.0
        logger.debug(f"Clutch position: {data.clutch_position:.1f}%")
    
    # Read clutch wear
    response = connection.send_command(
        0x21,
        bytes([SMG_PARAMETERS['CLUTCH_WEAR'].address]),
        ecu_addr
    )
    if response and len(response) > 1:
        data.clutch_wear = response[1] * 100.0 / 255.0
        logger.debug(f"Clutch wear: {data.clutch_wear:.1f}%")
    
    # Read hydraulic pressure
    response = connection.send_command(
        0x21,
        bytes([SMG_PARAMETERS['HYDRAULIC_PRESSURE'].address]),
        ecu_addr
    )
    if response and len(response) > 2:
        data.hydraulic_pressure = (response[1] * 256 + response[2]) / 10.0
        logger.debug(f"Hydraulic pressure: {data.hydraulic_pressure:.1f} bar")
    
    # Read pump status
    response = connection.send_command(
        0x21,
        bytes([SMG_PARAMETERS['PUMP_STATUS'].address]),
        ecu_addr
    )
    if response and len(response) > 1:
        data.pump_running = bool(response[1] & 0x01)
    
    # Read gearbox temperature
    response = connection.send_command(
        0x21,
        bytes([SMG_PARAMETERS['GEARBOX_TEMP'].address]),
        ecu_addr
    )
    if response and len(response) > 1:
        data.gearbox_temp = response[1] - 40  # Standard temp offset
        logger.debug(f"Gearbox temp: {data.gearbox_temp:.1f}°C")
    
    # Read last shift time
    response = connection.send_command(
        0x21,
        bytes([SMG_PARAMETERS['SHIFT_TIME'].address]),
        ecu_addr
    )
    if response and len(response) > 2:
        data.last_shift_time = response[1] * 256 + response[2]
        logger.debug(f"Last shift time: {data.last_shift_time:.0f} ms")
    
    # Check for driveability flag
    # This is set when the SMG needs adaptation or has issues
    response = connection.send_command(0x21, bytes([0x50]), ecu_addr)
    if response and len(response) > 1:
        data.driveability_flag = bool(response[1] & 0x01)
        if data.driveability_flag:
            logger.warning("SMG driveability flag is set")
    
    return data


def get_clutch_adaptation(connection: 'E46Connection') -> Dict[str, float]:
    """
    Read SMG clutch adaptation values.
    
    These values show how much the SMG has learned/adapted the clutch.
    
    Returns:
        Dictionary of adaptation values
    """
    ecu_addr = ECU_ADDRESSES.get('EGS', 0x32)
    adaptations = {}
    
    # Clutch kiss point
    response = connection.send_command(0x21, bytes([0x60]), ecu_addr)
    if response and len(response) > 1:
        adaptations['kiss_point'] = response[1] * 100.0 / 255.0
    
    # Clutch slip adaptation
    response = connection.send_command(0x21, bytes([0x61]), ecu_addr)
    if response and len(response) > 1:
        adaptations['slip_adaptation'] = response[1] - 128  # Signed value
    
    # Shift time adaptation
    response = connection.send_command(0x21, bytes([0x62]), ecu_addr)
    if response and len(response) > 1:
        adaptations['shift_time_adapt'] = response[1] - 128
    
    return adaptations


def reset_smg_adaptations(connection: 'E46Connection') -> bool:
    """
    Reset SMG clutch adaptations.
    
    WARNING: After reset, the SMG will need to re-learn clutch values.
    Drive gently for the first 50-100 shifts after reset.
    
    Returns:
        True if successful
    """
    logger.warning("Resetting SMG adaptations...")
    ecu_addr = ECU_ADDRESSES.get('EGS', 0x32)
    
    # Enter extended diagnostic session
    connection.send_command(0x10, bytes([0x86]), ecu_addr)
    
    # BMW routine to reset adaptations
    response = connection.send_command(0x31, bytes([0x01, 0xF0]), ecu_addr)
    
    if response and len(response) >= 1:
        if response[0] == 0x71:  # Positive response
            logger.success("SMG adaptations reset")
            return True
    
    logger.error("Failed to reset SMG adaptations")
    return False


def get_smg_fault_history(connection: 'E46Connection') -> list:
    """
    Get SMG-specific fault history.
    
    Returns more detailed SMG fault information than standard DTC reading.
    """
    from .dtc import FaultCode, DTCStatus, E46_M3_FAULT_CODES
    
    faults = []
    ecu_addr = ECU_ADDRESSES.get('EGS', 0x32)
    
    # Read SMG fault memory
    response = connection.send_command(0x18, bytes([0xFF, 0xFF]), ecu_addr)
    
    if response and len(response) > 2:
        i = 1
        while i + 2 < len(response):
            byte1 = response[i]
            byte2 = response[i + 1]
            status = response[i + 2]
            
            if byte1 != 0 or byte2 != 0:
                # Construct code
                code = f"P{byte1:02X}{byte2:02X}"
                
                # Try to find description
                desc = E46_M3_FAULT_CODES.get(code, "SMG fault")
                
                dtc_status = DTCStatus.CONFIRMED if status & 0x80 else DTCStatus.PENDING
                
                faults.append(FaultCode(
                    code=code,
                    description=desc,
                    status=dtc_status,
                    ecu='SMG'
                ))
            
            i += 3
    
    return faults


def smg_pump_test(connection: 'E46Connection') -> bool:
    """
    Run SMG hydraulic pump self-test.
    
    This activates the pump and checks pressure build-up.
    
    Returns:
        True if pump test passed
    """
    logger.info("Running SMG pump test...")
    ecu_addr = ECU_ADDRESSES.get('EGS', 0x32)
    
    # Enter extended diagnostic session
    connection.send_command(0x10, bytes([0x86]), ecu_addr)
    
    # Actuator test for pump
    response = connection.send_command(0x30, bytes([0x01, 0x01]), ecu_addr)
    
    if response and len(response) >= 2:
        if response[0] == 0x70:
            logger.success("SMG pump test passed")
            return True
    
    logger.error("SMG pump test failed")
    return False
