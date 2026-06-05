# GWASOAT PCB Design Notes — 2-Layer Board

## Board Specifications

| Parameter | Value |
|-----------|-------|
| Dimensions | 85mm × 55mm |
| Layers | 2 (F.Cu signal/power, B.Cu ground pour) |
| Thickness | 1.6mm FR4 |
| Copper Weight | 1oz (35µm) |
| Min Track Width | 0.3mm (signal), 0.5mm (power) |
| Min Via | 0.6mm dia / 0.3mm drill |
| Mounting | 4× M3 holes at corners |

---

## Power Architecture (USB-C + TP4056 + LiPo)

```
USB-C (J5)──►[TVS D2]──► VBUS 5V ──► TP4056 Module (External)
   │                                         │
   ├── CC1 ──[R3 5.1k]── GND                │ Charges battery
   └── CC2 ──[R4 5.1k]── GND                ▼
                                        LiPo Battery (3.7V)
                                             │
                                     [Schottky D1 SS14]
                                             │
                                             ▼ VBAT
                                    ┌── C1 ──┤
                                    │        ▼
                                    │   ┌─────────┐
                                    │   │ AMS1117 │──► +3V3 Rail
                                    │   │  (U2)   │    │
                                    │   └────┬────┘    ├── C2 (output)
                                    │        │         ├── C3 (decoupling)
                                    │       GND        ├── ESP32
                                    │                  ├── OLED
                                    └──────────────────├── FP Sensor
                                                       └── SD Card
```

### Protection Components

| Component | Part | Purpose |
|-----------|------|---------|
| D1 | SS14 (SMA) | Reverse polarity + backfeed protection |
| D2 | USBLC6-2SC6 (SOT-23-6) | ESD protection on USB-C VBUS/D+/D- |
| R3 | 5.1kΩ (0805) | CC1 pull-down (USB-C 5V sink ID) |
| R4 | 5.1kΩ (0805) | CC2 pull-down (USB-C 5V sink ID) |

---

## Layer Strategy

- **Front Copper (F.Cu):** All signal traces + power distribution
- **Back Copper (B.Cu):** Solid ground pour (GND plane)
- **Vias:** Used to connect component GND pads to the back-side ground plane

This gives you excellent ground return paths and EMI shielding for the ESP32's 2.4GHz radio.

---

## Component Placement (Top Side)

```
┌─────────────────────────────────────────────────────────────────────────┐
│ [H1]                    GWASOAT v1.0                             [H2]  │
│                                                                         │
│  ┌─────────┐    ┌──────────────────────────┐    ┌──────────────────┐   │
│  │  POWER  │    │                          │    │  J3: OLED 4-pin  │   │
│  │ J1 BAT  │    │    U1: ESP32-WROOM-32E   │    │  (GND VCC SDA SCL)│  │
│  │ U2 REG  │    │                          │    └──────────────────┘   │
│  │ C1 C2   │    │    (18mm × 25.5mm)       │                           │
│  └─────────┘    │                          │    ┌──────────────────┐   │
│                  │                          │    │ J4: FP Sensor    │   │
│  ┌─────────┐    │                          │    │ 6-pin header     │   │
│  │ SD CARD │    └──────────────────────────┘    │(VCC GND TX RX    │   │
│  │ J2 slot │                                    │ TOUCH 3V3)       │   │
│  │         │     [C3]                           └──────────────────┘   │
│  └─────────┘                                                           │
│                  [R1]  [R2]                                             │
│ [H3]           [SW1] [SW2]                                      [H4]  │
│                 RST   BOOT                                             │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Schematic Netlist

### Power Section

| Net | From | To | Notes |
|-----|------|----|-------|
| VBAT | J1 pin 1 (+) | U2 (AMS1117) Vin, C1+ | 3.7V LiPo input |
| GND | J1 pin 2 (−) | U2 GND, C1−, C2−, C3−, ESP32 GND | Common ground |
| +3V3 | U2 Vout | C2+, C3+, ESP32 3V3, R1, R2, J3, J4, J2 | Regulated 3.3V |

### ESP32 Boot Circuit

| Net | From | To | Notes |
|-----|------|----|-------|
| EN | ESP32 EN pin | R1 (10kΩ to +3V3), SW1 (to GND) | Pull-up + reset button |
| IO0 | ESP32 GPIO0 | R2 (10kΩ to +3V3), SW2 (to GND) | Pull-up + boot button |

### OLED Display (I2C) — J3

| J3 Pin | Signal | ESP32 GPIO | Notes |
|--------|--------|------------|-------|
| 1 | GND | GND | Ground |
| 2 | VCC | +3V3 | Power |
| 3 | SDA | GPIO21 | I2C Data |
| 4 | SCL | GPIO22 | I2C Clock |

### Fingerprint Sensor (UART) — J4

| J4 Pin | Signal | ESP32 GPIO | Notes |
|--------|--------|------------|-------|
| 1 | VCC | +3V3 | Power (3.3V) |
| 2 | GND | GND | Ground |
| 3 | TX | GPIO16 (RX2) | Sensor TX → ESP32 RX |
| 4 | RX | GPIO17 (TX2) | ESP32 TX → Sensor RX |
| 5 | TOUCH | GPIO4 | Touch detect interrupt |
| 6 | 3V3_OUT | +3V3 | Aux power (tied to rail) |

### MicroSD Card (SPI) — J2

| J2 Pin | Signal | ESP32 GPIO | Notes |
|--------|--------|------------|-------|
| 1 | GND | GND | Ground |
| 2 | VCC | +3V3 | Power |
| 3 | MISO | GPIO19 | SPI MISO |
| 4 | MOSI | GPIO23 | SPI MOSI |
| 5 | SCK | GPIO18 | SPI Clock |
| 6 | CS | GPIO5 | Chip Select |

---

## GPIO Assignment Summary

| GPIO | Function | Direction | Notes |
|------|----------|-----------|-------|
| GPIO0 | BOOT | Input | Pull-up R2, button SW2 |
| GPIO4 | FP_TOUCH | Input | Fingerprint touch IRQ |
| GPIO5 | CS_SD | Output | MicroSD chip select |
| GPIO16 | FP_RX (UART2 RX) | Input | From fingerprint TX |
| GPIO17 | FP_TX (UART2 TX) | Output | To fingerprint RX |
| GPIO18 | SPI_SCK | Output | SD card clock |
| GPIO19 | SPI_MISO | Input | SD card data out |
| GPIO21 | I2C_SDA | Bidir | OLED data |
| GPIO22 | I2C_SCL | Output | OLED clock |
| GPIO23 | SPI_MOSI | Output | SD card data in |
| EN | RESET | Input | Pull-up R1, button SW1 |

---

## Design Rules for 2-Layer

1. **Ground plane on B.Cu** — unbroken copper pour connected to GND net
2. **Power traces 0.5mm** minimum width on F.Cu (handles ~1A)
3. **Signal traces 0.3mm** minimum width
4. **Decoupling cap C3** placed within 5mm of ESP32 VDD/GND pins
5. **Keep antenna area clear** — no copper (either layer) under ESP32 antenna overhang
6. **SD card traces** kept short and matched length where possible
7. **UART traces** (FP sensor) routed away from SPI to avoid crosstalk

---

## BOM (Bill of Materials)

| Ref | Component | Value/Part | Package | Qty |
|-----|-----------|-----------|---------|-----|
| U1 | ESP32-WROOM-32E | — | Module (18×25.5mm) | 1 |
| U2 | AMS1117-3.3 | 3.3V LDO | SOT-223 | 1 |
| D1 | Schottky Diode | SS14 (1A/40V) | SMA | 1 |
| D2 | TVS Diode Array | USBLC6-2SC6 | SOT-23-6 | 1 |
| R1 | Resistor | 10kΩ | 0805 | 1 |
| R2 | Resistor | 10kΩ | 0805 | 1 |
| R3 | Resistor | 5.1kΩ (CC1) | 0805 | 1 |
| R4 | Resistor | 5.1kΩ (CC2) | 0805 | 1 |
| C1 | Electrolytic Cap | 10µF/16V | Radial 5mm | 1 |
| C2 | Electrolytic Cap | 10µF/16V | Radial 5mm | 1 |
| C3 | Ceramic Cap | 100nF | 0805 | 1 |
| SW1 | Tactile Switch | Reset | 6×6mm | 1 |
| SW2 | Tactile Switch | Boot | 6×6mm | 1 |
| J1 | Pin Header | 2-pin battery | 2.54mm pitch | 1 |
| J2 | MicroSD Socket | SPI module | 6-pin header | 1 |
| J3 | Pin Header | 4-pin OLED | 2.54mm pitch | 1 |
| J4 | Pin Header | 6-pin FP sensor | 2.54mm pitch | 1 |
| J5 | USB-C Receptacle | 6-pin power-only | Mid-mount SMD | 1 |
| H1-H4 | Mounting Hole | M3 | 3.2mm drill | 4 |

### External Module (Not on PCB)
| Component | Part | Purpose |
|-----------|------|---------|
| TP4056 Module | Type-C version with DW01 | LiPo charging (connects between J5 and J1) |
| LiPo Battery | 3.7V 2000mAh+ | Power source |

---

## Manufacturing Notes

- **Minimum order:** Most fabs (JLCPCB, PCBWay) accept 2-layer boards at ~$2-5 for 5pcs
- **Solder mask:** Green (default) both sides
- **Silkscreen:** White, front side
- **Surface finish:** HASL (lead-free) or ENIG
- **Panelization:** Single board, no panel needed at this size

---

## Assembly Order

1. Solder U2 (AMS1117-3.3) — SOT-223 pad
2. Solder C1, C2 (electrolytics — watch polarity)
3. Solder C3 (ceramic, near ESP32 footprint)
4. Solder R1, R2 (0805 SMD)
5. Solder ESP32-WROOM-32E module (reflow or hand-solder castellated pads)
6. Solder SW1, SW2 (through-hole tactile buttons)
7. Solder J1 (battery header), J2 (SD), J3 (OLED), J4 (FP sensor)
8. Verify continuity on +3V3 and GND before powering
