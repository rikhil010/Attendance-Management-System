

USE gwasoat;

-- -----------------------------------------------------------------------------
-- 1. INNER JOIN
--    Returns only rows that match on BOTH sides. Here: every (student, course)
--    enrolment pair — a student appears once per course they are enrolled in,
--    and unenrolled students / courses with no students do not appear.
-- -----------------------------------------------------------------------------
SELECT s.roll_no, s.name AS student, c.code, c.name AS course
FROM students s
INNER JOIN course_students cs ON cs.student_id = s.id
INNER JOIN courses c          ON c.id = cs.course_id
ORDER BY s.roll_no, c.code;

-- -----------------------------------------------------------------------------
-- 2. LEFT JOIN
--    Returns EVERY row from the left table (courses), filling NULL where the
--    right table has no match. Here: all courses with their teacher's name,
--    including a course that has no teacher assigned (teacher_name = NULL).
-- -----------------------------------------------------------------------------
SELECT c.code, c.name AS course, u.name AS teacher_name
FROM courses c
LEFT JOIN users u ON u.id = c.teacher_id
ORDER BY c.code;

-- -----------------------------------------------------------------------------
-- 3. SUBQUERY (nested query)
--    A query inside another query. Here: students who are NOT enrolled in any
--    course, using a subquery in a NOT IN predicate.
-- -----------------------------------------------------------------------------
SELECT s.id, s.roll_no, s.name
FROM students s
WHERE s.id NOT IN (SELECT DISTINCT student_id FROM course_students)
ORDER BY s.roll_no;

-- Correlated subquery variant: each course with its enrolment count computed by
-- a subquery that references the outer row (c.id).
SELECT c.code, c.name,
       (SELECT COUNT(*) FROM course_students cs WHERE cs.course_id = c.id) AS enrolled
FROM courses c
ORDER BY enrolled DESC;

-- -----------------------------------------------------------------------------
-- 4. GROUP BY + HAVING
--    Aggregate per group, then filter the GROUPS (HAVING, not WHERE). Here:
--    courses that have held MORE THAN ONE attendance session, with the count.
-- -----------------------------------------------------------------------------
SELECT c.code, c.name, COUNT(ses.id) AS sessions_held
FROM courses c
JOIN attendance_sessions ses ON ses.course_id = c.id
GROUP BY c.id, c.code, c.name
HAVING COUNT(ses.id) > 1
ORDER BY sessions_held DESC;

-- -----------------------------------------------------------------------------
-- 5. AGGREGATE — average grade per course
--    AVG/COUNT over grouped rows: the average percentage score and number of
--    graded entries for each course. ROUND formats the average.
-- -----------------------------------------------------------------------------
SELECT c.code, c.name AS course,
       COUNT(g.id)                                   AS graded_entries,
       ROUND(AVG(g.score / g.max_score * 100), 1)    AS avg_percent
FROM courses c
JOIN grades g ON g.course_id = c.id
WHERE g.score IS NOT NULL
GROUP BY c.id, c.code, c.name
ORDER BY avg_percent DESC;

-- -----------------------------------------------------------------------------
-- 6. QUERY ON A VIEW
--    Treat the v_attendance_summary view like a table. Here: the defaulters —
--    students below 75% attendance in a course — read straight from the view
--    (the view itself hides the underlying JOIN + GROUP BY logic).
-- -----------------------------------------------------------------------------
SELECT course_code, roll_no, student_name, total_sessions, present, percentage
FROM v_attendance_summary
WHERE total_sessions > 0 AND percentage < 75
ORDER BY percentage ASC, course_code;

-- =============================================================================
--  END OF DEMONSTRATION QUERIES
-- =============================================================================
