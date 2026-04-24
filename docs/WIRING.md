# Hardware Wiring Guide

## ESP32 Board Layout

```
                [USB]
                 ||
        ┌─────────┴─────────┐
        │                   │
    [3V3]                [GND]
    [5V]                 [GND]
   [GND]─────────────────────  [23 SCL/GPIO22] ← OLED Clock
   [GND]     [TX0 GPIO1]      [19]
   [GND]     [RX0 GPIO3]      [18]
   [GND]     [GPIO22/SCL]     [5]
   [GND]     [GPIO21/SDA]     [17 RXD2] ← Fingerprint RX
   [GND]     [GPIO34]         [16 TXD2] ← Fingerprint TX
   [GND]     [GPIO35]         [4]
   [GND]     [GPIO32]         [2]
   [GND]     [GPIO33]         [15]
            [GPIO25]         [14]
            [GPIO26]         [27]
            [GPIO27]         [26]
            [GPIO14]         [25]
        └─────────┬─────────┘
           [GND] [+5V]
```

## Fingerprint Sensor - ESP32 Connection

```
HLK-FPM383C Sensor          ESP32 Board
│                           │
├─ VCC (Red)      ──────→   3.3V
├─ TX (Green)     ──────→   GPIO 17 (RXD2)
├─ RX (Blue)      ──────→   GPIO 16 (TXD2)
└─ GND (Black)    ──────→   GND
```

**Connector Details:**
- VCC: 3.3V or 5V (use 3.3V for ESP32)
- TX: Serial Data Out (connect to GPIO 17)
- RX: Serial Data In (connect to GPIO 16)
- GND: Ground

## OLED Display - ESP32 Connection

```
SSD1306 OLED                ESP32 Board
│                           │
├─ VCC (Red)      ──────→   3.3V
├─ GND (Black)    ──────→   GND
├─ SDA (Green)    ──────→   GPIO 21
└─ SCL (Yellow)   ──────→   GPIO 22
```

**Display Details:**
- Resolution: 128x64 pixels
- I2C Address: 0x3C (or 0x3D)
- Color: Typically blue or yellow-green
- Operating voltage: 3.3V

## Complete System Wiring

```
                    [USB Power Cable]
                            │
                      ┌─────┴─────┐
                      │   ESP32   │
                      │  Dev Board│
                      └─────┬─────┘
                            │
            ┌───────────────┼───────────────┐
            │               │               │
       [GND]          [3V3/5V]        [GPIO Pins]
            │               │               │
            │               │      ┌────┬──┴──┬──────┐
            │               │      │    │     │      │
            ▼               ▼      │    │     │      │
       ┌─────────┐     ┌──────┐   │    │     │      │
       │         │     │      │   │    │     │      │
      GND    Fingerprint  Sensor  │ OLED    GPIO17  GPIO16
             │      │   │    │    ▼  Display │       │
             │      │   │    │    │    │     │       │
             │   VCC│   │    │   VCC  │     │       │
             │      │   │    │    │    │     │       │
        Sensor   3.3V  TX   RX   3.3V SDA  GPIO21 GPIO22/SCL
      Ground           │    │         (GND)   │      
       (Black)         │    │                 │      
                       │    │                 │      
                      GND  GND               GND
```

## Pinout Reference Table

### I2C Pins (OLED)
| Signal | ESP32 Pin | Wire Color | OLED Pin |
|--------|-----------|-----------|----------|
| SDA    | GPIO 21   | Green     | SDA      |
| SCL    | GPIO 22   | Yellow    | SCL      |
| GND    | GND       | Black     | GND      |
| VCC    | 3.3V      | Red       | VCC      |

### UART Pins (Fingerprint)
| Signal | ESP32 Pin | Wire Color | Sensor Pin |
|--------|-----------|-----------|------------|
| TXD2   | GPIO 16   | Blue      | RX         |
| RXD2   | GPIO 17   | Green     | TX         |
| GND    | GND       | Black     | GND        |
| VCC    | 3.3V      | Red       | VCC        |

## Power Supply Requirements

### Individual Components:
- **ESP32**: 500mA @ 5V (USB) or 3.3V
- **Fingerprint Sensor**: 100-150mA @ 3.3V
- **OLED Display**: 10-20mA @ 3.3V

### Total System:
- **Minimum**: 5V / 500mA USB supply
- **Recommended**: 5V / 1A or higher

### Power Distribution:
```
USB 5V ──┐
         ├─→ [5V to 3.3V Regulator] ──→ ESP32 3.3V Pin
         │
         └─→ +5V Rail
                │
                ├─→ Fingerprint VCC (if 5V capable)
                └─→ OLED VCC (3.3V requires separate regulator)
```

## Voltage Protection

Since the OLED and Fingerprint sensor are 3.3V devices:
- **Direct USB 5V**: Do NOT connect to sensor/OLED
- **Use ESP32 3.3V output**: Max 1A total
- **Optional**: Add external 3.3V regulator for better stability

## Testing Connections

### Check Fingerprint Sensor Wiring:
```cpp
Serial output should show:
"=== Fingerprint Attendance System READY ==="
If not, check RX/TX on GPIO 16/17
```

### Check OLED Wiring:
```cpp
OLED should display "System Ready"
If blank:
  - Check SDA/SCL on GPIO 21/22
  - Try different I2C address (0x3D instead of 0x3C)
```

## Troubleshooting Wiring Issues

**OLED not displaying:**
1. Check power (3.3V on VCC)
2. Check I2C address (0x3C vs 0x3D)
3. Try swapping SDA/SCL
4. Check for loose connections

**Fingerprint not responding:**
1. Check serial baud rate (57600)
2. Try swapping TX/RX
3. Verify 3.3V power
4. Check for short circuits

**System resets on sensor use:**
- Power supply too weak
- Missing GND connection
- Bad USB cable