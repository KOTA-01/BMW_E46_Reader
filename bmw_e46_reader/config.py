"""
BMW E46 M3 Configuration
~~~~~~~~~~~~~~~~~~~~~~~~

E46 M3 specific PIDs, addresses, and protocol settings.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional


# K-Line Protocol Settings
K_LINE_BAUD_RATE = 10400  # Standard BMW K-Line baud rate
K_LINE_INIT_BAUD = 5  # 5 baud init for ISO 9141-2

# D-CAN Protocol Settings  
DCAN_BAUD_RATE = 500000  # 500 kbps CAN

# ECU Addresses for E46 M3
ECU_ADDRESSES = {
    'DME': 0x12,      # Digital Motor Electronics (MSS54/MSS54HP)
    'EWS': 0x44,      # Electronic Immobilizer
    'EGS': 0x32,      # SMG Transmission Control
    'ABS': 0x56,      # Anti-lock Braking System (DSC)
    'IHKA': 0x5B,     # Climate Control
    'KOMBI': 0x80,    # Instrument Cluster
    'LCM': 0xD0,      # Light Control Module
    'GM': 0x00,       # General Module (body)
}

# Standard OBD-II PIDs (Mode 01)
@dataclass
class OBD_PID:
    """Standard OBD-II PID definition"""
    pid: int
    name: str
    description: str
    unit: str
    min_value: float
    max_value: float
    formula: str  # Formula to convert raw bytes to value


STANDARD_PIDS: Dict[str, OBD_PID] = {
    'ENGINE_LOAD': OBD_PID(
        pid=0x04,
        name='ENGINE_LOAD',
        description='Calculated Engine Load',
        unit='%',
        min_value=0,
        max_value=100,
        formula='A * 100 / 255'
    ),
    'COOLANT_TEMP': OBD_PID(
        pid=0x05,
        name='COOLANT_TEMP',
        description='Engine Coolant Temperature',
        unit='°C',
        min_value=-40,
        max_value=215,
        formula='A - 40'
    ),
    'SHORT_FUEL_TRIM_1': OBD_PID(
        pid=0x06,
        name='SHORT_FUEL_TRIM_1',
        description='Short Term Fuel Trim Bank 1',
        unit='%',
        min_value=-100,
        max_value=99.2,
        formula='(A - 128) * 100 / 128'
    ),
    'LONG_FUEL_TRIM_1': OBD_PID(
        pid=0x07,
        name='LONG_FUEL_TRIM_1',
        description='Long Term Fuel Trim Bank 1',
        unit='%',
        min_value=-100,
        max_value=99.2,
        formula='(A - 128) * 100 / 128'
    ),
    'SHORT_FUEL_TRIM_2': OBD_PID(
        pid=0x08,
        name='SHORT_FUEL_TRIM_2',
        description='Short Term Fuel Trim Bank 2',
        unit='%',
        min_value=-100,
        max_value=99.2,
        formula='(A - 128) * 100 / 128'
    ),
    'LONG_FUEL_TRIM_2': OBD_PID(
        pid=0x09,
        name='LONG_FUEL_TRIM_2',
        description='Long Term Fuel Trim Bank 2',
        unit='%',
        min_value=-100,
        max_value=99.2,
        formula='(A - 128) * 100 / 128'
    ),
    'INTAKE_PRESSURE': OBD_PID(
        pid=0x0B,
        name='INTAKE_PRESSURE',
        description='Intake Manifold Pressure',
        unit='kPa',
        min_value=0,
        max_value=255,
        formula='A'
    ),
    'RPM': OBD_PID(
        pid=0x0C,
        name='RPM',
        description='Engine RPM',
        unit='rpm',
        min_value=0,
        max_value=16383.75,
        formula='(A * 256 + B) / 4'
    ),
    'SPEED': OBD_PID(
        pid=0x0D,
        name='SPEED',
        description='Vehicle Speed',
        unit='km/h',
        min_value=0,
        max_value=255,
        formula='A'
    ),
    'TIMING_ADVANCE': OBD_PID(
        pid=0x0E,
        name='TIMING_ADVANCE',
        description='Timing Advance',
        unit='°',
        min_value=-64,
        max_value=63.5,
        formula='A / 2 - 64'
    ),
    'INTAKE_TEMP': OBD_PID(
        pid=0x0F,
        name='INTAKE_TEMP',
        description='Intake Air Temperature',
        unit='°C',
        min_value=-40,
        max_value=215,
        formula='A - 40'
    ),
    'MAF': OBD_PID(
        pid=0x10,
        name='MAF',
        description='Mass Air Flow Rate',
        unit='g/s',
        min_value=0,
        max_value=655.35,
        formula='(A * 256 + B) / 100'
    ),
    'THROTTLE_POS': OBD_PID(
        pid=0x11,
        name='THROTTLE_POS',
        description='Throttle Position',
        unit='%',
        min_value=0,
        max_value=100,
        formula='A * 100 / 255'
    ),
    'OIL_TEMP': OBD_PID(
        pid=0x5C,
        name='OIL_TEMP',
        description='Engine Oil Temperature',
        unit='°C',
        min_value=-40,
        max_value=210,
        formula='A - 40'
    ),
    'BATTERY_VOLTAGE': OBD_PID(
        pid=0x42,
        name='BATTERY_VOLTAGE',
        description='Control Module Voltage',
        unit='V',
        min_value=0,
        max_value=65.535,
        formula='(A * 256 + B) / 1000'
    ),
}


# BMW-Specific PIDs for MSS54 ECU (E46 M3 S54 Engine)
@dataclass
class BMW_PID:
    """BMW-specific PID definition"""
    address: int
    name: str
    description: str
    unit: str
    byte_count: int
    formula: str


MSS54_PIDS: Dict[str, BMW_PID] = {
    'ENGINE_RPM_BMW': BMW_PID(
        address=0x00,
        name='ENGINE_RPM_BMW',
        description='Engine RPM (BMW specific)',
        unit='rpm',
        byte_count=2,
        formula='(A * 256 + B) / 4'
    ),
    'VANOS_INTAKE': BMW_PID(
        address=0x10,
        name='VANOS_INTAKE',
        description='VANOS Intake Position',
        unit='°',
        byte_count=2,
        formula='(A * 256 + B) / 100'
    ),
    'VANOS_EXHAUST': BMW_PID(
        address=0x12,
        name='VANOS_EXHAUST',
        description='VANOS Exhaust Position',
        unit='°',
        byte_count=2,
        formula='(A * 256 + B) / 100'
    ),
    'KNOCK_SENSOR_1': BMW_PID(
        address=0x20,
        name='KNOCK_SENSOR_1',
        description='Knock Sensor 1 Retard',
        unit='°',
        byte_count=1,
        formula='A * 0.5'
    ),
    'KNOCK_SENSOR_2': BMW_PID(
        address=0x21,
        name='KNOCK_SENSOR_2',
        description='Knock Sensor 2 Retard',
        unit='°',
        byte_count=1,
        formula='A * 0.5'
    ),
    'FUEL_INJECTOR_TIME': BMW_PID(
        address=0x30,
        name='FUEL_INJECTOR_TIME',
        description='Fuel Injection Time',
        unit='ms',
        byte_count=2,
        formula='(A * 256 + B) / 1000'
    ),
    'LAMBDA_SENSOR_1': BMW_PID(
        address=0x40,
        name='LAMBDA_SENSOR_1',
        description='Lambda Sensor 1 (Pre-cat)',
        unit='λ',
        byte_count=2,
        formula='(A * 256 + B) / 32768'
    ),
    'LAMBDA_SENSOR_2': BMW_PID(
        address=0x42,
        name='LAMBDA_SENSOR_2',
        description='Lambda Sensor 2 (Post-cat)',
        unit='λ',
        byte_count=2,
        formula='(A * 256 + B) / 32768'
    ),
}


# SMG II Specific Parameters
@dataclass
class SMG_Parameter:
    """SMG II gearbox parameter definition"""
    address: int
    name: str
    description: str
    unit: str
    byte_count: int


SMG_PARAMETERS: Dict[str, SMG_Parameter] = {
    'GEAR_POSITION': SMG_Parameter(
        address=0x01,
        name='GEAR_POSITION',
        description='Current Gear Position',
        unit='',
        byte_count=1
    ),
    'GEAR_REQUESTED': SMG_Parameter(
        address=0x02,
        name='GEAR_REQUESTED',
        description='Requested Gear',
        unit='',
        byte_count=1
    ),
    'SHIFT_MODE': SMG_Parameter(
        address=0x03,
        name='SHIFT_MODE',
        description='Current Shift Program (S1-S6)',
        unit='',
        byte_count=1
    ),
    'CLUTCH_POSITION': SMG_Parameter(
        address=0x10,
        name='CLUTCH_POSITION',
        description='Clutch Actuator Position',
        unit='%',
        byte_count=1
    ),
    'CLUTCH_WEAR': SMG_Parameter(
        address=0x11,
        name='CLUTCH_WEAR',
        description='Estimated Clutch Wear',
        unit='%',
        byte_count=1
    ),
    'HYDRAULIC_PRESSURE': SMG_Parameter(
        address=0x20,
        name='HYDRAULIC_PRESSURE',
        description='SMG Hydraulic System Pressure',
        unit='bar',
        byte_count=2
    ),
    'PUMP_STATUS': SMG_Parameter(
        address=0x21,
        name='PUMP_STATUS',
        description='Hydraulic Pump Status',
        unit='',
        byte_count=1
    ),
    'GEARBOX_TEMP': SMG_Parameter(
        address=0x30,
        name='GEARBOX_TEMP',
        description='Gearbox Oil Temperature',
        unit='°C',
        byte_count=1
    ),
    'SHIFT_TIME': SMG_Parameter(
        address=0x40,
        name='SHIFT_TIME',
        description='Last Shift Duration',
        unit='ms',
        byte_count=2
    ),
}


# DTC (Diagnostic Trouble Code) Categories
DTC_CATEGORIES = {
    'P': 'Powertrain',
    'C': 'Chassis',
    'B': 'Body',
    'U': 'Network',
}


# Common E46 M3 Fault Codes
E46_M3_FAULT_CODES: Dict[str, str] = {
    # Engine/DME codes
    'P0300': 'Random/Multiple Cylinder Misfire Detected',
    'P0301': 'Cylinder 1 Misfire Detected',
    'P0302': 'Cylinder 2 Misfire Detected',
    'P0303': 'Cylinder 3 Misfire Detected',
    'P0304': 'Cylinder 4 Misfire Detected',
    'P0305': 'Cylinder 5 Misfire Detected',
    'P0306': 'Cylinder 6 Misfire Detected',
    'P0171': 'System Too Lean (Bank 1)',
    'P0174': 'System Too Lean (Bank 2)',
    'P0172': 'System Too Rich (Bank 1)',
    'P0175': 'System Too Rich (Bank 2)',
    'P0128': 'Coolant Thermostat (Coolant Temp Below Regulating Temp)',
    'P0340': 'Camshaft Position Sensor A Circuit',
    'P0341': 'Camshaft Position Sensor Range/Performance',
    'P0365': 'Camshaft Position Sensor B Circuit',
    'P0366': 'Camshaft Position Sensor B Range/Performance',
    'P1083': 'VANOS Intake - Max Limit Exceeded',
    'P1093': 'VANOS Exhaust - Max Limit Exceeded',
    'P1519': 'VANOS Intake Control - Signal Outside Limit',
    'P1520': 'VANOS Exhaust Control - Signal Outside Limit',
    'P0420': 'Catalyst System Efficiency Below Threshold (Bank 1)',
    'P0430': 'Catalyst System Efficiency Below Threshold (Bank 2)',
    'P0442': 'Evaporative Emission System Leak Detected (Small)',
    'P0455': 'Evaporative Emission System Leak Detected (Large)',
    'P0500': 'Vehicle Speed Sensor A',
    'P0113': 'Intake Air Temperature Sensor 1 Circuit High',
    'P0112': 'Intake Air Temperature Sensor 1 Circuit Low',
    
    # SMG codes
    'P1700': 'SMG - General Fault',
    'P1701': 'SMG - Hydraulic Pressure Too Low',
    'P1702': 'SMG - Hydraulic Pump Fault',
    'P1703': 'SMG - Clutch Actuator Fault',
    'P1704': 'SMG - Gear Selection Sensor Fault',
    'P1705': 'SMG - Shift Position Sensor Fault',
    'P1706': 'SMG - Clutch Temperature Too High',
    'P1707': 'SMG - Shift Quality Degraded',
    
    # DSC/ABS codes
    'P0562': 'System Voltage Low (DSC)',
    'P0563': 'System Voltage High (DSC)',
    'C1000': 'ABS Wheel Speed Sensor Front Left',
    'C1001': 'ABS Wheel Speed Sensor Front Right',
    'C1002': 'ABS Wheel Speed Sensor Rear Left',
    'C1003': 'ABS Wheel Speed Sensor Rear Right',
}


# Serial port patterns by OS
SERIAL_PORT_PATTERNS = {
    'linux': ['/dev/ttyUSB0', '/dev/ttyUSB1', '/dev/ttyACM0'],
    'darwin': ['/dev/tty.usbserial-*', '/dev/tty.wchusbserial*'],
    'win32': ['COM3', 'COM4', 'COM5', 'COM6'],
}
