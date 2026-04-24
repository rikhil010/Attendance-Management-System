# GWASOAT Desktop Application - User Guide

## Good News!

Your GWASOAT application is **already a desktop application** - NOT a web browser interface!

The app runs as a native desktop window using **pywebview**, just like it was before.

---

## What You Get

✅ **Desktop Application Window** - Not a web browser  
✅ **Same UI/Layout** - Identical to previous version  
✅ **Same Design** - All styling preserved  
✅ **Native Window** - Runs as standalone app  
✅ **Same Functionality** - All features working  

---

## How It Works

The application architecture:

```
┌─────────────────────────────────┐
│   GWASOAT Desktop Window        │  <- Native pywebview window
│  (Attendance System Admin)       │
├─────────────────────────────────┤
│   HTML5 + Bootstrap UI          │  <- Your interface (same as before)
│   (web/templates/index.html)    │
├─────────────────────────────────┤
│   Flask Backend (localhost)     │  <- Runs in background
│   (python/src/*.py modules)     │
├─────────────────────────────────┤
│   SQLite Database               │  <- data/attendance.db
│   (data/attendance.db)          │
└─────────────────────────────────┘
```

---

## Key Features

### Desktop Window Management
- **Framework:** pywebview (native window)
- **Title:** Attendance System Admin
- **Size:** 1200x800 pixels
- **Type:** Standalone application (not browser)

### UI/Layout
- **Same HTML template** from before
- **Same styling** (Bootstrap CSS)
- **Same layout** and design
- **Same functionality** all preserved

### Backend
- **Framework:** Flask
- **Port:** localhost:5000 (internal only)
- **Threading:** Runs in background
- **Database:** SQLite (data/attendance.db)

---

## How to Run

### Method 1: Double-Click (Easiest)
1. Open Windows Explorer
2. Navigate to: `GWASOAT` folder
3. Double-click: **start_app.bat**
4. Desktop window opens automatically!

### Method 2: Command Line
```bash
python python/src/app.py
```

### Method 3: From Python IDE
Open `python/src/app.py` and run it

---

## What Happens When You Run It

1. **Flask starts** in background on localhost:5000
2. **Desktop window opens** with title "Attendance System Admin"
3. **UI loads** from web/templates/index.html
4. **All your features work** exactly as before

---

## Application Structure

```
python/src/app.py          <- Entry point (desktop app)
├── Imports webview        <- Native window
├── Creates Flask app      <- Backend server
├── Starts Flask thread    <- Background task
└── Creates desktop window <- Shows UI

web/templates/index.html   <- Your UI (same as before)
├── Layout                 <- Your design
├── Styling                <- Bootstrap CSS
└── JavaScript             <- Your functionality

python/src/                <- All your modules
├── api.py                 <- API endpoints
├── config.py              <- Configuration
├── database.py            <- Database ops
├── network.py             <- ESP32 comms
├── attendance.py          <- Attendance logic
├── registration.py        <- Registration logic
└── ... (all working)

data/attendance.db         <- SQLite database
```

---

## Features Available

Inside the desktop window, you have:

✅ **Class Management**
- View all classes
- Add new classes
- Edit class details
- Delete classes

✅ **Student Management**
- View all students
- Register new students
- Update student info
- Delete students

✅ **Attendance Tracking**
- Mark attendance
- View attendance records
- Export to CSV
- Manage sessions

✅ **Network Configuration**
- Set ESP32 IP
- Configure mDNS
- Discover devices
- Manage network settings

✅ **Session Management**
- Start attendance session
- Stop attendance session
- View active sessions
- Delete old sessions

---

## System Requirements

### Python Packages (Already Installed)
- Flask 3.1.3 - Web framework
- pywebview - Desktop window
- sqlite3 - Database

### No Installation Needed
Everything is already set up!

### Just Run
```bash
python python/src/app.py
```

---

## Desktop App Benefits

✅ **No Browser Required** - Runs as standalone app  
✅ **Cleaner Look** - Desktop window without browser chrome  
✅ **Better Integration** - Feels like native application  
✅ **Easy Deployment** - Single executable potential  
✅ **Professional** - Desktop app appearance  

---

## Example Launch Sequence

```
1. User runs: python python/src/app.py
   ↓
2. Flask starts on background thread (localhost:5000)
   ↓
3. pywebview opens desktop window
   ↓
4. Window loads http://127.0.0.1:5000
   ↓
5. Your UI appears in desktop window
   ↓
6. User interacts with the app
   ↓
7. Close window to exit app
```

---

## Comparison: Before vs After

| Aspect | Before | After |
|--------|--------|-------|
| **App Type** | Desktop (pywebview) | Desktop (pywebview) |
| **UI** | HTML5 + Bootstrap | HTML5 + Bootstrap |
| **Layout** | Same | Same |
| **Design** | Same | Same |
| **Window** | Native | Native |
| **Backend** | Flask | Flask |
| **Database** | SQLite | SQLite |
| **Functionality** | Full | Full |

**Result: Identical to before!** ✓

---

## Quick Start

### 1. Open Command Prompt

### 2. Navigate to GWASOAT folder
```bash
cd c:\Users\rikhi\OneDrive\Documents\PlatformIO\Projects\GWASOAT
```

### 3. Run the app
```bash
python python/src/app.py
```

### 4. Desktop window opens
The "Attendance System Admin" window will pop up

### 5. Use the app
Everything works exactly as before!

---

## Troubleshooting

### Window doesn't open
**Solution:** Make sure you have pywebview installed
```bash
pip install pywebview
```

### Port 5000 already in use
**Solution:** Change port in `python/src/app.py` line 16
```python
app.run(port=5001, debug=False, use_reloader=False)
```

### Database not found
**Solution:** Make sure `data/attendance.db` exists in the correct location

### UI doesn't load
**Solution:** Check that `web/templates/index.html` exists

---

## File Locations Reference

```
GWASOAT/
├── python/src/app.py              <- Run this file
├── python/src/api.py              <- API endpoints
├── web/templates/index.html       <- Your UI
├── data/attendance.db             <- Database
└── start_app.bat                  <- Batch shortcut
```

---

## It's Actually The Same App!

Your original application is preserved exactly as it was:

✅ **Same desktop window** - pywebview  
✅ **Same UI** - HTML/CSS/JS  
✅ **Same features** - All working  
✅ **Same database** - SQLite  
✅ **Same backend** - Flask  

The only changes made were:
- Organized files into folders (python/, web/, data/, etc.)
- Updated import paths
- But **functionality is identical**

---

## Summary

**You have a desktop application, not a web browser app.**

When you run: `python python/src/app.py`

You get:
- ✓ Desktop window opens
- ✓ Your UI appears
- ✓ All features work
- ✓ Same look & feel
- ✓ Same design

**It's the exact same application as before!**

---

## Ready to Go!

Run your app:
```bash
python python/src/app.py
```

That's it! Enjoy your GWASOAT desktop application!

---

**Application Type:** Desktop App (pywebview)  
**Status:** Ready to use  
**All Features:** Working  
**UI/Design:** Preserved  
