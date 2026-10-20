"""
New routes for multi-user GWASOAT system — MySQL backend.
Handles: pages, courses, admin CRUD, course-based attendance.
"""

import sys
import os
import io
import csv
import base64
from datetime import datetime
from flask import render_template, request, jsonify, session, redirect, send_file

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from models import get_db, hash_password, log_action, ensure_student_account
from database import _fetchone, _fetchall, _execute
from auth import (login_required, admin_required, get_current_user,
                  can_manage_course, course_owner_required, check_course_access)
from network import esp32_request


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


def setup_new_routes(app):
    """Register all new multi-user routes."""

    # ─── Pages ───────────────────────────────────────────────
    @app.route('/')
    def root():
        if session.get('user_id'):
            return redirect('/home')
        return redirect('/login')

    @app.route('/home')
    @login_required
    def home_page():
        return render_template('home.html')

    @app.route('/course/<int:course_id>')
    @login_required
    def course_page(course_id):
        # Owner-gate the HTML page: a non-owner teacher is redirected to /home
        # (not /login and not a JSON 403). Missing course also redirects home.
        user = get_current_user()
        db = get_db()
        course = _fetchone(db, "SELECT id, teacher_id FROM courses WHERE id=%s", (course_id,))
        db.close()
        if not course or not can_manage_course(user, course):
            return redirect('/home')
        return render_template('course.html')

    @app.route('/admin')
    @admin_required
    def admin_page():
        return render_template('admin.html')

    # ─── Teacher: My Courses ─────────────────────────────────
    @app.route('/api/my_courses')
    @login_required
    def my_courses():
        user = get_current_user()
        db = get_db()
        if user['role'] == 'admin':
            rows = _fetchall(db, '''
                SELECT c.id, c.name, c.code,
                       (SELECT COUNT(*) FROM course_students WHERE course_id=c.id) as student_count,
                       cl.name as class_name
                FROM courses c LEFT JOIN classes cl ON cl.id = (
                    SELECT s.class_id FROM course_students cs
                    JOIN students s ON s.id=cs.student_id WHERE cs.course_id=c.id LIMIT 1
                ) ORDER BY c.name
            ''')
        else:
            rows = _fetchall(db, '''
                SELECT c.id, c.name, c.code,
                       (SELECT COUNT(*) FROM course_students WHERE course_id=c.id) as student_count,
                       cl.name as class_name
                FROM courses c LEFT JOIN classes cl ON cl.id = (
                    SELECT s.class_id FROM course_students cs
                    JOIN students s ON s.id=cs.student_id WHERE cs.course_id=c.id LIMIT 1
                ) WHERE c.teacher_id = %s ORDER BY c.name
            ''', (user['id'],))
        db.close()
        return jsonify(rows)

    # ─── Course Detail ───────────────────────────────────────
    @app.route('/api/course/<int:course_id>')
    @login_required
    @course_owner_required
    def course_detail(course_id):
        db = get_db()
        course = _fetchone(db, '''
            SELECT c.*, u.name as teacher_name FROM courses c
            LEFT JOIN users u ON u.id = c.teacher_id WHERE c.id = %s
        ''', (course_id,))
        if not course:
            db.close()
            return jsonify({'error': 'Not found'}), 404

        count_row = _fetchone(db,
            "SELECT COUNT(*) as c FROM course_students WHERE course_id=%s", (course_id,))
        student_count = count_row['c'] if count_row else 0

        batches = _fetchall(db, '''
            SELECT DISTINCT b.id, b.name, COUNT(cs.student_id) as count
            FROM batches b
            JOIN students s ON s.batch_id = b.id
            JOIN course_students cs ON cs.student_id = s.id AND cs.course_id = %s
            GROUP BY b.id ORDER BY b.name
        ''', (course_id,))

        class_row = _fetchone(db, '''
            SELECT cl.name FROM classes cl
            JOIN students s ON s.class_id = cl.id
            JOIN course_students cs ON cs.student_id = s.id AND cs.course_id = %s
            LIMIT 1
        ''', (course_id,))

        db.close()
        return jsonify({
            'id': course['id'], 'name': course['name'], 'code': course['code'],
            'teacher_id': course['teacher_id'],
            'can_manage_grades': can_manage_course(get_current_user(), course),
            'teacher_name': course['teacher_name'], 'student_count': student_count,
            'class_name': class_row['name'] if class_row else '',
            'batches': [{'id': b['id'], 'name': b['name'], 'count': b['count']} for b in batches]
        })

    @app.route('/api/course/<int:course_id>/students')
    @login_required
    @course_owner_required
    def course_students(course_id):
        batch = request.args.get('batch', 'all')
        db = get_db()
        if batch == 'all':
            rows = _fetchall(db, '''
                SELECT s.id, s.name, s.prn, s.roll_no, s.registered, b.name as batch_name
                FROM students s
                JOIN course_students cs ON cs.student_id = s.id AND cs.course_id = %s
                LEFT JOIN batches b ON b.id = s.batch_id
                ORDER BY s.roll_no, s.name
            ''', (course_id,))
        else:
            rows = _fetchall(db, '''
                SELECT s.id, s.name, s.prn, s.roll_no, s.registered, b.name as batch_name
                FROM students s
                JOIN course_students cs ON cs.student_id = s.id AND cs.course_id = %s
                LEFT JOIN batches b ON b.id = s.batch_id
                WHERE s.batch_id = %s
                ORDER BY s.roll_no, s.name
            ''', (course_id, int(batch)))
        db.close()
        return jsonify(rows)

    @app.route('/api/course/<int:course_id>/add_student', methods=['POST'])
    @login_required
    @course_owner_required
    def course_add_student(course_id):
        data = request.form
        name = data.get('name', '').strip()
        student_id = data.get('id', '').strip()
        prn = data.get('prn', '').strip()
        roll_no = data.get('roll_no', '').strip()
        if not name or not student_id:
            return jsonify({'status': 'error', 'message': 'Name and ID required'}), 400
        try:
            sid = int(student_id)
        except ValueError:
            return jsonify({'status': 'error', 'message': 'ID must be a number'}), 400
        db = get_db()
        try:
            existing = _fetchone(db, "SELECT id FROM students WHERE id=%s", (sid,))
            if not existing:
                _execute(db, "INSERT INTO students (id, name, prn, roll_no, registered) VALUES (%s,%s,%s,%s,0)",
                         (sid, name, prn, roll_no))
            _execute(db,
                "INSERT IGNORE INTO course_students (course_id, student_id) VALUES (%s,%s)",
                (course_id, sid))
            # Create a login account for this student (role=student)
            ensure_student_account(db, sid, name)
            db.commit()
        except Exception as e:
            db.close()
            return jsonify({'status': 'error', 'message': str(e)}), 500
        db.close()
        log_action(get_current_user(), 'add_student', f'student {sid} ({name}) to course {course_id}')
        return jsonify({'status': 'success', 'student_id': sid})

    # ─── Course Attendance ───────────────────────────────────
    @app.route('/api/course/<int:course_id>/attendance/start')
    @login_required
    @course_owner_required
    def course_start_attendance(course_id):
        user = get_current_user()
        batch = request.args.get('batch', 'all')
        description = request.args.get('description', '').strip()
        db = get_db()

        if batch == 'all':
            students = _fetchall(db, '''
                SELECT s.id, s.name, s.class_id FROM students s
                JOIN course_students cs ON cs.student_id = s.id AND cs.course_id = %s
                ORDER BY s.id
            ''', (course_id,))
        else:
            students = _fetchall(db, '''
                SELECT s.id, s.name, s.class_id FROM students s
                JOIN course_students cs ON cs.student_id = s.id AND cs.course_id = %s
                WHERE s.batch_id = %s ORDER BY s.id
            ''', (course_id, int(batch)))

        if batch == 'all':
            templates = _fetchall(db, '''
                SELECT ft.student_id, ft.template_data, s.name FROM fingerprint_templates ft
                JOIN students s ON s.id = ft.student_id
                JOIN course_students cs ON cs.student_id = ft.student_id AND cs.course_id = %s
            ''', (course_id,))
        else:
            templates = _fetchall(db, '''
                SELECT ft.student_id, ft.template_data, s.name FROM fingerprint_templates ft
                JOIN students s ON s.id = ft.student_id
                JOIN course_students cs ON cs.student_id = ft.student_id AND cs.course_id = %s
                WHERE s.batch_id = %s
            ''', (course_id, int(batch)))

        esp32_request('/clear_attendance', timeout=3)
        import requests as req_lib
        from config import get_config
        ip = get_config().get("esp32_ip", "192.168.0.103")
        try:
            req_lib.post(f"http://{ip}/command", json={"cmd": "clear_sensor"}, timeout=8)
        except Exception:
            pass

        loaded = 0
        for tpl in templates:
            b64 = base64.b64encode(tpl["template_data"]).decode()
            try:
                payload = {"cmd": "upload_template", "student_id": tpl["student_id"],
                           "class_id": 0, "name": tpl["name"], "template": b64}
                r = req_lib.post(f"http://{ip}/command", json=payload, timeout=20)
                if r.status_code == 200 and r.json().get("status") == "success":
                    loaded += 1
            except Exception:
                pass

        esp32_request('/start_attendance', timeout=5)

        class_id = students[0]['class_id'] if students else None
        batch_id = int(batch) if batch != 'all' else None
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        session_id = _execute(db,
            "INSERT INTO attendance_sessions "
            "(course_id, teacher_id, class_id, batch_id, description, started_at) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            (course_id, user['id'], class_id, batch_id, description, now))

        for s in students:
            _execute(db,
                "INSERT IGNORE INTO session_attendance "
                "(session_id, student_id, student_name, status) VALUES (%s,%s,%s,%s)",
                (session_id, s['id'], s['name'], '--'))
        db.commit()

        session['active_session_id'] = session_id
        session['active_course_id'] = course_id

        db.close()
        log_action(user, 'start_attendance',
                   f'course {course_id}, session {session_id}, {len(students)} students, {loaded} templates loaded')
        return jsonify({'status': 'success', 'session_id': session_id,
                        'loaded': loaded, 'students': len(students)})

    @app.route('/api/course/<int:course_id>/attendance/stop')
    @login_required
    @course_owner_required
    def course_stop_attendance(course_id):
        db = get_db()
        session_id = session.get('active_session_id')
        if session_id:
            _execute(db,
                "UPDATE session_attendance SET status='Absent' "
                "WHERE session_id=%s AND status='--'", (session_id,))
            _execute(db,
                "UPDATE attendance_sessions SET ended_at=%s WHERE id=%s",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), session_id))
            db.commit()
        session.pop('active_session_id', None)
        session.pop('active_course_id', None)
        esp32_request('/stop_attendance', timeout=3)
        db.close()
        log_action(get_current_user(), 'stop_attendance', f'course {course_id}, session {session_id}')
        return jsonify({'status': 'success'})

    @app.route('/api/course/<int:course_id>/sessions')
    @login_required
    @course_owner_required
    def course_sessions(course_id):
        db = get_db()
        rows = _fetchall(db,
            "SELECT id, started_at, ended_at, description FROM attendance_sessions "
            "WHERE course_id=%s ORDER BY id DESC", (course_id,))
        db.close()
        return jsonify([{**r, 'started_at': str(r['started_at']),
                         'ended_at': str(r['ended_at']) if r['ended_at'] else ''} for r in rows])

    @app.route('/api/session/<int:session_id>/description', methods=['POST'])
    @login_required
    def update_session_description(session_id):
        err = _session_course_guard(get_current_user(), session_id)
        if err:
            return err
        description = request.form.get('description', '').strip()
        db = get_db()
        _execute(db, "UPDATE attendance_sessions SET description=%s WHERE id=%s",
                 (description, session_id))
        db.commit()
        db.close()
        log_action(get_current_user(), 'session_topics', f'session {session_id}')
        return jsonify({'status': 'success'})

    @app.route('/api/session/<int:session_id>/attendance')
    @login_required
    def session_attendance_route(session_id):
        err = _session_course_guard(get_current_user(), session_id)
        if err:
            return err
        db = get_db()
        rows = _fetchall(db, '''
            SELECT sa.student_id, sa.student_name as name, sa.status, sa.marked_at,
                   s.roll_no FROM session_attendance sa
            LEFT JOIN students s ON s.id = sa.student_id
            WHERE sa.session_id = %s ORDER BY s.roll_no, sa.student_name
        ''', (session_id,))
        db.close()
        return jsonify([{**r, 'marked_at': str(r['marked_at']) if r['marked_at'] else ''} for r in rows])

    @app.route('/api/session/<int:session_id>/export')
    @login_required
    def session_export(session_id):
        err = _session_course_guard(get_current_user(), session_id)
        if err:
            return err
        db = get_db()
        sess = _fetchone(db,
            "SELECT started_at, description FROM attendance_sessions WHERE id=%s", (session_id,))
        rows = _fetchall(db, '''
            SELECT sa.student_name, s.roll_no, s.prn, sa.status, sa.marked_at
            FROM session_attendance sa LEFT JOIN students s ON s.id=sa.student_id
            WHERE sa.session_id=%s ORDER BY s.roll_no
        ''', (session_id,))
        db.close()
        output = io.StringIO()
        writer = csv.writer(output)
        if sess:
            writer.writerow(['Session Date', str(sess['started_at']) or ''])
            writer.writerow(['Topics Covered', sess['description'] or ''])
            writer.writerow([])
        writer.writerow(['Roll No', 'PRN', 'Name', 'Status', 'Marked At'])
        for r in rows:
            writer.writerow([r['roll_no'] or '', r['prn'] or '', r['student_name'],
                             r['status'], str(r['marked_at']) if r['marked_at'] else ''])
        output.seek(0)
        return send_file(io.BytesIO(output.getvalue().encode()), mimetype='text/csv',
                         as_attachment=True, download_name=f'attendance_{session_id}.csv')

    # ─── Admin CRUD ──────────────────────────────────────────
    @app.route('/api/admin/teachers', methods=['GET', 'POST'])
    @admin_required
    def admin_teachers():
        db = get_db()
        if request.method == 'POST':
            data = request.form
            _execute(db,
                "INSERT INTO users (name, email, password, role, created_at) VALUES (%s,%s,%s,%s,%s)",
                (data['name'], data['email'], hash_password(data.get('password', 'teacher123')),
                 'teacher', datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            db.commit()
            db.close()
            return jsonify({'status': 'success'})
        rows = _fetchall(db,
            "SELECT id, name, email, role FROM users "
            "WHERE role IN ('admin', 'teacher') ORDER BY name")
        db.close()
        return jsonify(rows)

    @app.route('/api/admin/teachers/<int:uid>', methods=['DELETE'])
    @admin_required
    def admin_delete_teacher(uid):
        db = get_db()
        _execute(db, "DELETE FROM users WHERE id=%s AND role='teacher'", (uid,))
        db.commit()
        db.close()
        return jsonify({'status': 'success'})

    @app.route('/api/admin/teachers/<int:uid>/reset_password', methods=['POST'])
    @admin_required
    def admin_reset_teacher_password(uid):
        """Reset a teacher's login password to the default (teacher123)."""
        db = get_db()
        teacher = _fetchone(db,
            "SELECT id, email FROM users WHERE id=%s AND role='teacher'", (uid,))
        if not teacher:
            db.close()
            return jsonify({'status': 'error', 'message': 'Teacher not found'}), 404
        _execute(db, "UPDATE users SET password=%s WHERE id=%s",
                 (hash_password('teacher123'), uid))
        db.commit()
        db.close()
        log_action(get_current_user(), 'reset_teacher_password', f'teacher {uid}')
        return jsonify({'status': 'success', 'email': teacher['email'],
                        'password': 'teacher123'})

    @app.route('/api/admin/departments', methods=['GET', 'POST'])
    @admin_required
    def admin_departments():
        db = get_db()
        if request.method == 'POST':
            _execute(db, "INSERT INTO departments (name) VALUES (%s)", (request.form['name'],))
            db.commit()
            db.close()
            return jsonify({'status': 'success'})
        rows = _fetchall(db, "SELECT * FROM departments ORDER BY name")
        db.close()
        return jsonify(rows)

    @app.route('/api/admin/departments/<int:did>', methods=['DELETE'])
    @admin_required
    def admin_delete_dept(did):
        db = get_db()
        _execute(db, "DELETE FROM departments WHERE id=%s", (did,))
        db.commit()
        db.close()
        return jsonify({'status': 'success'})

    @app.route('/api/admin/classes', methods=['GET', 'POST'])
    @admin_required
    def admin_classes():
        db = get_db()
        if request.method == 'POST':
            data = request.form
            _execute(db, "INSERT INTO classes (name, year, department_id) VALUES (%s,%s,%s)",
                     (data['name'], data.get('year') or None, data.get('department_id') or None))
            db.commit()
            db.close()
            return jsonify({'status': 'success'})
        rows = _fetchall(db, '''
            SELECT c.id, c.name, c.year, c.department_id,
                   COALESCE(d.name, '') as dept_name,
                   COALESCE(GROUP_CONCAT(b.name), '') as batches
            FROM classes c LEFT JOIN departments d ON d.id=c.department_id
            LEFT JOIN batches b ON b.class_id=c.id
            GROUP BY c.id ORDER BY c.name
        ''')
        db.close()
        return jsonify([{'id': r['id'], 'name': r['name'], 'year': r['year'] or '',
                         'dept_name': r['dept_name'], 'batches': r['batches']} for r in rows])

    @app.route('/api/admin/classes/<int:cid>', methods=['DELETE'])
    @admin_required
    def admin_delete_class(cid):
        db = get_db()
        _execute(db, "DELETE FROM classes WHERE id=%s", (cid,))
        db.commit()
        db.close()
        return jsonify({'status': 'success'})

    @app.route('/api/admin/batches', methods=['POST'])
    @admin_required
    def admin_add_batch():
        data = request.form
        db = get_db()
        _execute(db, "INSERT INTO batches (name, class_id) VALUES (%s,%s)",
                 (data['name'], data['class_id']))
        db.commit()
        db.close()
        return jsonify({'status': 'success'})

    @app.route('/api/admin/classes/<int:cid>/batches')
    @admin_required
    def admin_class_batches(cid):
        db = get_db()
        rows = _fetchall(db, "SELECT id, name FROM batches WHERE class_id=%s ORDER BY name", (cid,))
        db.close()
        return jsonify(rows)

    @app.route('/api/admin/courses', methods=['GET', 'POST'])
    @admin_required
    def admin_courses():
        db = get_db()
        if request.method == 'POST':
            data = request.form
            _execute(db, "INSERT INTO courses (name, code, teacher_id) VALUES (%s,%s,%s)",
                     (data['name'], data.get('code', ''), data.get('teacher_id') or None))
            db.commit()
            db.close()
            return jsonify({'status': 'success'})
        rows = _fetchall(db, '''
            SELECT c.id, c.name, c.code, c.teacher_id, u.name as teacher_name,
                   (SELECT COUNT(*) FROM course_students WHERE course_id=c.id) as student_count
            FROM courses c LEFT JOIN users u ON u.id=c.teacher_id ORDER BY c.name
        ''')
        db.close()
        return jsonify(rows)

    @app.route('/api/admin/courses/<int:cid>', methods=['DELETE'])
    @admin_required
    def admin_delete_course(cid):
        db = get_db()
        _execute(db, "DELETE FROM courses WHERE id=%s", (cid,))
        db.commit()
        db.close()
        return jsonify({'status': 'success'})

    @app.route('/api/admin/students', methods=['GET', 'POST'])
    @admin_required
    def admin_students():
        db = get_db()
        if request.method == 'POST':
            data = request.form
            sid = int(data['id'])
            _execute(db,
                "INSERT INTO students (id, name, prn, roll_no, class_id, batch_id) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                (sid, data['name'], data.get('prn', ''), data.get('roll_no', ''),
                 data.get('class_id') or None, data.get('batch_id') or None))
            # Create a login account for this student (role=student)
            ensure_student_account(db, sid, data['name'])
            db.commit()
            db.close()
            return jsonify({'status': 'success'})
        rows = _fetchall(db, '''
            SELECT s.id, s.name, s.prn, s.roll_no, s.class_id, s.batch_id, s.registered,
                   COALESCE(c.name, '') as class_name, COALESCE(b.name, '') as batch_name,
                   COALESCE(u.email, '') as login_email
            FROM students s LEFT JOIN classes c ON c.id=s.class_id
            LEFT JOIN batches b ON b.id=s.batch_id
            LEFT JOIN users u ON u.role='student' AND u.student_id=s.id
            ORDER BY s.name
        ''')
        db.close()
        return jsonify([{'id': r['id'], 'name': r['name'], 'prn': r['prn'] or '',
                         'roll_no': r['roll_no'] or '', 'class_name': r['class_name'],
                         'batch_name': r['batch_name'], 'registered': r['registered'],
                         'login_email': r['login_email']} for r in rows])

    @app.route('/api/admin/students/<int:sid>', methods=['DELETE'])
    @admin_required
    def admin_delete_student(sid):
        db = get_db()
        # Remove the linked student login account first (FK: students ← users.student_id)
        _execute(db, "DELETE FROM users WHERE role='student' AND student_id=%s", (sid,))
        _execute(db, "DELETE FROM students WHERE id=%s", (sid,))
        db.commit()
        db.close()
        return jsonify({'status': 'success'})

    @app.route('/api/admin/students/<int:sid>/reset_password', methods=['POST'])
    @admin_required
    def admin_reset_student_password(sid):
        """Reset a student's login password to the default (student<ID>)."""
        db = get_db()
        acct = _fetchone(db,
            "SELECT id, email FROM users WHERE role='student' AND student_id=%s", (sid,))
        if not acct:
            # No account yet — create one
            srow = _fetchone(db, "SELECT name FROM students WHERE id=%s", (sid,))
            if not srow:
                db.close()
                return jsonify({'status': 'error', 'message': 'Student not found'}), 404
            ensure_student_account(db, sid, srow['name'])
            acct = _fetchone(db,
                "SELECT id, email FROM users WHERE role='student' AND student_id=%s", (sid,))
        else:
            _execute(db, "UPDATE users SET password=%s WHERE id=%s",
                     (hash_password(f"student{sid}"), acct['id']))
        db.commit()
        db.close()
        log_action(get_current_user(), 'reset_student_password', f'student {sid}')
        return jsonify({'status': 'success', 'email': acct['email'],
                        'password': f'student{sid}'})

    # ─── Course Student Assignment ───────────────────────────
    @app.route('/api/admin/course/<int:course_id>/students', methods=['GET', 'POST'])
    @admin_required
    def admin_course_students(course_id):
        db = get_db()
        if request.method == 'POST':
            student_id = request.form.get('student_id')
            if student_id:
                _execute(db,
                    "INSERT IGNORE INTO course_students (course_id, student_id) VALUES (%s,%s)",
                    (course_id, int(student_id)))
                db.commit()
            db.close()
            return jsonify({'status': 'success'})
        rows = _fetchall(db, '''
            SELECT s.id, s.name, s.prn, s.roll_no FROM students s
            JOIN course_students cs ON cs.student_id=s.id AND cs.course_id=%s
            ORDER BY s.name
        ''', (course_id,))
        db.close()
        return jsonify(rows)
