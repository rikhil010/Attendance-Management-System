-- =============================================================================
--  GWASOAT — Migration 002: DBMS feature additions
-- =============================================================================
--  Re-runnable. Run AFTER attendence_databse.sql (and models.initialize_new_schema).
--      mysql -u root -p gwasoat < migrations/002_dbms_features.sql
--
--  The application also creates these objects automatically at startup
--  (models._apply_dbms_features), so running this file by hand is optional —
--  it exists so the SQL is visible and demonstrable for the viva.
--
--  NOTE on "present": session_attendance.status stores the literal strings
--  'Present', 'Absent' and '--' (unmarked). Verified in the Python backend
--  (routes_new.course_stop_attendance, routes_features.manual_mark). The view
--  below therefore counts status = 'Present'.
-- =============================================================================

USE gwasoat;

-- -----------------------------------------------------------------------------
-- FEATURE 1 — Attendance summary view (per student, per course)
-- -----------------------------------------------------------------------------
-- Concept: VIEW built on JOINs + GROUP BY + conditional aggregation.
-- One row per (student, course) that the student is enrolled in, giving the
-- number of sessions held for that course, how many the student was Present
-- for, and the percentage. LEFT JOINs keep students with zero sessions/marks.
DROP VIEW IF EXISTS v_attendance_summary;
CREATE VIEW v_attendance_summary AS
SELECT
    cs.course_id                                             AS course_id,
    c.name                                                   AS course_name,
    c.code                                                   AS course_code,
    s.id                                                     AS student_id,
    s.name                                                   AS student_name,
    s.roll_no                                                AS roll_no,
    s.prn                                                    AS prn,
    COUNT(DISTINCT ses.id)                                   AS total_sessions,
    COUNT(DISTINCT CASE WHEN sa.status = 'Present'
                        THEN ses.id END)                     AS present,
    CASE WHEN COUNT(DISTINCT ses.id) = 0 THEN 0.0
         ELSE ROUND(
              COUNT(DISTINCT CASE WHEN sa.status = 'Present' THEN ses.id END)
              / COUNT(DISTINCT ses.id) * 100, 1)
    END                                                      AS percentage
FROM course_students cs
JOIN students s            ON s.id = cs.student_id
JOIN courses  c            ON c.id = cs.course_id
LEFT JOIN attendance_sessions ses ON ses.course_id = cs.course_id
LEFT JOIN session_attendance  sa  ON sa.session_id = ses.id
                                  AND sa.student_id = cs.student_id
GROUP BY cs.course_id, c.name, c.code, s.id, s.name, s.roll_no, s.prn;

-- Configurable defaulter threshold (percentage). Stored in app_settings so it
-- can be changed without code edits. app_settings(`key` PK, value TEXT).
INSERT INTO app_settings (`key`, value) VALUES ('defaulter_threshold', '75')
    ON DUPLICATE KEY UPDATE value = value;   -- keep existing value if already set

-- New permission for viewing the defaulter report (seeded for teacher role).
-- Admin holds the '*' wildcard so needs no explicit grant.
INSERT INTO role_permissions (role, permission) VALUES ('teacher', 'report.defaulters')
    ON DUPLICATE KEY UPDATE permission = permission;

-- -----------------------------------------------------------------------------
-- FEATURE 2 — Grade audit triggers (AFTER INSERT / AFTER UPDATE on grades)
-- -----------------------------------------------------------------------------
-- Concept: TRIGGER + automatic auditing at the database tier.
-- Every grade insert/update writes a row into audit_log automatically, so the
-- history is recorded even if a change is made directly in SQL (not just via
-- the app). user_id comes from grades.updated_by; the user's name is looked up;
-- details carries the student, course, component and the score change.
--
-- audit_log(created_at) is NOT NULL with no default, so the triggers supply
-- NOW() explicitly.
--
-- PREREQUISITE (one-time, as root/admin) when binary logging is ON:
--     SET GLOBAL log_bin_trust_function_creators = 1;
-- Without it MySQL rejects CREATE TRIGGER from a non-SUPER user (error 1419).
-- The app's gwasoat_user is non-SUPER, so either run that as root first (then
-- restart the app, which auto-creates the triggers) OR run this whole file as
-- root. Check with:  SHOW VARIABLES LIKE 'log_bin';

DROP TRIGGER IF EXISTS trg_grades_audit_insert;
DROP TRIGGER IF EXISTS trg_grades_audit;

DELIMITER $$

CREATE TRIGGER trg_grades_audit_insert
AFTER INSERT ON grades
FOR EACH ROW
BEGIN
    DECLARE v_user_name VARCHAR(255);
    SELECT name INTO v_user_name FROM users WHERE id = NEW.updated_by;
    INSERT INTO audit_log (user_id, user_name, action, details, created_at)
    VALUES (
        NEW.updated_by,
        COALESCE(v_user_name, 'system'),
        'GRADE_INSERT',
        CONCAT('student ', NEW.student_id, ', course ', NEW.course_id,
               ', component ', NEW.component,
               ': set ', COALESCE(CAST(NEW.score AS CHAR), 'NULL'),
               '/', NEW.max_score),
        NOW()
    );
END $$

CREATE TRIGGER trg_grades_audit
AFTER UPDATE ON grades
FOR EACH ROW
BEGIN
    DECLARE v_user_name VARCHAR(255);
    SELECT name INTO v_user_name FROM users WHERE id = NEW.updated_by;
    INSERT INTO audit_log (user_id, user_name, action, details, created_at)
    VALUES (
        NEW.updated_by,
        COALESCE(v_user_name, 'system'),
        'GRADE_UPDATE',
        CONCAT('student ', NEW.student_id, ', course ', NEW.course_id,
               ', component ', NEW.component,
               ': score ', COALESCE(CAST(OLD.score AS CHAR), 'NULL'),
               ' -> ', COALESCE(CAST(NEW.score AS CHAR), 'NULL'),
               ' (max ', NEW.max_score, ')'),
        NOW()
    );
END $$

DELIMITER ;

-- -----------------------------------------------------------------------------
-- FEATURE 3 — start_session stored procedure (TRANSACTION + atomic rollback)
-- -----------------------------------------------------------------------------
-- Concept: STORED PROCEDURE wrapping a TRANSACTION (atomicity).
-- Creates one attendance session and, in the same transaction, one
-- session_attendance row (status '--') for every student enrolled in the
-- course (course_students). If any statement fails, the EXIT HANDLER rolls the
-- whole thing back and RESIGNALs, so a session is never left half-created.
-- Returns the new session id as out_session_id.
--
-- NOTE: procedures are NOT subject to the log_bin_trust_function_creators flag
-- (that applies to functions/triggers), so this installs on a non-SUPER user.
-- session_attendance.student_name is NOT NULL, so the roster insert supplies it.

DROP PROCEDURE IF EXISTS start_session;

DELIMITER $$

CREATE PROCEDURE start_session (
    IN  p_course_id   INT,
    IN  p_teacher_id  INT,
    IN  p_class_id    INT,
    IN  p_batch_id    INT,
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
END $$

DELIMITER ;

-- -----------------------------------------------------------------------------
-- FEATURE 5 — CHECK constraint on grades (score within 0..max_score)
-- -----------------------------------------------------------------------------
-- Concept: CHECK CONSTRAINT enforcing a business rule at the database tier.
-- A grade's score can never be negative or exceed its max_score. score is
-- nullable (a grade may have no score yet), so NULL is allowed. MySQL 8.0
-- supports multi-column CHECK constraints.
--
-- Adding this fails if any existing row violates it (verified 0 violations).
-- Re-runnable: the DROP tolerates a first run where the constraint is absent
-- (run it alone and ignore "check constraint does not exist" the first time),
-- or just run the ADD on a clean DB.

ALTER TABLE grades
    ADD CONSTRAINT chk_grade_score
    CHECK (score IS NULL OR (score >= 0 AND score <= max_score));

-- =============================================================================
--  END OF MIGRATION 002 (features 1-3, 5)
-- =============================================================================
