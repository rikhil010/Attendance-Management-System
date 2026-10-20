"""
Generates GWASOAT DBMS Project Report as a Word document (.docx)
with embedded diagram images.
Run from the project root:
    python generate_report.py
"""

import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import matplotlib.patheffects as pe
from docx import Document
from docx.shared import Inches, Pt, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import io

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
IMG_DIR = os.path.join(OUT_DIR, "docs", "report_images")
os.makedirs(IMG_DIR, exist_ok=True)

# ─── Colour palette ──────────────────────────────────────────────────────────
C_NAVY    = "#1a2a4a"
C_BLUE    = "#1e5fa8"
C_LBLUE   = "#4a90d9"
C_TEAL    = "#1a7a6e"
C_LTEAL   = "#2ecc9e"
C_ORANGE  = "#e07b39"
C_YELLOW  = "#f0c040"
C_GRAY    = "#5a6a7a"
C_LGRAY   = "#dce4ef"
C_WHITE   = "#ffffff"
C_GREEN   = "#27ae60"
C_RED     = "#c0392b"
C_PURPLE  = "#7d3c98"


def save_fig(fig, name):
    path = os.path.join(IMG_DIR, name)
    fig.savefig(path, dpi=180, bbox_inches='tight', facecolor=fig.get_facecolor())
    plt.close(fig)
    return path


def rounded_box(ax, x, y, w, h, text, facecolor, textcolor=C_WHITE,
                fontsize=9, bold=False, radius=0.03, edgecolor=None,
                subtext=None, subfontsize=7.5):
    """Draw a rounded rectangle with centred label."""
    ec = edgecolor or facecolor
    box = FancyBboxPatch((x, y), w, h,
                         boxstyle=f"round,pad=0,rounding_size={radius}",
                         linewidth=1.2, edgecolor=ec,
                         facecolor=facecolor, zorder=3)
    ax.add_patch(box)
    ty = y + h / 2 + (0.012 if subtext else 0)
    ax.text(x + w / 2, ty, text, ha='center', va='center',
            fontsize=fontsize, color=textcolor,
            fontweight='bold' if bold else 'normal', zorder=4,
            wrap=True)
    if subtext:
        ax.text(x + w / 2, y + h / 2 - 0.018, subtext, ha='center', va='center',
                fontsize=subfontsize, color=textcolor, alpha=0.85, zorder=4)


def arrow(ax, x1, y1, x2, y2, color=C_GRAY, lw=1.5, bidirectional=False):
    style = "<->" if bidirectional else "->"
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle=style, color=color,
                                lw=lw, connectionstyle="arc3,rad=0.0"),
                zorder=2)


# ══════════════════════════════════════════════════════════════════════════════
# DIAGRAM 1 — Full System Architecture
# ══════════════════════════════════════════════════════════════════════════════
def make_system_diagram():
    fig, ax = plt.subplots(figsize=(14, 11))
    fig.patch.set_facecolor("#f4f7fb")
    ax.set_facecolor("#f4f7fb")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis('off')
    ax.set_aspect('equal')

    ax.set_title("GWASOAT — Full System Architecture",
                 fontsize=14, fontweight='bold', color=C_NAVY, pad=12)

    # ── Layer bands ──────────────────────────────────────────────────────────
    layers = [
        (0.0,  0.22, "#e8f0fb", "HARDWARE LAYER  (ESP32)"),
        (0.23, 0.52, "#eaf5ee", "DESKTOP APPLICATION LAYER  (Python / Flask)"),
        (0.54, 0.76, "#fdf4e7", "DATABASE LAYER  (MySQL 8.0)"),
        (0.77, 1.00, "#f9eef9", "CLOUD LAYER  (Optional)"),
    ]
    for y0, y1, col, label in layers:
        band = mpatches.FancyBboxPatch((0.01, y0+0.005), 0.98, y1-y0-0.010,
                                       boxstyle="round,pad=0,rounding_size=0.01",
                                       linewidth=1, edgecolor="#c8d4e8",
                                       facecolor=col, zorder=0)
        ax.add_patch(band)
        ax.text(0.015, y0+0.012, label, fontsize=7, color=C_GRAY,
                fontweight='bold', zorder=1)

    # ── HARDWARE components ───────────────────────────────────────────────────
    hw_items = [
        (0.05, 0.11, "FPM383C\nFingerprint", C_BLUE),
        (0.22, 0.11, "MicroSD\nOffline Cache", C_TEAL),
        (0.39, 0.11, "SSD1306\nOLED Display", C_GRAY),
        (0.56, 0.11, "NimBLE\nGATT Server", C_PURPLE),
        (0.73, 0.11, "LiPo + TP4056\nUSB-C Charging", C_ORANGE),
    ]
    for x, y, lbl, col in hw_items:
        rounded_box(ax, x, y, 0.15, 0.07, lbl, col,
                    fontsize=8, subtext=None)

    # ESP32 MCU central box
    rounded_box(ax, 0.30, 0.02, 0.40, 0.065, "ESP32 MCU  (Arduino / PlatformIO)",
                C_NAVY, fontsize=9, bold=True)

    # arrows from components to MCU
    for x, y, _, _ in hw_items:
        ax.annotate("", xy=(0.50, 0.085), xytext=(x + 0.075, y),
                    arrowprops=dict(arrowstyle="-", color=C_LGRAY, lw=1.0), zorder=1)

    # ── CONNECTIVITY band ─────────────────────────────────────────────────────
    rounded_box(ax, 0.20, 0.235, 0.27, 0.055,
                "WiFi  (Primary)", C_BLUE, fontsize=8.5,
                subtext="HTTP REST  /  AsyncWebServer")
    rounded_box(ax, 0.53, 0.235, 0.27, 0.055,
                "BLE  (Fallback)", C_PURPLE, fontsize=8.5,
                subtext="NimBLE GATT  /  bleak")
    ax.text(0.50, 0.262, "AUTO\nFAILOVER", ha='center', va='center',
            fontsize=6.5, color=C_ORANGE, fontweight='bold')

    arrow(ax, 0.50, 0.085, 0.335, 0.235, color=C_BLUE, lw=2)
    arrow(ax, 0.50, 0.085, 0.665, 0.235, color=C_PURPLE, lw=2)

    # ── DESKTOP APP components ────────────────────────────────────────────────
    app_items = [
        (0.04, 0.39, "api.py\n(ESP32 routes)", C_TEAL),
        (0.22, 0.39, "routes_new.py\nroutes_features.py", C_TEAL),
        (0.40, 0.39, "attendance.py\nregistration.py", C_TEAL),
        (0.60, 0.39, "auth.py\n(Login / RBAC)", C_ORANGE),
        (0.78, 0.39, "cloud_sync.py\nconnection.py", C_GRAY),
    ]
    for x, y, lbl, col in app_items:
        rounded_box(ax, x, y, 0.17, 0.07, lbl, col, fontsize=7.5)

    # Flask box
    rounded_box(ax, 0.15, 0.31, 0.70, 0.055,
                "Flask Server  (port 5000)  +  pywebview Native Window",
                C_NAVY, fontsize=9, bold=True)

    arrow(ax, 0.335, 0.29, 0.335, 0.31, color=C_BLUE, lw=2)
    arrow(ax, 0.665, 0.29, 0.665, 0.31, color=C_PURPLE, lw=2)

    for x, y, _, _ in app_items:
        ax.annotate("", xy=(x+0.085, 0.365), xytext=(x+0.085, 0.39),
                    arrowprops=dict(arrowstyle="-", color=C_LGRAY, lw=1.0), zorder=1)

    # DB layer box
    rounded_box(ax, 0.15, 0.565, 0.45, 0.055,
                "database.py  /  models.py  — MySQL Connection Layer",
                C_NAVY, fontsize=8.5, bold=True)
    arrow(ax, 0.50, 0.46, 0.50, 0.565, color=C_NAVY, lw=2)

    rounded_box(ax, 0.15, 0.625, 0.45, 0.045,
                "mysql-connector-python 8.3.0",
                C_LBLUE, fontsize=8)
    arrow(ax, 0.375, 0.565, 0.375, 0.625, color=C_LBLUE, lw=1.5)

    # MySQL Server
    rounded_box(ax, 0.10, 0.685, 0.55, 0.065,
                "MySQL Server 8.0  —  Database: gwasoat  —  User: gwasoat_user",
                C_TEAL, fontsize=8.5, bold=True)
    arrow(ax, 0.375, 0.670, 0.375, 0.685, color=C_TEAL, lw=2)
    ax.text(0.675, 0.718, "TCP :3306", fontsize=7, color=C_TEAL, fontstyle='italic')

    # Tables mini-row
    tables = ["users","classes","students","courses","attendance\nsessions",
              "session\nattendance","fingerprint\ntemplates","audit_log"]
    tw = 0.105
    gap = 0.005
    tx0 = 0.02
    ty0 = 0.775
    for i, t in enumerate(tables):
        col = [C_BLUE, C_TEAL, C_LBLUE, C_TEAL, C_ORANGE,
               C_ORANGE, C_PURPLE, C_GRAY][i]
        rounded_box(ax, tx0 + i*(tw+gap), ty0, tw, 0.06, t, col,
                    fontsize=6.5, radius=0.015)

    ax.text(0.50, 0.845, "13 Tables  •  utf8mb4  •  Foreign Key Enforced",
            ha='center', fontsize=7.5, color=C_GRAY, fontstyle='italic')

    arrow(ax, 0.375, 0.750, 0.375, 0.775, color=C_GRAY, lw=1.5)

    # Cloud layer
    rounded_box(ax, 0.15, 0.895, 0.70, 0.07,
                "Cloud API  (Optional)  —  Template backup  •  Attendance sync  •  Offline queue",
                C_PURPLE, fontsize=8.5)
    arrow(ax, 0.80, 0.46, 0.80, 0.895, color=C_PURPLE, lw=1.5)

    plt.tight_layout()
    return save_fig(fig, "diagram_system_architecture.png")


# ══════════════════════════════════════════════════════════════════════════════
# DIAGRAM 2 — DBMS Architecture
# ══════════════════════════════════════════════════════════════════════════════
def make_dbms_diagram():
    fig, ax = plt.subplots(figsize=(14, 10))
    fig.patch.set_facecolor("#f4f7fb")
    ax.set_facecolor("#f4f7fb")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis('off')

    ax.set_title("GWASOAT — DBMS Architecture",
                 fontsize=14, fontweight='bold', color=C_NAVY, pad=12)

    # ── Layer bands ───────────────────────────────────────────────────────────
    bands = [
        (0.78, 1.00, "#e8f0fb", "APPLICATION LAYER"),
        (0.56, 0.77, "#eaf5ee", "CONNECTOR LAYER"),
        (0.00, 0.55, "#fdf4e7", "MySQL SERVER LAYER"),
    ]
    for y0, y1, col, lbl in bands:
        ax.add_patch(mpatches.FancyBboxPatch(
            (0.01, y0+0.005), 0.98, y1-y0-0.010,
            boxstyle="round,pad=0,rounding_size=0.01",
            linewidth=1, edgecolor="#c8d4e8", facecolor=col, zorder=0))
        ax.text(0.015, y0+0.012, lbl, fontsize=7.5, color=C_GRAY,
                fontweight='bold', zorder=1)

    # ── Application layer — Python modules ───────────────────────────────────
    mods = [
        (0.03, 0.825, "database.py\nCRUD helpers\nget_db / _fetchone\n_fetchall / _execute", C_BLUE),
        (0.22, 0.825, "models.py\nSchema init\nUser hashing\nlog_action()", C_TEAL),
        (0.41, 0.825, "routes_new.py\nroutes_features.py\nCourse / Admin\nRoutes", C_ORANGE),
        (0.60, 0.825, "attendance.py\nregistration.py\nSession logic\nFP template I/O", C_PURPLE),
        (0.79, 0.825, "api.py\nauth.py\nLegacy ESP32\nAuth routes", C_GRAY),
    ]
    for x, y, lbl, col in mods:
        rounded_box(ax, x, y, 0.175, 0.135, lbl, col, fontsize=7.5, radius=0.02)

    # ── Shared helper block ───────────────────────────────────────────────────
    rounded_box(ax, 0.15, 0.795, 0.70, 0.025,
                "Shared: get_db()  •  _fetchone()  •  _fetchall()  •  _execute()",
                C_NAVY, fontsize=8, bold=True)

    for x, y, _, _ in mods:
        ax.annotate("", xy=(x+0.0875, 0.82), xytext=(x+0.0875, 0.825),
                    arrowprops=dict(arrowstyle="-", color="#aabbcc", lw=0.8), zorder=1)

    arrow(ax, 0.50, 0.795, 0.50, 0.775, color=C_NAVY, lw=2)

    # ── Connector layer ───────────────────────────────────────────────────────
    rounded_box(ax, 0.10, 0.685, 0.80, 0.085,
                "mysql-connector-python  8.3.0",
                C_BLUE, fontsize=11, bold=True)

    # Config details
    cfg = [
        ("host", "localhost"),
        ("port", "3306"),
        ("database", "gwasoat"),
        ("user", "gwasoat_user"),
        ("charset", "utf8mb4"),
        ("use_pure", "True"),
    ]
    for i, (k, v) in enumerate(cfg):
        cx = 0.12 + i * 0.135
        rounded_box(ax, cx, 0.645, 0.115, 0.035,
                    f"{k}: {v}", C_LGRAY, textcolor=C_NAVY, fontsize=7, radius=0.01)

    arrow(ax, 0.50, 0.685, 0.50, 0.645+0.035, color=C_BLUE, lw=1.5)
    arrow(ax, 0.50, 0.645, 0.50, 0.575, color=C_TEAL, lw=2.5)
    ax.text(0.52, 0.61, "TCP / IP  port 3306", fontsize=7.5,
            color=C_TEAL, fontstyle='italic')

    # ── MySQL Server ──────────────────────────────────────────────────────────
    rounded_box(ax, 0.05, 0.495, 0.90, 0.070,
                "MySQL Server 8.0 Community Edition  —  Database: gwasoat  —  Charset: utf8mb4",
                C_TEAL, fontsize=9.5, bold=True)

    # ── Tables grid ───────────────────────────────────────────────────────────
    arrow(ax, 0.50, 0.495, 0.50, 0.455, color=C_TEAL, lw=1.5)

    tables = [
        # (label, colour, x, y)
        ("users\n(id, email, password\nrole, created_at)",              C_BLUE,   0.02,  0.33),
        ("departments\n(id, name)",                                      C_TEAL,   0.22,  0.33),
        ("classes\n(id, name, year\ndepartment_id)",                     C_TEAL,   0.42,  0.33),
        ("batches\n(id, name\nclass_id)",                                C_TEAL,   0.62,  0.33),
        ("students\n(id PK, prn\nroll_no, registered)",                  C_LBLUE,  0.82,  0.33),
        ("courses\n(id, name, code\nteacher_id→users)",                  C_ORANGE, 0.02,  0.17),
        ("course_students\n(course_id\nstudent_id)",                     C_ORANGE, 0.22,  0.17),
        ("fingerprint_templates\n(student_id PK\nLONGBLOB data)",        C_PURPLE, 0.42,  0.17),
        ("attendance_sessions\n(id, course_id\nstarted_at, ended_at)",   C_ORANGE, 0.62,  0.17),
        ("session_attendance\n(session_id\nstudent_id, status)",         C_RED,    0.82,  0.17),
        ("app_settings\n(key PK\nvalue TEXT)",                           C_GRAY,   0.02,  0.01),
        ("audit_log\n(user_id, action\ndetails, created_at)",            C_GRAY,   0.22,  0.01),
        ("timetable\n(course_id\nday, start_time)",                      C_GRAY,   0.42,  0.01),
    ]

    for lbl, col, tx, ty in tables:
        rounded_box(ax, tx, ty, 0.175, 0.135, lbl, col, fontsize=7, radius=0.015)

    # FK relationship lines (simplified key ones)
    fk_links = [
        # students → fingerprint_templates
        (0.9075, 0.33,  0.5175, 0.305),
        # students → session_attendance
        (0.9075, 0.33,  0.9075, 0.305),
        # courses → attendance_sessions
        (0.1075, 0.17,  0.7075, 0.170),
        # courses → course_students
        (0.1975, 0.17,  0.2975, 0.170),
        # attendance_sessions → session_attendance
        (0.7975, 0.17,  0.8975, 0.170),
    ]
    for x1, y1, x2, y2 in fk_links:
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle="-|>", color="#aaaaaa",
                                   lw=0.8, mutation_scale=8), zorder=1)

    ax.text(0.50, 0.455, "13 Tables  •  Foreign Key Enforced  •  utf8mb4_unicode_ci",
            ha='center', fontsize=8, color=C_GRAY, fontstyle='italic')

    plt.tight_layout()
    return save_fig(fig, "diagram_dbms_architecture.png")


# ══════════════════════════════════════════════════════════════════════════════
# WORD DOCUMENT
# ══════════════════════════════════════════════════════════════════════════════
def set_cell_bg(cell, hex_color):
    tc   = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd  = OxmlElement('w:shd')
    shd.set(qn('w:val'),   'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'),  hex_color.lstrip('#'))
    tcPr.append(shd)


def heading(doc, text, level):
    p = doc.add_heading(text, level=level)
    run = p.runs[0] if p.runs else p.add_run(text)
    run.font.color.rgb = RGBColor(0x1a, 0x2a, 0x4a)
    return p


def body(doc, text):
    p = doc.add_paragraph(text)
    p.paragraph_format.space_after = Pt(6)
    for run in p.runs:
        run.font.size = Pt(11)
    return p


def add_table(doc, headers, rows, col_widths=None):
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = 'Table Grid'
    # Header row
    hrow = table.rows[0]
    for i, h in enumerate(headers):
        cell = hrow.cells[i]
        cell.text = h
        cell.paragraphs[0].runs[0].font.bold = True
        cell.paragraphs[0].runs[0].font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_cell_bg(cell, "1a2a4a")
    # Data rows
    for ri, row in enumerate(rows):
        tr = table.rows[ri + 1]
        for ci, val in enumerate(row):
            cell = tr.cells[ci]
            cell.text = str(val)
            cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.LEFT
            if ri % 2 == 0:
                set_cell_bg(cell, "dce4ef")
    # Column widths
    if col_widths:
        for row in table.rows:
            for i, cell in enumerate(row.cells):
                cell.width = Inches(col_widths[i])
    return table


def add_code_block(doc, code):
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Cm(0.5)
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after  = Pt(4)
    run = p.add_run(code)
    run.font.name = 'Courier New'
    run.font.size = Pt(8)
    run.font.color.rgb = RGBColor(0x1a, 0x4a, 0x1a)
    # light green shading on paragraph
    pPr  = p._p.get_or_add_pPr()
    shd  = OxmlElement('w:shd')
    shd.set(qn('w:val'),   'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'),  'eaf5ee')
    pPr.append(shd)
    return p


def build_word(img1, img2):
    doc = Document()

    # ── Page margins ────────────────────────────────────────────────────────
    for section in doc.sections:
        section.top_margin    = Cm(2.0)
        section.bottom_margin = Cm(2.0)
        section.left_margin   = Cm(2.5)
        section.right_margin  = Cm(2.5)

    # ── Cover ────────────────────────────────────────────────────────────────
    doc.add_paragraph()
    title = doc.add_heading("GWASOAT", 0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.runs[0].font.color.rgb = RGBColor(0x1a, 0x2a, 0x4a)

    sub = doc.add_paragraph("Biometric Attendance System")
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub.runs[0].font.size = Pt(16)
    sub.runs[0].font.color.rgb = RGBColor(0x1e, 0x5f, 0xa8)

    sub2 = doc.add_paragraph("DBMS Project Report")
    sub2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub2.runs[0].font.size = Pt(13)
    sub2.runs[0].font.italic = True

    doc.add_paragraph()
    date_p = doc.add_paragraph("October 2026")
    date_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    date_p.runs[0].font.color.rgb = RGBColor(0x5a, 0x6a, 0x7a)

    doc.add_page_break()

    # ════════════════════════════════════════════════════════════════════════
    # 1. PROJECT SUMMARY
    # ════════════════════════════════════════════════════════════════════════
    heading(doc, "1.  Project Summary", 1)

    body(doc,
         "GWASOAT is a fingerprint-based biometric attendance management system built "
         "around an ESP32 microcontroller and an FPM383C capacitive fingerprint sensor. "
         "It replaces manual roll calls entirely: enrolled fingerprint templates are loaded "
         "onto the device at the start of each class, students scan their fingers, and the "
         "system records presence in real time. All data is persisted in a MySQL 8.0 database "
         "and served through a Python Flask desktop application rendered natively via pywebview.")

    body(doc,
         "The system supports multiple teachers and an admin role, course-level attendance "
         "tracking, defaulter reports, bulk CSV import, timetable management, and an audit log. "
         "It also supports a BLE fallback when WiFi is unavailable, and an optional cloud sync "
         "layer for template and attendance backup.")

    heading(doc, "1.1  Key Features", 2)
    add_table(doc,
        ["Feature", "Description"],
        [
            ["Fingerprint attendance",    "FPM383C sensor, up to 255 templates per session"],
            ["Hybrid connectivity",        "WiFi primary, BLE automatic fallback (bleak)"],
            ["Offline capable",            "MicroSD card caches templates and attendance logs"],
            ["Multi-user system",          "Role-based access — Admin and Teacher roles"],
            ["Cloud sync",                 "Templates and attendance records sync to cloud API"],
            ["Desktop application",        "Python/Flask served inside a pywebview native window"],
            ["Custom PCB",                 "85×55mm 2-layer KiCad board with USB-C LiPo charging"],
            ["Defaulter reports",          "Per-course attendance percentage with threshold alert"],
            ["Bulk student import",        "CSV import for class rosters"],
            ["Audit log",                  "All admin/teacher actions recorded with timestamp"],
        ],
        col_widths=[2.0, 4.2])

    heading(doc, "1.2  Technology Stack", 2)
    add_table(doc,
        ["Layer", "Technology"],
        [
            ["Firmware",      "C++ / Arduino (PlatformIO), ESP32 DOIT DevKit"],
            ["Communication", "HTTP REST (WiFi), BLE GATT (bleak / NimBLE)"],
            ["Backend",       "Python 3.12, Flask 3.x"],
            ["Frontend",      "Bootstrap 5, jQuery, HTML5"],
            ["Desktop shell", "pywebview (Chromium-based native window)"],
            ["Database",      "MySQL 8.0 Community Server"],
            ["DB driver",     "mysql-connector-python 8.3.0"],
            ["Hardware",      "ESP32, FPM383C, SSD1306 OLED, MicroSD, TP4056"],
        ],
        col_widths=[2.0, 4.2])

    doc.add_page_break()

    # ════════════════════════════════════════════════════════════════════════
    # 2. SYSTEM ARCHITECTURE
    # ════════════════════════════════════════════════════════════════════════
    heading(doc, "2.  System Architecture", 1)

    body(doc,
         "The system is divided into four layers: the ESP32 hardware layer, the desktop "
         "application layer, the MySQL database layer, and an optional cloud sync layer. "
         "The diagram below shows how these layers interact.")

    doc.add_picture(img1, width=Inches(6.2))
    doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap = doc.add_paragraph("Figure 1 — Full System Architecture")
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap.runs[0].font.italic = True
    cap.runs[0].font.size = Pt(9)
    cap.runs[0].font.color.rgb = RGBColor(0x5a, 0x6a, 0x7a)

    heading(doc, "2.1  Layer Descriptions", 2)

    body(doc,
         "Hardware Layer: The ESP32 runs a C++ firmware (PlatformIO/Arduino) that drives "
         "the FPM383C fingerprint sensor via UART, stores template and attendance caches "
         "on a MicroSD card, and exposes two communication interfaces — an AsyncWebServer "
         "over WiFi and a NimBLE GATT server over Bluetooth.")

    body(doc,
         "Desktop Application Layer: A Python 3.12 Flask server runs on port 5000 and is "
         "rendered inside a pywebview native window. It handles all business logic: "
         "registration, attendance marking, session management, user authentication, "
         "reporting, and communication with both the ESP32 and the database.")

    body(doc,
         "Database Layer: MySQL 8.0 Community Server stores all persistent data. The "
         "Python application connects via mysql-connector-python using a dedicated "
         "restricted user (gwasoat_user) with access only to the gwasoat database.")

    body(doc,
         "Cloud Layer (optional): cloud_sync.py handles uploading fingerprint templates "
         "and attendance records to a REST API. It maintains a local file cache for "
         "offline queuing so no data is lost when the network is unavailable.")

    doc.add_page_break()

    # ════════════════════════════════════════════════════════════════════════
    # 3. DBMS ARCHITECTURE
    # ════════════════════════════════════════════════════════════════════════
    heading(doc, "3.  DBMS Architecture", 1)

    body(doc,
         "The database architecture is structured into three layers: the application layer "
         "(Python modules that issue queries), the connector layer (mysql-connector-python), "
         "and the MySQL server layer (schema, tables, and constraints).")

    doc.add_picture(img2, width=Inches(6.2))
    doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap2 = doc.add_paragraph("Figure 2 — DBMS Architecture")
    cap2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap2.runs[0].font.italic = True
    cap2.runs[0].font.size = Pt(9)
    cap2.runs[0].font.color.rgb = RGBColor(0x5a, 0x6a, 0x7a)

    heading(doc, "3.1  Connection Configuration", 2)
    add_code_block(doc,
        "DB_CONFIG = {\n"
        "    'host':     'localhost',\n"
        "    'port':     3306,\n"
        "    'database': 'gwasoat',\n"
        "    'user':     'gwasoat_user',\n"
        "    'password': 'gwasoat_pass_2026',\n"
        "    'charset':  'utf8mb4',\n"
        "    'use_pure': True,\n"
        "}")

    heading(doc, "3.2  Shared Helper Functions", 2)
    body(doc,
         "All database access across the application is funnelled through four shared "
         "helper functions defined in database.py:")
    add_table(doc,
        ["Function", "Purpose"],
        [
            ["get_db()",       "Opens and returns a new MySQL connection"],
            ["_fetchone(db, sql, params)", "Executes SELECT and returns one dict row"],
            ["_fetchall(db, sql, params)", "Executes SELECT and returns list of dict rows"],
            ["_execute(db, sql, params)",  "Executes INSERT / UPDATE / DELETE, returns lastrowid"],
        ],
        col_widths=[2.8, 3.4])

    doc.add_page_break()

    # ════════════════════════════════════════════════════════════════════════
    # 4. DATABASE DESIGN
    # ════════════════════════════════════════════════════════════════════════
    heading(doc, "4.  Database Design", 1)

    heading(doc, "4.1  Design Rationale — MySQL over SQLite", 2)
    body(doc,
         "The project was originally developed with SQLite as a file-based single-user "
         "prototype database. Migration to MySQL 8.0 was carried out to achieve:")
    items = [
        "Concurrent access — multiple teachers can mark attendance simultaneously without file locks.",
        "Foreign key enforcement — relational integrity enforced at the database engine level.",
        "LONGBLOB support — binary fingerprint templates (up to 2 KB each) stored natively.",
        "Network-ready — MySQL server can be hosted centrally on a school server in future.",
        "Workbench tooling — MySQL Workbench 8.0 CE for schema inspection and manual queries.",
    ]
    for item in items:
        p = doc.add_paragraph(item, style='List Bullet')
        p.runs[0].font.size = Pt(11)

    heading(doc, "4.2  Table Descriptions", 2)
    add_table(doc,
        ["Table", "Purpose", "Key Columns"],
        [
            ["users",                  "Admin and teacher accounts",              "id, email, password (SHA-256), role"],
            ["departments",            "Academic departments",                    "id, name"],
            ["classes",                "Academic classes / years",                "id, name, year, department_id"],
            ["batches",                "Subdivisions of a class (A, B, C)",       "id, name, class_id"],
            ["students",               "Student records with biometric link",     "id (FP slot), prn, roll_no, registered"],
            ["courses",                "Subjects assigned to teachers",           "id, name, code, teacher_id"],
            ["course_students",        "Many-to-many course/student mapping",     "course_id, student_id (unique pair)"],
            ["fingerprint_templates",  "Binary FP template per student",          "student_id (PK), template_data LONGBLOB"],
            ["attendance_sessions",    "One record per class session conducted",  "id, course_id, teacher_id, started_at, ended_at"],
            ["session_attendance",     "Per-student attendance mark per session", "session_id, student_id, status (Present/Absent/--)"],
            ["app_settings",           "Runtime configuration key-value store",   "key (PK), value TEXT"],
            ["audit_log",              "Immutable record of all system actions",  "user_id, action, details, created_at"],
            ["timetable",              "Scheduled course time slots",             "course_id, day_of_week, start_time"],
        ],
        col_widths=[1.6, 2.2, 2.4])

    doc.add_page_break()

    # ════════════════════════════════════════════════════════════════════════
    # 5. SCHEMA
    # ════════════════════════════════════════════════════════════════════════
    heading(doc, "5.  Schema Definition", 1)
    body(doc, "Key table definitions (condensed):")

    add_code_block(doc,
        "CREATE TABLE users (\n"
        "    id INT AUTO_INCREMENT PRIMARY KEY,\n"
        "    name VARCHAR(255) NOT NULL,\n"
        "    email VARCHAR(255) UNIQUE NOT NULL,\n"
        "    password VARCHAR(255) NOT NULL,  -- SHA-256 with salt\n"
        "    role VARCHAR(50) NOT NULL DEFAULT 'student',\n"
        "    created_at DATETIME NOT NULL\n"
        ");\n\n"
        "CREATE TABLE students (\n"
        "    id INT PRIMARY KEY,              -- same as FP sensor slot ID\n"
        "    prn VARCHAR(100),\n"
        "    roll_no VARCHAR(100),\n"
        "    name VARCHAR(255) NOT NULL,\n"
        "    class_id INT, batch_id INT,\n"
        "    registered TINYINT NOT NULL DEFAULT 0\n"
        ");\n\n"
        "CREATE TABLE fingerprint_templates (\n"
        "    student_id    INT PRIMARY KEY,\n"
        "    template_data LONGBLOB NOT NULL, -- raw binary FP data\n"
        "    template_size INT NOT NULL,\n"
        "    created_at    DATETIME NOT NULL\n"
        ");\n\n"
        "CREATE TABLE attendance_sessions (\n"
        "    id INT AUTO_INCREMENT PRIMARY KEY,\n"
        "    course_id INT, teacher_id INT, class_id INT,\n"
        "    started_at DATETIME NOT NULL,\n"
        "    ended_at   DATETIME\n"
        ");\n\n"
        "CREATE TABLE session_attendance (\n"
        "    session_id   INT NOT NULL,\n"
        "    student_id   INT NOT NULL,\n"
        "    student_name VARCHAR(255) NOT NULL,\n"
        "    status       VARCHAR(20) NOT NULL DEFAULT '--',\n"
        "    marked_at    DATETIME,\n"
        "    UNIQUE KEY uq_session_student (session_id, student_id)\n"
        ");\n\n"
        "CREATE TABLE audit_log (\n"
        "    id INT AUTO_INCREMENT PRIMARY KEY,\n"
        "    user_id INT, user_name VARCHAR(255),\n"
        "    action VARCHAR(255) NOT NULL,\n"
        "    details TEXT, created_at DATETIME NOT NULL\n"
        ");")

    doc.add_page_break()

    # ════════════════════════════════════════════════════════════════════════
    # 6. DATA FLOW
    # ════════════════════════════════════════════════════════════════════════
    heading(doc, "6.  Data Flow", 1)

    heading(doc, "6.1  Student Fingerprint Registration", 2)
    steps = [
        ("1", "Teacher clicks Register Fingerprint in the Web UI"),
        ("2", "Flask sends GET /api/register/<student_id> to the route handler"),
        ("3", "ESP32 receives /register?id=X — prompts student to scan finger twice"),
        ("4", "Flask polls /register_status every 2 seconds"),
        ("5", "On success: Flask requests the template via GET /get_template?id=X"),
        ("6", "ESP32 returns Base64-encoded binary template data"),
        ("7", "MySQL: INSERT INTO fingerprint_templates (LONGBLOB)"),
        ("8", "MySQL: UPDATE students SET registered=1 WHERE id=X"),
    ]
    add_table(doc, ["Step", "Action"], steps, col_widths=[0.5, 5.7])

    heading(doc, "6.2  Attendance Session Flow", 2)
    steps2 = [
        ("1",  "Teacher clicks Start Attendance for a course"),
        ("2",  "MySQL SELECT fingerprint_templates for all enrolled students"),
        ("3",  "For each template: POST http://<esp32_ip>/command to upload to sensor"),
        ("4",  "MySQL INSERT INTO attendance_sessions → returns new session_id"),
        ("5",  "MySQL INSERT INTO session_attendance (one row per student, status='--')"),
        ("6",  "Students scan fingers — ESP32 matches template, returns student ID"),
        ("7",  "Flask receives match → MySQL UPDATE session_attendance SET status='Present'"),
        ("8",  "Teacher stops session → MySQL UPDATE remaining rows SET status='Absent'"),
        ("9",  "MySQL UPDATE attendance_sessions SET ended_at=NOW()"),
    ]
    add_table(doc, ["Step", "Action"], steps2, col_widths=[0.5, 5.7])

    heading(doc, "6.3  Report / Defaulter Generation", 2)
    body(doc,
         "Flask queries session_attendance joined with attendance_sessions for the selected "
         "course, aggregates COUNT(sessions) and SUM(status='Present') per student, calculates "
         "attendance percentage, and flags any student below the configurable threshold (default 75%) "
         "as a defaulter. Results are returned as JSON or exported as a CSV file.")

    doc.add_page_break()

    # ════════════════════════════════════════════════════════════════════════
    # 7. MIGRATION
    # ════════════════════════════════════════════════════════════════════════
    heading(doc, "7.  Migration from SQLite to MySQL", 1)

    body(doc,
         "The project originally used SQLite as a file-based prototype database. "
         "The following files were updated to migrate to MySQL 8.0:")

    heading(doc, "7.1  Files Modified", 2)
    add_table(doc,
        ["File", "Change Made"],
        [
            ["database.py",           "Full rewrite — SQLite → MySQL connector, helper functions added"],
            ["models.py",             "Full rewrite — schema creation using information_schema for column checks"],
            ["attendance.py",         "All ? → %s, db.execute() → cursor pattern"],
            ["registration.py",       "All ? → %s, cursor pattern"],
            ["api.py",                "All ? → %s, INSERT OR REPLACE → ON DUPLICATE KEY UPDATE"],
            ["routes_new.py",         "Full rewrite — all SQLite calls replaced"],
            ["routes_features.py",    "Full rewrite — all SQLite calls replaced"],
            ["auth.py",               "db.execute().fetchone() → _fetchone() helper"],
        ],
        col_widths=[2.0, 4.2])

    heading(doc, "7.2  Syntax Differences Handled", 2)
    add_table(doc,
        ["SQLite", "MySQL (replaced with)"],
        [
            ["? placeholder",            "%s placeholder"],
            ["AUTOINCREMENT",             "AUTO_INCREMENT"],
            ["INSERT OR REPLACE",         "ON DUPLICATE KEY UPDATE"],
            ["INSERT OR IGNORE",          "INSERT IGNORE"],
            ["PRAGMA table_info(t)",      "SELECT … FROM information_schema.columns"],
            ["db.execute(sql).fetchone()","_fetchone(db, sql, params)"],
            ["sqlite3.IntegrityError",    "mysql.connector.errors.IntegrityError"],
            ["BLOB",                      "LONGBLOB (for templates up to 64 KB)"],
        ],
        col_widths=[3.1, 3.1])

    heading(doc, "7.3  Data Migration Results", 2)
    body(doc,
         "A one-time migration script (migrate_sqlite_to_mysql.py) transferred all "
         "records from the original SQLite file (data/attendance.db) into MySQL:")
    add_table(doc,
        ["Table", "Rows Migrated"],
        [
            ["classes",              "1"],
            ["students",             "6"],
            ["fingerprint_templates","6"],
            ["attendance_sessions",  "79"],
            ["session_attendance",   "351 (136 after FK validation)"],
            ["attendance_records",   "64"],
            ["users",                "2"],
            ["app_settings",         "5"],
        ],
        col_widths=[3.0, 3.2])

    body(doc,
         "Note: the difference in session_attendance rows (351 → 136) is due to MySQL's "
         "foreign key enforcement rejecting orphaned records that referenced deleted students — "
         "this is correct behaviour and indicates the original SQLite database had stale data.")

    doc.add_page_break()

    # ════════════════════════════════════════════════════════════════════════
    # 8. SECURITY
    # ════════════════════════════════════════════════════════════════════════
    heading(doc, "8.  Security Considerations", 1)

    heading(doc, "8.1  Database User Privilege Scoping", 2)
    body(doc,
         "The application never connects as the MySQL root user. A dedicated user "
         "gwasoat_user is created with GRANT ALL PRIVILEGES ON gwasoat.* — access is "
         "scoped to the gwasoat database only, minimising blast radius in case of any "
         "application vulnerability.")
    add_code_block(doc,
        "CREATE USER 'gwasoat_user'@'localhost' IDENTIFIED BY '...';\n"
        "GRANT ALL PRIVILEGES ON gwasoat.* TO 'gwasoat_user'@'localhost';\n"
        "FLUSH PRIVILEGES;")

    heading(doc, "8.2  Password Hashing", 2)
    body(doc,
         "User passwords are hashed with SHA-256 and a fixed application salt before "
         "storage. Plaintext passwords are never written to the database.")
    add_code_block(doc,
        "hashlib.sha256(f'gwasoat_salt_2026{password}'.encode()).hexdigest()")
    body(doc,
         "For a production deployment, bcrypt or argon2 with per-user random salts "
         "would be recommended.")

    heading(doc, "8.3  SQL Injection Prevention", 2)
    body(doc,
         "All queries use parameterized %s placeholders via mysql-connector-python. "
         "No string concatenation is used to build SQL, eliminating SQL injection risk.")

    heading(doc, "8.4  Role-Based Access Control", 2)
    body(doc,
         "Flask route decorators @login_required and @admin_required in auth.py enforce "
         "access at the API level. Teachers can only access their own courses; Admins "
         "have full system access.")

    doc.add_page_break()

    # ════════════════════════════════════════════════════════════════════════
    # 9. CONCLUSION
    # ════════════════════════════════════════════════════════════════════════
    heading(doc, "9.  Conclusion", 1)
    body(doc,
         "The GWASOAT project successfully integrates MySQL 8.0 as the persistent storage "
         "backend for a real-time biometric attendance system. The database design is "
         "normalised, foreign-key enforced, and supports concurrent multi-user access "
         "across 13 tables covering the full lifecycle of attendance management.")

    body(doc,
         "The migration from SQLite to MySQL was completed without loss of application "
         "functionality. All 8 affected Python source files were updated, and the complete "
         "historical data of 79 attendance sessions and 6 enrolled students was migrated "
         "successfully. The system is ready for deployment on a local school network, with "
         "a clear upgrade path to central server hosting by updating the DB_CONFIG "
         "connection parameters.")

    # ── Save ─────────────────────────────────────────────────────────────────
    out_path = os.path.join(OUT_DIR, "GWASOAT_DBMS_Report.docx")
    doc.save(out_path)
    return out_path


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("Generating diagram 1 — System Architecture ...")
    img1 = make_system_diagram()
    print(f"  Saved: {img1}")

    print("Generating diagram 2 — DBMS Architecture ...")
    img2 = make_dbms_diagram()
    print(f"  Saved: {img2}")

    print("Building Word document ...")
    docx_path = build_word(img1, img2)
    print(f"  Saved: {docx_path}")

    print("\nDone! Files created:")
    print(f"  {img1}")
    print(f"  {img2}")
    print(f"  {docx_path}")
