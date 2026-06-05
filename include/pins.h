#ifndef PINS_H
#define PINS_H

/**
 * GWASOAT PCB v1.0 — Pin Definitions
 * Matches breadboard wiring for ESP32-WROOM-32E
 *
 * Power:
 *   3V3 → Breadboard Red Rail (+) → VCC for OLED, SD, FP Sensor
 *   GND → Breadboard Blue Rail (-) → GND for OLED, SD, FP Sensor
 */

// OLED Display (SSD1306, I2C)
#define PIN_OLED_SDA        21      // GPIO21 → OLED SDA
#define PIN_OLED_SCL        22      // GPIO22 → OLED SCK/SCL
#define OLED_I2C_ADDR       0x3C
#define OLED_WIDTH          128
#define OLED_HEIGHT         64

// Fingerprint Sensor (HLK-FPM383C, UART2)
#define PIN_FP_RX           16      // GPIO16 ← Sensor TX
#define PIN_FP_TX           17      // GPIO17 → Sensor RX
#define PIN_FP_TOUCH        4       // GPIO4 - Touch detect (optional)
#define FP_BAUD_RATE        57600

// MicroSD Card Reader (HW-125, SPI)
#define PIN_SD_MISO         12      // GPIO12 → SD MISO
#define PIN_SD_MOSI         13      // GPIO13 → SD MOSI
#define PIN_SD_SCK          14      // GPIO14 → SD SCK
#define PIN_SD_CS           5       // GPIO5  → SD CS

#endif
