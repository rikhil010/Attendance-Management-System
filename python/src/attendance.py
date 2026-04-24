"""
Attendance tracking and management module.
"""

import re
from datetime import datetime
from database import get_db
from network import esp32_request

session_seen_records = set()
session_marked_student_ids = set()


def mark_student_present(student_id, student_name='', class_id=None, session_id=None, fingerprint_time=''):
    """Mark a student as present in attendance."""
    from registration import _resolve_active_session
    
    target_class_id, target_session_id = _resolve_active_session(class_id, session_id)
    if target_class_id is None or target_session_id is None:
        return False

    db = get_db()
    student = db.execute(
        "SELECT id, name FROM students WHERE id = ?",
        (student_id,)
    ).fetchone()
    if student is None:
        db.close()
        return False

    now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    effective_name = student_name.strip() if student_name else student["name"]

    existing = db.execute(
        "SELECT status FROM session_attendance WHERE session_id = ? AND student_id = ?",
        (target_session_id, int(student["id"]))
    ).fetchone()
    
    if existing is not None and existing["status"] == "Present":
        db.close()
        return True

    if existing is None:
        db.execute(
            "INSERT INTO session_attendance "
            "(session_id, class_id, student_id, student_name, status, marked_at) "
            "VALUES (?, ?, ?, ?, 'Present', ?)",
            (target_session_id, target_class_id, int(student["id"]), effective_name, now_text)
        )
    else:
        db.execute(
            "UPDATE session_attendance SET status = 'Present', marked_at = ? "
            "WHERE session_id = ? AND student_id = ?",
            (now_text, target_session_id, int(student["id"]))
        )
    
    db.execute(
        "INSERT INTO attendance_records "
        "(session_id, class_id, student_id, student_name, fingerprint_time, recorded_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (target_session_id, target_class_id, int(student["id"]), effective_name, fingerprint_time or '', now_text)
    )
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
            db.execute(
                "UPDATE session_attendance SET status = 'Present', marked_at = COALESCE(marked_at, ?) "
                "WHERE session_id = ? AND student_id = ?",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), target_session_id, student_id)
            )
            continue

        student = db.execute(
            "SELECT id, name FROM students WHERE id = ?",
            (student_id,)
        ).fetchone()

        if student is None:
            continue

        db.execute(
            "INSERT INTO attendance_records "
            "(session_id, class_id, student_id, student_name, fingerprint_time, recorded_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (target_session_id, target_class_id, student["id"], student["name"],
             fingerprint_time, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        db.execute(
            "UPDATE session_attendance SET status = 'Present', marked_at = ? "
            "WHERE session_id = ? AND student_id = ?",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), target_session_id, student_id)
        )
        session_marked_student_ids.add(student_id)

    db.commit()
    db.close()


def get_attendance_summary(class_id, session_id=None):
    """Get attendance summary for a class and session."""
    db = get_db()
    resolved_session_id = session_id
    
    if resolved_session_id is None:
        row = db.execute(
            "SELECT id FROM attendance_sessions WHERE class_id = ? ORDER BY id DESC LIMIT 1",
            (class_id,)
        ).fetchone()
        if row is not None:
            resolved_session_id = int(row["id"])

    if resolved_session_id is None:
        db.close()
        return {
            "session_id": None,
            "session_time": "",
            "rows": []
        }

    session_row = db.execute(
        "SELECT id, started_at, ended_at FROM attendance_sessions WHERE id = ? AND class_id = ?",
        (resolved_session_id, class_id)
    ).fetchone()
    
    if session_row is None:
        db.close()
        return {
            "session_id": None,
            "session_time": "",
            "rows": []
        }

    rows = db.execute(
        "SELECT student_id, student_name, status, marked_at FROM session_attendance "
        "WHERE session_id = ? ORDER BY student_id",
        (resolved_session_id,)
    ).fetchall()

    summary_rows = []
    for index, row in enumerate(rows, start=1):
        summary_rows.append({
            "sr_no": index,
            "name": row["student_name"],
            "id": int(row["student_id"]),
            "session_time": session_row["started_at"],
            "status": row["status"],
            "marked_at": row["marked_at"] or ""
        })

    db.close()
    return {
        "session_id": int(session_row["id"]),
        "session_time": session_row["started_at"],
        "rows": summary_rows
    }


def list_sessions_for_class(class_id):
    """List all attendance sessions for a class."""
    db = get_db()
    rows = db.execute(
        "SELECT id, started_at, ended_at FROM attendance_sessions "
        "WHERE class_id = ? ORDER BY id DESC",
        (class_id,)
    ).fetchall()
    db.close()
    
    sessions = []
    for row in rows:
        sessions.append({
            "id": int(row["id"]),
            "started_at": row["started_at"],
            "ended_at": row["ended_at"] or "",
            "label": f"Session {row['id']} - {row['started_at']}"
        })
    return sessions


def delete_session(session_id):
    """Delete an attendance session."""
    db = get_db()
    session_row = db.execute(
        "SELECT id, class_id FROM attendance_sessions WHERE id = ?",
        (session_id,)
    ).fetchone()
    
    if session_row is None:
        db.close()
        return {'status': 'error', 'message': 'Session not found'}, 404

    db.execute("DELETE FROM session_attendance WHERE session_id = ?", (session_id,))
    db.execute("DELETE FROM attendance_records WHERE session_id = ?", (session_id,))
    db.execute("DELETE FROM attendance_sessions WHERE id = ?", (session_id,))
    db.commit()
    db.close()
    
    return {'status': 'success'}, 200
