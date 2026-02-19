"""
BMW E46 Reader CLI
~~~~~~~~~~~~~~~~~~

Command-line interface for BMW E46 M3 data reading.
"""

import sys
import click
from loguru import logger

# Configure loguru
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
    level="INFO"
)


@click.group()
@click.option('--port', '-p', default='/dev/ttyUSB0', help='Serial port for K+DCAN cable')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose output')
@click.pass_context
def cli(ctx, port, verbose):
    """BMW E46 M3 Diagnostic Reader
    
    Read engine data, fault codes, and SMG information from your E46 M3.
    Requires a K+DCAN USB cable connected to the OBD-II port.
    """
    ctx.ensure_object(dict)
    ctx.obj['PORT'] = port
    
    if verbose:
        logger.remove()
        logger.add(sys.stderr, level="DEBUG")


@cli.command()
@click.pass_context
def scan(ctx):
    """Scan for available serial ports"""
    from .connection import find_available_ports
    
    ports = find_available_ports()
    
    if ports:
        click.echo("Available serial ports:")
        for port in ports:
            click.echo(f"  {port}")
    else:
        click.echo("No serial ports found")


@cli.command()
@click.pass_context
def connect(ctx):
    """Test connection to vehicle"""
    from .connection import E46Connection
    
    port = ctx.obj['PORT']
    click.echo(f"Connecting to {port}...")
    
    try:
        with E46Connection(port) as car:
            click.echo(click.style("✓ Connected successfully", fg='green'))
            
            # Try to get VIN
            vin = car.get_vin()
            if vin:
                click.echo(f"VIN: {vin}")
    except Exception as e:
        click.echo(click.style(f"✗ Connection failed: {e}", fg='red'))
        sys.exit(1)


@cli.command()
@click.pass_context
def diagnose(ctx):
    """Run diagnostic tests to identify communication issues"""
    from .connection import E46Connection
    import json
    
    port = ctx.obj['PORT']
    click.echo(f"Running diagnostics on {port}...")
    click.echo("")
    
    try:
        conn = E46Connection(port)
        conn._serial = __import__('serial').Serial(
            port=port,
            baudrate=conn.baud_rate,
            timeout=conn.timeout
        )
        conn._serial.rts = False
        conn._serial.dtr = True
        
        results = conn.run_diagnostics()
        
        # Display results nicely
        click.echo("=" * 50)
        click.echo("DIAGNOSTIC RESULTS")
        click.echo("=" * 50)
        
        tests = results.get('tests', {})
        
        # Echo test
        echo_test = tests.get('echo', {})
        status = click.style("✓ PASS", fg='green') if echo_test.get('working') else click.style("✗ FAIL", fg='red')
        click.echo(f"\n1. K-Line Echo Test: {status}")
        click.echo(f"   Sent: {echo_test.get('sent')}, Received: {echo_test.get('received')}")
        
        # Slow init
        slow_init = tests.get('slow_init', {})
        status = click.style("✓ PASS", fg='green') if slow_init.get('success') else click.style("✗ FAIL", fg='red')
        click.echo(f"\n2. ISO 9141-2 Slow Init: {status}")
        if slow_init.get('keywords'):
            click.echo(f"   Keywords: {slow_init.get('keywords')}")
        
        # Fast init
        fast_init = tests.get('fast_init', {})
        status = click.style("✓ PASS", fg='green') if fast_init.get('success') else click.style("✗ FAIL", fg='red')
        click.echo(f"\n3. KWP2000 Fast Init: {status}")
        
        # OBD Mode 01
        obd_test = tests.get('obd_mode01', {})
        status = click.style("✓ PASS", fg='green') if obd_test.get('got_ecu_response') else click.style("✗ FAIL", fg='red')
        click.echo(f"\n4. OBD-II Mode 01 Response: {status}")
        click.echo(f"   Raw: {obd_test.get('raw_response')}")
        if obd_test.get('ecu_data'):
            click.echo(f"   ECU Data: {obd_test.get('ecu_data')}")
        
        # Summary
        click.echo("\n" + "=" * 50)
        click.echo("SUMMARY")
        click.echo("=" * 50)
        
        summary = results.get('summary', {})
        for key, value in summary.items():
            status = click.style("Yes", fg='green') if value else click.style("No", fg='yellow')
            click.echo(f"  {key}: {status}")
        
        # Notes
        notes = results.get('notes', [])
        if notes:
            click.echo("\n" + click.style("NOTES:", fg='yellow'))
            for note in notes:
                click.echo(f"  • {note}")
        
        conn._serial.close()
        
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg='red'))
        sys.exit(1)


@cli.command()
@click.option('--continuous', '-c', is_flag=True, help='Continuously read data')
@click.option('--interval', '-i', default=1.0, help='Read interval in seconds')
@click.pass_context
def engine(ctx, continuous, interval):
    """Read engine data"""
    from .connection import DS2Connection
    from .engine import get_engine_data_ds2
    
    port = ctx.obj['PORT']
    
    try:
        with DS2Connection(port) as car:
            if continuous:
                click.echo("Reading engine data (Ctrl+C to stop)...")
                try:
                    while True:
                        data = get_engine_data_ds2(car)
                        click.clear()
                        click.echo(str(data))
                        import time
                        time.sleep(interval)
                except KeyboardInterrupt:
                    click.echo("\nStopped")
            else:
                data = get_engine_data_ds2(car)
                click.echo(str(data))
                
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg='red'))
        sys.exit(1)


@cli.command()
@click.option('--clear', is_flag=True, help='Clear fault codes after reading')
@click.pass_context
def dtc(ctx, clear):
    """Read diagnostic trouble codes"""
    from .connection import E46Connection
    from .dtc import get_fault_codes, clear_fault_codes, print_fault_codes
    
    port = ctx.obj['PORT']
    
    try:
        with E46Connection(port) as car:
            codes = get_fault_codes(car)
            print_fault_codes(codes)
            
            if clear and codes:
                if click.confirm("Clear all fault codes?"):
                    if clear_fault_codes(car):
                        click.echo(click.style("✓ Fault codes cleared", fg='green'))
                    else:
                        click.echo(click.style("✗ Failed to clear codes", fg='red'))
                        
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg='red'))
        sys.exit(1)


@cli.command()
@click.option('--continuous', '-c', is_flag=True, help='Continuously read data')
@click.option('--interval', '-i', default=0.5, help='Read interval in seconds')
@click.pass_context
def smg(ctx, continuous, interval):
    """Read SMG transmission data"""
    from .connection import DS2Connection
    from .smg import get_smg_data_ds2
    
    port = ctx.obj['PORT']
    
    try:
        with DS2Connection(port) as car:
            if continuous:
                click.echo("Reading SMG data (Ctrl+C to stop)...")
                try:
                    while True:
                        data = get_smg_data_ds2(car)
                        click.clear()
                        click.echo(str(data))
                        import time
                        time.sleep(interval)
                except KeyboardInterrupt:
                    click.echo("\nStopped")
            else:
                data = get_smg_data_ds2(car)
                click.echo(str(data))
                
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg='red'))
        sys.exit(1)


@cli.command()
@click.option('--output', '-o', default='data.csv', help='Output file path')
@click.option('--interval', '-i', default=0.1, type=float, help='Log interval in seconds')
@click.option('--duration', '-d', default=0, type=int, help='Duration in seconds (0=unlimited)')
@click.option('--no-engine', is_flag=True, help='Skip engine data')
@click.option('--no-smg', is_flag=True, help='Skip SMG data')
@click.pass_context
def log(ctx, output, interval, duration, no_engine, no_smg):
    """Log data to CSV file"""
    from .connection import E46Connection
    from .logger import DataLogger
    import time
    
    port = ctx.obj['PORT']
    
    try:
        with E46Connection(port) as car:
            data_logger = DataLogger(
                car,
                output,
                log_engine=not no_engine,
                log_smg=not no_smg
            )
            
            # Add callback to show progress
            def progress_callback(data):
                rpm = data.get('rpm', 'N/A')
                gear = data.get('gear', 'N/A')
                click.echo(f"\rSamples: {data_logger.sample_count} | RPM: {rpm} | Gear: {gear}", nl=False)
            
            data_logger.add_callback(progress_callback)
            
            click.echo(f"Logging to {output} at {1/interval:.0f} Hz")
            click.echo("Press Ctrl+C to stop...")
            
            data_logger.start(interval=interval)
            
            try:
                if duration > 0:
                    time.sleep(duration)
                else:
                    while True:
                        time.sleep(1)
            except KeyboardInterrupt:
                pass
            
            stats = data_logger.stop()
            click.echo(f"\n\nLogging complete:")
            click.echo(f"  Samples: {stats.get('samples', 0)}")
            click.echo(f"  Duration: {stats.get('duration_seconds', 0):.1f}s")
            click.echo(f"  Rate: {stats.get('average_rate_hz', 0):.1f} Hz")
            click.echo(f"  Output: {stats.get('output_file', output)}")
            
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg='red'))
        sys.exit(1)


@cli.command()
@click.pass_context  
def info(ctx):
    """Show vehicle and ECU information"""
    from .connection import E46Connection, ECU_ADDRESSES
    
    port = ctx.obj['PORT']
    
    try:
        with E46Connection(port) as car:
            click.echo("Vehicle Information")
            click.echo("=" * 40)
            
            # VIN
            vin = car.get_vin()
            click.echo(f"VIN: {vin or 'Unable to read'}")
            
            # Query each ECU
            click.echo("\nECU Information:")
            for name, addr in ECU_ADDRESSES.items():
                info = car.get_ecu_info(addr)
                if info:
                    click.echo(f"  {name}: {info.part_number}")
                else:
                    click.echo(f"  {name}: Not responding")
                    
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg='red'))
        sys.exit(1)


@cli.command()
@click.pass_context
def dashboard(ctx):
    """Live dashboard display"""
    from .connection import E46Connection
    from .engine import get_engine_data
    from .smg import get_smg_data
    import time
    
    port = ctx.obj['PORT']
    
    try:
        with E46Connection(port) as car:
            click.echo("Live Dashboard (Ctrl+C to stop)")
            click.echo("Connecting...")
            
            try:
                while True:
                    engine = get_engine_data(car)
                    smg = get_smg_data(car)
                    
                    click.clear()
                    
                    # Header
                    click.echo("╔══════════════════════════════════════════════════════════╗")
                    click.echo("║            BMW E46 M3 Live Dashboard                     ║")
                    click.echo("╠══════════════════════════════════════════════════════════╣")
                    
                    # Engine section
                    rpm = engine.rpm or 0
                    rpm_bar = '█' * int(rpm / 500) + '░' * (16 - int(rpm / 500))
                    click.echo(f"║  RPM:     [{rpm_bar}] {rpm:>5.0f}              ║")
                    
                    throttle = engine.throttle_position or 0
                    thr_bar = '█' * int(throttle / 10) + '░' * (10 - int(throttle / 10))
                    click.echo(f"║  Throttle:[{thr_bar}] {throttle:>5.1f}%                  ║")
                    
                    click.echo(f"║  Coolant: {engine.coolant_temp or 0:>5.1f}°C    Oil: {engine.oil_temp or 0:>5.1f}°C          ║")
                    click.echo(f"║  Speed:   {engine.speed or 0:>5.0f} km/h   Load: {engine.engine_load or 0:>5.1f}%          ║")
                    
                    # SMG section
                    click.echo("╠══════════════════════════════════════════════════════════╣")
                    gear_str = str(smg.gear.value) if smg.gear.value >= 0 else 'N'
                    click.echo(f"║  Gear: [{gear_str}]  Mode: {smg.shift_mode.name}                               ║")
                    click.echo(f"║  Clutch: {smg.clutch_position or 0:>5.1f}%   Wear: {smg.clutch_wear or 0:>5.1f}%              ║")
                    click.echo(f"║  Hydraulic: {smg.hydraulic_pressure or 0:>5.1f} bar                          ║")
                    
                    click.echo("╚══════════════════════════════════════════════════════════╝")
                    click.echo("Press Ctrl+C to exit")
                    
                    time.sleep(0.2)
                    
            except KeyboardInterrupt:
                click.echo("\nDashboard closed")
                
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg='red'))
        sys.exit(1)


@cli.command()
@click.pass_context
def ds2test(ctx):
    """Test DS2 protocol communication (research-based)
    
    This tests the DS2 protocol with correct settings discovered from 
    community projects (pBmwScanner, EdiabasLib, Diolum's gateway analysis):
    
    - 9600 baud (not 10400)
    - EVEN parity (critical!)
    - DS2 message format with XOR checksum
    """
    from .connection import DS2Connection
    
    port = ctx.obj['PORT']
    click.echo(f"Testing DS2 protocol on {port}...")
    click.echo("")
    click.echo("Settings: 9600 baud, 8E1 (8 data bits, EVEN parity, 1 stop bit)")
    click.echo("")
    
    try:
        with DS2Connection(port) as ds2:
            click.echo("=" * 50)
            click.echo("DS2 Protocol Test")
            click.echo("=" * 50)
            
            # Test ECUs
            ecus = [
                (0x12, 'DME (Engine)'),
                (0x32, 'EGS/SMG'),
                (0x80, 'IKE (Instrument)'),
                (0x56, 'DSC (ABS)'),
                (0xD0, 'LCM (Lights)'),
                (0x5B, 'IHKA (Climate)'),
            ]
            
            responding = []
            
            for addr, name in ecus:
                click.echo(f"\n{name} (0x{addr:02X}):")
                
                # Try identity request (command 0x00)
                result = ds2.read_identity(addr)
                
                if result and result.get('status') == 0xA0:
                    click.echo(click.style(f"  ✓ Responding!", fg='green'))
                    click.echo(f"    Raw: {result['raw']}")
                    responding.append((addr, name))
                elif result:
                    click.echo(click.style(f"  ? Response: {result['raw']}", fg='yellow'))
                    if result.get('status'):
                        click.echo(f"    Status: 0x{result['status']:02X}")
                else:
                    click.echo(click.style("  ✗ No response", fg='red'))
            
            # Summary
            click.echo("\n" + "=" * 50)
            click.echo("SUMMARY")
            click.echo("=" * 50)
            
            if responding:
                click.echo(click.style(f"Responding ECUs: {len(responding)}", fg='green'))
                for addr, name in responding:
                    click.echo(f"  • {name} (0x{addr:02X})")
            else:
                click.echo(click.style("No ECUs responded", fg='yellow'))
                click.echo("\nPossible issues:")
                click.echo("  • Cable not connected to car")
                click.echo("  • Ignition not on")
                click.echo("  • Gateway blocking messages (OBD-II port)")
                click.echo("\nTry:")
                click.echo("  • Deep OBD app (Android) - handles gateway protocol")
                click.echo("  • 20-pin round connector in engine bay (direct access)")
                click.echo("  • INPA/EDIABAS on Windows")
            
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg='red'))
        import traceback
        traceback.print_exc()
        sys.exit(1)


@cli.command()
@click.option('--interval', '-i', default=1.0, help='Update interval in seconds')
@click.option('--engine-only', '-e', is_flag=True, help='Only read engine data')
@click.option('--smg-only', '-s', is_flag=True, help='Only read SMG data')
@click.pass_context
def live(ctx, interval, engine_only, smg_only):
    """Live data display using DS2 protocol
    
    Shows real-time engine and SMG data with continuous updates.
    Press Ctrl+C to stop.
    """
    from .connection import DS2Connection
    from .engine import get_engine_data_ds2, get_engine_identification
    from .smg import get_smg_data_ds2, get_smg_identification
    import time
    import os
    
    port = ctx.obj['PORT']
    click.echo(f"Connecting to {port} using DS2 protocol...")
    click.echo("Press Ctrl+C to stop")
    click.echo("")
    
    try:
        with DS2Connection(port) as ds2:
            # Initial identification
            click.echo("=" * 60)
            click.echo("ECU IDENTIFICATION")
            click.echo("=" * 60)
            
            if not smg_only:
                dme_id = get_engine_identification(ds2)
                if dme_id['raw_data']:
                    click.echo(f"DME: {dme_id.get('part_number', 'Unknown')}")
                    click.echo(f"     Raw: {dme_id['raw_data']}")
                else:
                    click.echo(click.style("DME: Not responding", fg='yellow'))
                    
            if not engine_only:
                smg_id = get_smg_identification(ds2)
                if smg_id['raw_data']:
                    click.echo(f"SMG: {smg_id.get('part_number', 'Unknown')}")
                    click.echo(f"     Raw: {smg_id['raw_data']}")
                else:
                    click.echo(click.style("SMG: Not responding", fg='yellow'))
            
            click.echo("")
            
            # Continuous data reading
            while True:
                # Clear screen (simple approach)
                click.echo("\033[H\033[J", nl=False)  # ANSI clear screen
                
                click.echo("=" * 60)
                click.echo(f"BMW E46 M3 LIVE DATA - {time.strftime('%H:%M:%S')}")
                click.echo("=" * 60)
                
                if not smg_only:
                    click.echo("")
                    click.echo("ENGINE DATA (DME)")
                    click.echo("-" * 30)
                    
                    engine_data = get_engine_data_ds2(ds2)
                    
                    if engine_data.rpm is not None:
                        click.echo(f"  RPM:              {engine_data.rpm:.0f}")
                    if engine_data.coolant_temp is not None:
                        click.echo(f"  Coolant Temp:     {engine_data.coolant_temp:.1f}°C")
                    if engine_data.oil_temp is not None:
                        click.echo(f"  Oil Temp:         {engine_data.oil_temp:.1f}°C")
                    if engine_data.intake_temp is not None:
                        click.echo(f"  Intake Temp:      {engine_data.intake_temp:.1f}°C")
                    if engine_data.engine_load is not None:
                        click.echo(f"  Engine Load:      {engine_data.engine_load:.1f}%")
                    if engine_data.throttle_position is not None:
                        click.echo(f"  Throttle:         {engine_data.throttle_position:.1f}%")
                    if engine_data.speed is not None:
                        click.echo(f"  Speed:            {engine_data.speed:.0f} km/h")
                    if engine_data.battery_voltage is not None:
                        click.echo(f"  Battery:          {engine_data.battery_voltage:.1f}V")
                    if engine_data.vanos_intake is not None:
                        click.echo(f"  VANOS Intake:     {engine_data.vanos_intake:.1f}°")
                    if engine_data.vanos_exhaust is not None:
                        click.echo(f"  VANOS Exhaust:    {engine_data.vanos_exhaust:.1f}°")
                    if engine_data.timing_advance is not None:
                        click.echo(f"  Timing Advance:   {engine_data.timing_advance:.1f}°")
                    
                    # Check if we got any data
                    if all(getattr(engine_data, attr) is None for attr in 
                           ['rpm', 'coolant_temp', 'oil_temp', 'engine_load', 'throttle_position']):
                        click.echo(click.style("  No data (engine off?)", fg='yellow'))
                
                if not engine_only:
                    click.echo("")
                    click.echo("SMG DATA")
                    click.echo("-" * 30)
                    
                    smg_data = get_smg_data_ds2(ds2)
                    
                    # Gear display
                    from .smg import GearPosition
                    gear_str = 'N' if smg_data.gear == GearPosition.NEUTRAL else \
                               'R' if smg_data.gear == GearPosition.REVERSE else \
                               str(smg_data.gear.value) if smg_data.gear != GearPosition.UNKNOWN else '?'
                    click.echo(f"  Current Gear:     {gear_str}")
                    click.echo(f"  Shift Mode:       {smg_data.shift_mode.name}")
                    
                    if smg_data.clutch_position is not None:
                        click.echo(f"  Clutch Position:  {smg_data.clutch_position:.1f}%")
                    if smg_data.hydraulic_pressure is not None:
                        click.echo(f"  Hydraulic Press:  {smg_data.hydraulic_pressure:.1f} bar")
                    click.echo(f"  Pump Running:     {'Yes' if smg_data.pump_running else 'No'}")
                    if smg_data.gearbox_temp is not None:
                        click.echo(f"  Gearbox Temp:     {smg_data.gearbox_temp:.1f}°C")
                
                click.echo("")
                click.echo("-" * 60)
                click.echo("Press Ctrl+C to stop")
                
                time.sleep(interval)
                
    except KeyboardInterrupt:
        click.echo("\n\nStopped by user")
    except Exception as e:
        click.echo(click.style(f"\nError: {e}", fg='red'))
        import traceback
        traceback.print_exc()
        sys.exit(1)


@cli.command()
@click.pass_context
def gui(ctx):
    """Launch graphical dashboard"""
    from .gui import launch_gui
    
    port = ctx.obj['PORT']
    click.echo(f"Launching GUI dashboard (port: {port})...")
    launch_gui(port)


def main():
    """Main entry point"""
    cli(obj={})


if __name__ == '__main__':
    main()
