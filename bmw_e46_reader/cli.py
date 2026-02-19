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
@click.option('--continuous', '-c', is_flag=True, help='Continuously read data')
@click.option('--interval', '-i', default=1.0, help='Read interval in seconds')
@click.pass_context
def engine(ctx, continuous, interval):
    """Read engine data"""
    from .connection import E46Connection
    from .engine import get_engine_data
    
    port = ctx.obj['PORT']
    
    try:
        with E46Connection(port) as car:
            if continuous:
                click.echo("Reading engine data (Ctrl+C to stop)...")
                try:
                    while True:
                        data = get_engine_data(car)
                        click.clear()
                        click.echo(str(data))
                        import time
                        time.sleep(interval)
                except KeyboardInterrupt:
                    click.echo("\nStopped")
            else:
                data = get_engine_data(car)
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
    from .connection import E46Connection
    from .smg import get_smg_data
    
    port = ctx.obj['PORT']
    
    try:
        with E46Connection(port) as car:
            if continuous:
                click.echo("Reading SMG data (Ctrl+C to stop)...")
                try:
                    while True:
                        data = get_smg_data(car)
                        click.clear()
                        click.echo(str(data))
                        import time
                        time.sleep(interval)
                except KeyboardInterrupt:
                    click.echo("\nStopped")
            else:
                data = get_smg_data(car)
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
