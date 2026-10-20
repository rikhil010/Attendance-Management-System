"""
Database models and schema for GWASOAT multi-user system — MySQL backend.
Handles schema creation and migration for the role-based system.
"""

import hashlib
from datetime import datetime
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
    """Get a MySQL database connection with dictionary cursor support."""
    return mysql.connector.connect(**DB_CONFIG)


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


def hash_password(password):
    """Hash password with salt using SHA-256."""
    salt = "gwasoat_salt_2026"
    return hashlib.sha256(f"{salt}{password}".encode()).hexdigest()


def _column_exists(db, table, column):
    """Check if a column exists in a table."""
    row = _fetchone(db,
        "SELECT COUNT(*) AS cnt FROM information_schema.columns "
        "WHERE table_schema = %s AND table_name = %s AND column_name = %s",
        ('gwasoat', table, column))
    return row and row['cnt'] > 0


def initialize_new_schema():
    """Create all tables for the multi-user system."""
    db = get_db()

    # Users (admin + teachers + students)
    # student_id links a user account to a row in the students table (NULL for admin/teacher)
    _execute(db, '''CREATE TABLE IF NOT EXISTS users (
        id         INT AUTO_INCREMENT PRIMARY KEY,
        name       VARCHAR(255) NOT NULL,
        email      VARCHAR(255) UNIQUE NOT NULL,
        password   VARCHAR(255) NOT NULL,
        role       VARCHAR(50) NOT NULL DEFAULT 'student',
        student_id INT,
        created_at DATETIME NOT NULL
    )''')

    # Role → permission mapping (role-based access control)
    _execute(db, '''CREATE TABLE IF NOT EXISTS role_permissions (
        role       VARCHAR(50) NOT NULL,
        permission VARCHAR(100) NOT NULL,
        PRIMARY KEY (role, permission)
    )''')

    # Departments
    _execute(db, '''CREATE TABLE IF NOT EXISTS departments (
        id   INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(255) UNIQUE NOT NULL
    )''')

    # Classes
    _execute(db, '''CREATE TABLE IF NOT EXISTS classes (
        id            INT AUTO_INCREMENT PRIMARY KEY,
        name          VARCHAR(255) NOT NULL,
        year          INT,
        department_id INT,
        FOREIGN KEY (department_id) REFERENCES departments(id)
    )''')

    # Batches (subdivisions of a class)
    _execute(db, '''CREATE TABLE IF NOT EXISTS batches (
        id       INT AUTO_INCREMENT PRIMARY KEY,
        name     VARCHAR(255) NOT NULL,
        class_id INT NOT NULL,
        FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE
    )''')

    # Students
    _execute(db, '''CREATE TABLE IF NOT EXISTS students (
        id         INT PRIMARY KEY,
        prn        VARCHAR(100),
        roll_no    VARCHAR(100),
        name       VARCHAR(255) NOT NULL,
        class_id   INT,
        batch_id   INT,
        registered TINYINT NOT NULL DEFAULT 0,
        FOREIGN KEY (class_id) REFERENCES classes(id),
        FOREIGN KEY (batch_id) REFERENCES batches(id)
    )''')

    # Courses (assigned to a teacher, has custom student list)
    _execute(db, '''CREATE TABLE IF NOT EXISTS courses (
        id         INT AUTO_INCREMENT PRIMARY KEY,
        name       VARCHAR(255) NOT NULL,
        code       VARCHAR(100),
        teacher_id INT,
        FOREIGN KEY (teacher_id) REFERENCES users(id)
    )''')

    # Course-Student mapping (many-to-many)
    _execute(db, '''CREATE TABLE IF NOT EXISTS course_students (
        id         INT AUTO_INCREMENT PRIMARY KEY,
        course_id  INT NOT NULL,
        student_id INT NOT NULL,
        UNIQUE KEY uq_course_student (course_id, student_id),
        FOREIGN KEY (course_id)  REFERENCES courses(id)  ON DELETE CASCADE,
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
    )''')

    # Fingerprint templates
    _execute(db, '''CREATE TABLE IF NOT EXISTS fingerprint_templates (
        student_id    INT PRIMARY KEY,
        class_id      INT,
        template_data LONGBLOB NOT NULL,
        template_size INT NOT NULL,
        created_at    DATETIME NOT NULL,
        FOREIGN KEY (student_id) REFERENCES students(id)
    )''')

    # Attendance sessions
    _execute(db, '''CREATE TABLE IF NOT EXISTS attendance_sessions (
        id          INT AUTO_INCREMENT PRIMARY KEY,
        course_id   INT,
        teacher_id  INT,
        class_id    INT,
        batch_id    INT,
        description TEXT,
        started_at  DATETIME NOT NULL,
        ended_at    DATETIME,
        FOREIGN KEY (course_id)  REFERENCES courses(id),
        FOREIGN KEY (teacher_id) REFERENCES users(id),
        FOREIGN KEY (class_id)   REFERENCES classes(id)
    )''')

    # Session attendance records
    _execute(db, '''CREATE TABLE IF NOT EXISTS session_attendance (
        id           INT AUTO_INCREMENT PRIMARY KEY,
        session_id   INT NOT NULL,
        student_id   INT NOT NULL,
        student_name VARCHAR(255) NOT NULL,
        status       VARCHAR(20) NOT NULL DEFAULT '--',
        marked_at    DATETIME,
        UNIQUE KEY uq_session_student (session_id, student_id),
        FOREIGN KEY (session_id) REFERENCES attendance_sessions(id) ON DELETE CASCADE,
        FOREIGN KEY (student_id) REFERENCES students(id)
    )''')

    # App settings
    _execute(db, '''CREATE TABLE IF NOT EXISTS app_settings (
        `key` VARCHAR(255) PRIMARY KEY,
        value TEXT NOT NULL
    )''')

    # Audit log
    _execute(db, '''CREATE TABLE IF NOT EXISTS audit_log (
        id         INT AUTO_INCREMENT PRIMARY KEY,
        user_id    INT,
        user_name  VARCHAR(255),
        action     VARCHAR(255) NOT NULL,
        details    TEXT,
        created_at DATETIME NOT NULL
    )''')

    # Timetable
    _execute(db, '''CREATE TABLE IF NOT EXISTS timetable (
        id          INT AUTO_INCREMENT PRIMARY KEY,
        course_id   INT NOT NULL,
        day_of_week INT NOT NULL,
        start_time  VARCHAR(10) NOT NULL,
        end_time    VARCHAR(10),
        room        VARCHAR(100),
        FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE
    )''')

    # Grades (per student, per course) — students can view, teachers/admin can edit
    _execute(db, '''CREATE TABLE IF NOT EXISTS grades (
        id          INT AUTO_INCREMENT PRIMARY KEY,
        student_id  INT NOT NULL,
        course_id   INT NOT NULL,
        component   VARCHAR(100) NOT NULL,
        score       DECIMAL(6,2),
        max_score   DECIMAL(6,2) NOT NULL DEFAULT 100,
        grade       VARCHAR(10),
        remarks     TEXT,
        updated_by  INT,
        updated_at  DATETIME NOT NULL,
        UNIQUE KEY uq_student_course_component (student_id, course_id, component),
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
        FOREIGN KEY (course_id)  REFERENCES courses(id)  ON DELETE CASCADE
    )''')

    # Seed default admin if no users exist
    count_row = _fetchone(db, "SELECT COUNT(*) AS c FROM users")
    if count_row and count_row['c'] == 0:
        _execute(db,
            "INSERT INTO users (name, email, password, role, created_at) "
            "VALUES (%s, %s, %s, %s, %s)",
            ("Admin", "admin@gwasoat.local", hash_password("admin123"), "admin",
             datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        print("[DB] Default admin created: admin@gwasoat.local / admin123")

    # Migration: add missing columns to existing tables
    def add_col(table, col, definition):
        if not _column_exists(db, table, col):
            _execute(db, f"ALTER TABLE {table} ADD COLUMN {col} {definition}")
            print(f"[DB] Added column {table}.{col}")

    add_col("classes",            "year",          "INT")
    add_col("classes",            "department_id", "INT")
    add_col("students",           "prn",           "VARCHAR(100)")
    add_col("students",           "roll_no",       "VARCHAR(100)")
    add_col("students",           "batch_id",      "INT")
    add_col("attendance_sessions","course_id",     "INT")
    add_col("attendance_sessions","teacher_id",    "INT")
    add_col("attendance_sessions","class_id",      "INT")
    add_col("attendance_sessions","batch_id",      "INT")
    add_col("attendance_sessions","description",   "TEXT")
    add_col("users",              "student_id",    "INT")

    # Seed role → permission mapping (idempotent)
    _seed_permissions(db)

    # Backfill: ensure every existing student has a login account
    _backfill_student_accounts(db)

    db.commit()
    db.close()
    print("[DB] Schema initialized")


def _backfill_student_accounts(db):
    """Create student login accounts for any students that don't have one yet."""
    try:
        rows = _fetchall_local(db, '''
            SELECT s.id, s.name FROM students s
            LEFT JOIN users u ON u.role='student' AND u.student_id = s.id
            WHERE u.id IS NULL
        ''')
        created = 0
        for r in rows:
            ensure_student_account(db, r['id'], r['name'])
            created += 1
        if created:
            print(f"[DB] Created {created} student login account(s)")
    except Exception as e:
        print(f"[DB] Student backfill skipped: {e}")


def _fetchall_local(db, sql, params=()):
    cur = db.cursor(dictionary=True)
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    return rows


# ─── Role-Based Access Control ───────────────────────────────────────────────

# Permission catalogue. Admin implicitly has ALL permissions (see has_permission).
ROLE_PERMISSIONS = {
    'admin': ['*'],  # wildcard — full access
    'teacher': [
        'course.view', 'course.manage_students', 'attendance.run',
        'attendance.mark', 'report.view', 'report.export',
        'grade.view', 'grade.edit', 'timetable.view', 'profile.edit',
    ],
    'student': [
        'self.course.view', 'self.attendance.view', 'self.grade.view',
        'self.timetable.view', 'self.class.view', 'profile.edit',
    ],
}


def _seed_permissions(db):
    """Populate role_permissions table from ROLE_PERMISSIONS (idempotent)."""
    for role, perms in ROLE_PERMISSIONS.items():
        for perm in perms:
            try:
                _execute(db,
                    "INSERT IGNORE INTO role_permissions (role, permission) VALUES (%s, %s)",
                    (role, perm))
            except Exception:
                pass


def get_role_permissions(role):
    """
    Return the set of permissions granted to a role.

    Source of truth is the role_permissions table in the database, so the
    permission model can be managed from SQL. If the table is empty or the
    DB is unreachable, fall back to the ROLE_PERMISSIONS defaults in code.
    """
    try:
        db = get_db()
        rows = _fetchall_local(db,
            "SELECT permission FROM role_permissions WHERE role = %s", (role,))
        db.close()
        perms = {r['permission'] for r in rows}
        if perms:
            return perms
    except Exception:
        pass
    # Fallback to code defaults (also used before the table is seeded)
    return set(ROLE_PERMISSIONS.get(role, []))


def has_permission(role, permission):
    """True if the given role is allowed the given permission. '*' means all."""
    perms = get_role_permissions(role)
    return '*' in perms or permission in perms


def ensure_student_account(db, student_id, name, email=None, password=None):
    """
    Create (or return existing) login account for a student.
    Default email: student<ID>@gwasoat.local, default password: student<ID>.
    Returns the users.id of the student account.
    """
    existing = _fetchone(db,
        "SELECT id FROM users WHERE role='student' AND student_id=%s", (student_id,))
    if existing:
        return existing['id']

    email = email or f"student{student_id}@gwasoat.local"
    raw_pw = password or f"student{student_id}"

    # Avoid email collision
    clash = _fetchone(db, "SELECT id FROM users WHERE email=%s", (email,))
    if clash:
        email = f"student{student_id}.{datetime.now().strftime('%H%M%S')}@gwasoat.local"

    uid = _execute(db,
        "INSERT INTO users (name, email, password, role, student_id, created_at) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (name, email, hash_password(raw_pw), 'student', student_id,
         datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    return uid


def log_action(user, action, details=''):
    """Record an entry in the audit log."""
    try:
        db = get_db()
        _execute(db,
            "INSERT INTO audit_log (user_id, user_name, action, details, created_at) "
            "VALUES (%s, %s, %s, %s, %s)",
            (
                user['id']   if user else None,
                user['name'] if user else 'system',
                action,
                details,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ))
        db.commit()
        db.close()
    except Exception:
        pass
