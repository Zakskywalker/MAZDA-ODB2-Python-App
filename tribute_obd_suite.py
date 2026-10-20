import csv
import datetime
import json
import queue
import random
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# Gracefully handle missing dependencies with clear diagnostic guidance
try:
    import obd
    from obd import OBDStatus
    import serial
    import serial.tools.list_ports
    OBD_AVAILABLE = True
except ImportError:
    OBD_AVAILABLE = False


class MazdaTributeOBDSuite:
    """
    Comprehensive OBD-II Diagnostic, Verification & Timeline Suite
    Optimized for Veepeak VP11 (ELM327) and 2002 Mazda Tribute (SAE J1850 PWM).
    """

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("2002 Mazda Tribute // Veepeak VP11 Diagnostic & Timeline Suite")
        self.root.geometry("1360x860")
        self.root.configure(bg="#121212")

        # Connection & Threading State
        self.connection = None
        self.raw_serial = None
        self.is_connected = False
        self.is_polling = False
        self.serial_lock = threading.Lock()
        self.sim_mode = tk.BooleanVar(value=False)
        self.poll_interval = tk.DoubleVar(value=1.0)
        self.selected_port = tk.StringVar(value="Auto-Detect")
        self.selected_proto = tk.StringVar(value="1 - SAE J1850 PWM (Mazda/Ford)")

        # Data Stores
        self.ui_queue = queue.Queue()
        self.sensor_latest = {}        # name -> dict of current/min/max/unit/status
        self.timeline_history = []     # list of dicts: timestamp, category, item, value, unit, notes
        self.supported_commands = []
        self.health_results = []
        self.last_health_eval = 0
        self.health_test_details = {
            "Battery Resting / State of Charge": {
                "background": "The battery provides cranking energy and voltage stabilization for the Ford EEC-V PCM and sensor reference circuits. In KOEO (Key On Engine Off), a healthy lead-acid battery sits at 12.4V to 12.8V.",
                "action": "If < 12.0V, charge battery and test with a carbon-pile or digital conductance tester. Inspect terminals for blue/white copper-sulfate corrosion."
            },
            "Alternator Output & Regulator Test": {
                "background": "With the 3.0L V6 / 2.0L running, the alternator should supply between 13.5V and 14.7V to recharge the battery and run accessories.",
                "action": "If < 13.2V, check serpentine belt tensioner and alternator diodes/brushes. If > 15.0V, the internal voltage regulator has shorted—shut off immediately to prevent frying the PCM and instrument cluster."
            },
            "Alternator AC Ripple & Diode Health": {
                "background": "The alternator produces 3-phase AC voltage converted to DC via internal rectifier diodes. If a diode shorts or opens, AC voltage leaks into the vehicle electrical bus, causing battery boiling and phantom sensor codes.",
                "action": "If voltage ripple exceeds 0.45V peak-to-peak, bench test the alternator or replace the alternator assembly."
            },
            "Starter & Cranking Voltage Drop": {
                "background": "During engine cranking, heavy current draw (120-180A) pulls battery voltage down. A healthy starter and battery will maintain at least 9.6V to 10.2V during crank.",
                "action": "If cranking voltage drops below 9.5V, test battery CCA capacity and inspect positive starter cable and engine ground block for corrosion."
            },
            "Vacuum Leak Test (Bank 1 Total Trim)": {
                "background": "Total Trim = Short Term + Long Term. On the 2002 Mazda Tribute 3.0L Duratec, dried upper and lower intake manifold plenum o-rings and cracked PCV rubber elbows under the throttle body are the #1 cause of unmetered air and P0171 codes.",
                "action": "If total trim > +12% at idle, spray brake cleaner or water mist around the upper intake plenum joints while monitoring live RPM. If trims improve at 2500 RPM, it confirms a vacuum leak rather than a fuel delivery fault."
            },
            "Vacuum Leak Test (Bank 2 Total Trim)": {
                "background": "Monitors the front cylinder bank (Cylinders 4, 5, 6). Evaluates unmetered air entering the front bank intake runners.",
                "action": "If Bank 2 is high along with Bank 1, the leak is common (PCV elbow, throttle body gasket, or brake booster hose). If only Bank 2 is high, inspect Bank 2 lower intake gasket or injector seals."
            },
            "Bank-to-Bank Fuel Trim Balance": {
                "background": "Compares Bank 1 (firewall side) vs Bank 2 (radiator side). The two banks should track within 8-10% of each other on a healthy engine.",
                "action": "If split exceeds 10%, suspect a clogged fuel injector, exhaust manifold crack before the upstream O2 sensor, or a lazy oxygen sensor."
            },
            "Intake Manifold Pressure & Engine Vacuum (MAP)": {
                "background": "Measures absolute air pressure in the intake manifold. At warm curb idle, a healthy engine generates 18 to 21 inHg of vacuum (approx 28 to 36 kPa absolute).",
                "action": "If MAP > 44 kPa at warm idle, check for large intake vacuum leaks, a sticking EGR valve allowing exhaust backflow, or valve timing issues."
            },
            "Coolant Temperature & Thermostat Integrity": {
                "background": "The Ford/Mazda EEC-V PCM requires the engine to reach at least 82C (180F) to enter Closed-Loop Fuel Control and run emissions monitors. Operating range is 88C-98C (190F-208F).",
                "action": "If < 80C after 10 min driving, the thermostat is stuck open (replace with 192F OEM thermostat). If > 105C, check dual electric cooling fan relays and water pump impeller."
            },
            "Cold Soak Sensor Rationality (ECT vs IAT)": {
                "background": "Before a cold engine is started, Engine Coolant Temp (ECT) and Intake Air Temp (IAT) should read within 6C of each other, matching ambient temperature.",
                "action": "If split > 10C on a cold morning, one thermistor has drifted. Test sensor resistance with a multimeter against factory temperature-resistance curves."
            },
            "Mass Air Flow (MAF) Sensor Flow Check": {
                "background": "Measures grams of air per second entering the engine. At warm curb idle (~700 RPM), the 3.0L V6 typically draws 3.0 - 5.0 g/s.",
                "action": "If < 2.2 g/s at idle, the heated wire element is fouled with dust/oil. Remove the sensor and clean delicately with CRC Mass Air Flow Sensor Cleaner."
            },
            "Throttle Position Sensor (TPS) Resting Angle": {
                "background": "Reports throttle plate position to the PCM. Closed throttle resting voltage should report around 15% to 20% on OBD-II Mode 01.",
                "action": "If > 24%, the throttle return spring or cruise control cable may be binding, or carbon sludge is wedging the throttle plate open. Clean the throttle body bore."
            },
            "Engine Load vs RPM Plausibility": {
                "background": "Calculated engine load measures percentage of peak airflow capacity. Normal curb idle load without AC is 18% to 28%.",
                "action": "If load > 38% at idle, engine is fighting excessive mechanical drag (AC compressor seizing, power steering pump, or transmission torque converter drag)."
            },
            "Ignition Spark Advance & Timing": {
                "background": "The PCM controls ignition timing base advance via Crankshaft Position Sensor (CKP). Nominal idle timing is 8 to 16 deg BTDC.",
                "action": "If timing is negative or heavily retarded at idle, the PCM has detected knock or the harmonic balancer outer ring has slipped."
            },
            "Upstream O2 Sensor Switching (Bank 1 & 2)": {
                "background": "Upstream sensors (B1S1, B2S1) must cycle between 0.1V (lean) and 0.9V (rich) multiple times per second as the PCM modulates the fuel pulse.",
                "action": "If voltage flatlines around 0.45V or stays static, replace the upstream oxygen sensor (common failure point beyond 100k miles on Tribute/Escape)."
            },
            "Catalytic Converter Downstream O2 Activity": {
                "background": "Downstream sensors (B1S2, B2S2) monitor catalytic converter efficiency. When the cat is healthy, downstream O2 voltage remains steady (~0.6V-0.75V) with minimal switching.",
                "action": "If downstream O2 sensor mirrors upstream switching with wide voltage swings, the catalytic converter catalyst washcoat has degraded (precursor to P0420/P0430 codes)."
            },
            "Instant Fuel Consumption Rate (Calculated GPH)": {
                "background": "Computes real-time gasoline burn rate from MAF airflow and stoichiometric 14.7:1 combustion ratio.",
                "action": "Normal warm curb idle consumption is 0.35 to 0.65 GPH. If > 0.85 GPH, inspect for dragging brakes, high idle RPM, or leaking fuel injectors."
            },
            "Idle RPM Stability & Misfire Pre-Screen": {
                "background": "Monitors RPM variance at idle. Smooth 6-cylinder idle has less than 80-120 RPM variation.",
                "action": "If RPM fluctuates > 160 RPM at curb idle, an intermittent cylinder misfire, vacuum leak, or sticky Idle Air Control (IAC) valve is present."
            },
            "Check Engine Light (MIL) & Stored DTCs": {
                "background": "Direct check of the onboard diagnostic malfunction indicator status.",
                "action": "If MIL is ON, switch to the 'Fault Codes & Freeze Frame' tab to read stored codes and freeze frame operating snapshots."
            }
        }
        self.sort_Directions = {}      # treeview column sort state

        self._apply_dark_theme()
        self._build_layout()
        self._refresh_ports()
        self._process_ui_queue()
        self._check_terms_on_startup()

        if not OBD_AVAILABLE:
            self.log_event(
                "System",
                "Dependency Warning",
                "python-obd or pyserial not found. Run: pip install obd pyserial. Simulation Mode remains functional.",
                level="WARN"
            )

    def _apply_dark_theme(self):
        style = ttk.Style()
        style.theme_use("clam")

        bg_dark = "#121212"
        bg_panel = "#1E1E1E"
        bg_input = "#2A2A2A"
        fg_main = "#E0E0E0"
        accent = "#00ACC1"

        style.configure(".", background=bg_dark, foreground=fg_main, font=("Segoe UI", 10))
        style.configure("TFrame", background=bg_dark)
        style.configure("Panel.TFrame", background=bg_panel)
        style.configure("TLabel", background=bg_dark, foreground=fg_main)
        style.configure("Panel.TLabel", background=bg_panel, foreground=fg_main)
        style.configure("Header.TLabel", background=bg_panel, foreground="#00E5FF", font=("Segoe UI", 11, "bold"))

        style.configure("TButton", background="#2D2D30", foreground=fg_main, borderwidth=1, focusthickness=0, padding=6)
        style.map("TButton", background=[("active", "#3E3E42"), ("disabled", "#1B1B1B")])

        style.configure("Accent.TButton", background="#006978", foreground="#FFFFFF", font=("Segoe UI", 10, "bold"))
        style.map("Accent.TButton", background=[("active", "#00838F")])

        style.configure("Danger.TButton", background="#8E0000", foreground="#FFFFFF", font=("Segoe UI", 10, "bold"))
        style.map("Danger.TButton", background=[("active", "#B71C1C")])

        style.configure("TNotebook", background=bg_dark, borderwidth=0)
        style.configure("TNotebook.Tab", background=bg_panel, foreground="#9E9E9E", padding=[14, 8], font=("Segoe UI", 10, "bold"))
        style.map("TNotebook.Tab", background=[("selected", "#263238")], foreground=[("selected", "#00E5FF")])

        style.configure(
            "Treeview",
            background=bg_panel,
            foreground=fg_main,
            fieldbackground=bg_panel,
            rowheight=26,
            borderwidth=0,
            font=("Consolas", 10)
        )
        style.configure("Treeview.Heading", background="#263238", foreground="#00E5FF", font=("Segoe UI", 10, "bold"), relief="flat")
        style.map("Treeview", background=[("selected", "#004D40")], foreground=[("selected", "#FFFFFF")])

        style.configure("TCombobox", fieldbackground=bg_input, background=bg_input, foreground=fg_main)
        style.configure("TCheckbutton", background=bg_panel, foreground=fg_main)

    def _build_layout(self):
        # 1. Top Control Bar
        top_bar = ttk.Frame(self.root, style="Panel.TFrame", padding=10)
        top_bar.pack(fill=tk.X, padx=8, pady=(8, 4))

        ttk.Label(top_bar, text="COM Port:", style="Panel.TLabel").pack(side=tk.LEFT, padx=(4, 4))
        self.port_combo = ttk.Combobox(top_bar, textvariable=self.selected_port, width=15)
        self.port_combo.pack(side=tk.LEFT, padx=4)

        ttk.Button(top_bar, text="Refresh", command=self._refresh_ports).pack(side=tk.LEFT, padx=4)

        ttk.Label(top_bar, text="Protocol:", style="Panel.TLabel").pack(side=tk.LEFT, padx=(12, 4))
        proto_options = [
            "Auto-Detect",
            "1 - SAE J1850 PWM (Mazda/Ford)",
            "2 - SAE J1850 VPW (GM)",
            "3 - ISO 9141-2 (Chrysler/Asian)",
            "6 - ISO 15765-4 CAN (11b/500k)"
        ]
        self.proto_combo = ttk.Combobox(top_bar, textvariable=self.selected_proto, values=proto_options, width=32, state="readonly")
        self.proto_combo.pack(side=tk.LEFT, padx=4)

        ttk.Checkbutton(top_bar, text="Simulation Mode (Offline Test)", variable=self.sim_mode).pack(side=tk.LEFT, padx=14)

        self.btn_connect = ttk.Button(top_bar, text="Connect Adapter", style="Accent.TButton", command=self.toggle_connection)
        self.btn_connect.pack(side=tk.LEFT, padx=6)

        self.btn_poll = ttk.Button(top_bar, text="Start Live Polling", command=self.toggle_polling, state=tk.DISABLED)
        self.btn_poll.pack(side=tk.LEFT, padx=6)

        ttk.Button(top_bar, text="Terms & Legal Disclaimer", command=self.show_terms_and_conditions).pack(side=tk.RIGHT, padx=4)
        ttk.Button(top_bar, text="Export Full Snapshot", command=self.export_all_data).pack(side=tk.RIGHT, padx=4)

        # Status Bar Banner
        status_bar = ttk.Frame(self.root, style="Panel.TFrame", padding=(10, 6))
        status_bar.pack(fill=tk.X, padx=8, pady=(0, 6))

        self.lbl_status = ttk.Label(status_bar, text="STATUS: DISCONNECTED", style="Header.TLabel")
        self.lbl_status.pack(side=tk.LEFT, padx=4)

        self.lbl_elm_info = ttk.Label(status_bar, text="Adapter: -- | Protocol: -- | Voltage: --", style="Panel.TLabel")
        self.lbl_elm_info.pack(side=tk.RIGHT, padx=8)

        # 2. Main Tabbed Notebook
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        self._build_tab_health_tests()
        self._build_tab_sensors()
        self._build_tab_dtcs()
        self._build_tab_readiness()
        self._build_tab_timeline()
        self._build_tab_raw_console()
        self._build_tab_troubleshooting_wizard()

    def _build_tab_health_tests(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Automated Health & Issue Tests")

        # Top control & summary bar
        top_frame = ttk.Frame(tab, style="Panel.TFrame", padding=10)
        top_frame.pack(fill=tk.X, pady=(0, 6))

        ttk.Button(
            top_frame,
            text="⚡ Run Full Diagnostic Health Scan",
            style="Accent.TButton",
            command=self.run_full_health_scan
        ).pack(side=tk.LEFT, padx=6)

        self.auto_eval_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            top_frame,
            text="Auto-Evaluate During Live Polling",
            variable=self.auto_eval_var
        ).pack(side=tk.LEFT, padx=12)

        self.lbl_overall_health = ttk.Label(
            top_frame,
            text="OVERALL STATUS: AWAITING SCAN",
            font=("Segoe UI", 11, "bold"),
            foreground="#00E5FF"
        )
        self.lbl_overall_health.pack(side=tk.RIGHT, padx=12)

        # Split into upper Treeview of tests and lower Diagnostic Advice & Mechanics Insight
        paned = ttk.PanedWindow(tab, orient=tk.VERTICAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # Upper frame: Tests Table
        upper_frame = ttk.Frame(paned)
        paned.add(upper_frame, weight=3)

        cols = ("category", "test_name", "measured", "reference", "status", "finding")
        self.tree_health = ttk.Treeview(upper_frame, columns=cols, show="headings")
        headers = {
            "category": ("Subsystem", 160),
            "test_name": ("Diagnostic Test", 230),
            "measured": ("Live Reading", 130),
            "reference": ("Nominal Spec", 160),
            "status": ("Health Status", 130),
            "finding": ("Diagnostic Assessment & Mazda Tribute Insights", 460)
        }
        for c, (txt, w) in headers.items():
            self.tree_health.heading(c, text=txt, command=lambda _c=c: self.sort_treeview(self.tree_health, _c))
            self.tree_health.column(c, width=w, anchor=tk.W if c in ("category", "test_name", "finding") else tk.CENTER)

        self.tree_health.tag_configure("PASS", foreground="#00E676")
        self.tree_health.tag_configure("WARN", foreground="#FFD600")
        self.tree_health.tag_configure("FAIL", foreground="#FF5252")
        self.tree_health.tag_configure("INFO", foreground="#00E5FF")

        scroll_h = ttk.Scrollbar(upper_frame, orient=tk.VERTICAL, command=self.tree_health.yview)
        self.tree_health.configure(yscrollcommand=scroll_h.set)
        self.tree_health.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_h.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree_health.bind("<<TreeviewSelect>>", self._on_health_test_select)

        # Lower frame: Detailed Diagnostic Breakdown & Repair Advice
        lower_frame = ttk.Frame(paned, style="Panel.TFrame", padding=10)
        paned.add(lower_frame, weight=2)

        ttk.Label(lower_frame, text="Repair & Inspection Guidance (Click any test above for detailed mechanical walkthrough):", style="Header.TLabel").pack(anchor=tk.W, pady=(0, 4))
        self.txt_health_advice = tk.Text(
            lower_frame,
            bg="#161616",
            fg="#E0E0E0",
            font=("Segoe UI", 10),
            height=7,
            wrap=tk.WORD,
            borderwidth=1,
            relief="solid"
        )
        self.txt_health_advice.pack(fill=tk.BOTH, expand=True)
        self.txt_health_advice.insert(tk.END, "Click 'Run Full Diagnostic Health Scan' or connect adapter to evaluate battery, charging system, vacuum leaks, and engine sensors.")

    def _on_health_test_select(self, event):
        selected = self.tree_health.selection()
        if not selected:
            return
        item = self.tree_health.item(selected[0])
        values = item.get("values", [])
        if not values or len(values) < 6:
            return
        cat, name, measured, spec, status, finding = values[:6]
        details = self.health_test_details.get(name, {})

        advice_text = f"=== {cat.upper()} :: {name} [{status}] ===\n\n"
        advice_text += f"• Measured Live Value: {measured}\n"
        advice_text += f"• Factory Nominal Spec: {spec}\n\n"
        advice_text += f"DIAGNOSTIC FINDING:\n{finding}\n\n"
        if details:
            advice_text += f"MECHANICAL BACKGROUND:\n{details.get('background', '')}\n\n"
            advice_text += f"RECOMMENDED ACTION FOR 2002 MAZDA TRIBUTE / ESCAPE:\n{details.get('action', '')}\n"
        self.txt_health_advice.delete("1.0", tk.END)
        self.txt_health_advice.insert(tk.END, advice_text)

    def run_full_health_scan(self):
        """Runs an immediate dedicated scan of all critical health parameters and evaluates rules."""
        if not self.is_connected:
            messagebox.showwarning("Not Connected", "Connect to the Veepeak adapter or enable Simulation Mode first.")
            return
        threading.Thread(target=self._health_scan_worker, daemon=True).start()

    def _health_scan_worker(self):
        self.ui_queue.put(("STATUS", ("SCANNING HEALTH...", "Querying critical engine PIDs for health analysis...")))
        self._poll_cycle(single_run=True)
        self.evaluate_health_rules()
        self.ui_queue.put(("STATUS", ("HEALTH SCAN READY", "Full system health evaluation complete.")))

    def evaluate_health_rules(self):
        """Applies diagnostic rules against the latest sensor readings and updates the Health tab."""
        s = self.sensor_latest
        results = []
        fail_count = 0
        warn_count = 0

        def get_val(name):
            rec = s.get(name)
            if not rec:
                return None
            v = rec.get("value")
            try:
                return float(v)
            except (ValueError, TypeError):
                return None

        def get_stats(name):
            rec = s.get(name)
            if not rec:
                return None, None, None
            v = rec.get("value")
            mn = rec.get("min")
            mx = rec.get("max")
            try:
                v = float(v)
            except (ValueError, TypeError):
                v = None
            try:
                mn = float(mn)
            except (ValueError, TypeError):
                mn = v
            try:
                mx = float(mx)
            except (ValueError, TypeError):
                mx = v
            return v, mn, mx

        rpm = get_val("RPM")
        is_running = (rpm is not None and rpm > 450)
        is_curb_idle = (is_running and rpm < 900)

        # -------------------------------------------------------------
        # 1. ELECTRICAL & CHARGING SYSTEM TESTS
        # -------------------------------------------------------------
        volt, v_min, v_max = get_stats("ELM_VOLTAGE")
        if volt is not None:
            if is_running:
                # 1a. Alternator Charging Voltage Test
                if 13.5 <= volt <= 14.8:
                    st, msg = "PASS", f"Charging at {volt:.2f}V. Alternator and internal regulator charging normally."
                elif 13.0 <= volt < 13.5:
                    st, msg = "WARN", f"Marginal charging voltage ({volt:.2f}V). Check serpentine belt tension or worn brushes."
                    warn_count += 1
                elif volt < 13.0:
                    st, msg = "FAIL", f"Severe Undercharging ({volt:.2f}V)! Alternator not keeping up with vehicle load."
                    fail_count += 1
                else:
                    st, msg = "FAIL", f"Overcharging Danger ({volt:.2f}V)! Internal regulator shorted, risk of battery boil."
                    fail_count += 1
                results.append(("⚡ Electrical", "Alternator Output & Regulator Test", f"{volt:.2f} V", "13.5 - 14.8 V", st, msg))

                # 1b. Alternator AC Ripple & Diode Health
                if v_min is not None and v_max is not None:
                    ripple = round(v_max - v_min, 2)
                    if ripple > 0.65:
                        st_rip, msg_rip = "FAIL", f"Excessive AC Voltage Ripple (Δ {ripple:.2f}V). Stator diode breakdown in alternator."
                        fail_count += 1
                    elif ripple > 0.40:
                        st_rip, msg_rip = "WARN", f"Moderate voltage fluctuation (Δ {ripple:.2f}V). Check battery clamps and ground block."
                        warn_count += 1
                    else:
                        st_rip, msg_rip = "PASS", f"Voltage ripple stable (Δ {ripple:.2f}V). Clean DC rectification."
                    results.append(("⚡ Electrical", "Alternator AC Ripple & Diode Health", f"Δ {ripple:.2f} V", "< 0.35 V Ripple", st_rip, msg_rip))
            else:
                # 1c. Battery Resting Test (KOEO)
                if volt >= 12.4:
                    st, msg = "PASS", f"Resting battery at {volt:.2f}V. Good state of charge."
                elif 11.9 <= volt < 12.4:
                    st, msg = "WARN", f"Discharged/Weak battery ({volt:.2f}V). Charge and conduct conductance test."
                    warn_count += 1
                else:
                    st, msg = "FAIL", f"Deeply Discharged ({volt:.2f}V)! Risk of no-start or ECU reference dropouts."
                    fail_count += 1
                results.append(("⚡ Electrical", "Battery Resting / State of Charge", f"{volt:.2f} V", "12.4 - 12.8 V", st, msg))

            # 1d. Starter & Cranking Voltage Drop
            if v_min is not None and v_min < 11.5:
                if v_min >= 9.6:
                    st_crk, msg_crk = "PASS", f"Cranking voltage held above threshold ({v_min:.2f}V minimum)."
                else:
                    st_crk, msg_crk = "FAIL", f"Excessive Cranking Drop ({v_min:.2f}V < 9.6V min)! Weak battery or high starter draw."
                    fail_count += 1
                results.append(("⚡ Electrical", "Starter & Cranking Voltage Drop", f"Min {v_min:.2f} V", ">= 9.6 V Min", st_crk, msg_crk))
        else:
            results.append(("⚡ Electrical", "Battery / Alternator Test", "N/A", "12.4V (Off) / 14V (Run)", "INFO", "Awaiting voltage telemetry sample"))

        # -------------------------------------------------------------
        # 2. FUEL SYSTEM & VACUUM LEAK TESTS (MAZDA TRIBUTE / ESCAPE)
        # -------------------------------------------------------------
        stft1 = get_val("SHORT_FUEL_TRIM_1") or 0.0
        ltft1 = get_val("LONG_FUEL_TRIM_1") or 0.0
        has_trim1 = ("SHORT_FUEL_TRIM_1" in s or "LONG_FUEL_TRIM_1" in s)

        if has_trim1:
            tot1 = stft1 + ltft1
            if tot1 > 15.0:
                st, msg = "FAIL", f"High Lean Trim (+{tot1:.1f}%). Common Tribute upper intake o-ring or PCV hose leak."
                fail_count += 1
            elif tot1 > 10.0:
                st, msg = "WARN", f"Moderate Lean Trim (+{tot1:.1f}%). Minor intake vacuum leak or unmetered air."
                warn_count += 1
            elif tot1 < -12.0:
                st, msg = "FAIL", f"High Rich Trim ({tot1:.1f}%). Leaking injector or purge valve sticking open."
                fail_count += 1
            else:
                st, msg = "PASS", f"Total trim nominal ({tot1:+.1f}%). Closed-loop air/fuel mixture balanced."
            results.append(("💨 Fuel & Air", "Vacuum Leak Test (Bank 1 Total Trim)", f"{tot1:+.1f} %", "±8.0 %", st, msg))

        stft2 = get_val("SHORT_FUEL_TRIM_2")
        ltft2 = get_val("LONG_FUEL_TRIM_2")
        if stft2 is not None and ltft2 is not None:
            tot2 = stft2 + ltft2
            if tot2 > 15.0:
                st, msg = "FAIL", f"Bank 2 High Lean (+{tot2:.1f}%). Check Bank 2 lower intake gasket/injectors."
                fail_count += 1
            elif tot2 > 10.0:
                st, msg = "WARN", f"Bank 2 Moderate Lean (+{tot2:.1f}%)."
                warn_count += 1
            else:
                st, msg = "PASS", f"Bank 2 trim nominal ({tot2:+.1f}%)."
            results.append(("💨 Fuel & Air", "Vacuum Leak Test (Bank 2 Total Trim)", f"{tot2:+.1f} %", "±8.0 %", st, msg))

            # Bank split comparison
            split = abs(tot1 - tot2)
            if split > 10.0:
                st, msg = "WARN", f"Bank Split {split:.1f}%! Asymmetrical intake leak or dirty injector on one bank."
                warn_count += 1
            else:
                st, msg = "PASS", f"Banks balanced within {split:.1f}%."
            results.append(("💨 Fuel & Air", "Bank-to-Bank Fuel Trim Balance", f"Δ {split:.1f} %", "< 8.0 % Split", st, msg))

        # -------------------------------------------------------------
        # 3. INTAKE MANIFOLD PRESSURE & VACUUM (MAP)
        # -------------------------------------------------------------
        map_kpa = get_val("INTAKE_PRESSURE")
        if map_kpa is not None:
            inhg_vac = round(max(0.0, 29.92 - (map_kpa * 0.2953)), 1)
            if is_curb_idle:
                if map_kpa > 44.0:
                    st_map, msg_map = "FAIL", f"Low Engine Vacuum ({map_kpa:.1f} kPa / {inhg_vac} inHg vac). Large vacuum leak or stuck EGR."
                    fail_count += 1
                elif map_kpa > 38.0:
                    st_map, msg_map = "WARN", f"Moderate Engine Vacuum ({map_kpa:.1f} kPa / {inhg_vac} inHg vac). Minor vacuum leak."
                    warn_count += 1
                else:
                    st_map, msg_map = "PASS", f"Healthy Engine Vacuum ({map_kpa:.1f} kPa / {inhg_vac} inHg vac). Manifold airtight."
                results.append(("💨 Fuel & Air", "Intake Manifold Pressure & Engine Vacuum (MAP)", f"{map_kpa:.0f} kPa ({inhg_vac} inHg)", "28 - 36 kPa @ Idle", st_map, msg_map))

        # -------------------------------------------------------------
        # 4. COOLING SYSTEM & THERMOSTAT INTEGRITY
        # -------------------------------------------------------------
        ect = get_val("COOLANT_TEMP")
        iat = get_val("INTAKE_TEMP")
        if ect is not None:
            if ect > 108.0:
                st, msg = "FAIL", f"Overheating ({ect:.1f}°C / {ect*1.8+32:.0f}°F)! Stop engine; check fan relay/coolant."
                fail_count += 1
            elif ect > 102.0:
                st, msg = "WARN", f"High Operating Temp ({ect:.1f}°C). Electric cooling fan slow-speed test advised."
                warn_count += 1
            elif is_running and ect < 78.0 and time.time() - getattr(self, "session_start", time.time()) > 300:
                st, msg = "WARN", f"Engine Cold ({ect:.1f}°C). Thermostat stuck open, causes low MPG and P0125/P0128."
                warn_count += 1
            else:
                st, msg = "PASS", f"Coolant at {ect:.1f}°C ({ect*1.8+32:.0f}°F). Thermostat regulating properly."
            results.append(("🌡️ Cooling", "Coolant Temperature & Thermostat Integrity", f"{ect:.1f} °C", "85 - 98 °C", st, msg))

            # 4b. Cold Soak Sensor Rationality (ECT vs IAT)
            if not is_running and ect < 55.0 and iat is not None:
                soak_diff = abs(ect - iat)
                if soak_diff > 10.0:
                    st_soak, msg_soak = "WARN", f"Cold soak sensor mismatch ({soak_diff:.1f}°C split: ECT {ect:.1f}°C vs IAT {iat:.1f}°C). Sensor drift."
                    warn_count += 1
                else:
                    st_soak, msg_soak = "PASS", f"Cold soak sensors agree within {soak_diff:.1f}°C (ECT {ect:.1f}°C, IAT {iat:.1f}°C)."
                results.append(("🌡️ Cooling", "Cold Soak Sensor Rationality (ECT vs IAT)", f"Δ {soak_diff:.1f} °C", "< 6.0 °C Split", st_soak, msg_soak))

        # -------------------------------------------------------------
        # 5. AIR INDUCTION & MAF SENSOR
        # -------------------------------------------------------------
        maf = get_val("MAF")
        if maf is not None and rpm is not None and is_running:
            if is_curb_idle:
                if maf < 2.0:
                    st, msg = "WARN", f"Low flow ({maf:.1f} g/s) at idle. Hot wire contaminated; clean with MAF spray."
                    warn_count += 1
                elif maf > 6.0:
                    st, msg = "WARN", f"High idle air flow ({maf:.1f} g/s). Check for throttle sludge or AC load."
                    warn_count += 1
                else:
                    st, msg = "PASS", f"MAF reporting {maf:.1f} g/s at {rpm:.0f} RPM. Plausible engine air intake."
                results.append(("🌪️ Induction", "Mass Air Flow (MAF) Sensor Flow Check", f"{maf:.1f} g/s", "2.5 - 5.0 g/s @ idle", st, msg))

            # 5b. Calculated Fuel Consumption Rate (GPH)
            gph = round((maf * 3600.0) / (14.7 * 2800.0), 2)
            lph = round(gph * 3.785, 2)
            if is_curb_idle:
                if gph > 0.85:
                    st_gph, msg_gph = "WARN", f"High idle fuel consumption ({gph} GPH / {lph} L/h). Engine over-fueling."
                    warn_count += 1
                else:
                    st_gph, msg_gph = "PASS", f"Idle fuel burn rate nominal ({gph} GPH / {lph} L/h)."
                results.append(("⛽ Fuel Econ", "Instant Fuel Consumption Rate (Calculated GPH)", f"{gph} GPH", "0.35 - 0.65 GPH", st_gph, msg_gph))

        # -------------------------------------------------------------
        # 6. THROTTLE POSITION & ENGINE LOAD
        # -------------------------------------------------------------
        tps = get_val("THROTTLE_POS")
        if tps is not None:
            if is_curb_idle and tps > 23.0:
                st, msg = "WARN", f"High closed TPS ({tps:.1f}%). Check throttle cable binding or throttle shaft carbon."
                warn_count += 1
            elif tps < 10.0:
                st, msg = "WARN", f"Abnormally low TPS ({tps:.1f}%). Verify TPS sensor mounting."
                warn_count += 1
            else:
                st, msg = "PASS", f"TPS angle {tps:.1f}% nominal."
            results.append(("🎚️ Throttle", "Throttle Position Sensor (TPS) Resting Angle", f"{tps:.1f} %", "15 - 20 % at Idle", st, msg))

        load = get_val("ENGINE_LOAD")
        if load is not None and is_curb_idle:
            if load > 38.0:
                st_ld, msg_ld = "WARN", f"High idle engine load ({load:.1f}%). Fighting mechanical drag or severe vacuum leak."
                warn_count += 1
            elif load < 14.0:
                st_ld, msg_ld = "WARN", f"Abnormally low engine load ({load:.1f}%)."
                warn_count += 1
            else:
                st_ld, msg_ld = "PASS", f"Engine load nominal ({load:.1f}%)."
            results.append(("⚙️ Engine Load", "Engine Load vs RPM Plausibility", f"{load:.1f} %", "18 - 28 % @ Idle", st_ld, msg_ld))

        # -------------------------------------------------------------
        # 7. IGNITION SPARK TIMING
        # -------------------------------------------------------------
        timing = get_val("TIMING_ADVANCE")
        if timing is not None and is_curb_idle:
            if timing < 4.0:
                st_tim, msg_tim = "WARN", f"Retarded spark timing ({timing:.1f}° BTDC). Knock sensor active or harmonic balancer slipped."
                warn_count += 1
            elif timing > 24.0:
                st_tim, msg_tim = "WARN", f"High idle advance ({timing:.1f}° BTDC)."
                warn_count += 1
            else:
                st_tim, msg_tim = "PASS", f"Spark timing advance nominal ({timing:.1f}° BTDC)."
            results.append(("⚡ Ignition", "Ignition Spark Advance & Timing", f"{timing:.1f}° BTDC", "8 - 16° BTDC", st_tim, msg_tim))

        # -------------------------------------------------------------
        # 8. O2 SENSORS & CATALYTIC CONVERTER HEALTH
        # -------------------------------------------------------------
        o2_b1s1, b1s1_min, b1s1_max = get_stats("O2_B1S1")
        if b1s1_min is not None and b1s1_max is not None and is_running:
            b1_span = round(b1s1_max - b1s1_min, 2)
            if b1_span >= 0.45:
                st_o2, msg_o2 = "PASS", f"Bank 1 Sensor 1 actively cycling across stoich ({b1s1_min:.2f}V to {b1s1_max:.2f}V)."
            elif b1_span < 0.20:
                st_o2, msg_o2 = "WARN", f"Bank 1 Sensor 1 lazy / low amplitude ({b1s1_min:.2f}V to {b1s1_max:.2f}V). Sensor aging."
                warn_count += 1
            else:
                st_o2, msg_o2 = "PASS", f"Bank 1 Sensor 1 cycling ({b1s1_min:.2f}V to {b1s1_max:.2f}V)."
            results.append(("🔥 Emissions", "Upstream O2 Sensor Switching (Bank 1 & 2)", f"Span {b1_span:.2f} V", "Span >= 0.45 V", st_o2, msg_o2))

        o2_b1s2, b1s2_min, b1s2_max = get_stats("O2_B1S2")
        if b1s2_min is not None and b1s2_max is not None and is_running:
            b1s2_span = round(b1s2_max - b1s2_min, 2)
            if b1s2_span > 0.40:
                st_cat, msg_cat = "WARN", f"Downstream O2 oscillating ({b1s2_min:.2f}V - {b1s2_max:.2f}V). Catalyst oxygen storage depleted (P0420 precursor)."
                warn_count += 1
            else:
                st_cat, msg_cat = "PASS", f"Downstream O2 steady ({o2_b1s2 or 0.7:.2f}V). Catalytic converter active."
            results.append(("🔥 Emissions", "Catalytic Converter Downstream O2 Activity", f"{o2_b1s2 or 0.7:.2f} V", "Steady 0.6 - 0.75 V", st_cat, msg_cat))

        # -------------------------------------------------------------
        # 9. IDLE RPM STABILITY & MISFIRE PRE-SCREEN
        # -------------------------------------------------------------
        rpm_val, rpm_min, rpm_max = get_stats("RPM")
        if is_curb_idle and rpm_min is not None and rpm_max is not None:
            rpm_var = int(rpm_max - rpm_min)
            if rpm_var > 160:
                st_rpm, msg_rpm = "WARN", f"Rough / Unstable Idle (RPM delta {rpm_var}). Suspect cylinder misfire, vacuum leak, or dirty IAC valve."
                warn_count += 1
            else:
                st_rpm, msg_rpm = "PASS", f"Curb idle stable within {rpm_var} RPM."
            results.append(("📊 Stability", "Idle RPM Stability & Misfire Pre-Screen", f"Δ {rpm_var} RPM", "< 120 RPM Delta", st_rpm, msg_rpm))

        # -------------------------------------------------------------
        # 10. CHECK ENGINE LIGHT & DTCS
        # -------------------------------------------------------------
        has_mil_records = [e for e in self.timeline_history if e.get("category") == "DTC" and "NONE" not in e.get("parameter", "")]
        if has_mil_records:
            st, msg = "FAIL", f"{len(has_mil_records)} Fault code(s) recorded. Review Fault Codes tab."
            fail_count += 1
            results.append(("⚠️ Diagnostics", "Check Engine Light (MIL) & Stored DTCs", f"{len(has_mil_records)} Codes", "0 Active Codes", st, msg))
        else:
            results.append(("⚠️ Diagnostics", "Check Engine Light (MIL) & Stored DTCs", "0 Codes", "0 Active Codes", "PASS", "No active fault codes detected."))

        # Overall Status Assessment
        if fail_count > 0:
            overall_status = f"ATTENTION: {fail_count} CRITICAL ISSUE(S) FOUND"
            overall_color = "#FF5252"
        elif warn_count > 0:
            overall_status = f"ADVISORY: {warn_count} ITEM(S) TO INSPECT"
            overall_color = "#FFD600"
        else:
            overall_status = "ALL SYSTEMS HEALTHY & VERIFIED"
            overall_color = "#00E676"

        self.last_health_eval = time.time()
        self.ui_queue.put(("HEALTH", (overall_status, overall_color, results)))
    # -------------------------------------------------------------------------
    # Terms & Conditions / Legal Liability Waiver
    # -------------------------------------------------------------------------
    def _get_disclaimer_file(self):
        import os
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), ".disclaimer_accepted.json")

    def _check_terms_on_startup(self):
        import os
        disclaimer_file = self._get_disclaimer_file()
        if not os.path.exists(disclaimer_file):
            self.root.after(200, self.show_terms_and_conditions, True)

    def show_terms_and_conditions(self, is_startup: bool = False):
        win = tk.Toplevel(self.root)
        win.title("Terms & Conditions — Automotive Diagnostic Liability Waiver")
        win.geometry("860x680")
        win.configure(bg="#181818")
        win.transient(self.root)
        if is_startup:
            win.grab_set()

        header = ttk.Frame(win, style="Panel.TFrame", padding=14)
        header.pack(fill=tk.X, padx=10, pady=10)

        ttk.Label(
            header,
            text="⚠️ TERMS OF SERVICE, LIMITATION OF LIABILITY & ZERO-WARRANTY WAIVER",
            font=("Segoe UI", 12, "bold"),
            foreground="#FF5252"
        ).pack(anchor=tk.W)

        ttk.Label(
            header,
            text="Please review carefully before operating this diagnostic software on any motor vehicle.",
            font=("Segoe UI", 9),
            foreground="#B0BEC5"
        ).pack(anchor=tk.W, pady=(4, 0))

        content_frame = ttk.Frame(win, padding=10)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=10)

        txt = tk.Text(
            content_frame,
            bg="#121212",
            fg="#ECEFF1",
            font=("Consolas", 10),
            wrap=tk.WORD,
            borderwidth=1,
            relief="solid",
            padx=12,
            pady=12
        )
        scroll = ttk.Scrollbar(content_frame, orient=tk.VERTICAL, command=txt.yview)
        txt.configure(yscrollcommand=scroll.set)
        txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        disclaimer_body = (
            "========================================================================================\n"
            "   IMPORTANT LEGAL NOTICE & COMPLETE DISCLAIMER OF LIABILITY\n"
            "========================================================================================\n\n"
            "1. EXPRESS DISCLAIMER OF VEHICLE DAMAGE AND LIABILITIES:\n"
            "   THE DEVELOPER, AUTHOR, DISTRIBUTOR, AND OWNER OF THIS SOFTWARE ('CARSCAN / TRIBUTE OBD SUITE')\n"
            "   ASSUME ABSOLUTELY NO RESPONSIBILITY OR LIABILITY WHATSOEVER FOR ANY EVENT, MECHANICAL BREAKDOWN,\n"
            "   ELECTRICAL SHORT, COMPUTER/PCM/ECU DAMAGE, SENSOR MALFUNCTION, TRANSMISSION DAMAGE,\n"
            "   BLOWN FUSES, BATTERY DRAINAGE, FIRE HAZARD, PERSONAL INJURY, LOSS OF LIFE, OR PROPERTY DAMAGE\n"
            "   ARISING DIRECTLY OR INDIRECTLY FROM THE USE, TESTING, SENSOR POLLING, COMMAND ISSUING,\n"
            "   CLEARING OF DIAGNOSTIC TROUBLE CODES (DTCs), OR INTERPRETATION OF DATA DISPLAYED BY THIS TOOL.\n\n"
            "2. THE SOFTWARE DOES NOT COVER NOR WARRANTY ANYTHING THAT HAPPENS TO THE VEHICLE:\n"
            "   YOU EXPLICITLY ACKNOWLEDGE AND AGREE THAT YOU ARE USING THIS SOFTWARE ON YOUR CAR ENTIRELY\n"
            "   AT YOUR OWN SOLE RISK. NO MECHANICAL, REPAIR, TOWING, REPLACEMENT, OR FINANCIAL COSTS\n"
            "   WILL BE COVERED, REIMBURSED, OR COMPENSATED UNDER ANY CIRCUMSTANCES.\n\n"
            "3. NO PROFESSIONAL OR CERTIFIED ADVICE PROVIDED:\n"
            "   All automated diagnostic test results (including battery assessments, alternator tests, vacuum\n"
            "   leak estimates, catalytic converter statuses, and guided repair steps) are generated algorithmically\n"
            "   for informational, hobbyist, and diagnostic troubleshooting assistance only. They do not constitute\n"
            "   certified professional mechanical or engineering opinions. Always verify symptoms with an ASE-certified\n"
            "   automotive technician before conducting repairs or replacing components.\n\n"
            "4. HIGH-RISK OPERATIONS (MODE 04 CLEAR DTCs & RAW COMMANDS):\n"
            "   Clearing diagnostic codes (Mode 04) will erase vehicle freeze-frame records and reset all OBD-II\n"
            "   readiness inspection monitors to INCOMPLETE, which will cause the vehicle to fail state emissions\n"
            "   testing until a full drive cycle is completed. Sending raw ELM327 / AT / Hex commands directly to\n"
            "   the ECU serial bus can interrupt vehicle module communication if used incorrectly.\n\n"
            "5. ROAD SAFETY AND OPERATIONAL HAZARD:\n"
            "   NEVER configure, read, or manipulate this software while operating a moving vehicle on public\n"
            "   roadways. Only perform diagnostic scans when the vehicle is stationary, parked safely, with the\n"
            "   emergency brake firmly set, or with an assistant operating the diagnostic console.\n\n"
            "========================================================================================\n"
            "BY PROCEEDING AND CHECKING THE BOX BELOW, YOU CONFIRM THAT YOU ARE AT LEAST 18 YEARS OF AGE,\n"
            "LEGALLY AUTHORIZED TO OPERATE THIS VEHICLE, AND AGREE TO BE BOUND BY THIS COMPLETE WAIVER OF LIABILITY.\n"
            "========================================================================================\n"
        )
        txt.insert(tk.END, disclaimer_body)
        txt.configure(state=tk.DISABLED)

        bot_frame = ttk.Frame(win, style="Panel.TFrame", padding=12)
        bot_frame.pack(fill=tk.X, padx=10, pady=(0, 10))

        agreed_var = tk.BooleanVar(value=not is_startup)

        def save_and_close():
            import json
            try:
                with open(self._get_disclaimer_file(), "w", encoding="utf-8") as f:
                    json.dump({"accepted": True, "timestamp": datetime.datetime.now().isoformat()}, f)
            except Exception:
                pass
            win.destroy()

        def on_check():
            if agreed_var.get():
                btn_accept.configure(state=tk.NORMAL)
            else:
                btn_accept.configure(state=tk.DISABLED)

        chk = ttk.Checkbutton(
            bot_frame,
            text="I have read, understood, and accept these Terms & Conditions and agree that the developer covers NO vehicle damage.",
            variable=agreed_var,
            command=on_check
        )
        chk.pack(side=tk.LEFT, padx=6)

        btn_accept = ttk.Button(
            bot_frame,
            text="Accept & Proceed",
            style="Accent.TButton",
            command=save_and_close,
            state=tk.NORMAL if not is_startup else tk.DISABLED
        )
        btn_accept.pack(side=tk.RIGHT, padx=6)

        if is_startup:
            ttk.Button(
                bot_frame,
                text="Decline & Exit",
                style="Danger.TButton",
                command=self.root.destroy
            ).pack(side=tk.RIGHT, padx=6)

    # -------------------------------------------------------------------------
    # Troubleshooting & Guided Diagnostic Wizards Tab
    # -------------------------------------------------------------------------
    def _build_tab_troubleshooting_wizard(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Troubleshooting & Repair Wizards")

        paned = ttk.PanedWindow(tab, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        # Left list of common 2002 Mazda Tribute issues
        left_frame = ttk.Frame(paned, style="Panel.TFrame", padding=8, width=380)
        paned.add(left_frame, weight=1)

        ttk.Label(left_frame, text="Select Problem to Troubleshoot:", style="Header.TLabel").pack(anchor=tk.W, pady=(0, 6))

        wizards = [
            ("P0171 / P0174: Lean Vacuum Leak Wizard", "LEAN"),
            ("P0300 - P0306: Misfire & Ignition Coil (COP)", "MISFIRE"),
            ("P0401: EGR Insufficient Flow / DPFE Sensor", "EGR"),
            ("P0125 / P0128: Thermostat Stuck & Overheating", "COOLING"),
            ("Electrical: Alternator Ripple & Battery Drain", "ELECTRICAL"),
            ("Transmission: CD4E Shift Flare & Fluid Temp", "TRANS"),
            ("P0420 / P0430: Catalytic Converter Efficiency", "CATALYST"),
            ("P0505 / P0506: Idle Air Control & Rough Idle", "IAC")
        ]

        self.selected_wizard_var = tk.StringVar(value="LEAN")
        for label, tag in wizards:
            ttk.Radiobutton(
                left_frame,
                text=label,
                value=tag,
                variable=self.selected_wizard_var,
                command=self._display_wizard_details
            ).pack(anchor=tk.W, pady=3, padx=4)

        # Quick action buttons
        ttk.Separator(left_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)
        ttk.Label(left_frame, text="Quick Diagnostic Tool Actions:", style="Header.TLabel").pack(anchor=tk.W, pady=(0, 4))

        ttk.Button(
            left_frame,
            text="⚡ Run Live Vacuum Leak Check (Trims)",
            command=self._wizard_check_vacuum
        ).pack(fill=tk.X, pady=3)

        ttk.Button(
            left_frame,
            text="🔋 Test Alternator AC Ripple & Voltage",
            command=self._wizard_check_voltage
        ).pack(fill=tk.X, pady=3)

        ttk.Button(
            left_frame,
            text="🌡️ Query CD4E Trans Fluid Temp (Mode 22)",
            command=lambda: self._run_preset("22 16 74")
        ).pack(fill=tk.X, pady=3)

        # Right frame: Detailed Guided Walkthrough
        right_frame = ttk.Frame(paned, style="Panel.TFrame", padding=10)
        paned.add(right_frame, weight=3)

        self.lbl_wiz_title = ttk.Label(right_frame, text="Interactive Troubleshooting Guide", font=("Segoe UI", 12, "bold"), foreground="#00E5FF")
        self.lbl_wiz_title.pack(anchor=tk.W, pady=(0, 6))

        self.txt_wizard = tk.Text(
            right_frame,
            bg="#141414",
            fg="#EEEEEE",
            font=("Segoe UI", 10),
            wrap=tk.WORD,
            borderwidth=1,
            relief="solid",
            padx=12,
            pady=12
        )
        scroll_w = ttk.Scrollbar(right_frame, orient=tk.VERTICAL, command=self.txt_wizard.yview)
        self.txt_wizard.configure(yscrollcommand=scroll_w.set)
        self.txt_wizard.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_w.pack(side=tk.RIGHT, fill=tk.Y)

        self._display_wizard_details()

    def _wizard_check_vacuum(self):
        self.run_full_health_scan()
        messagebox.showinfo("Vacuum Test", "Vacuum & Fuel Trim evaluation updated in the 'Automated Health & Issue Tests' tab.")

    def _wizard_check_voltage(self):
        self.run_full_health_scan()
        volt_rec = self.sensor_latest.get("ELM_VOLTAGE", {})
        val = volt_rec.get("value", "N/A")
        mn = volt_rec.get("min", "N/A")
        mx = volt_rec.get("max", "N/A")
        messagebox.showinfo(
            "Voltage Diagnostic",
            f"Current Voltage: {val} V\nObserved Minimum: {mn} V\nObserved Maximum: {mx} V\n\nCheck the Health tab for Alternator Ripple analysis."
        )

    def _display_wizard_details(self):
        tag = self.selected_wizard_var.get()
        guides = {
            "LEAN": (
                "P0171 / P0174 — SYSTEM TOO LEAN (BANK 1 & BANK 2 VACUUM LEAK WIZARD)\n\n"
                "• BACKGROUND ON 2002 MAZDA TRIBUTE 3.0L DURATEC V6:\n"
                "  This is the #1 most common failure on 2001-2004 Mazda Tributes and Ford Escapes. As the engine ages,\n"
                "  the green silicone upper intake manifold o-rings shrink in cold weather, and the rubber PCV hose elbow\n"
                "  nestled beneath the throttle body collapses and cracks from oil vapor.\n\n"
                "• LIVE PID CONFIRMATION:\n"
                "  1. Go to 'Live Sensors & PIDs' or 'Automated Health Tests'.\n"
                "  2. Observe SHORT_FUEL_TRIM_1/2 and LONG_FUEL_TRIM_1/2 at curb idle (approx 700 RPM).\n"
                "  3. If Total Trim (STFT + LTFT) is > +15% at idle, but DROPS to under +8% when revved to 2500 RPM,\n"
                "     a vacuum leak is 100% CONFIRMED (vacuum leaks have less influence as throttle opens).\n\n"
                "• STEP-BY-STEP TROUBLESHOOTING & REPAIR:\n"
                "  Step 1: Inspect the 90-degree rubber PCV hose elbow located under the lower rear of the intake plenum.\n"
                "          It often softens and sucks flat, developing a split along the seam.\n"
                "  Step 2: Replace Upper Intake Plenum Gaskets (6 upper oval port seals, Ford Part # 2L8Z-9461-BA).\n"
                "  Step 3: Clean the MAF sensor with aerosol MAF cleaner (never touch the heated wires directly).\n"
                "  Step 4: Check the brake booster vacuum hose and vacuum lines connecting to the EGR vacuum solenoid."
            ),
            "MISFIRE": (
                "P0300 - P0306 — CYLINDER MISFIRE & COIL-ON-PLUG (COP) WIZARD\n\n"
                "• CYLINDER LAYOUT (2002 MAZDA TRIBUTE 3.0L V6):\n"
                "  FIREWALL (Rear / Bank 1):   [Cylinder 1]  [Cylinder 2]  [Cylinder 3]\n"
                "  RADIATOR (Front / Bank 2):   [Cylinder 4]  [Cylinder 5]  [Cylinder 6]\n"
                "  *Note: Cylinders 1, 2, 3 require removing the upper intake manifold to access.*\n\n"
                "• DIAGNOSTIC PROCEDURE:\n"
                "  Step 1: Check the DTC code to identify the cylinder (P0301 = Cyl 1, P0304 = Cyl 4, etc.).\n"
                "  Step 2: Swap the suspected ignition coil with an easily accessible front cylinder (Cyl 4, 5, or 6).\n"
                "          Clear codes and test drive. If the misfire code moves with the coil, the coil is bad.\n"
                "  Step 3: Inspect spark plug wells for oil contamination caused by leaking valve cover spark plug tube seals.\n"
                "  Step 4: Always use Motorcraft AGSF-32N-M / Double Platinum plugs gapped to 0.054 in (1.37 mm)."
            ),
            "EGR": (
                "P0401 — EGR INSUFFICIENT FLOW DETECTED (DPFE SENSOR WIZARD)\n\n"
                "• THE COMMON CULPRIT: DPFE SENSOR\n"
                "  On the 2002 Tribute, the Delta Pressure Feedback EGR (DPFE) sensor (rectangular sensor with two small\n"
                "  silicone hoses connected to the metal EGR pipe) has an extremely high failure rate due to moisture condensation.\n\n"
                "• STEP-BY-STEP DIAGNOSIS:\n"
                "  Step 1: Inspect the two silicone rubber hoses going from the metal EGR tube to the DPFE sensor.\n"
                "          If they are melted, cracked, or clogged with soot, the sensor cannot read pressure drops.\n"
                "  Step 2: Remove the EGR valve and check the intake manifold passage for carbon buildup.\n"
                "  Step 3: Replace the DPFE sensor with an updated plastic Motorcraft DPFE-4 (or equivalent)."
            ),
            "COOLING": (
                "COOLING SYSTEM, OVERHEATING & THERMOSTAT STUCK OPEN (P0125/P0128)\n\n"
                "• OPERATING TEMPERATURE SPECIFICATION: 88°C – 98°C (190°F – 208°F)\n\n"
                "• THERMOSTAT STUCK OPEN (P0125 / P0128):\n"
                "  If the engine never exceeds 75°C (167°F) while driving, the thermostat is stuck open. The PCM will remain in\n"
                "  Open-Loop warmup mode, burning 20-30% more gasoline and never running EVAP/Catalyst emissions monitors.\n\n"
                "• OVERHEATING (> 105°C / 221°F):\n"
                "  Step 1: Check dual electric cooling fans. Low speed should trigger at 100°C (212°F); high speed at 106°C (223°F).\n"
                "  Step 2: Test the cooling fan low-speed resistor and underhood fan relays.\n"
                "  Step 3: Inspect the water pump drive belt on the rear of the camshaft (Duratec 3.0L)."
            ),
            "ELECTRICAL": (
                "ELECTRICAL: ALTERNATOR AC RIPPLE, CHARGING & BATTERY DRAIN\n\n"
                "• CHARGING VOLTAGE SPECIFICATIONS:\n"
                "  - Key Off Engine Off (KOEO): 12.4V – 12.8V (Healthy)\n"
                "  - Engine Running (KOER): 13.5V – 14.7V (Alternator Charging)\n"
                "  - AC Voltage Ripple: < 0.35V peak-to-peak\n\n"
                "• TROUBLESHOOTING ALTERNATOR ISSUES:\n"
                "  1. If running voltage is under 13.2V, test the serpentine belt tensioner and check for heavy corrosion\n"
                "     on the 175A master mega-fuse in the high-current engine bay distribution box.\n"
                "  2. If AC ripple exceeds 0.50V, an alternator diode has blown. This can cause erratic TCM shifting\n"
                "     and ghost communication DTCs across the J1850 data bus.\n"
                "  3. For battery drain when parked: Measure parasitic draw with a multimeter in series (should be < 50 mA)."
            ),
            "TRANS": (
                "TRANSMISSION: CD4E 4-SPEED AUTOMATIC DIAGNOSTICS & FLUID TEMP\n\n"
                "• BACKGROUND ON 2002 TRIBUTE CD4E TRANSAXLE:\n"
                "  The CD4E transmission is sensitive to fluid temperature and internal line pressure. Overheating causes\n"
                "  the forward clutch piston and 2-4 band to slip and burn.\n\n"
                "• MODE 22 EXTENDED PID TRANSMISSION FLUID TEMP (TFT):\n"
                "  Send command '22 16 74' in the Raw Console tab or click the button on the left.\n"
                "  Nominal operating temperature: 160°F – 195°F (71°C – 90°C).\n"
                "  If fluid temp exceeds 220°F (104°C), auxiliary transmission cooling is strongly advised."
            ),
            "CATALYST": (
                "P0420 / P0430 — CATALYTIC CONVERTER SYSTEM EFFICIENCY BELOW THRESHOLD\n\n"
                "• HOW TO DISTINGUISH A BAD CATALYST FROM A BAD O2 SENSOR:\n"
                "  1. Upstream O2 (B1S1 / B2S1) MUST switch rapidly between 0.1V and 0.9V.\n"
                "  2. Downstream O2 (B1S2 / B2S2) should hold a steady voltage (around 0.65V to 0.75V) with minimal movement.\n"
                "  3. IF downstream O2 mimics upstream O2 by swinging wildly between 0.1V and 0.8V, the converter's\n"
                "     precious metal washcoat has lost oxygen storage capacity, confirming catalytic converter failure."
            ),
            "IAC": (
                "P0505 / P0506 — IDLE AIR CONTROL (IAC) VALVE & ROUGH IDLE\n\n"
                "• SYMPTOMS: Engine dies when coming to a stop, or idle RPM surges between 500 and 1200 RPM.\n\n"
                "• REPAIR PROCEDURE:\n"
                "  1. The IAC valve is mounted on top of the upper intake manifold adjacent to the throttle body.\n"
                "  2. Carbon deposits build up on the internal pintle shaft, preventing it from opening smoothly.\n"
                "  3. Remove 2 bolts (8mm), clean with throttle body spray, and install a new gasket (Part # F68Z-9F670-AA)."
            )
        }
        details = guides.get(tag, "Select a guided troubleshooting wizard from the left list.")
        self.lbl_wiz_title.configure(text=f"Guided Troubleshooting: {tag}")
        self.txt_wizard.delete("1.0", tk.END)
        self.txt_wizard.insert(tk.END, details)

    def _build_tab_sensors(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Live Sensors & PIDs (Mode 01)")

        ctrl_frame = ttk.Frame(tab, style="Panel.TFrame", padding=8)
        ctrl_frame.pack(fill=tk.X, pady=(0, 4))

        ttk.Label(ctrl_frame, text="Filter Sensor:", style="Panel.TLabel").pack(side=tk.LEFT, padx=4)
        self.sensor_filter_var = tk.StringVar()
        self.sensor_filter_var.trace_add("write", lambda *args: self._refresh_sensor_tree())
        ttk.Entry(ctrl_frame, textvariable=self.sensor_filter_var, width=28).pack(side=tk.LEFT, padx=6)

        ttk.Label(ctrl_frame, text="Poll Delay (s):", style="Panel.TLabel").pack(side=tk.LEFT, padx=(16, 4))
        ttk.Spinbox(ctrl_frame, from_=0.2, to=10.0, increment=0.2, textvariable=self.poll_interval, width=6).pack(side=tk.LEFT, padx=4)

        ttk.Button(ctrl_frame, text="Scan All Supported PIDs Once", command=self.scan_all_sensors_once).pack(side=tk.LEFT, padx=12)
        ttk.Label(ctrl_frame, text="Click any column header to sort", style="Panel.TLabel").pack(side=tk.RIGHT, padx=8)

        cols = ("pid", "name", "value", "min", "max", "unit", "updated")
        self.tree_sensors = ttk.Treeview(tab, columns=cols, show="headings")
        headers = {
            "pid": ("PID / Mode", 100),
            "name": ("Sensor Parameter", 280),
            "value": ("Current Value", 150),
            "min": ("Min Observed", 130),
            "max": ("Max Observed", 130),
            "unit": ("Units", 120),
            "updated": ("Last Timestamp", 140)
        }
        for col, (text, width) in headers.items():
            self.tree_sensors.heading(col, text=text, command=lambda c=col: self.sort_treeview(self.tree_sensors, c))
            self.tree_sensors.column(col, width=width, anchor=tk.W if col in ("pid", "name", "unit") else tk.E)

        scroll = ttk.Scrollbar(tab, orient=tk.VERTICAL, command=self.tree_sensors.yview)
        self.tree_sensors.configure(yscrollcommand=scroll.set)
        self.tree_sensors.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def _build_tab_dtcs(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Fault Codes & Freeze Frame (Modes 02/03/07)")

        ctrl = ttk.Frame(tab, style="Panel.TFrame", padding=8)
        ctrl.pack(fill=tk.X, pady=(0, 4))

        ttk.Button(ctrl, text="Read Stored, Pending & Freeze Frame Codes", style="Accent.TButton", command=self.read_all_dtcs).pack(side=tk.LEFT, padx=6)
        ttk.Button(ctrl, text="Clear DTCs / Reset MIL (Mode 04)", style="Danger.TButton", command=self.clear_all_dtcs).pack(side=tk.RIGHT, padx=6)

        paned = ttk.PanedWindow(tab, orient=tk.VERTICAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # Upper: DTC List
        dtc_frame = ttk.Frame(paned)
        paned.add(dtc_frame, weight=1)

        cols_dtc = ("type", "code", "description", "timestamp")
        self.tree_dtcs = ttk.Treeview(dtc_frame, columns=cols_dtc, show="headings")
        self.tree_dtcs.heading("type", text="Code Category", command=lambda: self.sort_treeview(self.tree_dtcs, "type"))
        self.tree_dtcs.heading("code", text="DTC Code", command=lambda: self.sort_treeview(self.tree_dtcs, "code"))
        self.tree_dtcs.heading("description", text="Diagnostic Description", command=lambda: self.sort_treeview(self.tree_dtcs, "description"))
        self.tree_dtcs.heading("timestamp", text="Detected At", command=lambda: self.sort_treeview(self.tree_dtcs, "timestamp"))

        self.tree_dtcs.column("type", width=160)
        self.tree_dtcs.column("code", width=120)
        self.tree_dtcs.column("description", width=680)
        self.tree_dtcs.column("timestamp", width=160)
        self.tree_dtcs.pack(fill=tk.BOTH, expand=True)

        # Lower: Freeze Frame Snapshot
        ff_frame = ttk.Frame(paned)
        paned.add(ff_frame, weight=1)

        ttk.Label(ff_frame, text="Mode 02 Freeze Frame Snapshot (Engine Conditions When Fault Occurred):", style="Header.TLabel").pack(fill=tk.X, pady=(6, 2))
        cols_ff = ("parameter", "value", "unit")
        self.tree_ff = ttk.Treeview(ff_frame, columns=cols_ff, show="headings")
        self.tree_ff.heading("parameter", text="Freeze Frame Parameter", command=lambda: self.sort_treeview(self.tree_ff, "parameter"))
        self.tree_ff.heading("value", text="Recorded Snapshot Value", command=lambda: self.sort_treeview(self.tree_ff, "value"))
        self.tree_ff.heading("unit", text="Unit", command=lambda: self.sort_treeview(self.tree_ff, "unit"))
        self.tree_ff.column("parameter", width=380)
        self.tree_ff.column("value", width=220)
        self.tree_ff.column("unit", width=160)
        self.tree_ff.pack(fill=tk.BOTH, expand=True)

    def _build_tab_readiness(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Readiness Verification & ECU Info (Modes 01/06/09)")

        ctrl = ttk.Frame(tab, style="Panel.TFrame", padding=8)
        ctrl.pack(fill=tk.X, pady=(0, 4))

        ttk.Button(ctrl, text="Run Complete Verification & Inspection Check", style="Accent.TButton", command=self.read_verification_monitors).pack(side=tk.LEFT, padx=6)
        self.lbl_mil_summary = ttk.Label(ctrl, text="MIL (Check Engine Light): UNKNOWN | Total DTC Count: --", style="Header.TLabel")
        self.lbl_mil_summary.pack(side=tk.RIGHT, padx=10)

        cols = ("category", "monitor", "available", "complete", "details")
        self.tree_monitors = ttk.Treeview(tab, columns=cols, show="headings")
        self.tree_monitors.heading("category", text="System Category", command=lambda: self.sort_treeview(self.tree_monitors, "category"))
        self.tree_monitors.heading("monitor", text="Verification Monitor / Test", command=lambda: self.sort_treeview(self.tree_monitors, "monitor"))
        self.tree_monitors.heading("available", text="Supported", command=lambda: self.sort_treeview(self.tree_monitors, "available"))
        self.tree_monitors.heading("complete", text="Verification Status", command=lambda: self.sort_treeview(self.tree_monitors, "complete"))
        self.tree_monitors.heading("details", text="Diagnostic Notes / Thresholds", command=lambda: self.sort_treeview(self.tree_monitors, "details"))

        self.tree_monitors.column("category", width=180)
        self.tree_monitors.column("monitor", width=260)
        self.tree_monitors.column("available", width=120, anchor=tk.CENTER)
        self.tree_monitors.column("complete", width=160, anchor=tk.CENTER)
        self.tree_monitors.column("details", width=450)
        self.tree_monitors.pack(fill=tk.BOTH, expand=True)

    def _build_tab_timeline(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Timeline Diagnostics & Anomaly Log")

        ctrl = ttk.Frame(tab, style="Panel.TFrame", padding=8)
        ctrl.pack(fill=tk.X, pady=(0, 4))

        ttk.Label(ctrl, text="Filter Category:", style="Panel.TLabel").pack(side=tk.LEFT, padx=4)
        self.timeline_filter = tk.StringVar(value="ALL")
        cb = ttk.Combobox(ctrl, textvariable=self.timeline_filter, values=["ALL", "ANOMALY", "DTC", "VERIFY", "SENSOR", "SYSTEM"], width=14, state="readonly")
        cb.pack(side=tk.LEFT, padx=6)
        cb.bind("<<ComboboxSelected>>", lambda e: self._refresh_timeline_tree())

        ttk.Button(ctrl, text="Clear Timeline History", command=self._clear_timeline).pack(side=tk.RIGHT, padx=6)

        cols = ("timestamp", "elapsed", "category", "parameter", "value", "notes")
        self.tree_timeline = ttk.Treeview(tab, columns=cols, show="headings")
        self.tree_timeline.heading("timestamp", text="Timestamp", command=lambda: self.sort_treeview(self.tree_timeline, "timestamp"))
        self.tree_timeline.heading("elapsed", text="Session +s", command=lambda: self.sort_treeview(self.tree_timeline, "elapsed"))
        self.tree_timeline.heading("category", text="Event Type", command=lambda: self.sort_treeview(self.tree_timeline, "category"))
        self.tree_timeline.heading("parameter", text="Sensor / Subsystem", command=lambda: self.sort_treeview(self.tree_timeline, "parameter"))
        self.tree_timeline.heading("value", text="Recorded Value", command=lambda: self.sort_treeview(self.tree_timeline, "value"))
        self.tree_timeline.heading("notes", text="Diagnostic Evaluation", command=lambda: self.sort_treeview(self.tree_timeline, "notes"))

        self.tree_timeline.column("timestamp", width=150)
        self.tree_timeline.column("elapsed", width=95, anchor=tk.E)
        self.tree_timeline.column("category", width=110, anchor=tk.CENTER)
        self.tree_timeline.column("parameter", width=230)
        self.tree_timeline.column("value", width=160, anchor=tk.E)
        self.tree_timeline.column("notes", width=460)

        scroll = ttk.Scrollbar(tab, orient=tk.VERTICAL, command=self.tree_timeline.yview)
        self.tree_timeline.configure(yscrollcommand=scroll.set)
        self.tree_timeline.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.session_start = time.time()

    def _build_tab_raw_console(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Raw ELM327 / J1850 Hex Console (Mode 22 / Mode 06)")

        info = ttk.Label(
            tab,
            text="Send direct AT or OBD Hex commands (e.g., 'AT RV' for battery voltage, '01 00' for PIDs, '06 01' for J1850 Mode 06 tests, '22 11 01' for Ford/Mazda extended PIDs).",
            style="Panel.TLabel",
            padding=8
        )
        info.pack(fill=tk.X)

        cmd_bar = ttk.Frame(tab, style="Panel.TFrame", padding=8)
        cmd_bar.pack(fill=tk.X, pady=(0, 4))

        self.raw_cmd_var = tk.StringVar(value="AT RV")
        entry = ttk.Entry(cmd_bar, textvariable=self.raw_cmd_var, width=40, font=("Consolas", 11))
        entry.pack(side=tk.LEFT, padx=6)
        entry.bind("<Return>", lambda e: self.send_raw_command())

        ttk.Button(cmd_bar, text="Send Command", style="Accent.TButton", command=self.send_raw_command).pack(side=tk.LEFT, padx=6)

        # Quick Preset Buttons for 2002 Mazda Tribute
        presets = [
            ("Battery Voltage (AT RV)", "AT RV"),
            ("Protocol Info (AT DP)", "AT DP"),
            ("J1850 O2 Mode 06 (0601)", "06 01"),
            ("J1850 Misfire Mode 06 (0653)", "06 53"),
            ("Ford Trans Temp (221674)", "22 16 74")
        ]
        for label, cmd in presets:
            ttk.Button(cmd_bar, text=label, command=lambda c=cmd: self._run_preset(c)).pack(side=tk.LEFT, padx=4)

        self.txt_console = tk.Text(tab, bg="#161616", fg="#00E676", font=("Consolas", 10), insertbackground="#FFFFFF")
        self.txt_console.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

    # -------------------------------------------------------------------------
    # Utility & Sorting Methods
    # -------------------------------------------------------------------------
    def _get_candidate_ports(self):
        """Scans for valid serial ports, filtering out Windows incoming Bluetooth ports that error."""
        valid = []
        if OBD_AVAILABLE:
            try:
                for p in serial.tools.list_ports.comports():
                    # Filter out Windows incoming virtual Bluetooth ports
                    if "LOCALMFG" in p.hwid or "000000000000" in p.hwid:
                        continue
                    valid.append(p.device)
            except Exception as e:
                self.log_event("SYSTEM", "Port Scan Error", str(e), level="WARN")
        return valid

    def _refresh_ports(self):
        detected = self._get_candidate_ports()
        if not detected and OBD_AVAILABLE:
            try:
                detected = [
                    p.device for p in serial.tools.list_ports.comports()
                    if not ("LOCALMFG" in p.hwid or "000000000000" in p.hwid)
                ]
            except Exception:
                detected = []
        ports = ["Auto-Detect"] + detected
        self.port_combo["values"] = ports
        if detected:
            self.selected_port.set(detected[0])
        else:
            self.selected_port.set("Auto-Detect")

    def sort_treeview(self, tree: ttk.Treeview, col: str):
        """Sorts any Treeview column numerically or alphabetically on header click."""
        items = [(tree.set(k, col), k) for k in tree.get_children("")]

        def convert_val(v):
            clean = str(v).replace("%", "").replace("V", "").replace("s", "").strip()
            try:
                return (0, float(clean))
            except ValueError:
                return (1, str(v).lower())

        reverse = self.sort_Directions.get((str(tree), col), False)
        items.sort(key=lambda t: convert_val(t[0]), reverse=reverse)

        for index, (_, k) in enumerate(items):
            tree.move(k, "", index)

        self.sort_Directions[(str(tree), col)] = not reverse

    def log_event(self, category: str, parameter: str, value: str, notes: str = "", level: str = "INFO"):
        now_str = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        elapsed = f"{time.time() - getattr(self, 'session_start', time.time()):.1f}s"
        entry = {
            "timestamp": now_str,
            "elapsed": elapsed,
            "category": category.upper(),
            "parameter": parameter,
            "value": str(value),
            "notes": notes or level
        }
        self.ui_queue.put(("TIMELINE", entry))

    def _clear_timeline(self):
        self.timeline_history.clear()
        for item in self.tree_timeline.get_children():
            self.tree_timeline.delete(item)

    def _refresh_timeline_tree(self):
        for item in self.tree_timeline.get_children():
            self.tree_timeline.delete(item)
        flt = self.timeline_filter.get()
        for entry in self.timeline_history:
            if flt == "ALL" or entry["category"] == flt:
                self.tree_timeline.insert(
                    "",
                    0,
                    values=(entry["timestamp"], entry["elapsed"], entry["category"], entry["parameter"], entry["value"], entry["notes"])
                )

    def _refresh_sensor_tree(self):
        flt = self.sensor_filter_var.get().strip().lower()
        for item in self.tree_sensors.get_children():
            self.tree_sensors.delete(item)

        for name, data in sorted(self.sensor_latest.items()):
            if flt and flt not in name.lower() and flt not in data["pid"].lower():
                continue
            self.tree_sensors.insert(
                "",
                tk.END,
                iid=name,
                values=(
                    data["pid"],
                    name,
                    data["value"],
                    data["min"],
                    data["max"],
                    data["unit"],
                    data["updated"]
                )
            )

    # -------------------------------------------------------------------------
    # Connection & Background Worker Threads
    # -------------------------------------------------------------------------
    def toggle_connection(self):
        if self.is_connected:
            self.disconnect_obd()
        else:
            threading.Thread(target=self._connect_worker, daemon=True).start()

    def _connect_worker(self):
        self.ui_queue.put(("STATUS", ("CONNECTING...", "Initializing Veepeak VP11 link...")))

        if self.sim_mode.get():
            time.sleep(0.6)
            self.is_connected = True
            self.ui_queue.put(("CONNECTED", ("SIMULATION-VP11", "SAE J1850 PWM (Simulated 2002 Tribute)", "14.1V")))
            self.log_event("SYSTEM", "Connection", "Simulation Active", "Running virtual 2002 Mazda Tribute 3.0L V6 ECU")
            self._run_initial_discovery()
            return

        if not OBD_AVAILABLE:
            self.ui_queue.put(("ERROR", "Missing python-obd / pyserial libraries. Enable Simulation Mode or install packages."))
            return

        port_arg = None if self.selected_port.get() == "Auto-Detect" else self.selected_port.get()
        if not port_arg:
            candidates = self._get_candidate_ports()
            if candidates:
                port_arg = candidates[0]
                self.ui_queue.put(("STATUS", ("CONNECTING...", f"Targeting detected adapter on {port_arg}...")))

        proto_str = self.selected_proto.get()
        proto_arg = None if proto_str == "Auto-Detect" else proto_str.split(" ")[0]

        try:
            self.ui_queue.put(("STATUS", ("CONNECTING...", f"Opening {port_arg or 'adapter'} link...")))
            # fast=False is critical for Veepeak VP11 + 2002 Mazda Tribute J1850 PWM stability
            with self.serial_lock:
                self.connection = obd.OBD(
                    portstr=port_arg,
                    protocol=proto_arg,
                    fast=False,
                    timeout=8.0
                )

            if self.connection and self.connection.status() == OBDStatus.CAR_CONNECTED:
                self.is_connected = True
                port_name = self.connection.port_name()
                proto_name = self.connection.protocol_name()

                # Query voltage if supported
                volt_str = "N/A"
                try:
                    with self.serial_lock:
                        r_volt = self.connection.query(obd.commands.ELM_VOLTAGE)
                    if not r_volt.is_null():
                        volt_str = str(r_volt.value)
                except Exception:
                    pass

                self.supported_commands = list(self.connection.supported_commands)
                self.ui_queue.put(("CONNECTED", (port_name, proto_name, volt_str)))
                self.log_event(
                    "SYSTEM",
                    "ECU Connected",
                    f"{port_name} ({proto_name})",
                    f"Discovered {len(self.supported_commands)} supported commands"
                )
                self._run_initial_discovery()
            else:
                status_msg = self.connection.status() if self.connection else "No response"
                self.ui_queue.put(("ERROR", f"Adapter Status: {status_msg}.\n\nVerify Veepeak VP11 is paired, car ignition is ON, and COM port is {port_arg or 'Outgoing Bluetooth COM port'}."))
                if self.connection:
                    with self.serial_lock:
                        self.connection.close()
                    self.connection = None
        except Exception as exc:
            self.ui_queue.put(("ERROR", f"Connection Exception: {exc}"))
            self.log_event("SYSTEM", "Connection Failure", str(exc), "Verify Bluetooth pairing PIN 1234", level="ERROR")
            if self.connection:
                try:
                    self.connection.close()
                except Exception:
                    pass
                self.connection = None

    def _run_initial_discovery(self):
        """Runs the initial diagnostics sequentially to avoid serial bus collisions."""
        self.ui_queue.put(("STATUS", ("READING MONITORS...", "Reading emissions readiness status (Mode 01)...")))
        self._verification_worker_sync()
        self.ui_queue.put(("STATUS", ("READING DTCS...", "Scanning stored & pending fault codes...")))
        self._dtc_worker_sync()
        self.ui_queue.put(("STATUS", ("SCANNING SENSORS...", "Scanning initial Mode 01 telemetry...")))
        self._poll_cycle(single_run=True)
        self.evaluate_health_rules()
        self.ui_queue.put(("STATUS", ("CONNECTED & READY", "Ready. Click 'Start Live Polling' for live telemetry streaming.")) )

    def disconnect_obd(self):
        self.is_polling = False
        self.is_connected = False
        if self.connection:
            try:
                with self.serial_lock:
                    self.connection.close()
            except Exception:
                pass
            self.connection = None
        self.lbl_status.configure(text="STATUS: DISCONNECTED")
        self.btn_connect.configure(text="Connect Adapter")
        self.btn_poll.configure(state=tk.DISABLED, text="Start Live Polling")
        self.log_event("SYSTEM", "Disconnect", "Closed", "Serial connection safely terminated")

    # -------------------------------------------------------------------------
    # Sensor Scanning & Live Polling
    # -------------------------------------------------------------------------
    def toggle_polling(self):
        if not self.is_connected:
            return
        self.is_polling = not self.is_polling
        if self.is_polling:
            self.btn_poll.configure(text="Stop Live Polling")
            threading.Thread(target=self._polling_worker, daemon=True).start()
        else:
            self.btn_poll.configure(text="Start Live Polling")

    def scan_all_sensors_once(self):
        if not self.is_connected:
            messagebox.showwarning("Not Connected", "Connect to the Veepeak adapter or enable Simulation Mode first.")
            return
        threading.Thread(target=self._poll_cycle, kwargs={"single_run": True}, daemon=True).start()

    def _polling_worker(self):
        while self.is_polling and self.is_connected:
            self._poll_cycle(single_run=False)
            time.sleep(max(0.2, float(self.poll_interval.get())))

    def _poll_cycle(self, single_run: bool = False):
        now_str = datetime.datetime.now().strftime("%H:%M:%S")
        if self.sim_mode.get():
            sim_sensors = [
                ("010C", "RPM", round(random.uniform(720, 2650), 0), "rpm"),
                ("010D", "SPEED", round(random.uniform(0, 65), 1), "mph"),
                ("0105", "COOLANT_TEMP", round(random.uniform(88, 108), 1), "degC"),
                ("0104", "ENGINE_LOAD", round(random.uniform(18, 75), 1), "%"),
                ("0106", "SHORT_FUEL_TRIM_1", round(random.uniform(-8.5, 16.2), 2), "%"),
                ("0107", "LONG_FUEL_TRIM_1", round(random.uniform(-4.0, 14.5), 2), "%"),
                ("0108", "SHORT_FUEL_TRIM_2", round(random.uniform(-7.0, 12.0), 2), "%"),
                ("0109", "LONG_FUEL_TRIM_2", round(random.uniform(-3.5, 11.2), 2), "%"),
                ("010B", "INTAKE_PRESSURE", round(random.uniform(28, 95), 1), "kPa"),
                ("010E", "TIMING_ADVANCE", round(random.uniform(8, 28), 1), "deg"),
                ("010F", "INTAKE_TEMP", round(random.uniform(24, 52), 1), "degC"),
                ("0110", "MAF", round(random.uniform(3.2, 42.0), 2), "g/s"),
                ("0111", "THROTTLE_POS", round(random.uniform(14.5, 62.0), 1), "%"),
                ("0114", "O2_B1S1", round(random.uniform(0.1, 0.88), 3), "V"),
                ("0115", "O2_B1S2", round(random.uniform(0.65, 0.78), 3), "V"),
                ("0118", "O2_B2S1", round(random.uniform(0.12, 0.86), 3), "V"),
                ("ATRV", "ELM_VOLTAGE", round(random.uniform(13.1, 14.4), 2), "V")
            ]
            for pid, name, val, unit in sim_sensors:
                self._record_sensor_value(pid, name, val, unit, now_str)
            return

        # Real Vehicle Polling: Query all Mode 1 commands + ELM Voltage
        cmds_to_query = [
            c for c in self.supported_commands
            if getattr(c, "mode", None) == 1 and c.name not in ("STATUS", "FREEZE_DTC", "PIDS_A", "PIDS_B", "PIDS_C")
        ]
        if obd.commands.ELM_VOLTAGE not in cmds_to_query:
            cmds_to_query.append(obd.commands.ELM_VOLTAGE)

        for cmd in cmds_to_query:
            if not self.is_connected or (not self.is_polling and not single_run):
                break
            try:
                with self.serial_lock:
                    resp = self.connection.query(cmd)
                if resp.is_null():
                    continue
                val_obj = resp.value
                if hasattr(val_obj, "magnitude"):
                    num_val = round(float(val_obj.magnitude), 3)
                    unit_str = str(val_obj.units)
                else:
                    num_val = str(val_obj)
                    unit_str = ""

                pid_code = cmd.command.decode("utf-8", errors="ignore") if isinstance(cmd.command, bytes) else str(cmd.command)
                self._record_sensor_value(pid_code, cmd.name, num_val, unit_str, now_str)
            except Exception as e:
                self.log_event("SYSTEM", f"PID Error ({cmd.name})", str(e), "Skipped failed sensor frame", level="WARN")

    def _record_sensor_value(self, pid: str, name: str, val, unit: str, timestamp: str):
        prev = self.sensor_latest.get(name)
        is_numeric = isinstance(val, (int, float))

        if prev is None:
            min_v = val if is_numeric else "--"
            max_v = val if is_numeric else "--"
        else:
            if is_numeric and isinstance(prev["min"], (int, float)):
                min_v = min(prev["min"], val)
                max_v = max(prev["max"], val)
            else:
                min_v, max_v = val, val

        record = {
            "pid": pid,
            "name": name,
            "value": val,
            "min": min_v,
            "max": max_v,
            "unit": unit,
            "updated": timestamp
        }
        self.ui_queue.put(("SENSOR", record))
        if getattr(self, "auto_eval_var", None) and self.auto_eval_var.get():
            if time.time() - getattr(self, "last_health_eval", 0) > 2.0:
                self.evaluate_health_rules()

        # Check for 2002 Mazda Tribute specific diagnostic anomalies
        if is_numeric:
            if "FUEL_TRIM" in name and abs(val) > 15.0:
                self.log_event(
                    "ANOMALY",
                    name,
                    f"{val} {unit}",
                    "High Fuel Trim (>15%): Check Tribute intake manifold gaskets / PCV hose vacuum leak"
                )
            elif name == "COOLANT_TEMP" and val > 105.0:
                self.log_event("ANOMALY", name, f"{val} {unit}", "Elevated Coolant Temp (>105C): Check thermostat & cooling fans")
            elif name == "ELM_VOLTAGE" and val < 12.0:
                self.log_event("ANOMALY", name, f"{val} {unit}", "Low System Voltage (<12.0V): Check alternator output / battery")
            else:
                self.log_event("SENSOR", name, f"{val} {unit}", "Nominal telemetry sample")

    # -------------------------------------------------------------------------
    # DTCs, Freeze Frame & Readiness Verification
    # -------------------------------------------------------------------------
    def read_all_dtcs(self):
        if not self.is_connected:
            messagebox.showwarning("Not Connected", "Connect to the adapter or enable Simulation Mode first.")
            return
        threading.Thread(target=self._dtc_worker_sync, daemon=True).start()

    def _dtc_worker_sync(self):
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        dtc_rows = []
        ff_rows = []

        if self.sim_mode.get():
            dtc_rows = [
                ("Mode 03 (Stored)", "P0171", "System Too Lean (Bank 1) - Common Tribute Upper Intake Gasket/PCV", now_str),
                ("Mode 03 (Stored)", "P0303", "Cylinder 3 Misfire Detected - Check Ignition Coil-on-Plug", now_str),
                ("Mode 07 (Pending)", "P0401", "Exhaust Gas Recirculation (EGR) Flow Insufficient Detected (DPFE Sensor)", now_str),
                ("Mode 02 (Freeze DTC)", "P0171", "DTC that triggered Freeze Frame Snapshot", now_str)
            ]
            ff_rows = [
                ("FREEZE_DTC", "P0171", "Code"),
                ("RPM", "2140", "rpm"),
                ("COOLANT_TEMP", "92.0", "degC"),
                ("SHORT_FUEL_TRIM_1", "18.75", "%"),
                ("LONG_FUEL_TRIM_1", "14.84", "%"),
                ("ENGINE_LOAD", "48.2", "%")
            ]
        else:
            # 1. Stored DTCs (Mode 03)
            try:
                with self.serial_lock:
                    r_dtc = self.connection.query(obd.commands.GET_DTC)
                if not r_dtc.is_null() and r_dtc.value:
                    for code, desc in r_dtc.value:
                        dtc_rows.append(("Mode 03 (Stored)", code, desc or "Manufacturer Specific Fault", now_str))
            except Exception as e:
                self.log_event("SYSTEM", "Mode 03 Error", str(e), level="ERROR")

            # 2. Pending DTCs (Mode 07)
            try:
                if hasattr(obd.commands, "GET_CURRENT_DTC"):
                    with self.serial_lock:
                        r_pend = self.connection.query(obd.commands.GET_CURRENT_DTC)
                    if not r_pend.is_null() and r_pend.value:
                        for code, desc in r_pend.value:
                            dtc_rows.append(("Mode 07 (Pending)", code, desc or "Pending Fault", now_str))
            except Exception as e:
                self.log_event("SYSTEM", "Mode 07 Error", str(e), level="WARN")

            # 3. Freeze Frame DTC & Parameters (Mode 02)
            try:
                with self.serial_lock:
                    r_ff_dtc = self.connection.query(obd.commands.FREEZE_DTC)
                if not r_ff_dtc.is_null() and r_ff_dtc.value:
                    code, desc = r_ff_dtc.value
                    dtc_rows.append(("Mode 02 (Freeze DTC)", code, desc or "Freeze Frame Trigger", now_str))

                    # Query Mode 02 PIDs only if a freeze frame code is actually present
                    mode2_cmds = [c for c in self.supported_commands if getattr(c, "mode", None) == 2]
                    for c in mode2_cmds:
                        with self.serial_lock:
                            r_m2 = self.connection.query(c)
                        if not r_m2.is_null():
                            val = r_m2.value
                            if hasattr(val, "magnitude"):
                                ff_rows.append((c.name, str(round(val.magnitude, 3)), str(val.units)))
                            else:
                                ff_rows.append((c.name, str(val), ""))
            except Exception as e:
                self.log_event("SYSTEM", "Mode 02 Error", str(e), level="WARN")

        if not dtc_rows:
            dtc_rows.append(("All Modes (02/03/07)", "NONE", "No Stored or Pending Trouble Codes Found", now_str))

        for category, code, desc, ts in dtc_rows:
            self.log_event("DTC", f"{code} ({category})", desc, "Fault verification scan completed")

        self.ui_queue.put(("DTCS", (dtc_rows, ff_rows)))

    def clear_all_dtcs(self):
        if not self.is_connected:
            return
        confirm = messagebox.askyesno(
            "Confirm Mode 04 Reset",
            "Clearing DTCs will turn off the Check Engine Light (MIL), wipe Freeze Frame data, and reset all Readiness Monitors to INCOMPLETE.\n\nProceed?"
        )
        if not confirm:
            return

        if not self.sim_mode.get():
            try:
                with self.serial_lock:
                    self.connection.query(obd.commands.CLEAR_DTC)
            except Exception as e:
                messagebox.showerror("Reset Error", f"Failed to clear DTCs: {e}")
                return

        self.log_event("DTC", "CLEAR_DTC (Mode 04)", "Executed", "All fault codes and readiness monitors reset")
        self.read_all_dtcs()

    def read_verification_monitors(self):
        if not self.is_connected:
            messagebox.showwarning("Not Connected", "Connect to the adapter or enable Simulation Mode first.")
            return
        threading.Thread(target=self._verification_worker_sync, daemon=True).start()

    def _verification_worker_sync(self):
        rows = []
        mil_text = "MIL: OFF | Total DTCs: 0"

        if self.sim_mode.get():
            mil_text = "MIL (Check Engine Light): ON | Total DTC Count: 2 | Ignition: Spark (Gasoline)"
            sim_monitors = [
                ("Continuous Monitor", "MISFIRE_MONITORING", "Yes", "COMPLETE (VERIFIED)", "Continuous loop active"),
                ("Continuous Monitor", "FUEL_SYSTEM_MONITORING", "Yes", "COMPLETE (VERIFIED)", "Closed-loop fuel control verified"),
                ("Continuous Monitor", "COMPONENT_MONITORING", "Yes", "COMPLETE (VERIFIED)", "Comprehensive component check passed"),
                ("Drive Cycle Monitor", "CATALYST_MONITORING", "Yes", "COMPLETE (VERIFIED)", "Bank 1 & Bank 2 efficiency within spec"),
                ("Drive Cycle Monitor", "EGR_MONITORING", "Yes", "INCOMPLETE", "Requires steady cruise 45-65 mph test"),
                ("Drive Cycle Monitor", "EVAPORATIVE_SYSTEM_MONITORING", "Yes", "INCOMPLETE", "Requires tank between 15% and 85%"),
                ("Drive Cycle Monitor", "OXYGEN_SENSOR_MONITORING", "Yes", "COMPLETE (VERIFIED)", "All 4 O2 sensors switching properly"),
                ("Drive Cycle Monitor", "OXYGEN_SENSOR_HEATER_MONITORING", "Yes", "COMPLETE (VERIFIED)", "Heater current draw within limits"),
                ("ECU Identification", "VIN (Mode 09)", "Yes", "4F2YZ041X2KM00000", "2002 Mazda Tribute 3.0L V6 AJ Engine"),
                ("ECU Identification", "CALIBRATION_ID (Mode 09)", "Yes", "2L8A-12A650-AC", "Ford EEC-V PCM Calibration")
            ]
            rows.extend(sim_monitors)
        else:
            try:
                with self.serial_lock:
                    r_stat = self.connection.query(obd.commands.STATUS)
                if not r_stat.is_null() and r_stat.value:
                    st = r_stat.value
                    mil_state = "ON (FAULT ACTIVE)" if st.MIL else "OFF (NORMAL)"
                    mil_text = f"MIL: {mil_state} | Stored DTC Count: {st.DTC_count} | Ignition: {st.ignition_type}"

                    monitor_names = [
                        "MISFIRE_MONITORING", "FUEL_SYSTEM_MONITORING", "COMPONENT_MONITORING",
                        "CATALYST_MONITORING", "HEATED_CATALYST_MONITORING", "EVAPORATIVE_SYSTEM_MONITORING",
                        "SECONDARY_AIR_SYSTEM_MONITORING", "OXYGEN_SENSOR_MONITORING",
                        "OXYGEN_SENSOR_HEATER_MONITORING", "EGR_MONITORING"
                    ]
                    for m_name in monitor_names:
                        if hasattr(st, m_name):
                            m_obj = getattr(st, m_name)
                            avail = "Yes" if m_obj.available else "No"
                            comp = "COMPLETE (VERIFIED)" if (m_obj.available and m_obj.complete) else ("INCOMPLETE" if m_obj.available else "N/A")
                            rows.append(("Readiness (Mode 01)", m_name, avail, comp, "OBD-II Emissions Inspection Monitor"))
            except Exception as e:
                self.log_event("SYSTEM", "Status Monitor Error", str(e), level="ERROR")

            # Query Mode 09 if supported
            for cmd in self.supported_commands:
                if getattr(cmd, "mode", None) == 9:
                    try:
                        with self.serial_lock:
                            r = self.connection.query(cmd)
                        if not r.is_null():
                            rows.append(("Mode 09 Info", cmd.name, "Yes", "VERIFIED", str(r.value)))
                    except Exception:
                        pass

        for cat, mon, avail, comp, det in rows:
            self.log_event("VERIFY", mon, comp, det)

        self.ui_queue.put(("MONITORS", (mil_text, rows)))

    # -------------------------------------------------------------------------
    # Raw ELM327 / J1850 Console
    # -------------------------------------------------------------------------
    def _run_preset(self, cmd: str):
        self.raw_cmd_var.set(cmd)
        self.send_raw_command()

    def send_raw_command(self):
        cmd_str = self.raw_cmd_var.get().strip().upper()
        if not cmd_str:
            return
        threading.Thread(target=self._raw_cmd_worker, args=(cmd_str,), daemon=True).start()

    def _raw_cmd_worker(self, cmd_str: str):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        if self.sim_mode.get():
            sim_replies = {
                "AT RV": "14.1V",
                "AT DP": "SAE J1850 PWM",
                "06 01": "46 01 01 00 8A 00 FF (Bank 1 Sensor 1 Switch Threshold: Passed)",
                "06 53": "46 53 01 00 00 03 E8 (Cylinder Misfire Count Test: Passed)",
                "22 16 74": "62 16 74 05 A0 (Ford/Mazda Trans Fluid Temp: 176 F)"
            }
            reply = sim_replies.get(cmd_str, f"41 {cmd_str[-2:]} 00 1A F8 (Simulated Hex Response)")
            self.ui_queue.put(("CONSOLE", f"[{ts}] > {cmd_str}\n{reply}\n\n"))
            self.log_event("SYSTEM", f"Raw Command ({cmd_str})", reply, "Simulated ELM327 query")
            return

        if not self.is_connected or not self.connection:
            self.ui_queue.put(("CONSOLE", f"[{ts}] ERROR: Connect to Veepeak adapter before sending raw commands.\n\n"))
            return

        try:
            with self.serial_lock:
                low_level = getattr(self.connection, "interface", None)
                if low_level and hasattr(low_level, "send_and_parse"):
                    lines = low_level.send_and_parse(cmd_str.encode("ascii"))
                    out = "\n".join([str(line.raw) if hasattr(line, "raw") else str(line) for line in lines])
                else:
                    out = "Low-level ELM interface busy or unavailable."
            self.ui_queue.put(("CONSOLE", f"[{ts}] > {cmd_str}\n{out or 'NO DATA'}\n\n"))
            self.log_event("SYSTEM", f"Raw Hex ({cmd_str})", out or "NO DATA", "Direct ELM327 command")
        except Exception as e:
            self.ui_queue.put(("CONSOLE", f"[{ts}] > {cmd_str}\nERROR: {e}\n\n"))

    # -------------------------------------------------------------------------
    # UI Queue Processing & Data Export
    # -------------------------------------------------------------------------
    def _process_ui_queue(self):
        try:
            while True:
                msg_type, payload = self.ui_queue.get_nowait()

                if msg_type == "STATUS":
                    title, detail = payload
                    self.lbl_status.configure(text=f"STATUS: {title}")
                    self.lbl_elm_info.configure(text=detail)

                elif msg_type == "CONNECTED":
                    port_name, proto_name, volt_str = payload
                    self.lbl_status.configure(text="STATUS: CONNECTED")
                    self.lbl_elm_info.configure(text=f"Port: {port_name} | Protocol: {proto_name} | Battery: {volt_str}")
                    self.btn_connect.configure(text="Disconnect")
                    self.btn_poll.configure(state=tk.NORMAL)

                elif msg_type == "ERROR":
                    self.lbl_status.configure(text="STATUS: CONNECTION ERROR")
                    messagebox.showerror("OBD-II Diagnostic Error", str(payload))

                elif msg_type == "HEALTH":
                    overall_status, overall_color, rows = payload
                    self.lbl_overall_health.configure(text=f"OVERALL STATUS: {overall_status}", foreground=overall_color)
                    for item in self.tree_health.get_children():
                        self.tree_health.delete(item)
                    for r in rows:
                        tag = r[4] # "PASS", "WARN", "FAIL", "INFO"
                        self.tree_health.insert("", tk.END, values=r, tags=(tag,))

                elif msg_type == "SENSOR":
                    name = payload["name"]
                    self.sensor_latest[name] = payload
                    flt = self.sensor_filter_var.get().strip().lower()
                    if not flt or flt in name.lower() or flt in payload["pid"].lower():
                        vals = (
                            payload["pid"], name, payload["value"],
                            payload["min"], payload["max"], payload["unit"], payload["updated"]
                        )
                        if self.tree_sensors.exists(name):
                            self.tree_sensors.item(name, values=vals)
                        else:
                            self.tree_sensors.insert("", tk.END, iid=name, values=vals)

                elif msg_type == "DTCS":
                    dtc_rows, ff_rows = payload
                    for item in self.tree_dtcs.get_children():
                        self.tree_dtcs.delete(item)
                    for r in dtc_rows:
                        self.tree_dtcs.insert("", tk.END, values=r)

                    for item in self.tree_ff.get_children():
                        self.tree_ff.delete(item)
                    for r in ff_rows:
                        self.tree_ff.insert("", tk.END, values=r)

                elif msg_type == "MONITORS":
                    mil_text, rows = payload
                    self.lbl_mil_summary.configure(text=mil_text)
                    for item in self.tree_monitors.get_children():
                        self.tree_monitors.delete(item)
                    for r in rows:
                        self.tree_monitors.insert("", tk.END, values=r)

                elif msg_type == "TIMELINE":
                    self.timeline_history.append(payload)
                    flt = self.timeline_filter.get()
                    if flt == "ALL" or payload["category"] == flt:
                        self.tree_timeline.insert(
                            "",
                            0,
                            values=(
                                payload["timestamp"], payload["elapsed"], payload["category"],
                                payload["parameter"], payload["value"], payload["notes"]
                            )
                        )

                elif msg_type == "CONSOLE":
                    self.txt_console.insert(tk.END, payload)
                    self.txt_console.see(tk.END)

        except queue.Empty:
            pass
        finally:
            self.root.after(100, self._process_ui_queue)

    def export_all_data(self):
        if not self.timeline_history and not self.sensor_latest:
            messagebox.showinfo("No Data", "No diagnostic data collected yet to export.")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON Diagnostic Report", "*.json"), ("CSV Timeline Log", "*.csv")],
            title="Export 2002 Mazda Tribute Diagnostic Report"
        )
        if not file_path:
            return

        try:
            if file_path.endswith(".csv"):
                with open(file_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=["timestamp", "elapsed", "category", "parameter", "value", "notes"])
                    writer.writeheader()
                    writer.writerows(self.timeline_history)
            else:
                export_payload = {
                    "vehicle": "2002 Mazda Tribute",
                    "adapter": "Veepeak VP11",
                    "exported_at": datetime.datetime.now().isoformat(),
                    "sensors_summary": self.sensor_latest,
                    "timeline_events": self.timeline_history
                }
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(export_payload, f, indent=2)

            messagebox.showinfo("Export Complete", f"Diagnostic snapshot saved to:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Export Failed", f"Could not write file: {e}")


if __name__ == "__main__":
    root = tk.Tk()
    app = MazdaTributeOBDSuite(root)
    root.mainloop()