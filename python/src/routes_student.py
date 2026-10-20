"""
Student self-service routes for GWASOAT — MySQL backend.

Students can view (read-only) their own:
  - enrolled courses
  - class / batch info
  - attendance (overall + per course + per session)
  - grades
  - timetable
  - profile

All endpoints are guarded so a student can only ever see their own data.
"""

import sys
import os
import io
import csv
from datetime import datetime
from flask import render_template, request, jsonify, session, redirect, send_file

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from models import get_db
from database import _fetchone, _fetchall
from auth import login_required, student_required, permission_required, get_current_user


def _current_student_id():
    """Resolve the students.id linked to the logged-in student account."""
    user = get_current_user()
    if not user or user['role'] != 'student':
        return None
    return user.get('student_id')


def setup_student_routes(app):
    """Register all student-facing routes."""

    # ─── Pages ───────────────────────────────────────────────
    @app.route('/student')
    @student_required
    def student_home():
        return render_template('student_home.html')

    @app.route('/student/course/<int:course_id>')
    @student_required
    def student_course_page(course_id):
        return render_template('student_course.html')

    # ─── My profile summary ──────────────────────────────────
    @app.route('/api/student/me')
    @student_required
    def student_me():
        sid = _current_student_id()
        user = get_current_user()
        db = get_db()
        student = _fetchone(db, '''
            SELECT s.id, s.name, s.prn, s.roll_no, s.registered,
                   COALESCE(c.name,'') AS class_name, c.year AS class_year,
                   COALESCE(d.name,'') AS dept_name, COALESCE(b.name,'') AS batch_name
            FROM students s
            LEFT JOIN classes c ON c.id = s.class_id
            LEFT JOIN departments d ON d.id = c.department_id
            LEFT JOIN batches b ON b.id = s.batch_id
            WHERE s.id = %s
        ''', (sid,))
        db.close()
        if not student:
            return jsonify({'status': 'error', 'message': 'No student record linked to this account'}), 404
        return jsonify({
            'account': {'id': user['id'], 'name': user['name'], 'email': user['email'],
                        'role': user['role'], 'permissions': user['permissions']},
            'student': {**student, 'class_year': student['class_year'] or ''},
        })

    # ─── My courses ──────────────────────────────────────────
    @app.route('/api/student/courses')
    @student_required
    def student_courses():
        sid = _current_student_id()
        db = get_db()
        rows = _fetchall(db, '''
            SELECT c.id, c.name, c.code, u.name AS teacher_name
            FROM courses c
            JOIN course_students cs ON cs.course_id = c.id AND cs.student_id = %s
            LEFT JOIN users u ON u.id = c.teacher_id
            ORDER BY c.name
        ''', (sid,))
        db.close()
        return jsonify(rows)

    # ─── My attendance (overall, grouped by course) ──────────
    @app.route('/api/student/attendance')
    @student_required
    def student_attendance():
        sid = _current_student_id()
        db = get_db()
        rows = _fetchall(db, '''
            SELECT c.id AS course_id, c.name AS course_name, c.code,
                   COUNT(sa.id) AS held,
                   SUM(CASE WHEN sa.status='Present' THEN 1 ELSE 0 END) AS present
            FROM courses c
            JOIN course_students cs ON cs.course_id = c.id AND cs.student_id = %s
            LEFT JOIN attendance_sessions ses ON ses.course_id = c.id
            LEFT JOIN session_attendance sa ON sa.session_id = ses.id AND sa.student_id = %s
            GROUP BY c.id
            ORDER BY c.name
        ''', (sid, sid))
        db.close()
        out = []
        tot_held = tot_present = 0
        for r in rows:
            held = r['held'] or 0
            present = r['present'] or 0
            tot_held += held
            tot_present += present
            out.append({
                'course_id': r['course_id'], 'course_name': r['course_name'],
                'code': r['code'] or '', 'held': held, 'present': present,
                'absent': held - present,
                'percent': round(present / held * 100, 1) if held else 0.0,
            })
        overall = round(tot_present / tot_held * 100, 1) if tot_held else 0.0
        return jsonify({'overall_percent': overall, 'total_held': tot_held,
                        'total_present': tot_present, 'courses': out})

    # ─── My attendance for a single course (session by session) ─
    @app.route('/api/student/course/<int:course_id>/attendance')
    @student_required
    def student_course_attendance(course_id):
        sid = _current_student_id()
        db = get_db()
        # Verify enrolment
        enrolled = _fetchone(db,
            "SELECT 1 AS ok FROM course_students WHERE course_id=%s AND student_id=%s",
            (course_id, sid))
        if not enrolled:
            db.close()
            return jsonify({'status': 'error', 'message': 'You are not enrolled in this course'}), 403

        course = _fetchone(db, '''
            SELECT c.id, c.name, c.code, u.name AS teacher_name
            FROM courses c LEFT JOIN users u ON u.id = c.teacher_id
            WHERE c.id = %s
        ''', (course_id,))

        rows = _fetchall(db, '''
            SELECT ses.id AS session_id, ses.started_at, ses.description,
                   COALESCE(sa.status, '--') AS status, sa.marked_at
            FROM attendance_sessions ses
            LEFT JOIN session_attendance sa
                   ON sa.session_id = ses.id AND sa.student_id = %s
            WHERE ses.course_id = %s
            ORDER BY ses.id DESC
        ''', (sid, course_id))
        db.close()

        held = sum(1 for r in rows if r['status'] in ('Present', 'Absent'))
        present = sum(1 for r in rows if r['status'] == 'Present')
        return jsonify({
            'course': course,
            'summary': {'held': held, 'present': present, 'absent': held - present,
                        'percent': round(present / held * 100, 1) if held else 0.0},
            'sessions': [{
                'session_id': r['session_id'],
                'started_at': str(r['started_at']),
                'description': r['description'] or '',
                'status': r['status'],
                'marked_at': str(r['marked_at']) if r['marked_at'] else '',
            } for r in rows],
        })

    # ─── My grades ───────────────────────────────────────────
    @app.route('/api/student/grades')
    @student_required
    def student_grades():
        sid = _current_student_id()
        db = get_db()
        rows = _fetchall(db, '''
            SELECT g.id, g.component, g.score, g.max_score, g.grade, g.remarks,
                   g.updated_at, c.id AS course_id, c.name AS course_name, c.code
            FROM grades g
            JOIN courses c ON c.id = g.course_id
            JOIN course_students cs ON cs.course_id = c.id AND cs.student_id = %s
            WHERE g.student_id = %s
            ORDER BY c.name, g.component
        ''', (sid, sid))
        db.close()

        courses = {}
        for r in rows:
            cid = r['course_id']
            courses.setdefault(cid, {
                'course_id': cid, 'course_name': r['course_name'],
                'code': r['code'] or '', 'items': [],
            })
            courses[cid]['items'].append({
                'id': r['id'], 'component': r['component'],
                'score': float(r['score']) if r['score'] is not None else None,
                'max_score': float(r['max_score']) if r['max_score'] is not None else None,
                'grade': r['grade'] or '', 'remarks': r['remarks'] or '',
                'updated_at': str(r['updated_at']),
            })
        return jsonify(list(courses.values()))

    # ─── My class info ───────────────────────────────────────
    @app.route('/api/student/class')
    @student_required
    def student_class():
        sid = _current_student_id()
        db = get_db()
        info = _fetchone(db, '''
            SELECT c.id, c.name, c.year,
                   COALESCE(d.name,'') AS dept_name,
                   COALESCE(b.name,'') AS batch_name
            FROM students s
            LEFT JOIN classes c ON c.id = s.class_id
            LEFT JOIN departments d ON d.id = c.department_id
            LEFT JOIN batches b ON b.id = s.batch_id
            WHERE s.id = %s
        ''', (sid,))
        if not info or not info['id']:
            db.close()
            return jsonify({'class': None, 'classmates': []})

        classmates = _fetchall(db, '''
            SELECT s.id, s.name, s.roll_no, COALESCE(b.name,'') AS batch_name
            FROM students s LEFT JOIN batches b ON b.id = s.batch_id
            WHERE s.class_id = %s ORDER BY s.roll_no, s.name
        ''', (info['id'],))
        db.close()
        return jsonify({
            'class': {'id': info['id'], 'name': info['name'], 'year': info['year'] or '',
                      'dept_name': info['dept_name'], 'batch_name': info['batch_name']},
            'classmates': classmates,
        })

    # ─── My timetable ────────────────────────────────────────
    @app.route('/api/student/timetable')
    @student_required
    def student_timetable():
        DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        sid = _current_student_id()
        db = get_db()
        rows = _fetchall(db, '''
            SELECT t.id, t.day_of_week, t.start_time, t.end_time, t.room,
                   c.name AS course_name, c.code, u.name AS teacher_name
            FROM timetable t
            JOIN courses c ON c.id = t.course_id
            JOIN course_students cs ON cs.course_id = c.id AND cs.student_id = %s
            LEFT JOIN users u ON u.id = c.teacher_id
            ORDER BY t.day_of_week, t.start_time
        ''', (sid,))
        db.close()
        return jsonify([{**r,
                         'day_name': DAYS[r['day_of_week']] if 0 <= r['day_of_week'] < 7 else '?'}
                        for r in rows])

    # ─── Export my attendance for a course (CSV) ─────────────
    @app.route('/api/student/course/<int:course_id>/attendance/export')
    @student_required
    def student_course_attendance_export(course_id):
        sid = _current_student_id()
        db = get_db()
        enrolled = _fetchone(db,
            "SELECT 1 AS ok FROM course_students WHERE course_id=%s AND student_id=%s",
            (course_id, sid))
        if not enrolled:
            db.close()
            return jsonify({'status': 'error', 'message': 'Not enrolled'}), 403
        rows = _fetchall(db, '''
            SELECT ses.started_at, ses.description, COALESCE(sa.status,'--') AS status
            FROM attendance_sessions ses
            LEFT JOIN session_attendance sa
                   ON sa.session_id = ses.id AND sa.student_id = %s
            WHERE ses.course_id = %s ORDER BY ses.id
        ''', (sid, course_id))
        db.close()
        output = io.StringIO()
        w = csv.writer(output)
        w.writerow(['Date', 'Topic', 'Status'])
        for r in rows:
            w.writerow([str(r['started_at']), r['description'] or '', r['status']])
        output.seek(0)
        return send_file(io.BytesIO(output.getvalue().encode()), mimetype='text/csv',
                         as_attachment=True,
                         download_name=f'my_attendance_course_{course_id}.csv')
