"""
Database module for GWASOAT.
Handles all database operations and initialization.
"""

import sqlite3


def get_db():
    """Get database connection with row factory."""
    import os
    db_path = os.path.join(os.path.dirname(__file__), '../../data/attendance.db')
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    return db


def ensure_column(db, table_name, column_name, definition):
    """Add column to table if it doesn't exist."""
    cursor = db.execute(f"PRAGMA table_info({table_name})")
    cols = [row[1] for row in cursor.fetchall()]
    if column_name not in cols:
        db.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def initialize_database():
    """Initialize database schema."""
    db = get_db()
    
    # Create tables
    db.execute('''CREATE TABLE IF NOT EXISTS classes (
                    id INTEGER PRIMARY KEY,
                    name TEXT UNIQUE)''')
    
    db.execute('''CREATE TABLE IF NOT EXISTS students (
                    id INTEGER PRIMARY KEY,
                    name TEXT,
                    class_id INTEGER,
                    registered INTEGER NOT NULL DEFAULT 0)''')
    
    db.execute('''CREATE TABLE IF NOT EXISTS attendance_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER,
                    class_id INTEGER NOT NULL,
                    student_id INTEGER NOT NULL,
                    student_name TEXT NOT NULL,
                    fingerprint_time TEXT,
                    recorded_at TEXT NOT NULL)''')
    
    db.execute('''CREATE TABLE IF NOT EXISTS attendance_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    class_id INTEGER NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT)''')
    
    db.execute('''CREATE TABLE IF NOT EXISTS session_attendance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    class_id INTEGER NOT NULL,
                    student_id INTEGER NOT NULL,
                    student_name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT '--',
                    marked_at TEXT,
                    UNIQUE(session_id, student_id))''')
    
    db.execute('''CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL)''')
    
    # Add missing columns
    ensure_column(db, "students", "class_id", "INTEGER")
    ensure_column(db, "students", "registered", "INTEGER NOT NULL DEFAULT 0")
    ensure_column(db, "attendance_records", "session_id", "INTEGER")
    
    db.commit()
    db.close()


def get_classes():
    """Get all classes."""
    db = get_db()
    cursor = db.execute("SELECT * FROM classes ORDER BY id")
    classes = [dict(row) for row in cursor]
    db.close()
    return classes


def add_class(name):
    """Add a new class."""
    db = get_db()
    try:
        db.execute("INSERT INTO classes (name) VALUES (?)", (name,))
        db.commit()
        db.close()
        return {'status': 'success'}
    except sqlite3.IntegrityError:
        db.close()
        return {'status': 'error', 'message': 'Class name already exists'}


def update_class(class_id, name):
    """Update class name."""
    db = get_db()
    try:
        db.execute("UPDATE classes SET name = ? WHERE id = ?", (name, class_id))
        db.commit()
        db.close()
        return {'status': 'success'}
    except sqlite3.IntegrityError:
        db.close()
        return {'status': 'error', 'message': 'Class name already exists'}


def delete_class(class_id):
    """Delete class and associated data."""
    db = get_db()
    db.execute("DELETE FROM session_attendance WHERE class_id = ?", (class_id,))
    db.execute("DELETE FROM attendance_records WHERE class_id = ?", (class_id,))
    db.execute("DELETE FROM attendance_sessions WHERE class_id = ?", (class_id,))
    db.execute("DELETE FROM classes WHERE id = ?", (class_id,))
    db.commit()
    db.close()
    return {'status': 'success'}


def get_students(class_id=None):
    """Get students, optionally filtered by class."""
    db = get_db()
    if class_id is None:
        cursor = db.execute("SELECT * FROM students ORDER BY id")
    else:
        cursor = db.execute(
            "SELECT * FROM students WHERE class_id = ? ORDER BY id",
            (class_id,)
        )
    students = [dict(row) for row in cursor]
    db.close()
    return students


def add_student(student_id, name, class_id):
    """Add a new student."""
    db = get_db()
    try:
        db.execute(
            "INSERT INTO students (id, name, class_id) VALUES (?, ?, ?)",
            (student_id, name, class_id)
        )
        db.commit()
        db.close()
        return {'status': 'success'}
    except sqlite3.IntegrityError:
        db.close()
        return {'status': 'error', 'message': 'Student ID already exists'}


def update_student(old_id, new_id, name):
    """Update student information."""
    db = get_db()
    try:
        db.execute(
            "UPDATE students SET name = ?, id = ? WHERE id = ?",
            (name, new_id, old_id)
        )
        db.commit()
        db.close()
        return {'status': 'success'}
    except sqlite3.IntegrityError:
        db.close()
        return {'status': 'error', 'message': 'Student ID already exists'}


def delete_student(student_id):
    """Delete student."""
    db = get_db()
    db.execute("DELETE FROM students WHERE id = ?", (student_id,))
    db.commit()
    db.close()
    return {'status': 'success'}
