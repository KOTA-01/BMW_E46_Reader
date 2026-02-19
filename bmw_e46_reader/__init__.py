"""
BMW E46 M3 Reader
~~~~~~~~~~~~~~~~~

A Python library for reading diagnostic data from a BMW E46 M3.

:copyright: (c) 2026
:license: MIT, see LICENSE for more details.
"""

__version__ = '0.1.0'
__author__ = 'BMW E46 Reader Contributors'

from .connection import E46Connection
from .engine import EngineData, get_engine_data
from .dtc import FaultCode, get_fault_codes, clear_fault_codes
from .smg import SMGData, get_smg_data
from .logger import DataLogger

__all__ = [
    'E46Connection',
    'EngineData',
    'get_engine_data',
    'FaultCode',
    'get_fault_codes',
    'clear_fault_codes',
    'SMGData',
    'get_smg_data',
    'DataLogger',
]
