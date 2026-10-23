"""
Feature routes for GWASOAT — MySQL backend.
Manual override, reports/defaulters, bulk import, edit support,
teacher profile, dashboard, audit log, and timetable.
"""

import sys
import os
import io
import csv
from datetime import datetime
from flask import render_template, request, jsonify, session, send_file

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from models import (get_db, hash_password, log_action, ensure_student_account,
                    get_defaulter_threshold, set_setting, grade_triggers_installed)
from database import _fetchone, _fetchall, _execute
from auth import (login_required, admin_required, get_current_user,
                  permission_required, staff_required,
                  course_owner_required, check_course_access)

DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']


def _session_course_guard(user, session_id):
    """Resolve the owning course of a session and apply the ownership rule.

    Returns None when the user may manage the session's course, a
    (response, 404) tuple when the session does not exist, or the
    check_course_access denial tuple otherwise.
    """
    db = get_db()
    row = _fetchone(db, "SELECT course_id FROM attendance_sessions WHERE id=%s", (session_id,))
    db.close()
    if not row:
        return jsonify({'status': 'error', 'message': 'Session not found'}), 404
    return check_course_access(user, row['course_id'])


def _date_filter(args, alias='s'):
    """Return (where_sql, params) fragment for a date range on <alias>.started_at."""
    start = args.get('start')
    end = args.get('end')
    where, params = '', []
    if start:
        where += f" AND date({alias}.started_at) >= date(%s)"
        params.append(start)
    if end:
        where += f" AND date({alias}.started_at) <= date(%s)"
        params.append(end)
    return where, params


def setup_feature_routes(app):

    # ─── Manual attendance override ──────────────────────────
    @app.route('/api/session/<int:session_id>/mark', methods=['POST'])
    @login_required
    def manual_mark(session_id):
        err = _session_course_guard(get_current_user(), session_id)
        if err:
            return err
        status = request.form.get('status', '').strip()
        student_id = request.form.get('student_id')
        if status not in ('Present', 'Absent', '--'):
            return jsonify({'status': 'error', 'message': 'Invalid status'}), 400
        if not student_id:
            return jsonify({'status': 'error', 'message': 'student_id required'}), 400
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db = get_db()
        _execute(db,
            "UPDATE session_attendance SET status=%s, marked_at=%s "
            "WHERE session_id=%s AND student_id=%s",
            (status, now if status != '--' else None, session_id, int(student_id)))
        db.commit()
        db.close()
        log_action(get_current_user(), 'manual_mark',
                   f'session {session_id} student {student_id} -> {status}')
        return jsonify({'status': 'success'})

    @app.route('/api/session/<int:session_id>/mark_all', methods=['POST'])
    @login_required
    def mark_all(session_id):
        err = _session_course_guard(get_current_user(), session_id)
        if err:
            return err
        status = request.form.get('status', '').strip()
        only_unmarked = request.form.get('only_unmarked', '0') == '1'
        if status not in ('Present', 'Absent', '--'):
            return jsonify({'status': 'error', 'message': 'Invalid status'}), 400
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db = get_db()
        if only_unmarked:
            _execute(db,
                "UPDATE session_attendance SET status=%s, marked_at=%s "
                "WHERE session_id=%s AND status='--'",
                (status, now, session_id))
        else:
            _execute(db,
                "UPDATE session_attendance SET status=%s, marked_at=%s WHERE session_id=%s",
                (status, now if status != '--' else None, session_id))
        db.commit()
        db.close()
        log_action(get_current_user(), 'mark_all', f'session {session_id} -> {status}')
        return jsonify({'status': 'success'})

    # ─── Reports / defaulters ────────────────────────────────
    def _build_report(course_id, args):
        """Build the per-student attendance report for a course.

        When no date range is given, the per-student totals and percentage are
        read directly from the v_attendance_summary VIEW (no Python-side
        percentage maths). A date range falls back to a session-scoped query,
        because the view aggregates over all sessions.
        The defaulter threshold defaults to the configurable app_settings value.
        """
        db = get_db()
        default_threshold = get_defaulter_threshold(db)
        threshold = float(args.get('threshold', default_threshold))
        start, end = args.get('start'), args.get('end')

        if not start and not end:
            # Canonical path: read straight from the view.
            total_row = _fetchone(db,
                "SELECT COUNT(*) c FROM attendance_sessions WHERE course_id=%s", (course_id,))
            total_sessions = total_row['c'] if total_row else 0
            rows = _fetchall(db, '''
                SELECT student_id AS id, student_name AS name, prn, roll_no,
                       total_sessions AS held, present, percentage AS percent
                FROM v_attendance_summary
                WHERE course_id=%s
                ORDER BY roll_no, student_name
            ''', (course_id,))
            db.close()
            report = []
            for r in rows:
                held = r['held'] or 0
                present = r['present'] or 0
                pct = float(r['percent']) if r['percent'] is not None else 0.0
                report.append({
                    'id': r['id'], 'name': r['name'], 'prn': r['prn'] or '',
                    'roll_no': r['roll_no'] or '', 'held': held, 'present': present,
                    'absent': held - present, 'percent': pct,
                    'defaulter': held > 0 and pct < threshold
                })
            return total_sessions, threshold, report

        # Date-filtered path: the view cannot scope by date, so aggregate directly.
        where, params = _date_filter(args, alias='ses')
        count_row = _fetchone(db,
            "SELECT COUNT(*) c FROM attendance_sessions ses WHERE ses.course_id=%s" + where,
            tuple([course_id] + params))
        total_sessions = count_row['c'] if count_row else 0
        rows = _fetchall(db, '''
            SELECT s.id, s.name, s.prn, s.roll_no,
                   COUNT(sa.id) AS held,
                   SUM(CASE WHEN sa.status='Present' THEN 1 ELSE 0 END) AS present
            FROM students s
            JOIN course_students cs ON cs.student_id=s.id AND cs.course_id=%s
            LEFT JOIN attendance_sessions ses ON ses.course_id=%s
        ''' + where + '''
            LEFT JOIN session_attendance sa ON sa.session_id=ses.id AND sa.student_id=s.id
            GROUP BY s.id ORDER BY s.roll_no, s.name
        ''', tuple([course_id, course_id] + params))
        db.close()
        report = []
        for r in rows:
            held = r['held'] or 0
            present = r['present'] or 0
            pct = round(present / held * 100, 1) if held else 0.0
            report.append({
                'id': r['id'], 'name': r['name'], 'prn': r['prn'] or '',
                'roll_no': r['roll_no'] or '', 'held': held, 'present': present,
                'absent': held - present, 'percent': pct,
                'defaulter': held > 0 and pct < threshold
            })
        return total_sessions, threshold, report

    @app.route('/api/course/<int:course_id>/report')
    @login_required
    @course_owner_required
    def course_report(course_id):
        total_sessions, threshold, report = _build_report(course_id, request.args)
        defaulters = [r for r in report if r['defaulter']]
        return jsonify({
            'total_sessions': total_sessions, 'threshold': threshold,
            'students': report, 'defaulter_count': len(defaulters)
        })

    @app.route('/api/course/<int:course_id>/report/export')
    @login_required
    @course_owner_required
    def course_report_export(course_id):
        _, threshold, report = _build_report(course_id, request.args)
        output = io.StringIO()
        w = csv.writer(output)
        w.writerow(['Roll No', 'PRN', 'Name', 'Sessions Held', 'Present',
                    'Absent', 'Attendance %', 'Defaulter'])
        for r in report:
            w.writerow([r['roll_no'], r['prn'], r['name'], r['held'], r['present'],
                        r['absent'], r['percent'], 'YES' if r['defaulter'] else ''])
        output.seek(0)
        return send_file(io.BytesIO(output.getvalue().encode()), mimetype='text/csv',
                         as_attachment=True, download_name=f'course_{course_id}_report.csv')

    # ─── Attendance summary (from the v_attendance_summary VIEW) ─────────
    @app.route('/api/course/<int:course_id>/attendance_summary')
    @login_required
    @course_owner_required
    def attendance_summary(course_id):
        """Per-student attendance summary for a course, read from the view."""
        db = get_db()
        threshold = get_defaulter_threshold(db)
        rows = _fetchall(db, '''
            SELECT student_id, student_name, roll_no, prn,
                   total_sessions, present, percentage
            FROM v_attendance_summary
            WHERE course_id=%s
            ORDER BY roll_no, student_name
        ''', (course_id,))
        db.close()
        return jsonify({
            'threshold': threshold,
            'students': [{
                'student_id': r['student_id'], 'name': r['student_name'],
                'roll_no': r['roll_no'] or '', 'prn': r['prn'] or '',
                'total_sessions': r['total_sessions'], 'present': r['present'],
                'percentage': float(r['percentage']) if r['percentage'] is not None else 0.0,
                'defaulter': (r['total_sessions'] or 0) > 0
                             and float(r['percentage'] or 0) < threshold,
            } for r in rows]
        })

    @app.route('/api/course/<int:course_id>/defaulters')
    @permission_required('report.defaulters')
    @course_owner_required
    def course_defaulters(course_id):
        """Students below the (configurable) attendance threshold, from the view."""
        db = get_db()
        threshold = float(request.args.get('threshold', get_defaulter_threshold(db)))
        rows = _fetchall(db, '''
            SELECT student_id, student_name, roll_no, prn,
                   total_sessions, present, percentage
            FROM v_attendance_summary
            WHERE course_id=%s AND total_sessions > 0 AND percentage < %s
            ORDER BY percentage ASC, roll_no
        ''', (course_id, threshold))
        db.close()
        return jsonify({
            'threshold': threshold,
            'defaulters': [{
                'student_id': r['student_id'], 'name': r['student_name'],
                'roll_no': r['roll_no'] or '', 'prn': r['prn'] or '',
                'total_sessions': r['total_sessions'], 'present': r['present'],
                'percentage': float(r['percentage']) if r['percentage'] is not None else 0.0,
            } for r in rows]
        })

    @app.route('/api/settings/defaulter_threshold', methods=['GET', 'POST'])
    @login_required
    def defaulter_threshold_setting():
        """Read (any staff) or update (admin only) the configurable threshold."""
        user = get_current_user()
        db = get_db()
        if request.method == 'POST':
            if user['role'] != 'admin':
                db.close()
                return jsonify({'status': 'error', 'message': 'Admin access required'}), 403
            try:
                value = float(request.form.get('value', ''))
            except ValueError:
                db.close()
                return jsonify({'status': 'error', 'message': 'Threshold must be a number'}), 400
            if not 0 <= value <= 100:
                db.close()
                return jsonify({'status': 'error', 'message': 'Threshold must be between 0 and 100'}), 400
            set_setting(db, 'defaulter_threshold', value)
            db.commit()
            db.close()
            log_action(user, 'set_defaulter_threshold', str(value))
            return jsonify({'status': 'success', 'threshold': value})
        threshold = get_defaulter_threshold(db)
        db.close()
        return jsonify({'threshold': threshold})

    # ─── Bulk student import ─────────────────────────────────
    @app.route('/api/course/<int:course_id>/import_students', methods=['POST'])
    @login_required
    @course_owner_required
    def import_students(course_id):
        f = request.files.get('file')
        if not f:
            return jsonify({'status': 'error', 'message': 'No file uploaded'}), 400
        try:
            content = f.read().decode('utf-8-sig')
        except Exception:
            return jsonify({'status': 'error', 'message': 'Could not read file (use UTF-8 CSV)'}), 400
        reader = csv.DictReader(io.StringIO(content))
        added, linked, errors = 0, 0, []
        db = get_db()
        for i, row in enumerate(reader, start=2):
            norm = {(k or '').strip().lower(): (v or '').strip() for k, v in row.items()}
            sid  = norm.get('id') or norm.get('fingerprint id') or norm.get('fingerprint_id')
            name = norm.get('name') or norm.get('student name')
            prn  = norm.get('prn') or norm.get('enrollment') or ''
            roll = norm.get('roll_no') or norm.get('roll no') or norm.get('roll') or ''
            if not sid or not name:
                errors.append(f'Row {i}: missing id or name')
                continue
            try:
                sid = int(sid)
            except ValueError:
                errors.append(f'Row {i}: id "{sid}" is not a number')
                continue
            try:
                existing = _fetchone(db, "SELECT id FROM students WHERE id=%s", (sid,))
                if not existing:
                    _execute(db,
                        "INSERT INTO students (id, name, prn, roll_no, registered) VALUES (%s,%s,%s,%s,0)",
                        (sid, name, prn, roll))
                    added += 1
                else:
                    _execute(db,
                        "UPDATE students SET name=%s, prn=%s, roll_no=%s WHERE id=%s",
                        (name, prn, roll, sid))
                _execute(db,
                    "INSERT IGNORE INTO course_students (course_id, student_id) VALUES (%s,%s)",
                    (course_id, sid))
                # Ensure a login account exists for this student
                ensure_student_account(db, sid, name)
                linked += 1
            except Exception as e:
                errors.append(f'Row {i}: {e}')
        db.commit()
        db.close()
        log_action(get_current_user(), 'import_students',
                   f'course {course_id}: +{added} new, {linked} linked')
        return jsonify({'status': 'success', 'added': added, 'linked': linked, 'errors': errors})

    # ─── Edit support (admin) ────────────────────────────────
    @app.route('/api/admin/students/<int:sid>/edit', methods=['POST'])
    @admin_required
    def edit_student(sid):
        d = request.form
        db = get_db()
        _execute(db,
            "UPDATE students SET name=%s, prn=%s, roll_no=%s, class_id=%s, batch_id=%s WHERE id=%s",
            (d.get('name'), d.get('prn', ''), d.get('roll_no', ''),
             d.get('class_id') or None, d.get('batch_id') or None, sid))
        db.commit()
        db.close()
        log_action(get_current_user(), 'edit_student', f'student {sid}')
        return jsonify({'status': 'success'})

    @app.route('/api/admin/courses/<int:cid>/edit', methods=['POST'])
    @admin_required
    def edit_course(cid):
        d = request.form
        db = get_db()
        _execute(db,
            "UPDATE courses SET name=%s, code=%s, teacher_id=%s WHERE id=%s",
            (d.get('name'), d.get('code', ''), d.get('teacher_id') or None, cid))
        db.commit()
        db.close()
        log_action(get_current_user(), 'edit_course', f'course {cid}')
        return jsonify({'status': 'success'})

    @app.route('/api/admin/classes/<int:cid>/edit', methods=['POST'])
    @admin_required
    def edit_class(cid):
        d = request.form
        db = get_db()
        _execute(db,
            "UPDATE classes SET name=%s, year=%s, department_id=%s WHERE id=%s",
            (d.get('name'), d.get('year') or None, d.get('department_id') or None, cid))
        db.commit()
        db.close()
        log_action(get_current_user(), 'edit_class', f'class {cid}')
        return jsonify({'status': 'success'})

    # ─── Teacher profile ─────────────────────────────────────
    @app.route('/profile')
    @login_required
    def profile_page():
        return render_template('profile.html')

    @app.route('/api/profile', methods=['GET', 'POST'])
    @login_required
    def profile():
        user = get_current_user()
        db = get_db()
        if request.method == 'POST':
            name  = request.form.get('name', '').strip()
            email = request.form.get('email', '').strip()
            if not name or not email:
                db.close()
                return jsonify({'status': 'error', 'message': 'Name and email required'}), 400
            try:
                _execute(db, "UPDATE users SET name=%s, email=%s WHERE id=%s",
                         (name, email, user['id']))
                db.commit()
            except Exception as e:
                db.close()
                return jsonify({'status': 'error', 'message': str(e)}), 400
            session['user_name'] = name
            db.close()
            log_action(user, 'update_profile', name)
            return jsonify({'status': 'success'})

        stats = {}
        if user['role'] != 'admin':
            r = _fetchone(db, "SELECT COUNT(*) c FROM courses WHERE teacher_id=%s", (user['id'],))
            stats['course_count'] = r['c'] if r else 0
        r = _fetchone(db, "SELECT COUNT(*) c FROM attendance_sessions WHERE teacher_id=%s", (user['id'],))
        stats['session_count'] = r['c'] if r else 0
        db.close()
        return jsonify({**user, 'stats': stats})

    @app.route('/api/profile/password', methods=['POST'])
    @login_required
    def change_password():
        user = get_current_user()
        current = request.form.get('current', '')
        new = request.form.get('new', '')
        if len(new) < 6:
            return jsonify({'status': 'error', 'message': 'New password must be at least 6 characters'}), 400
        db = get_db()
        row = _fetchone(db, "SELECT password FROM users WHERE id=%s", (user['id'],))
        if row['password'] != hash_password(current):
            db.close()
            return jsonify({'status': 'error', 'message': 'Current password is incorrect'}), 400
        _execute(db, "UPDATE users SET password=%s WHERE id=%s", (hash_password(new), user['id']))
        db.commit()
        db.close()
        log_action(user, 'change_password', '')
        return jsonify({'status': 'success'})

    # ─── Dashboard ───────────────────────────────────────────
    @app.route('/api/dashboard')
    @login_required
    def dashboard():
        user = get_current_user()
        db = get_db()
        today = datetime.now().strftime("%Y-%m-%d")
        is_admin = user['role'] == 'admin'

        if is_admin:
            r = _fetchone(db,
                "SELECT COUNT(*) c FROM attendance_sessions WHERE date(started_at)=%s", (today,))
        else:
            r = _fetchone(db,
                "SELECT COUNT(*) c FROM attendance_sessions WHERE date(started_at)=%s AND teacher_id=%s",
                (today, user['id']))
        sessions_today = r['c'] if r else 0

        if is_admin:
            r = _fetchone(db, "SELECT COUNT(*) c FROM courses")
        else:
            r = _fetchone(db, "SELECT COUNT(*) c FROM courses WHERE teacher_id=%s", (user['id'],))
        course_count = r['c'] if r else 0

        r = _fetchone(db, "SELECT COUNT(*) c FROM students")
        student_count = r['c'] if r else 0

        r = _fetchone(db, "SELECT COUNT(*) c FROM students WHERE registered=1")
        registered_count = r['c'] if r else 0

        if is_admin:
            rate_row = _fetchone(db, '''
                SELECT COUNT(*) total,
                       SUM(CASE WHEN sa.status='Present' THEN 1 ELSE 0 END) present
                FROM session_attendance sa
                JOIN attendance_sessions s ON s.id=sa.session_id
                WHERE date(s.started_at)=%s
            ''', (today,))
        else:
            rate_row = _fetchone(db, '''
                SELECT COUNT(*) total,
                       SUM(CASE WHEN sa.status='Present' THEN 1 ELSE 0 END) present
                FROM session_attendance sa
                JOIN attendance_sessions s ON s.id=sa.session_id
                WHERE date(s.started_at)=%s AND s.teacher_id=%s
            ''', (today, user['id']))
        total   = rate_row['total']   if rate_row and rate_row['total']   else 0
        present = rate_row['present'] if rate_row and rate_row['present'] else 0
        rate = round(present / total * 100, 1) if total else 0.0

        if is_admin:
            recent = _fetchall(db, '''
                SELECT s.id, s.started_at, s.ended_at, c.name course_name, c.code,
                       (SELECT COUNT(*) FROM session_attendance WHERE session_id=s.id AND status='Present') present,
                       (SELECT COUNT(*) FROM session_attendance WHERE session_id=s.id) total
                FROM attendance_sessions s LEFT JOIN courses c ON c.id=s.course_id
                ORDER BY s.id DESC LIMIT 8
            ''')
        else:
            recent = _fetchall(db, '''
                SELECT s.id, s.started_at, s.ended_at, c.name course_name, c.code,
                       (SELECT COUNT(*) FROM session_attendance WHERE session_id=s.id AND status='Present') present,
                       (SELECT COUNT(*) FROM session_attendance WHERE session_id=s.id) total
                FROM attendance_sessions s LEFT JOIN courses c ON c.id=s.course_id
                WHERE s.teacher_id=%s ORDER BY s.id DESC LIMIT 8
            ''', (user['id'],))
        db.close()

        return jsonify({
            'role': user['role'], 'sessions_today': sessions_today, 'course_count': course_count,
            'student_count': student_count, 'registered_count': registered_count,
            'attendance_rate_today': rate,
            'recent': [{**r, 'started_at': str(r['started_at']),
                        'ended_at': str(r['ended_at']) if r['ended_at'] else ''} for r in recent]
        })

    # ─── Audit log (admin) ───────────────────────────────────
    @app.route('/api/admin/audit')
    @admin_required
    def admin_audit():
        """Audit log, newest first, with optional action and date-range filters."""
        action = (request.args.get('action') or '').strip()
        start = (request.args.get('start') or '').strip()
        end = (request.args.get('end') or '').strip()
        where, params = [], []
        if action:
            where.append("action = %s")
            params.append(action)
        if start:
            where.append("date(created_at) >= date(%s)")
            params.append(start)
        if end:
            where.append("date(created_at) <= date(%s)")
            params.append(end)
        sql = "SELECT user_name, action, details, created_at FROM audit_log"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY id DESC LIMIT 500"
        db = get_db()
        rows = _fetchall(db, sql, tuple(params))
        db.close()
        return jsonify([{**r, 'created_at': str(r['created_at'])} for r in rows])

    @app.route('/api/admin/audit/actions')
    @admin_required
    def admin_audit_actions():
        """Distinct action names present in the audit log, for the filter dropdown."""
        db = get_db()
        rows = _fetchall(db, "SELECT DISTINCT action FROM audit_log ORDER BY action")
        db.close()
        return jsonify([r['action'] for r in rows])

    # ─── DB Insights (admin): each metric is a real JOIN/GROUP BY query ──
    @app.route('/api/admin/insights')
    @admin_required
    def admin_insights():
        """Institution-wide metrics, computed entirely in SQL (no Python maths):
           average grade per course, attendance % per class, sessions per teacher."""
        db = get_db()

        # Average grade per course — JOIN grades to courses, GROUP BY course,
        # AVG of the percentage score. Only scored entries count.
        avg_grade = _fetchall(db, '''
            SELECT c.code, c.name AS course,
                   COUNT(g.id)                                AS graded_entries,
                   ROUND(AVG(g.score / g.max_score * 100), 1) AS avg_percent
            FROM courses c
            LEFT JOIN grades g ON g.course_id = c.id AND g.score IS NOT NULL
            GROUP BY c.id, c.code, c.name
            ORDER BY avg_percent DESC
        ''')

        # Attendance % per class — JOIN class -> sessions -> session_attendance,
        # GROUP BY class, AVG of (status='Present') as a percentage.
        attendance_by_class = _fetchall(db, '''
            SELECT cl.name AS class_name,
                   COUNT(DISTINCT ses.id)                        AS sessions,
                   COUNT(sa.id)                                  AS marks,
                   ROUND(AVG(sa.status = 'Present') * 100, 1)    AS attendance_percent
            FROM classes cl
            LEFT JOIN attendance_sessions ses ON ses.class_id = cl.id
            LEFT JOIN session_attendance  sa  ON sa.session_id = ses.id
            GROUP BY cl.id, cl.name
            ORDER BY attendance_percent DESC
        ''')

        # Sessions per teacher — JOIN sessions to users (teacher), GROUP BY teacher.
        sessions_by_teacher = _fetchall(db, '''
            SELECT u.name AS teacher,
                   COUNT(ses.id)                              AS session_count,
                   COUNT(DISTINCT ses.course_id)             AS courses_taught
            FROM users u
            LEFT JOIN attendance_sessions ses ON ses.teacher_id = u.id
            WHERE u.role IN ('teacher', 'admin')
            GROUP BY u.id, u.name
            HAVING COUNT(ses.id) > 0
            ORDER BY session_count DESC
        ''')

        def fnum(v):
            return float(v) if v is not None else 0.0
        db.close()
        return jsonify({
            'avg_grade_per_course': [
                {'code': r['code'] or '', 'course': r['course'],
                 'graded_entries': r['graded_entries'],
                 'avg_percent': fnum(r['avg_percent'])} for r in avg_grade],
            'attendance_per_class': [
                {'class_name': r['class_name'], 'sessions': r['sessions'],
                 'marks': r['marks'],
                 'attendance_percent': fnum(r['attendance_percent'])} for r in attendance_by_class],
            'sessions_per_teacher': [
                {'teacher': r['teacher'], 'session_count': r['session_count'],
                 'courses_taught': r['courses_taught']} for r in sessions_by_teacher],
        })

    # ─── Grade change history (from audit_log, filtered to grade actions) ──
    @app.route('/api/course/<int:course_id>/grade_history')
    @permission_required('grade.view')
    @course_owner_required
    def grade_history(course_id):
        """History of grade changes for a course (optionally one student/component),
        read from the audit entries written by the grade triggers."""
        student_id = request.args.get('student_id')
        component = request.args.get('component')
        # The trigger records 'student <id>, course <course_id>, component <name>: ...'
        like = f"%course {course_id}%"
        clauses = ["action IN ('GRADE_INSERT','GRADE_UPDATE')", "details LIKE %s"]
        params = [like]
        if student_id:
            clauses.append("details LIKE %s")
            params.append(f"student {int(student_id)},%")
        if component:
            clauses.append("details LIKE %s")
            params.append(f"%component {component}:%")
        db = get_db()
        rows = _fetchall(db,
            "SELECT user_name, action, details, created_at FROM audit_log "
            "WHERE " + " AND ".join(clauses) + " ORDER BY id DESC LIMIT 200",
            tuple(params))
        db.close()
        return jsonify([{**r, 'created_at': str(r['created_at'])} for r in rows])

    # ─── Timetable ───────────────────────────────────────────
    @app.route('/api/admin/timetable', methods=['GET', 'POST'])
    @admin_required
    def admin_timetable():
        db = get_db()
        if request.method == 'POST':
            d = request.form
            _execute(db,
                "INSERT INTO timetable (course_id, day_of_week, start_time, end_time, room) "
                "VALUES (%s,%s,%s,%s,%s)",
                (d['course_id'], int(d['day_of_week']), d['start_time'],
                 d.get('end_time', ''), d.get('room', '')))
            db.commit()
            db.close()
            log_action(get_current_user(), 'add_timetable', '')
            return jsonify({'status': 'success'})
        rows = _fetchall(db, '''
            SELECT t.id, t.day_of_week, t.start_time, t.end_time, t.room,
                   c.name course_name, c.code, u.name teacher_name
            FROM timetable t LEFT JOIN courses c ON c.id=t.course_id
            LEFT JOIN users u ON u.id=c.teacher_id
            ORDER BY t.day_of_week, t.start_time
        ''')
        db.close()
        return jsonify([{**r, 'day_name': DAYS[r['day_of_week']] if 0 <= r['day_of_week'] < 7 else '?'}
                        for r in rows])

    @app.route('/api/admin/timetable/<int:tid>', methods=['DELETE'])
    @admin_required
    def delete_timetable(tid):
        db = get_db()
        _execute(db, "DELETE FROM timetable WHERE id=%s", (tid,))
        db.commit()
        db.close()
        return jsonify({'status': 'success'})

    # ─── Grades (teacher/admin manage; students view via /api/student API) ───
    @app.route('/api/course/<int:course_id>/grades', methods=['GET'])
    @permission_required('grade.view')
    @course_owner_required
    def course_grades(course_id):
        """List all grade entries for every student in a course."""
        db = get_db()
        rows = _fetchall(db, '''
            SELECT s.id AS student_id, s.name, s.roll_no, s.prn,
                   g.id AS grade_id, g.component, g.score, g.max_score,
                   g.grade, g.remarks, g.updated_at
            FROM students s
            JOIN course_students cs ON cs.student_id = s.id AND cs.course_id = %s
            LEFT JOIN grades g ON g.student_id = s.id AND g.course_id = %s
            ORDER BY s.roll_no, s.name, g.component
        ''', (course_id, course_id))
        db.close()
        return jsonify([{
            'student_id': r['student_id'], 'name': r['name'],
            'roll_no': r['roll_no'] or '', 'prn': r['prn'] or '',
            'grade_id': r['grade_id'], 'component': r['component'] or '',
            'score': float(r['score']) if r['score'] is not None else None,
            'max_score': float(r['max_score']) if r['max_score'] is not None else None,
            'grade': r['grade'] or '', 'remarks': r['remarks'] or '',
            'updated_at': str(r['updated_at']) if r['updated_at'] else '',
        } for r in rows])

    @app.route('/api/course/<int:course_id>/grades', methods=['POST'])
    @permission_required('grade.edit')
    @course_owner_required
    def save_grade(course_id):
        """Create or update a grade entry for a student in a course."""
        user = get_current_user()
        d = request.form
        student_id = d.get('student_id')
        component = (d.get('component') or '').strip()
        if not student_id or not component:
            return jsonify({'status': 'error', 'message': 'student_id and component required'}), 400
        try:
            student_id = int(student_id)
        except ValueError:
            return jsonify({'status': 'error', 'message': 'student_id must be a number'}), 400

        # grades.score / max_score are DECIMAL(6,2): cap at 9999.99 to avoid overflow errors.
        try:
            max_score = float(d.get('max_score') or 100)
        except ValueError:
            return jsonify({'status': 'error', 'message': 'Max score must be a number'}), 400
        if not 0 < max_score <= 9999.99:
            return jsonify({'status': 'error',
                            'message': 'Max score must be greater than 0 and at most 9999.99'}), 400
        score = d.get('score')
        if score in (None, ''):
            score = None
        else:
            try:
                score = float(score)
            except ValueError:
                return jsonify({'status': 'error', 'message': 'Score must be a number'}), 400
            if not 0 <= score <= max_score:  # also rejects NaN
                return jsonify({'status': 'error',
                                'message': f'Score must be between 0 and the max score ({max_score:g})'}), 400
        grade = (d.get('grade') or '').strip()
        remarks = (d.get('remarks') or '').strip()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        db = get_db()
        enrolled = _fetchone(db,
            "SELECT 1 AS ok FROM course_students WHERE course_id=%s AND student_id=%s",
            (course_id, student_id))
        if not enrolled:
            db.close()
            return jsonify({'status': 'error', 'message': 'Student not in this course'}), 400

        # Read the prior score so the audit entry can show old -> new, and decide
        # whether this will be an INSERT or an UPDATE.
        prior = _fetchone(db,
            "SELECT score FROM grades WHERE student_id=%s AND course_id=%s AND component=%s",
            (student_id, course_id, component))
        is_update = prior is not None
        old_score = prior['score'] if prior else None

        try:
            _execute(db, '''
                INSERT INTO grades
                    (student_id, course_id, component, score, max_score, grade, remarks, updated_by, updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE
                    score=VALUES(score), max_score=VALUES(max_score),
                    grade=VALUES(grade), remarks=VALUES(remarks),
                    updated_by=VALUES(updated_by), updated_at=VALUES(updated_at)
            ''', (student_id, course_id, component, score, max_score,
                  grade or None, remarks or None, user['id'], now))
            db.commit()
        except Exception as e:
            try:
                db.rollback()
            except Exception:
                pass
            db.close()
            # The CHECK constraint chk_grade_score (score within 0..max_score)
            # is the database's last-line guard. Translate its violation (MySQL
            # error 3819) into a friendly message instead of a 500.
            if '3819' in str(e) or 'chk_grade_score' in str(e):
                return jsonify({'status': 'error',
                                'message': 'Score must be between 0 and the max score.'}), 400
            return jsonify({'status': 'error', 'message': f'Could not save grade: {e}'}), 400

        # Auditing: the DB triggers (trg_grades_audit_insert / trg_grades_audit)
        # record this automatically WHEN THEY ARE INSTALLED. If they are not
        # (e.g. the server flag log_bin_trust_function_creators was off, error
        # 1419), fall back to logging the same entry from the app so History and
        # the GRADE_* filters still work. The check prevents double-logging.
        if not grade_triggers_installed(db):
            def _fmt(v):
                return 'NULL' if v is None else (f'{float(v):g}')
            if is_update:
                details = (f'student {student_id}, course {course_id}, component {component}: '
                           f'score {_fmt(old_score)} -> {_fmt(score)} (max {max_score:g})')
                action = 'GRADE_UPDATE'
            else:
                details = (f'student {student_id}, course {course_id}, component {component}: '
                           f'set {_fmt(score)}/{max_score:g}')
                action = 'GRADE_INSERT'
            log_action(user, action, details)
        db.close()
        return jsonify({'status': 'success'})

    @app.route('/api/grades/<int:grade_id>', methods=['DELETE'])
    @permission_required('grade.edit')
    def delete_grade(grade_id):
        user = get_current_user()
        db = get_db()
        row = _fetchone(db, "SELECT course_id FROM grades WHERE id=%s", (grade_id,))
        if not row:
            db.close()
            return jsonify({'status': 'error', 'message': 'Grade not found'}), 404
        error = check_course_access(user, row['course_id'])
        if error:
            db.close()
            return error
        _execute(db, "DELETE FROM grades WHERE id=%s", (grade_id,))
        db.commit()
        db.close()
        log_action(user, 'delete_grade', f'grade {grade_id} course {row["course_id"]}')
        return jsonify({'status': 'success'})

    @app.route('/api/my_timetable')
    @login_required
    def my_timetable():
        user = get_current_user()
        db = get_db()
        if user['role'] == 'admin':
            rows = _fetchall(db, '''
                SELECT t.id, t.course_id, t.day_of_week, t.start_time, t.end_time, t.room,
                       c.name course_name, c.code FROM timetable t
                LEFT JOIN courses c ON c.id=t.course_id ORDER BY t.day_of_week, t.start_time
            ''')
        else:
            rows = _fetchall(db, '''
                SELECT t.id, t.course_id, t.day_of_week, t.start_time, t.end_time, t.room,
                       c.name course_name, c.code FROM timetable t
                JOIN courses c ON c.id=t.course_id
                WHERE c.teacher_id=%s ORDER BY t.day_of_week, t.start_time
            ''', (user['id'],))
        db.close()
        return jsonify([{**r, 'day_name': DAYS[r['day_of_week']] if 0 <= r['day_of_week'] < 7 else '?'}
                        for r in rows])
