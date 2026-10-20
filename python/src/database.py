"""
Database module for GWASOAT — MySQL backend.
Handles all database operations and initialization.
"""

import mysql.connector
from mysql.connector import IntegrityError

DB_CONFIG = {
    'host':     'localhost',
    'port':     3306,
    'database': 'gwasoat',
    'user':     'gwasoat_user',
    'password': 'gwasoat_pass_2026',
    'charset':  'utf8mb4',
    'use_pure': True,
}


def get_db():
    """Return a new MySQL connection."""
    return mysql.connector.connect(**DB_CONFIG)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _fetchall(db, sql, params=()):
    cur = db.cursor(dictionary=True)
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    return rows


def _fetchone(db, sql, params=()):
    cur = db.cursor(dictionary=True)
    cur.execute(sql, params)
    row = cur.fetchone()
    cur.close()
    return row


def _execute(db, sql, params=()):
    cur = db.cursor()
    cur.execute(sql, params)
    lastrowid = cur.lastrowid
    cur.close()
    return lastrowid


# ── Schema init (legacy — main schema lives in models.py) ────────────────────

def initialize_database():
    """Ensure legacy tables exist. Main schema is handled by models.py."""
    db = get_db()

    _execute(db, '''CREATE TABLE IF NOT EXISTS classes (
        id   INT PRIMARY KEY,
        name VARCHAR(255) UNIQUE NOT NULL
    )''')

    _execute(db, '''CREATE TABLE IF NOT EXISTS students (
        id         INT PRIMARY KEY,
        name       VARCHAR(255),
        class_id   INT,
        registered TINYINT NOT NULL DEFAULT 0
    )''')

    _execute(db, '''CREATE TABLE IF NOT EXISTS attendance_sessions (
        id         INT AUTO_INCREMENT PRIMARY KEY,
        class_id   INT NOT NULL,
        started_at DATETIME NOT NULL,
        ended_at   DATETIME
    )''')

    _execute(db, '''CREATE TABLE IF NOT EXISTS attendance_records (
        id               INT AUTO_INCREMENT PRIMARY KEY,
        session_id       INT,
        class_id         INT NOT NULL,
        student_id       INT NOT NULL,
        student_name     VARCHAR(255) NOT NULL,
        fingerprint_time DATETIME,
        recorded_at      DATETIME NOT NULL
    )''')

    _execute(db, '''CREATE TABLE IF NOT EXISTS session_attendance (
        id           INT AUTO_INCREMENT PRIMARY KEY,
        session_id   INT NOT NULL,
        class_id     INT NOT NULL,
        student_id   INT NOT NULL,
        student_name VARCHAR(255) NOT NULL,
        status       VARCHAR(20) NOT NULL DEFAULT '--',
        marked_at    DATETIME,
        UNIQUE KEY uq_session_student (session_id, student_id)
    )''')

    _execute(db, '''CREATE TABLE IF NOT EXISTS app_settings (
        `key` VARCHAR(255) PRIMARY KEY,
        value TEXT NOT NULL
    )''')

    _execute(db, '''CREATE TABLE IF NOT EXISTS fingerprint_templates (
        student_id    INT PRIMARY KEY,
        class_id      INT NOT NULL,
        template_data LONGBLOB NOT NULL,
        template_size INT NOT NULL,
        created_at    DATETIME NOT NULL
    )''')

    db.commit()
    db.close()


# ── Classes ───────────────────────────────────────────────────────────────────

def get_classes():
    """Get all classes."""
    db = get_db()
    rows = _fetchall(db, "SELECT * FROM classes ORDER BY id")
    db.close()
    return rows


def add_class(name):
    """Add a new class."""
    db = get_db()
    try:
        _execute(db, "INSERT INTO classes (name) VALUES (%s)", (name,))
        db.commit()
        db.close()
        return {'status': 'success'}
    except IntegrityError:
        db.close()
        return {'status': 'error', 'message': 'Class name already exists'}


def update_class(class_id, name):
    """Update class name."""
    db = get_db()
    try:
        _execute(db, "UPDATE classes SET name = %s WHERE id = %s", (name, class_id))
        db.commit()
        db.close()
        return {'status': 'success'}
    except IntegrityError:
        db.close()
        return {'status': 'error', 'message': 'Class name already exists'}


def delete_class(class_id):
    """Delete class and all associated data."""
    db = get_db()
    _execute(db, "DELETE FROM session_attendance WHERE class_id = %s", (class_id,))
    _execute(db, "DELETE FROM attendance_records WHERE class_id = %s", (class_id,))
    _execute(db, "DELETE FROM attendance_sessions WHERE class_id = %s", (class_id,))
    _execute(db, "DELETE FROM classes WHERE id = %s", (class_id,))
    db.commit()
    db.close()
    return {'status': 'success'}


# ── Students ──────────────────────────────────────────────────────────────────

def get_students(class_id=None):
    """Get students, optionally filtered by class."""
    db = get_db()
    if class_id is None:
        rows = _fetchall(db, "SELECT * FROM students ORDER BY id")
    else:
        rows = _fetchall(db,
            "SELECT * FROM students WHERE class_id = %s ORDER BY id",
            (class_id,))
    db.close()
    return rows


def add_student(student_id, name, class_id):
    """Add a new student."""
    db = get_db()
    try:
        _execute(db,
            "INSERT INTO students (id, name, class_id) VALUES (%s, %s, %s)",
            (student_id, name, class_id))
        db.commit()
        db.close()
        return {'status': 'success'}
    except IntegrityError:
        db.close()
        return {'status': 'error', 'message': 'Student ID already exists'}


def update_student(old_id, new_id, name):
    """Update student information."""
    db = get_db()
    try:
        _execute(db,
            "UPDATE students SET name = %s, id = %s WHERE id = %s",
            (name, new_id, old_id))
        db.commit()
        db.close()
        return {'status': 'success'}
    except IntegrityError:
        db.close()
        return {'status': 'error', 'message': 'Student ID already exists'}


def delete_student(student_id):
    """Delete a student."""
    db = get_db()
    _execute(db, "DELETE FROM students WHERE id = %s", (student_id,))
    db.commit()
    db.close()
    return {'status': 'success'}
