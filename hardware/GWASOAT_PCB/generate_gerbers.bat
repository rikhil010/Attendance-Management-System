@echo off
REM ============================================================
REM GWASOAT PCB - Gerber Generation Script
REM Run from KiCad CLI or use File > Plot in KiCad PCB Editor
REM ============================================================
REM
REM This script is a reference for the layers to export.
REM In KiCad 8, use: File > Plot > Select layers below > Plot
REM
REM Required Gerber layers for 2-layer fab:
REM   F.Cu        - Front copper (signals + power)
REM   B.Cu        - Back copper (ground pour)
REM   F.SilkS     - Front silkscreen
REM   B.SilkS     - Back silkscreen (optional)
REM   F.Mask      - Front solder mask
REM   B.Mask      - Back solder mask
REM   Edge.Cuts   - Board outline
REM   F.Paste     - Front paste (for stencil, optional)
REM
REM Drill file:
REM   Generate via File > Fabrication Outputs > Drill Files
REM   Format: Excellon, PTH and NPTH in single file
REM   Units: mm
REM
REM For JLCPCB:
REM   Zip all .gbr + .drl files together
REM   Upload at https://cart.jlcpcb.com/quote
REM   Select: 2 layers, 1.6mm, FR4, HASL lead-free
REM
echo.
echo Open GWASOAT_PCB.kicad_pcb in KiCad PCB Editor
echo Then: File ^> Plot ^> Select all layers listed above ^> Plot
echo Then: File ^> Fabrication Outputs ^> Drill Files ^> Generate
echo.
pause
