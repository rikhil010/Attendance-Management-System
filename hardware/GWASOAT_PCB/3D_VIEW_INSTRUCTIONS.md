# GWASOAT PCB — 3D Model Viewing Options

## Option 1: KiCad 3D Viewer (Recommended)

The fastest way to see your board in 3D:

1. Open `GWASOAT_PCB.kicad_pcb` in KiCad PCB Editor
2. Press **Alt+3** or go to **View → 3D Viewer**
3. KiCad will auto-render the board with:
   - Green solder mask (both sides)
   - Copper traces visible through mask
   - Component 3D models from KiCad's library
   - Board edge cuts and mounting holes

KiCad's built-in library already has 3D models for:
- ESP32-WROOM-32E (`RF_Module:ESP32-WROOM-32E`)
- SOT-223 package (AMS1117)
- 0805 resistors/capacitors
- Electrolytic capacitors (radial 5mm)
- 6×6mm tactile switches
- Pin headers (all sizes)

---

## Option 2: OpenSCAD (Standalone 3D Model)

For a standalone parametric 3D model you can rotate, export, and 3D print:

1. Download OpenSCAD: https://openscad.org/downloads.html
2. Open `GWASOAT_PCB_3D.scad`
3. Press **F5** for preview (fast, wireframe)
4. Press **F6** for full render (slower, solid)
5. Export as:
   - **STL** → for 3D printing an enclosure mockup
   - **OFF** → for mesh viewers
   - **CSG** → for further CAD work

### Controls in OpenSCAD:
- Left-click drag → rotate
- Right-click drag → pan
- Scroll → zoom
- View → Reset View → front/top/iso views

---

## Option 3: Online 3D Viewer (No Install)

If you don't have KiCad or OpenSCAD installed:

1. Go to https://www.viewstl.com/ 
2. Export the OpenSCAD model as STL first
3. Drag the .stl file onto the viewer

Or use KiCad's online Gerber viewer:
1. Export Gerbers from KiCad
2. Go to https://gerber-viewer.ucamco.com/
3. Upload the Gerber zip to see a 2D render with layer colors

---

## 3D Model Preview (ASCII Isometric)

```
                    ╔══════════════════════════════════════╗
                   ╱                                      ╱│
                  ╱    ┌──────┐    ┌─────────────┐      ╱ │
                 ╱     │ OLED │    │             │     ╱  │
                ╱      │ ████ │    │  ESP32      │    ╱   │
               ╱       │ ████ │    │  MODULE     │   ╱    │
              ╱        └──┬───┘    │  ┌───────┐  │  ╱     │
             ╱            │        │  │ANTENNA│  │ ╱      │
            ╱  ┌────┐     │        │  └───────┘  │╱       │
           ╱   │ SD │     │        └─────────────┘        │
          ╱    │CARD│     │                               │
         ╱     └────┘     │    ┌──┐ ┌──┐                  │
        ╱                 │    │R │ │B │  ← Buttons       │
       ╱   ║C1  ║C2      │    │S │ │O │                   │
      ╱    ║    ║    [REG]│    │T │ │OT│                   │
     ╱     ║    ║         │    └──┘ └──┘                   │
    ╱  [BAT+−]           │         ┌────────┐             │
   ╱                      │         │   FP   │             │
  ╔═══════════════════════╧═════════│ SENSOR │═════════════╣
  ║          PCB (green, 1.6mm)     │  ████  │             ║
  ║                                 └────────┘             ║
  ╚════════════════════════════════════════════════════════╝
        ◄──────────────── 80mm ────────────────►

  Height profile:
  ┌─────────────────────────────────────────────────┐
  │  OLED: ~12mm    ESP32: ~3.2mm    FP: ~11mm      │
  │  Caps: ~8mm     Buttons: ~5mm   SD: ~11mm      │
  │  PCB:  1.6mm    Headers: ~8.5mm                 │
  └─────────────────────────────────────────────────┘
  Max component height: ~12mm (OLED module on header)
  Suggested enclosure internal height: 15mm minimum
```

---

## Enclosure Considerations

Based on the 3D model dimensions:

| Parameter | Value |
|-----------|-------|
| PCB footprint | 80 × 55 mm |
| Max height (top) | ~12mm (OLED on header) |
| Max height (bottom) | ~3mm (through-hole leads) |
| Suggested box internal | 86 × 61 × 18mm |
| Mounting holes | M3, 68mm × 47mm pattern |

The tallest components are the OLED and fingerprint sensor modules sitting on their pin headers. If you want a slimmer profile, consider soldering them directly with shorter pins or using right-angle headers on the board edge.
