import webview
import threading
from flask import Flask, render_template, request, jsonify, send_file
import sqlite3
import requests
import csv
import io
import os
import socket
import ipaddress
import concurrent.futures
import re
from datetime import datetime
from config import get_config

app = Flask(__name__)

last_working_host = None
active_class_id = None
active_session_id = None
attendance_session_started_at = None
session_seen_records = set()
session_marked_student_ids = set()
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


def esp32_request(path, params=None, timeout=3):
    global last_working_host
    cfg = get_config()
    hosts_from_settings = cfg.get_esp32_hosts()

    hosts_to_try = []
    if last_working_host:
        hosts_to_try.append(last_working_host)
    for host in hosts_from_settings:
        if host not in hosts_to_try:
            hosts_to_try.append(host)

    errors = []
    for host in hosts_to_try:
        url = f"http://{host}{path}"
        try:
            response = requests.get(url, params=params, timeout=timeout)
            last_working_host = host
            return response, host, None
        except requests.RequestException as ex:
            errors.append(f"{host}: {ex}")

    if not errors:
        errors.append("No ESP32 hosts configured")
    return None, None, " | ".join(errors)

def get_db():
    db = sqlite3.connect("attendance.db")
    db.row_factory = sqlite3.Row
    return db


def get_setting(key, default_value=""):
    """Helper to get setting from config."""
    cfg = get_config()
    return cfg.get(key, default_value)


def set_setting(key, value):
    """Helper to set setting in config."""
    cfg = get_config()
    cfg.set(key, value)


def set_register_job(state, detail='', student_id=None, student_name='', final_result='', error=''):
    with register_lock:
        register_job['state'] = state
        register_job['detail'] = detail
        register_job['student_id'] = student_id
        register_job['student_name'] = student_name
        register_job['final_result'] = final_result
        register_job['error'] = error
        register_job['active'] = state not in ('idle', 'success', 'failed')


def get_register_job_snapshot():
    with register_lock:
        return dict(register_job)


def get_local_ipv4():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return ""


def probe_esp32_host(host, timeout=0.35):
    try:
        response = requests.get(f"http://{host}/status", timeout=timeout)
        if response.status_code != 200:
            return None
        data = response.json()
        if "ap_ip" in data or "sta_connected" in data:
            return {"host": host, "status": data}
    except (requests.RequestException, ValueError):
        return None
    return None


def discover_esp32_host():
    """Discover ESP32 host on network with intelligent fallback."""
    cfg = get_config()
    
    # First, try likely hosts quickly.
    likely_hosts = []
    for h in [last_working_host, cfg.get("esp32_ip"), "192.168.0.103"]:
        if h and h not in likely_hosts:
            likely_hosts.append(h)

    for host in likely_hosts:
        found = probe_esp32_host(host, timeout=0.6)
        if found:
            return found

    # Then scan current local /24 subnet.
    local_ip = get_local_ipv4()
    if not local_ip:
        return None

    try:
        network = ipaddress.ip_network(f"{local_ip}/24", strict=False)
    except ValueError:
        return None

    candidate_hosts = [str(ip) for ip in network.hosts()]
    with concurrent.futures.ThreadPoolExecutor(max_workers=48) as executor:
        futures = [executor.submit(probe_esp32_host, host, 0.25) for host in candidate_hosts]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                return result

    return None


def ensure_column(db, table_name, column_name, definition):
    cursor = db.execute(f"PRAGMA table_info({table_name})")
    cols = [row[1] for row in cursor.fetchall()]
    if column_name not in cols:
        db.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")

def create_tables():
    db = get_db()
    cfg = get_config()
    
    db.execute('''CREATE TABLE IF NOT EXISTS classes (
                    id INTEGER PRIMARY KEY,
                    name TEXT UNIQUE)''')
    db.execute('''CREATE TABLE IF NOT EXISTS students (
                    id INTEGER PRIMARY KEY,
                    name TEXT,
                    class_id INTEGER,
                    registered INTEGER NOT NULL DEFAULT 0)''')
    db.execute('''CREATE TABLE IF NOT EXISTS attendance_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER,
                    class_id INTEGER NOT NULL,
                    student_id INTEGER NOT NULL,
                    student_name TEXT NOT NULL,
                    fingerprint_time TEXT,
                    recorded_at TEXT NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS attendance_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    class_id INTEGER NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT)''')
    db.execute('''CREATE TABLE IF NOT EXISTS session_attendance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    class_id INTEGER NOT NULL,
                    student_id INTEGER NOT NULL,
                    student_name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT '--',
                    marked_at TEXT,
                    UNIQUE(session_id, student_id))''')
    db.execute('''CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL)''')
    ensure_column(db, "students", "class_id", "INTEGER")
    ensure_column(db, "students", "registered", "INTEGER NOT NULL DEFAULT 0")
    ensure_column(db, "attendance_records", "session_id", "INTEGER")
    db.commit()

create_tables()


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
            "SELECT id FROM attendance_sessions WHERE class_id = ? AND ended_at IS NULL ORDER BY id DESC LIMIT 1",
            (resolved_class_id,)
        ).fetchone()
        if open_row is not None:
            resolved_session_id = int(open_row["id"])

    return resolved_class_id, resolved_session_id


def mark_student_present(student_id, student_name='', class_id=None, session_id=None, fingerprint_time=''):
    target_class_id, target_session_id = _resolve_active_session(class_id, session_id)
    if target_class_id is None or target_session_id is None:
        return False

    db = get_db()
    student = db.execute(
        "SELECT id, name FROM students WHERE id = ?",
        (student_id,)
    ).fetchone()
    if student is None:
        return False

    now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    effective_name = student_name.strip() if student_name else student["name"]

    existing = db.execute(
        "SELECT status FROM session_attendance WHERE session_id = ? AND student_id = ?",
        (target_session_id, int(student["id"]))
    ).fetchone()
    if existing is not None and existing["status"] == "Present":
        return True

    if existing is None:
        db.execute(
            "INSERT INTO session_attendance (session_id, class_id, student_id, student_name, status, marked_at) VALUES (?, ?, ?, ?, 'Present', ?)",
            (target_session_id, target_class_id, int(student["id"]), effective_name, now_text)
        )
    else:
        db.execute(
            "UPDATE session_attendance SET status = 'Present', marked_at = ? WHERE session_id = ? AND student_id = ?",
            (now_text, target_session_id, int(student["id"]))
        )
    db.execute(
        "INSERT INTO attendance_records (session_id, class_id, student_id, student_name, fingerprint_time, recorded_at) VALUES (?, ?, ?, ?, ?, ?)",
        (target_session_id, target_class_id, int(student["id"]), effective_name, fingerprint_time or '', now_text)
    )
    db.commit()

    session_marked_student_ids.add(int(student["id"]))
    return True


def sync_attendance_from_esp32(class_id=None, session_id=None):
    target_class_id, target_session_id = _resolve_active_session(class_id, session_id)
    if target_class_id is None:
        return
    if target_session_id is None:
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
                "UPDATE session_attendance SET status = 'Present', marked_at = COALESCE(marked_at, ?) WHERE session_id = ? AND student_id = ?",
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
            "INSERT INTO attendance_records (session_id, class_id, student_id, student_name, fingerprint_time, recorded_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                target_session_id,
                target_class_id,
                student["id"],
                student["name"],
                fingerprint_time,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )
        )
        db.execute(
            "UPDATE session_attendance SET status = 'Present', marked_at = ? WHERE session_id = ? AND student_id = ?",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), target_session_id, student_id)
        )
        session_marked_student_ids.add(student_id)

    db.commit()


def get_attendance_summary(class_id, session_id=None):
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
        return {
            "session_id": None,
            "session_time": "",
            "rows": []
        }

    rows = db.execute(
        """
        SELECT student_id, student_name, status, marked_at
        FROM session_attendance
        WHERE session_id = ?
        ORDER BY student_id
        """,
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

    return {
        "session_id": int(session_row["id"]),
        "session_time": session_row["started_at"],
        "rows": summary_rows
    }


def list_sessions_for_class(class_id):
    db = get_db()
    rows = db.execute(
        "SELECT id, started_at, ended_at FROM attendance_sessions WHERE class_id = ? ORDER BY id DESC",
        (class_id,)
    ).fetchall()
    sessions = []
    for row in rows:
        sessions.append({
            "id": int(row["id"]),
            "started_at": row["started_at"],
            "ended_at": row["ended_at"] or "",
            "label": f"Session {row['id']} - {row['started_at']}"
        })
    return sessions


@app.route('/api/network', methods=['GET', 'POST'])
def network_settings():
    global last_working_host
    cfg = get_config()

    if request.method == 'GET':
        return jsonify({
            'esp32_ip': cfg.get("esp32_ip"),
            'esp32_use_mdns': cfg.get("esp32_use_mdns"),
            'last_working_host': last_working_host or ""
        })

    esp32_ip = request.form.get('esp32_ip', '').strip()
    esp32_use_mdns = request.form.get('esp32_use_mdns', '0').strip()

    if not esp32_ip:
        return jsonify({'status': 'error', 'message': 'ESP32 IP cannot be empty'}), 400

    cfg.set("esp32_ip", esp32_ip)
    cfg.set("esp32_use_mdns", "1" if esp32_use_mdns == "1" else "0")
    last_working_host = None
    return jsonify({'status': 'success'})


@app.route('/api/network/discover', methods=['GET'])
def discover_network():
    global last_working_host

    found = discover_esp32_host()
    if not found:
        return jsonify({'status': 'error', 'message': 'ESP32 not found on current network'}), 404

    host = found["host"]
    set_setting("esp32_ip", host)
    last_working_host = host
    return jsonify({'status': 'success', 'esp32_ip': host, 'device_status': found.get("status", {})})

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/classes', methods=['GET', 'POST'])
def classes():
    db = get_db()
    if request.method == 'POST':
        name = request.form['name']
        try:
            db.execute("INSERT INTO classes (name) VALUES (?)", (name,))
            db.commit()
            return jsonify({'status': 'success'})
        except sqlite3.IntegrityError:
            return jsonify({'status': 'error', 'message': 'Class name already exists'})
    else:
        cursor = db.execute("SELECT * FROM classes ORDER BY id")
        classes = [dict(row) for row in cursor]
        return jsonify(classes)

@app.route('/api/classes/<int:class_id>', methods=['PUT', 'DELETE'])
def class_detail(class_id):
    db = get_db()
    if request.method == 'PUT':
        name = request.form['name']
        try:
            db.execute("UPDATE classes SET name = ? WHERE id = ?", (name, class_id))
            db.commit()
            return jsonify({'status': 'success'})
        except sqlite3.IntegrityError:
            return jsonify({'status': 'error', 'message': 'Class name already exists'})
    elif request.method == 'DELETE':
        db.execute("DELETE FROM session_attendance WHERE class_id = ?", (class_id,))
        db.execute("DELETE FROM attendance_records WHERE class_id = ?", (class_id,))
        db.execute("DELETE FROM attendance_sessions WHERE class_id = ?", (class_id,))
        db.execute("DELETE FROM classes WHERE id = ?", (class_id,))
        db.commit()
        return jsonify({'status': 'success'})

@app.route('/api/students', methods=['GET', 'POST'])
def students():
    db = get_db()
    if request.method == 'POST':
        name = request.form['name']
        student_id = request.form['id']
        class_id = request.form.get('class_id')
        try:
            db.execute("INSERT INTO students (id, name, class_id) VALUES (?, ?, ?)", (student_id, name, class_id))
            db.commit()
            return jsonify({'status': 'success'})
        except sqlite3.IntegrityError:
            return jsonify({'status': 'error', 'message': 'Student ID already exists'})
    else:
        class_id = request.args.get('class_id', type=int)
        if class_id is None:
            cursor = db.execute("SELECT * FROM students ORDER BY id")
        else:
            cursor = db.execute("SELECT * FROM students WHERE class_id = ? ORDER BY id", (class_id,))
        students = [dict(row) for row in cursor]
        return jsonify(students)

@app.route('/api/students/<int:student_id>', methods=['PUT', 'DELETE'])
def student_detail(student_id):
    db = get_db()
    if request.method == 'PUT':
        name = request.form['name']
        new_id = request.form['id']
        try:
            db.execute("UPDATE students SET name = ?, id = ? WHERE id = ?", (name, new_id, student_id))
            db.commit()
            return jsonify({'status': 'success'})
        except sqlite3.IntegrityError:
            return jsonify({'status': 'error', 'message': 'Student ID already exists'})
    elif request.method == 'DELETE':
        db.execute("DELETE FROM students WHERE id = ?", (student_id,))
        db.commit()
        return jsonify({'status': 'success'})

@app.route('/api/register/<int:student_id>')
def register_fingerprint(student_id):
    db = get_db()
    student_row = db.execute("SELECT name, registered FROM students WHERE id = ?", (student_id,)).fetchone()
    if student_row and int(student_row["registered"]) == 1:
        return jsonify({'status': 'error', 'message': 'Student is already registered'}), 409

    student_name = request.args.get('name', '').strip()
    if not student_name:
        if student_row:
            student_name = student_row["name"]

    params = {"id": student_id}
    if student_name:
        params["name"] = student_name

    with register_lock:
        if register_job['active']:
            return jsonify({'status': 'error', 'message': 'Another registration is already running'}), 409
        register_job['active'] = True
        register_job['state'] = 'starting'
        register_job['detail'] = f"{student_name} | {student_id}"
        register_job['student_id'] = student_id
        register_job['student_name'] = student_name
        register_job['final_result'] = ''
        register_job['error'] = ''

    def run_registration():
        try:
            response, host, err = esp32_request('/register', params=params, timeout=120)
            if response is None:
                set_register_job('failed', f"{student_name} | {student_id}", student_id, student_name, 'failed', f'Registration timed out or ESP32 unreachable. {err}')
                return

            if response.status_code == 202:
                # ESP32 accepted the request and is processing it in the background.
                set_register_job('starting', f"{student_name} | {student_id}", student_id, student_name, '', '')
                return

            if response.status_code == 200:
                db_local = get_db()
                db_local.execute("UPDATE students SET registered = 1 WHERE id = ?", (student_id,))
                db_local.commit()
                set_register_job('success', f"{student_name} | {student_id}", student_id, student_name, 'success', '')
                return

            set_register_job('failed', f"{student_name} | {student_id}", student_id, student_name, 'failed', response.text)
        except Exception as ex:
            set_register_job('failed', f"{student_name} | {student_id}", student_id, student_name, 'failed', str(ex))

    threading.Thread(target=run_registration, daemon=True).start()
    return jsonify({'status': 'started', 'student_id': student_id, 'student_name': student_name})


@app.route('/api/register_status', methods=['GET'])
def register_status():
    job_snapshot = get_register_job_snapshot()
    response, host, err = esp32_request('/register_status', timeout=2)
    esp32_state = {}
    if response is not None and response.status_code == 200:
        try:
            esp32_state = response.json()
        except ValueError:
            esp32_state = {}

    esp_state = esp32_state.get('state', '') if isinstance(esp32_state, dict) else ''
    if job_snapshot.get('active') and esp_state in ('success', 'failed'):
        if esp_state == 'success':
            db = get_db()
            sid = job_snapshot.get('student_id')
            if sid is not None:
                db.execute("UPDATE students SET registered = 1 WHERE id = ?", (sid,))
                db.commit()
            set_register_job('success', job_snapshot.get('detail', ''), sid, job_snapshot.get('student_name', ''), 'success', '')
        else:
            esp_detail = ''
            if isinstance(esp32_state, dict):
                esp_detail = str(esp32_state.get('detail', '')).strip()
            final_error = esp_detail if esp_detail else 'ESP32 reported registration failure'
            set_register_job('failed', job_snapshot.get('detail', ''), job_snapshot.get('student_id'), job_snapshot.get('student_name', ''), 'failed', final_error)
        job_snapshot = get_register_job_snapshot()

    return jsonify({
        'status': 'success',
        'job': job_snapshot,
        'esp32_host': host or '',
        'esp32_state': esp32_state,
        'error': err or ''
    })


@app.route('/api/start_attendance')
def start_attendance():
    class_id = request.args.get('class_id', type=int)
    if class_id is None:
        return jsonify({'status': 'error', 'message': 'Missing class_id'}), 400

    global active_class_id
    global active_session_id
    global attendance_session_started_at
    global session_seen_records
    global session_marked_student_ids
    global last_working_host

    db = get_db()
    resolved_class_id, resolved_session_id = _resolve_active_session(active_class_id, active_session_id)

    # If attendance is already active for this class, return the current open session.
    if resolved_session_id is not None and resolved_class_id == class_id:
        existing = db.execute(
            "SELECT id, started_at FROM attendance_sessions WHERE id = ? AND ended_at IS NULL",
            (resolved_session_id,)
        ).fetchone()
        if existing is not None:
            esp32_request('/start_attendance', timeout=6)
            return jsonify({
                'status': 'success',
                'esp32_host': last_working_host or '',
                'class_id': class_id,
                'session_id': int(existing['id']),
                'session_time': existing['started_at']
            })

    # If switching classes while another session is still open, close the old one first.
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
        db.commit()

    # Reset device-side temporary attendance buffer for a fresh session (best effort).
    esp32_request('/clear_attendance', timeout=2)

    # Start attendance on ESP32 with a retry path to handle transient network hiccups.
    response, host, err = esp32_request('/start_attendance', timeout=8)
    if response is None:
        found = discover_esp32_host()
        if found and found.get('host'):
            last_working_host = found.get('host')
        response, host, err = esp32_request('/start_attendance', timeout=8)

    if response is None:
        return jsonify({'status': 'error', 'message': f'Cannot connect to ESP32. {err}'}), 502
    if response.status_code != 200:
        return jsonify({'status': 'error', 'message': response.text, 'esp32_host': host}), response.status_code

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
            "INSERT OR REPLACE INTO session_attendance (session_id, class_id, student_id, student_name, status, marked_at) VALUES (?, ?, ?, ?, '--', NULL)",
            (active_session_id, class_id, int(student["id"]), student["name"])
        )
    db.commit()

    set_setting("attendance_session_started_at", attendance_session_started_at)
    set_setting("active_class_id", str(class_id))
    set_setting("active_session_id", str(active_session_id))
    session_seen_records = set()
    session_marked_student_ids = set()
    active_class_id = class_id

    return jsonify({'status': 'success', 'esp32_host': host, 'class_id': class_id, 'session_id': active_session_id, 'session_time': attendance_session_started_at})


@app.route('/api/stop_attendance')
def stop_attendance():
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

    active_class_id = None
    active_session_id = None
    attendance_session_started_at = None
    set_setting("attendance_session_started_at", "")
    set_setting("active_class_id", "")
    set_setting("active_session_id", "")

    response, host, err = esp32_request('/stop_attendance')
    if response is None:
        return jsonify({'status': 'error', 'message': f'Cannot connect to ESP32. {err}'}), 502
    if response.status_code == 200:
        return jsonify({'status': 'success', 'esp32_host': host})
    return jsonify({'status': 'error', 'message': response.text, 'esp32_host': host}), response.status_code

@app.route('/api/attendance')
def attendance():
    class_id = request.args.get('class_id', type=int)
    session_id = request.args.get('session_id', type=int)
    # ESP32 attendance scan can wait several seconds for a finger; keep timeout aligned.
    response, host, err = esp32_request('/attendance', timeout=15)
    if response is None:
        return jsonify({'status': 'error', 'message': f'Cannot connect to ESP32. {err}'}), 502
    if response.status_code == 200:
        text = response.text or ''
        updated = False
        sid = None
        sname = ''
        m_named = re.search(r"Attendance marked for\s+(.+?)\s+\(ID:\s*(\d+)\)", text)
        if m_named:
            sname = m_named.group(1).strip()
            sid = int(m_named.group(2))
            updated = mark_student_present(sid, sname, class_id=class_id, session_id=session_id)
        else:
            m = re.search(r"ID:\s*(\d+)\)", text)
            if m:
                sid = int(m.group(1))
                updated = mark_student_present(sid, class_id=class_id, session_id=session_id)
        return jsonify({'status': 'success', 'esp32_host': host, 'message': text, 'updated': updated, 'student_id': sid, 'student_name': sname})
    return jsonify({'status': 'error', 'message': response.text, 'esp32_host': host}), response.status_code


@app.route('/api/manual_attendance', methods=['POST'])
def manual_attendance():
    class_id = request.form.get('class_id', type=int)
    session_id = request.form.get('session_id', type=int)
    response, host, err = esp32_request('/attendance', timeout=15)
    if response is None:
        return jsonify({'status': 'error', 'message': f'Cannot connect to ESP32. {err}'}), 502
    if response.status_code == 200:
        text = response.text or ''
        m = re.search(r"Attendance marked for\s+(.+?)\s+\(ID:\s*(\d+)\)", text)
        if m:
            sname = m.group(1).strip()
            sid = int(m.group(2))
            mark_student_present(sid, sname, class_id=class_id, session_id=session_id)
        else:
            m2 = re.search(r"ID:\s*(\d+)\)", text)
            if m2:
                sid = int(m2.group(1))
                mark_student_present(sid, class_id=class_id, session_id=session_id)
        return jsonify({'status': 'success', 'message': response.text, 'esp32_host': host})
    return jsonify({'status': 'error', 'message': response.text, 'esp32_host': host}), response.status_code

@app.route('/api/get_attendance')
def get_attendance():
    class_id = request.args.get('class_id', type=int)
    session_id = request.args.get('session_id', type=int)
    sync_device = request.args.get('sync', default='0') == '1'
    try:
        if sync_device:
            sync_attendance_from_esp32(class_id, session_id)
    except Exception:
        # Keep endpoint responsive even if device sync has transient parsing/network issues.
        pass

    if class_id is None:
        class_id = active_class_id

    if class_id is None:
        return jsonify({'session_id': None, 'session_time': '', 'rows': []})

    return jsonify(get_attendance_summary(class_id, session_id))


@app.route('/api/sessions')
def get_sessions():
    class_id = request.args.get('class_id', type=int)
    if class_id is None:
        return jsonify([])
    return jsonify(list_sessions_for_class(class_id))


@app.route('/api/sessions/<int:session_id>', methods=['DELETE'])
def delete_session(session_id):
    db = get_db()
    session_row = db.execute(
        "SELECT id, class_id FROM attendance_sessions WHERE id = ?",
        (session_id,)
    ).fetchone()
    if session_row is None:
        return jsonify({'status': 'error', 'message': 'Session not found'}), 404

    db.execute("DELETE FROM session_attendance WHERE session_id = ?", (session_id,))
    db.execute("DELETE FROM attendance_records WHERE session_id = ?", (session_id,))
    db.execute("DELETE FROM attendance_sessions WHERE id = ?", (session_id,))
    db.commit()

    global active_session_id
    global active_class_id
    global attendance_session_started_at
    if active_session_id == session_id:
        active_session_id = None
        active_class_id = None
        attendance_session_started_at = None
        set_setting("attendance_session_started_at", "")
        set_setting("active_class_id", "")
        set_setting("active_session_id", "")

    return jsonify({'status': 'success'})


@app.route('/api/export_csv')
def export_csv():
    class_id = request.args.get('class_id', type=int)
    session_id = request.args.get('session_id', type=int)
    if class_id is None:
        class_id = active_class_id
    sync_attendance_from_esp32(class_id, session_id)

    if class_id is None:
        return jsonify({'status': 'error', 'message': 'No class selected'}), 400

    summary = get_attendance_summary(class_id, session_id)
    attendance_data = summary.get("rows", [])

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Sr No", "Student Name", "ID", "Date and Time of Session", "Attendance", "Marked At"])
    for record in attendance_data:
        writer.writerow([
            record["sr_no"],
            record["name"],
            record["id"],
            summary.get("session_time", ""),
            record["status"],
            record["marked_at"]
        ])
    output.seek(0)
    return send_file(io.BytesIO(output.getvalue().encode()), mimetype='text/csv', as_attachment=True, download_name='attendance.csv')

def run_flask():
    app.run(port=5000, debug=False, use_reloader=False)

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    webview.create_window('Attendance System Admin', 'http://127.0.0.1:5000', width=1200, height=800)
    webview.start()