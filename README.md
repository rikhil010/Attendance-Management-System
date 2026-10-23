# GWASOAT — Biometric Attendance System

A fingerprint-based attendance system using ESP32, with a MySQL-backed desktop
management app, cloud sync, BLE+WiFi hybrid connectivity, and role-based access
for administrators, teachers and students.

## Architecture

```
Cloud (optional backup API)
    ↕ Templates + Attendance Records
Desktop App (Python / Flask + pywebview, MySQL database)
    ↕ WiFi (primary) or BLE (fallback)
ESP32 Device
    ├── FPM383C Fingerprint Sensor (temporary cache per class)
    ├── MicroSD Card (offline cache)
    ├── SSD1306 OLED Display
    └── LiPo Battery + TP4056 USB-C Charging
```

## Key Features

- **Fingerprint sensor as cache**: unlimited students in the database, up to 255 templates loaded per session
- **Hybrid WiFi + BLE**: automatic failover if WiFi drops
- **Offline capable**: SD card caches templates and attendance logs
- **Role-based access**: Administrator, Teacher and Student roles, driven by a `role_permissions` table
- **Student portal**: students log in to view their own courses, attendance, grades and timetable
- **Grades and reports**: per-component grades, attendance percentages and defaulter lists with CSV export
- **Cloud sync**: templates and attendance records sync to an optional cloud API
- **Custom PCB**: 85×55 mm 2-layer KiCad board with USB-C charging

---

## Getting Started

### Prerequisites

| Requirement | Notes |
|-------------|-------|
| **Python 3.10+** | 3.12 recommended. Download from [python.org](https://www.python.org/downloads/). |
| **MySQL 8.0** | Community Server. The desktop app stores all data here. |
| **PlatformIO** | Only needed to build/flash the ESP32 firmware. VS Code extension or `pip install platformio`. |
| **ESP32 device** | DOIT DevKit v1 with an FPM383C fingerprint sensor (optional for app-only testing). |

### 1. Clone the repository

```bash
git clone https://github.com/rikhil010/Attendance-Management-System.git
cd Attendance-Management-System
```

### 2. Create the MySQL database

Start MySQL, then run the schema script. It creates the `gwasoat` database, a
dedicated `gwasoat_user` account, all tables, the RBAC seed data and a default
admin login.

```bash
mysql -u root -p < dbms/attendence_databse.sql
```

Optionally load the DBMS lab demonstration objects (views, stored procedures,
functions, triggers and a cursor):

```bash
mysql -u root -p gwasoat < dbms/dbms_syllabus_demo.sql
```

> **Note:** the app connects as `gwasoat_user`. If you change the database name,
> user or password in `dbms/attendence_databse.sql`, update the matching `DB_CONFIG`
> values in `python/src/database.py` and `python/src/models.py`.

### 3. Install Python dependencies

A virtual environment is recommended.

```bash
# Windows (PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

```bash
# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4. Run the desktop application

**Windows** — double-click `start.bat`, or from a terminal:

```bash
start.bat
```

**Any platform** — run the app entry point directly:

```bash
python python/src/app.py
```

The app opens in a native window. It also serves at
<http://127.0.0.1:5000/> if you prefer a browser.

**Default admin login** (created by `dbms/attendence_databse.sql`):

- Email: `admin@gwasoat.local`
- Password: `admin123`  *(change this after first login)*

### 5. (Optional) Flash the ESP32 firmware

Connect the ESP32 over USB, then from the project root:

```bash
pio run --target upload        # build and flash
pio device monitor             # view serial output (115200 baud)
```

The default upload port is `COM3` (see `platformio.ini`); change it to match
your system if needed.

---

## Typical Workflow

1. Log in as **admin** and create departments, classes, batches, courses and teachers.
2. As a **teacher**, open a course and add/import students.
3. **Register fingerprints** for each student (enrols the template on the device).
4. **Start an attendance session** — the enrolled templates load onto the ESP32.
5. Students **scan their fingers**; matches are marked Present in real time.
6. **Stop the session**, then view the report or **export CSV**.
7. **Students** log in to see their own attendance, grades and timetable.

---

## Project Structure

```
Attendance-Management-System/
├── src/main.cpp              # ESP32 firmware (BLE + WiFi + SD + fingerprint)
├── include/                  # Firmware headers (pins, display, drivers)
├── python/src/               # Desktop application (Flask back end)
│   ├── app.py                # Entry point (Flask + pywebview)
│   ├── models.py             # MySQL schema, RBAC, audit
│   ├── auth.py               # Authentication + role/permission decorators
│   ├── routes_new.py         # Pages, courses, attendance, admin CRUD
│   ├── routes_features.py    # Reports, grades, timetable, profile, import
│   ├── routes_student.py     # Student self-service portal
│   ├── api.py                # Legacy single-class API + ESP32 bridge
│   ├── connection.py         # Hybrid WiFi + BLE connection manager
│   ├── cloud_sync.py         # Optional cloud template/attendance sync
│   └── config.py             # Local settings (SQLite)
├── web/                      # Front end (Bootstrap 5 + jQuery), served by Flask
├── hardware/GWASOAT_PCB/     # KiCad 2-layer PCB design
├── docs/                     # Diagrams (ER, architecture) + report images
├── documents/                # Project reports (.docx / .md) + generate_report.py
├── dbms/                     # All SQL: schema, DBMS features, syllabus demo, queries
│   ├── attendence_databse.sql    # MySQL schema + seed data (run first)
│   ├── 002_dbms_features.sql     # View, grade triggers, start_session procedure
│   ├── dbms_syllabus_demo.sql    # Views, procedures, functions, triggers, cursor
│   └── demo_queries.sql          # Sample CALL / SELECT queries
├── requirements.txt          # Python dependencies
├── platformio.ini            # PlatformIO build config
└── start.bat                 # Desktop app launcher (Windows)
```

## Hardware Wiring (breadboard)

| ESP32 Pin | Component |
|-----------|-----------|
| 3V3 | VCC for OLED, SD, FP sensor |
| GND | GND for all modules |
| GPIO21 | OLED SDA |
| GPIO22 | OLED SCL |
| GPIO12 | SD Card MISO |
| GPIO13 | SD Card MOSI |
| GPIO14 | SD Card SCK |
| GPIO5  | SD Card CS |
| GPIO16 | Fingerprint TX |
| GPIO17 | Fingerprint RX |

## Troubleshooting

- **`No module named 'mysql'`** — run `pip install -r requirements.txt`; the MySQL driver is required.
- **`Access denied for user 'gwasoat_user'`** — the schema script did not run, or the credentials in `database.py` / `models.py` do not match `dbms/attendence_databse.sql`.
- **App window is blank** — make sure nothing else is using port 5000, then restart.
- **ESP32 not found** — confirm the device and laptop are on the same WiFi, or set the device IP in the app's network settings. BLE fallback requires `bleak` installed.

## Documentation

See the `docs/` folder for the configuration guide, wiring, ER diagram and the
DBMS project report (`DBMS_PROJECT_REPORT.md`,
`GWASOAT_DBMS_Mini_Project_Report.docx`).
