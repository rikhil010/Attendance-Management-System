"""
Attendance tracking and management module — MySQL backend.
"""

import sys
import os
import re
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import get_db, _fetchone, _fetchall, _execute
from network import esp32_request

session_seen_records = set()
session_marked_student_ids = set()


def mark_student_present(student_id, student_name='', class_id=None, session_id=None, fingerprint_time=''):
    """Mark a student as present in attendance."""
    import registration

    target_class_id, target_session_id = registration._resolve_active_session(class_id, session_id)
    if target_class_id is None or target_session_id is None:
        return False

    db = get_db()
    student = _fetchone(db,
        "SELECT id, name, class_id FROM students WHERE id = %s",
        (student_id,))
    if student is None:
        db.close()
        return False

    now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    effective_name = student_name.strip() if student_name else student["name"]

    existing = _fetchone(db,
        "SELECT status FROM session_attendance WHERE session_id = %s AND student_id = %s",
        (target_session_id, int(student["id"])))

    if existing is not None and existing["status"] == "Present":
        db.close()
        return True

    if existing is None:
        _execute(db,
            "INSERT INTO session_attendance "
            "(session_id, class_id, student_id, student_name, status, marked_at) "
            "VALUES (%s, %s, %s, %s, 'Present', %s)",
            (target_session_id, target_class_id, int(student["id"]), effective_name, now_text))
    else:
        _execute(db,
            "UPDATE session_attendance SET status = 'Present', marked_at = %s "
            "WHERE session_id = %s AND student_id = %s",
            (now_text, target_session_id, int(student["id"])))

    _execute(db,
        "INSERT INTO attendance_records "
        "(session_id, class_id, student_id, student_name, fingerprint_time, recorded_at) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (target_session_id, target_class_id, int(student["id"]), effective_name,
         fingerprint_time or None, now_text))

    db.commit()
    db.close()

    session_marked_student_ids.add(int(student["id"]))
    return True


def sync_attendance_from_esp32(class_id=None, session_id=None):
    """Sync attendance records from ESP32 to database."""
    from registration import _resolve_active_session

    target_class_id, target_session_id = _resolve_active_session(class_id, session_id)
    if target_class_id is None or target_session_id is None:
        return

    response, _, _ = esp32_request('/get_attendance')
    if response is None or response.status_code != 200:
        return

    try:
        device_records = response.json()
    except ValueError:
        return

    if not isinstance(device_records, list):
        return

    db = get_db()
    global session_seen_records
    global session_marked_student_ids

    for record in device_records:
        if not isinstance(record, dict):
            continue
        student_id = int(record.get("id", -1))
        if student_id < 0:
            continue
        fingerprint_time = str(record.get("time", ""))
        key = (student_id, fingerprint_time)
        if key in session_seen_records:
            continue
        session_seen_records.add(key)

        if student_id in session_marked_student_ids:
            _execute(db,
                "UPDATE session_attendance SET status = 'Present', "
                "marked_at = COALESCE(marked_at, %s) "
                "WHERE session_id = %s AND student_id = %s",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                 target_session_id, student_id))
            continue

        student = _fetchone(db,
            "SELECT id, name FROM students WHERE id = %s", (student_id,))
        if student is None:
            continue

        _execute(db,
            "INSERT INTO attendance_records "
            "(session_id, class_id, student_id, student_name, fingerprint_time, recorded_at) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (target_session_id, target_class_id, student["id"], student["name"],
             fingerprint_time, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

        _execute(db,
            "UPDATE session_attendance SET status = 'Present', marked_at = %s "
            "WHERE session_id = %s AND student_id = %s",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
             target_session_id, student_id))

        session_marked_student_ids.add(student_id)

    db.commit()
    db.close()


def get_attendance_summary(class_id, session_id=None):
    """Get attendance summary for a class and session."""
    db = get_db()
    resolved_session_id = session_id

    if resolved_session_id is None:
        row = _fetchone(db,
            "SELECT id FROM attendance_sessions WHERE class_id = %s "
            "ORDER BY id DESC LIMIT 1",
            (class_id,))
        if row is not None:
            resolved_session_id = int(row["id"])

    if resolved_session_id is None:
        db.close()
        return {"session_id": None, "session_time": "", "rows": []}

    session_row = _fetchone(db,
        "SELECT id, started_at, ended_at FROM attendance_sessions "
        "WHERE id = %s AND class_id = %s",
        (resolved_session_id, class_id))

    if session_row is None:
        db.close()
        return {"session_id": None, "session_time": "", "rows": []}

    rows = _fetchall(db,
        "SELECT student_id, student_name, status, marked_at "
        "FROM session_attendance WHERE session_id = %s ORDER BY student_id",
        (resolved_session_id,))

    summary_rows = []
    for index, row in enumerate(rows, start=1):
        summary_rows.append({
            "sr_no":        index,
            "name":         row["student_name"],
            "id":           int(row["student_id"]),
            "session_time": str(session_row["started_at"]),
            "status":       row["status"],
            "marked_at":    str(row["marked_at"]) if row["marked_at"] else ""
        })

    db.close()
    return {
        "session_id":   int(session_row["id"]),
        "session_time": str(session_row["started_at"]),
        "rows":         summary_rows
    }


def list_sessions_for_class(class_id):
    """List all attendance sessions for a class."""
    db = get_db()
    rows = _fetchall(db,
        "SELECT id, started_at, ended_at FROM attendance_sessions "
        "WHERE class_id = %s ORDER BY id DESC",
        (class_id,))
    db.close()

    sessions = []
    for row in rows:
        sessions.append({
            "id":         int(row["id"]),
            "started_at": str(row["started_at"]),
            "ended_at":   str(row["ended_at"]) if row["ended_at"] else "",
            "label":      f"Session {row['id']} - {row['started_at']}"
        })
    return sessions


def delete_session(session_id):
    """Delete an attendance session."""
    db = get_db()
    session_row = _fetchone(db,
        "SELECT id, class_id FROM attendance_sessions WHERE id = %s",
        (session_id,))

    if session_row is None:
        db.close()
        return {'status': 'error', 'message': 'Session not found'}, 404

    _execute(db, "DELETE FROM session_attendance WHERE session_id = %s", (session_id,))
    _execute(db, "DELETE FROM attendance_records WHERE session_id = %s", (session_id,))
    _execute(db, "DELETE FROM attendance_sessions WHERE id = %s", (session_id,))
    db.commit()
    db.close()

    return {'status': 'success'}, 200
