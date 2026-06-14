"""
Database models and schema for GWASOAT multi-user system.
Handles migration from old single-user schema to new role-based schema.
"""

import sqlite3
import hashlib
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'attendance.db')


def get_db():
    """Get database connection."""
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def hash_password(password):
    """Hash password with salt using SHA-256."""
    salt = "gwasoat_salt_2026"
    return hashlib.sha256(f"{salt}{password}".encode()).hexdigest()


def initialize_new_schema():
    """Create all tables for the multi-user system."""
    db = get_db()

    # Users (admin + teachers)
    db.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'teacher',
        created_at TEXT NOT NULL
    )''')

    # Departments
    db.execute('''CREATE TABLE IF NOT EXISTS departments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL
    )''')

    # Classes
    db.execute('''CREATE TABLE IF NOT EXISTS classes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        year INTEGER,
        department_id INTEGER,
        FOREIGN KEY (department_id) REFERENCES departments(id)
    )''')

    # Batches (subdivisions of a class)
    db.execute('''CREATE TABLE IF NOT EXISTS batches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        class_id INTEGER NOT NULL,
        FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE
    )''')

    # Students
    db.execute('''CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY,
        prn TEXT,
        roll_no TEXT,
        name TEXT NOT NULL,
        class_id INTEGER,
        batch_id INTEGER,
        registered INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (class_id) REFERENCES classes(id),
        FOREIGN KEY (batch_id) REFERENCES batches(id)
    )''')

    # Courses (assigned to a teacher, has custom student list)
    db.execute('''CREATE TABLE IF NOT EXISTS courses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        code TEXT,
        teacher_id INTEGER,
        FOREIGN KEY (teacher_id) REFERENCES users(id)
    )''')

    # Course-Student mapping (many-to-many)
    db.execute('''CREATE TABLE IF NOT EXISTS course_students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        course_id INTEGER NOT NULL,
        student_id INTEGER NOT NULL,
        UNIQUE(course_id, student_id),
        FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
    )''')

    # Fingerprint templates
    db.execute('''CREATE TABLE IF NOT EXISTS fingerprint_templates (
        student_id INTEGER PRIMARY KEY,
        class_id INTEGER,
        template_data BLOB NOT NULL,
        template_size INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (student_id) REFERENCES students(id)
    )''')

    # Attendance sessions
    db.execute('''CREATE TABLE IF NOT EXISTS attendance_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        course_id INTEGER,
        teacher_id INTEGER,
        class_id INTEGER,
        batch_id INTEGER,
        started_at TEXT NOT NULL,
        ended_at TEXT,
        FOREIGN KEY (course_id) REFERENCES courses(id),
        FOREIGN KEY (teacher_id) REFERENCES users(id),
        FOREIGN KEY (class_id) REFERENCES classes(id)
    )''')

    # Session attendance records
    db.execute('''CREATE TABLE IF NOT EXISTS session_attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL,
        student_id INTEGER NOT NULL,
        student_name TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT '--',
        marked_at TEXT,
        UNIQUE(session_id, student_id),
        FOREIGN KEY (session_id) REFERENCES attendance_sessions(id) ON DELETE CASCADE,
        FOREIGN KEY (student_id) REFERENCES students(id)
    )''')

    # App settings
    db.execute('''CREATE TABLE IF NOT EXISTS app_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )''')

    # Seed default admin user if no users exist
    existing = db.execute("SELECT COUNT(*) as c FROM users").fetchone()['c']
    if existing == 0:
        db.execute(
            "INSERT INTO users (name, email, password, role, created_at) VALUES (?, ?, ?, ?, ?)",
            ("Admin", "admin@gwasoat.local", hash_password("admin123"), "admin",
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        print("[DB] Default admin created: admin@gwasoat.local / admin123")

    # Migrate existing tables - add missing columns
    def add_col(table, col, definition):
        try:
            db.execute(f"SELECT {col} FROM {table} LIMIT 1")
        except sqlite3.OperationalError:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {definition}")
            print(f"[DB] Added column {table}.{col}")

    add_col("classes", "year", "INTEGER")
    add_col("classes", "department_id", "INTEGER")
    add_col("students", "prn", "TEXT")
    add_col("students", "roll_no", "TEXT")
    add_col("students", "batch_id", "INTEGER")

    db.commit()
    db.close()
    print("[DB] Schema initialized")
