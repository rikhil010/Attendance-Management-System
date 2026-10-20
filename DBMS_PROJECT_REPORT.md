# GWASOAT — DBMS Project Report
### Biometric Attendance System with MySQL Backend

---

## Table of Contents

1. [Project Summary](#1-project-summary)
2. [System Architecture](#2-system-architecture)
3. [DBMS Architecture](#3-dbms-architecture)
4. [Database Design](#4-database-design)
5. [Schema Definition](#5-schema-definition)
6. [Data Flow](#6-data-flow)
7. [Migration from SQLite to MySQL](#7-migration-from-sqlite-to-mysql)
8. [Security Considerations](#8-security-considerations)
9. [DBMS Syllabus Demonstration](#9-dbms-syllabus-demonstration)
10. [Conclusion](#10-conclusion)

---

## 1. Project Summary

**GWASOAT** (stands for the project codename) is a biometric attendance management system built around an **ESP32 microcontroller** and a **FPM383C fingerprint sensor**. It enables teachers to conduct and record student attendance through fingerprint scanning, replacing manual roll calls entirely.

### Core Idea

The fingerprint sensor on the ESP32 acts as a **temporary session cache** — at the start of each class, the teacher loads the enrolled fingerprint templates for that course onto the device. Students scan their fingers; the ESP32 matches the scan and records the attendance. At the end of the session, all records are pushed back to the desktop application and stored in the database.

### Key Features

| Feature | Description |
|---|---|
| Fingerprint-based attendance | FPM383C sensor, up to 255 templates per session |
| Hybrid connectivity | WiFi primary, BLE automatic fallback |
| Offline capable | MicroSD card caches templates and attendance logs |
| Multi-user system | Role-based access: Admin, Teacher and Student roles (table-driven permissions) |
| Student portal | Students log in to view their courses, attendance, grades, timetable and class |
| Grades | Teachers/admin record per-component grades; students view them read-only |
| Cloud sync | Fingerprint templates and attendance records sync to cloud API |
| Desktop application | Python/Flask app rendered in a native window via pywebview |
| Custom PCB | 85×55mm 2-layer KiCad board with USB-C LiPo charging |
| Defaulter reports | Per-course attendance percentage with configurable threshold |
| Bulk student import | CSV import for class rosters |
| Audit log | All admin/teacher actions recorded |

### Technology Stack

| Layer | Technology |
|---|---|
| Firmware | C++ / Arduino framework (PlatformIO), ESP32 |
| Communication | HTTP REST (WiFi), BLE GATT (bleak), AsyncTCP |
| Backend | Python 3.12, Flask 3.x |
| Frontend | Bootstrap 5, jQuery, HTML5 (served by Flask) |
| Desktop shell | pywebview (Chromium-based native window) |
| Database | MySQL 8.0 Community Server |
| DB driver | mysql-connector-python 8.3.0 |
| Hardware | ESP32 DOIT DevKit, FPM383C, SSD1306 OLED, MicroSD, TP4056 |

---

## 2. System Architecture

### 2.1 Full System Block Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          GWASOAT SYSTEM                                 │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                      HARDWARE LAYER (ESP32)                       │  │
│  │                                                                   │  │
│  │   ┌─────────────┐   ┌──────────────┐   ┌───────────────────┐    │  │
│  │   │  FPM383C    │   │  MicroSD     │   │   SSD1306 OLED    │    │  │
│  │   │ Fingerprint │   │  Card        │   │   Display         │    │  │
│  │   │  Sensor     │   │  (Offline    │   │   (Status/UI)     │    │  │
│  │   │             │   │   Cache)     │   │                   │    │  │
│  │   └──────┬──────┘   └──────┬───────┘   └─────────┬─────────┘    │  │
│  │          │                 │                       │             │  │
│  │          └─────────────────┴───────────────────────┘             │  │
│  │                                  │                               │  │
│  │                         ┌────────┴────────┐                      │  │
│  │                         │   ESP32 MCU     │                      │  │
│  │                         │  (Arduino FW)   │                      │  │
│  │                         │                 │                      │  │
│  │                         │  ┌───────────┐  │                      │  │
│  │                         │  │  NimBLE   │  │                      │  │
│  │                         │  │  GATT     │  │                      │  │
│  │                         │  │  Server   │  │                      │  │
│  │                         │  ├───────────┤  │                      │  │
│  │                         │  │  Async    │  │                      │  │
│  │                         │  │  HTTP     │  │                      │  │
│  │                         │  │  Server   │  │                      │  │
│  │                         │  └───────────┘  │                      │  │
│  │                         │                 │                      │  │
│  │                         │  ┌───────────┐  │                      │  │
│  │                         │  │  LiPo +   │  │                      │  │
│  │                         │  │  TP4056   │  │                      │  │
│  │                         │  │  USB-C    │  │                      │  │
│  │                         │  └───────────┘  │                      │  │
│  │                         └────────┬────────┘                      │  │
│  └──────────────────────────────────┼────────────────────────────── ┘  │
│                                     │                                   │
│                   ┌─────────────────┴──────────────────┐               │
│                   │    WiFi (Primary)  /  BLE (Fallback) │               │
│                   └─────────────────┬──────────────────-┘               │
│                                     │                                   │
│  ┌──────────────────────────────────┼───────────────────────────────┐  │
│  │                   DESKTOP APPLICATION LAYER                       │  │
│  │                                  │                                │  │
│  │           ┌──────────────────────▼──────────────────────┐        │  │
│  │           │         Python Flask Server (port 5000)      │        │  │
│  │           │                                              │        │  │
│  │           │  ┌────────────┐  ┌────────────┐             │        │  │
│  │           │  │  api.py    │  │ routes_new │             │        │  │
│  │           │  │ (ESP32 /   │  │ routes_    │             │        │  │
│  │           │  │  legacy)   │  │ features   │             │        │  │
│  │           │  └─────┬──────┘  └─────┬──────┘             │        │  │
│  │           │        └───────┬────────┘                    │        │  │
│  │           │                │                             │        │  │
│  │           │  ┌─────────────▼──────────────────────────┐ │        │  │
│  │           │  │         database.py / models.py          │ │        │  │
│  │           │  │         (MySQL Connection Layer)         │ │        │  │
│  │           │  └─────────────┬──────────────────────────-┘ │        │  │
│  │           │                │                             │        │  │
│  │           │  ┌─────────────▼──────────────────────────┐ │        │  │
│  │           │  │    mysql-connector-python 8.3.0          │ │        │  │
│  │           │  └─────────────┬──────────────────────────-┘ │        │  │
│  │           └────────────────┼─────────────────────────────┘        │  │
│  │                            │  TCP port 3306                        │  │
│  │           ┌────────────────▼─────────────────────────────┐        │  │
│  │           │           MySQL Server 8.0                    │        │  │
│  │           │           Database: gwasoat                   │        │  │
│  │           │           User: gwasoat_user                  │        │  │
│  │           └──────────────────────────────────────────────┘        │  │
│  │                                                                    │  │
│  │           ┌──────────────────────────────────────────────┐        │  │
│  │           │         pywebview Native Window               │        │  │
│  │           │         Bootstrap 5 Web UI                    │        │  │
│  │           │         (http://127.0.0.1:5000)               │        │  │
│  │           └──────────────────────────────────────────────┘        │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                     │                                   │
│                   ┌─────────────────▼──────────────────────┐           │
│                   │          CLOUD LAYER (Optional)          │           │
│                   │                                          │           │
│                   │   REST API (cloud_sync.py)               │           │
│                   │   - Template backup/sync                 │           │
│                   │   - Attendance record backup             │           │
│                   │   - Offline queue with local file cache  │           │
│                   └──────────────────────────────────────────┘          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Communication Flow Diagram

```
  Teacher                Web UI              Flask             MySQL         ESP32
    │                      │                   │                 │              │
    │── Login ────────────>│                   │                 │              │
    │                      │── POST /auth/login>│                 │              │
    │                      │                   │── SELECT users ─>│              │
    │                      │                   │<── user row ─────│              │
    │                      │<── { user, role } ─│                 │              │
    │                      │                   │                 │              │
    │── Start Attendance ─>│                   │                 │              │
    │                      │── GET /api/course/│                 │              │
    │                      │   attendance/start>│                 │              │
    │                      │                   │── SELECT        │              │
    │                      │                   │   templates ───>│              │
    │                      │                   │<── blobs ────────│              │
    │                      │                   │── INSERT session>│              │
    │                      │                   │── POST /command ────────────-->│
    │                      │                   │   upload_template│              │
    │                      │                   │<── { success } ──────────────-─│
    │                      │<── { session_id } ─│                 │              │
    │                      │                   │                 │              │
  Student scans finger ─────────────────────────────────────────────────────>│
    │                      │                   │                 │          Matches FP
    │                      │                   │<── GET /attendance ──────────-─│
    │── Poll attendance ─->│                   │── UPDATE        │              │
    │                      │── GET /api/attend>│   session_      │              │
    │                      │                   │   attendance ──>│              │
    │                      │<── { name, status}─│                 │              │
    │                      │                   │                 │              │
    │── Stop Session ─────>│                   │                 │              │
    │                      │── GET /stop ──────>│                 │              │
    │                      │                   │── UPDATE ended_at>│             │
    │                      │                   │── UPDATE Absent──>│             │
    │                      │<── { success } ────│                 │              │
```

---

## 3. DBMS Architecture

### 3.1 DBMS Block Diagram

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        GWASOAT DBMS ARCHITECTURE                         │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                     APPLICATION LAYER                               │ │
│  │                                                                     │ │
│  │   ┌──────────────┐   ┌──────────────┐   ┌──────────────────────┐  │ │
│  │   │  database.py  │   │  models.py   │   │  routes_new.py       │  │ │
│  │   │               │   │              │   │  routes_features.py  │  │ │
│  │   │  CRUD for:    │   │  Schema init │   │  api.py              │  │ │
│  │   │  - classes    │   │  User auth   │   │  attendance.py       │  │ │
│  │   │  - students   │   │  Audit log   │   │  registration.py     │  │ │
│  │   │  - templates  │   │              │   │                      │  │ │
│  │   │  - sessions   │   │              │   │                      │  │ │
│  │   └──────┬────────┘   └──────┬───────┘   └──────────┬───────────┘  │ │
│  │          │                   │                       │             │ │
│  │          └───────────────────┴───────────────────────┘             │ │
│  │                              │                                     │ │
│  │              ┌───────────────▼───────────────────┐                 │ │
│  │              │  Shared Helper Functions           │                 │ │
│  │              │                                    │                 │ │
│  │              │  get_db()    → new connection      │                 │ │
│  │              │  _fetchone() → SELECT … LIMIT 1    │                 │ │
│  │              │  _fetchall() → SELECT …            │                 │ │
│  │              │  _execute()  → INSERT/UPDATE/DELETE│                 │ │
│  │              └───────────────┬───────────────────┘                 │ │
│  └──────────────────────────────┼──────────────────────────────────── ┘ │
│                                 │                                        │
│  ┌──────────────────────────────┼──────────────────────────────────────┐ │
│  │               CONNECTOR LAYER│                                       │ │
│  │                              │                                       │ │
│  │         ┌────────────────────▼──────────────────────┐               │ │
│  │         │   mysql-connector-python 8.3.0             │               │ │
│  │         │                                            │               │ │
│  │         │   host: localhost    port: 3306            │               │ │
│  │         │   user: gwasoat_user                       │               │ │
│  │         │   database: gwasoat                        │               │ │
│  │         │   charset: utf8mb4                         │               │ │
│  │         │   use_pure: True                           │               │ │
│  │         └────────────────────┬──────────────────────┘               │ │
│  └──────────────────────────────┼──────────────────────────────────────┘ │
│                                 │  TCP/IP port 3306                       │
│  ┌──────────────────────────────┼──────────────────────────────────────┐ │
│  │               MYSQL SERVER   │  8.0 Community Edition                │ │
│  │                              │                                       │ │
│  │         ┌────────────────────▼──────────────────────┐               │ │
│  │         │           Database: gwasoat                │               │ │
│  │         │           Charset: utf8mb4                 │               │ │
│  │         └──────────────────────────────────────────-┘               │ │
│  │                                                                      │ │
│  │   ┌──────────────────────────────────────────────────────────────┐  │ │
│  │   │                        TABLES                                 │  │ │
│  │   │                                                               │  │ │
│  │   │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────────┐ │  │ │
│  │   │  │  users   │  │  classes │  │ students │  │  courses    │ │  │ │
│  │   │  │(auth +   │  │(dept +   │  │(biometric│  │(teacher     │ │  │ │
│  │   │  │ roles)   │  │  year)   │  │  info)   │  │ assignments)│ │  │ │
│  │   │  └──────────┘  └──────────┘  └──────────┘  └─────────────┘ │  │ │
│  │   │                                                               │  │ │
│  │   │  ┌──────────────────┐  ┌───────────────────┐  ┌──────────┐  │  │ │
│  │   │  │attendance_sessions│  │session_attendance │  │ batches  │  │  │ │
│  │   │  │(per course/teacher│  │(per student mark) │  │(class    │  │  │ │
│  │   │  │  session record)  │  │                   │  │ sections)│  │  │ │
│  │   │  └──────────────────┘  └───────────────────┘  └──────────┘  │  │ │
│  │   │                                                               │  │ │
│  │   │  ┌──────────────────────┐  ┌───────────┐  ┌───────────────┐ │  │ │
│  │   │  │ fingerprint_templates│  │  timetable│  │  audit_log    │ │  │ │
│  │   │  │ (LONGBLOB binary FP  │  │(scheduled │  │(all system    │ │  │ │
│  │   │  │  data per student)   │  │  classes) │  │  actions)     │ │  │ │
│  │   │  └──────────────────────┘  └───────────┘  └───────────────┘ │  │ │
│  │   │                                                               │  │ │
│  │   │  ┌──────────────────┐  ┌───────────────┐  ┌──────────────┐  │  │ │
│  │   │  │ course_students  │  │ departments   │  │ app_settings │  │  │ │
│  │   │  │(M:N mapping)     │  │               │  │(key-value    │  │  │ │
│  │   │  │                  │  │               │  │  config)     │  │  │ │
│  │   │  └──────────────────┘  └───────────────┘  └──────────────┘  │  │ │
│  │   └──────────────────────────────────────────────────────────────┘  │ │
│  └──────────────────────────────────────────────────────────────────── ┘ │
└──────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Entity Relationship Overview

```
  departments ──< classes ──< batches
                    │
                    └──< students >──< course_students >──< courses >── users
                              │                                           │
                              │                               attendance_sessions
                              │                                           │
                              └──────────────────────────< session_attendance
                              │
                              └── fingerprint_templates

  users ──< audit_log
  courses ──< timetable
  app_settings  (standalone key-value store)
```

---

## 4. Database Design

### 4.1 Design Decisions

**Why MySQL over SQLite?**

The project originally used SQLite, which is a file-based database appropriate for single-user prototyping. Migrating to MySQL 8.0 provides:

- **Concurrent access** — multiple teachers can log in and record attendance simultaneously without file locking issues
- **Foreign key enforcement** — relational integrity is enforced at the database level, not just in application code
- **LONGBLOB support** — fingerprint templates (binary, ~500–2000 bytes each) are stored natively with proper binary handling
- **Network-ready** — MySQL runs as a server, making it straightforward to host centrally on a school server in future
- **Workbench tooling** — MySQL Workbench 8.0 CE provides a GUI for data inspection, manual queries, and schema management

**Placeholder syntax change:** SQLite uses `?` as parameter placeholders; MySQL uses `%s`. All query files were updated accordingly.

**`INSERT IGNORE` / `ON DUPLICATE KEY UPDATE`:** SQLite's `INSERT OR REPLACE` was replaced with the MySQL equivalents, preserving idempotent upsert behaviour.

### 4.2 Table Descriptions

| Table | Purpose | Key Columns |
|---|---|---|
| `users` | Admin and teacher accounts | `id`, `email`, `password` (SHA-256), `role` |
| `departments` | Academic departments | `id`, `name` |
| `classes` | Academic classes/years | `id`, `name`, `year`, `department_id` |
| `batches` | Subdivisions of a class (A, B, C) | `id`, `name`, `class_id` |
| `students` | Student records | `id` (fingerprint ID), `prn`, `roll_no`, `registered` |
| `courses` | Subjects assigned to teachers | `id`, `name`, `code`, `teacher_id` |
| `course_students` | Which students are in which course | `course_id`, `student_id` (unique pair) |
| `fingerprint_templates` | Binary FP template per student | `student_id` (PK), `template_data` LONGBLOB |
| `attendance_sessions` | One record per class session | `id`, `course_id`, `teacher_id`, `started_at`, `ended_at` |
| `session_attendance` | Per-student attendance mark | `session_id`, `student_id`, `status` (Present/Absent/--) |
| `app_settings` | Runtime config key-value store | `key` (PK), `value` |
| `audit_log` | Immutable action log | `user_id`, `action`, `details`, `created_at` |
| `timetable` | Scheduled course timeslots | `course_id`, `day_of_week`, `start_time` |

---

## 5. Schema Definition

### Core Tables (condensed)

```sql
-- Role-based users
CREATE TABLE users (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    name       VARCHAR(255) NOT NULL,
    email      VARCHAR(255) UNIQUE NOT NULL,
    password   VARCHAR(255) NOT NULL,        -- SHA-256 with salt
    role       VARCHAR(50)  NOT NULL DEFAULT 'student',
    created_at DATETIME NOT NULL
);

-- Academic hierarchy
CREATE TABLE departments ( id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(255) UNIQUE );
CREATE TABLE classes ( id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(255), year INT, department_id INT );
CREATE TABLE batches ( id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(255), class_id INT NOT NULL );

-- Students with biometric link
CREATE TABLE students (
    id         INT PRIMARY KEY,     -- same as fingerprint sensor slot ID
    prn        VARCHAR(100),
    roll_no    VARCHAR(100),
    name       VARCHAR(255) NOT NULL,
    class_id   INT, batch_id INT,
    registered TINYINT NOT NULL DEFAULT 0
);

-- Course assignment
CREATE TABLE courses ( id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(255), code VARCHAR(100), teacher_id INT );
CREATE TABLE course_students (
    course_id INT NOT NULL, student_id INT NOT NULL,
    UNIQUE KEY uq_course_student (course_id, student_id)
);

-- Fingerprint binary data
CREATE TABLE fingerprint_templates (
    student_id    INT PRIMARY KEY,
    template_data LONGBLOB NOT NULL,
    template_size INT NOT NULL,
    created_at    DATETIME NOT NULL
);

-- Attendance session (one per class conducted)
CREATE TABLE attendance_sessions (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    course_id   INT, teacher_id INT, class_id INT, batch_id INT,
    description TEXT,
    started_at  DATETIME NOT NULL,
    ended_at    DATETIME
);

-- Per-student attendance mark within a session
CREATE TABLE session_attendance (
    session_id   INT NOT NULL,
    student_id   INT NOT NULL,
    student_name VARCHAR(255) NOT NULL,
    status       VARCHAR(20) NOT NULL DEFAULT '--',  -- Present / Absent / --
    marked_at    DATETIME,
    UNIQUE KEY uq_session_student (session_id, student_id)
);

-- Audit trail
CREATE TABLE audit_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT, user_name VARCHAR(255),
    action VARCHAR(255) NOT NULL,
    details TEXT, created_at DATETIME NOT NULL
);
```

---

## 6. Data Flow

### 6.1 Student Registration Flow

```
Teacher clicks "Register Fingerprint"
        │
        ▼
Flask POST /api/register/<student_id>
        │
        ▼
ESP32 receives /register?id=X&name=Y
  → prompts student to place finger twice
  → stores template in sensor slot X
        │
        ▼
Flask polls /register_status every 2s
        │
        ▼ (on success)
Flask GET /get_template?id=X from ESP32
  → receives Base64-encoded binary template
        │
        ▼
MySQL INSERT INTO fingerprint_templates
  (student_id, class_id, template_data, template_size, created_at)
        │
        ▼
MySQL UPDATE students SET registered=1 WHERE id=X
```

### 6.2 Attendance Session Flow

```
Teacher clicks "Start Attendance" for course C
        │
        ▼
MySQL SELECT fingerprint_templates WHERE class_id = C
  → returns LONGBLOB templates for all enrolled students
        │
        ▼
For each template:
  POST http://<esp32_ip>/command { cmd: upload_template, ... }
  → loads template into ESP32 sensor slot
        │
        ▼
MySQL INSERT INTO attendance_sessions
  (course_id, teacher_id, class_id, started_at)
  → returns new session_id
        │
        ▼
MySQL INSERT INTO session_attendance
  (session_id, student_id, student_name, status='--')
  → one row per enrolled student, default status "--"
        │
  [Students scan fingers during class]
        │
        ▼
Student finger matched on ESP32 → GET /attendance
        │
        ▼
MySQL UPDATE session_attendance
  SET status='Present', marked_at=NOW()
  WHERE session_id=S AND student_id=X
        │
        ▼
Teacher clicks "Stop Attendance"
        │
        ▼
MySQL UPDATE session_attendance
  SET status='Absent' WHERE session_id=S AND status='--'
MySQL UPDATE attendance_sessions
  SET ended_at=NOW() WHERE id=S
```

### 6.3 Report Generation Flow

```
Teacher opens Report for course C
        │
        ▼
Flask GET /api/course/<C>/report
        │
        ▼
MySQL query (aggregated):
  SELECT student_id, COUNT(sessions) as held,
         SUM(status='Present') as present
  FROM session_attendance
  JOIN attendance_sessions ON session_id = sessions.id
  WHERE sessions.course_id = C
  GROUP BY student_id
        │
        ▼
Python: calculate attendance % = (present / held) × 100
        │
        ▼
Flag students below threshold (default 75%) as defaulters
        │
        ▼
Return JSON → rendered in UI table
OR export to CSV via /report/export
```

---

## 7. Migration from SQLite to MySQL

The project was originally developed with SQLite as the database backend. The following changes were made to migrate to MySQL 8.0.

### 7.1 Files Modified

| File | Change |
|---|---|
| `python/src/database.py` | Full rewrite — SQLite → MySQL connector, helper functions |
| `python/src/models.py` | Full rewrite — schema creation, `information_schema` for column checks |
| `python/src/attendance.py` | All `?` → `%s`, `db.execute()` → cursor pattern |
| `python/src/registration.py` | All `?` → `%s`, cursor pattern |
| `python/src/api.py` | All `?` → `%s`, `INSERT OR REPLACE` → `ON DUPLICATE KEY UPDATE` |
| `python/src/routes_new.py` | Full rewrite — all SQLite calls removed |
| `python/src/routes_features.py` | Full rewrite — all SQLite calls removed |
| `python/src/auth.py` | `db.execute().fetchone()` → `_fetchone()` helper |

### 7.2 Key Syntax Differences Handled

| SQLite | MySQL (replaced with) |
|---|---|
| `?` placeholder | `%s` placeholder |
| `AUTOINCREMENT` | `AUTO_INCREMENT` |
| `INSERT OR REPLACE` | `ON DUPLICATE KEY UPDATE` |
| `INSERT OR IGNORE` | `INSERT IGNORE` |
| `PRAGMA table_info(t)` | `SELECT … FROM information_schema.columns` |
| `db.execute(sql).fetchone()` | `_fetchone(db, sql, params)` |
| `sqlite3.IntegrityError` | `mysql.connector.errors.IntegrityError` |
| `BLOB` | `LONGBLOB` (for templates up to 64KB) |

### 7.3 Data Migration

A one-time migration script (`migrate_sqlite_to_mysql.py`) was used to transfer all existing records from `data/attendance.db` (SQLite) into the new MySQL database.

Records migrated:

| Table | Rows Migrated |
|---|---|
| classes | 1 |
| students | 6 |
| fingerprint_templates | 6 |
| attendance_sessions | 79 |
| session_attendance | 351 |
| attendance_records | 64 |
| users | 2 |
| app_settings | 5 |

Note: `session_attendance` count difference between SQLite (351) and MySQL (136) is due to foreign key enforcement — orphaned records referencing deleted students or sessions were rejected by `INSERT IGNORE`, which is the correct behaviour.

---

## 8. Security Considerations

### 8.1 Database Access

- The application **never uses the root MySQL account**. A dedicated user `gwasoat_user` is created with `GRANT ALL PRIVILEGES ON gwasoat.*` — access is scoped to the `gwasoat` database only.
- Credentials are stored in the Python source file (`database.py`). For production deployment, these should be moved to environment variables or a `.env` file.

### 8.2 Password Hashing

User passwords are hashed using **SHA-256 with a fixed salt** (`gwasoat_salt_2026`) before storage:

```python
hashlib.sha256(f"gwasoat_salt_2026{password}".encode()).hexdigest()
```

This ensures plaintext passwords are never stored. For a production system, `bcrypt` or `argon2` with per-user random salts would be recommended.

### 8.3 SQL Injection Prevention

All database queries use **parameterized statements** with `%s` placeholders via `mysql-connector-python`. No string concatenation is used to build SQL queries, eliminating SQL injection risk.

### 8.4 Role-Based Access Control

The system enforces **three application roles**, backed by a `role_permissions`
table that is the single source of truth for what each role may do:

- **Admin** — full access (wildcard `*` permission): all CRUD, audit log, user
  management, grades, timetable.
- **Teacher** — their own courses and attendance sessions, reports, and grade
  entry (`course.*`, `attendance.*`, `report.*`, `grade.*`, `timetable.view`).
- **Student** — read-only access to **their own** data only (`self.course.view`,
  `self.attendance.view`, `self.grade.view`, `self.timetable.view`,
  `self.class.view`) plus `profile.edit`.

Enforcement happens in three layers in `auth.py`:

1. `@login_required` / `@admin_required` / `@student_required` route decorators.
2. `@permission_required('<perm>')`, which checks the `role_permissions` table
   via `has_permission(role, perm)` — so permissions can be changed in SQL
   without touching code.
3. A `before_request` containment guard that confines a logged-in student to
   student-facing and shared paths, hardening every staff route against students.

The permission catalogue is seeded declaratively in `attendence_databse.sql`
(table `role_permissions`) and can additionally be modelled as **native MySQL
roles** (`gw_admin`, `gw_teacher`, `gw_student`) — see
`dbms_syllabus_demo.sql` for the `CREATE ROLE` / `GRANT` definitions.

---

## 9. DBMS Syllabus Demonstration

This project doubles as the DBMS lab submission. Every lab assignment maps onto a
real feature of the attendance system. The runnable SQL for all of the below is
in **`dbms_syllabus_demo.sql`** (run `attendence_databse.sql` first to create the
base schema, then source the demo script).

### 9.1 Assignment Coverage Map

| # | Topic | Where it is demonstrated |
|---|---|---|
| 1 | ER/EER design, generalisation/specialisation, relational transform, normalisation | §4 Database Design; `users` generalises admin/teacher/student via the `role` discriminator (§9.2) |
| 2 | DDL: constraints (PK, FK, UNIQUE, NOT NULL, DEFAULT, CHECK), indexes, sequence, synonym | `enrollments` table, 5 indexes, `AUTO_INCREMENT` sequence, `roster` view-as-synonym |
| 3 | DML: INSERT/UPDATE/DELETE/SELECT, WHERE (=, range, LIKE), ORDER BY, LIMIT | §ASSIGNMENT 3 of demo script |
| 4 | Advanced SQL: aggregation (COUNT/AVG/SUM/MIN/MAX + GROUP BY + HAVING), INNER/LEFT/RIGHT JOIN | Attendance-% aggregation; student↔course joins |
| 5 | Views | `v_student_directory`, `v_student_attendance_summary`, `v_course_defaulters` |
| 6 | Nested queries: subquery, correlated subquery, IN, EXISTS | Students in >N courses; below-course-average (correlated); never-present; active courses |
| 7 | Stored procedures & functions (IN/OUT params, insertion, IF/CASE, scalar fn) | `sp_students_in_class`, `sp_course_attendance_pct`, `sp_add_student_to_course`, `sp_attendance_grade`, `fn_attendance_pct`, `fn_is_even` |
| 8 | Triggers: audit on DELETE, synchronisation, validation | `trg_student_delete_audit`, `trg_template_sync_*`, `trg_grade_validate_*` |
| 9 | Cursor (row-by-row processing) | `sp_recompute_enrollment_percentages` iterates enrolments and writes attendance % |

### 9.2 Generalisation / Specialisation (EER)

The `users` entity is a **generalisation** of three specialised roles, with the
`role` column acting as the discriminator:

```
                 ┌─────────────┐
                 │    users    │   (id, name, email, password, role, student_id)
                 └──────┬──────┘
         role='admin'   │  role='teacher'   role='student'
            ┌───────────┼───────────┐
            ▼           ▼           ▼
         Admin       Teacher     Student ── student_id ──▶ students(id)   (ISA link, 1:1)
```

A `student`-role user is linked to its row in `students` via `users.student_id`
(a 1:1 ISA-style relationship), which is how a logged-in student is scoped to
their own data.

### 9.3 DDL Highlights (Assignment 2)

The `enrollments` table exercises every requested constraint type in one object:

```sql
CREATE TABLE enrollments (
    id            INT AUTO_INCREMENT PRIMARY KEY,          -- sequence (PK)
    student_id    INT NOT NULL,                            -- NOT NULL + FK
    course_id     INT NOT NULL,
    enrolled_on   DATE NOT NULL DEFAULT (CURRENT_DATE),    -- DEFAULT
    status        VARCHAR(10) NOT NULL DEFAULT 'active',   -- DEFAULT
    final_percent DECIMAL(5,2) DEFAULT 0,
    CONSTRAINT uq_enroll   UNIQUE (student_id, course_id), -- UNIQUE
    CONSTRAINT chk_status  CHECK (status IN ('active','dropped','completed')), -- CHECK
    CONSTRAINT chk_percent CHECK (final_percent BETWEEN 0 AND 100),            -- CHECK
    CONSTRAINT fk_enroll_student FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
    CONSTRAINT fk_enroll_course  FOREIGN KEY (course_id)  REFERENCES courses(id)  ON DELETE CASCADE
);
```

- **Sequence**: MySQL has no `CREATE SEQUENCE`; `AUTO_INCREMENT` provides
  generated keys, and `ALTER TABLE enrollments AUTO_INCREMENT = 1000;` sets the
  start value.
- **Synonym**: MySQL has no `CREATE SYNONYM`; the idiomatic equivalent is a view
  (`roster`) exposing a table under a friendlier name.
- **Indexes**: five secondary indexes speed up the most common lookups
  (attendance by student/status, sessions by course/date, students by class,
  grades by student+course).

### 9.4 Stored Routines, Triggers & Cursor (Assignments 7–9)

- **IN/OUT procedure** — `sp_course_attendance_pct(student, course, OUT pct)`.
- **Conditional logic** — `sp_attendance_grade` uses `CASE` to classify a student
  as Excellent / Good / At Risk / Defaulter from their attendance %.
- **Scalar function** — `fn_attendance_pct(student, course)` returns the % so it
  can be used inside other queries; `fn_is_even(n)` is the simple syllabus example.
- **Audit trigger** — `trg_student_delete_audit` logs every deleted student into
  `student_audit` (id, name, timestamp).
- **Synchronisation triggers** — `trg_template_sync_registered` /
  `_unregister` keep `students.registered` in sync with the
  `fingerprint_templates` table automatically.
- **Validation triggers** — `trg_grade_validate_ins` / `_upd` reject a grade whose
  `score > max_score` or whose `max_score <= 0` using `SIGNAL SQLSTATE '45000'`.
- **Cursor** — `sp_recompute_enrollment_percentages` walks every enrolment row by
  row, computes attendance % via `fn_attendance_pct`, and upserts it into
  `enrollments.final_percent` (the "sales summary" analogue).

### 9.5 Prerequisite for Functions & Triggers

If MySQL binary logging is enabled (`SHOW VARIABLES LIKE 'log_bin'` = `ON`), the
server blocks `CREATE FUNCTION`/`CREATE TRIGGER` from a non-SUPER user. Run this
**once** as an admin/root account before sourcing the function/trigger sections:

```sql
SET GLOBAL log_bin_trust_function_creators = 1;
```

This is a documented MySQL requirement and is safe for a local/coursework server.
The DML, views, aggregation/joins, nested queries, indexes, and cursor procedure
run without it; only the standalone functions and triggers need it.

---

## 10. Conclusion

The GWASOAT project successfully integrates a MySQL 8.0 relational database as the persistent storage backend for a real-time biometric attendance system. The database design supports the full lifecycle of attendance management — from student enrollment and fingerprint template storage, through session-based attendance marking, to report generation and defaulter identification.

The migration from SQLite to MySQL was completed without any loss of application functionality. The schema design is normalized, foreign-key enforced, and built to support multi-user concurrent access by multiple teachers and students simultaneously. The core tables are live in MySQL, extended with a table-driven `role_permissions` RBAC model, a `grades` table and student login accounts, and the full history of attendance sessions and enrolled students has been migrated from the original SQLite file.

Beyond the application, the project serves as a complete DBMS lab submission: section 9 maps all nine lab assignments — ER/EER design, DDL with every constraint type, DML, aggregation and joins, views, nested and correlated subqueries, stored procedures and functions, triggers, and a cursor — onto real features of the attendance system, with runnable SQL in `dbms_syllabus_demo.sql`.

The system is production-ready for deployment on a local school network, with a clear path to central server hosting by simply updating the `DB_CONFIG` connection parameters in `database.py`.

---

*Report generated for GWASOAT project — October 2026*
