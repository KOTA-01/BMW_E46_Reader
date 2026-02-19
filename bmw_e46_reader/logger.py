"""
BMW E46 Data Logger Module
~~~~~~~~~~~~~~~~~~~~~~~~~~

Real-time data logging to CSV files.
"""

import csv
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Callable, Dict, Any, TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from .connection import E46Connection


class DataLogger:
    """
    Real-time data logger for E46 M3.
    
    Logs engine and/or SMG data to CSV files at configurable intervals.
    
    Usage:
        with E46Connection('/dev/ttyUSB0') as car:
            logger = DataLogger(car, 'output.csv')
            logger.start(interval=0.1)  # Log every 100ms
            
            time.sleep(60)  # Log for 60 seconds
            
            logger.stop()
    """
    
    def __init__(
        self,
        connection: 'E46Connection',
        output_file: str,
        log_engine: bool = True,
        log_smg: bool = True,
        custom_pids: Optional[List[str]] = None
    ):
        """
        Initialize data logger.
        
        Args:
            connection: Active E46Connection
            output_file: Path to output CSV file
            log_engine: Include engine data
            log_smg: Include SMG data
            custom_pids: List of specific PIDs to log (optional)
        """
        self.connection = connection
        self.output_path = Path(output_file)
        self.log_engine = log_engine
        self.log_smg = log_smg
        self.custom_pids = custom_pids or []
        
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._csv_file = None
        self._csv_writer = None
        self._sample_count = 0
        self._start_time: Optional[datetime] = None
        
        # Callbacks for real-time data display
        self._callbacks: List[Callable[[Dict[str, Any]], None]] = []
    
    def add_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """
        Add a callback function to receive real-time data.
        
        Args:
            callback: Function that receives a dict of current values
        """
        self._callbacks.append(callback)
    
    def remove_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """Remove a callback function"""
        if callback in self._callbacks:
            self._callbacks.remove(callback)
    
    def start(self, interval: float = 0.1):
        """
        Start logging data.
        
        Args:
            interval: Time between samples in seconds (default: 100ms)
        """
        if self._running:
            logger.warning("Logger already running")
            return
        
        self._running = True
        self._start_time = datetime.now()
        self._sample_count = 0
        
        # Create output directory if needed
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Open CSV file
        self._csv_file = open(self.output_path, 'w', newline='')
        
        # Write header
        headers = self._get_headers()
        self._csv_writer = csv.DictWriter(self._csv_file, fieldnames=headers)
        self._csv_writer.writeheader()
        
        # Start logging thread
        self._thread = threading.Thread(
            target=self._log_loop,
            args=(interval,),
            daemon=True
        )
        self._thread.start()
        
        logger.info(f"Started logging to {self.output_path} at {1/interval:.1f} Hz")
    
    def stop(self) -> Dict[str, Any]:
        """
        Stop logging and close file.
        
        Returns:
            Summary statistics
        """
        if not self._running:
            return {}
        
        self._running = False
        
        # Wait for thread to finish
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        
        # Close file
        if self._csv_file:
            self._csv_file.close()
            self._csv_file = None
        
        # Calculate statistics
        duration = (datetime.now() - self._start_time).total_seconds() if self._start_time else 0
        avg_rate = self._sample_count / duration if duration > 0 else 0
        
        stats = {
            'samples': self._sample_count,
            'duration_seconds': duration,
            'average_rate_hz': avg_rate,
            'output_file': str(self.output_path),
        }
        
        logger.info(f"Logging stopped: {self._sample_count} samples in {duration:.1f}s ({avg_rate:.1f} Hz)")
        
        return stats
    
    def _get_headers(self) -> List[str]:
        """Get CSV column headers"""
        headers = ['timestamp', 'elapsed_ms']
        
        if self.log_engine:
            headers.extend([
                'rpm', 'speed', 'engine_load', 'throttle_position',
                'coolant_temp', 'oil_temp', 'intake_temp',
                'maf', 'intake_pressure',
                'short_fuel_trim_1', 'long_fuel_trim_1',
                'short_fuel_trim_2', 'long_fuel_trim_2',
                'timing_advance', 'battery_voltage',
                'vanos_intake', 'vanos_exhaust',
                'knock_sensor_1', 'knock_sensor_2',
                'lambda_sensor_1', 'lambda_sensor_2',
                'fuel_injector_time'
            ])
        
        if self.log_smg:
            headers.extend([
                'gear', 'shift_mode',
                'clutch_position', 'clutch_wear',
                'hydraulic_pressure', 'pump_running',
                'gearbox_temp', 'last_shift_time'
            ])
        
        # Add custom PIDs
        for pid in self.custom_pids:
            if pid not in headers:
                headers.append(pid.lower())
        
        return headers
    
    def _log_loop(self, interval: float):
        """Main logging loop (runs in separate thread)"""
        next_sample_time = time.time()
        
        while self._running:
            try:
                # Collect data
                data = self._collect_data()
                
                # Write to CSV
                if self._csv_writer:
                    self._csv_writer.writerow(data)
                    self._csv_file.flush()  # Ensure data is written
                
                # Call callbacks
                for callback in self._callbacks:
                    try:
                        callback(data)
                    except Exception as e:
                        logger.warning(f"Callback error: {e}")
                
                self._sample_count += 1
                
                # Calculate next sample time
                next_sample_time += interval
                sleep_time = next_sample_time - time.time()
                
                if sleep_time > 0:
                    time.sleep(sleep_time)
                else:
                    # We're falling behind, skip to next interval
                    next_sample_time = time.time()
                    
            except Exception as e:
                logger.error(f"Logging error: {e}")
                time.sleep(interval)
    
    def _collect_data(self) -> Dict[str, Any]:
        """Collect all data for one sample"""
        now = datetime.now()
        elapsed_ms = (now - self._start_time).total_seconds() * 1000 if self._start_time else 0
        
        data = {
            'timestamp': now.isoformat(),
            'elapsed_ms': f"{elapsed_ms:.1f}",
        }
        
        # Collect engine data
        if self.log_engine:
            try:
                from .engine import get_engine_data
                engine = get_engine_data(self.connection)
                engine_dict = engine.to_dict()
                del engine_dict['timestamp']  # Already have timestamp
                data.update(engine_dict)
            except Exception as e:
                logger.debug(f"Engine data error: {e}")
        
        # Collect SMG data
        if self.log_smg:
            try:
                from .smg import get_smg_data
                smg = get_smg_data(self.connection)
                smg_dict = smg.to_dict()
                del smg_dict['timestamp']
                
                # Convert gear enum to value
                if 'gear' in smg_dict:
                    smg_dict['gear'] = smg_dict['gear'] if smg_dict['gear'] is not None else ''
                
                data.update(smg_dict)
            except Exception as e:
                logger.debug(f"SMG data error: {e}")
        
        return data
    
    @property
    def is_running(self) -> bool:
        """Check if logger is currently running"""
        return self._running
    
    @property
    def sample_count(self) -> int:
        """Get current sample count"""
        return self._sample_count


class TriggeredLogger(DataLogger):
    """
    Data logger that starts/stops based on triggers.
    
    Useful for capturing specific events like acceleration runs,
    shifts, or fault conditions.
    """
    
    def __init__(
        self,
        connection: 'E46Connection',
        output_file: str,
        trigger_start: Optional[Callable[[Dict], bool]] = None,
        trigger_stop: Optional[Callable[[Dict], bool]] = None,
        pre_trigger_samples: int = 50,
        post_trigger_samples: int = 50,
        **kwargs
    ):
        """
        Initialize triggered logger.
        
        Args:
            trigger_start: Function that returns True to start recording
            trigger_stop: Function that returns True to stop recording
            pre_trigger_samples: Number of samples to keep before trigger
            post_trigger_samples: Number of samples to record after stop trigger
        """
        super().__init__(connection, output_file, **kwargs)
        
        self.trigger_start = trigger_start
        self.trigger_stop = trigger_stop
        self.pre_trigger_samples = pre_trigger_samples
        self.post_trigger_samples = post_trigger_samples
        
        self._pre_buffer: List[Dict] = []
        self._triggered = False
        self._post_count = 0
    
    def _log_loop(self, interval: float):
        """Triggered logging loop"""
        next_sample_time = time.time()
        
        while self._running:
            try:
                data = self._collect_data()
                
                if not self._triggered:
                    # Store in pre-trigger buffer
                    self._pre_buffer.append(data)
                    if len(self._pre_buffer) > self.pre_trigger_samples:
                        self._pre_buffer.pop(0)
                    
                    # Check start trigger
                    if self.trigger_start and self.trigger_start(data):
                        self._triggered = True
                        logger.info("Trigger condition met - starting capture")
                        
                        # Write pre-trigger buffer
                        for buffered in self._pre_buffer:
                            self._csv_writer.writerow(buffered)
                        self._pre_buffer.clear()
                
                else:
                    # Recording mode
                    self._csv_writer.writerow(data)
                    self._csv_file.flush()
                    self._sample_count += 1
                    
                    # Check stop trigger
                    if self.trigger_stop and self.trigger_stop(data):
                        self._post_count += 1
                        if self._post_count >= self.post_trigger_samples:
                            logger.info("Stop trigger - ending capture")
                            self._running = False
                
                # Callbacks
                for callback in self._callbacks:
                    try:
                        callback(data)
                    except:
                        pass
                
                next_sample_time += interval
                sleep_time = next_sample_time - time.time()
                if sleep_time > 0:
                    time.sleep(sleep_time)
                else:
                    next_sample_time = time.time()
                    
            except Exception as e:
                logger.error(f"Logging error: {e}")
                time.sleep(interval)


def create_acceleration_logger(
    connection: 'E46Connection',
    output_file: str,
    rpm_threshold: int = 3000
) -> TriggeredLogger:
    """
    Create a logger that captures acceleration events.
    
    Starts recording when RPM exceeds threshold and stops
    when throttle is released.
    
    Args:
        rpm_threshold: RPM to trigger start (default: 3000)
    """
    def start_trigger(data: Dict) -> bool:
        rpm = data.get('rpm')
        throttle = data.get('throttle_position')
        return rpm is not None and rpm > rpm_threshold and throttle and throttle > 80
    
    def stop_trigger(data: Dict) -> bool:
        throttle = data.get('throttle_position')
        return throttle is not None and throttle < 20
    
    return TriggeredLogger(
        connection=connection,
        output_file=output_file,
        trigger_start=start_trigger,
        trigger_stop=stop_trigger,
        pre_trigger_samples=100,
        post_trigger_samples=50
    )


def create_shift_logger(
    connection: 'E46Connection',
    output_file: str
) -> TriggeredLogger:
    """
    Create a logger that captures gear shifts.
    
    Useful for analyzing SMG shift performance.
    """
    last_gear = [None]
    
    def start_trigger(data: Dict) -> bool:
        current_gear = data.get('gear')
        if current_gear != last_gear[0] and last_gear[0] is not None:
            return True
        last_gear[0] = current_gear
        return False
    
    def stop_trigger(data: Dict) -> bool:
        # Stop 500ms after shift detected
        return True
    
    return TriggeredLogger(
        connection=connection,
        output_file=output_file,
        trigger_start=start_trigger,
        trigger_stop=stop_trigger,
        pre_trigger_samples=50,
        post_trigger_samples=50,
        log_smg=True
    )
