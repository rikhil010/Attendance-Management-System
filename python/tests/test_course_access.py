"""
Course access tests: a teacher may only access/operate on courses they teach;
admin keeps full access. Mirrors the ownership rule already used for grades,
now applied to roster, attendance, sessions, reports, imports, the course page,
and the session-scoped endpoints.

Runs against the configured MySQL database with self-created fixtures that are
removed afterwards. Sessions are set directly (never via /auth/*) so
data/.remember is untouched.

Run from the python dir:  python -m unittest tests.test_course_access -v
"""

import os
import sys
import uuid
import unittest
from datetime import datetime

SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src'))
ADMIN_ID = 1
STUDENT_ID = 990101
MISSING_ID = 999999999


class CourseAccessTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, SRC)
        os.chdir(SRC)
        import app as app_module
        from models import get_db, hash_password
        from database import _execute
        cls.app = app_module.app
        cls.app.testing = True
        cls.get_db = staticmethod(get_db)

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        tag = uuid.uuid4().hex[:8]
        db = get_db()
        # t1 owns the temp course; t2 is the non-owner.
        cls.t1 = _execute(db,
            "INSERT INTO users (name, email, password, role, created_at) VALUES (%s,%s,%s,'teacher',%s)",
            ('GW CA T1', f'gw_ca_t1_{tag}@test.local', hash_password('x'), now))
        cls.t2 = _execute(db,
            "INSERT INTO users (name, email, password, role, created_at) VALUES (%s,%s,%s,'teacher',%s)",
            ('GW CA T2', f'gw_ca_t2_{tag}@test.local', hash_password('x'), now))
        cls.course = _execute(db,
            "INSERT INTO courses (name, code, teacher_id) VALUES (%s,%s,%s)",
            ('GW CA Course', 'GWCA', cls.t1))
        # A student enrolled in the owning teacher's course.
        _execute(db, "DELETE FROM students WHERE id=%s", (STUDENT_ID,))
        _execute(db, "INSERT INTO students (id, name, roll_no) VALUES (%s,%s,%s)",
                 (STUDENT_ID, 'GW CA Student', 'C01'))
        _execute(db, "INSERT INTO course_students (course_id, student_id) VALUES (%s,%s)",
                 (cls.course, STUDENT_ID))
        # A session under the owning teacher's course with one attendance row.
        cls.session = _execute(db,
            "INSERT INTO attendance_sessions (course_id, teacher_id, started_at) VALUES (%s,%s,%s)",
            (cls.course, cls.t1, now))
        _execute(db,
            "INSERT INTO session_attendance (session_id, student_id, student_name, status) "
            "VALUES (%s,%s,%s,%s)",
            (cls.session, STUDENT_ID, 'GW CA Student', '--'))
        db.commit()
        db.close()

    @classmethod
    def tearDownClass(cls):
        from database import _execute
        db = cls.get_db()
        _execute(db, "DELETE FROM session_attendance WHERE session_id=%s", (cls.session,))
        _execute(db, "DELETE FROM attendance_sessions WHERE course_id=%s", (cls.course,))
        _execute(db, "DELETE FROM grades WHERE course_id=%s", (cls.course,))
        _execute(db, "DELETE FROM course_students WHERE course_id=%s", (cls.course,))
        _execute(db, "DELETE FROM courses WHERE id=%s", (cls.course,))
        _execute(db, "DELETE FROM students WHERE id=%s", (STUDENT_ID,))
        _execute(db, "DELETE FROM audit_log WHERE user_id IN (%s,%s)", (cls.t1, cls.t2))
        _execute(db, "DELETE FROM users WHERE id IN (%s,%s)", (cls.t1, cls.t2))
        db.commit()
        db.close()

    # ── helpers ──
    def client_as(self, user_id, role, student_id=None):
        c = self.app.test_client()
        with c.session_transaction() as s:
            s['user_id'] = user_id
            s['user_name'] = 'test'
            s['user_role'] = role
            s['student_id'] = student_id
        return c

    def assert_error_403(self, resp):
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.get_json()['status'], 'error')

    # ── cases ──
    def test_owner_api_ok(self):
        """The owning teacher reads/operates on their own course without error."""
        c = self.client_as(self.t1, 'teacher')
        cid, sid = self.course, self.session
        self.assertEqual(c.get(f'/api/course/{cid}').status_code, 200)
        self.assertEqual(c.get(f'/api/course/{cid}/students').status_code, 200)
        self.assertEqual(c.get(f'/api/course/{cid}/sessions').status_code, 200)
        self.assertEqual(c.get(f'/api/course/{cid}/report').status_code, 200)
        self.assertEqual(c.get(f'/api/session/{sid}/attendance').status_code, 200)
        self.assertEqual(
            c.post(f'/api/session/{sid}/mark',
                   data={'student_id': STUDENT_ID, 'status': 'Present'}).status_code, 200)
        self.assertEqual(
            c.post(f'/api/session/{sid}/description', data={'description': 'x'}).status_code, 200)

    def test_nonowner_api_403(self):
        """A different teacher is forbidden on every URL-course_id endpoint."""
        c = self.client_as(self.t2, 'teacher')
        cid = self.course
        self.assert_error_403(c.get(f'/api/course/{cid}'))
        self.assert_error_403(c.get(f'/api/course/{cid}/students'))
        self.assert_error_403(c.post(f'/api/course/{cid}/add_student',
                                     data={'name': 'X', 'id': '990199'}))
        self.assert_error_403(c.get(f'/api/course/{cid}/attendance/start'))
        self.assert_error_403(c.get(f'/api/course/{cid}/attendance/stop'))
        self.assert_error_403(c.get(f'/api/course/{cid}/sessions'))
        self.assert_error_403(c.get(f'/api/course/{cid}/report'))
        self.assert_error_403(c.get(f'/api/course/{cid}/report/export'))
        self.assert_error_403(c.post(f'/api/course/{cid}/import_students'))

    def test_nonowner_session_403(self):
        """A different teacher is forbidden on every session-scoped endpoint."""
        c = self.client_as(self.t2, 'teacher')
        sid = self.session
        self.assert_error_403(c.get(f'/api/session/{sid}/attendance'))
        self.assert_error_403(c.get(f'/api/session/{sid}/export'))
        self.assert_error_403(c.post(f'/api/session/{sid}/description', data={'description': 'x'}))
        self.assert_error_403(c.post(f'/api/session/{sid}/mark',
                                     data={'student_id': STUDENT_ID, 'status': 'Present'}))
        self.assert_error_403(c.post(f'/api/session/{sid}/mark_all', data={'status': 'Present'}))

    def test_missing_session_404(self):
        """Session routes return 404 for a non-existent session."""
        c = self.client_as(self.t1, 'teacher')
        self.assertEqual(c.get(f'/api/session/{MISSING_ID}/attendance').status_code, 404)
        self.assertEqual(c.get(f'/api/session/{MISSING_ID}/export').status_code, 404)
        self.assertEqual(
            c.post(f'/api/session/{MISSING_ID}/description', data={'description': 'x'}).status_code, 404)
        self.assertEqual(
            c.post(f'/api/session/{MISSING_ID}/mark',
                   data={'student_id': STUDENT_ID, 'status': 'Present'}).status_code, 404)
        self.assertEqual(
            c.post(f'/api/session/{MISSING_ID}/mark_all', data={'status': 'Present'}).status_code, 404)

    def test_missing_course_404(self):
        """URL-course_id routes return 404 for a non-existent course."""
        c = self.client_as(self.t1, 'teacher')
        self.assertEqual(c.get(f'/api/course/{MISSING_ID}').status_code, 404)
        self.assertEqual(c.get(f'/api/course/{MISSING_ID}/students').status_code, 404)

    def test_page_owner_200(self):
        c = self.client_as(self.t1, 'teacher')
        r = c.get(f'/course/{self.course}')
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'GWASOAT - Course', r.data)

    def test_page_nonowner_redirect(self):
        c = self.client_as(self.t2, 'teacher')
        r = c.get(f'/course/{self.course}', follow_redirects=False)
        self.assertIn(r.status_code, (301, 302))
        self.assertTrue(r.headers['Location'].endswith('/home'))
        self.assertNotEqual(r.status_code, 200)

    def test_page_missing_redirect(self):
        c = self.client_as(self.t2, 'teacher')
        r = c.get(f'/course/{MISSING_ID}', follow_redirects=False)
        self.assertIn(r.status_code, (301, 302))
        self.assertTrue(r.headers['Location'].endswith('/home'))

    def test_admin_ok(self):
        c = self.client_as(ADMIN_ID, 'admin')
        cid, sid = self.course, self.session
        self.assertEqual(c.get(f'/api/course/{cid}').status_code, 200)
        self.assertEqual(c.get(f'/api/course/{cid}/students').status_code, 200)
        self.assertEqual(c.get(f'/api/course/{cid}/sessions').status_code, 200)
        self.assertEqual(c.get(f'/api/session/{sid}/attendance').status_code, 200)
        self.assertEqual(c.get(f'/course/{cid}').status_code, 200)

    def test_student_blocked(self):
        c = self.client_as(ADMIN_ID, 'student', student_id=STUDENT_ID)
        self.assertEqual(c.get(f'/api/course/{self.course}').status_code, 403)
        self.assertEqual(c.get(f'/api/course/{self.course}/students').status_code, 403)
        r = c.get(f'/course/{self.course}', follow_redirects=False)
        self.assertIn(r.status_code, (301, 302))
        self.assertTrue(r.headers['Location'].endswith('/student'))


if __name__ == '__main__':
    unittest.main()
