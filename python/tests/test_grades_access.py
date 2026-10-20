"""
Grade access tests: a teacher manages grades only for courses they teach; admin manages all.

Runs against the configured MySQL database with self-created fixtures that are removed
afterwards. Sessions are set directly (never via /auth/*) so data/.remember is untouched.

Run from the repo root:  python -m unittest discover -s python\\tests -v
"""

import os
import sys
import uuid
import unittest
from datetime import datetime

SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src'))
ADMIN_ID = 1
STUDENT_ID = 990001


class GradeAccessTest(unittest.TestCase):

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
        _execute(db, "DELETE FROM students WHERE id=%s", (STUDENT_ID,))
        cls.t1 = _execute(db,
            "INSERT INTO users (name, email, password, role, created_at) VALUES (%s,%s,%s,'teacher',%s)",
            ('GW Test T1', f'gw_test_t1_{tag}@test.local', hash_password('x'), now))
        cls.t2 = _execute(db,
            "INSERT INTO users (name, email, password, role, created_at) VALUES (%s,%s,%s,'teacher',%s)",
            ('GW Test T2', f'gw_test_t2_{tag}@test.local', hash_password('x'), now))
        _execute(db, "INSERT INTO students (id, name, roll_no) VALUES (%s,%s,%s)",
                 (STUDENT_ID, 'GW Test Student', 'T01'))
        cls.course_a = _execute(db, "INSERT INTO courses (name, code, teacher_id) VALUES (%s,%s,%s)",
                                ('GW Test A', 'GWTA', cls.t1))
        cls.course_b = _execute(db, "INSERT INTO courses (name, code, teacher_id) VALUES (%s,%s,%s)",
                                ('GW Test B', 'GWTB', cls.t2))
        for cid in (cls.course_a, cls.course_b):
            _execute(db, "INSERT INTO course_students (course_id, student_id) VALUES (%s,%s)",
                     (cid, STUDENT_ID))
        # Second student, not enrolled anywhere (for the enrolment check).
        _execute(db, "DELETE FROM students WHERE id=%s", (STUDENT_ID + 1,))
        _execute(db, "INSERT INTO students (id, name) VALUES (%s,%s)", (STUDENT_ID + 1, 'GW Test Other'))
        db.commit()
        db.close()

    @classmethod
    def tearDownClass(cls):
        from database import _execute
        db = cls.get_db()
        courses = (cls.course_a, cls.course_b)
        _execute(db, "DELETE FROM grades WHERE course_id IN (%s,%s)", courses)
        _execute(db, "DELETE FROM course_students WHERE course_id IN (%s,%s)", courses)
        _execute(db, "DELETE FROM courses WHERE id IN (%s,%s)", courses)
        _execute(db, "DELETE FROM students WHERE id IN (%s,%s)", (STUDENT_ID, STUDENT_ID + 1))
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

    def save(self, client, course_id, **fields):
        data = {'student_id': STUDENT_ID, 'component': 'Quiz', 'score': '8', 'max_score': '10'}
        data.update(fields)
        return client.post(f'/api/course/{course_id}/grades', data=data)

    def grade_id(self, course_id, component):
        from database import _fetchone
        db = self.get_db()
        row = _fetchone(db, "SELECT id FROM grades WHERE course_id=%s AND component=%s",
                        (course_id, component))
        db.close()
        return row['id'] if row else None

    # ── cases ──
    def test_a_owner_get_post_delete(self):
        c = self.client_as(self.t1, 'teacher')
        self.assertEqual(self.save(c, self.course_a, component='OwnerQuiz').status_code, 200)
        r = c.get(f'/api/course/{self.course_a}/grades')
        self.assertEqual(r.status_code, 200)
        self.assertIn('OwnerQuiz', [g['component'] for g in r.get_json()])
        gid = self.grade_id(self.course_a, 'OwnerQuiz')
        self.assertEqual(c.delete(f'/api/grades/{gid}').status_code, 200)
        self.assertIsNone(self.grade_id(self.course_a, 'OwnerQuiz'))

    def test_b_other_teacher_get_post_forbidden(self):
        c = self.client_as(self.t2, 'teacher')
        for r in (c.get(f'/api/course/{self.course_a}/grades'),
                  self.save(c, self.course_a, component='Intruder')):
            self.assertEqual(r.status_code, 403)
            self.assertEqual(r.get_json()['status'], 'error')
        self.assertIsNone(self.grade_id(self.course_a, 'Intruder'))

    def test_c_other_teacher_delete_forbidden(self):
        owner = self.client_as(self.t1, 'teacher')
        self.assertEqual(self.save(owner, self.course_a, component='Keep').status_code, 200)
        gid = self.grade_id(self.course_a, 'Keep')
        r = self.client_as(self.t2, 'teacher').delete(f'/api/grades/{gid}')
        self.assertEqual(r.status_code, 403)
        self.assertIsNotNone(self.grade_id(self.course_a, 'Keep'))

    def test_d_admin_full_access(self):
        c = self.client_as(ADMIN_ID, 'admin')
        self.assertEqual(self.save(c, self.course_a, component='AdminQuiz').status_code, 200)
        self.assertEqual(c.get(f'/api/course/{self.course_a}/grades').status_code, 200)
        gid = self.grade_id(self.course_a, 'AdminQuiz')
        self.assertEqual(c.delete(f'/api/grades/{gid}').status_code, 200)

    def test_e_delete_missing_grade_404(self):
        c = self.client_as(self.t1, 'teacher')
        self.assertEqual(c.delete('/api/grades/999999999').status_code, 404)

    def test_f_missing_course_404(self):
        c = self.client_as(self.t1, 'teacher')
        self.assertEqual(c.get('/api/course/999999999/grades').status_code, 404)

    def test_g_invalid_scores_400(self):
        c = self.client_as(self.t1, 'teacher')
        bad = [{'score': '11', 'max_score': '10'}, {'max_score': '0'}, {'max_score': '-5'},
               {'max_score': 'abc'}, {'score': '-1'}, {'max_score': '10000'}, {'score': 'nan'}]
        for fields in bad:
            with self.subTest(fields=fields):
                self.assertEqual(self.save(c, self.course_a, component='Bad', **fields).status_code, 400)
        self.assertIsNone(self.grade_id(self.course_a, 'Bad'))

    def test_h_blank_score_allowed(self):
        c = self.client_as(self.t1, 'teacher')
        self.assertEqual(self.save(c, self.course_a, component='Blank', score='').status_code, 200)

    def test_i_not_enrolled_400(self):
        c = self.client_as(self.t1, 'teacher')
        r = self.save(c, self.course_a, component='X', student_id=STUDENT_ID + 1)
        self.assertEqual(r.status_code, 400)

    def test_j_student_forbidden(self):
        c = self.client_as(ADMIN_ID, 'student', student_id=STUDENT_ID)
        self.assertEqual(c.get(f'/api/course/{self.course_a}/grades').status_code, 403)

    def test_k_can_manage_grades_flag(self):
        # GET /api/course/<id> is now owner-gated: the owner and admin get 200
        # and can read can_manage_grades; a non-owning teacher gets 403.
        for uid, role in ((self.t1, 'teacher'), (ADMIN_ID, 'admin')):
            with self.subTest(uid=uid):
                r = self.client_as(uid, role).get(f'/api/course/{self.course_a}')
                self.assertEqual(r.status_code, 200)
                self.assertIs(r.get_json()['can_manage_grades'], True)
        with self.subTest(uid=self.t2):
            r = self.client_as(self.t2, 'teacher').get(f'/api/course/{self.course_a}')
            self.assertEqual(r.status_code, 403)
            self.assertEqual(r.get_json()['status'], 'error')


if __name__ == '__main__':
    unittest.main()
