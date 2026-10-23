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
        created_at DATETIME NOT NULL,
        CONSTRAINT chk_user_role CHECK (role COLLATE utf8mb4_bin IN ('admin', 'teacher', 'student'))
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

    # Create DBMS feature objects (views, triggers, procedures) and seed settings
    _apply_dbms_features(db)

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
        'attendance.mark', 'report.view', 'report.export', 'report.defaulters',
        'grade.view', 'grade.edit', 'timetable.view', 'profile.edit',
    ],
    'student': [
        'self.course.view', 'self.attendance.view', 'self.grade.view',
        'self.timetable.view', 'self.class.view', 'profile.edit',
    ],
}


def _apply_dbms_features(db):
    """Create/refresh the DBMS feature objects (idempotent).

    Mirrors dbms/002_dbms_features.sql so the features work whether or not
    the migration file was run by hand. Safe to call on every startup.

    Feature 1: v_attendance_summary view + defaulter_threshold setting.
    """
    try:
        # Attendance summary view (per student, per course). Counts status='Present'.
        _execute(db, "DROP VIEW IF EXISTS v_attendance_summary")
        _execute(db, '''
            CREATE VIEW v_attendance_summary AS
            SELECT
                cs.course_id   AS course_id,
                c.name         AS course_name,
                c.code         AS course_code,
                s.id           AS student_id,
                s.name         AS student_name,
                s.roll_no      AS roll_no,
                s.prn          AS prn,
                COUNT(DISTINCT ses.id) AS total_sessions,
                COUNT(DISTINCT CASE WHEN sa.status='Present' THEN ses.id END) AS present,
                CASE WHEN COUNT(DISTINCT ses.id)=0 THEN 0.0
                     ELSE ROUND(COUNT(DISTINCT CASE WHEN sa.status='Present' THEN ses.id END)
                                / COUNT(DISTINCT ses.id) * 100, 1)
                END AS percentage
            FROM course_students cs
            JOIN students s ON s.id = cs.student_id
            JOIN courses  c ON c.id = cs.course_id
            LEFT JOIN attendance_sessions ses ON ses.course_id = cs.course_id
            LEFT JOIN session_attendance  sa  ON sa.session_id = ses.id
                                              AND sa.student_id = cs.student_id
            GROUP BY cs.course_id, c.name, c.code, s.id, s.name, s.roll_no, s.prn
        ''')

        # Configurable defaulter threshold (keep existing value if already set).
        _execute(db,
            "INSERT INTO app_settings (`key`, value) VALUES ('defaulter_threshold', '75') "
            "ON DUPLICATE KEY UPDATE value = value")
        print("[DB] DBMS features applied (v_attendance_summary)")
    except Exception as e:
        print(f"[DB] DBMS view/setting apply skipped: {e}")

    # Feature 2: grade audit triggers (AFTER INSERT / AFTER UPDATE on grades).
    # Kept in its OWN try-block: creating triggers needs either SUPER or the
    # server flag log_bin_trust_function_creators=1 when binary logging is on.
    # If that is not set, trigger creation fails with MySQL error 1419 — we log
    # a clear hint and continue (the app still works; grade changes just are not
    # auto-audited until the triggers are installed via the migration as root).
    try:
        _execute(db, "DROP TRIGGER IF EXISTS trg_grades_audit_insert")
        _execute(db, "DROP TRIGGER IF EXISTS trg_grades_audit")
        _execute(db, '''
            CREATE TRIGGER trg_grades_audit_insert
            AFTER INSERT ON grades
            FOR EACH ROW
            BEGIN
                DECLARE v_user_name VARCHAR(255);
                SELECT name INTO v_user_name FROM users WHERE id = NEW.updated_by;
                INSERT INTO audit_log (user_id, user_name, action, details, created_at)
                VALUES (NEW.updated_by, COALESCE(v_user_name, 'system'), 'GRADE_INSERT',
                        CONCAT('student ', NEW.student_id, ', course ', NEW.course_id,
                               ', component ', NEW.component,
                               ': set ', COALESCE(CAST(NEW.score AS CHAR), 'NULL'),
                               '/', NEW.max_score),
                        NOW());
            END
        ''')
        _execute(db, '''
            CREATE TRIGGER trg_grades_audit
            AFTER UPDATE ON grades
            FOR EACH ROW
            BEGIN
                DECLARE v_user_name VARCHAR(255);
                SELECT name INTO v_user_name FROM users WHERE id = NEW.updated_by;
                INSERT INTO audit_log (user_id, user_name, action, details, created_at)
                VALUES (NEW.updated_by, COALESCE(v_user_name, 'system'), 'GRADE_UPDATE',
                        CONCAT('student ', NEW.student_id, ', course ', NEW.course_id,
                               ', component ', NEW.component,
                               ': score ', COALESCE(CAST(OLD.score AS CHAR), 'NULL'),
                               ' -> ', COALESCE(CAST(NEW.score AS CHAR), 'NULL'),
                               ' (max ', NEW.max_score, ')'),
                        NOW());
            END
        ''')
        print("[DB] Grade audit triggers installed")
    except Exception as e:
        if '1419' in str(e):
            print("[DB] Grade audit triggers NOT installed (error 1419). Run as root once:\n"
                  "     SET GLOBAL log_bin_trust_function_creators = 1;\n"
                  "     then restart the app, or run dbms/002_dbms_features.sql as root.")
        else:
            print(f"[DB] Grade audit trigger apply skipped: {e}")

    # Feature 3: start_session stored procedure (transaction + atomic rollback).
    # Same 1419 prerequisite as triggers; kept in its own try-block so a failure
    # here never blocks the view/triggers. The app falls back to inline inserts
    # when the procedure is absent (see routes_new.course_start_attendance).
    try:
        _execute(db, "DROP PROCEDURE IF EXISTS start_session")
        _execute(db, '''
            CREATE PROCEDURE start_session (
                IN  p_course_id  INT,
                IN  p_teacher_id INT,
                IN  p_class_id   INT,
                IN  p_batch_id   INT,
                IN  p_description TEXT,
                OUT out_session_id INT
            )
            BEGIN
                DECLARE EXIT HANDLER FOR SQLEXCEPTION
                BEGIN
                    ROLLBACK;
                    RESIGNAL;
                END;

                START TRANSACTION;

                INSERT INTO attendance_sessions
                    (course_id, teacher_id, class_id, batch_id, description, started_at)
                VALUES (p_course_id, p_teacher_id, p_class_id, p_batch_id, p_description, NOW());

                SET out_session_id = LAST_INSERT_ID();

                INSERT IGNORE INTO session_attendance (session_id, student_id, student_name, status)
                SELECT out_session_id, s.id, s.name, '--'
                FROM course_students cs
                JOIN students s ON s.id = cs.student_id
                WHERE cs.course_id = p_course_id;

                COMMIT;
            END
        ''')
        print("[DB] start_session procedure installed")
    except Exception as e:
        if '1419' in str(e):
            print("[DB] start_session procedure NOT installed (error 1419). "
                  "Enable log_bin_trust_function_creators as root to use it; "
                  "the app falls back to inline inserts meanwhile.")
        else:
            print(f"[DB] start_session procedure apply skipped: {e}")

    # Feature 5: CHECK constraint on grades (score within 0..max_score).
    # Idempotent: MySQL has no ADD CONSTRAINT IF NOT EXISTS, so check first.
    try:
        exists = _fetchone(db, '''
            SELECT COUNT(*) AS c FROM information_schema.table_constraints
            WHERE table_schema = DATABASE() AND table_name = 'grades'
              AND constraint_name = 'chk_grade_score' AND constraint_type = 'CHECK'
        ''')
        if not (exists and exists['c']):
            _execute(db,
                "ALTER TABLE grades ADD CONSTRAINT chk_grade_score "
                "CHECK (score IS NULL OR (score >= 0 AND score <= max_score))")
            print("[DB] CHECK constraint chk_grade_score added to grades")
    except Exception as e:
        print(f"[DB] grades CHECK constraint apply skipped: {e}")


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


def grade_triggers_installed(db):
    """True if the grade-audit triggers exist in the database.

    Used so the application can fall back to logging grade changes itself when
    the DB triggers could not be created (e.g. error 1419 on a non-SUPER user),
    without double-logging when they ARE present.
    """
    try:
        row = _fetchone(db, '''
            SELECT COUNT(*) AS c FROM information_schema.triggers
            WHERE trigger_schema = DATABASE()
              AND trigger_name IN ('trg_grades_audit', 'trg_grades_audit_insert')
        ''')
        return bool(row and row['c'] and row['c'] >= 2)
    except Exception:
        return False


def procedure_installed(db, name):
    """True if a stored procedure with the given name exists in this database."""
    try:
        row = _fetchone(db, '''
            SELECT COUNT(*) AS c FROM information_schema.routines
            WHERE routine_schema = DATABASE()
              AND routine_type = 'PROCEDURE' AND routine_name = %s
        ''', (name,))
        return bool(row and row['c'])
    except Exception:
        return False


def get_setting(db, key, default=None):
    """Read a value from the MySQL app_settings table (returns default if absent)."""
    row = _fetchone(db, "SELECT value FROM app_settings WHERE `key`=%s", (key,))
    return row['value'] if row else default


def set_setting(db, key, value):
    """Upsert a value into the MySQL app_settings table."""
    _execute(db,
        "INSERT INTO app_settings (`key`, value) VALUES (%s, %s) "
        "ON DUPLICATE KEY UPDATE value=VALUES(value)",
        (key, str(value)))


def get_defaulter_threshold(db):
    """Return the configured defaulter threshold as a float (default 75)."""
    try:
        return float(get_setting(db, 'defaulter_threshold', '75'))
    except (TypeError, ValueError):
        return 75.0


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
