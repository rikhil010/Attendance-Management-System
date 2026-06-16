"""
New routes for multi-user GWASOAT system.
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
from models import get_db, hash_password
from auth import login_required, admin_required, get_current_user
from network import esp32_request


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
            rows = db.execute('''
                SELECT c.id, c.name, c.code,
                       (SELECT COUNT(*) FROM course_students WHERE course_id=c.id) as student_count,
                       cl.name as class_name
                FROM courses c LEFT JOIN classes cl ON cl.id = (
                    SELECT s.class_id FROM course_students cs 
                    JOIN students s ON s.id=cs.student_id WHERE cs.course_id=c.id LIMIT 1
                ) ORDER BY c.name
            ''').fetchall()
        else:
            rows = db.execute('''
                SELECT c.id, c.name, c.code,
                       (SELECT COUNT(*) FROM course_students WHERE course_id=c.id) as student_count,
                       cl.name as class_name
                FROM courses c LEFT JOIN classes cl ON cl.id = (
                    SELECT s.class_id FROM course_students cs 
                    JOIN students s ON s.id=cs.student_id WHERE cs.course_id=c.id LIMIT 1
                ) WHERE c.teacher_id = ? ORDER BY c.name
            ''', (user['id'],)).fetchall()
        db.close()
        return jsonify([dict(r) for r in rows])

    # ─── Course Detail ───────────────────────────────────────
    @app.route('/api/course/<int:course_id>')
    @login_required
    def course_detail(course_id):
        db = get_db()
        course = db.execute('''
            SELECT c.*, u.name as teacher_name FROM courses c
            LEFT JOIN users u ON u.id = c.teacher_id WHERE c.id = ?
        ''', (course_id,)).fetchone()
        if not course:
            db.close()
            return jsonify({'error': 'Not found'}), 404
        
        student_count = db.execute(
            "SELECT COUNT(*) as c FROM course_students WHERE course_id=?", (course_id,)
        ).fetchone()['c']
        
        # Get batches for students in this course
        batches = db.execute('''
            SELECT DISTINCT b.id, b.name, COUNT(cs.student_id) as count
            FROM batches b
            JOIN students s ON s.batch_id = b.id
            JOIN course_students cs ON cs.student_id = s.id AND cs.course_id = ?
            GROUP BY b.id ORDER BY b.name
        ''', (course_id,)).fetchall()
        
        # Get class name
        class_row = db.execute('''
            SELECT cl.name FROM classes cl
            JOIN students s ON s.class_id = cl.id
            JOIN course_students cs ON cs.student_id = s.id AND cs.course_id = ?
            LIMIT 1
        ''', (course_id,)).fetchone()
        
        db.close()
        return jsonify({
            'id': course['id'], 'name': course['name'], 'code': course['code'],
            'teacher_name': course['teacher_name'], 'student_count': student_count,
            'class_name': class_row['name'] if class_row else '',
            'batches': [{'id': b['id'], 'name': b['name'], 'count': b['count']} for b in batches]
        })

    @app.route('/api/course/<int:course_id>/students')
    @login_required
    def course_students(course_id):
        batch = request.args.get('batch', 'all')
        db = get_db()
        if batch == 'all':
            rows = db.execute('''
                SELECT s.id, s.name, s.prn, s.roll_no, s.registered, b.name as batch_name
                FROM students s
                JOIN course_students cs ON cs.student_id = s.id AND cs.course_id = ?
                LEFT JOIN batches b ON b.id = s.batch_id
                ORDER BY s.roll_no, s.name
            ''', (course_id,)).fetchall()
        else:
            rows = db.execute('''
                SELECT s.id, s.name, s.prn, s.roll_no, s.registered, b.name as batch_name
                FROM students s
                JOIN course_students cs ON cs.student_id = s.id AND cs.course_id = ?
                LEFT JOIN batches b ON b.id = s.batch_id
                WHERE s.batch_id = ?
                ORDER BY s.roll_no, s.name
            ''', (course_id, int(batch))).fetchall()
        db.close()
        return jsonify([dict(r) for r in rows])

    @app.route('/api/course/<int:course_id>/add_student', methods=['POST'])
    @login_required
    def course_add_student(course_id):
        """Add a new student and link to this course."""
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
        # Check if student ID already exists
        existing = db.execute("SELECT id FROM students WHERE id=?", (sid,)).fetchone()
        if existing:
            # Just link to course
            db.execute("INSERT OR IGNORE INTO course_students (course_id, student_id) VALUES (?,?)", (course_id, sid))
        else:
            # Create student and link
            db.execute("INSERT INTO students (id, name, prn, roll_no) VALUES (?,?,?,?)",
                      (sid, name, prn, roll_no))
            db.execute("INSERT INTO course_students (course_id, student_id) VALUES (?,?)", (course_id, sid))
        db.commit()
        db.close()
        return jsonify({'status': 'success'})

    # ─── Course Attendance ───────────────────────────────────
    @app.route('/api/course/<int:course_id>/attendance/start')
    @login_required
    def course_start_attendance(course_id):
        user = get_current_user()
        batch = request.args.get('batch', 'all')
        db = get_db()
        
        # Get students for this course (filtered by batch if specified)
        if batch == 'all':
            students = db.execute('''
                SELECT s.id, s.name, s.class_id FROM students s
                JOIN course_students cs ON cs.student_id = s.id AND cs.course_id = ?
                ORDER BY s.id
            ''', (course_id,)).fetchall()
        else:
            students = db.execute('''
                SELECT s.id, s.name, s.class_id FROM students s
                JOIN course_students cs ON cs.student_id = s.id AND cs.course_id = ?
                WHERE s.batch_id = ? ORDER BY s.id
            ''', (course_id, int(batch))).fetchall()
        
        # Load templates into sensor
        templates = db.execute('''
            SELECT ft.student_id, ft.template_data, s.name FROM fingerprint_templates ft
            JOIN students s ON s.id = ft.student_id
            JOIN course_students cs ON cs.student_id = ft.student_id AND cs.course_id = ?
        ''' + (' AND s.batch_id = ?' if batch != 'all' else ''),
            (course_id, int(batch)) if batch != 'all' else (course_id,)
        ).fetchall()
        
        # Clear sensor and load templates
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
        
        # Create session
        class_id = students[0]['class_id'] if students else None
        batch_id = int(batch) if batch != 'all' else None
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur = db.execute(
            "INSERT INTO attendance_sessions (course_id, teacher_id, class_id, batch_id, started_at) VALUES (?,?,?,?,?)",
            (course_id, user['id'], class_id, batch_id, now)
        )
        session_id = cur.lastrowid
        
        for s in students:
            db.execute(
                "INSERT OR IGNORE INTO session_attendance (session_id, student_id, student_name, status) VALUES (?,?,?,?)",
                (session_id, s['id'], s['name'], '--')
            )
        db.commit()
        
        # Store active session in app session
        session['active_session_id'] = session_id
        session['active_course_id'] = course_id
        
        db.close()
        return jsonify({'status': 'success', 'session_id': session_id, 'loaded': loaded, 'students': len(students)})

    @app.route('/api/course/<int:course_id>/attendance/stop')
    @login_required
    def course_stop_attendance(course_id):
        db = get_db()
        session_id = session.get('active_session_id')
        if session_id:
            db.execute("UPDATE session_attendance SET status='Absent' WHERE session_id=? AND status='--'", (session_id,))
            db.execute("UPDATE attendance_sessions SET ended_at=? WHERE id=?",
                      (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), session_id))
            db.commit()
        session.pop('active_session_id', None)
        session.pop('active_course_id', None)
        esp32_request('/stop_attendance', timeout=3)
        db.close()
        return jsonify({'status': 'success'})

    @app.route('/api/course/<int:course_id>/sessions')
    @login_required
    def course_sessions(course_id):
        db = get_db()
        rows = db.execute(
            "SELECT id, started_at, ended_at FROM attendance_sessions WHERE course_id=? ORDER BY id DESC",
            (course_id,)
        ).fetchall()
        db.close()
        return jsonify([dict(r) for r in rows])

    @app.route('/api/session/<int:session_id>/attendance')
    @login_required
    def session_attendance(session_id):
        db = get_db()
        rows = db.execute('''
            SELECT sa.student_id, sa.student_name as name, sa.status, sa.marked_at,
                   s.roll_no FROM session_attendance sa
            LEFT JOIN students s ON s.id = sa.student_id
            WHERE sa.session_id = ? ORDER BY s.roll_no, sa.student_name
        ''', (session_id,)).fetchall()
        db.close()
        return jsonify([dict(r) for r in rows])

    @app.route('/api/session/<int:session_id>/export')
    @login_required
    def session_export(session_id):
        db = get_db()
        rows = db.execute('''
            SELECT sa.student_name, s.roll_no, s.prn, sa.status, sa.marked_at
            FROM session_attendance sa LEFT JOIN students s ON s.id=sa.student_id
            WHERE sa.session_id=? ORDER BY s.roll_no
        ''', (session_id,)).fetchall()
        db.close()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Roll No', 'PRN', 'Name', 'Status', 'Marked At'])
        for r in rows:
            writer.writerow([r['roll_no'] or '', r['prn'] or '', r['student_name'], r['status'], r['marked_at'] or ''])
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
            db.execute("INSERT INTO users (name, email, password, role, created_at) VALUES (?,?,?,?,?)",
                      (data['name'], data['email'], hash_password(data.get('password', 'teacher123')),
                       'teacher', datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            db.commit(); db.close()
            return jsonify({'status': 'success'})
        rows = db.execute("SELECT id, name, email, role FROM users ORDER BY name").fetchall()
        db.close()
        return jsonify([dict(r) for r in rows])

    @app.route('/api/admin/teachers/<int:uid>', methods=['DELETE'])
    @admin_required
    def admin_delete_teacher(uid):
        db = get_db(); db.execute("DELETE FROM users WHERE id=? AND role='teacher'", (uid,)); db.commit(); db.close()
        return jsonify({'status': 'success'})

    @app.route('/api/admin/departments', methods=['GET', 'POST'])
    @admin_required
    def admin_departments():
        db = get_db()
        if request.method == 'POST':
            db.execute("INSERT INTO departments (name) VALUES (?)", (request.form['name'],))
            db.commit(); db.close()
            return jsonify({'status': 'success'})
        rows = db.execute("SELECT * FROM departments ORDER BY name").fetchall()
        db.close()
        return jsonify([dict(r) for r in rows])

    @app.route('/api/admin/departments/<int:did>', methods=['DELETE'])
    @admin_required
    def admin_delete_dept(did):
        db = get_db(); db.execute("DELETE FROM departments WHERE id=?", (did,)); db.commit(); db.close()
        return jsonify({'status': 'success'})

    @app.route('/api/admin/classes', methods=['GET', 'POST'])
    @admin_required
    def admin_classes():
        db = get_db()
        if request.method == 'POST':
            data = request.form
            db.execute("INSERT INTO classes (name, year, department_id) VALUES (?,?,?)",
                      (data['name'], data.get('year') or None, data.get('department_id') or None))
            db.commit(); db.close()
            return jsonify({'status': 'success'})
        rows = db.execute('''
            SELECT c.id, c.name, c.year, c.department_id,
                   COALESCE(d.name, '') as dept_name,
                   COALESCE(GROUP_CONCAT(b.name), '') as batches
            FROM classes c LEFT JOIN departments d ON d.id=c.department_id
            LEFT JOIN batches b ON b.class_id=c.id
            GROUP BY c.id ORDER BY c.name
        ''').fetchall()
        db.close()
        return jsonify([{'id': r['id'], 'name': r['name'], 'year': r['year'] or '',
                        'dept_name': r['dept_name'], 'batches': r['batches']} for r in rows])

    @app.route('/api/admin/classes/<int:cid>', methods=['DELETE'])
    @admin_required
    def admin_delete_class(cid):
        db = get_db(); db.execute("DELETE FROM classes WHERE id=?", (cid,)); db.commit(); db.close()
        return jsonify({'status': 'success'})

    @app.route('/api/admin/batches', methods=['POST'])
    @admin_required
    def admin_add_batch():
        data = request.form
        db = get_db()
        db.execute("INSERT INTO batches (name, class_id) VALUES (?,?)", (data['name'], data['class_id']))
        db.commit(); db.close()
        return jsonify({'status': 'success'})

    @app.route('/api/admin/courses', methods=['GET', 'POST'])
    @admin_required
    def admin_courses():
        db = get_db()
        if request.method == 'POST':
            data = request.form
            db.execute("INSERT INTO courses (name, code, teacher_id) VALUES (?,?,?)",
                      (data['name'], data.get('code', ''), data.get('teacher_id') or None))
            db.commit(); db.close()
            return jsonify({'status': 'success'})
        rows = db.execute('''
            SELECT c.*, u.name as teacher_name,
                   (SELECT COUNT(*) FROM course_students WHERE course_id=c.id) as student_count
            FROM courses c LEFT JOIN users u ON u.id=c.teacher_id ORDER BY c.name
        ''').fetchall()
        db.close()
        return jsonify([dict(r) for r in rows])

    @app.route('/api/admin/courses/<int:cid>', methods=['DELETE'])
    @admin_required
    def admin_delete_course(cid):
        db = get_db(); db.execute("DELETE FROM courses WHERE id=?", (cid,)); db.commit(); db.close()
        return jsonify({'status': 'success'})

    @app.route('/api/admin/students', methods=['GET', 'POST'])
    @admin_required
    def admin_students():
        db = get_db()
        if request.method == 'POST':
            data = request.form
            db.execute("INSERT INTO students (id, name, prn, roll_no, class_id, batch_id) VALUES (?,?,?,?,?,?)",
                      (int(data['id']), data['name'], data.get('prn', ''), data.get('roll_no', ''),
                       data.get('class_id') or None, data.get('batch_id') or None))
            db.commit(); db.close()
            return jsonify({'status': 'success'})
        rows = db.execute('''
            SELECT s.id, s.name, s.prn, s.roll_no, s.class_id, s.batch_id, s.registered,
                   COALESCE(c.name, '') as class_name, COALESCE(b.name, '') as batch_name
            FROM students s LEFT JOIN classes c ON c.id=s.class_id
            LEFT JOIN batches b ON b.id=s.batch_id ORDER BY s.name
        ''').fetchall()
        db.close()
        return jsonify([{'id': r['id'], 'name': r['name'], 'prn': r['prn'] or '',
                        'roll_no': r['roll_no'] or '', 'class_name': r['class_name'],
                        'batch_name': r['batch_name'], 'registered': r['registered']} for r in rows])

    @app.route('/api/admin/students/<int:sid>', methods=['DELETE'])
    @admin_required
    def admin_delete_student(sid):
        db = get_db(); db.execute("DELETE FROM students WHERE id=?", (sid,)); db.commit(); db.close()
        return jsonify({'status': 'success'})

    # ─── Course Student Assignment ───────────────────────────
    @app.route('/api/admin/course/<int:course_id>/students', methods=['GET', 'POST'])
    @admin_required
    def admin_course_students(course_id):
        db = get_db()
        if request.method == 'POST':
            student_id = request.form.get('student_id')
            if student_id:
                db.execute("INSERT OR IGNORE INTO course_students (course_id, student_id) VALUES (?,?)",
                          (course_id, int(student_id)))
                db.commit()
            db.close()
            return jsonify({'status': 'success'})
        # Get students in course
        rows = db.execute('''
            SELECT s.id, s.name, s.prn, s.roll_no FROM students s
            JOIN course_students cs ON cs.student_id=s.id AND cs.course_id=?
            ORDER BY s.name
        ''', (course_id,)).fetchall()
        db.close()
        return jsonify([dict(r) for r in rows])
