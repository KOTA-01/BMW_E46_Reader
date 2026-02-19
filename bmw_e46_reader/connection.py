"""
BMW E46 Connection Module
~~~~~~~~~~~~~~~~~~~~~~~~~

Handles K+DCAN cable connection and KWP2000/ISO 9141-2 communication.

Note: E46 M3 uses BMW's proprietary protocols. For full functionality with
SMG data, VANOS, etc., consider using:
- Deep OBD (Android app) with INPA cable
- INPA/EDIABAS on Windows
- BMW Standard Tools

This module implements standard OBD-II and attempts BMW protocols.
"""

import time
import serial
from typing import Optional, List, Tuple, Dict, Any
from enum import Enum
from dataclasses import dataclass
from loguru import logger

from .config import (
    K_LINE_BAUD_RATE,
    ECU_ADDRESSES,
)


class Protocol(Enum):
    """Communication protocol types"""
    K_LINE = "k_line"
    D_CAN = "d_can"


class ConnectionState(Enum):
    """Connection state"""
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
    BMW E46 M3 K+DCAN communication handler.
    
    Implements KWP2000 (ISO 14230) protocol for BMW diagnostics.
    """
    
    def __init__(
        self,
        port: str,
        baud_rate: int = K_LINE_BAUD_RATE,
        protocol: Protocol = Protocol.K_LINE,
        timeout: float = 2.0
    ):
        self.port = port
        self.baud_rate = baud_rate
        self.protocol = protocol
        self.timeout = timeout
        self.state = ConnectionState.DISCONNECTED
        self._serial: Optional[serial.Serial] = None
        self._initialized = False
        
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
        return False
    
    def connect(self) -> bool:
        """Establish connection to vehicle"""
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
                write_timeout=self.timeout,
            )
            
            time.sleep(0.5)
            self._serial.reset_input_buffer()
            self._serial.reset_output_buffer()
            
            # Set RTS low for K-line mode on INPA cables
            self._serial.rts = False
            self._serial.dtr = True
            
            # Try fast init first
            success = self._fast_init()
            
            if not success:
                # Try slow init
                logger.info("Fast init failed, trying slow init...")
                success, keywords = self._slow_init()
            
            if success:
                self.state = ConnectionState.CONNECTED
                self._initialized = True
                logger.success("Connected successfully")
                return True
            else:
                # Some cables work without explicit init
                self.state = ConnectionState.CONNECTED
                self._initialized = True
                logger.warning("Init unclear, attempting anyway")
                return True
                
        except serial.SerialException as e:
            self.state = ConnectionState.ERROR
            logger.error(f"Serial connection failed: {e}")
            raise ConnectionError(f"Failed to connect to {self.port}: {e}")
    
    def disconnect(self):
        """Close connection"""
        if self._serial and self._serial.is_open:
            try:
                self._send_stop_communication()
            except:
                pass
            self._serial.close()
        self.state = ConnectionState.DISCONNECTED
        self._initialized = False
        logger.info("Disconnected")
    
    def _fast_init(self) -> bool:
        """KWP2000 fast initialization - 25ms break pulse"""
        logger.debug("Fast init...")
        
        try:
            # Break signal: 25ms low, 25ms high
            self._serial.break_condition = True
            time.sleep(0.025)
            self._serial.break_condition = False
            time.sleep(0.025)
            
            # StartCommunication request
            msg = self._build_message(0x81, b'', target=0x10)
            self._serial.write(msg)
            self._serial.flush()
            
            time.sleep(0.1)
            
            # Read echo + response
            response = self._serial.read(100)
            logger.debug(f"Init response ({len(response)} bytes): {response.hex() if response else 'empty'}")
            
            # Look for positive response 0xC1
            if b'\xc1' in response:
                return True
            
            # Any response suggests communication is possible
            return len(response) > 0
            
        except Exception as e:
            logger.error(f"Fast init error: {e}")
            return False
    
    def _slow_init(self, address: int = 0x33) -> Tuple[bool, Optional[Tuple[int, int]]]:
        """
        ISO 9141-2 slow init (5-baud address).
        
        Returns: (success, (keyword1, keyword2) or None)
        """
        logger.debug(f"Slow init to 0x{address:02X}...")
        
        try:
            self._serial.reset_input_buffer()
            bit_time = 0.2  # 5 baud = 200ms per bit
            
            # Send address at 5 baud using break signal
            # Start bit (low)
            self._serial.break_condition = True
            time.sleep(bit_time)
            
            # 8 data bits, LSB first
            for i in range(8):
                bit = (address >> i) & 1
                self._serial.break_condition = (bit == 0)
                time.sleep(bit_time)
            
            # Stop bit (high)
            self._serial.break_condition = False
            time.sleep(bit_time)
            
            # Wait for ECU response
            time.sleep(0.3)
            response = self._serial.read(20)
            
            logger.debug(f"Slow init response: {response.hex() if response else 'None'}")
            
            # Look for sync byte 0x55
            if response and 0x55 in response:
                idx = list(response).index(0x55)
                if len(response) > idx + 2:
                    k1 = response[idx + 1]
                    k2 = response[idx + 2]
                    logger.info(f"Got sync! Keywords: 0x{k1:02X} 0x{k2:02X}")
                    
                    # Send inverted K2 to complete handshake
                    inv_k2 = (~k2) & 0xFF
                    time.sleep(0.025)  # W4 timing
                    self._serial.write(bytes([inv_k2]))
                    time.sleep(0.1)
                    
                    # Read echo (and possible ECU ack)
                    ack = self._serial.read(10)
                    logger.debug(f"Handshake response: {ack.hex() if ack else 'None'}")
                    
                    return True, (k1, k2)
            
            return False, None
            
        except Exception as e:
            logger.error(f"Slow init error: {e}")
            return False, None
    
    def _send_stop_communication(self):
        """Send stop communication service"""
        msg = self._build_message(0x82, b'')
        self._serial.write(msg)
        self._serial.flush()
    
    def _build_message(self, service: int, data: bytes, target: int = 0x10) -> bytes:
        """
        Build KWP2000 message.
        
        Format: [FMT] [TGT] [SRC] [DATA...] [CS]
        FMT = 0x80 | length (for lengths <= 63)
        """
        source = 0xF1  # Tester address
        payload = bytes([service]) + data
        length = len(payload)
        
        if length <= 63:
            header = bytes([0x80 | length, target, source])
        else:
            header = bytes([0x80, target, source, length])
        
        full_msg = header + payload
        checksum = sum(full_msg) & 0xFF
        
        return full_msg + bytes([checksum])
    
    def send_command(
        self,
        service: int,
        data: bytes = b'',
        target: int = 0x10
    ) -> Optional[bytes]:
        """
        Send OBD/KWP2000 command and get response.
        
        Args:
            service: Service ID (0x01=current data, 0x03=DTCs, 0x21=BMW local ID, etc.)
            data: Additional data bytes
            target: Target address (0x10=OBD broadcast, 0x12=DME, 0x32=EGS)
            
        Returns:
            Response data (without header/checksum) or None
        """
        if not self._serial or not self._serial.is_open:
            logger.error("Not connected")
            return None
        
        try:
            msg = self._build_message(service, data, target)
            
            logger.debug(f"TX [{target:02X}]: {service:02X} {data.hex() if data else ''}")
            
            self._serial.reset_input_buffer()
            self._serial.write(msg)
            self._serial.flush()
            
            # K-line is half-duplex - read echo + response
            time.sleep(0.1)
            
            raw = self._serial.read(256)
            
            if not raw:
                logger.debug("No response")
                return None
            
            logger.debug(f"RX raw ({len(raw)} bytes): {raw.hex()}")
            
            # Parse response - skip echo, find ECU response
            response = self._parse_response(raw, len(msg))
            
            if response:
                logger.debug(f"RX data: {response.hex()}")
            
            return response
            
        except Exception as e:
            logger.error(f"Command error: {e}")
            return None
    
    def _parse_response(self, raw: bytes, echo_len: int) -> Optional[bytes]:
        """
        Parse KWP2000 response from raw data.
        
        Skips the echo and extracts ECU response data.
        """
        if len(raw) <= echo_len:
            return None
        
        # Skip echo
        data = raw[echo_len:]
        
        if len(data) < 4:
            return None
        
        try:
            # Parse format byte
            fmt = data[0]
            
            if fmt & 0x80:
                # Length in format byte
                length = fmt & 0x3F
                
                # Skip format + target + source
                if len(data) >= 3 + length:
                    # Return payload (skip header, exclude checksum)
                    return data[3:3+length]
            
            # Fallback: return everything after minimal header
            if len(data) >= 4:
                return data[3:-1] if len(data) > 4 else data[3:]
                
        except Exception as e:
            logger.debug(f"Parse error: {e}")
        
        return None
    
    def query_pid(self, pid: int, mode: int = 0x01) -> Optional[bytes]:
        """Query standard OBD-II PID"""
        return self.send_command(mode, bytes([pid]))
    
    def read_local_id(self, local_id: int, ecu: int = 0x12) -> Optional[bytes]:
        """Read BMW local identifier (service 0x21)"""
        return self.send_command(0x21, bytes([local_id]), ecu)
    
    def read_memory(self, address: int, size: int, ecu: int = 0x12) -> Optional[bytes]:
        """Read ECU memory (service 0x23)"""
        addr_bytes = address.to_bytes(3, 'big')
        return self.send_command(0x23, addr_bytes + bytes([size]), ecu)
    
    def tester_present(self):
        """Send TesterPresent to keep session alive"""
        self.send_command(0x3E)
    
    def get_vin(self) -> Optional[str]:
        """Get Vehicle Identification Number"""
        response = self.send_command(0x09, bytes([0x02]))
        if response and len(response) >= 18:
            try:
                return response[1:18].decode('ascii', errors='ignore')
            except:
                pass
        return None
    
    def get_ecu_info(self, ecu_address: int) -> Optional[ECUInfo]:
        """Get ECU identification"""
        response = self.send_command(0x1A, bytes([0x87]), ecu_address)
        
        if response and len(response) > 1:
            return ECUInfo(
                name=self._ecu_name_from_address(ecu_address),
                address=ecu_address,
                variant="",
                part_number=response[1:].decode('ascii', errors='ignore').strip(),
                sw_version="",
                hw_version=""
            )
        return None
    
    def _ecu_name_from_address(self, address: int) -> str:
        for name, addr in ECU_ADDRESSES.items():
            if addr == address:
                return name
        return f"ECU_0x{address:02X}"
    
    # Convenience methods
    def get_engine_data(self):
        from .engine import get_engine_data
        return get_engine_data(self)
    
    def get_fault_codes(self):
        from .dtc import get_fault_codes
        return get_fault_codes(self)
    
    def clear_fault_codes(self):
        from .dtc import clear_fault_codes
        return clear_fault_codes(self)
    
    def get_smg_data(self):
        from .smg import get_smg_data
        return get_smg_data(self)
    
    @property
    def is_connected(self) -> bool:
        return self.state == ConnectionState.CONNECTED

    def run_diagnostics(self) -> Dict[str, Any]:
        """
        Run diagnostic tests to identify communication issues.
        
        Returns dict with test results.
        """
        results = {
            'port': self.port,
            'baud': self.baud_rate,
            'tests': {}
        }
        
        if not self._serial or not self._serial.is_open:
            results['error'] = 'Not connected'
            return results
        
        # Test 1: Echo test
        logger.info("Testing K-line echo...")
        self._serial.reset_input_buffer()
        test_byte = bytes([0xAA])
        self._serial.write(test_byte)
        time.sleep(0.1)
        echo = self._serial.read(10)
        results['tests']['echo'] = {
            'sent': test_byte.hex(),
            'received': echo.hex() if echo else 'None',
            'working': echo == test_byte
        }
        
        # Test 2: Slow init (5-baud)
        logger.info("Testing ISO 9141-2 slow init...")
        success, keywords = self._slow_init(0x33)
        results['tests']['slow_init'] = {
            'success': success,
            'keywords': f"0x{keywords[0]:02X} 0x{keywords[1]:02X}" if keywords else None
        }
        
        # Test 3: Fast init (KWP2000)
        logger.info("Testing KWP2000 fast init...")
        fast_ok = self._fast_init()
        results['tests']['fast_init'] = {
            'success': fast_ok
        }
        
        # Test 4: OBD-II Mode 01 PID 00
        logger.info("Testing OBD-II Mode 01...")
        if success:  # Use slow init first if it works
            time.sleep(0.05)
        
        self._serial.reset_input_buffer()
        msg = bytes([0x68, 0x6A, 0xF1, 0x01, 0x00])
        cs = sum(msg) & 0xFF
        self._serial.write(msg + bytes([cs]))
        time.sleep(0.3)
        resp = self._serial.read(100)
        echo_len = 6
        got_response = len(resp) > echo_len if resp else False
        results['tests']['obd_mode01'] = {
            'raw_response': resp.hex() if resp else 'None',
            'got_ecu_response': got_response,
            'ecu_data': resp[echo_len:].hex() if got_response else None
        }
        
        # Summary
        results['summary'] = {
            'echo_working': results['tests']['echo']['working'],
            'init_working': success,
            'ecu_responding': got_response,
        }
        
        if not got_response and success:
            results['notes'] = [
                "K-line init works but ECU doesn't respond to commands.",
                "This is common with BMW gateway modules.",
                "Try: Deep OBD app (Android) or INPA on Windows."
            ]
        
        return results


class DS2Connection:
    """
    BMW DS2 Protocol Communication Handler.
    
    Based on research from:
    - pBmwScanner (https://github.com/gigijoe/pBmwScanner)
    - Diolum's gateway analysis (http://www.diolum.fr/analyse-gateway-e46)
    - EdiabasLib (https://github.com/uholeschak/ediabaslib)
    
    DS2 Protocol Format:
    [ADDRESS][LENGTH][DATA...][XOR_CHECKSUM]
    
    Settings: 9600 baud, 8E1 (8 data bits, EVEN parity, 1 stop bit)
    """
    
    # Common ECU addresses
    DME = 0x12      # Digital Motor Electronics
    EGS = 0x32      # SMG/Transmission
    DSC = 0x56      # Dynamic Stability Control
    IHKA = 0x5B     # Climate Control
    IKE = 0x80      # Instrument Cluster
    AIRBAG = 0xA4   # Multi Restraint System
    LCM = 0xD0      # Light Control Module
    RLS = 0xE8      # Rain/Light Sensor
    
    def __init__(self, port: str, timeout: float = 0.5):
        self.port = port
        self.timeout = timeout
        self._serial: Optional[serial.Serial] = None
    
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
        return False
    
    def connect(self) -> bool:
        """Open serial connection with DS2 settings"""
        try:
            self._serial = serial.Serial(
                port=self.port,
                baudrate=9600,              # DS2 uses 9600 baud
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_EVEN,  # EVEN parity is critical!
                stopbits=serial.STOPBITS_ONE,
                timeout=self.timeout,
                write_timeout=self.timeout,
            )
            
            # INPA cable in K-line mode
            self._serial.rts = False
            self._serial.dtr = True
            
            time.sleep(0.1)
            self._serial.reset_input_buffer()
            self._serial.reset_output_buffer()
            
            logger.info(f"DS2 connection opened on {self.port}")
            return True
            
        except serial.SerialException as e:
            logger.error(f"DS2 connection failed: {e}")
            return False
    
    def disconnect(self):
        """Close serial connection"""
        if self._serial and self._serial.is_open:
            self._serial.close()
            logger.info("DS2 connection closed")
    
    @staticmethod
    def _checksum(data: bytes) -> int:
        """Calculate XOR checksum"""
        result = 0
        for b in data:
            result ^= b
        return result
    
    def _write(self, address: int, payload: bytes) -> None:
        """
        Send DS2 message.
        
        Format: [ADDRESS][LENGTH][PAYLOAD...][CHECKSUM]
        Length = address + length byte + payload + checksum
        """
        length = 2 + len(payload) + 1  # addr + len + payload + checksum
        msg = bytes([address, length]) + payload
        checksum = self._checksum(msg)
        full_msg = msg + bytes([checksum])
        
        logger.debug(f"DS2 TX: {full_msg.hex()}")
        self._serial.write(full_msg)
    
    def _read(self) -> Optional[bytes]:
        """
        Read DS2 response.
        
        Returns full message including checksum, or None on timeout/error.
        """
        try:
            # Read address byte
            addr_byte = self._serial.read(1)
            if not addr_byte:
                return None
            
            # Read length byte
            len_byte = self._serial.read(1)
            if not len_byte:
                return None
            
            address = addr_byte[0]
            length = len_byte[0]
            
            # Read remaining bytes (length - 2 already read)
            remaining = length - 2
            if remaining > 0:
                data = self._serial.read(remaining)
                if len(data) < remaining:
                    logger.warning(f"DS2 RX incomplete: expected {remaining}, got {len(data)}")
                    return None
            else:
                data = b''
            
            full_msg = addr_byte + len_byte + data
            
            # Verify checksum
            expected_cs = self._checksum(full_msg[:-1])
            actual_cs = full_msg[-1]
            
            if expected_cs != actual_cs:
                logger.warning(f"DS2 checksum mismatch: expected {expected_cs:02X}, got {actual_cs:02X}")
            
            logger.debug(f"DS2 RX: {full_msg.hex()}")
            return full_msg
            
        except Exception as e:
            logger.error(f"DS2 RX error: {e}")
            return None
    
    def execute(self, address: int, command: bytes) -> Optional[bytes]:
        """
        Send DS2 command and receive response.
        
        Args:
            address: Target ECU address
            command: Command bytes to send
            
        Returns:
            Response bytes (excluding echo), or None on error
        """
        self._serial.reset_input_buffer()
        self._write(address, command)
        
        # Read echo (DS2 is half-duplex K-line)
        echo = self._read()
        
        # Read actual response
        response = self._read()
        
        if response is None:
            logger.warning(f"No response from ECU 0x{address:02X}")
            return None
        
        # Check response status
        if len(response) > 2:
            status = response[2]
            if status == 0xA0:
                pass  # Success
            elif status == 0xA1:
                logger.warning("ECU busy")
            elif status == 0xA2:
                logger.warning("Invalid parameter")
            elif status == 0xFF:
                logger.warning("Invalid command")
            else:
                logger.debug(f"Response status: 0x{status:02X}")
        
        return response
    
    def read_identity(self, address: int) -> Optional[Dict[str, Any]]:
        """Read ECU identity (command 0x00)"""
        response = self.execute(address, bytes([0x00]))
        if response and len(response) > 3:
            return {
                'raw': response.hex(),
                'address': response[0],
                'length': response[1],
                'status': response[2] if len(response) > 2 else None,
                'data': response[3:] if len(response) > 3 else b'',
            }
        return None
    
    def read_status(self, address: int) -> Optional[Dict[str, Any]]:
        """Read ECU status (command 0x0B)"""
        response = self.execute(address, bytes([0x0B]))
        if response and len(response) > 3:
            return {
                'raw': response.hex(),
                'address': response[0],
                'length': response[1],
                'status': response[2] if len(response) > 2 else None,
                'data': response[3:] if len(response) > 3 else b'',
            }
        return None
    
    def read_faults(self, address: int) -> Optional[Dict[str, Any]]:
        """Read stored fault codes (command 0x07)"""
        response = self.execute(address, bytes([0x07]))
        if response and len(response) > 3:
            return {
                'raw': response.hex(),
                'address': response[0],
                'length': response[1],
                'status': response[2] if len(response) > 2 else None,
                'data': response[3:] if len(response) > 3 else b'',
            }
        return None
    
    def send(self, address: int, command: int, data: bytes = b'') -> Optional['DS2Response']:
        """
        Send DS2 command and return structured response.
        
        Compatible with ds2.py DS2Connection interface.
        
        Args:
            address: Target ECU address
            command: DS2 command byte
            data: Additional data bytes
            
        Returns:
            DS2Response-like object with .valid and .data attributes
        """
        cmd_bytes = bytes([command]) + data
        response = self.execute(address, cmd_bytes)
        
        if response and len(response) > 2:
            # Create a simple response object
            class DS2Response:
                def __init__(self, raw_response: bytes):
                    self.address = raw_response[0]
                    self.length = raw_response[1]
                    self.status = raw_response[2] if len(raw_response) > 2 else 0
                    self.data = raw_response[3:-1] if len(raw_response) > 4 else b''
                    self.valid = self.status == 0xA0  # 0xA0 = success
                    self.raw = raw_response
            
            return DS2Response(response)
        return None


def find_available_ports() -> List[str]:
    """Find available serial ports"""
    import sys
    import glob
    
    if sys.platform.startswith('linux'):
        ports = glob.glob('/dev/ttyUSB*') + glob.glob('/dev/ttyACM*')
    elif sys.platform == 'darwin':
        ports = glob.glob('/dev/tty.usbserial*') + glob.glob('/dev/tty.wchusbserial*')
    elif sys.platform == 'win32':
        ports = []
        for i in range(1, 21):
            try:
                s = serial.Serial(f'COM{i}')
                s.close()
                ports.append(f'COM{i}')
            except:
                pass
    else:
        ports = []
    
    return sorted(ports)


def auto_connect() -> Optional[E46Connection]:
    """Auto-detect and connect"""
    ports = find_available_ports()
    
    for port in ports:
        logger.info(f"Trying {port}...")
        try:
            conn = E46Connection(port)
            if conn.connect():
                return conn
        except:
            continue
    
    return None
