"""
BMW E46 DS2 Protocol Module
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Implements BMW DS2 protocol for E36/E38/E39/E46/E52/E53/E83/E85/E86.

DS2 is BMW's proprietary diagnostic protocol used BEFORE the BMW-FAST protocol.
It does NOT use ISO 9141-2 5-baud initialization - messages are sent directly.

Protocol format:
    [ADDRESS] [LENGTH] [DATA...] [XOR_CHECKSUM]
    
Where:
    - ADDRESS: Target ECU address (1 byte)
    - LENGTH: Length of data including this byte (1 byte)  
    - DATA: Command/response data (variable)
    - XOR_CHECKSUM: XOR of all preceding bytes (1 byte)

Common ECU addresses:
    0x12 = DME (Engine Control Module)
    0x32 = SMG (Sequential Manual Gearbox)
    0x18 = EGS (Automatic Gearbox)
    0x00 = ZKE (Body Electronics)
    0x08 = IKE (Instrument Cluster)
    0x60 = PDC (Parking Distance Control)
    0x44 = EWS (Immobilizer)

References:
    - EdiabasLib: https://github.com/uholeschak/ediabaslib
    - Deep OBD for BMW: Android app using EdiabasLib
"""

import time
import serial
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import IntEnum
from loguru import logger


class DS2ECUAddress(IntEnum):
    """BMW DS2 ECU addresses"""
    DME = 0x12      # Engine Control (MS43/MS45/MSS54)
    SMG = 0x32      # Sequential Manual Gearbox
    EGS = 0x18      # Automatic Gearbox
    ZKE = 0x00      # Body Electronics / Central Body Electronics
    IKE = 0x08      # Instrument Cluster
    MRS = 0x50      # Airbag Module
    ABS = 0x29      # ABS/DSC Module
    PDC = 0x60      # Parking Distance Control
    EWS = 0x44      # Immobilizer
    IHKA = 0x5B     # Climate Control
    LCM = 0x00      # Light Control Module (same as ZKE)
    RAD = 0x68      # Radio
    NAV = 0x7F      # Navigation


class DS2Service(IntEnum):
    """Common DS2 service IDs (vary by ECU)"""
    IDENT = 0x00                # Get ECU identification
    READ_STATUS = 0x0B          # Read current status
    READ_FAULTS = 0x04          # Read fault codes
    CLEAR_FAULTS = 0x05         # Clear fault codes
    READ_ADAPTATION = 0x60      # Read adaptation values
    READ_MEMORY = 0x06          # Read memory
    ACTUATOR_TEST = 0x30        # Activate actuators


@dataclass
class DS2Response:
    """DS2 protocol response"""
    address: int
    length: int
    data: bytes
    checksum: int
    valid: bool
    
    @property
    def payload(self) -> bytes:
        """Data without address/length/checksum"""
        return self.data

    def __repr__(self):
        return f"DS2Response(addr=0x{self.address:02X}, len={self.length}, data={self.data.hex()}, valid={self.valid})"


class DS2Connection:
    """
    BMW DS2 Protocol connection handler.
    
    This is the correct protocol for E46 and other older BMW models.
    Does NOT use ISO 9141-2 initialization!
    
    Usage:
        conn = DS2Connection('/dev/ttyUSB0')
        conn.connect()
        
        # Read DME identification
        response = conn.send(DS2ECUAddress.DME, DS2Service.IDENT)
        if response and response.valid:
            print(f"DME data: {response.data.hex()}")
            
        conn.disconnect()
    """
    
    # Standard BMW DS2 timings
    INTER_BYTE_TIME = 0.005     # 5ms between bytes (P4 timing)
    RESPONSE_TIMEOUT = 1.0     # Timeout waiting for response
    INTER_MSG_TIME = 0.050     # 50ms minimum between messages
    
    def __init__(
        self,
        port: str,
        baud_rate: int = 9600,
        parity: str = 'E',  # Even parity is common for DS2
        timeout: float = 1.0
    ):
        self.port = port
        self.baud_rate = baud_rate
        self.parity = parity
        self.timeout = timeout
        self._serial: Optional[serial.Serial] = None
        self._last_comm_time = 0.0
        
    def connect(self) -> bool:
        """
        Establish DS2 connection.
        
        NOTE: DS2 does NOT require initialization sequence!
        Just open the port and start communicating.
        """
        logger.info(f"DS2: Connecting to {self.port} at {self.baud_rate} baud...")
        
        try:
            # Map parity string to pyserial constant
            parity_map = {
                'N': serial.PARITY_NONE,
                'E': serial.PARITY_EVEN,
                'O': serial.PARITY_ODD
            }
            
            self._serial = serial.Serial(
                port=self.port,
                baudrate=self.baud_rate,
                bytesize=serial.EIGHTBITS,
                parity=parity_map.get(self.parity, serial.PARITY_EVEN),
                stopbits=serial.STOPBITS_ONE,
                timeout=self.timeout,
                write_timeout=self.timeout,
            )
            
            time.sleep(0.1)
            self._serial.reset_input_buffer()
            self._serial.reset_output_buffer()
            
            # Most INPA-compatible cables need these settings
            # DTR low, RTS may vary
            self._serial.dtr = False
            self._serial.rts = False
            
            logger.success(f"DS2: Port opened successfully")
            
            # Test with a simple ident request
            test = self.send(DS2ECUAddress.DME, DS2Service.IDENT, timeout=0.5)
            if test and test.valid:
                logger.success(f"DS2: DME responded! Data: {test.data.hex()}")
                return True
            else:
                logger.warning("DS2: DME didn't respond - trying alternate settings")
                
                # Try with no parity
                self._serial.parity = serial.PARITY_NONE
                test = self.send(DS2ECUAddress.DME, DS2Service.IDENT, timeout=0.5)
                if test and test.valid:
                    logger.success(f"DS2: DME responded (no parity)! Data: {test.data.hex()}")
                    return True
                    
                # Try with DTR high
                self._serial.dtr = True
                test = self.send(DS2ECUAddress.DME, DS2Service.IDENT, timeout=0.5)
                if test and test.valid:
                    logger.success(f"DS2: DME responded (DTR high)! Data: {test.data.hex()}")
                    return True
                
                logger.warning("DS2: No ECU response - connection may still work")
                return True  # Port is open, ECU may respond to other commands
                
        except serial.SerialException as e:
            logger.error(f"DS2: Serial connection failed: {e}")
            return False
            
    def disconnect(self):
        """Close connection"""
        if self._serial and self._serial.is_open:
            self._serial.close()
        logger.info("DS2: Disconnected")
        
    @staticmethod
    def calc_checksum(data: bytes) -> int:
        """Calculate DS2 XOR checksum"""
        checksum = 0
        for byte in data:
            checksum ^= byte
        return checksum
        
    def send(
        self,
        address: int,
        service: int,
        data: bytes = b'',
        timeout: Optional[float] = None
    ) -> Optional[DS2Response]:
        """
        Send DS2 message and receive response.
        
        Args:
            address: Target ECU address
            service: DS2 service ID  
            data: Additional data bytes
            timeout: Response timeout (default: self.timeout)
            
        Returns:
            DS2Response object or None on failure
        """
        if not self._serial or not self._serial.is_open:
            logger.error("DS2: Not connected")
            return None
            
        timeout = timeout or self.timeout
        
        # Build message: [ADDRESS] [LENGTH] [SERVICE] [DATA...] [CHECKSUM]
        # LENGTH includes itself + service + data (NOT address, NOT checksum)
        payload = bytes([service]) + data
        length = len(payload) + 1  # +1 for length byte itself
        
        msg = bytes([address, length]) + payload
        checksum = self.calc_checksum(msg)
        msg = msg + bytes([checksum])
        
        logger.debug(f"DS2 TX -> 0x{address:02X}: {msg.hex()}")
        
        # Respect inter-message timing
        elapsed = time.time() - self._last_comm_time
        if elapsed < self.INTER_MSG_TIME:
            time.sleep(self.INTER_MSG_TIME - elapsed)
        
        try:
            self._serial.reset_input_buffer()
            
            # Send with optional inter-byte delay
            if self.INTER_BYTE_TIME > 0:
                for byte in msg:
                    self._serial.write(bytes([byte]))
                    time.sleep(self.INTER_BYTE_TIME)
            else:
                self._serial.write(msg)
                
            self._serial.flush()
            self._last_comm_time = time.time()
            
            # Wait for response
            time.sleep(0.05)  # Small initial delay
            
            return self._receive_response(timeout)
            
        except Exception as e:
            logger.error(f"DS2: Send error: {e}")
            return None
            
    def _receive_response(self, timeout: float) -> Optional[DS2Response]:
        """Receive and parse DS2 response"""
        start_time = time.time()
        
        # Wait for first byte (address)
        self._serial.timeout = timeout
        addr_byte = self._serial.read(1)
        
        if not addr_byte:
            logger.debug("DS2: No response (timeout)")
            return None
            
        address = addr_byte[0]
        
        # Read length byte
        remaining_timeout = timeout - (time.time() - start_time)
        self._serial.timeout = max(0.1, remaining_timeout)
        len_byte = self._serial.read(1)
        
        if not len_byte:
            logger.debug("DS2: Incomplete response (no length)")
            return None
            
        length = len_byte[0]
        
        if length < 1 or length > 255:
            logger.warning(f"DS2: Invalid length: {length}")
            return None
            
        # Read data + checksum
        # Length includes itself, so we need (length - 1) more bytes for data
        # Plus 1 byte for checksum
        data_len = length - 1  # Data bytes
        remaining_timeout = timeout - (time.time() - start_time)
        self._serial.timeout = max(0.1, remaining_timeout)
        
        rest = self._serial.read(data_len + 1)  # +1 for checksum
        
        if len(rest) < data_len + 1:
            logger.debug(f"DS2: Incomplete response (got {len(rest)}, expected {data_len + 1})")
            return None
            
        data = rest[:data_len]
        checksum = rest[data_len]
        
        # Verify checksum
        msg_bytes = bytes([address, length]) + data
        expected_cs = self.calc_checksum(msg_bytes)
        valid = (checksum == expected_cs)
        
        if not valid:
            logger.warning(f"DS2: Checksum mismatch: got 0x{checksum:02X}, expected 0x{expected_cs:02X}")
        
        response = DS2Response(
            address=address,
            length=length,
            data=data,
            checksum=checksum,
            valid=valid
        )
        
        logger.debug(f"DS2 RX <- 0x{address:02X}: {response}")
        
        return response
        
    def get_identification(self, ecu: int = DS2ECUAddress.DME) -> Optional[bytes]:
        """Get ECU identification string"""
        response = self.send(ecu, DS2Service.IDENT)
        return response.data if response and response.valid else None
        
    def read_status(self, ecu: int = DS2ECUAddress.DME) -> Optional[bytes]:
        """Read current ECU status"""
        response = self.send(ecu, DS2Service.READ_STATUS)
        return response.data if response and response.valid else None
        
    def read_faults(self, ecu: int = DS2ECUAddress.DME) -> Optional[bytes]:
        """Read fault codes from ECU"""
        response = self.send(ecu, DS2Service.READ_FAULTS)
        return response.data if response and response.valid else None
        
    def clear_faults(self, ecu: int = DS2ECUAddress.DME) -> bool:
        """Clear fault codes from ECU"""
        response = self.send(ecu, DS2Service.CLEAR_FAULTS)
        return response is not None and response.valid
        
    def run_diagnostics(self) -> Dict[str, Any]:
        """
        Run comprehensive DS2 protocol tests.
        
        Tests various ECU addresses and settings to determine
        what works with the connected cable/vehicle.
        """
        logger.info("DS2: Running protocol diagnostics...")
        
        results = {
            'port': self.port,
            'baud_rate': self.baud_rate,
            'parity': self.parity,
            'ecus_found': [],
            'ecus_tested': {},
            'recommended_settings': {}
        }
        
        # Test all known ECU addresses
        ecus_to_test = [
            (DS2ECUAddress.DME, "DME (Engine)"),
            (DS2ECUAddress.SMG, "SMG (Gearbox)"),
            (DS2ECUAddress.EGS, "EGS (Auto Trans)"),
            (DS2ECUAddress.IKE, "IKE (Instrument)"),
            (DS2ECUAddress.ABS, "ABS/DSC"),
            (DS2ECUAddress.ZKE, "ZKE (Body)"),
        ]
        
        for addr, name in ecus_to_test:
            logger.info(f"DS2: Testing {name} (0x{addr:02X})...")
            
            response = self.send(addr, DS2Service.IDENT, timeout=0.3)
            
            test_result = {
                'address': f"0x{addr:02X}",
                'name': name,
                'responded': response is not None,
                'valid': response.valid if response else False,
                'data': response.data.hex() if response else None
            }
            results['ecus_tested'][name] = test_result
            
            if response and response.valid:
                results['ecus_found'].append({
                    'address': addr,
                    'name': name,
                    'ident': response.data.hex()
                })
                logger.success(f"DS2: {name} responded! Data: {response.data.hex()}")
            else:
                logger.debug(f"DS2: {name} - no valid response")
                
        # Summary
        results['summary'] = {
            'ecus_responding': len(results['ecus_found']),
            'total_tested': len(ecus_to_test),
            'connection_working': len(results['ecus_found']) > 0
        }
        
        if len(results['ecus_found']) == 0:
            results['troubleshooting'] = [
                "No ECUs responded to DS2 protocol.",
                "Try these steps:",
                "1. Verify ignition is ON (position II)",
                "2. Check OBD port connection (Pins 7+8 for K-line)",
                "3. Try different baud rates: 9600, 10400",
                "4. Try with/without parity",
                "5. Verify cable is 'INPA compatible' not just ELM327",
                "6. If INPA works on Windows, capture traffic with logic analyzer"
            ]
        
        return results


def test_ds2_connection(port: str) -> Dict[str, Any]:
    """
    Test DS2 protocol on specified port.
    
    Tries multiple settings to find working configuration.
    """
    logger.info(f"Testing DS2 protocol on {port}")
    
    results = {'port': port, 'tests': []}
    
    # Settings to try
    configs = [
        {'baud': 9600, 'parity': 'E', 'desc': '9600 baud, even parity'},
        {'baud': 9600, 'parity': 'N', 'desc': '9600 baud, no parity'},
        {'baud': 10400, 'parity': 'E', 'desc': '10400 baud, even parity'},
        {'baud': 10400, 'parity': 'N', 'desc': '10400 baud, no parity'},
    ]
    
    for config in configs:
        logger.info(f"Testing: {config['desc']}")
        
        try:
            conn = DS2Connection(port, baud_rate=config['baud'], parity=config['parity'])
            conn.connect()
            
            # Quick test
            response = conn.send(DS2ECUAddress.DME, DS2Service.IDENT, timeout=0.5)
            
            test_result = {
                'config': config['desc'],
                'success': response is not None and response.valid,
                'data': response.data.hex() if response else None
            }
            results['tests'].append(test_result)
            
            conn.disconnect()
            
            if test_result['success']:
                results['working_config'] = config
                logger.success(f"WORKING: {config['desc']}")
                break
                
        except Exception as e:
            results['tests'].append({
                'config': config['desc'],
                'error': str(e)
            })
            
    return results


# Example usage / test script
if __name__ == "__main__":
    import sys
    
    # Configure logging
    logger.remove()
    logger.add(sys.stderr, level="DEBUG")
    
    port = sys.argv[1] if len(sys.argv) > 1 else '/dev/ttyUSB0'
    
    print(f"\n{'='*60}")
    print("BMW E46 DS2 Protocol Tester")
    print(f"{'='*60}\n")
    
    # Run comprehensive test
    results = test_ds2_connection(port)
    
    print(f"\nResults for {port}:")
    print("-" * 40)
    
    for test in results.get('tests', []):
        status = "✓" if test.get('success') else "✗"
        print(f"{status} {test['config']}: {test.get('data', test.get('error', 'No response'))}")
    
    if 'working_config' in results:
        print(f"\n✓ Working configuration found!")
        print(f"  Baud: {results['working_config']['baud']}")
        print(f"  Parity: {results['working_config']['parity']}")
    else:
        print("\n✗ No working configuration found")
        print("\nTroubleshooting tips:")
        print("  - Ensure ignition is ON")
        print("  - Verify K+DCAN cable supports Pins 7+8")
        print("  - Check if INPA works on Windows with same cable")
