-- Create the database
CREATE DATABASE gwasoat
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

-- Create a dedicated user
CREATE USER 'gwasoat_user'@'localhost' IDENTIFIED BY 'gwasoat_pass_2026';
GRANT ALL PRIVILEGES ON gwasoat.* TO 'gwasoat_user'@'localhost';
FLUSH PRIVILEGES;

-- Switch to it
USE gwasoat;

-- Users: admin + teachers + students.
-- role        -> application role used for access control (admin|teacher|student)
-- student_id  -> links a student login account to its students row (NULL for staff)
CREATE TABLE users (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    name       VARCHAR(255) NOT NULL,
    email      VARCHAR(255) UNIQUE NOT NULL,
    password   VARCHAR(255) NOT NULL,
    role       VARCHAR(50) NOT NULL DEFAULT 'student',  -- fail-closed: least-privileged fallback
    student_id INT,
    created_at DATETIME NOT NULL,
    -- case-sensitive whitelist: only the exact lowercase roles are allowed
    CONSTRAINT chk_user_role CHECK (role IN ('admin', 'teacher', 'student'))
);

CREATE TABLE departments (
    id   INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL
);

CREATE TABLE classes (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    name          VARCHAR(255) NOT NULL,
    year          INT,
    department_id INT,
    FOREIGN KEY (department_id) REFERENCES departments(id)
);

CREATE TABLE batches (
    id       INT AUTO_INCREMENT PRIMARY KEY,
    name     VARCHAR(255) NOT NULL,
    class_id INT NOT NULL,
    FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE
);

CREATE TABLE students (
    id         INT PRIMARY KEY,
    prn        VARCHAR(100),
    roll_no    VARCHAR(100),
    name       VARCHAR(255) NOT NULL,
    class_id   INT,
    batch_id   INT,
    registered TINYINT NOT NULL DEFAULT 0,
    FOREIGN KEY (class_id) REFERENCES classes(id),
    FOREIGN KEY (batch_id) REFERENCES batches(id)
);

CREATE TABLE courses (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    name       VARCHAR(255) NOT NULL,
    code       VARCHAR(100),
    teacher_id INT,
    FOREIGN KEY (teacher_id) REFERENCES users(id)
);

CREATE TABLE course_students (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    course_id  INT NOT NULL,
    student_id INT NOT NULL,
    UNIQUE KEY uq_course_student (course_id, student_id),
    FOREIGN KEY (course_id)  REFERENCES courses(id)  ON DELETE CASCADE,
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
);

CREATE TABLE fingerprint_templates (
    student_id    INT PRIMARY KEY,
    class_id      INT,
    template_data LONGBLOB NOT NULL,
    template_size INT NOT NULL,
    created_at    DATETIME NOT NULL,
    FOREIGN KEY (student_id) REFERENCES students(id)
);

CREATE TABLE attendance_sessions (
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
);

CREATE TABLE session_attendance (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    session_id   INT NOT NULL,
    student_id   INT NOT NULL,
    student_name VARCHAR(255) NOT NULL,
    status       VARCHAR(20) NOT NULL DEFAULT '--',
    marked_at    DATETIME,
    UNIQUE KEY uq_session_student (session_id, student_id),
    FOREIGN KEY (session_id) REFERENCES attendance_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (student_id) REFERENCES students(id)
);

CREATE TABLE app_settings (
    `key` VARCHAR(255) PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE audit_log (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    user_id    INT,
    user_name  VARCHAR(255),
    action     VARCHAR(255) NOT NULL,
    details    TEXT,
    created_at DATETIME NOT NULL
);

CREATE TABLE timetable (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    course_id   INT NOT NULL,
    day_of_week INT NOT NULL,
    start_time  VARCHAR(10) NOT NULL,
    end_time    VARCHAR(10),
    room        VARCHAR(100),
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE
);

-- Grades: one row per (student, course, component). Teachers/admin edit; students read.
CREATE TABLE grades (
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
);

-- ─────────────────────────────────────────────────────────────────────────────
-- Application-level Role-Based Access Control (RBAC)
-- ─────────────────────────────────────────────────────────────────────────────
-- role_permissions maps each application role to the permissions it is granted.
-- The application reads this to decide what each logged-in user may do.
-- Admin is granted the wildcard '*' which the app treats as "all permissions".
CREATE TABLE role_permissions (
    role       VARCHAR(50)  NOT NULL,
    permission VARCHAR(100) NOT NULL,
    PRIMARY KEY (role, permission)
);

-- Link student login accounts to their students row (added now that students exists)
ALTER TABLE users
    ADD CONSTRAINT fk_users_student
    FOREIGN KEY (student_id) REFERENCES students(id);

-- Seed the permission catalogue -----------------------------------------------
-- Admin: full access via wildcard.
INSERT INTO role_permissions (role, permission) VALUES
    ('admin', '*');

-- Teacher: manage their courses, run/mark attendance, reports, grades, timetable.
INSERT INTO role_permissions (role, permission) VALUES
    ('teacher', 'course.view'),
    ('teacher', 'course.manage_students'),
    ('teacher', 'attendance.run'),
    ('teacher', 'attendance.mark'),
    ('teacher', 'report.view'),
    ('teacher', 'report.export'),
    ('teacher', 'grade.view'),
    ('teacher', 'grade.edit'),
    ('teacher', 'timetable.view'),
    ('teacher', 'profile.edit');

-- Student: read-only access to their own data only.
INSERT INTO role_permissions (role, permission) VALUES
    ('student', 'self.course.view'),
    ('student', 'self.attendance.view'),
    ('student', 'self.grade.view'),
    ('student', 'self.timetable.view'),
    ('student', 'self.class.view'),
    ('student', 'profile.edit');

-- Seed the default admin user (password = admin123)
INSERT INTO users (name, email, password, role, created_at)
VALUES ('Admin', 'admin@gwasoat.local',
        SHA2(CONCAT('gwasoat_salt_2026', 'admin123'), 256),
        'admin', NOW());

