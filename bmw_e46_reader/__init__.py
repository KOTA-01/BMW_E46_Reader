"""
BMW E46 M3 Reader
~~~~~~~~~~~~~~~~~

A Python library for reading diagnostic data from a BMW E46 M3.

Uses BMW DS2 protocol (9600 baud, EVEN parity) for communication.

:copyright: (c) 2026
:license: MIT, see LICENSE for more details.
"""

__version__ = '0.1.0'
__author__ = 'BMW E46 Reader Contributors'

from .connection import E46Connection, DS2Connection
from .engine import EngineData, get_engine_data_ds2
from .dtc import FaultCode, get_fault_codes, clear_fault_codes
from .smg import SMGData, get_smg_data_ds2
from .logger import DataLogger

# Aliases for backward compatibility
get_engine_data = get_engine_data_ds2
get_smg_data = get_smg_data_ds2

__all__ = [
    'E46Connection',
    'DS2Connection',
    'EngineData',
    'get_engine_data',
    'get_engine_data_ds2',
    'FaultCode',
    'get_fault_codes',
    'clear_fault_codes',
    'SMGData',
    'get_smg_data',
    'get_smg_data_ds2',
    'DataLogger',
]
