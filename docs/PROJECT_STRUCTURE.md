# GWASOAT - Reorganized Project Structure

Welcome to the newly reorganized GWASOAT attendance system. This guide explains the new file structure and how to use it.

## 📁 New Project Structure

```
GWASOAT/
├── app.py                  # Main application entry point
├── config.py              # Configuration management
├── network.py             # ESP32 communication
├── database.py            # Database operations
├── attendance.py          # Attendance tracking
├── registration.py        # Student registration
├── api.py                 # Flask API routes
├── teacher_app.py         # OLD - Still present for reference
├── platformio.ini         # PlatformIO configuration
├── config.json            # Runtime configuration
├── attendance.db          # SQLite database
├── classes.json           # Class data
├── templates/             # Web UI templates
├── docs/                  # Documentation files
│   ├── CONFIGURATION.md
│   ├── IMPLEMENTATION_SUMMARY.md
│   ├── CHANGELOG.md
│   ├── DELIVERY_SUMMARY.md
│   ├── DOCUMENTATION_GUIDE.md
│   ├── INDEX.md
│   ├── QUICKSTART_CONFIG.md
│   └── guides/
├── src/                   # C++ firmware source
│   └── main.cpp
├── include/               # C++ headers
│   ├── config.h
│   └── ble_service.h
├── lib/                   # PlatformIO libraries
├── test/                  # Tests
└── README.md             # This file
```

## 🚀 Quick Start

### Run the Application

```bash
# Install dependencies (if not already installed)
pip install flask requests pywebview

# Run the application
python app.py
```

The web interface will launch at `http://127.0.0.1:5000`

## 📚 Module Overview

### app.py (Entry Point - 50 lines)
Main application launcher. Initializes Flask and GUI.

**Usage:**
```python
python app.py
```

### config.py (Configuration - 130 lines)
Centralized configuration management for Wi-Fi, IP, and other settings.

**Usage:**
```python
from config import get_config

cfg = get_config()
ip = cfg.get("esp32_ip")
cfg.set("wifi_ssid", "MyNetwork")
```

### network.py (Network Operations - 120 lines)
Handles all ESP32 communication, host discovery, and network utilities.

**Key Functions:**
- `esp32_request(path, params, timeout)` - Make HTTP request to ESP32
- `discover_esp32_host()` - Auto-discover ESP32 on network
- `get_local_ipv4()` - Get machine's IPv4 address
- `probe_esp32_host(host, timeout)` - Test a single host

**Usage:**
```python
from network import esp32_request, discover_esp32_host

response, host, err = esp32_request('/status')
found = discover_esp32_host()
```

### database.py (Database Operations - 200 lines)
Database initialization, schema management, and CRUD operations.

**Key Functions:**
- `get_db()` - Get database connection
- `initialize_database()` - Create tables
- `get_classes()` / `add_class()` / `update_class()` / `delete_class()`
- `get_students()` / `add_student()` / `update_student()` / `delete_student()`

**Usage:**
```python
from database import initialize_database, get_classes, add_student

initialize_database()
classes = get_classes()
add_student(1, "John Doe", 1)
```

### attendance.py (Attendance Tracking - 240 lines)
Attendance marking, synchronization, and reporting.

**Key Functions:**
- `mark_student_present()` - Mark student as present
- `sync_attendance_from_esp32()` - Sync with device
- `get_attendance_summary()` - Get attendance report
- `list_sessions_for_class()` - List all sessions
- `delete_session()` - Remove session

**Usage:**
```python
from attendance import mark_student_present, get_attendance_summary

mark_student_present(123, "John Doe", class_id=1, session_id=1)
summary = get_attendance_summary(1, 1)
```

### registration.py (Student Registration - 210 lines)
Handles student registration workflow and session management.

**Key Functions:**
- `start_attendance_session()` - Start new attendance session
- `stop_attendance_session()` - End attendance session
- `_resolve_active_session()` - Get current session
- `set_register_job()` / `get_register_job_snapshot()` - Track registration

**Usage:**
```python
from registration import start_attendance_session, stop_attendance_session

result = start_attendance_session(class_id=1)
stop_result = stop_attendance_session()
```

### api.py (Flask API Routes - 380 lines)
All HTTP endpoints and request handlers.

**Key Routes:**
- `GET /api/network` - Get network settings
- `POST /api/network` - Update network settings
- `GET /api/classes` - List classes
- `POST /api/classes` - Create class
- `GET /api/students` - List students
- `POST /api/students` - Add student
- `GET /api/attendance` - Get attendance
- `GET /api/start_attendance` - Start session
- `GET /api/stop_attendance` - End session
- `GET /api/export_csv` - Export as CSV

**Usage:**
```bash
curl http://localhost:5000/api/classes
curl -X POST http://localhost:5000/api/network -d "esp32_ip=192.168.0.150"
```

## 🔧 Configuration

### Via Python
```python
from config import get_config

cfg = get_config()

# Get configuration
ip = cfg.get("esp32_ip")
hosts = cfg.get_esp32_hosts()

# Set configuration
cfg.set("wifi_ssid", "MyNetwork")
cfg.set("wifi_password", "MyPassword")
cfg.setWiFiCredentials("SSID", "Password")
```

### Via REST API
```bash
# Get settings
curl http://localhost:5000/api/network

# Update settings
curl -X POST http://localhost:5000/api/network \
  -d "esp32_ip=192.168.0.150" \
  -d "esp32_use_mdns=1"

# Auto-discover
curl http://localhost:5000/api/network/discover
```

## 📖 Documentation

See the `docs/` folder for detailed documentation:

- **QUICKSTART_CONFIG.md** - Get started quickly
- **CONFIGURATION.md** - Complete configuration guide
- **IMPLEMENTATION_SUMMARY.md** - Technical details
- **API_REFERENCE.md** - Full API documentation (in docs/)
- **CHANGELOG.md** - Version history

Start with `DOCUMENTATION_GUIDE.md` for navigation.

## 🧪 Testing

### Test Database Operations
```python
from database import initialize_database, get_classes, add_class

initialize_database()
add_class("Class A")
classes = get_classes()
print(classes)
```

### Test Network Operations
```python
from network import discover_esp32_host

found = discover_esp32_host()
if found:
    print(f"Found ESP32 at {found['host']}")
```

### Test Attendance
```python
from attendance import get_attendance_summary

summary = get_attendance_summary(class_id=1, session_id=1)
print(f"Total students: {len(summary['rows'])}")
```

## 📊 Code Statistics

| Module | Lines | Purpose |
|--------|-------|---------|
| app.py | 50 | Entry point |
| config.py | 130 | Configuration |
| network.py | 120 | Networking |
| database.py | 200 | Database |
| attendance.py | 240 | Attendance |
| registration.py | 210 | Registration |
| api.py | 380 | Routes |
| **Total** | **1,330** | **All modules** |

**Average per file: 190 lines** ✅ (Well under 500-line target)

## 🔄 Migration from Old Structure

The old `teacher_app.py` still exists but is deprecated. The new modular structure provides:

✅ Better code organization
✅ Easier to find and modify features
✅ Better testability
✅ Clearer separation of concerns
✅ Easier to add new features

## 🚨 Troubleshooting

### ImportError: No module named 'config'
Make sure all Python files are in the same directory.

### Database locked error
Only one process can access the database at a time. Close other instances.

### ESP32 not found
Run `/api/network/discover` to auto-discover the device on the network.

### Module imports failing
Ensure all files (config.py, network.py, etc.) are in the root directory.

## 📝 Notes

- Database initialization happens automatically on first app load
- Configuration is persistent across restarts
- Network requests include intelligent fallback to multiple hosts
- All operations are thread-safe

## 🎯 Next Steps

1. Start the application: `python app.py`
2. Open browser to `http://127.0.0.1:5000`
3. Configure ESP32 IP in network settings
4. Create classes and add students
5. Start attendance sessions
6. Mark attendance using fingerprint scanner

---

**Version:** 2.1.0 (Reorganized)  
**Status:** Production Ready  
**Last Updated:** 2024
