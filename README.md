# 2002 Mazda Tribute // Veepeak VP11 Diagnostic & Timeline Suite

**Built by Zak Millikin (M_A.P.) & Anti-Gravity (Gemini 3.8 Flash Medium)**

An advanced, dark-themed OBD-II automotive diagnostic suite, timeline logger, and real-time telemetry analyzer engineered specifically for the **2002 Mazda Tribute** (3.0L Duratec V6 / 2.0L Zetec, Ford CD2 platform, Ford EEC-V PCM) and the **Veepeak VP11 Bluetooth (ELM327)** interface.

---

## 📋 Table of Contents
- [Overview](#overview)
- [Key Features](#key-features)
- [Automated Health & Issue Tests](#automated-health--issue-tests)
- [Guided Troubleshooting Wizards](#guided-troubleshooting-wizards)
- [Hardware & Connection Setup](#hardware--connection-setup)
- [Installation & Quick Start](#installation--quick-start)
- [Module Architecture](#module-architecture)
- [Common Mazda Tribute Pitfalls & Tips](#common-mazda-tribute-pitfalls--tips)
- [Terms, Conditions & Legal Disclaimer](#terms-conditions--legal-disclaimer)
- [Authors & Credits](#authors--credits)

---

## 🚗 Overview

The 2002 Mazda Tribute (shared platform with the 2001–2004 Ford Escape) communicates over the legacy **SAE J1850 PWM** (Pulse Width Modulation) protocol at 41.6 kbaud. Standard off-the-shelf OBD-II apps often struggle with J1850 timing, freeze when polling too quickly, or fail to interpret model-specific Ford EEC-V extended PIDs and failure patterns.

This suite is custom-tuned with:
- Serial-bus query locking to prevent buffer collisions on 41.6 kbaud J1850 lines.
- Intelligent Windows Bluetooth COM port filtering (automatically ignores virtual incoming listening ports like `COM5` to target real outgoing links like `COM6`).
- Pre-configured PID profiles for Tribute/Escape fuel trims, vacuum leaks, coolant temperatures, alternator ripple, and transmission fluid temperatures.
- Complete offline **Simulation Mode** for demonstrations without a vehicle connected.

---

## ⚡ Key Features

1. **Automated Health & Issue Tests (Tab 1):** Real-time automated rule evaluation across 18+ engine parameters with visual `PASS`, `WARN`, `FAIL` badges and DIY mechanical inspection advice.
2. **Troubleshooting & Guided Diagnostic Wizards (Tab 2):** Step-by-step diagnostic workflows for the most common Mazda Tribute failure codes (`P0171/P0174`, `P0300-P0306`, `P0401`, cooling fan relays, CD4E trans temp, etc.).
3. **Live Sensors & Mode 01 PID Telemetry (Tab 3):** High-speed streaming table featuring live values, min/max tracking, unit conversions, instant search filter, and column header sorting.
4. **Fault Codes & Freeze Frame (Tab 4):** Reads Stored DTCs (Mode 03), Pending DTCs (Mode 07), and Freeze Frame engine snapshots (Mode 02). Includes safe Mode 04 clearing with confirmation guards.
5. **Readiness Monitors & Inspection Verification (Tab 5):** Checks all 10 continuous and non-continuous emissions readiness monitors to verify whether the vehicle is ready for state inspection.
6. **Timeline Diagnostics & Anomaly Log (Tab 6):** Chronological event log tracking connection states, sensor threshold excursions, and anomaly warnings with millisecond timestamps.
7. **Raw ELM327 / J1850 Hex Console (Tab 7):** Direct AT/Hex terminal supporting Mode 06 component tests and Ford extended Mode 22 PIDs (e.g., `22 16 74` for transmission temperature).
8. **Snapshot Data Export:** Export complete session snapshots, including all sensor minimums/maximums and timeline logs, to formatted **JSON** or **CSV**.

---

## 🔬 Automated Health & Issue Tests

The suite evaluates incoming live telemetry against factory specifications:

| Subsystem | Diagnostic Test | Nominal Specification | Typical Failure Indication |
| :--- | :--- | :--- | :--- |
| **⚡ Electrical** | Alternator Output & Regulator | `13.5V – 14.8V` | Undercharging (< 13.0V) or Dangerous Overcharging (> 15.0V) |
| **⚡ Electrical** | Alternator AC Ripple & Diode | `< 0.35V Ripple` | Ripple > 0.60V indicates a blown alternator stator diode |
| **⚡ Electrical** | Starter & Cranking Voltage Drop | `>= 9.6V Min` | Cranking drop < 9.5V flags weak battery or high starter draw |
| **⚡ Electrical** | Battery Resting State of Charge | `12.4V – 12.8V` | Discharged (< 12.0V) in Key On, Engine Off state |
| **💨 Fuel & Air** | Vacuum Leak Test (Bank 1 & 2) | `±8.0% Total Trim` | Trim > +15% flags dried upper intake o-rings or torn PCV elbow |
| **💨 Fuel & Air** | Bank-to-Bank Fuel Trim Balance | `< 8.0% Split` | Split > 10% flags single-bank vacuum leak or clogged injector |
| **💨 Fuel & Air** | Intake Manifold Vacuum (MAP) | `28 – 36 kPa @ Idle` | MAP > 44 kPa (< 17" vac) flags large vacuum leak or stuck EGR |
| **🌡️ Cooling** | Coolant Temp & Thermostat | `85°C – 98°C` | Overheating (> 105°C) or Thermostat stuck open (< 78°C) |
| **🌡️ Cooling** | Cold-Soak Sensor Rationality | `< 6.0°C Split` | Split > 10°C between ECT and IAT flags thermistor calibration drift |
| **🌪️ Induction** | Mass Air Flow (MAF) Sensor | `2.5 – 5.0 g/s @ Idle` | Flow < 2.2 g/s indicates contaminated hot wire needing cleaning |
| **🎚️ Throttle** | TPS Idle Resting Angle | `15% – 20% Closed` | TPS > 23% flags binding throttle cable or bore carbon buildup |
| **⚙️ Engine Load** | Engine Load vs RPM | `18% – 28% @ Idle` | Load > 38% indicates excessive accessory drag or mechanical labor |
| **⚡ Ignition** | Spark Advance & Timing | `8° – 16° BTDC` | Retarded timing indicates active knock sensor retarding spark |
| **🔥 Emissions** | Upstream O2 Sensor Switching | `Span >= 0.45V` | Span < 0.20V flags lazy / degraded upstream oxygen sensor |
| **🔥 Emissions** | Downstream O2 Catalytic Monitor | `Steady 0.6 – 0.75V` | Rapid oscillation indicates catalytic converter washcoat breakdown |
| **⛽ Fuel Econ** | Instant Fuel Consumption Rate | `0.35 – 0.65 GPH` | Calculated fuel burn rate derived from MAF airflow |
| **📊 Stability** | Idle RPM Stability & Misfire | `< 120 RPM Delta` | Spread > 160 RPM indicates rough idle or intermittent misfire |
| **⚠️ Diagnostics**| Check Engine Light & DTCs | `0 Active Codes` | Real-time verification of active MIL and fault counts |

---

## 🛠️ Guided Troubleshooting Wizards

Select any problem from the **Troubleshooting & Repair Wizards** tab for interactive step-by-step diagnostic workflows:
1. **P0171 / P0174 (System Too Lean):** Identifying upper intake manifold plenum o-ring shrinkage vs. cracked rubber PCV elbows under the throttle body.
2. **P0300 – P0306 (Cylinder Misfire & COP Failures):** Cylinder bank layout guide (Rear Bank 1 Cylinders 1-2-3 vs. Front Bank 2 Cylinders 4-5-6), coil swap test procedures, and spark plug well oil leak inspection.
3. **P0401 (EGR Flow Insufficient / DPFE Sensor):** Testing DPFE silicone hoses, carbon buildup in the intake EGR port, and vacuum regulator solenoid checks.
4. **P0125 / P0128 (Thermostat & Cooling):** Diagnosing stuck-open thermostats causing open-loop fuel waste, dual electric fan low/high speed relays, and water pump drive belts.
5. **Electrical & Battery Drain:** Alternator diode ripple testing, master mega-fuse inspection, and parasitic draw isolation.
6. **Transmission (CD4E Shift Flare & Fluid Temp):** Monitoring transmission fluid temperature via Ford Mode 22 hex commands to prevent forward clutch slippage.
7. **P0420 / P0430 (Catalytic Converter vs. O2 Sensor):** Analyzing upstream vs. downstream voltage waveforms to confirm true catalyst failure before replacing converters.
8. **P0505 / P0506 (Idle Air Control):** IAC valve cleaning and pintle shaft servicing.

---

## 🔌 Hardware & Connection Setup

### 1. Adapter Requirements
- **Hardware:** Veepeak VP11 Bluetooth OBD-II Scanner (or any genuine ELM327 v1.5 compatible Bluetooth/USB adapter).
- **Vehicle Port:** Standard 16-pin OBD-II port located under the dashboard directly below the steering column.

### 2. Windows Bluetooth Pairing
1. Plug the Veepeak VP11 into the OBD-II port (red LED should illuminate).
2. On your Windows PC, go to **Settings > Bluetooth & devices > Add device > Bluetooth**.
3. Select **"OBDII"** or **"VEEPEAK"** and enter the pairing PIN (typically **`1234`** or **`0000`**).
4. Windows will generate two virtual COM ports: an **Outgoing port** (e.g., `COM6`) and an **Incoming port** (e.g., `COM5`). The software will automatically select the valid Outgoing port.

### 3. Ignition Key Position
- Turn vehicle ignition key to the **ON / RUN** position (engine may be off for KOEO testing or running for KOER testing). Instrument cluster warning lights must be illuminated to power the ECU.

---

## 💻 Installation & Quick Start

### 1. Clone or Download Repository
Navigate to the project folder:
```powershell
cd c:\Users\zaksk\Documents\Source\Python\CarScan
```

### 2. Install Required Dependencies
Ensure you install dependencies into your active Python environment:
```powershell
pip install obd pyserial
```

### 3. Launch the Application
```powershell
python tribute_obd_suite.py
```

### 4. Connect
1. The **COM Port** will automatically be set to your adapter's outgoing link (e.g., `COM6`).
2. The **Protocol** will default to **`1 - SAE J1850 PWM (Mazda/Ford)`**.
3. Click **Connect Adapter**. The suite will run its initial discovery scan, populate readiness monitors, check trouble codes, and fill the health tests table.
4. Click **Start Live Polling** to start real-time telemetry streaming.

---

## 🏗️ Module Architecture

- **`tribute_obd_suite.py`**: Monolithic, highly responsive single-file architecture utilizing `tkinter` and `ttk` with clam theme dark-mode customization.
- **Thread Safety:** All serial communication with `obd.OBD` and low-level ELM interfaces is protected by a central `threading.Lock()`.
- **Decoupled UI Queue:** Worker threads communicate with the GUI via a thread-safe `queue.Queue()`, preventing GUI freezes during serial latency.

---

## ⚠️ Common Mazda Tribute Pitfalls & Tips

- **Protocol Selection:** A 2002 Mazda Tribute utilizes Ford's **SAE J1850 PWM** protocol (**Protocol 1** in ELM327). Selecting Protocol 2 (SAE J1850 VPW) will fail because VPW is GM's protocol.
- **Port PermissionError:** If you see `PermissionError: Access is denied` on `COM5`, Windows is attempting to open the Bluetooth *Incoming* port. Always ensure you connect to the *Outgoing* port (`COM6`), which this software does automatically.
- **Rear Bank 1 Access:** To change spark plugs or ignition coils on Cylinders 1, 2, or 3, the upper aluminum intake plenum must be unbolted. Always replace the 6 upper intake manifold gaskets (green o-rings) whenever the plenum is lifted.

---

## ⚖️ Terms, Conditions & Legal Disclaimer

> [!IMPORTANT]
> **COMPLETE DISCLAIMER OF LIABILITY & ZERO-WARRANTY NOTICE**
> 
> 1. **AS-IS Software:** This diagnostic software is provided on an *"AS-IS"* and *"AS-AVAILABLE"* basis for educational, personal, and hobbyist diagnostic assistance only.
> 2. **NO Vehicle Damage Coverage:** The author, developer, and distributor assume **ABSOLUTELY NO RESPONSIBILITY OR LIABILITY WHATSOEVER** for any vehicle damage, mechanical breakdown, transmission failure, engine failure, electrical shorts, blown fuses, fried modules/ECUs/PCMs, battery drain, voided vehicle warranties, fines, or repair costs of any kind resulting from the use of this tool, diagnostic procedures, live polling, active tests, clearing fault codes, or interpretation of data.
> 3. **User Operates at 100% Sole Risk:** Connecting hardware to an automotive serial bus carries inherent electrical and operational risks. You agree that you operate this software and hardware entirely at your own exclusive risk.
> 4. **Not Professional Mechanical Advice:** Diagnostic results and wizard guides are generated algorithmically and do not replace certified professional mechanical advice. Always confirm vehicle issues with a qualified ASE-certified technician.
> 5. **Road Safety:** NEVER operate or monitor this software while driving on public roads. Always operate safely with the vehicle parked and emergency brake set.

---

## 👥 Authors & Credits

- **Zak Millikin (M_A.P.)** — Concept, vehicle domain expertise, system testing, and project direction.
- **Anti-Gravity (Gemini 3.8 Flash Medium)** — Advanced AI pairing, automated health rules, architecture, and diagnostics engineering.
