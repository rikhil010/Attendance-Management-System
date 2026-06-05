"""
Flask API routes module.
Handles all HTTP endpoints for the attendance system.
"""

import sys
import os
import re
import io
import csv
import threading
from flask import render_template, request, jsonify, send_file

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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
    start_attendance_session, stop_attendance_session, register_lock,
    extract_and_upload_template, load_class_to_device
)
from connection import get_connection
from cloud_sync import get_cloud

# Try to import BLE functionality, but don't fail if bleak is not installed
try:
    from ble import discover_esp32_ble, get_ble_status
    ble_available = True
except ImportError:
    ble_available = False
    # Provide fallback functions
    def discover_esp32_ble(timeout=10):
        return None, "BLE module not available"
    
    def get_ble_status():
        return {'available': False, 'message': 'bleak library not installed'}

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

    @app.route('/api/network/discover_ble', methods=['GET'])
    def discover_ble():
        """Discover ESP32 via BLE and connect."""
        conn = get_connection()
        conn_info = conn.get_connection_info()
        
        if not conn_info.get('ble_available'):
            return jsonify({
                'status': 'error',
                'message': 'BLE not available. Install bleak: pip install bleak'
            }), 400

        try:
            success = conn.connect_ble()
            if success:
                # Try to get device status over BLE to confirm it works
                status = conn.get_status()
                return jsonify({
                    'status': 'success',
                    'message': 'Connected to GWASOAT device via BLE',
                    'ble_address': conn.ble_address,
                    'device_status': status or {}
                })
            else:
                return jsonify({
                    'status': 'not_found',
                    'message': 'GWASOAT device not found. Make sure ESP32 is powered on.'
                }), 404
        except Exception as e:
            return jsonify({
                'status': 'error',
                'message': f'BLE connection failed: {str(e)}'
            }), 500

    @app.route('/api/network/ble_status', methods=['GET'])
    def ble_status():
        """Get BLE module status."""
        return jsonify(get_ble_status())

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
                    # Extract template from ESP32 and upload to cloud
                    class_id_for_reg = request.args.get('class_id', type=int) or 0
                    try:
                        extract_and_upload_template(student_id, student_name, class_id_for_reg)
                    except Exception as cloud_err:
                        print(f"[REG] Cloud upload warning: {cloud_err}")
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
        
        # Pre-check: Ensure ESP32 is reachable before starting attendance
        response, host, err = esp32_request('/status', timeout=5)
        if response is None:
            return jsonify({
                'status': 'error', 
                'message': f'Cannot reach ESP32. Please check connection and try again. Error: {err}'
            }), 502
        
        # ESP32 is reachable, start attendance
        return start_attendance_session(class_id)

    @app.route('/api/stop_attendance')
    def stop_attendance():
        return stop_attendance_session()

    @app.route('/api/attendance')
    def attendance():
        class_id = request.args.get('class_id', type=int)
        session_id = request.args.get('session_id', type=int)
        
        # Try WiFi first
        response, host, err = esp32_request('/attendance', timeout=3)
        
        if response is not None and response.status_code == 200:
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
            return jsonify({'status': 'success', 'message': text,
                          'updated': updated, 'student_id': sid, 'student_name': sname})
        
        # WiFi failed — try BLE via ConnectionManager
        conn = get_connection()
        result = conn.send_command({"cmd": "get_attendance"}, timeout=5.0)
        if result is not None:
            # Parse attendance array from BLE response
            records = result if isinstance(result, list) else []
            if records:
                last = records[-1] if records else {}
                sid = last.get("id")
                sname = last.get("name", "")
                if sid:
                    updated = mark_student_present(sid, sname, class_id=class_id, session_id=session_id)
                    return jsonify({'status': 'success', 'updated': updated,
                                  'student_id': sid, 'student_name': sname,
                                  'message': f'Attendance marked for {sname} (ID: {sid})'})
            return jsonify({'status': 'success', 'updated': False, 'message': 'Waiting for fingerprint'})
        
        return jsonify({'status': 'error', 'message': 'Cannot connect to ESP32 (WiFi and BLE failed)'}), 502

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

    # ─── New Routes: Cloud Sync, Class Loading, Connection Info ───

    @app.route('/api/load_class', methods=['POST'])
    def load_class():
        """Load class templates from cloud to ESP32 device."""
        class_id = request.form.get('class_id', type=int)
        if class_id is None:
            return jsonify({'status': 'error', 'message': 'Missing class_id'}), 400
        result = load_class_to_device(class_id)
        return jsonify(result)

    @app.route('/api/connection', methods=['GET'])
    def connection_info():
        """Get current connection status (WiFi/BLE)."""
        conn = get_connection()
        info = conn.get_connection_info()
        return jsonify(info)

    @app.route('/api/connection/ble_connect', methods=['POST'])
    def ble_connect():
        """Manually trigger BLE connection."""
        conn = get_connection()
        success = conn.connect_ble()
        return jsonify({
            'status': 'success' if success else 'error',
            'ble_connected': success,
            'mode': conn.mode
        })

    @app.route('/api/cloud/status', methods=['GET'])
    def cloud_status():
        """Check cloud connectivity."""
        cloud = get_cloud()
        online = cloud.check_connection()
        return jsonify({
            'status': 'success',
            'online': online,
            'base_url': cloud.base_url
        })

    @app.route('/api/cloud/sync', methods=['POST'])
    def cloud_sync():
        """Sync pending uploads (templates + attendance) to cloud."""
        cloud = get_cloud()
        templates_synced = cloud.sync_pending_templates()
        attendance_synced = cloud.sync_pending_attendance()
        return jsonify({
            'status': 'success',
            'templates_synced': templates_synced,
            'attendance_synced': attendance_synced
        })

    @app.route('/api/device/status', methods=['GET'])
    def device_status():
        """Get ESP32 device status via ConnectionManager."""
        conn = get_connection()
        result = conn.get_status()
        if result:
            return jsonify(result)
        return jsonify({'status': 'error', 'message': 'Cannot reach device'}), 502
