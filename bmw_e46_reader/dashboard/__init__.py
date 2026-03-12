"""
BMW E46 Telemetry Dashboard Server
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Async web server that serves the motorsport telemetry dashboard and
streams live data to the browser via WebSocket.

Uses aiohttp for async HTTP/WS. Falls back to simple HTTP if aiohttp
is not installed.
"""

import asyncio
import json
import os
import time
import threading
from pathlib import Path
from typing import Optional, Dict, Any, Set

from loguru import logger

# Dashboard file paths
DASHBOARD_DIR = Path(__file__).parent
TEMPLATES_DIR = DASHBOARD_DIR / 'templates'
STATIC_DIR = DASHBOARD_DIR / 'static'


class TelemetryBridge:
    """
    Bridges the BMW E46 connection modules to the web dashboard.
    
    Collects data from EngineReader and SMGReader, packages it as JSON,
    and broadcasts to all connected WebSocket clients.
    """
    
    def __init__(self, port: str = '/dev/ttyUSB0'):
        self.serial_port = port
        self.connection = None
        self._running = False
        self._poll_thread: Optional[threading.Thread] = None
        
        # Latest data snapshot
        self._data: Dict[str, Any] = {}
        self._data_lock = threading.Lock()
        
        # WebSocket clients
        self._clients: Set = set()
        
        # Telemetry stats
        self._update_count = 0
        self._error_count = 0
        self._last_update = 0.0
        
        # Health tracking
        self._health = {
            'ecu': {'status': 'ok', 'text': 'OK'},
            'smg': {'status': 'ok', 'text': 'OK'},
            'kline': {'status': 'ok', 'text': 'OK'},
            'sensors': {'status': 'ok', 'text': 'OK'},
            'dtc_count': 0,
        }
    
    @property
    def latest_data(self) -> Dict[str, Any]:
        with self._data_lock:
            return dict(self._data)
    
    def start_polling(self):
        """Start background thread that reads from the car."""
        if self._running:
            return
        self._running = True
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()
        logger.info("Telemetry polling started")
    
    def stop_polling(self):
        """Stop the polling thread."""
        self._running = False
        if self._poll_thread:
            self._poll_thread.join(timeout=3.0)
        self._disconnect()
        logger.info("Telemetry polling stopped")
    
    def _connect(self) -> bool:
        """Attempt to connect to the vehicle."""
        try:
            from ..connection import E46Connection
            self.connection = E46Connection(self.serial_port)
            self.connection.connect()
            self._health['kline'] = {'status': 'ok', 'text': 'OK'}
            logger.info(f"Connected to vehicle on {self.serial_port}")
            return True
        except Exception as e:
            self._health['kline'] = {'status': 'error', 'text': str(e)[:20]}
            logger.error(f"Connection failed: {e}")
            return False
    
    def _disconnect(self):
        """Disconnect from vehicle."""
        if self.connection:
            try:
                self.connection.disconnect()
            except Exception:
                pass
            self.connection = None
    
    def _poll_loop(self):
        """Main polling loop — reads engine and SMG data continuously."""
        from ..engine import get_engine_data
        from ..smg import get_smg_data
        
        if not self._connect():
            logger.warning("Running in disconnected mode — no live data")
            self._health['kline'] = {'status': 'error', 'text': 'NO CONN'}
            return
        
        consecutive_errors = 0
        
        while self._running:
            try:
                engine_data = get_engine_data(self.connection)
                engine_dict = engine_data.to_dict()
                
                smg_dict = {}
                try:
                    smg_data = get_smg_data(self.connection)
                    smg_dict = smg_data.to_dict()
                    self._health['smg'] = {'status': 'ok', 'text': 'OK'}
                except Exception as e:
                    self._health['smg'] = {'status': 'warn', 'text': str(e)[:20]}
                
                # Package the telemetry frame
                frame = {
                    'engine': engine_dict,
                    'smg': smg_dict,
                    'health': self._health,
                    'gforce_lat': 0,    # Populated if IMU is available
                    'gforce_lon': 0,
                    'dsc_active': True,
                    'traction': {},
                    'track': {},
                }
                
                with self._data_lock:
                    self._data = frame
                
                self._update_count += 1
                self._last_update = time.time()
                consecutive_errors = 0
                self._health['ecu'] = {'status': 'ok', 'text': 'OK'}
                self._health['sensors'] = {'status': 'ok', 'text': 'OK'}
                
                time.sleep(0.1)  # ~10 Hz target
                
            except Exception as e:
                consecutive_errors += 1
                self._error_count += 1
                logger.warning(f"Poll error ({consecutive_errors}): {e}")
                
                self._health['ecu'] = {
                    'status': 'warn' if consecutive_errors < 5 else 'error',
                    'text': f'ERR x{consecutive_errors}'
                }
                
                if consecutive_errors > 10:
                    logger.error("Too many consecutive errors, attempting reconnect")
                    self._disconnect()
                    time.sleep(2.0)
                    if not self._connect():
                        time.sleep(5.0)
                    consecutive_errors = 0
                else:
                    time.sleep(0.5)


async def run_dashboard_server(
    host: str = '0.0.0.0',
    port: int = 8046,
    serial_port: str = '/dev/ttyUSB0',
    no_car: bool = False,
):
    """
    Start the telemetry dashboard web server.
    
    Args:
        host: Bind address
        port: HTTP port (default 8046 — E46!)
        serial_port: Serial port for K+DCAN cable
        no_car: If True, run without connecting to a real car (demo mode)
    """
    try:
        from aiohttp import web
    except ImportError:
        logger.error("aiohttp is required for the dashboard server. Install with: pip install aiohttp")
        return
    
    bridge = TelemetryBridge(serial_port)
    
    # ── Routes ────────────────────────────────────────────
    async def index_handler(request):
        html = (TEMPLATES_DIR / 'index.html').read_text()
        return web.Response(text=html, content_type='text/html')
    
    async def websocket_handler(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        
        bridge._clients.add(ws)
        logger.info(f"WebSocket client connected ({len(bridge._clients)} total)")
        
        try:
            async for msg in ws:
                # Handle client messages (e.g., lap trigger, config)
                if msg.type == web.WSMsgType.TEXT:
                    try:
                        cmd = json.loads(msg.data)
                        await handle_client_command(cmd, ws, bridge)
                    except json.JSONDecodeError:
                        pass
                elif msg.type == web.WSMsgType.ERROR:
                    logger.warning(f"WebSocket error: {ws.exception()}")
        finally:
            bridge._clients.discard(ws)
            logger.info(f"WebSocket client disconnected ({len(bridge._clients)} total)")
        
        return ws
    
    async def handle_client_command(cmd: dict, ws, bridge: TelemetryBridge):
        """Process commands from the dashboard client."""
        action = cmd.get('action')
        if action == 'lap_reset':
            # Could trigger lap timer reset
            pass
        elif action == 'config':
            # Could update thresholds, etc.
            pass
    
    async def broadcast_loop(app):
        """Broadcast telemetry data to all WebSocket clients at ~10 Hz."""
        while True:
            if bridge._clients:
                data = bridge.latest_data
                if data:
                    payload = json.dumps(data)
                    closed = set()
                    for ws in bridge._clients:
                        try:
                            await ws.send_str(payload)
                        except Exception:
                            closed.add(ws)
                    bridge._clients -= closed
            await asyncio.sleep(0.1)
    
    async def on_startup(app):
        if not no_car:
            bridge.start_polling()
        app['broadcast_task'] = asyncio.create_task(broadcast_loop(app))
    
    async def on_cleanup(app):
        bridge.stop_polling()
        app['broadcast_task'].cancel()
        # Close all websocket connections
        for ws in set(bridge._clients):
            await ws.close()
    
    # ── App Setup ─────────────────────────────────────────
    app = web.Application()
    app.router.add_get('/', index_handler)
    app.router.add_get('/ws', websocket_handler)
    app.router.add_static('/static', STATIC_DIR)
    
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    
    logger.info(f"Starting telemetry dashboard on http://{host}:{port}")
    logger.info(f"Serial port: {serial_port} | Car connected: {not no_car}")
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    
    # Keep running
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await runner.cleanup()


def launch_dashboard(
    host: str = '0.0.0.0',
    port: int = 8046,
    serial_port: str = '/dev/ttyUSB0',
    no_car: bool = False,
):
    """Synchronous entry point to launch the dashboard server."""
    asyncio.run(run_dashboard_server(host, port, serial_port, no_car))
