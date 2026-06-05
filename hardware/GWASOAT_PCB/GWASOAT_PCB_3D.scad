// ============================================================
// GWASOAT PCB v1.0 — 3D Model (OpenSCAD)
// 80mm x 55mm, 2-Layer FR4 Board
// 
// Open this file in OpenSCAD (free: https://openscad.org)
// Press F5 to preview, F6 to render, File > Export > STL/STEP
// ============================================================

// Board dimensions
board_w = 80;
board_h = 55;
board_t = 1.6;  // FR4 thickness

// Mounting hole params
mount_hole_d = 3.2;
mount_pad_d = 6.0;
mount_inset = 4.0;

// Colors
pcb_color = [0.1, 0.5, 0.1];       // Green solder mask
copper_color = [0.8, 0.6, 0.2];    // Gold/copper
silk_color = [1, 1, 1];            // White silkscreen
black_color = [0.15, 0.15, 0.15];  // IC/module body
silver_color = [0.75, 0.75, 0.78]; // Metal pins/caps

// ============================================================
// PCB BOARD
// ============================================================
module pcb_board() {
    difference() {
        // Main board body
        color(pcb_color)
        linear_extrude(board_t)
        square([board_w, board_h]);
        
        // Mounting holes
        for (pos = [
            [mount_inset, mount_inset],
            [board_w - mount_inset, mount_inset],
            [mount_inset, board_h - mount_inset],
            [board_w - mount_inset, board_h - mount_inset]
        ]) {
            translate([pos[0], pos[1], -0.1])
            cylinder(h = board_t + 0.2, d = mount_hole_d, $fn = 32);
        }
    }
    
    // Copper pads around mounting holes
    for (pos = [
        [mount_inset, mount_inset],
        [board_w - mount_inset, mount_inset],
        [mount_inset, board_h - mount_inset],
        [board_w - mount_inset, board_h - mount_inset]
    ]) {
        color(copper_color)
        translate([pos[0], pos[1], board_t])
        difference() {
            cylinder(h = 0.035, d = mount_pad_d, $fn = 32);
            cylinder(h = 0.1, d = mount_hole_d, $fn = 32);
        }
    }
}

// ============================================================
// ESP32-WROOM-32E MODULE (18mm x 25.5mm x 3.2mm)
// ============================================================
module esp32_module() {
    // Metal shield body
    color(silver_color)
    translate([0, 0, 0])
    cube([18, 25.5, 3.2]);
    
    // Antenna section (extends beyond shield)
    color(pcb_color)
    translate([2, 25.5, 0])
    cube([14, 5.5, 0.8]);
    
    // Label on top
    color(black_color)
    translate([1, 2, 3.2])
    cube([16, 18, 0.05]);
    
    // Castellated pads (simplified as strips)
    color(copper_color)
    for (i = [0:13]) {
        // Left side pads
        translate([-0.3, 1.27 + i * 1.27, 0])
        cube([0.6, 0.8, 1.0]);
        // Right side pads
        translate([17.7, 1.27 + i * 1.27, 0])
        cube([0.6, 0.8, 1.0]);
    }
    // Bottom pads
    color(copper_color)
    for (i = [0:5]) {
        translate([2 + i * 2.5, -0.3, 0])
        cube([0.8, 0.6, 1.0]);
    }
    // GND pad underneath
    color(copper_color)
    translate([4, 5, -0.05])
    cube([10, 10, 0.05]);
}

// ============================================================
// AMS1117-3.3 REGULATOR (SOT-223)
// ============================================================
module ams1117() {
    // Body
    color(black_color)
    cube([6.5, 3.5, 1.6]);
    
    // Tab pad (large)
    color(silver_color)
    translate([1.5, 3.5, 0])
    cube([3.5, 1.5, 0.2]);
    
    // 3 pins on opposite side
    color(silver_color)
    for (i = [0:2]) {
        translate([0.8 + i * 2.3, -1.2, 0])
        cube([0.7, 1.5, 0.2]);
    }
}

// ============================================================
// ELECTROLYTIC CAPACITOR (Radial, 5mm dia)
// ============================================================
module cap_electrolytic() {
    // Body cylinder
    color([0.2, 0.2, 0.8])  // Blue
    translate([0, 0, 0.5])
    cylinder(h = 7, d = 5, $fn = 24);
    
    // Top marking
    color(silver_color)
    translate([0, 0, 7.5])
    cylinder(h = 0.1, d = 4.5, $fn = 24);
    
    // Leads
    color(silver_color)
    for (x = [-1.25, 1.25]) {
        translate([x, 0, -1.5])
        cylinder(h = 2, d = 0.5, $fn = 12);
    }
}

// ============================================================
// SMD CAPACITOR / RESISTOR (0805)
// ============================================================
module smd_0805(body_color = [0.2, 0.15, 0.1]) {
    // Body
    color(body_color)
    translate([-1.0, -0.625, 0])
    cube([2.0, 1.25, 0.6]);
    
    // End caps
    color(silver_color)
    translate([-1.1, -0.725, 0])
    cube([0.4, 1.45, 0.7]);
    color(silver_color)
    translate([0.7, -0.725, 0])
    cube([0.4, 1.45, 0.7]);
}

// ============================================================
// TACTILE PUSH BUTTON (6x6mm)
// ============================================================
module tactile_button() {
    // Base
    color(black_color)
    translate([-3, -3, 0])
    cube([6, 6, 3.5]);
    
    // Button cap
    color([0.9, 0.9, 0.9])
    translate([0, 0, 3.5])
    cylinder(h = 1.5, d = 3.5, $fn = 24);
    
    // Pins (4 legs)
    color(silver_color)
    for (pos = [[-3.25, -2.25], [-3.25, 2.25], [3.25, -2.25], [3.25, 2.25]]) {
        translate([pos[0], pos[1], -1.5])
        cube([0.8, 0.5, 2.0]);
    }
}

// ============================================================
// PIN HEADER (vertical, 2.54mm pitch)
// ============================================================
module pin_header(pins = 4) {
    // Plastic housing
    color(black_color)
    translate([-1.27, -1.27, 0])
    cube([pins * 2.54, 2.54, 2.5]);
    
    // Pins
    color(copper_color)
    for (i = [0:pins-1]) {
        translate([i * 2.54, 0, -3])
        cube([0.64, 0.64, 11.5]);  // 3mm below + 2.5 housing + 6mm above
    }
}

// ============================================================
// OLED DISPLAY MODULE (approximation on header)
// ============================================================
module oled_display() {
    // PCB of OLED module
    color([0.1, 0.1, 0.6])
    translate([-1, -1, 8.5])
    cube([27, 28, 1.2]);
    
    // Display glass
    color([0.05, 0.05, 0.05])
    translate([0, 3, 9.7])
    cube([25, 14, 1.5]);
    
    // Active display area (blue tint)
    color([0.0, 0.3, 0.8, 0.8])
    translate([1, 4, 11.2])
    cube([23, 12, 0.1]);
    
    // Header pins going down
    pin_header(4);
}

// ============================================================
// FINGERPRINT SENSOR MODULE (approximation)
// ============================================================
module fp_sensor() {
    // Sensor body
    color([0.2, 0.4, 0.2])
    translate([-2, -2, 8.5])
    cube([20, 22, 2.5]);
    
    // Sensing area (capacitive pad)
    color([0.6, 0.6, 0.65])
    translate([2, 5, 11])
    cube([12, 14, 0.5]);
    
    // Connector ribbon area
    color([0.9, 0.85, 0.7])
    translate([0, -2, 8.5])
    cube([16, 4, 0.3]);
    
    // Header pins
    pin_header(6);
}

// ============================================================
// MICROSD MODULE (approximation)
// ============================================================
module microsd_module() {
    // Module PCB
    color([0.1, 0.1, 0.6])
    translate([-2, -2, 8.5])
    cube([24, 18, 1.2]);
    
    // SD card slot (metal housing)
    color(silver_color)
    translate([-1, 0, 9.7])
    cube([15, 14, 2.0]);
    
    // Card slot opening
    color([0.3, 0.3, 0.3])
    translate([0, 14, 10])
    cube([12, 1, 1.5]);
    
    // Header pins
    pin_header(6);
}

// ============================================================
// FULL ASSEMBLY
// ============================================================
module assembly() {
    // PCB Board
    pcb_board();
    
    // U1: ESP32-WROOM-32E — center of board
    translate([31, 14, board_t])
    esp32_module();
    
    // U2: AMS1117-3.3 — top-left power area
    translate([8, 35, board_t])
    ams1117();
    
    // C1: Input cap — near regulator input
    translate([6, 28, board_t])
    cap_electrolytic();
    
    // C2: Output cap — near regulator output
    translate([16, 28, board_t])
    cap_electrolytic();
    
    // C3: Decoupling cap — near ESP32 VDD
    translate([28, 10, board_t])
    smd_0805([0.6, 0.5, 0.2]);
    
    // R1: EN pull-up — near buttons
    translate([30, 6, board_t])
    smd_0805([0.2, 0.15, 0.1]);
    
    // R2: IO0 pull-up — near buttons
    translate([36, 6, board_t])
    smd_0805([0.2, 0.15, 0.1]);
    
    // SW1: Reset button
    translate([30, 3, board_t])
    tactile_button();
    
    // SW2: Boot button
    translate([40, 3, board_t])
    tactile_button();
    
    // J1: Battery header (2-pin) — top-left edge
    translate([5, 45, board_t])
    pin_header(2);
    
    // J2: MicroSD module (6-pin) — left side
    translate([5, 16, board_t])
    microsd_module();
    
    // J3: OLED display (4-pin) — top-right
    translate([60, 38, board_t])
    oled_display();
    
    // J4: Fingerprint sensor (6-pin) — right side
    translate([60, 12, board_t])
    fp_sensor();
}

// Render the full board
assembly();
