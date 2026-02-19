"""
BMW E46 M3 GUI Dashboard
~~~~~~~~~~~~~~~~~~~~~~~~

Real-time graphical dashboard for E46 M3 data display.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
from typing import Optional
from datetime import datetime

from loguru import logger


class E46Dashboard:
    """
    Real-time GUI dashboard for BMW E46 M3.
    
    Shows engine and SMG data with gauges and live updates.
    """
    
    def __init__(self, port: str = '/dev/ttyUSB0'):
        self.port = port
        self.connection = None
        self._running = False
        self._update_thread: Optional[threading.Thread] = None
        
        # Data storage
        self.engine_data = {}
        self.smg_data = {}
        
        # Create main window
        self.root = tk.Tk()
        self.root.title("BMW E46 M3 Dashboard")
        self.root.geometry("900x700")
        self.root.configure(bg='#1a1a2e')
        
        # Style configuration
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self._configure_styles()
        
        # Build UI
        self._create_widgets()
        
        # Bind close event
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
    
    def _configure_styles(self):
        """Configure ttk styles for dark theme"""
        self.style.configure('Dark.TFrame', background='#1a1a2e')
        self.style.configure('Dark.TLabel', background='#1a1a2e', foreground='#eee')
        self.style.configure('Title.TLabel', background='#1a1a2e', foreground='#00d4ff', 
                           font=('Helvetica', 24, 'bold'))
        self.style.configure('Section.TLabel', background='#16213e', foreground='#00d4ff',
                           font=('Helvetica', 14, 'bold'))
        self.style.configure('Value.TLabel', background='#16213e', foreground='#00ff88',
                           font=('Consolas', 18, 'bold'))
        self.style.configure('Unit.TLabel', background='#16213e', foreground='#888',
                           font=('Helvetica', 10))
        self.style.configure('Status.TLabel', background='#1a1a2e', foreground='#888',
                           font=('Helvetica', 10))
        self.style.configure('Gear.TLabel', background='#16213e', foreground='#ff6b6b',
                           font=('Helvetica', 72, 'bold'))
        self.style.configure('Dark.TButton', font=('Helvetica', 11))
    
    def _create_widgets(self):
        """Create all UI widgets"""
        # Main container
        main_frame = ttk.Frame(self.root, style='Dark.TFrame')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Title bar
        title_frame = ttk.Frame(main_frame, style='Dark.TFrame')
        title_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(title_frame, text="BMW E46 M3", style='Title.TLabel').pack(side=tk.LEFT)
        
        # Connection status
        self.status_label = ttk.Label(title_frame, text="● Disconnected", style='Status.TLabel')
        self.status_label.pack(side=tk.RIGHT)
        
        # Connect button
        self.connect_btn = ttk.Button(title_frame, text="Connect", command=self._toggle_connection)
        self.connect_btn.pack(side=tk.RIGHT, padx=10)
        
        # Content area - two columns
        content_frame = ttk.Frame(main_frame, style='Dark.TFrame')
        content_frame.pack(fill=tk.BOTH, expand=True)
        
        # Left column - Engine data
        left_frame = ttk.Frame(content_frame, style='Dark.TFrame')
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        self._create_engine_panel(left_frame)
        
        # Right column - SMG data
        right_frame = ttk.Frame(content_frame, style='Dark.TFrame')
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        self._create_smg_panel(right_frame)
        
        # Bottom bar
        bottom_frame = ttk.Frame(main_frame, style='Dark.TFrame')
        bottom_frame.pack(fill=tk.X, pady=(10, 0))
        
        self.time_label = ttk.Label(bottom_frame, text="", style='Status.TLabel')
        self.time_label.pack(side=tk.LEFT)
        
        self.rate_label = ttk.Label(bottom_frame, text="", style='Status.TLabel')
        self.rate_label.pack(side=tk.RIGHT)
    
    def _create_engine_panel(self, parent):
        """Create engine data panel"""
        # Section header
        header = tk.Frame(parent, bg='#16213e', height=40)
        header.pack(fill=tk.X, pady=(0, 2))
        header.pack_propagate(False)
        ttk.Label(header, text="ENGINE", style='Section.TLabel').pack(pady=8)
        
        # Engine data container
        engine_frame = tk.Frame(parent, bg='#16213e')
        engine_frame.pack(fill=tk.BOTH, expand=True)
        
        # RPM gauge
        rpm_frame = tk.Frame(engine_frame, bg='#16213e')
        rpm_frame.pack(fill=tk.X, padx=15, pady=10)
        
        ttk.Label(rpm_frame, text="RPM", style='Dark.TLabel', 
                 background='#16213e').pack(anchor=tk.W)
        self.rpm_label = ttk.Label(rpm_frame, text="----", style='Value.TLabel')
        self.rpm_label.pack(anchor=tk.W)
        
        # RPM bar
        self.rpm_canvas = tk.Canvas(rpm_frame, height=20, bg='#0f0f1a', 
                                   highlightthickness=0)
        self.rpm_canvas.pack(fill=tk.X, pady=5)
        self.rpm_bar = self.rpm_canvas.create_rectangle(0, 0, 0, 20, fill='#00ff88')
        
        # Grid for other values
        grid_frame = tk.Frame(engine_frame, bg='#16213e')
        grid_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)
        
        # Create value displays
        self.engine_values = {}
        
        values = [
            ('speed', 'Speed', 'km/h'),
            ('throttle_position', 'Throttle', '%'),
            ('engine_load', 'Load', '%'),
            ('coolant_temp', 'Coolant', '°C'),
            ('oil_temp', 'Oil Temp', '°C'),
            ('intake_temp', 'Intake', '°C'),
            ('maf', 'MAF', 'g/s'),
            ('battery_voltage', 'Battery', 'V'),
            ('timing_advance', 'Timing', '°'),
            ('vanos_intake', 'VANOS In', '°'),
            ('vanos_exhaust', 'VANOS Ex', '°'),
        ]
        
        for i, (key, label, unit) in enumerate(values):
            row, col = divmod(i, 2)
            cell = tk.Frame(grid_frame, bg='#16213e')
            cell.grid(row=row, column=col, sticky='nsew', padx=5, pady=5)
            
            ttk.Label(cell, text=label, style='Dark.TLabel',
                     background='#16213e', font=('Helvetica', 9)).pack(anchor=tk.W)
            
            val_frame = tk.Frame(cell, bg='#16213e')
            val_frame.pack(anchor=tk.W)
            
            val_label = ttk.Label(val_frame, text="--", style='Value.TLabel',
                                 font=('Consolas', 14, 'bold'))
            val_label.pack(side=tk.LEFT)
            
            ttk.Label(val_frame, text=f" {unit}", style='Unit.TLabel',
                     background='#16213e').pack(side=tk.LEFT, pady=(5, 0))
            
            self.engine_values[key] = val_label
        
        grid_frame.columnconfigure(0, weight=1)
        grid_frame.columnconfigure(1, weight=1)
    
    def _create_smg_panel(self, parent):
        """Create SMG data panel"""
        # Section header
        header = tk.Frame(parent, bg='#16213e', height=40)
        header.pack(fill=tk.X, pady=(0, 2))
        header.pack_propagate(False)
        ttk.Label(header, text="SMG II", style='Section.TLabel').pack(pady=8)
        
        # SMG data container
        smg_frame = tk.Frame(parent, bg='#16213e')
        smg_frame.pack(fill=tk.BOTH, expand=True)
        
        # Large gear display
        gear_frame = tk.Frame(smg_frame, bg='#16213e')
        gear_frame.pack(fill=tk.X, pady=20)
        
        self.gear_label = ttk.Label(gear_frame, text="N", style='Gear.TLabel')
        self.gear_label.pack()
        
        self.mode_label = ttk.Label(gear_frame, text="S3", style='Section.TLabel',
                                   font=('Helvetica', 18))
        self.mode_label.pack()
        
        # Clutch info
        clutch_frame = tk.Frame(smg_frame, bg='#16213e')
        clutch_frame.pack(fill=tk.X, padx=15, pady=10)
        
        ttk.Label(clutch_frame, text="CLUTCH", style='Dark.TLabel',
                 background='#16213e').pack(anchor=tk.W)
        
        # Clutch position bar
        self.clutch_canvas = tk.Canvas(clutch_frame, height=25, bg='#0f0f1a',
                                      highlightthickness=0)
        self.clutch_canvas.pack(fill=tk.X, pady=5)
        self.clutch_bar = self.clutch_canvas.create_rectangle(0, 0, 0, 25, fill='#00d4ff')
        
        self.clutch_label = ttk.Label(clutch_frame, text="---%", style='Value.TLabel',
                                     font=('Consolas', 12))
        self.clutch_label.pack(anchor=tk.W)
        
        # SMG values grid
        grid_frame = tk.Frame(smg_frame, bg='#16213e')
        grid_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)
        
        self.smg_values = {}
        
        smg_vals = [
            ('clutch_wear', 'Clutch Wear', '%'),
            ('hydraulic_pressure', 'Hydraulic', 'bar'),
            ('gearbox_temp', 'Gearbox Temp', '°C'),
            ('last_shift_time', 'Last Shift', 'ms'),
        ]
        
        for i, (key, label, unit) in enumerate(smg_vals):
            row, col = divmod(i, 2)
            cell = tk.Frame(grid_frame, bg='#16213e')
            cell.grid(row=row, column=col, sticky='nsew', padx=5, pady=8)
            
            ttk.Label(cell, text=label, style='Dark.TLabel',
                     background='#16213e', font=('Helvetica', 9)).pack(anchor=tk.W)
            
            val_frame = tk.Frame(cell, bg='#16213e')
            val_frame.pack(anchor=tk.W)
            
            val_label = ttk.Label(val_frame, text="--", style='Value.TLabel',
                                 font=('Consolas', 14, 'bold'))
            val_label.pack(side=tk.LEFT)
            
            ttk.Label(val_frame, text=f" {unit}", style='Unit.TLabel',
                     background='#16213e').pack(side=tk.LEFT, pady=(5, 0))
            
            self.smg_values[key] = val_label
        
        grid_frame.columnconfigure(0, weight=1)
        grid_frame.columnconfigure(1, weight=1)
        
        # Pump status
        pump_frame = tk.Frame(smg_frame, bg='#16213e')
        pump_frame.pack(fill=tk.X, padx=15, pady=10)
        
        ttk.Label(pump_frame, text="Pump: ", style='Dark.TLabel',
                 background='#16213e').pack(side=tk.LEFT)
        self.pump_label = ttk.Label(pump_frame, text="--", style='Value.TLabel',
                                   font=('Consolas', 12))
        self.pump_label.pack(side=tk.LEFT)
    
    def _toggle_connection(self):
        """Toggle connection state"""
        if self._running:
            self._disconnect()
        else:
            self._connect()
    
    def _connect(self):
        """Establish connection and start updates"""
        try:
            from .connection import E46Connection
            
            self.status_label.configure(text="● Connecting...", foreground='#ffaa00')
            self.root.update()
            
            self.connection = E46Connection(self.port)
            self.connection.connect()
            
            self._running = True
            self.connect_btn.configure(text="Disconnect")
            self.status_label.configure(text="● Connected", foreground='#00ff88')
            
            # Start update thread
            self._update_thread = threading.Thread(target=self._update_loop, daemon=True)
            self._update_thread.start()
            
        except Exception as e:
            self.status_label.configure(text="● Connection Failed", foreground='#ff6b6b')
            messagebox.showerror("Connection Error", str(e))
    
    def _disconnect(self):
        """Disconnect and stop updates"""
        self._running = False
        
        if self._update_thread:
            self._update_thread.join(timeout=2.0)
        
        if self.connection:
            self.connection.disconnect()
            self.connection = None
        
        self.connect_btn.configure(text="Connect")
        self.status_label.configure(text="● Disconnected", foreground='#888')
    
    def _update_loop(self):
        """Background thread for data updates"""
        from .engine import get_engine_data
        from .smg import get_smg_data
        
        update_count = 0
        start_time = time.time()
        
        while self._running:
            try:
                # Read engine data
                engine = get_engine_data(self.connection)
                self.engine_data = engine.to_dict()
                
                # Read SMG data
                smg = get_smg_data(self.connection)
                self.smg_data = smg.to_dict()
                
                update_count += 1
                elapsed = time.time() - start_time
                rate = update_count / elapsed if elapsed > 0 else 0
                
                # Schedule UI update on main thread
                self.root.after(0, lambda: self._update_ui(rate))
                
                time.sleep(0.1)  # ~10 Hz update rate
                
            except Exception as e:
                logger.error(f"Update error: {e}")
                time.sleep(0.5)
    
    def _update_ui(self, rate: float):
        """Update UI with current data (called on main thread)"""
        if not self._running:
            return
        
        # Update time
        self.time_label.configure(text=datetime.now().strftime("%H:%M:%S"))
        self.rate_label.configure(text=f"{rate:.1f} Hz")
        
        # Update engine values
        rpm = self.engine_data.get('rpm')
        if rpm is not None:
            self.rpm_label.configure(text=f"{rpm:.0f}")
            # Update RPM bar (0-8000 RPM range)
            self.rpm_canvas.update_idletasks()
            bar_width = (rpm / 8000) * self.rpm_canvas.winfo_width()
            color = '#00ff88' if rpm < 6000 else '#ffaa00' if rpm < 7000 else '#ff6b6b'
            self.rpm_canvas.coords(self.rpm_bar, 0, 0, bar_width, 20)
            self.rpm_canvas.itemconfig(self.rpm_bar, fill=color)
        
        for key, label in self.engine_values.items():
            val = self.engine_data.get(key)
            if val is not None:
                if key in ['speed', 'timing_advance']:
                    label.configure(text=f"{val:.0f}")
                else:
                    label.configure(text=f"{val:.1f}")
            else:
                label.configure(text="--")
        
        # Update SMG values
        gear = self.smg_data.get('gear')
        if gear is not None:
            gear_display = 'N' if gear == 0 else 'R' if gear == 7 else str(gear)
            self.gear_label.configure(text=gear_display)
        
        mode = self.smg_data.get('shift_mode', 'S3')
        self.mode_label.configure(text=mode)
        
        clutch_pos = self.smg_data.get('clutch_position')
        if clutch_pos is not None:
            self.clutch_label.configure(text=f"{clutch_pos:.1f}%")
            self.clutch_canvas.update_idletasks()
            bar_width = (clutch_pos / 100) * self.clutch_canvas.winfo_width()
            self.clutch_canvas.coords(self.clutch_bar, 0, 0, bar_width, 25)
        
        for key, label in self.smg_values.items():
            val = self.smg_data.get(key)
            if val is not None:
                if key == 'last_shift_time':
                    label.configure(text=f"{val:.0f}")
                else:
                    label.configure(text=f"{val:.1f}")
            else:
                label.configure(text="--")
        
        pump = self.smg_data.get('pump_running')
        if pump is not None:
            self.pump_label.configure(text="ON" if pump else "OFF",
                                     foreground='#00ff88' if pump else '#888')
    
    def _on_close(self):
        """Handle window close"""
        self._disconnect()
        self.root.destroy()
    
    def run(self):
        """Start the GUI application"""
        self.root.mainloop()


def launch_gui(port: str = '/dev/ttyUSB0'):
    """Launch the GUI dashboard"""
    app = E46Dashboard(port)
    app.run()


if __name__ == '__main__':
    launch_gui()
