"""
Flask API routes module.
Handles all HTTP endpoints for the attendance system.
"""

import re
import io
import csv
import threading
from flask import render_template, request, jsonify, send_file
from config import get_config
from database import (
    get_db, initialize_database, get_classes, add_class, update_class, 
    delete_class, get_students, add_student, update_student, delete_student
)
from network import esp32_request, discover_esp32_host, set_last_working_host, get_last_working_host
from attendance import (
    mark_student_present, sync_attendance_from_esp32, 
    get_attendance_summary, list_sessions_for_class, delete_session
)
from registration import (
    _resolve_active_session, set_register_job, get_register_job_snapshot,
    start_attendance_session, stop_attendance_session, register_lock
)

# Initialize database on module load
initialize_database()

active_class_id = None
active_session_id = None


def setup_routes(app):
    """Setup all Flask API routes."""

    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/api/network', methods=['GET', 'POST'])
    def network_settings():
        cfg = get_config()
        if request.method == 'GET':
            return jsonify({
                'esp32_ip': cfg.get("esp32_ip"),
                'esp32_use_mdns': cfg.get("esp32_use_mdns"),
                'last_working_host': get_last_working_host() or ""
            })

        esp32_ip = request.form.get('esp32_ip', '').strip()
        esp32_use_mdns = request.form.get('esp32_use_mdns', '0').strip()

        if not esp32_ip:
            return jsonify({'status': 'error', 'message': 'ESP32 IP cannot be empty'}), 400

        cfg.set("esp32_ip", esp32_ip)
        cfg.set("esp32_use_mdns", "1" if esp32_use_mdns == "1" else "0")
        set_last_working_host(None)
        return jsonify({'status': 'success'})

    @app.route('/api/network/discover', methods=['GET'])
    def discover_network():
        found = discover_esp32_host()
        if not found:
            return jsonify({'status': 'error', 'message': 'ESP32 not found on current network'}), 404

        host = found["host"]
        get_config().set("esp32_ip", host)
        set_last_working_host(host)
        return jsonify({'status': 'success', 'esp32_ip': host, 'device_status': found.get("status", {})})

    @app.route('/api/classes', methods=['GET', 'POST'])
    def classes():
        if request.method == 'POST':
            name = request.form['name']
            result = add_class(name)
            return jsonify(result) if result['status'] == 'success' else (jsonify(result), 409)
        return jsonify(get_classes())

    @app.route('/api/classes/<int:class_id>', methods=['PUT', 'DELETE'])
    def class_detail(class_id):
        if request.method == 'PUT':
            name = request.form['name']
            result = update_class(class_id, name)
            return jsonify(result) if result['status'] == 'success' else (jsonify(result), 409)
        elif request.method == 'DELETE':
            delete_class(class_id)
            return jsonify({'status': 'success'})

    @app.route('/api/students', methods=['GET', 'POST'])
    def students():
        if request.method == 'POST':
            name = request.form['name']
            student_id = request.form['id']
            class_id = request.form.get('class_id')
            result = add_student(student_id, name, class_id)
            return jsonify(result) if result['status'] == 'success' else (jsonify(result), 409)
        
        class_id = request.args.get('class_id', type=int)
        return jsonify(get_students(class_id))

    @app.route('/api/students/<int:student_id>', methods=['PUT', 'DELETE'])
    def student_detail(student_id):
        if request.method == 'PUT':
            name = request.form['name']
            new_id = request.form['id']
            result = update_student(student_id, new_id, name)
            return jsonify(result) if result['status'] == 'success' else (jsonify(result), 409)
        elif request.method == 'DELETE':
            delete_student(student_id)
            return jsonify({'status': 'success'})

    @app.route('/api/register/<int:student_id>')
    def register_fingerprint(student_id):
        db = get_db()
        student_row = db.execute(
            "SELECT name, registered FROM students WHERE id = ?", (student_id,)
        ).fetchone()
        db.close()
        
        if student_row and int(student_row["registered"]) == 1:
            return jsonify({'status': 'error', 'message': 'Student is already registered'}), 409

        student_name = request.args.get('name', '').strip()
        if not student_name and student_row:
            student_name = student_row["name"]

        params = {"id": student_id}
        if student_name:
            params["name"] = student_name

        with register_lock:
            if get_register_job_snapshot()['active']:
                return jsonify({'status': 'error', 'message': 'Another registration is running'}), 409
            set_register_job('starting', f"{student_name} | {student_id}", student_id, student_name)

        def run_registration():
            try:
                response, host, err = esp32_request('/register', params=params, timeout=120)
                if response is None:
                    set_register_job('failed', f"{student_name} | {student_id}", student_id, 
                                   student_name, 'failed', f'Timeout. {err}')
                    return

                if response.status_code == 202:
                    set_register_job('starting', f"{student_name} | {student_id}", student_id, student_name)
                    return

                if response.status_code == 200:
                    db = get_db()
                    db.execute("UPDATE students SET registered = 1 WHERE id = ?", (student_id,))
                    db.commit()
                    db.close()
                    set_register_job('success', f"{student_name} | {student_id}", student_id, 
                                   student_name, 'success')
                    return

                set_register_job('failed', f"{student_name} | {student_id}", student_id, 
                               student_name, 'failed', response.text)
            except Exception as ex:
                set_register_job('failed', f"{student_name} | {student_id}", student_id, 
                               student_name, 'failed', str(ex))

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
                pass

        esp_state = esp32_state.get('state', '') if isinstance(esp32_state, dict) else ''
        if job_snapshot.get('active') and esp_state in ('success', 'failed'):
            if esp_state == 'success':
                db = get_db()
                sid = job_snapshot.get('student_id')
                if sid:
                    db.execute("UPDATE students SET registered = 1 WHERE id = ?", (sid,))
                    db.commit()
                db.close()
                set_register_job('success', job_snapshot.get('detail', ''), sid,
                               job_snapshot.get('student_name', ''), 'success')
            else:
                esp_detail = str(esp32_state.get('detail', '')).strip() if isinstance(esp32_state, dict) else ''
                final_error = esp_detail if esp_detail else 'ESP32 reported failure'
                set_register_job('failed', job_snapshot.get('detail', ''),
                               job_snapshot.get('student_id'), job_snapshot.get('student_name', ''),
                               'failed', final_error)

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
        return start_attendance_session(class_id)

    @app.route('/api/stop_attendance')
    def stop_attendance():
        return stop_attendance_session()

    @app.route('/api/attendance')
    def attendance():
        class_id = request.args.get('class_id', type=int)
        session_id = request.args.get('session_id', type=int)
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
            return jsonify({'status': 'success', 'esp32_host': host, 'message': text,
                          'updated': updated, 'student_id': sid, 'student_name': sname})
        
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
    def delete_session_route(session_id):
        result, code = delete_session(session_id)
        return jsonify(result), code

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
        return send_file(io.BytesIO(output.getvalue().encode()), 
                        mimetype='text/csv', as_attachment=True, download_name='attendance.csv')
