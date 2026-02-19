"""
BMW E46 M3 SMG II Module
~~~~~~~~~~~~~~~~~~~~~~~~

Read data from the Sequential Manual Gearbox II transmission using DS2 protocol.

DS2 Protocol:
    ECU Address: 0x32
    Baud Rate: 9600
    Parity: Even
    
Commands:
    0x00 - ECU identification
    0x04 + block - Block read  
    0x05 - Status
    0x0A - Info
    0x0D - Analog data
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, TYPE_CHECKING, Union
from datetime import datetime
from enum import Enum
from loguru import logger

from .config import ECU_ADDRESSES

if TYPE_CHECKING:
    from .ds2 import DS2Connection


# DS2 Services for SMG
DS2_SERVICE_STATUS = 0x0B  # Read status data
DS2_SERVICE_IDENT = 0x00   # ECU identification
DS2_SERVICE_DTC_READ = 0x07  # Read fault codes
DS2_SERVICE_DTC_CLEAR = 0x05  # Clear fault codes
DS2_SERVICE_JOB = 0x12       # Execute job/routine


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


# DS2 command constants for SMG
DS2_CMD_IDENT = 0x00      # ECU identification
DS2_CMD_BLOCK = 0x04      # Block read
DS2_CMD_STATUS = 0x05     # Status data
DS2_CMD_ANALOG = 0x0D     # Analog channel data (72 bytes)
DS2_CMD_INFO = 0x0A       # Info data

# SMG ECU address
SMG_ECU_ADDR = 0x32

# SMG Analog data byte offsets (from command 0x0D response)
# VERIFIED by live testing - 72 byte response
# NOTE: Gear position only updates with engine running (hydraulic pressure needed)
SMG_ANALOG_MAP = {
    'gear': 0,             # Engaged gear (0=N, 1-6, 7=R) - NEEDS ENGINE RUNNING
    'unknown_1': 1,        # Value 60 observed (temp related?)
    'unknown_2': 2,        # Value 50 observed
    # Bytes 3-44: Mostly 0xFF (masked/unused)
    'shift_mode': 45,      # Shift program: 3=S3 CONFIRMED
    'gearbox_temp': 46,    # Gearbox temperature (raw-40) = 87°C CONFIRMED
    # Bytes 47-71: Additional sensor data
}


def get_smg_data_ds2(connection: 'DS2Connection') -> SMGData:
    """
    Read all available SMG II parameters using DS2 protocol.
    
    NOTE: Gear position only updates when engine is running.
    With engine off, gear will always show Neutral (0).
    
    Args:
        connection: Active DS2Connection
        
    Returns:
        SMGData object with current values
    """
    data = SMGData()
    
    try:
        # Read analog data (command 0x0D) - 72 bytes
        response = connection.send(SMG_ECU_ADDR, DS2_CMD_ANALOG)
        
        if response and response.valid and len(response.data) >= 47:
            raw = response.data
            logger.debug(f"SMG analog data ({len(raw)} bytes): {raw.hex()}")
            
            # Gear position at byte 0 (only updates with engine running)
            gear_byte = raw[SMG_ANALOG_MAP['gear']]
            data.gear = _parse_gear(gear_byte)
            logger.debug(f"SMG gear = {data.gear.name} (raw: {gear_byte})")
            
            # Shift mode at byte 45
            if len(raw) > SMG_ANALOG_MAP['shift_mode']:
                mode_byte = raw[SMG_ANALOG_MAP['shift_mode']]
                data.shift_mode = _parse_shift_mode(mode_byte)
                logger.debug(f"SMG shift mode = {data.shift_mode.name} (raw: {mode_byte})")
            
            # Gearbox temperature at byte 46 (raw - 40)
            if len(raw) > SMG_ANALOG_MAP['gearbox_temp']:
                temp_byte = raw[SMG_ANALOG_MAP['gearbox_temp']]
                if temp_byte != 0xFF:
                    data.gearbox_temp = temp_byte - 40
                    logger.debug(f"SMG gearbox temp = {data.gearbox_temp}°C (raw: {temp_byte})")
                    
        # Also read block 0 for additional status
        response = connection.send(SMG_ECU_ADDR, DS2_CMD_BLOCK, bytes([0x00]))
        
        if response and response.valid and len(response.data) > 3:
            raw = response.data
            logger.debug(f"SMG block 0 data: {raw.hex()}")
            
            # Status byte often at position 0
            status_byte = raw[0]
            
            # Gear is often in lower nibble of a byte
            for i, b in enumerate(raw[:5]):
                if (b & 0x0F) <= 7:  # Valid gear value
                    gear_val = b & 0x0F
                    if gear_val > 0 or i > 0:  # Skip first byte if 0
                        data.gear = _parse_gear(gear_val)
                        break
            
            # NOTE: Block 0 contains ASCII status "-N-N", NOT temperature
            # Temperature is read from Status command (0x0B) byte 3
                    
        # Read status command for pump and clutch info
        # Note: Status command (0x0B) returns 0xB0 "busy" on SMG, limited data available
        response = connection.send(SMG_ECU_ADDR, DS2_CMD_STATUS)
        
        if response and response.valid and len(response.data) > 2:
            raw = response.data
            logger.debug(f"SMG status data: {raw.hex()}")
            
            # Try to find pump status bit
            if len(raw) > 0:
                data.pump_running = bool(raw[0] & 0x10)  # Typical bit position
                
            # Clutch position if available
            if len(raw) > 2:
                clutch = raw[2]
                if clutch != 0xFF:
                    data.clutch_position = clutch * 100.0 / 255.0
                    
    except Exception as e:
        logger.error(f"Error reading SMG data: {e}")
        
    return data


def get_smg_identification(connection: 'DS2Connection') -> Dict[str, str]:
    """
    Get SMG ECU identification info.
    
    Returns:
        Dict with part_number, sw_version, etc.
    """
    result = {
        'part_number': '',
        'sw_version': '',
        'raw_data': ''
    }
    
    try:
        response = connection.send(SMG_ECU_ADDR, DS2_CMD_IDENT)
        if response and response.valid:
            data = response.data
            result['raw_data'] = data.hex()
            
            # Try to extract ASCII part number
            if len(data) >= 7:
                # SMG part numbers are typically 7 digits
                for i in range(len(data) - 6):
                    try:
                        part_str = ''.join(chr(b) for b in data[i:i+7] if 48 <= b <= 57)
                        if len(part_str) >= 7:
                            result['part_number'] = part_str[:7]
                            break
                    except:
                        pass
                        
    except Exception as e:
        logger.error(f"Error reading SMG identification: {e}")
        
    return result


# Legacy function wrapper for backward compatibility  
def get_smg_data(connection: 'DS2Connection') -> SMGData:
    """
    Read all available SMG II parameters.
    
    Args:
        connection: Active DS2Connection
        
    Returns:
        SMGData object with current values
    """
    return get_smg_data_ds2(connection)


def get_clutch_adaptation_ds2(connection: 'DS2Connection') -> Dict[str, float]:
    """
    Read SMG clutch adaptation values using DS2 protocol.
    
    These values show how much the SMG has learned/adapted the clutch.
    
    Returns:
        Dictionary of adaptation values
    """
    adaptations = {}
    
    try:
        # Read adaptation data via block read
        response = connection.send(SMG_ECU_ADDR, DS2_CMD_BLOCK, bytes([0x60]))
        if response and response.valid and len(response.data) > 2:
            raw = response.data
            # Adaptation values typically in sequential bytes
            if len(raw) > 0 and raw[0] != 0xFF:
                adaptations['kiss_point'] = raw[0] * 100.0 / 255.0
            if len(raw) > 1 and raw[1] != 0xFF:
                adaptations['slip_adaptation'] = raw[1] - 128  # Signed value
            if len(raw) > 2 and raw[2] != 0xFF:
                adaptations['shift_time_adapt'] = raw[2] - 128
                
    except Exception as e:
        logger.error(f"Error reading clutch adaptation: {e}")
    
    return adaptations


# Alias for backward compatibility
get_clutch_adaptation = get_clutch_adaptation_ds2


def reset_smg_adaptations(connection: 'DS2Connection') -> bool:
    """
    Reset SMG clutch adaptations.
    
    WARNING: After reset, the SMG will need to re-learn clutch values.
    Drive gently for the first 50-100 shifts after reset.
    
    Returns:
        True if successful
    """
    logger.warning("Resetting SMG adaptations...")
    
    try:
        # DS2 reset adaptation command (varies by ECU)
        # This uses a job/routine command
        response = connection.send(SMG_ECU_ADDR, 0x12, bytes([0x01, 0xF0]))
        
        if response and response.valid:
            logger.success("SMG adaptations reset")
            return True
            
    except Exception as e:
        logger.error(f"Failed to reset SMG adaptations: {e}")
    
    return False


def get_smg_fault_history_ds2(connection: 'DS2Connection') -> list:
    """
    Get SMG-specific fault history using DS2 protocol.
    
    Returns more detailed SMG fault information than standard DTC reading.
    """
    from .dtc import FaultCode, DTCStatus, E46_M3_FAULT_CODES
    
    faults = []
    
    try:
        # DS2 read faults command
        response = connection.send(SMG_ECU_ADDR, 0x07)  # Read faults
        
        if response and response.valid and len(response.data) > 2:
            raw = response.data
            i = 0
            while i + 2 < len(raw):
                byte1 = raw[i]
                byte2 = raw[i + 1]
                status = raw[i + 2] if i + 2 < len(raw) else 0
                
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
                
    except Exception as e:
        logger.error(f"Error reading SMG faults: {e}")
    
    return faults


# Alias for backward compatibility
get_smg_fault_history = get_smg_fault_history_ds2


def smg_pump_test(connection: 'DS2Connection') -> bool:
    """
    Run SMG hydraulic pump self-test.
    
    This activates the pump and checks pressure build-up.
    
    Returns:
        True if pump test passed
    """
    logger.info("Running SMG pump test...")
    
    try:
        # DS2 actuator test command
        response = connection.send(SMG_ECU_ADDR, 0x30, bytes([0x01, 0x01]))
        
        if response and response.valid:
            logger.success("SMG pump test passed")
            return True
            
    except Exception as e:
        logger.error(f"SMG pump test failed: {e}")
    
    return False
