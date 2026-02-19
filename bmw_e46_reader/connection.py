"""
BMW E46 Connection Module
~~~~~~~~~~~~~~~~~~~~~~~~~

Handles K+DCAN cable connection and communication protocols.
"""

import time
import serial
from typing import Optional, List, Tuple
from enum import Enum
from dataclasses import dataclass
from loguru import logger

from .config import (
    K_LINE_BAUD_RATE,
    ECU_ADDRESSES,
    SERIAL_PORT_PATTERNS,
)


class Protocol(Enum):
    """Communication protocol types"""
    K_LINE = "k_line"      # ISO 9141-2
    D_CAN = "d_can"        # ISO 15765-4


class ConnectionState(Enum):
    """Connection state enumeration"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class ECUInfo:
    """ECU identification information"""
    name: str
    address: int
    variant: str
    part_number: str
    sw_version: str
    hw_version: str


class E46Connection:
    """
    Main connection class for BMW E46 M3 K+DCAN communication.
    
    Supports both K-Line (ISO 9141-2) and D-CAN (ISO 15765-4) protocols.
    The E46 M3 primarily uses K-Line for most ECUs.
    
    Usage:
        with E46Connection('/dev/ttyUSB0') as car:
            engine_data = car.get_engine_data()
            print(f"RPM: {engine_data.rpm}")
    """
    
    def __init__(
        self,
        port: str,
        baud_rate: int = K_LINE_BAUD_RATE,
        protocol: Protocol = Protocol.K_LINE,
        timeout: float = 1.0
    ):
        """
        Initialize E46 connection.
        
        Args:
            port: Serial port path (e.g., '/dev/ttyUSB0')
            baud_rate: Communication baud rate (default: 10400 for K-Line)
            protocol: Communication protocol to use
            timeout: Serial timeout in seconds
        """
        self.port = port
        self.baud_rate = baud_rate
        self.protocol = protocol
        self.timeout = timeout
        self.state = ConnectionState.DISCONNECTED
        self._serial: Optional[serial.Serial] = None
        self._connected_ecus: List[ECUInfo] = []
        
    def __enter__(self):
        """Context manager entry"""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.disconnect()
        return False
    
    def connect(self) -> bool:
        """
        Establish connection to the vehicle.
        
        Returns:
            True if connection successful, False otherwise
        """
        logger.info(f"Connecting to {self.port}...")
        self.state = ConnectionState.CONNECTING
        
        try:
            self._serial = serial.Serial(
                port=self.port,
                baudrate=self.baud_rate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self.timeout,
                xonxoff=False,
                rtscts=False,
                dsrdtr=False
            )
            
            # Allow serial port to initialize
            time.sleep(0.5)
            
            # Perform protocol-specific initialization
            if self.protocol == Protocol.K_LINE:
                success = self._init_k_line()
            else:
                success = self._init_dcan()
                
            if success:
                self.state = ConnectionState.CONNECTED
                logger.success("Connected successfully")
                return True
            else:
                self.state = ConnectionState.ERROR
                logger.error("Failed to initialize communication")
                return False
                
        except serial.SerialException as e:
            self.state = ConnectionState.ERROR
            logger.error(f"Serial connection failed: {e}")
            raise ConnectionError(f"Failed to connect to {self.port}: {e}")
    
    def disconnect(self):
        """Close the connection"""
        if self._serial and self._serial.is_open:
            self._serial.close()
        self.state = ConnectionState.DISCONNECTED
        self._connected_ecus = []
        logger.info("Disconnected")
    
    def _init_k_line(self) -> bool:
        """
        Initialize K-Line communication using 5-baud init (ISO 9141-2).
        
        The E46 uses the slow init procedure for K-Line.
        """
        logger.debug("Initializing K-Line (5-baud init)")
        
        try:
            # Clear any pending data
            self._serial.reset_input_buffer()
            self._serial.reset_output_buffer()
            
            # Send 5-baud init address (0x33 for OBD-II)
            # This is done by bit-banging at 5 baud
            init_address = 0x33
            self._send_5baud_byte(init_address)
            
            # Wait for sync byte (0x55)
            time.sleep(0.3)
            response = self._serial.read(1)
            
            if response and response[0] == 0x55:
                logger.debug("Received sync byte 0x55")
                
                # Read keyword bytes
                keywords = self._serial.read(2)
                if len(keywords) == 2:
                    logger.debug(f"Keywords: {keywords.hex()}")
                    
                    # Send inverted second keyword as acknowledgment
                    ack = bytes([~keywords[1] & 0xFF])
                    time.sleep(0.025)  # W4 timing
                    self._serial.write(ack)
                    
                    # Wait for ECU to acknowledge
                    time.sleep(0.05)
                    ecu_ack = self._serial.read(1)
                    
                    if ecu_ack:
                        logger.debug(f"ECU acknowledged: {ecu_ack.hex()}")
                        return True
            
            # If slow init didn't work, try fast init
            logger.debug("Trying fast init...")
            return self._fast_init()
            
        except Exception as e:
            logger.error(f"K-Line init failed: {e}")
            return False
    
    def _send_5baud_byte(self, byte_val: int):
        """
        Send a byte at 5 baud by manipulating break condition.
        
        This simulates the slow init required by ISO 9141-2.
        """
        # Each bit takes 200ms at 5 baud
        bit_time = 0.2
        
        # Start bit (low)
        self._serial.break_condition = True
        time.sleep(bit_time)
        
        # Data bits (LSB first)
        for i in range(8):
            bit = (byte_val >> i) & 0x01
            self._serial.break_condition = not bit
            time.sleep(bit_time)
        
        # Stop bit (high)
        self._serial.break_condition = False
        time.sleep(bit_time)
    
    def _fast_init(self) -> bool:
        """
        Attempt fast initialization (ISO 14230 KWP2000).
        
        Some E46 modules support fast init.
        """
        try:
            # Send wake-up pattern (25ms low, 25ms high)
            self._serial.break_condition = True
            time.sleep(0.025)
            self._serial.break_condition = False
            time.sleep(0.025)
            
            # Send start communication request
            # Format: [length] [target] [source] [service] [checksum]
            start_comm = bytes([0x81, 0x10, 0xF1, 0x81])  # StartCommunication
            checksum = sum(start_comm) & 0xFF
            start_comm += bytes([checksum])
            
            self._serial.write(start_comm)
            time.sleep(0.1)
            
            response = self._serial.read(10)
            if response and len(response) >= 4:
                logger.debug(f"Fast init response: {response.hex()}")
                return True
                
            return False
            
        except Exception as e:
            logger.error(f"Fast init failed: {e}")
            return False
    
    def _init_dcan(self) -> bool:
        """
        Initialize D-CAN communication.
        
        Late E46s and some modules use CAN communication.
        """
        logger.debug("Initializing D-CAN")
        
        # D-CAN typically requires 500kbps
        if self.baud_rate != 500000:
            self._serial.baudrate = 500000
        
        # Send tester present message
        tester_present = bytes([0x3E, 0x00])
        self._serial.write(tester_present)
        time.sleep(0.1)
        
        response = self._serial.read(5)
        if response:
            logger.debug(f"D-CAN response: {response.hex()}")
            return True
            
        return False
    
    def send_command(
        self,
        service_id: int,
        data: bytes = b'',
        target_ecu: int = ECU_ADDRESSES['DME']
    ) -> Optional[bytes]:
        """
        Send a diagnostic command and receive response.
        
        Args:
            service_id: OBD/KWP2000 service ID
            data: Additional command data
            target_ecu: Target ECU address (default: DME)
            
        Returns:
            Response bytes or None if failed
        """
        if self.state != ConnectionState.CONNECTED:
            logger.error("Not connected")
            return None
            
        try:
            # Build message based on protocol
            if self.protocol == Protocol.K_LINE:
                message = self._build_k_line_message(service_id, data, target_ecu)
            else:
                message = self._build_can_message(service_id, data)
            
            # Send message
            self._serial.reset_input_buffer()
            self._serial.write(message)
            
            # Wait for response
            time.sleep(0.05)
            
            # Read response
            response = self._read_response()
            return response
            
        except Exception as e:
            logger.error(f"Command failed: {e}")
            return None
    
    def _build_k_line_message(
        self,
        service_id: int,
        data: bytes,
        target_ecu: int
    ) -> bytes:
        """Build K-Line formatted message"""
        source = 0xF1  # Tester address
        
        # Calculate length byte
        msg_len = 1 + len(data)  # service_id + data
        
        if msg_len <= 63:
            # Short format: length in header
            header = bytes([0x80 | msg_len, target_ecu, source])
        else:
            # Long format: separate length byte
            header = bytes([0x80, target_ecu, source, msg_len])
        
        body = bytes([service_id]) + data
        
        # Calculate checksum
        full_msg = header + body
        checksum = sum(full_msg) & 0xFF
        
        return full_msg + bytes([checksum])
    
    def _build_can_message(self, service_id: int, data: bytes) -> bytes:
        """Build CAN formatted message"""
        # Standard OBD-II CAN format
        msg_len = 1 + len(data)
        return bytes([msg_len, service_id]) + data
    
    def _read_response(self, max_bytes: int = 256) -> Optional[bytes]:
        """Read and parse response from ECU"""
        try:
            # Read header to determine message length
            header = self._serial.read(3)
            if len(header) < 3:
                return None
            
            # Parse length from header
            if header[0] & 0x80:
                # Length in first byte
                msg_len = header[0] & 0x3F
            else:
                # Length in separate byte
                length_byte = self._serial.read(1)
                if not length_byte:
                    return None
                msg_len = length_byte[0]
            
            # Read body + checksum
            body = self._serial.read(msg_len + 1)  # +1 for checksum
            
            if len(body) < msg_len + 1:
                return None
            
            # Verify checksum
            full_msg = header + body[:-1]
            expected_checksum = sum(full_msg) & 0xFF
            
            if body[-1] != expected_checksum:
                logger.warning("Checksum mismatch in response")
            
            # Return just the data portion
            return body[:-1]
            
        except Exception as e:
            logger.error(f"Error reading response: {e}")
            return None
    
    def query_pid(self, pid: int, mode: int = 0x01) -> Optional[bytes]:
        """
        Query a standard OBD-II PID.
        
        Args:
            pid: PID to query
            mode: OBD mode (default: 0x01 for current data)
            
        Returns:
            Response data bytes or None
        """
        return self.send_command(mode, bytes([pid]))
    
    def get_vin(self) -> Optional[str]:
        """Get Vehicle Identification Number"""
        response = self.send_command(0x09, bytes([0x02]))
        if response and len(response) >= 17:
            try:
                return response[:17].decode('ascii')
            except:
                return response[:17].hex()
        return None
    
    def get_ecu_info(self, ecu_address: int) -> Optional[ECUInfo]:
        """
        Get ECU identification information.
        
        Args:
            ecu_address: Target ECU address
            
        Returns:
            ECUInfo object or None
        """
        # Send ReadECUIdentification request
        response = self.send_command(0x1A, bytes([0x87]), ecu_address)
        
        if response:
            # Parse response into ECUInfo
            # Format varies by ECU
            try:
                return ECUInfo(
                    name=self._ecu_name_from_address(ecu_address),
                    address=ecu_address,
                    variant="",
                    part_number=response[:10].decode('ascii', errors='ignore').strip(),
                    sw_version="",
                    hw_version=""
                )
            except:
                pass
        return None
    
    def _ecu_name_from_address(self, address: int) -> str:
        """Get ECU name from address"""
        for name, addr in ECU_ADDRESSES.items():
            if addr == address:
                return name
        return f"Unknown (0x{address:02X})"
    
    def get_engine_data(self):
        """Get current engine data"""
        from .engine import get_engine_data
        return get_engine_data(self)
    
    def get_fault_codes(self):
        """Get stored fault codes"""
        from .dtc import get_fault_codes
        return get_fault_codes(self)
    
    def clear_fault_codes(self):
        """Clear stored fault codes"""
        from .dtc import clear_fault_codes
        return clear_fault_codes(self)
    
    def get_smg_data(self):
        """Get SMG transmission data"""
        from .smg import get_smg_data
        return get_smg_data(self)
    
    @property
    def is_connected(self) -> bool:
        """Check if currently connected"""
        return self.state == ConnectionState.CONNECTED


def find_available_ports() -> List[str]:
    """
    Find available serial ports that might be K+DCAN cables.
    
    Returns:
        List of available port paths
    """
    import sys
    import glob
    
    if sys.platform.startswith('linux'):
        ports = glob.glob('/dev/ttyUSB*') + glob.glob('/dev/ttyACM*')
    elif sys.platform == 'darwin':
        ports = glob.glob('/dev/tty.usbserial*') + glob.glob('/dev/tty.wchusbserial*')
    elif sys.platform == 'win32':
        # Check COM ports 1-20
        ports = []
        for i in range(1, 21):
            try:
                s = serial.Serial(f'COM{i}')
                s.close()
                ports.append(f'COM{i}')
            except serial.SerialException:
                pass
    else:
        ports = []
    
    return sorted(ports)


def auto_connect() -> Optional[E46Connection]:
    """
    Automatically find and connect to E46.
    
    Returns:
        E46Connection object or None if no connection found
    """
    ports = find_available_ports()
    
    if not ports:
        logger.warning("No serial ports found")
        return None
    
    for port in ports:
        logger.info(f"Trying {port}...")
        try:
            conn = E46Connection(port)
            if conn.connect():
                return conn
        except Exception as e:
            logger.debug(f"Failed: {e}")
            continue
    
    return None
