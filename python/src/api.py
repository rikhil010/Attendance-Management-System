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
    register_job, extract_and_upload_template, load_class_to_device
)
from connection import get_connection
from cloud_sync import get_cloud
from wifi_manager import (
    get_current_ssid, connect_to_hotspot, get_ip_for_current_network, auto_sync_ip
)

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
            # Auto-sync IP based on current WiFi
            sync_result = auto_sync_ip()
            return jsonify({
                'esp32_ip': cfg.get("esp32_ip"),
                'esp32_use_mdns': cfg.get("esp32_use_mdns"),
                'last_working_host': get_last_working_host() or "",
                'current_ssid': sync_result.get("ssid", ""),
                'mode': sync_result.get("mode", "online")
            })

        esp32_ip = request.form.get('esp32_ip', '').strip()
        esp32_use_mdns = request.form.get('esp32_use_mdns', '0').strip()

        if not esp32_ip:
            return jsonify({'status': 'error', 'message': 'ESP32 IP cannot be empty'}), 400

        cfg.set("esp32_ip", esp32_ip)
        # Save as router IP if not the hotspot IP
        if esp32_ip != "192.168.4.1":
            cfg.set("router_esp32_ip", esp32_ip)
        cfg.set("esp32_use_mdns", "1" if esp32_use_mdns == "1" else "0")
        set_last_working_host(esp32_ip)
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

    @app.route('/api/network/offline_mode', methods=['POST'])
    def offline_mode():
        """Connect laptop WiFi to ESP32 hotspot and switch IP."""
        import threading

        def do_connect():
            pass  # Connection happens below

        success = connect_to_hotspot()
        if success:
            cfg = get_config()
            cfg.set("esp32_ip", "192.168.4.1")
            set_last_working_host("192.168.4.1")
            return jsonify({
                'status': 'success',
                'message': 'Connected to ESP32 hotspot',
                'esp32_ip': '192.168.4.1',
                'ssid': 'GWASOAT-Device'
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Failed to connect to GWASOAT-Device hotspot. '
                           'Make sure ESP32 is powered on and in range.'
            }), 500

    @app.route('/api/network/sync_ip', methods=['GET'])
    def sync_ip():
        """Auto-detect WiFi and sync ESP32 IP accordingly."""
        result = auto_sync_ip()
        return jsonify({
            'status': 'success',
            'ssid': result['ssid'],
            'esp32_ip': result['esp32_ip'],
            'changed': result['changed'],
            'mode': result['mode']
        })

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
            "SELECT name, registered, class_id FROM students WHERE id = ?", (student_id,)
        ).fetchone()
        db.close()

        if student_row is None:
            return jsonify({'status': 'error', 'message': 'Student not found in database'}), 404

        student_name = request.args.get('name', '').strip()
        if not student_name:
            student_name = student_row["name"]

        # Reset any stuck job directly (no lock nesting)
        register_job['active'] = False
        register_job['state'] = 'starting'
        register_job['detail'] = f"{student_name} | {student_id}"
        register_job['student_id'] = student_id
        register_job['student_name'] = student_name
        register_job['final_result'] = ''
        register_job['error'] = ''
        register_job['active'] = True

        params = {"id": student_id, "name": student_name}

        def run_registration():
            try:
                print(f"[REGISTER] Sending to ESP32: /register?id={student_id}&name={student_name}")
                response, host, err = esp32_request('/register', params=params, timeout=10)
                print(f"[REGISTER] Response: host={host}, err={err}, status={response.status_code if response else 'None'}")
                
                if response is None:
                    register_job['state'] = 'failed'
                    register_job['final_result'] = 'failed'
                    register_job['error'] = f'Cannot reach ESP32. {err}'
                    register_job['active'] = False
                    return

                if response.status_code not in (200, 202):
                    register_job['state'] = 'failed'
                    register_job['final_result'] = 'failed'
                    register_job['error'] = f'ESP32 returned {response.status_code}'
                    register_job['active'] = False
                    return

                # ESP32 accepted - now poll until registration completes
                print(f"[REGISTER] Waiting for ESP32 to finish enrollment...")
                import time
                for _ in range(60):  # Poll for up to 60 seconds
                    time.sleep(1)
                    resp, _, _ = esp32_request('/register_status', timeout=3)
                    if resp and resp.status_code == 200:
                        try:
                            state_data = resp.json()
                            esp_state = state_data.get('state', '')
                            register_job['state'] = esp_state
                            print(f"[REGISTER] ESP32 state: {esp_state}")
                            
                            if esp_state == 'success':
                                # Registration done! Extract template NOW
                                print(f"[REGISTER] Success! Extracting template...")
                                import base64
                                from datetime import datetime
                                
                                db2 = get_db()
                                db2.execute("UPDATE students SET registered = 1 WHERE id = ?", (student_id,))
                                
                                tpl_resp, _, _ = esp32_request('/get_template', params={'id': student_id}, timeout=10)
                                if tpl_resp and tpl_resp.status_code == 200:
                                    tpl_data = tpl_resp.json()
                                    if tpl_data.get('status') == 'success' and tpl_data.get('template'):
                                        template_bytes = base64.b64decode(tpl_data['template'])
                                        s_row = db2.execute("SELECT class_id FROM students WHERE id = ?", (student_id,)).fetchone()
                                        cid = s_row['class_id'] if s_row else 0
                                        db2.execute(
                                            "INSERT OR REPLACE INTO fingerprint_templates "
                                            "(student_id, class_id, template_data, template_size, created_at) "
                                            "VALUES (?, ?, ?, ?, ?)",
                                            (student_id, cid, template_bytes, len(template_bytes),
                                             datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                                        )
                                        print(f"[REGISTER] Template saved: {len(template_bytes)} bytes")
                                        # Delete from sensor
                                        esp32_request('/delete', params={'id': student_id}, timeout=5)
                                        print(f"[REGISTER] Deleted from sensor")
                                    else:
                                        print(f"[REGISTER] Template extraction failed: {tpl_data}")
                                else:
                                    print(f"[REGISTER] get_template request failed")
                                
                                db2.commit()
                                db2.close()
                                register_job['final_result'] = 'success'
                                register_job['active'] = False
                                return
                            
                            elif esp_state == 'failed':
                                register_job['final_result'] = 'failed'
                                register_job['error'] = state_data.get('detail', 'Failed')
                                register_job['active'] = False
                                return
                        except ValueError:
                            pass
                
                # Timeout
                register_job['state'] = 'failed'
                register_job['final_result'] = 'failed'
                register_job['error'] = 'Registration timeout (60s)'
                register_job['active'] = False
                
            except Exception as ex:
                register_job['state'] = 'failed'
                register_job['final_result'] = 'failed'
                register_job['error'] = str(ex)
                register_job['active'] = False
                print(f"[REGISTER] EXCEPTION: {ex}")

        threading.Thread(target=run_registration, daemon=True).start()
        return jsonify({'status': 'started', 'student_id': student_id, 'student_name': student_name})

    @app.route('/api/register_status', methods=['GET'])
    def register_status():
        # Get local job state
        job_snapshot = dict(register_job)
        
        # Poll ESP32 for device-side registration state
        esp32_state = {}
        response, host, err = esp32_request('/register_status', timeout=2)
        if response is not None and response.status_code == 200:
            try:
                esp32_state = response.json()
            except ValueError:
                pass

        # If ESP32 reports success/failed, update local job
        esp_state = esp32_state.get('state', '')
        if job_snapshot.get('active') and esp_state in ('success', 'failed'):
            if esp_state == 'success':
                sid = job_snapshot.get('student_id')
                if sid:
                    db = get_db()
                    db.execute("UPDATE students SET registered = 1 WHERE id = ?", (sid,))
                    db.commit()
                    
                    # Extract template from ESP32 and save to database
                    try:
                        tpl_resp, _, _ = esp32_request('/get_template', params={'id': sid}, timeout=10)
                        if tpl_resp and tpl_resp.status_code == 200:
                            tpl_data = tpl_resp.json()
                            if tpl_data.get('status') == 'success' and tpl_data.get('template'):
                                import base64
                                from datetime import datetime
                                template_bytes = base64.b64decode(tpl_data['template'])
                                student_row = db.execute(
                                    "SELECT class_id FROM students WHERE id = ?", (sid,)
                                ).fetchone()
                                cid = student_row['class_id'] if student_row else 0
                                db.execute(
                                    "INSERT OR REPLACE INTO fingerprint_templates "
                                    "(student_id, class_id, template_data, template_size, created_at) "
                                    "VALUES (?, ?, ?, ?, ?)",
                                    (sid, cid, template_bytes, len(template_bytes),
                                     datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                                )
                                db.commit()
                                print(f"[REG] Template saved: student {sid}, {len(template_bytes)} bytes")
                                
                                # Delete from sensor (it's now in the database)
                                esp32_request('/delete', params={'id': sid}, timeout=5)
                                print(f"[REG] Template deleted from sensor: student {sid}")
                    except Exception as e:
                        print(f"[REG] Template extraction warning: {e}")
                    
                    db.close()
                register_job['state'] = 'success'
                register_job['final_result'] = 'success'
                register_job['active'] = False
            else:
                esp_detail = str(esp32_state.get('detail', '')).strip()
                register_job['state'] = 'failed'
                register_job['final_result'] = 'failed'
                register_job['error'] = esp_detail or 'ESP32 reported failure'
                register_job['active'] = False

        return jsonify({
            'status': 'success',
            'job': dict(register_job),
            'esp32_state': esp32_state,
        })

    @app.route('/api/extract_templates', methods=['GET', 'POST'])
    def extract_templates():
        """Extract all registered templates from sensor and save to database."""
        import base64
        from datetime import datetime
        
        db = get_db()
        students = db.execute(
            "SELECT id, name, class_id FROM students WHERE registered = 1"
        ).fetchall()
        
        extracted = 0
        failed = 0
        for student in students:
            sid = student['id']
            # Check if already in database
            existing = db.execute(
                "SELECT student_id FROM fingerprint_templates WHERE student_id = ?", (sid,)
            ).fetchone()
            if existing:
                continue  # Already extracted
            
            # Try to extract from ESP32 sensor
            tpl_resp, _, _ = esp32_request('/get_template', params={'id': sid}, timeout=10)
            if tpl_resp and tpl_resp.status_code == 200:
                try:
                    tpl_data = tpl_resp.json()
                    if tpl_data.get('status') == 'success' and tpl_data.get('template'):
                        template_bytes = base64.b64decode(tpl_data['template'])
                        db.execute(
                            "INSERT OR REPLACE INTO fingerprint_templates "
                            "(student_id, class_id, template_data, template_size, created_at) "
                            "VALUES (?, ?, ?, ?, ?)",
                            (sid, student['class_id'], template_bytes, len(template_bytes),
                             datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                        )
                        extracted += 1
                        print(f"[EXTRACT] Saved template for {student['name']} (ID:{sid}), {len(template_bytes)} bytes")
                    else:
                        failed += 1
                except Exception as e:
                    failed += 1
                    print(f"[EXTRACT] Failed for ID {sid}: {e}")
            else:
                failed += 1
        
        db.commit()
        db.close()
        return jsonify({
            'status': 'success',
            'extracted': extracted,
            'failed': failed,
            'total_registered': len(students)
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
