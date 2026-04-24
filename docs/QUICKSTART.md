# Quick Start Guide - Attendance System

## 5-Minute Setup

### Hardware Assembly (2 minutes)

**Fingerprint Sensor wiring:**
- RX to GPIO 17
- TX to GPIO 16
- GND to GND
- VCC to 3.3V

**OLED Display wiring:**
- SDA to GPIO 21
- SCL to GPIO 22
- GND to GND
- VCC to 3.3V

**Power:**
- Connect ESP32 via USB cable

### Software Upload (2 minutes)

```bash
pio run --target upload
```

Wait for upload to complete. You should see message on OLED: "System Ready"

### Run Application (1 minute)

```bash
python teacher_app.py
```

Desktop app opens. You're ready to use!

---

## Basic Workflow

### 1. Add Class (30 seconds)
```
Click "Add Class" → Type "Class 1" → Save
```

### 2. Add Student (30 seconds)
```
Click "Add Student" → Name: "John" → ID: 1 → Save
```

### 3. Register Fingerprint (30 seconds)
```
Select "John" → Click "Register" 
→ Place finger 2x on sensor → Wait for ✓ Registered
```

### 4. Start Attendance (10 seconds)
```
Select "Class 1" → Click "Start Attendance"
→ OLED shows: "Attendance Mode ON"
```

### 5. Mark Attendance (10 seconds per student)
```
Place registered finger on sensor → OLED shows ✓ ID: 1
```

### 6. Stop & Export (20 seconds)
```
Click "Stop Attendance" → Click "Export CSV" → Save file
```

---

## Common Issues & Quick Fixes

### OLED Blank
**Check:** SDA/SCL wired to GPIO 21/22?
```cpp
// If still blank, try changing I2C address in main.cpp:
display.begin(SSD1306_SWITCHCAPVCC, 0x3D);  // instead of 0x3C
```

### Register Button Not Working
**Check:** 
- Is ESP32 powered on?
- Is computer connected to "Vaswani_2.4" WiFi?
- Try restarting ESP32

### Fingerprint Not Recognized
**Check:**
- Is finger clean and dry?
- Is sensor powered (3.3V)?
- Try registering again with different pressure

### App Can't Connect
**Check:** 
```bash
ping 192.168.0.102
```
If fails, restart ESP32

---

## Pin Configuration Reference

| Device | Pin | Function |
|--------|-----|----------|
| Fingerprint TX | GPIO 16 | UART RX |
| Fingerprint RX | GPIO 17 | UART TX |
| OLED SDA | GPIO 21 | I2C Data |
| OLED SCL | GPIO 22 | I2C Clock |

---

## Default Credentials

| Setting | Value |
|---------|-------|
| WiFi SSID | Vaswani_2.4 |
| WiFi Password | ******* |
| ESP32 IP | 192.168.0.102 |
| OLED Address | 0x3C |
| Baud Rate | 115200 |

---

## Testing Checklist

- [ ] ESP32 boots and shows "System Ready" on OLED
- [ ] Computer connects to Vaswani_2.4 WiFi
- [ ] App launches successfully
- [ ] Can add class
- [ ] Can add student
- [ ] Can register fingerprint (✓ Registered shows)
- [ ] Can start attendance ("Attendance Mode ON" shows)
- [ ] Can place finger and see attendance recorded
- [ ] Stop attendance works
- [ ] CSV export works

If all checked, system is fully operational! ✓