"""
BMW E46 Diagnostic Trouble Codes (DTC) Module
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Read and clear fault codes from ECUs.
"""

from dataclasses import dataclass
from typing import List, Optional, TYPE_CHECKING
from enum import Enum
from loguru import logger

from .config import E46_M3_FAULT_CODES, ECU_ADDRESSES

if TYPE_CHECKING:
    from .connection import E46Connection


class DTCStatus(Enum):
    """DTC status flags"""
    CONFIRMED = "confirmed"
    PENDING = "pending"
    PERMANENT = "permanent"
    CLEARED = "cleared"


@dataclass
class FaultCode:
    """
    Diagnostic Trouble Code container.
    """
    code: str
    description: str
    status: DTCStatus
    ecu: str
    freeze_frame: Optional[dict] = None
    
    def __str__(self) -> str:
        return f"{self.code}: {self.description} ({self.status.value})"
    
    def to_dict(self) -> dict:
        return {
            'code': self.code,
            'description': self.description,
            'status': self.status.value,
            'ecu': self.ecu,
            'freeze_frame': self.freeze_frame,
        }


def _decode_dtc(byte1: int, byte2: int) -> str:
    """
    Decode DTC bytes into standard format.
    
    DTC format: PXXXX, CXXXX, BXXXX, or UXXXX
    First 2 bits of byte1 determine type:
    - 00 = P (Powertrain)
    - 01 = C (Chassis)
    - 10 = B (Body)
    - 11 = U (Network)
    
    Args:
        byte1: First DTC byte
        byte2: Second DTC byte
        
    Returns:
        DTC string (e.g., "P0300")
    """
    # Type prefix
    type_bits = (byte1 >> 6) & 0x03
    type_prefix = ['P', 'C', 'B', 'U'][type_bits]
    
    # First digit
    digit1 = (byte1 >> 4) & 0x03
    
    # Second digit
    digit2 = byte1 & 0x0F
    
    # Third and fourth digits
    digit3 = (byte2 >> 4) & 0x0F
    digit4 = byte2 & 0x0F
    
    return f"{type_prefix}{digit1}{digit2:X}{digit3:X}{digit4:X}"


def _get_dtc_description(code: str) -> str:
    """Get description for DTC code"""
    if code in E46_M3_FAULT_CODES:
        return E46_M3_FAULT_CODES[code]
    return "Unknown fault code"


def get_fault_codes(
    connection: 'E46Connection',
    include_pending: bool = True,
    include_permanent: bool = True
) -> List[FaultCode]:
    """
    Read all stored fault codes from all ECUs.
    
    Args:
        connection: Active E46Connection
        include_pending: Include pending (mode 07) codes
        include_permanent: Include permanent (mode 0A) codes
        
    Returns:
        List of FaultCode objects
    """
    fault_codes = []
    
    # Read confirmed DTCs (Mode 03)
    logger.debug("Reading confirmed DTCs...")
    confirmed = _read_dtcs_mode(connection, 0x03, DTCStatus.CONFIRMED)
    fault_codes.extend(confirmed)
    
    # Read pending DTCs (Mode 07)
    if include_pending:
        logger.debug("Reading pending DTCs...")
        pending = _read_dtcs_mode(connection, 0x07, DTCStatus.PENDING)
        fault_codes.extend(pending)
    
    # Read permanent DTCs (Mode 0A) - OBD-II 2010+
    if include_permanent:
        logger.debug("Reading permanent DTCs...")
        permanent = _read_dtcs_mode(connection, 0x0A, DTCStatus.PERMANENT)
        fault_codes.extend(permanent)
    
    # Also check BMW-specific modules
    for ecu_name, ecu_addr in ECU_ADDRESSES.items():
        if ecu_name not in ['DME']:  # DME already covered by OBD
            bmw_codes = _read_bmw_dtcs(connection, ecu_addr, ecu_name)
            fault_codes.extend(bmw_codes)
    
    logger.info(f"Found {len(fault_codes)} fault code(s)")
    return fault_codes


def _read_dtcs_mode(
    connection: 'E46Connection',
    mode: int,
    status: DTCStatus
) -> List[FaultCode]:
    """Read DTCs using specific OBD mode"""
    codes = []
    
    response = connection.send_command(mode)
    
    if response and len(response) >= 2:
        # First byte is number of codes (after service ID)
        service_id = response[0]
        
        if service_id == (mode + 0x40):  # Positive response
            # Parse DTC pairs
            i = 1
            while i + 1 < len(response):
                byte1 = response[i]
                byte2 = response[i + 1]
                
                # Skip empty codes (0x0000)
                if byte1 != 0 or byte2 != 0:
                    code = _decode_dtc(byte1, byte2)
                    description = _get_dtc_description(code)
                    
                    codes.append(FaultCode(
                        code=code,
                        description=description,
                        status=status,
                        ecu='DME'
                    ))
                    
                i += 2
    
    return codes


def _read_bmw_dtcs(
    connection: 'E46Connection',
    ecu_address: int,
    ecu_name: str
) -> List[FaultCode]:
    """Read DTCs from BMW-specific ECU using KWP2000"""
    codes = []
    
    # BMW uses ReadDTCByStatus (0x18) service
    # Status mask 0xFF = all DTCs
    response = connection.send_command(0x18, bytes([0xFF]), ecu_address)
    
    if response and len(response) >= 3:
        # Parse BMW DTC format
        i = 1
        while i + 2 < len(response):
            byte1 = response[i]
            byte2 = response[i + 1]
            status_byte = response[i + 2]
            
            if byte1 != 0 or byte2 != 0:
                code = _decode_dtc(byte1, byte2)
                description = _get_dtc_description(code)
                
                # Determine status from BMW status byte
                if status_byte & 0x80:
                    dtc_status = DTCStatus.CONFIRMED
                elif status_byte & 0x01:
                    dtc_status = DTCStatus.PENDING
                else:
                    dtc_status = DTCStatus.CONFIRMED
                
                codes.append(FaultCode(
                    code=code,
                    description=description,
                    status=dtc_status,
                    ecu=ecu_name
                ))
            
            i += 3
    
    return codes


def get_dtc_count(connection: 'E46Connection') -> int:
    """
    Get the number of stored DTCs without reading them all.
    
    Returns:
        Number of DTCs stored
    """
    response = connection.send_command(0x01, bytes([0x01]))
    
    if response and len(response) >= 3:
        # Mode 01 PID 01: Number of DTCs
        mil_on = bool(response[2] & 0x80)
        dtc_count = response[2] & 0x7F
        
        if mil_on:
            logger.warning("MIL (Check Engine Light) is ON")
        
        return dtc_count
    
    return 0


def get_freeze_frame(
    connection: 'E46Connection',
    dtc_code: str
) -> Optional[dict]:
    """
    Get freeze frame data for a specific DTC.
    
    Freeze frame stores engine conditions at the time the DTC was set.
    
    Args:
        dtc_code: DTC code to get freeze frame for
        
    Returns:
        Dictionary of freeze frame data or None
    """
    # Mode 02: Request freeze frame data
    # This gets frame 0 (most recent)
    pids_to_read = [0x02, 0x03, 0x04, 0x05, 0x0C, 0x0D, 0x11]
    
    freeze_data = {}
    
    for pid in pids_to_read:
        response = connection.send_command(0x02, bytes([pid, 0x00]))
        
        if response and len(response) >= 4:
            # Parse based on PID
            if pid == 0x04:  # Engine load
                freeze_data['engine_load'] = response[3] * 100 / 255
            elif pid == 0x05:  # Coolant temp
                freeze_data['coolant_temp'] = response[3] - 40
            elif pid == 0x0C:  # RPM
                if len(response) >= 5:
                    freeze_data['rpm'] = (response[3] * 256 + response[4]) / 4
            elif pid == 0x0D:  # Speed
                freeze_data['speed'] = response[3]
            elif pid == 0x11:  # Throttle
                freeze_data['throttle'] = response[3] * 100 / 255
    
    return freeze_data if freeze_data else None


def clear_fault_codes(connection: 'E46Connection') -> bool:
    """
    Clear all stored DTCs and turn off MIL.
    
    WARNING: This will clear ALL fault codes from the vehicle.
    Make sure to record codes before clearing if needed.
    
    Args:
        connection: Active E46Connection
        
    Returns:
        True if successful, False otherwise
    """
    logger.warning("Clearing all fault codes...")
    
    # Mode 04: Clear DTCs
    response = connection.send_command(0x04)
    
    if response and len(response) >= 1:
        if response[0] == 0x44:  # Positive response
            logger.success("Fault codes cleared successfully")
            return True
        elif response[0] == 0x7F:  # Negative response
            logger.error("ECU rejected clear request")
            return False
    
    # Also clear BMW-specific ECUs
    for ecu_name, ecu_addr in ECU_ADDRESSES.items():
        # BMW ClearDTC service (0x14)
        connection.send_command(0x14, bytes([0xFF, 0x00]), ecu_addr)
    
    return True


def print_fault_codes(codes: List[FaultCode]):
    """Pretty print fault codes to console"""
    if not codes:
        print("No fault codes stored")
        return
    
    print(f"\n{'='*60}")
    print(f"{'DTC':<8} {'Status':<12} {'ECU':<8} Description")
    print(f"{'='*60}")
    
    for code in codes:
        print(f"{code.code:<8} {code.status.value:<12} {code.ecu:<8} {code.description[:35]}")
    
    print(f"{'='*60}")
    print(f"Total: {len(codes)} fault code(s)\n")
