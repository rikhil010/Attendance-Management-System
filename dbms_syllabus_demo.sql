-- =============================================================================
--  GWASOAT — DBMS Syllabus Demonstration Script
-- =============================================================================
--  Application : Biometric (fingerprint) Student Attendance Management System
--  Engine      : MySQL 8.0
--  Database    : gwasoat
--
--  This script demonstrates every topic in the DBMS lab syllabus (Assignments
--  1-9) using the real attendance-system schema. It is organised assignment by
--  assignment. Each section is self-contained and commented so it can be run
--  and explained individually in a viva/report.
--
--  HOW TO RUN
--    1. Create the base schema first:   SOURCE attendence_databse.sql;
--       (that file creates the database, tables and seed data)
--    2. Then run this file:             SOURCE dbms_syllabus_demo.sql;
--
--  NOTE: DELIMITER is switched to $$ for stored routines/triggers and reset to
--        ; afterwards, as required by MySQL for multi-statement bodies.
--
--  PREREQUISITE (one-time, needs an admin/root account):
--    If binary logging is enabled (SHOW VARIABLES LIKE 'log_bin' = ON), MySQL
--    refuses CREATE FUNCTION/TRIGGER from a non-SUPER user unless this is set:
--
--        SET GLOBAL log_bin_trust_function_creators = 1;
--
--    Run that once as root before Assignment 7 & 8 below. It is safe for a
--    local/coursework server. (gwasoat_user cannot set it as it lacks SUPER.)
-- =============================================================================

USE gwasoat;

-- =============================================================================
--  BONUS — NATIVE MySQL ROLES & PRIVILEGES  (database-level RBAC)
-- =============================================================================
--  In addition to the application-level RBAC stored in the role_permissions
--  table, MySQL 8 supports *native* database roles. These restrict what SQL a
--  given database account may execute. We model the three application roles as
--  real DB roles for demonstration. (The running app connects as gwasoat_user;
--  these roles show how privilege separation would be enforced at the DB tier.)
--
--  Requires an admin/root account to CREATE ROLE and GRANT. Run once.

CREATE ROLE IF NOT EXISTS 'gw_admin', 'gw_teacher', 'gw_student';

-- Admin role: full control of the schema.
GRANT ALL PRIVILEGES ON gwasoat.* TO 'gw_admin';

-- Teacher role: read everything, write to the tables a teacher operates on.
GRANT SELECT ON gwasoat.* TO 'gw_teacher';
GRANT INSERT, UPDATE, DELETE ON gwasoat.attendance_sessions TO 'gw_teacher';
GRANT INSERT, UPDATE, DELETE ON gwasoat.session_attendance  TO 'gw_teacher';
GRANT INSERT, UPDATE, DELETE ON gwasoat.course_students     TO 'gw_teacher';
GRANT INSERT, UPDATE, DELETE ON gwasoat.grades              TO 'gw_teacher';

-- Student role: read-only, and only the views that expose "own" data.
GRANT SELECT ON gwasoat.v_student_directory          TO 'gw_student';
GRANT SELECT ON gwasoat.v_student_attendance_summary TO 'gw_student';
GRANT SELECT ON gwasoat.grades                       TO 'gw_student';
GRANT SELECT ON gwasoat.timetable                    TO 'gw_student';

-- Example: create per-role login accounts and assign roles.
--   CREATE USER 'alice_teacher'@'localhost' IDENTIFIED BY '***';
--   GRANT 'gw_teacher' TO 'alice_teacher'@'localhost';
--   SET DEFAULT ROLE 'gw_teacher' TO 'alice_teacher'@'localhost';

-- Inspect:
--   SHOW GRANTS FOR 'gw_teacher';
-- -----------------------------------------------------------------------------


-- =============================================================================
--  ASSIGNMENT 1 — ER / EER DESIGN  (transformed to relational tables)
-- =============================================================================
--  The conceptual model is realised by the base schema. Summary of the model:
--
--  ENTITIES & KEYS
--    departments(id PK)                      strong entity
--    classes(id PK, department_id FK)        year, dept
--    batches(id PK, class_id FK)             weak-ish: a batch belongs to a class
--    students(id PK, class_id FK, batch_id FK)
--    users(id PK, student_id FK -> students) admin / teacher / student
--    courses(id PK, teacher_id FK -> users)
--    course_students(course_id FK, student_id FK)  M:N bridge (associative entity)
--    attendance_sessions(id PK, course_id FK, teacher_id FK, class_id FK)
--    session_attendance(id PK, session_id FK, student_id FK)  M:N bridge
--    grades(id PK, student_id FK, course_id FK)
--    timetable(id PK, course_id FK)
--    fingerprint_templates(student_id PK/FK)  1:1 with students
--
--  RELATIONSHIPS & CARDINALITIES
--    department 1 --- * class 1 --- * batch 1 --- * student        (1:N chains)
--    course    * --- * student            via course_students      (M:N)
--    session   * --- * student            via session_attendance   (M:N)
--    teacher(user) 1 --- * course                                   (1:N)
--    student   1 --- 1 fingerprint_template                          (1:1)
--
--  GENERALISATION / SPECIALISATION (EER)
--    users is a GENERALISATION of three specialisations distinguished by the
--    `role` discriminator: {admin, teacher, student}. A student user is further
--    related to the students entity through users.student_id (ISA-style link).
--
--  The relational transformation + normalisation (up to 3NF/BCNF) is documented
--  in DBMS_PROJECT_REPORT.md, section "Database Design".
-- -----------------------------------------------------------------------------


-- =============================================================================
--  ASSIGNMENT 2 — DDL QUERIES
--    Tables w/ constraints, CHECK, DEFAULT, UNIQUE, NOT NULL, FK,
--    indexes, AUTO_INCREMENT (MySQL's sequence equivalent), and a view that
--    serves as a "synonym" for easier access.
-- =============================================================================

-- 2.1  A table that exercises ALL the requested constraint types ----------------
--      enrollments: a richer M:N enrolment record between students and courses.
CREATE TABLE IF NOT EXISTS enrollments (
    id            INT AUTO_INCREMENT PRIMARY KEY,                 -- AUTO_INCREMENT = sequence
    student_id    INT          NOT NULL,                          -- NOT NULL
    course_id     INT          NOT NULL,
    enrolled_on   DATE         NOT NULL DEFAULT (CURRENT_DATE),   -- DEFAULT
    status        VARCHAR(10)  NOT NULL DEFAULT 'active',         -- DEFAULT
    final_percent DECIMAL(5,2) DEFAULT 0,
    CONSTRAINT uq_enroll UNIQUE (student_id, course_id),          -- UNIQUE
    CONSTRAINT chk_status CHECK (status IN ('active','dropped','completed')), -- CHECK
    CONSTRAINT chk_percent CHECK (final_percent BETWEEN 0 AND 100),           -- CHECK
    CONSTRAINT fk_enroll_student FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
    CONSTRAINT fk_enroll_course  FOREIGN KEY (course_id)  REFERENCES courses(id)  ON DELETE CASCADE
);

-- 2.2  Indexes to optimise queries on large datasets ----------------------------
--      A helper procedure makes index creation idempotent (MySQL has no
--      CREATE INDEX IF NOT EXISTS). It only creates the index if absent.
DELIMITER $$
DROP PROCEDURE IF EXISTS sp_add_index $$
CREATE PROCEDURE sp_add_index (IN p_table VARCHAR(64), IN p_index VARCHAR(64), IN p_cols VARCHAR(255))
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.statistics
        WHERE table_schema = DATABASE() AND table_name = p_table AND index_name = p_index
    ) THEN
        SET @ddl = CONCAT('CREATE INDEX ', p_index, ' ON ', p_table, ' (', p_cols, ')');
        PREPARE s FROM @ddl; EXECUTE s; DEALLOCATE PREPARE s;
    END IF;
END $$
DELIMITER ;

CALL sp_add_index('session_attendance',  'idx_session_att_student',  'student_id');
CALL sp_add_index('session_attendance',  'idx_session_att_status',   'status');
CALL sp_add_index('attendance_sessions', 'idx_sessions_course_date', 'course_id, started_at');
CALL sp_add_index('students',            'idx_students_class',       'class_id');
CALL sp_add_index('grades',              'idx_grades_student',       'student_id, course_id');

-- 2.3  "Sequence" demonstration -------------------------------------------------
--      MySQL has no CREATE SEQUENCE; AUTO_INCREMENT provides generated unique
--      primary keys. We can control the starting value explicitly:
ALTER TABLE enrollments AUTO_INCREMENT = 1000;   -- enrolment ids start at 1000

-- 2.4  "Synonym" demonstration --------------------------------------------------
--      MySQL has no CREATE SYNONYM. The idiomatic equivalent is a VIEW that
--      exposes a table/query under a friendlier name for easier access.
CREATE OR REPLACE VIEW roster AS      -- `roster` is a synonym-like alias
    SELECT s.id AS student_id, s.name, s.roll_no, s.prn, c.name AS class_name
    FROM students s
    LEFT JOIN classes c ON c.id = s.class_id;


-- =============================================================================
--  ASSIGNMENT 3 — DML QUERIES
--    INSERT / UPDATE / DELETE / SELECT, WHERE (equality, range, LIKE),
--    ORDER BY and LIMIT.
-- =============================================================================

-- 3.1  INSERT -------------------------------------------------------------------
INSERT INTO departments (name) VALUES ('Computer Engineering')
    ON DUPLICATE KEY UPDATE name = name;   -- idempotent demo insert

-- 3.2  UPDATE (equality condition) ----------------------------------------------
UPDATE students SET registered = 1 WHERE id = 1;

-- 3.3  SELECT + WHERE equality --------------------------------------------------
SELECT id, name, roll_no FROM students WHERE class_id = 1;

-- 3.4  SELECT + WHERE range (BETWEEN) -------------------------------------------
SELECT id, name FROM students WHERE id BETWEEN 1 AND 50;

-- 3.5  SELECT + WHERE pattern match (LIKE) --------------------------------------
SELECT id, name FROM students WHERE name LIKE 'A%';          -- names starting with A
SELECT id, name FROM courses  WHERE code LIKE '%CS%';        -- codes containing CS

-- 3.6  ORDER BY + LIMIT ---------------------------------------------------------
SELECT id, name, roll_no FROM students ORDER BY roll_no ASC LIMIT 10;

-- 3.7  DELETE (safe, scoped) ----------------------------------------------------
--      Remove dropped enrolments only.
DELETE FROM enrollments WHERE status = 'dropped';


-- =============================================================================
--  ASSIGNMENT 4 — ADVANCED SQL: AGGREGATION + JOINS
-- =============================================================================

-- 4.1  Aggregation: COUNT / AVG / SUM / MIN / MAX with GROUP BY + HAVING ---------
--      Attendance percentage per course, keeping only courses that have held
--      at least one session.
SELECT  c.id,
        c.name                                   AS course_name,
        COUNT(sa.id)                             AS total_marks,
        SUM(sa.status = 'Present')               AS total_present,
        MIN(ses.started_at)                      AS first_session,
        MAX(ses.started_at)                      AS last_session,
        ROUND(AVG(sa.status = 'Present') * 100, 2) AS avg_attendance_pct
FROM courses c
JOIN attendance_sessions ses ON ses.course_id = c.id
JOIN session_attendance  sa  ON sa.session_id = ses.id
GROUP BY c.id, c.name
HAVING COUNT(DISTINCT ses.id) >= 1
ORDER BY avg_attendance_pct DESC;

-- 4.2  INNER JOIN ---------------------------------------------------------------
--      Every student with the course(s) they are enrolled in.
SELECT s.name AS student, c.name AS course
FROM students s
INNER JOIN course_students cs ON cs.student_id = s.id
INNER JOIN courses c          ON c.id = cs.course_id
ORDER BY s.name;

-- 4.3  LEFT JOIN ----------------------------------------------------------------
--      All students, even those not assigned to any class (class may be NULL).
SELECT s.name, c.name AS class_name
FROM students s
LEFT JOIN classes c ON c.id = s.class_id
ORDER BY s.name;

-- 4.4  RIGHT JOIN ---------------------------------------------------------------
--      All courses, including those with no assigned teacher.
SELECT u.name AS teacher, c.name AS course
FROM users u
RIGHT JOIN courses c ON c.id = c.id AND u.id = c.teacher_id
ORDER BY c.name;


-- =============================================================================
--  ASSIGNMENT 5 — VIEWS
-- =============================================================================

-- 5.1  Simple projection view (selected columns only) ---------------------------
--      Analogous to "employee names, titles, salaries": here we expose only a
--      student's identity + class, hiding internal columns like batch_id, etc.
CREATE OR REPLACE VIEW v_student_directory AS
SELECT s.id, s.roll_no, s.name, c.name AS class_name
FROM students s
LEFT JOIN classes c ON c.id = s.class_id;

-- 5.2  Analytical view: per-student attendance summary across all courses -------
CREATE OR REPLACE VIEW v_student_attendance_summary AS
SELECT  s.id                                   AS student_id,
        s.name,
        s.roll_no,
        COUNT(sa.id)                           AS sessions_marked,
        SUM(sa.status = 'Present')             AS sessions_present,
        ROUND(AVG(sa.status = 'Present') * 100, 2) AS attendance_pct
FROM students s
LEFT JOIN session_attendance sa ON sa.student_id = s.id
GROUP BY s.id, s.name, s.roll_no;

-- 5.3  View usable directly by the app for defaulter dashboards -----------------
CREATE OR REPLACE VIEW v_course_defaulters AS
SELECT  c.id   AS course_id,
        c.name AS course_name,
        s.id   AS student_id,
        s.name AS student_name,
        s.roll_no,
        COUNT(sa.id)                               AS held,
        SUM(sa.status = 'Present')                 AS present,
        ROUND(AVG(sa.status = 'Present') * 100, 2) AS pct
FROM courses c
JOIN course_students cs      ON cs.course_id = c.id
JOIN students s              ON s.id = cs.student_id
LEFT JOIN attendance_sessions ses ON ses.course_id = c.id
LEFT JOIN session_attendance  sa  ON sa.session_id = ses.id AND sa.student_id = s.id
GROUP BY c.id, c.name, s.id, s.name, s.roll_no;


-- =============================================================================
--  ASSIGNMENT 6 — NESTED QUERIES (subqueries & correlated subqueries)
-- =============================================================================

-- 6.1  Students enrolled in MORE THAN a given number of courses -----------------
--      (parallel to "customers with more than three orders")
SELECT s.id, s.name,
       (SELECT COUNT(*) FROM course_students cs WHERE cs.student_id = s.id) AS course_count
FROM students s
WHERE (SELECT COUNT(*) FROM course_students cs WHERE cs.student_id = s.id) > 2;

-- 6.2  Correlated subquery: students whose attendance in a course is BELOW the
--      average attendance of that same course (parallel to "salary exceeds dept
--      average"). Uses v_course_defaulters for clarity.
SELECT d.course_name, d.student_name, d.pct
FROM v_course_defaulters d
WHERE d.pct < (
    SELECT AVG(d2.pct)
    FROM v_course_defaulters d2
    WHERE d2.course_id = d.course_id          -- correlation on course_id
);

-- 6.3  IN subquery: all students who have NEVER been marked present -------------
SELECT id, name FROM students
WHERE id NOT IN (
    SELECT DISTINCT student_id FROM session_attendance WHERE status = 'Present'
);

-- 6.4  EXISTS subquery: courses that currently have at least one enrolled student
SELECT c.id, c.name FROM courses c
WHERE EXISTS (
    SELECT 1 FROM course_students cs WHERE cs.course_id = c.id
);


-- =============================================================================
--  ASSIGNMENT 7 — STORED PROCEDURES & FUNCTIONS
-- =============================================================================
DELIMITER $$

-- 7.1  Basic stored procedure: fetch all students of a given class --------------
DROP PROCEDURE IF EXISTS sp_students_in_class $$
CREATE PROCEDURE sp_students_in_class (IN p_class_id INT)
BEGIN
    SELECT id, roll_no, name, prn
    FROM students
    WHERE class_id = p_class_id
    ORDER BY roll_no;
END $$

-- 7.2  Procedure with INPUT and OUTPUT parameters -------------------------------
--      Return a student's attendance percentage in a course via an OUT param.
DROP PROCEDURE IF EXISTS sp_course_attendance_pct $$
CREATE PROCEDURE sp_course_attendance_pct (
    IN  p_student_id INT,
    IN  p_course_id  INT,
    OUT p_pct        DECIMAL(5,2)
)
BEGIN
    DECLARE v_held    INT DEFAULT 0;
    DECLARE v_present INT DEFAULT 0;

    SELECT COUNT(sa.id), SUM(sa.status = 'Present')
      INTO v_held, v_present
    FROM attendance_sessions ses
    JOIN session_attendance  sa ON sa.session_id = ses.id
    WHERE ses.course_id = p_course_id AND sa.student_id = p_student_id;

    IF v_held = 0 THEN
        SET p_pct = 0;
    ELSE
        SET p_pct = ROUND(v_present / v_held * 100, 2);
    END IF;
END $$

-- 7.3  Procedure for data insertion ---------------------------------------------
--      Add a student and immediately enrol them in a course in one call.
DROP PROCEDURE IF EXISTS sp_add_student_to_course $$
CREATE PROCEDURE sp_add_student_to_course (
    IN p_id      INT,
    IN p_name    VARCHAR(255),
    IN p_roll    VARCHAR(100),
    IN p_course  INT
)
BEGIN
    INSERT INTO students (id, name, roll_no, registered)
    VALUES (p_id, p_name, p_roll, 0)
    ON DUPLICATE KEY UPDATE name = VALUES(name), roll_no = VALUES(roll_no);

    INSERT IGNORE INTO course_students (course_id, student_id)
    VALUES (p_course, p_id);
END $$

-- 7.4  Procedure with CONDITIONAL LOGIC (IF / CASE) -----------------------------
--      Classify a student's standing in a course from their attendance %.
DROP PROCEDURE IF EXISTS sp_attendance_grade $$
CREATE PROCEDURE sp_attendance_grade (
    IN  p_student_id INT,
    IN  p_course_id  INT,
    OUT p_standing   VARCHAR(20)
)
BEGIN
    DECLARE v_pct DECIMAL(5,2);
    CALL sp_course_attendance_pct(p_student_id, p_course_id, v_pct);

    SET p_standing = CASE
        WHEN v_pct >= 90 THEN 'Excellent'
        WHEN v_pct >= 75 THEN 'Good'
        WHEN v_pct >= 50 THEN 'At Risk'
        ELSE 'Defaulter'
    END;
END $$

-- 7.5  Stored FUNCTION to perform a calculation ---------------------------------
--      Return attendance percentage as a scalar (usable inside other queries).
DROP FUNCTION IF EXISTS fn_attendance_pct $$
CREATE FUNCTION fn_attendance_pct (p_student_id INT, p_course_id INT)
RETURNS DECIMAL(5,2)
DETERMINISTIC
READS SQL DATA
BEGIN
    DECLARE v_held    INT DEFAULT 0;
    DECLARE v_present INT DEFAULT 0;

    SELECT COUNT(sa.id), SUM(sa.status = 'Present')
      INTO v_held, v_present
    FROM attendance_sessions ses
    JOIN session_attendance  sa ON sa.session_id = ses.id
    WHERE ses.course_id = p_course_id AND sa.student_id = p_student_id;

    IF v_held = 0 THEN
        RETURN 0;
    END IF;
    RETURN ROUND(v_present / v_held * 100, 2);
END $$

-- 7.6  Simple scalar function (syllabus example: even/odd) ----------------------
DROP FUNCTION IF EXISTS fn_is_even $$
CREATE FUNCTION fn_is_even (p_num INT)
RETURNS VARCHAR(4)
DETERMINISTIC
BEGIN
    RETURN IF(p_num % 2 = 0, 'EVEN', 'ODD');
END $$

DELIMITER ;


-- =============================================================================
--  ASSIGNMENT 8 — TRIGGERS
--    (a) audit log on DELETE, (b) data synchronisation, (c) validation
-- =============================================================================

-- 8.0  Audit table for deleted students (used by trigger 8.1) -------------------
CREATE TABLE IF NOT EXISTS student_audit (
    audit_id   INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT,
    name       VARCHAR(255),
    deleted_at DATETIME NOT NULL
);

DELIMITER $$

-- 8.1  AUDIT trigger: log every student deletion --------------------------------
DROP TRIGGER IF EXISTS trg_student_delete_audit $$
CREATE TRIGGER trg_student_delete_audit
AFTER DELETE ON students
FOR EACH ROW
BEGIN
    INSERT INTO student_audit (student_id, name, deleted_at)
    VALUES (OLD.id, OLD.name, NOW());
END $$

-- 8.2  SYNCHRONISATION trigger: keep students.registered in sync with the
--      fingerprint_templates table. When a template is inserted for a student,
--      automatically flag that student as registered.
DROP TRIGGER IF EXISTS trg_template_sync_registered $$
CREATE TRIGGER trg_template_sync_registered
AFTER INSERT ON fingerprint_templates
FOR EACH ROW
BEGIN
    UPDATE students SET registered = 1 WHERE id = NEW.student_id;
END $$

--      Companion: when a template is removed, clear the flag.
DROP TRIGGER IF EXISTS trg_template_sync_unregister $$
CREATE TRIGGER trg_template_sync_unregister
AFTER DELETE ON fingerprint_templates
FOR EACH ROW
BEGIN
    UPDATE students SET registered = 0 WHERE id = OLD.student_id;
END $$

-- 8.3  VALIDATION trigger: enforce a business rule on grades.
--      A score may never exceed its max_score, and max_score must be positive.
DROP TRIGGER IF EXISTS trg_grade_validate_ins $$
CREATE TRIGGER trg_grade_validate_ins
BEFORE INSERT ON grades
FOR EACH ROW
BEGIN
    IF NEW.max_score <= 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'max_score must be greater than 0';
    END IF;
    IF NEW.score IS NOT NULL AND NEW.score > NEW.max_score THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'score cannot exceed max_score';
    END IF;
END $$

DROP TRIGGER IF EXISTS trg_grade_validate_upd $$
CREATE TRIGGER trg_grade_validate_upd
BEFORE UPDATE ON grades
FOR EACH ROW
BEGIN
    IF NEW.max_score <= 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'max_score must be greater than 0';
    END IF;
    IF NEW.score IS NOT NULL AND NEW.score > NEW.max_score THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'score cannot exceed max_score';
    END IF;
END $$

DELIMITER ;


-- =============================================================================
--  ASSIGNMENT 9 — CURSOR (row-by-row processing)
-- =============================================================================
--  Iterate over every (student, course) enrolment, compute attendance %, and
--  write it into enrollments.final_percent — the "Sales Summary" analogue.
DELIMITER $$

DROP PROCEDURE IF EXISTS sp_recompute_enrollment_percentages $$
CREATE PROCEDURE sp_recompute_enrollment_percentages ()
BEGIN
    DECLARE v_done     INT DEFAULT 0;
    DECLARE v_student  INT;
    DECLARE v_course   INT;
    DECLARE v_pct      DECIMAL(5,2);

    -- Cursor over all current course enrolments
    DECLARE cur CURSOR FOR
        SELECT student_id, course_id FROM course_students;
    DECLARE CONTINUE HANDLER FOR NOT FOUND SET v_done = 1;

    OPEN cur;
    read_loop: LOOP
        FETCH cur INTO v_student, v_course;
        IF v_done = 1 THEN
            LEAVE read_loop;
        END IF;

        -- reuse the scalar function from Assignment 7
        SET v_pct = fn_attendance_pct(v_student, v_course);

        -- upsert the computed percentage into the summary table
        INSERT INTO enrollments (student_id, course_id, final_percent, status)
        VALUES (v_student, v_course, v_pct, 'active')
        ON DUPLICATE KEY UPDATE final_percent = v_pct;
    END LOOP;
    CLOSE cur;
END $$

DELIMITER ;

-- =============================================================================
--  END OF SYLLABUS DEMONSTRATION SCRIPT
-- =============================================================================
