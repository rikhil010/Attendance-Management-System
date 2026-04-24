# ESP32 Fingerprint Attendance System - Complete Setup Guide

## Hardware Connections

### 1. Fingerprint Sensor (HLK-FPM383C)
- **RX (Sensor)** → GPIO 17 (TXD2)
- **TX (Sensor)** → GPIO 16 (RXD2)
- **GND** → GND
- **VCC** → 3.3V or 5V (check sensor specs, typically 3.3V)

### 2. OLED Display (SSD1306 128x64)
- **SDA (Data)** → GPIO 21
- **SCL (Clock)** → GPIO 22
- **GND** → GND
- **VCC** → 3.3V

### 3. Power
- Connect USB-C cable to ESP32 for power and programming
- Ensure proper power supply for sensors (3.3V or 5V as needed)

---

## Software Setup

### Step 1: Update PlatformIO Dependencies
The `platformio.ini` already includes required libraries:
- ESPAsyncWebServer
- ArduinoJson
- Adafruit SSD1306 (for OLED)
- Adafruit GFX (for graphics)

### Step 2: Build and Upload Firmware
1. Open terminal in the project directory
2. Run: `pio run --target upload`
3. Wait for compilation and upload to complete
4. Monitor output: `pio run --target upload --target monitor`

### Step 3: Verify Hardware Connection
After upload, open Serial Monitor (115200 baud):
- Should see: `=== Fingerprint Attendance System READY ===`
- OLED should display the system status

---

## Using the System

### Step 1: Connect to WiFi
1. On your computer, find WiFi network: **"Vaswani_2.4"**
2. Password: **"*******"**
3. Connect to it

### Step 2: Start Teacher App
1. Run: `python teacher_app.py`
2. Desktop app window opens
3. Current IP: `192.168.0.102`

### Step 3: Add Class
1. In app sidebar, click "Add Class"
2. Enter class name (e.g., "Physics 101")
3. Save

### Step 4: Add Students
1. Click "Add Student"
2. Enter **Student Name** and **Student ID** (must be unique)
3. Example: Name="Alice", ID=1
4. Click Save

### Step 5: Register Fingerprint
1. Select a student from the list
2. Click the "Register" button
3. **On OLED**: You'll see "Register Mode" message
4. **Place your finger on the sensor twice** (about 2 seconds each, with 1 second gap)
5. Wait for confirmation
6. **On OLED**: 
   - If successful: "✓ Registered" (ID shown)
   - If failed: "✗ Register Failed"
7. On app: Success message appears

### Step 6: Start Attendance Session
1. Select a **Class** from the left panel
2. Click **"Start Attendance"** button
3. **On OLED**: "Attendance Mode ON"
4. System continuously scans for fingerprints

### Step 7: Mark Attendance
1. **Place a registered finger on the sensor**
2. Hold for 1-2 seconds
3. **On OLED**: "✓ ID: [number]" appears briefly
4. **In app**: Attendance recorded in the attendance list
5. Time stamp is automatically recorded

### Step 8: Stop Attendance
1. Click **"Stop Attendance"** button
2. **On OLED**: "Attendance Mode OFF"
3. System stops scanning

### Step 9: Export Results
1. Click **"Export CSV"** button
2. Choose save location
3. CSV file contains: ID, Time

---

## OLED Display Messages

| Message | Meaning |
|---------|---------|
| `System Ready` | Startup complete, waiting for commands |
| `Register Mode` | Awaiting fingerprint registration |
| `✓ Registered` | Fingerprint successfully saved |
| `✗ Register Failed` | Registration error (duplicate or sensor issue) |
| `Attendance Mode ON` | Scanning for fingerprints |
| `Attendance Mode OFF` | Scanning stopped |
| `✓ ID: 1` | Fingerprint matched (attendance recorded) |
| `✗ No Match` | Fingerprint not recognized |
| `Error: Sensor` | Sensor communication error |

---

## Troubleshooting

### OLED Not Displaying
- Check I2C connections (SDA to GPIO 21, SCL to GPIO 22)
- Verify I2C address (default: 0x3C)
- Check power supply to OLED (3.3V)

### Fingerprint Sensor Not Responding
- Verify UART connections (RX→GPIO17, TX→GPIO16)
- Check baud rate (57600)
- Ensure 3.3V power supply

### Registration Fails
- Ensure finger is clean and dry
- Place finger firmly on sensor
- Try different fingers or angles
- Check sensor is powered correctly

### WiFi Connection Fails
- Ensure ESP32 WiFi is enabled
- Check if "Vaswani_2.4" SSID is visible
- Try password: "*******" (case-sensitive)

### App Cannot Connect to ESP32
- Verify both devices on same WiFi network
- Ping ESP32: `ping 192.168.0.102`
- Restart ESP32 and try again

---

## Advanced Configuration

### WiFi Settings (in main.cpp)
```cpp
const char* WIFI_SSID = "Vaswani_2.4";
const char* WIFI_PASSWORD = "*******";
IPAddress localIP(192, 168, 0, 102);
```

### I2C Address for OLED
```cpp
display.begin(SSD1306_SWITCHCAPVCC, 0x3C);
```
Change `0x3C` if your OLED uses different address (typically 0x3D)

### Serial Baud Rate
Fingerprint sensor: 57600 baud (fixed)

---

## Testing Checklist

- [ ] ESP32 powers on and runs
- [ ] OLED displays "System Ready"
- [ ] Computer connects to "Vaswani_2.4" WiFi
- [ ] Teacher app launches and connects successfully
- [ ] Can add classes and students
- [ ] Can register a fingerprint (OLED shows ✓ Registered)
- [ ] Can start attendance and see "Attendance Mode ON"
- [ ] Can mark attendance with registered finger
- [ ] Can export CSV with attendance data
- [ ] Can stop attendance and see "Attendance Mode OFF"