# Portable Wireless Attendance System with Fingerprint & OLED Display

This project implements a portable wireless attendance system using ESP32 Node MCU, HLK-FPM383C fingerprint sensor, and SSD1306 OLED display.

## Hardware Requirements

### Components
- ESP32 Development Board
- HLK-FPM383C Fingerprint Sensor
- SSD1306 OLED Display (128x64)
- USB Power Supply

### Wiring Diagram

#### Fingerprint Sensor (HLK-FPM383C)
```
Sensor RX  → ESP32 GPIO 17 (TXD2)
Sensor TX  → ESP32 GPIO 16 (RXD2)
Sensor GND → ESP32 GND
Sensor VCC → ESP32 3.3V
```

#### OLED Display (SSD1306)
```
SDA (Data) → ESP32 GPIO 21
SCL (Clock)→ ESP32 GPIO 22
GND        → ESP32 GND
VCC        → ESP32 3.3V
```

## Software Setup

### Installation Steps

1. **Install Dependencies**
   ```bash
   pip install flask requests pywebview
   ```

2. **Build and Upload Firmware**
   ```bash
   cd src
   pio run --target upload
   ```

3. **Monitor Serial Output**
   ```bash
   pio run --target upload --target monitor
   ```

## System Usage

### Step 1: Connect to WiFi
1. Find WiFi SSID: **"Vaswani_2.4"**
2. Password: **"*******"**
3. Connect from your computer

### Step 2: Start Teacher Application
```bash
python teacher_app.py
```
The desktop application will open (connects to 192.168.0.102)

### Step 3: Add Class
1. Click "Add Class" button
2. Enter class name (e.g., "Physics 101")
3. Save

### Step 4: Add Students
1. Click "Add Student"
2. Enter student name and unique ID
3. Save (students are global, not tied to specific class)

### Step 5: Register Fingerprint
1. Select student from list
2. Click "Register" button
3. **OLED shows:** "Register Mode"
4. **Place finger on sensor twice** (2 sec each, 1 sec apart)
5. **OLED shows:** "✓ Registered" or "✗ Register Failed"
6. App confirms with success/error message

### Step 6: Start Attendance Session
1. Select a class from sidebar
2. Click "Start Attendance" button
3. **OLED shows:** "Attendance Mode ON"
4. System continuously scans for fingerprints

### Step 7: Record Attendance
1. **Place registered finger on sensor**
2. Hold for 1-2 seconds
3. **OLED shows:** "✓ ID: [number]"
4. **App updates:** Attendance recorded with timestamp

### Step 8: Stop Attendance
1. Click "Stop Attendance" button
2. **OLED shows:** "Attendance Mode OFF"
3. Sensor stops scanning

### Step 9: Export Data
1. Click "Export CSV" button
2. Save file with attendance records
3. CSV contains: ID, Time

## OLED Display Messages

| Message | When | Meaning |
|---------|------|---------|
| `System Ready` | Startup complete | Waiting for command |
| `Register Mode` | Registration starting | Awaiting fingerprint enrollment |
| `✓ Registered` | Success | Fingerprint saved (ID shown) |
| `✗ Register Failed` | Error | Registration failed, try again |
| `Attendance Mode ON` | Started | Scanning for fingerprints |
| `Attendance Mode OFF` | Stopped | Scanning disabled |
| `✓ ID: [number]` | Match found | Attendance recorded |
| `✗ No Match` | No match | Fingerprint not recognized |

## Database Schema

### Classes Table
```sql
id (INTEGER PRIMARY KEY)
name (TEXT UNIQUE)
```

### Students Table
```sql
id (INTEGER PRIMARY KEY)
name (TEXT)
```

## API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/register?id=<id>` | GET | Register fingerprint for student |
| `/start_attendance` | GET | Enable fingerprint scanning |
| `/stop_attendance` | GET | Disable fingerprint scanning |
| `/get_attendance` | GET | Retrieve attendance data (JSON) |
| `/clear_attendance` | GET | Clear attendance records |
| `/delete?id=<id>` | GET | Remove registered fingerprint |

## Troubleshooting

### OLED Not Displaying
- Check I2C wiring (SDA→GPIO21, SCL→GPIO22)
- Verify I2C address: 0x3C (could be 0x3D)
- Check 3.3V power to OLED

### Fingerprint Sensor Issues
- Verify UART wiring (RX→GPIO17, TX→GPIO16)
- Check baud rate: 57600
- Ensure 3.3V power supply
- Clean sensor surface

### Registration Fails
- Ensure finger is clean and dry
- Place finger firmly on sensor
- Try different finger or angle
- Check sensor power supply

### App Cannot Connect
- Verify ESP32 WiFi is active
- Ensure computer on "Vaswani_2.4" network
- Try: `ping 192.168.0.102`
- Restart ESP32 and retry

## Advanced Configuration

### Change WiFi Settings
Edit `src/main.cpp`:
```cpp
const char* WIFI_SSID = "Vaswani_2.4";
const char* WIFI_PASSWORD = "*******";
IPAddress localIP(192, 168, 137, 123);
```

### Change I2C Address (if needed)
Edit `src/main.cpp`:
```cpp
display.begin(SSD1306_SWITCHCAPVCC, 0x3D);  // Change 0x3C to 0x3D
```

## File Structure

```
GWASOAT/
├── src/
│   └── main.cpp           # ESP32 firmware
├── include/
│   └── README
├── lib/
│   └── README
├── templates/
│   └── index.html         # Web UI
├── teacher_app.py         # Desktop application
├── attendance.db          # SQLite database (auto-created)
├── platformio.ini         # PlatformIO config
├── README.md              # This file
└── SETUP_GUIDE.md         # Detailed setup instructions
```

## Libraries Used

### Arduino/ESP32
- Wire (I2C)
- HardwareSerial (UART)
- Adafruit_SSD1306 (OLED Display)
- Adafruit_GFX (Graphics)
- ESPAsyncWebServer (WiFi Server)
- ArduinoJson (JSON handling)

### Python
- Flask (Web framework)
- Requests (HTTP client)
- pywebview (Desktop window)
- sqlite3 (Database)

## Performance Notes

- Fingerprint enrollment: ~5 seconds per registration
- Fingerprint matching: ~1 second per scan
- Attendance update: ~500ms from scan to display
- OLED refresh: ~100ms
- WiFi latency: Minimal (local network)

## Security Notes

- Default WiFi password: "*******" (change in production)
- No authentication on ESP32 endpoints (add in production)
- Attendance data stored locally (encrypt in production)
- Fingerprint templates stored on sensor (secure)