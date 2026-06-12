"""
Student registration management module.
Now integrates with cloud sync and ConnectionManager for template handling.
"""

import base64
import threading
from datetime import datetime
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import get_config
from database import get_db
from network import esp32_request
from connection import get_connection
from cloud_sync import get_cloud

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
            "SELECT id FROM attendance_sessions WHERE class_id = ? "
            "AND ended_at IS NULL ORDER BY id DESC LIMIT 1",
            (resolved_class_id,)
        ).fetchone()
        db.close()
        if open_row is not None:
            resolved_session_id = int(open_row["id"])

    return resolved_class_id, resolved_session_id


def set_register_job(state, detail='', student_id=None, student_name='',
                     final_result='', error=''):
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


def extract_and_upload_template(student_id, student_name, class_id):
    """
    After successful enrollment, extract template from ESP32 sensor
    and upload to cloud. This is the key function that makes the
    fingerprint sensor act as a temporary cache.
    """
    conn = get_connection()
    cloud = get_cloud()

    # Ask ESP32 to extract the template from the sensor
    result = conn.send_command({"cmd": "get_template", "id": student_id},
                               timeout=15.0)
    if not result or result.get("status") != "success":
        print(f"[REG] Failed to extract template for student {student_id}")
        return False

    template_b64 = result.get("template", "")
    if not template_b64:
        print(f"[REG] Empty template for student {student_id}")
        return False

    template_bytes = base64.b64decode(template_b64)
    print(f"[REG] Extracted template: {len(template_bytes)} bytes")

    # Upload to cloud (with local cache fallback)
    cloud.upload_template(class_id, student_id, student_name, template_bytes)
    print(f"[REG] Template uploaded to cloud for student {student_id}")
    return True


def load_class_to_device(class_id):
    """
    Download all templates for a class from cloud and push them to ESP32.
    This loads the fingerprint sensor's temporary cache for the session.
    """
    conn = get_connection()
    cloud = get_cloud()

    # Get student list from database
    db = get_db()
    students = db.execute(
        "SELECT id, name FROM students WHERE class_id = ? AND registered = 1 "
        "ORDER BY id", (class_id,)
    ).fetchall()
    db.close()

    if not students:
        print(f"[REG] No registered students in class {class_id}")
        return {"status": "error", "message": "No registered students"}

    # Download templates from cloud (falls back to local cache if offline)
    templates = cloud.download_class_templates(class_id)

    if not templates:
        # Try loading from ESP32's SD card as last resort
        result = conn.send_command(
            {"cmd": "load_class_from_sd", "class_id": class_id}, timeout=30.0
        )
        if result and result.get("status") == "success":
            return {
                "status": "success",
                "loaded": result.get("loaded", 0),
                "source": "sd_card"
            }
        return {"status": "error", "message": "No templates available"}

    # Push templates to ESP32 via WiFi (fast) or BLE (slower)
    student_list = [{"id": int(s["id"]), "name": s["name"]} for s in students]

    # First, send the load_class command with student roster
    result = conn.send_command({
        "cmd": "load_class",
        "class_id": class_id,
        "students": student_list
    }, timeout=5.0)

    # Then send each template
    sent_count = 0
    for tpl in templates:
        success = conn.send_template(
            class_id,
            tpl["student_id"],
            tpl["name"],
            tpl["template_bytes"]
        )
        if success:
            sent_count += 1

    # Now tell ESP32 to load them from its SD cache
    result = conn.send_command(
        {"cmd": "load_class_from_sd", "class_id": class_id}, timeout=30.0
    )

    loaded = result.get("loaded", 0) if result else 0
    return {
        "status": "success",
        "loaded": loaded,
        "sent": sent_count,
        "total_students": len(students),
        "source": "cloud"
    }


def start_attendance_session(class_id):
    """
    Start attendance session for a class.
    Always starts a new session (closes any previous open session).
    """
    global active_class_id, active_session_id, attendance_session_started_at

    from network import set_last_working_host, get_last_working_host, discover_esp32_host

    db = get_db()

    # Close any existing open session first
    open_sessions = db.execute(
        "SELECT id FROM attendance_sessions WHERE class_id = ? AND ended_at IS NULL",
        (class_id,)
    ).fetchall()
    for sess in open_sessions:
        db.execute(
            "UPDATE session_attendance SET status = 'Absent' WHERE session_id = ? AND status = '--'",
            (sess["id"],)
        )
        db.execute(
            "UPDATE attendance_sessions SET ended_at = ? WHERE id = ?",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), sess["id"])
        )
    db.commit()

    # ─── CACHE MODE: Load class templates from DB into sensor ───
    import base64
    import requests as req_lib
    ip = get_config().get("esp32_ip", "192.168.0.103")

    templates = db.execute(
        "SELECT ft.student_id, ft.template_data, ft.template_size, s.name "
        "FROM fingerprint_templates ft "
        "JOIN students s ON s.id = ft.student_id "
        "WHERE ft.class_id = ? ORDER BY ft.student_id",
        (class_id,)
    ).fetchall()

    # Clear sensor cache and attendance buffer
    esp32_request('/clear_attendance', timeout=3)
    try:
        req_lib.post(f"http://{ip}/command", json={"cmd": "clear_sensor"}, timeout=8)
    except Exception as e:
        print(f"[ATT] clear_sensor warning: {e}")

    loaded = 0
    for tpl in templates:
        sid = tpl["student_id"]
        name = tpl["name"]
        b64 = base64.b64encode(tpl["template_data"]).decode()
        try:
            payload = {
                "cmd": "upload_template",
                "student_id": sid,
                "class_id": class_id,
                "name": name,
                "template": b64
            }
            r = req_lib.post(f"http://{ip}/command", json=payload, timeout=20)
            if r.status_code == 200 and r.json().get("status") == "success":
                loaded += 1
                print(f"[ATT] Loaded {name} (ID:{sid}) into sensor")
            else:
                print(f"[ATT] Failed loading {name}: {r.text[:120]}")
        except Exception as e:
            print(f"[ATT] Error loading {name}: {e}")

    print(f"[ATT] {loaded}/{len(templates)} templates loaded into sensor")

    esp32_request('/start_attendance', timeout=5)
    print(f"[ATT] Attendance started")
    print(f"[ATT] Attendance started")

    attendance_session_started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur = db.execute(
        "INSERT INTO attendance_sessions (class_id, started_at, ended_at) "
        "VALUES (?, ?, NULL)",
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
        'class_id': class_id,
        'session_id': active_session_id,
        'session_time': attendance_session_started_at
    }


def stop_attendance_session():
    """Stop current attendance session and sync attendance to cloud."""
    global active_class_id, active_session_id, attendance_session_started_at

    resolved_class_id, resolved_session_id = _resolve_active_session(
        active_class_id, active_session_id)

    if resolved_session_id is not None and resolved_class_id is not None:
        db = get_db()
        db.execute(
            "UPDATE session_attendance SET status = 'Absent' "
            "WHERE session_id = ? AND status = '--'",
            (resolved_session_id,)
        )
        db.execute(
            "UPDATE attendance_sessions SET ended_at = ? WHERE id = ?",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), resolved_session_id)
        )
        db.commit()

        # Sync attendance records to cloud
        try:
            cloud = get_cloud()
            rows = db.execute(
                "SELECT student_id, student_name, status, marked_at "
                "FROM session_attendance WHERE session_id = ?",
                (resolved_session_id,)
            ).fetchall()
            records = [
                {
                    "student_id": int(r["student_id"]),
                    "name": r["student_name"],
                    "status": r["status"],
                    "marked_at": r["marked_at"] or ""
                }
                for r in rows
            ]
            cloud.upload_attendance(resolved_class_id, resolved_session_id, records)
        except Exception as e:
            print(f"[REG] Cloud attendance sync failed: {e}")

        db.close()

    active_class_id = None
    active_session_id = None
    attendance_session_started_at = None

    cfg = get_config()
    cfg.set("attendance_session_started_at", "")
    cfg.set("active_class_id", "")
    cfg.set("active_session_id", "")

    response, host, err = esp32_request('/stop_attendance')
    
    # Clear only the attendance buffer - templates stay on sensor
    esp32_request('/clear_attendance', timeout=3)
    
    if response is None:
        return {'status': 'error', 'message': 'Cannot connect to ESP32.'}, 502

    return {'status': 'success'}
