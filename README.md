# GWASOAT — Biometric Attendance System

A fingerprint-based attendance system using ESP32, with cloud sync, BLE+WiFi hybrid connectivity, and a desktop management app.

## Architecture

```
Cloud (Firebase/AWS/Custom)
    ↕ Templates + Attendance Records
Desktop App (Python/Flask)
    ↕ WiFi (primary) or BLE (fallback)
ESP32 Device
    ├── FPM383C Fingerprint Sensor (temporary cache per class)
    ├── MicroSD Card (offline cache)
    ├── SSD1306 OLED Display
    └── LiPo Battery + TP4056 USB-C Charging
```

## Project Structure

```
GWASOAT/
├── src/main.cpp          # ESP32 firmware (BLE + WiFi + SD + fingerprint)
├── include/              # Firmware headers
│   ├── pins.h            # GPIO pin definitions
│   ├── fingerprint.h     # FPM383C sensor driver
│   ├── sd_cache.h        # MicroSD template storage
│   ├── ble_service.h     # NimBLE GATT service
│   └── config.h          # WiFi/SPIFFS config manager
├── python/src/           # Desktop application
│   ├── app.py            # Entry point (Flask + pywebview)
│   ├── api.py            # REST API routes
│   ├── connection.py     # Hybrid WiFi+BLE connection manager
│   ├── cloud_sync.py     # Cloud template/attendance sync
│   ├── registration.py   # Fingerprint enrollment + class loading
│   ├── attendance.py     # Attendance tracking
│   ├── database.py       # SQLite operations
│   ├── network.py        # ESP32 HTTP communication
│   └── config.py         # App configuration
├── web/templates/        # Web UI (Bootstrap 5)
├── hardware/GWASOAT_PCB/ # KiCad 2-layer PCB design
├── data/                 # Runtime data (attendance.db)
├── docs/                 # Documentation
├── platformio.ini        # PlatformIO build config
└── start.bat             # Desktop app launcher
```

## Quick Start

### 1. Upload firmware
```bash
pio run --target upload
```

### 2. Run desktop app
```bash
cd python/src
pip install flask pywebview requests bleak
python app.py
```

### 3. Workflow
1. Add class → Add students → Register fingerprints
2. Start attendance → Students scan fingers → Export CSV

## Key Features

- **Fingerprint sensor as cache**: Unlimited students (cloud storage), 255 loaded per session
- **Hybrid WiFi+BLE**: Auto-failover if WiFi drops
- **Offline capable**: SD card caches templates + attendance logs
- **Cloud sync**: Templates and attendance records sync when online
- **Custom PCB**: 85×55mm 2-layer board with USB-C charging

## Hardware (Breadboard Wiring)

| ESP32 Pin | Component |
|-----------|-----------|
| 3V3 | VCC for OLED, SD, FP Sensor |
| GND | GND for all modules |
| GPIO21 | OLED SDA |
| GPIO22 | OLED SCL |
| GPIO12 | SD Card MISO |
| GPIO13 | SD Card MOSI |
| GPIO14 | SD Card SCK |
| GPIO5 | SD Card CS |
| GPIO16 | Fingerprint TX |
| GPIO17 | Fingerprint RX |

## Dependencies

**Firmware**: ESP32Async, ArduinoJson, Adafruit SSD1306/GFX, NimBLE-Arduino, SD  
**Python**: Flask, pywebview, requests, bleak (optional for BLE)
