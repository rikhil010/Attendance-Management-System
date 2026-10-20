#ifndef PINS_H
#define PINS_H

/**
 * GWASOAT PCB v2.0 — Final Pin Definitions
 * ESP32-WROOM-32, ILI9341 2.8" TFT (MSP2807), HLK-FPM383C, microSD
 *
 * Power:
 *   Battery → TP4056 (bare IC) → AP2112K-3.3 → 3V3
 *   AO3401 P-MOSFET switches 3V3_SW to TFT + fingerprint
 */

// ─── TFT Display (ILI9341 2.8", SPI / VSPI) ─────────────────
// TFT_eSPI pins configured via build_flags in platformio.ini
#define PIN_TFT_MOSI        23      // D23 → TFT SDI(MOSI)
#define PIN_TFT_SCLK        18      // D18 → TFT SCK
#define PIN_TFT_CS           5      // D5  → TFT CS
#define PIN_TFT_DC           2      // D2  → TFT DC
#define PIN_TFT_RST         26      // D26 → TFT RESET
#define PIN_TFT_BL          15      // D15 → TFT backlight (LED)
// SDO(MISO) left unconnected — display is write-only

// ─── SD Card (dedicated HSPI-capable bus) ────────────────────
#define PIN_SD_CS           27      // D27 → SD CS
#define PIN_SD_MOSI         13      // D13 → SD MOSI
#define PIN_SD_SCK          25      // D25 → SD SCK
#define PIN_SD_MISO         22      // D22 → SD MISO

// ─── Fingerprint Sensor (HLK-FPM383C, UART2) ─────────────────
#define PIN_FP_RX           16      // D16 (RX2) ← Sensor TX
#define PIN_FP_TX           17      // D17 (TX2) → Sensor RX
#define PIN_FP_WAKE         14      // D14 → Sensor WAKE/IRQ
#define FP_BAUD_RATE        57600

// ─── Power control ────────────────────────────────────────────
#define PIN_REG_EN           4      // D4  → AP2112K EN (soft-latch hold)
#define PIN_PERIPH_EN       12      // D12 → AO3401 gate (3V3_SW switch)

// ─── Battery ADC ──────────────────────────────────────────────
#define PIN_VBAT_ADC        35      // D35 → 47k/47k divider from VBAT_SYS

#endif
