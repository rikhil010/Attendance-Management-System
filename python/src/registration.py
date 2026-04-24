"""
Student registration management module.
"""

import threading
from datetime import datetime
from config import get_config
from database import get_db
from network import esp32_request

active_class_id = None
active_session_id = None
attendance_session_started_at = None

register_lock = threading.Lock()
register_job = {
    'active': False,
    'state': 'idle',
    'detail': '',
    'student_id': None,
    'student_name': '',
    'final_result': '',
    'error': ''
}


def _resolve_active_session(class_id=None, session_id=None):
    """Resolve active session from parameters or stored settings."""
    cfg = get_config()
    
    resolved_class_id = class_id if class_id is not None else active_class_id
    if resolved_class_id is None:
        class_setting = cfg.get("active_class_id", "").strip()
        if class_setting:
            try:
                resolved_class_id = int(class_setting)
            except ValueError:
                resolved_class_id = None

    resolved_session_id = session_id if session_id is not None else active_session_id
    if resolved_session_id is None:
        session_setting = cfg.get("active_session_id", "").strip()
        if session_setting:
            try:
                resolved_session_id = int(session_setting)
            except ValueError:
                resolved_session_id = None

    if resolved_session_id is None and resolved_class_id is not None:
        db = get_db()
        open_row = db.execute(
            "SELECT id FROM attendance_sessions WHERE class_id = ? AND ended_at IS NULL "
            "ORDER BY id DESC LIMIT 1",
            (resolved_class_id,)
        ).fetchone()
        db.close()
        if open_row is not None:
            resolved_session_id = int(open_row["id"])

    return resolved_class_id, resolved_session_id


def set_register_job(state, detail='', student_id=None, student_name='', final_result='', error=''):
    """Update registration job status."""
    with register_lock:
        register_job['state'] = state
        register_job['detail'] = detail
        register_job['student_id'] = student_id
        register_job['student_name'] = student_name
        register_job['final_result'] = final_result
        register_job['error'] = error
        register_job['active'] = state not in ('idle', 'success', 'failed')


def get_register_job_snapshot():
    """Get current registration job status."""
    with register_lock:
        return dict(register_job)


def start_attendance_session(class_id):
    """Start attendance session for a class."""
    global active_class_id
    global active_session_id
    global attendance_session_started_at
    
    from network import set_last_working_host, get_last_working_host, discover_esp32_host
    
    db = get_db()
    resolved_class_id, resolved_session_id = _resolve_active_session(active_class_id, active_session_id)

    # If attendance already active for this class, return current session
    if resolved_session_id is not None and resolved_class_id == class_id:
        existing = db.execute(
            "SELECT id, started_at FROM attendance_sessions WHERE id = ? AND ended_at IS NULL",
            (resolved_session_id,)
        ).fetchone()
        if existing is not None:
            esp32_request('/start_attendance', timeout=6)
            db.close()
            return {
                'status': 'success',
                'esp32_host': get_last_working_host() or '',
                'class_id': class_id,
                'session_id': int(existing['id']),
                'session_time': existing['started_at']
            }

    # Close old session if switching classes
    if resolved_session_id is not None and resolved_class_id is not None and resolved_class_id != class_id:
        closed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db.execute(
            "UPDATE session_attendance SET status = 'Absent' WHERE session_id = ? AND status = '--'",
            (resolved_session_id,)
        )
        db.execute(
            "UPDATE attendance_sessions SET ended_at = ? WHERE id = ?",
            (closed_at, resolved_session_id)
        )

    # Clear device attendance buffer
    esp32_request('/clear_attendance', timeout=2)

    # Start attendance on ESP32
    response, host, err = esp32_request('/start_attendance', timeout=8)
    if response is None:
        found = discover_esp32_host()
        if found and found.get('host'):
            set_last_working_host(found.get('host'))
        response, host, err = esp32_request('/start_attendance', timeout=8)

    if response is None:
        db.close()
        return {'status': 'error', 'message': f'Cannot connect to ESP32. {err}'}, 502
    
    if response.status_code != 200:
        db.close()
        return {'status': 'error', 'message': response.text, 'esp32_host': host}, response.status_code

    attendance_session_started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur = db.execute(
        "INSERT INTO attendance_sessions (class_id, started_at, ended_at) VALUES (?, ?, NULL)",
        (class_id, attendance_session_started_at)
    )
    active_session_id = int(cur.lastrowid)
    
    students = db.execute(
        "SELECT id, name FROM students WHERE class_id = ? ORDER BY id",
        (class_id,)
    ).fetchall()
    
    for student in students:
        db.execute(
            "INSERT OR REPLACE INTO session_attendance "
            "(session_id, class_id, student_id, student_name, status, marked_at) "
            "VALUES (?, ?, ?, ?, '--', NULL)",
            (active_session_id, class_id, int(student["id"]), student["name"])
        )
    
    db.commit()

    get_config().set("attendance_session_started_at", attendance_session_started_at)
    get_config().set("active_class_id", str(class_id))
    get_config().set("active_session_id", str(active_session_id))
    
    from attendance import session_seen_records, session_marked_student_ids
    session_seen_records.clear()
    session_marked_student_ids.clear()
    active_class_id = class_id

    db.close()
    return {
        'status': 'success',
        'esp32_host': host,
        'class_id': class_id,
        'session_id': active_session_id,
        'session_time': attendance_session_started_at
    }


def stop_attendance_session():
    """Stop current attendance session."""
    global active_class_id
    global active_session_id
    global attendance_session_started_at

    resolved_class_id, resolved_session_id = _resolve_active_session(active_class_id, active_session_id)
    if resolved_session_id is not None and resolved_class_id is not None:
        db = get_db()
        db.execute(
            "UPDATE session_attendance SET status = 'Absent' WHERE session_id = ? AND status = '--'",
            (resolved_session_id,)
        )
        db.execute(
            "UPDATE attendance_sessions SET ended_at = ? WHERE id = ?",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), resolved_session_id)
        )
        db.commit()
        db.close()

    active_class_id = None
    active_session_id = None
    attendance_session_started_at = None
    
    cfg = get_config()
    cfg.set("attendance_session_started_at", "")
    cfg.set("active_class_id", "")
    cfg.set("active_session_id", "")

    response, host, err = esp32_request('/stop_attendance')
    if response is None:
        return {'status': 'error', 'message': f'Cannot connect to ESP32. {err}'}, 502
    
    if response.status_code == 200:
        return {'status': 'success', 'esp32_host': host}
    
    return {'status': 'error', 'message': response.text, 'esp32_host': host}, response.status_code
