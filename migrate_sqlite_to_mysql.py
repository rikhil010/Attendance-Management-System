"""
One-time migration: copies all data from SQLite attendance.db into MySQL gwasoat database.
Safe to run multiple times — uses INSERT IGNORE to skip duplicates.
"""

import sqlite3
import mysql.connector

SQLITE_PATH = r'c:\Users\rikhi\OneDrive\Documents\PlatformIO\Projects\GWASOAT\data\attendance.db'

MYSQL_CONFIG = {
    'host':     'localhost',
    'port':     3306,
    'database': 'gwasoat',
    'user':     'gwasoat_user',
    'password': 'gwasoat_pass_2026',
    'charset':  'utf8mb4',
    'use_pure': True,
}


def migrate():
    src = sqlite3.connect(SQLITE_PATH)
    src.row_factory = sqlite3.Row

    dst = mysql.connector.connect(**MYSQL_CONFIG)
    cur = dst.cursor()

    # ── classes ──────────────────────────────────────────────
    rows = src.execute('SELECT id, name FROM classes').fetchall()
    for r in rows:
        cur.execute('INSERT IGNORE INTO classes (id, name) VALUES (%s,%s)',
                    (r['id'], r['name']))
    print(f'classes:              {len(rows)} rows')

    # ── students ─────────────────────────────────────────────
    rows = src.execute('SELECT id, name, class_id, registered FROM students').fetchall()
    for r in rows:
        cur.execute(
            'INSERT IGNORE INTO students (id, name, class_id, registered) VALUES (%s,%s,%s,%s)',
            (r['id'], r['name'], r['class_id'], r['registered']))
    print(f'students:             {len(rows)} rows')

    # ── fingerprint_templates ─────────────────────────────────
    rows = src.execute(
        'SELECT student_id, class_id, template_data, template_size, created_at '
        'FROM fingerprint_templates').fetchall()
    for r in rows:
        cur.execute(
            'INSERT IGNORE INTO fingerprint_templates '
            '(student_id, class_id, template_data, template_size, created_at) '
            'VALUES (%s,%s,%s,%s,%s)',
            (r['student_id'], r['class_id'], r['template_data'],
             r['template_size'], r['created_at']))
    print(f'fingerprint_templates:{len(rows)} rows')

    # ── attendance_sessions ───────────────────────────────────
    rows = src.execute(
        'SELECT id, class_id, started_at, ended_at FROM attendance_sessions').fetchall()
    for r in rows:
        cur.execute(
            'INSERT IGNORE INTO attendance_sessions '
            '(id, class_id, started_at, ended_at) VALUES (%s,%s,%s,%s)',
            (r['id'], r['class_id'], r['started_at'], r['ended_at']))
    print(f'attendance_sessions:  {len(rows)} rows')

    # ── session_attendance ────────────────────────────────────
    rows = src.execute(
        'SELECT id, session_id, student_id, student_name, status, marked_at '
        'FROM session_attendance').fetchall()
    for r in rows:
        cur.execute(
            'INSERT IGNORE INTO session_attendance '
            '(id, session_id, student_id, student_name, status, marked_at) '
            'VALUES (%s,%s,%s,%s,%s,%s)',
            (r['id'], r['session_id'], r['student_id'],
             r['student_name'], r['status'], r['marked_at']))
    print(f'session_attendance:   {len(rows)} rows')

    # ── attendance_records ────────────────────────────────────
    rows = src.execute(
        'SELECT id, session_id, class_id, student_id, student_name, '
        'fingerprint_time, recorded_at FROM attendance_records').fetchall()
    for r in rows:
        cur.execute(
            'INSERT IGNORE INTO attendance_records '
            '(id, session_id, class_id, student_id, student_name, fingerprint_time, recorded_at) '
            'VALUES (%s,%s,%s,%s,%s,%s,%s)',
            (r['id'], r['session_id'], r['class_id'], r['student_id'],
             r['student_name'], r['fingerprint_time'], r['recorded_at']))
    print(f'attendance_records:   {len(rows)} rows')

    # ── users ─────────────────────────────────────────────────
    rows = src.execute(
        'SELECT id, name, email, password, role, created_at FROM users').fetchall()
    for r in rows:
        cur.execute(
            'INSERT IGNORE INTO users (id, name, email, password, role, created_at) '
            'VALUES (%s,%s,%s,%s,%s,%s)',
            (r['id'], r['name'], r['email'], r['password'], r['role'], r['created_at']))
    print(f'users:                {len(rows)} rows')

    # ── app_settings ──────────────────────────────────────────
    try:
        rows = src.execute('SELECT key, value FROM app_settings').fetchall()
        for r in rows:
            cur.execute(
                'INSERT IGNORE INTO app_settings (`key`, value) VALUES (%s,%s)',
                (r['key'], r['value']))
        print(f'app_settings:         {len(rows)} rows')
    except Exception:
        print('app_settings:         skipped (table not in source)')

    dst.commit()
    cur.close()
    src.close()
    dst.close()
    print('\nMigration complete!')


if __name__ == '__main__':
    migrate()
