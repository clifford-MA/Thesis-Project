import tkinter as tk
from tkinter import messagebox
import requests
import hashlib
from PIL import Image, ImageTk
import threading
import time
import os
import sqlite3
from datetime import datetime
from threading import Lock
from flask import Flask, request, jsonify
from flask_cors import CORS

# IMPORT SHARED CONFIG
from config import (
    IS_SERVER, SERVER_IP, SERVER_PORT,
    API_BASE_URL, SERVER_URL, REQUEST_TIMEOUT 
)

# FLASK SERVER SETUP
DB_PATH = "database/opd_queue.db"
db_lock = Lock()
app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def migrate_database():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(opd_services)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'is_active' not in columns:
            cursor.execute("ALTER TABLE opd_services ADD COLUMN is_active INTEGER DEFAULT 1")
            conn.commit()
        if 'operating_hours' not in columns:
            cursor.execute("ALTER TABLE opd_services ADD COLUMN operating_hours TEXT DEFAULT 'Mon-Fri, 8AM-5PM'")
            conn.commit()
        cursor.execute("PRAGMA table_info(tickets)")
        ticket_columns = [col[1] for col in cursor.fetchall()]
        if 'queue_type' not in ticket_columns:
            cursor.execute("ALTER TABLE tickets ADD COLUMN queue_type TEXT DEFAULT 'Regular'")
            conn.commit()
        if 'display_ticket_number' not in ticket_columns:
            cursor.execute("ALTER TABLE tickets ADD COLUMN display_ticket_number TEXT")
            conn.commit()
        conn.close()
    except Exception as e:
        print(f"[ERROR] Migration failed: {e}")


def init_db():
    if not os.path.exists("database"):
        os.makedirs("database")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT NOT NULL, specialization TEXT,
        username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS tickets (
        ticket_id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticket_number TEXT NOT NULL UNIQUE, patient_name TEXT,
        service_id INTEGER, status TEXT DEFAULT 'Waiting',
        stage INTEGER DEFAULT 1, queue_type TEXT DEFAULT 'Regular',
        display_ticket_number TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (service_id) REFERENCES opd_services(service_id))""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS opd_services (
        service_id INTEGER PRIMARY KEY AUTOINCREMENT,
        service_name TEXT NOT NULL, service_code TEXT NOT NULL UNIQUE,
        color TEXT DEFAULT '#1E88E5', is_active INTEGER DEFAULT 1)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS activity_log (
        log_id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticket_number TEXT NOT NULL, service_name TEXT,
        status TEXT, action TEXT, date TEXT, time TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS announcements (
        announcement_id INTEGER PRIMARY KEY AUTOINCREMENT,
        message TEXT NOT NULL, created_at DATETIME NOT NULL,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")
    cursor.execute("SELECT COUNT(*) FROM announcements")
    if cursor.fetchone()[0] == 0:
        cursor.execute(
            "INSERT INTO announcements (message, created_at) VALUES (?, datetime('now'))",
            ('Welcome to ISMC OPD. Please wait for your ticket number to be called.',)
        )
    conn.commit()
    conn.close()
    migrate_database()

# FLASK ROUTES

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({'success': True, 'message': 'Server is running',
                    'timestamp': datetime.now().isoformat()})

@app.route('/api/auth/login', methods=['POST'])
def login_api():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return jsonify({'success': False, 'message': 'Username and password required'}), 400
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT user_id, full_name, specialization FROM users WHERE username=? AND password_hash=?",
            (username, hash_password(password))
        )
        user = cursor.fetchone()
        conn.close()
    if user:
        return jsonify({'success': True, 'user_id': user[0], 'full_name': user[1], 'specialization': user[2]})
    return jsonify({'success': False, 'message': 'Invalid credentials'}), 401

@app.route('/api/auth/register', methods=['POST'])
def register_api():
    data = request.json
    full_name = data.get('full_name')
    specialization = data.get('specialization')
    username = data.get('username')
    password = data.get('password')
    if not full_name or not username or not password:
        return jsonify({'success': False, 'message': 'Required fields missing'}), 400
    if len(password) < 6:
        return jsonify({'success': False, 'message': 'Password must be at least 6 characters'}), 400
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username=?", (username,))
        if cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'message': 'Username already exists'}), 409
        cursor.execute(
            "INSERT INTO users (full_name, specialization, username, password_hash) VALUES (?, ?, ?, ?)",
            (full_name, specialization, username, hash_password(password))
        )
        conn.commit()
        user_id = cursor.lastrowid
        conn.close()
    return jsonify({'success': True, 'user_id': user_id, 'message': 'Registration successful'})


@app.route('/api/tickets/create', methods=['POST'])
def create_ticket():
    data             = request.json
    patient_name     = data.get('patient_name', 'Walk-in Patient')
    queue_type       = data.get('queue_type', 'Regular')
    requested_number = data.get('requested_number')
    force_number     = data.get('force_number', False)

    with db_lock:
        conn   = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        today  = datetime.now().strftime("%Y-%m-%d")

        if queue_type == "Priority":
            prefix = "P"
        elif queue_type == "Special Lane":
            prefix = "SL"
        elif queue_type == "ABTC":
            prefix = "AB"
        else:
            prefix = "R"

        if force_number and requested_number and isinstance(requested_number, int):
            next_num = requested_number
            display_candidate  = f"{prefix}{next_num:03d}"
            suffix = 1
            while True:
                if suffix == 1:
                    internal_candidate = f"{today}-{display_candidate}"
                else:
                    internal_candidate = f"{today}-{display_candidate}-{suffix}"
                cursor.execute(
                    "SELECT ticket_id FROM tickets WHERE ticket_number = ?",
                    (internal_candidate,)
                )
                if not cursor.fetchone():
                    break
                suffix += 1
        else:
            cursor.execute(
                """SELECT display_ticket_number FROM tickets
                   WHERE queue_type = ? AND DATE(created_at) = ?
                   AND display_ticket_number LIKE ? AND display_ticket_number NOT LIKE '%-%'""",
                (queue_type, today, prefix + '%')
            )
            rows    = cursor.fetchall()
            max_num = 0
            for (dtn,) in rows:
                try:
                    val = int(dtn[len(prefix):])
                    if val > max_num:
                        max_num = val
                except (ValueError, IndexError):
                    pass

            db_next = max_num + 1

            if requested_number and isinstance(requested_number, int) and requested_number >= db_next:
                next_num = requested_number
            else:
                next_num = db_next

            display_candidate  = f"{prefix}{next_num:03d}"
            internal_candidate = f"{today}-{display_candidate}"

            suffix = 1
            while True:
                cursor.execute(
                    "SELECT ticket_id FROM tickets WHERE ticket_number = ?",
                    (internal_candidate,)
                )
                if not cursor.fetchone():
                    break
                suffix   += 1
                next_num += 1
                display_candidate  = f"{prefix}{next_num:03d}"
                internal_candidate = f"{today}-{display_candidate}"

        try:
            cursor.execute(
                "INSERT INTO tickets "
                "(ticket_number, patient_name, queue_type, status, stage, display_ticket_number) "
                "VALUES (?, ?, ?, 'Waiting', 1, ?)",
                (internal_candidate, patient_name, queue_type, display_candidate)
            )
            ticket_id = cursor.lastrowid
        except sqlite3.IntegrityError:
            conn.close()
            return jsonify({
                'success': False,
                'message': 'Could not assign a unique ticket number. Please try again.'
            }), 500

        cursor.execute(
            "INSERT INTO activity_log (ticket_number, service_name, status, action, date, time) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (display_candidate, 'Triage', 'Created', 'Ticket Created',
             datetime.now().strftime("%b %d, %Y"), datetime.now().strftime("%H:%M:%S"))
        )
        conn.commit()
        conn.close()

    return jsonify({
        'success':        True,
        'ticket_id':      ticket_id,
        'ticket_number':  display_candidate
    })


@app.route('/api/tickets/list', methods=['GET'])
def get_tickets():
    stage = request.args.get('stage', type=int)
    status = request.args.get('status')
    today_only = request.args.get('today_only', 'false').lower() == 'true'
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        query = """SELECT t.ticket_id, t.ticket_number, t.patient_name,
                   COALESCE(t.queue_type,'Regular'), t.service_id, s.service_name,
                   s.service_code, t.status, t.stage, t.created_at, t.updated_at,
                   COALESCE(t.display_ticket_number, t.ticket_number)
                   FROM tickets t LEFT JOIN opd_services s ON t.service_id = s.service_id WHERE 1=1"""
        params = []
        if stage:
            query += " AND t.stage = ?"
            params.append(stage)
        if status:
            query += " AND t.status = ?"
            params.append(status)
        if today_only:
            query += " AND DATE(t.created_at) = DATE('now')"
        query += " ORDER BY t.created_at ASC"
        cursor.execute(query, params)
        tickets = cursor.fetchall()
        conn.close()
    return jsonify({'success': True, 'tickets': [
        {'ticket_id': t[0], 'ticket_number': t[1], 'patient_name': t[2], 'queue_type': t[3],
         'service_id': t[4], 'service_name': t[5], 'service_code': t[6], 'status': t[7],
         'stage': t[8], 'created_at': t[9], 'updated_at': t[10], 'display_ticket_number': t[11]}
        for t in tickets]})


@app.route('/api/tickets/<int:ticket_id>/update', methods=['PUT'])
def update_ticket(ticket_id):
    data       = request.json
    stage      = data.get('stage')
    status     = data.get('status')
    service_id = data.get('service_id')

    with db_lock:
        conn   = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        if stage == 3 and status == 'Ready for Service':
            cursor.execute(
                "SELECT display_ticket_number FROM tickets WHERE ticket_id = ?",
                (ticket_id,)
            )
            row = cursor.fetchone()
            if row and row[0]:
                dtn   = row[0]
                parts = dtn.split("-")
                if len(parts) > 1 and parts[-1] and parts[-1][0] in ("R", "P", "S"):
                    clean_dtn = parts[-1]
                else:
                    clean_dtn = dtn
                cursor.execute(
                    "UPDATE tickets SET display_ticket_number=?, service_id=NULL, "
                    "stage=3, status='Ready for Service', updated_at=datetime('now') "
                    "WHERE ticket_id=?",
                    (clean_dtn, ticket_id)
                )
                cursor.execute(
                    "SELECT display_ticket_number FROM tickets WHERE ticket_id=?",
                    (ticket_id,)
                )
                final_row = cursor.fetchone()
                display_num = final_row[0] if final_row else clean_dtn
                cursor.execute(
                    "INSERT INTO activity_log "
                    "(ticket_number, service_name, status, action, date, time) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (display_num, 'System', 'Ready for Service', 'Re-queued (Redo)',
                     datetime.now().strftime("%b %d, %Y"),
                     datetime.now().strftime("%H:%M:%S"))
                )
                conn.commit()
                conn.close()
                return jsonify({'success': True, 'message': 'Ticket re-queued successfully'})

        update_fields = []
        params        = []
        if stage is not None:
            update_fields.append("stage = ?");     params.append(stage)
        if status:
            update_fields.append("status = ?");    params.append(status)
        if service_id is not None:
            update_fields.append("service_id = ?"); params.append(service_id)
        update_fields.append("updated_at = datetime('now')")
        cursor.execute(
            f"UPDATE tickets SET {', '.join(update_fields)} WHERE ticket_id = ?",
            params + [ticket_id]
        )
        cursor.execute(
            "SELECT display_ticket_number, ticket_number FROM tickets WHERE ticket_id = ?",
            (ticket_id,)
        )
        row = cursor.fetchone()
        display_num = row[0] if row and row[0] else (row[1] if row else str(ticket_id))
        cursor.execute(
            "INSERT INTO activity_log "
            "(ticket_number, service_name, status, action, date, time) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (display_num, 'System', status or 'Updated',
             f"Updated to stage {stage}" if stage else "Status updated",
             datetime.now().strftime("%b %d, %Y"), datetime.now().strftime("%H:%M:%S"))
        )
        conn.commit()
        conn.close()
    return jsonify({'success': True, 'message': 'Ticket updated successfully'})


@app.route('/api/tickets/<ticket_number>/move-to-admitting', methods=['POST'])
def move_to_admitting(ticket_number):
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE tickets SET stage=2, status='In Admitting', updated_at=datetime('now') "
            "WHERE display_ticket_number=? OR ticket_number=?",
            (ticket_number, ticket_number)
        )
        cursor.execute(
            "INSERT INTO activity_log (ticket_number, service_name, status, action, date, time) VALUES (?, ?, ?, ?, ?, ?)",
            (ticket_number, 'Admitting', 'In Admitting', 'Moved to Admitting',
             datetime.now().strftime("%b %d, %Y"), datetime.now().strftime("%H:%M:%S"))
        )
        conn.commit()
        conn.close()
    return jsonify({'success': True})

@app.route('/api/tickets/<ticket_number>/move-to-queue', methods=['POST'])
def move_to_queue(ticket_number):
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE tickets SET stage=3, status='Ready for Service', updated_at=datetime('now') "
            "WHERE display_ticket_number=? OR ticket_number=?",
            (ticket_number, ticket_number)
        )
        cursor.execute(
            "INSERT INTO activity_log (ticket_number, service_name, status, action, date, time) VALUES (?, ?, ?, ?, ?, ?)",
            (ticket_number, 'Queue Console', 'Ready for Service', 'Moved to Queue Console',
             datetime.now().strftime("%b %d, %Y"), datetime.now().strftime("%H:%M:%S"))
        )
        conn.commit()
        conn.close()
    return jsonify({'success': True})

@app.route('/api/tickets/<ticket_number>/assign-service', methods=['POST'])
def assign_service(ticket_number):
    data = request.json
    service_id = data.get('service_id')
    if not service_id:
        return jsonify({'success': False, 'message': 'Service ID required'}), 400
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT service_code, service_name FROM opd_services WHERE service_id = ?", (service_id,))
        service = cursor.fetchone()
        if not service:
            conn.close()
            return jsonify({'success': False, 'message': 'Service not found'}), 404
        service_code, service_name = service
        display_ticket_number = f"{service_code}-{ticket_number}"
        cursor.execute(
            "UPDATE tickets SET service_id=?, status='Waiting', display_ticket_number=?, updated_at=datetime('now') "
            "WHERE display_ticket_number=? OR ticket_number=?",
            (service_id, display_ticket_number, ticket_number, ticket_number)
        )
        cursor.execute(
            "INSERT INTO activity_log (ticket_number, service_name, status, action, date, time) VALUES (?, ?, ?, ?, ?, ?)",
            (display_ticket_number, service_name, 'Waiting', f'Service Assigned: {service_name}',
             datetime.now().strftime("%b %d, %Y"), datetime.now().strftime("%H:%M:%S"))
        )
        conn.commit()
        conn.close()
    return jsonify({'success': True, 'display_ticket_number': display_ticket_number})

@app.route('/api/services/list', methods=['GET'])
def get_services():
    active_only = request.args.get('active_only', 'false').lower() == 'true'
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(opd_services)")
        columns = [col[1] for col in cursor.fetchall()]
        has_hours = 'operating_hours' in columns
        query = (
            "SELECT service_id, service_name, service_code, COALESCE(color,'#1E88E5'), COALESCE(is_active,1)"
            + (", COALESCE(operating_hours,'Mon-Fri, 8AM-5PM')" if has_hours else "")
            + " FROM opd_services"
        )
        if active_only:
            query += " WHERE COALESCE(is_active,1)=1"
        query += " ORDER BY service_name ASC"
        cursor.execute(query)
        services = cursor.fetchall()
        conn.close()
    result = []
    for s in services:
        d = {'service_id': s[0], 'service_name': s[1], 'service_code': s[2],
             'color': s[3], 'is_active': s[4]}
        d['operating_hours'] = s[5] if has_hours and len(s) > 5 else 'Mon-Fri, 8AM-5PM'
        result.append(d)
    return jsonify({'success': True, 'services': result})

@app.route('/api/services/create', methods=['POST'])
def create_service():
    data = request.json
    service_name = data.get('service_name')
    service_code = data.get('service_code')
    color = data.get('color', '#1E88E5')
    operating_hours = data.get('operating_hours', 'Mon-Fri, 8AM-5PM')
    if not service_name or not service_code:
        return jsonify({'success': False, 'message': 'Service name and code required'}), 400
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(opd_services)")
        columns = [col[1] for col in cursor.fetchall()]
        has_hours = 'operating_hours' in columns
        try:
            if has_hours:
                cursor.execute(
                    "INSERT INTO opd_services (service_name, service_code, color, is_active, operating_hours) VALUES (?, ?, ?, 1, ?)",
                    (service_name, service_code.upper(), color, operating_hours)
                )
            else:
                cursor.execute(
                    "INSERT INTO opd_services (service_name, service_code, color, is_active) VALUES (?, ?, ?, 1)",
                    (service_name, service_code.upper(), color)
                )
            conn.commit()
            service_id = cursor.lastrowid
            conn.close()
            return jsonify({'success': True, 'service_id': service_id})
        except sqlite3.IntegrityError:
            conn.close()
            return jsonify({'success': False, 'message': 'Service code already exists'}), 409

@app.route('/api/services/<int:service_id>/toggle', methods=['PUT'])
def toggle_service(service_id):
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT is_active FROM opd_services WHERE service_id = ?", (service_id,))
        result = cursor.fetchone()
        if not result:
            conn.close()
            return jsonify({'success': False, 'message': 'Service not found'}), 404
        new_status = 0 if result[0] == 1 else 1
        cursor.execute("UPDATE opd_services SET is_active = ? WHERE service_id = ?", (new_status, service_id))
        conn.commit()
        conn.close()
    return jsonify({'success': True, 'is_active': new_status})

@app.route('/api/services/<int:service_id>/update', methods=['PUT'])
def update_service(service_id):
    data            = request.json
    service_name    = data.get('service_name')
    new_code        = data.get('service_code')
    color           = data.get('color')
    operating_hours = data.get('operating_hours')

    if not service_name:
        return jsonify({'success': False, 'message': 'service_name is required'}), 400

    with db_lock:
        conn   = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("SELECT service_code FROM opd_services WHERE service_id = ?", (service_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return jsonify({'success': False, 'message': 'Service not found'}), 404

        old_code   = row[0]
        final_code = new_code.upper() if new_code else old_code

        if final_code != old_code:
            cursor.execute(
                "SELECT service_id FROM opd_services WHERE service_code = ? AND service_id != ?",
                (final_code, service_id)
            )
            if cursor.fetchone():
                conn.close()
                return jsonify({'success': False,
                                'message': 'That service code is already used by another service'}), 409

        cursor.execute("PRAGMA table_info(opd_services)")
        columns   = [col[1] for col in cursor.fetchall()]
        has_hours = 'operating_hours' in columns

        if has_hours:
            cursor.execute(
                "UPDATE opd_services SET service_name=?, service_code=?, color=?, "
                "operating_hours=? WHERE service_id=?",
                (service_name, final_code, color, operating_hours, service_id)
            )
        else:
            cursor.execute(
                "UPDATE opd_services SET service_name=?, service_code=?, color=? "
                "WHERE service_id=?",
                (service_name, final_code, color, service_id)
            )

        tickets_updated = 0
        if final_code != old_code:
            cursor.execute(
                "SELECT ticket_id, display_ticket_number FROM tickets "
                "WHERE service_id = ? AND display_ticket_number IS NOT NULL",
                (service_id,)
            )
            for ticket_id, dtn in cursor.fetchall():
                if dtn and dtn.startswith(old_code + "-"):
                    new_dtn = final_code + "-" + dtn[len(old_code) + 1:]
                    cursor.execute(
                        "UPDATE tickets SET display_ticket_number=? WHERE ticket_id=?",
                        (new_dtn, ticket_id)
                    )
                    tickets_updated += 1

        conn.commit()
        conn.close()

    return jsonify({
        'success':         True,
        'message':         'Service updated successfully',
        'tickets_updated': tickets_updated
    })

@app.route('/api/services/<int:service_id>/delete', methods=['DELETE'])
def delete_service_permanently(service_id):
    with db_lock:
        conn   = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT service_name FROM opd_services WHERE service_id = ?", (service_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return jsonify({'success': False, 'message': 'Service not found'}), 404
        service_name = row[0]
        cursor.execute("UPDATE tickets SET service_id = NULL WHERE service_id = ?", (service_id,))
        cursor.execute("DELETE FROM opd_services WHERE service_id = ?", (service_id,))
        conn.commit()
        conn.close()
    return jsonify({'success': True, 'message': f'"{service_name}" has been permanently deleted.'})

@app.route('/api/announcements/current', methods=['GET'])
def get_current_announcement():
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT message, created_at FROM announcements ORDER BY created_at DESC LIMIT 1")
        announcement = cursor.fetchone()
        conn.close()
    if announcement:
        return jsonify({'success': True, 'message': announcement[0], 'created_at': announcement[1]})
    return jsonify({'success': True, 'message': '', 'created_at': None})

@app.route('/api/announcements/update', methods=['POST'])
def update_announcement():
    data = request.json
    message = data.get('message')
    if not message:
        return jsonify({'success': False, 'message': 'Message required'}), 400
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM announcements")
        cursor.execute("INSERT INTO announcements (message, created_at) VALUES (?, datetime('now'))", (message,))
        conn.commit()
        conn.close()
    return jsonify({'success': True})

@app.route('/api/stats/today', methods=['GET'])
def get_today_stats():
    with db_lock:
        conn   = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        today  = datetime.now().strftime("%Y-%m-%d")

        cursor.execute(
            "SELECT COUNT(*) FROM tickets WHERE DATE(created_at)=?", (today,)
        )
        total = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM tickets WHERE status='Served' AND DATE(created_at)=?", (today,)
        )
        served = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM tickets "
            "WHERE status IN ('Waiting', 'Ready for Service') AND DATE(created_at)=?",
            (today,)
        )
        raw_waiting = cursor.fetchone()[0]

        stage1_currents = 0
        for qt in ('Regular', 'Priority', 'Special Lane', 'ABTC'):
            cursor.execute(
                "SELECT COUNT(*) FROM tickets "
                "WHERE stage=1 AND status='Waiting' AND queue_type=? AND DATE(created_at)=?",
                (qt, today)
            )
            if cursor.fetchone()[0] > 0:
                stage1_currents += 1

        waiting = max(0, raw_waiting - stage1_currents)

        cursor.execute(
            "SELECT COUNT(*) FROM tickets WHERE status='Skipped' AND DATE(created_at)=?", (today,)
        )
        skipped = cursor.fetchone()[0]

        conn.close()

    return jsonify({
        'success': True,
        'total':   total,
        'served':  served,
        'waiting': waiting,
        'skipped': skipped
    })


@app.route('/api/activity/list', methods=['GET'])
def get_activity_log():
    date = request.args.get('date')
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        if date:
            cursor.execute(
                "SELECT ticket_number, service_name, status, action, date, time FROM activity_log WHERE date=? ORDER BY log_id DESC LIMIT 100",
                (date,)
            )
        else:
            cursor.execute(
                "SELECT ticket_number, service_name, status, action, date, time FROM activity_log ORDER BY log_id DESC LIMIT 100"
            )
        logs = cursor.fetchall()
        conn.close()
    return jsonify({'success': True, 'logs': [
        {'ticket_number': l[0], 'service_name': l[1], 'status': l[2],
         'action': l[3], 'date': l[4], 'time': l[5]}
        for l in logs]})

@app.route('/api/queue/service-stats-all', methods=['GET'])
def get_all_service_stats():
    today = datetime.now().strftime("%Y-%m-%d")
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT s.service_code
            FROM tickets t
            JOIN opd_services s ON t.service_id = s.service_id
            WHERE t.status = 'Serving' AND DATE(t.created_at) = ?
        """, (today,))
        serving_codes = [row[0] for row in cursor.fetchall()]
        conn.close()
    return jsonify({'success': True, 'serving_codes': serving_codes})

@app.route('/api/queue/service-stats', methods=['GET'])
def get_service_stats():
    service_code = request.args.get('service_code')
    if not service_code:
        return jsonify({'success': False, 'message': 'service_code required'}), 400
    today = datetime.now().strftime("%Y-%m-%d")
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT service_id FROM opd_services WHERE service_code=?", (service_code,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return jsonify({'success': False, 'message': 'Service not found'}), 404
        service_id = row[0]
        cursor.execute(
            "SELECT COALESCE(display_ticket_number,ticket_number) FROM tickets WHERE service_id=? AND status='Serving' AND DATE(created_at)=? ORDER BY created_at ASC LIMIT 1",
            (service_id, today)
        )
        serving = cursor.fetchone()
        cursor.execute(
            "SELECT COUNT(*) FROM tickets WHERE service_id=? AND status='Waiting' AND DATE(created_at)=?",
            (service_id, today)
        )
        waiting = cursor.fetchone()[0]
        cursor.execute(
            "SELECT COUNT(*) FROM tickets WHERE service_id=? AND status='Served' AND DATE(created_at)=?",
            (service_id, today)
        )
        served = cursor.fetchone()[0]
        cursor.execute(
            "SELECT COUNT(*) FROM tickets WHERE service_id=? AND status='Serving' AND DATE(created_at)=?",
            (service_id, today)
        )
        serving_count = cursor.fetchone()[0]
        conn.close()
    return jsonify({
        'success': True,
        'serving': serving[0] if serving else None,
        'serving_count': serving_count,
        'waiting': waiting,
        'served': served
    })

@app.route('/api/queue/mark-served', methods=['POST'])
def api_mark_served():
    data = request.json
    service_code = data.get('service_code')
    today = datetime.now().strftime("%Y-%m-%d")
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT service_id, service_name FROM opd_services WHERE service_code=?", (service_code,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return jsonify({'success': False, 'message': 'Service not found'}), 404
        service_id, service_name = row
        cursor.execute(
            "SELECT ticket_id, COALESCE(display_ticket_number,ticket_number) FROM tickets WHERE service_id=? AND status IN ('Serving','Waiting') AND DATE(created_at)=? ORDER BY CASE status WHEN 'Serving' THEN 1 WHEN 'Waiting' THEN 2 END, created_at ASC LIMIT 1",
            (service_id, today)
        )
        current = cursor.fetchone()
        if not current:
            conn.close()
            return jsonify({'success': False, 'message': 'No ticket to mark'}), 404
        current_ticket_id, display_ticket = current
        cursor.execute("UPDATE tickets SET status='Served' WHERE ticket_id=?", (current_ticket_id,))
        cursor.execute(
            "SELECT ticket_id FROM tickets WHERE service_id=? AND status='Waiting' AND DATE(created_at)=? ORDER BY created_at ASC LIMIT 1",
            (service_id, today)
        )
        next_ticket = cursor.fetchone()
        if next_ticket:
            cursor.execute("UPDATE tickets SET status='Serving' WHERE ticket_id=?", (next_ticket[0],))
        now = datetime.now()
        cursor.execute(
            "INSERT INTO activity_log (ticket_number, service_name, status, action, date, time) VALUES (?,?,?,?,?,?)",
            (display_ticket, service_name, 'Served', 'Mark Served',
             now.strftime("%b %d, %Y"), now.strftime("%H:%M:%S"))
        )
        conn.commit()
        conn.close()
    return jsonify({'success': True, 'served_ticket': display_ticket})

@app.route('/api/queue/skip-ticket', methods=['POST'])
def api_skip_ticket():
    data = request.json
    service_code = data.get('service_code')
    today = datetime.now().strftime("%Y-%m-%d")
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT service_id, service_name FROM opd_services WHERE service_code=?", (service_code,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return jsonify({'success': False, 'message': 'Service not found'}), 404
        service_id, service_name = row
        cursor.execute(
            "SELECT ticket_id, COALESCE(display_ticket_number,ticket_number) FROM tickets WHERE service_id=? AND status IN ('Serving','Waiting') AND DATE(created_at)=? ORDER BY CASE status WHEN 'Serving' THEN 1 WHEN 'Waiting' THEN 2 END, created_at ASC LIMIT 1",
            (service_id, today)
        )
        current = cursor.fetchone()
        if not current:
            conn.close()
            return jsonify({'success': False, 'message': 'No ticket to skip'}), 404
        current_ticket_id, display_ticket = current
        cursor.execute("UPDATE tickets SET status='Skipped' WHERE ticket_id=?", (current_ticket_id,))
        cursor.execute(
            "SELECT ticket_id FROM tickets WHERE service_id=? AND status='Waiting' AND DATE(created_at)=? ORDER BY created_at ASC LIMIT 1",
            (service_id, today)
        )
        next_ticket = cursor.fetchone()
        if next_ticket:
            cursor.execute("UPDATE tickets SET status='Serving' WHERE ticket_id=?", (next_ticket[0],))
        now = datetime.now()
        cursor.execute(
            "INSERT INTO activity_log (ticket_number, service_name, status, action, date, time) VALUES (?,?,?,?,?,?)",
            (display_ticket, service_name, 'Skipped', 'Skip',
             now.strftime("%b %d, %Y"), now.strftime("%H:%M:%S"))
        )
        conn.commit()
        conn.close()
    return jsonify({'success': True, 'skipped_ticket': display_ticket})


@app.route('/api/queue/mark-served-ticket', methods=['POST'])
def api_mark_served_ticket():
    data          = request.json
    ticket_number = data.get('ticket_number')
    service_code  = data.get('service_code')
    today         = datetime.now().strftime("%Y-%m-%d")

    if not ticket_number or not service_code:
        return jsonify({'success': False, 'message': 'ticket_number and service_code required'}), 400

    with db_lock:
        conn   = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT service_id, service_name FROM opd_services WHERE service_code=?",
            (service_code,)
        )
        row = cursor.fetchone()
        if not row:
            conn.close()
            return jsonify({'success': False, 'message': 'Service not found'}), 404
        service_id, service_name = row

        cursor.execute(
            """SELECT ticket_id, status
               FROM tickets
               WHERE (display_ticket_number=? OR ticket_number=?)
                 AND service_id=?
                 AND DATE(created_at)=?
               LIMIT 1""",
            (ticket_number, ticket_number, service_id, today)
        )
        ticket_row = cursor.fetchone()
        if not ticket_row:
            conn.close()
            return jsonify({'success': False, 'message': 'Ticket not found in this service queue'}), 404

        target_ticket_id, current_status = ticket_row

        if current_status not in ('Serving', 'Waiting'):
            conn.close()
            return jsonify({'success': False, 'message': f'Ticket is already {current_status}'}), 400

        cursor.execute(
            "UPDATE tickets SET status='Served', updated_at=datetime('now') WHERE ticket_id=?",
            (target_ticket_id,)
        )

        if current_status == 'Serving':
            cursor.execute(
                """SELECT ticket_id FROM tickets
                   WHERE service_id=? AND status='Waiting' AND DATE(created_at)=?
                   ORDER BY created_at ASC LIMIT 1""",
                (service_id, today)
            )
            next_ticket = cursor.fetchone()
            if next_ticket:
                cursor.execute(
                    "UPDATE tickets SET status='Serving' WHERE ticket_id=?",
                    (next_ticket[0],)
                )

        now = datetime.now()
        cursor.execute(
            "INSERT INTO activity_log (ticket_number, service_name, status, action, date, time) "
            "VALUES (?,?,?,?,?,?)",
            (ticket_number, service_name, 'Served', 'Mark Served (Focused)',
             now.strftime("%b %d, %Y"), now.strftime("%H:%M:%S"))
        )
        conn.commit()
        conn.close()

    return jsonify({'success': True, 'served_ticket': ticket_number})


@app.route('/api/queue/skip-ticket-specific', methods=['POST'])
def api_skip_ticket_specific():
    data          = request.json
    ticket_number = data.get('ticket_number')
    service_code  = data.get('service_code')
    today         = datetime.now().strftime("%Y-%m-%d")

    if not ticket_number or not service_code:
        return jsonify({'success': False, 'message': 'ticket_number and service_code required'}), 400

    with db_lock:
        conn   = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT service_id, service_name FROM opd_services WHERE service_code=?",
            (service_code,)
        )
        row = cursor.fetchone()
        if not row:
            conn.close()
            return jsonify({'success': False, 'message': 'Service not found'}), 404
        service_id, service_name = row

        cursor.execute(
            """SELECT ticket_id, status
               FROM tickets
               WHERE (display_ticket_number=? OR ticket_number=?)
                 AND service_id=?
                 AND DATE(created_at)=?
               LIMIT 1""",
            (ticket_number, ticket_number, service_id, today)
        )
        ticket_row = cursor.fetchone()
        if not ticket_row:
            conn.close()
            return jsonify({'success': False, 'message': 'Ticket not found in this service queue'}), 404

        target_ticket_id, current_status = ticket_row

        if current_status not in ('Serving', 'Waiting'):
            conn.close()
            return jsonify({'success': False, 'message': f'Ticket is already {current_status}'}), 400

        cursor.execute(
            "UPDATE tickets SET status='Skipped', updated_at=datetime('now') WHERE ticket_id=?",
            (target_ticket_id,)
        )

        if current_status == 'Serving':
            cursor.execute(
                """SELECT ticket_id FROM tickets
                   WHERE service_id=? AND status='Waiting' AND DATE(created_at)=?
                   ORDER BY created_at ASC LIMIT 1""",
                (service_id, today)
            )
            next_ticket = cursor.fetchone()
            if next_ticket:
                cursor.execute(
                    "UPDATE tickets SET status='Serving' WHERE ticket_id=?",
                    (next_ticket[0],)
                )

        now = datetime.now()
        cursor.execute(
            "INSERT INTO activity_log (ticket_number, service_name, status, action, date, time) "
            "VALUES (?,?,?,?,?,?)",
            (ticket_number, service_name, 'Skipped', 'Skip (Focused)',
             now.strftime("%b %d, %Y"), now.strftime("%H:%M:%S"))
        )
        conn.commit()
        conn.close()

    return jsonify({'success': True, 'skipped_ticket': ticket_number})


@app.route('/api/queue/distribute', methods=['POST'])
def api_distribute_ticket():
    data = request.json
    ticket_number = data.get('ticket_number')
    service_codes = data.get('service_codes', [])
    today = datetime.now().strftime("%Y-%m-%d")
    if not ticket_number or not service_codes:
        return jsonify({'success': False, 'message': 'ticket_number and service_codes required'}), 400
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT patient_name, queue_type FROM tickets WHERE display_ticket_number=? AND DATE(created_at)=?",
            (ticket_number, today)
        )
        ticket_data = cursor.fetchone()
        if not ticket_data:
            cursor.execute(
                "SELECT patient_name, queue_type FROM tickets WHERE ticket_number=?",
                (ticket_number,)
            )
            ticket_data = cursor.fetchone()
        if not ticket_data:
            conn.close()
            return jsonify({'success': False, 'message': 'Ticket not found'}), 404
        patient_name, queue_type = ticket_data
        distributed = []
        for service_code in service_codes:
            cursor.execute(
                "SELECT service_id, service_name FROM opd_services WHERE service_code=?",
                (service_code,)
            )
            srv = cursor.fetchone()
            if not srv:
                continue
            service_id, service_name = srv
            display_ticket = f"{service_code}-{ticket_number}"
            cursor.execute(
                "SELECT ticket_id FROM tickets WHERE display_ticket_number=? AND DATE(created_at)=?",
                (display_ticket, today)
            )
            if cursor.fetchone():
                continue

            cursor.execute(
                "SELECT COUNT(*) FROM tickets "
                "WHERE service_id=? AND status IN ('Serving','Waiting') "
                "AND DATE(created_at)=?",
                (service_id, today)
            )
            existing = cursor.fetchone()[0]
            ticket_status = 'Serving' if existing == 0 else 'Waiting'

            internal_key = f"{today}-{display_ticket}"
            try:
                cursor.execute(
                    "INSERT INTO tickets (ticket_number, patient_name, queue_type, service_id, status, stage, display_ticket_number, created_at) VALUES (?,?,?,?,?,3,?,?)",
                    (internal_key, patient_name, queue_type, service_id, ticket_status, display_ticket, datetime.now())
                )
            except sqlite3.IntegrityError:
                continue
            now = datetime.now()
            cursor.execute(
                "INSERT INTO activity_log (ticket_number, service_name, status, action, date, time) VALUES (?,?,?,?,?,?)",
                (display_ticket, service_name, 'Assigned to Service', 'Distribute',
                 now.strftime("%b %d, %Y"), now.strftime("%H:%M:%S"))
            )
            distributed.append(display_ticket)
        cursor.execute(
            "UPDATE tickets SET status='Distributed' WHERE display_ticket_number=? AND DATE(created_at)=? AND stage=3 AND status='Ready for Service'",
            (ticket_number, today)
        )
        conn.commit()
        conn.close()
    return jsonify({'success': True, 'distributed': distributed})


@app.route('/api/queue/deploy-order', methods=['GET'])
def get_deploy_order():
    today = datetime.now().strftime("%Y-%m-%d")
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                COALESCE(t.display_ticket_number, t.ticket_number) AS display_num,
                s.service_name,
                t.status,
                t.created_at
            FROM tickets t
            JOIN opd_services s ON t.service_id = s.service_id
            WHERE t.status IN ('Serving', 'Waiting')
              AND t.stage = 3
              AND DATE(t.created_at) = ?
            ORDER BY t.created_at ASC
        """, (today,))
        rows = cursor.fetchall()
        conn.close()
    return jsonify({'success': True, 'queue': [
        {'ticket_number': r[0], 'service_name': r[1],
         'status': r[2], 'deployed_at': r[3]}
        for r in rows
    ]})


@app.route('/api/display/admitting', methods=['GET'])
def get_display_admitting():
    with db_lock:
        conn   = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        today  = datetime.now().strftime("%Y-%m-%d")
        result = {}
        for queue_type in ['Regular', 'Priority', 'Special Lane', 'ABTC']:
            cursor.execute(
                "SELECT COALESCE(display_ticket_number, ticket_number) FROM tickets "
                "WHERE stage=1 AND status='Waiting' AND queue_type=? "
                "AND DATE(created_at)=? "
                "ORDER BY created_at ASC LIMIT 1",
                (queue_type, today)
            )
            row = cursor.fetchone()

            cursor.execute(
                "SELECT COUNT(*) FROM tickets "
                "WHERE stage=1 AND status='Waiting' AND queue_type=? "
                "AND DATE(created_at)=?",
                (queue_type, today)
            )
            total_waiting = cursor.fetchone()[0]

            displayed_waiting = max(0, total_waiting - (1 if row else 0))

            cursor.execute(
                "SELECT COALESCE(display_ticket_number, ticket_number) FROM tickets "
                "WHERE stage=1 AND status='Waiting' AND queue_type=? "
                "AND DATE(created_at)=? "
                "ORDER BY created_at ASC LIMIT 6",
                (queue_type, today)
            )
            all_waiting  = [r[0] for r in cursor.fetchall()]
            next_tickets = all_waiting[1:] if len(all_waiting) > 1 else []

            result[queue_type] = {
                'current':      row[0] if row else None,
                'waiting':      displayed_waiting,
                'next_tickets': next_tickets,
            }
        conn.close()
    return jsonify({'success': True, 'admitting': result})


@app.route('/api/display/services', methods=['GET'])
def get_display_services():
    today = datetime.now().strftime("%Y-%m-%d")
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT service_id, service_name, service_code, color "
            "FROM opd_services WHERE is_active=1 ORDER BY service_id ASC"
        )
        all_services = cursor.fetchall()

        result = []
        for sid, name, code, color in all_services:
            cursor.execute(
                """SELECT MIN(created_at) FROM tickets
                   WHERE service_id=? AND status IN ('Serving','Waiting')
                   AND DATE(created_at)=?""",
                (sid, today)
            )
            min_row = cursor.fetchone()
            earliest_deploy = min_row[0] if min_row and min_row[0] else None

            cursor.execute(
                "SELECT COALESCE(display_ticket_number, ticket_number) FROM tickets "
                "WHERE service_id=? AND status='Serving' AND DATE(created_at)=? "
                "ORDER BY created_at ASC LIMIT 1",
                (sid, today)
            )
            serving = cursor.fetchone()

            cursor.execute(
                "SELECT COUNT(*) FROM tickets "
                "WHERE service_id=? AND status='Waiting' AND DATE(created_at)=?",
                (sid, today)
            )
            waiting = cursor.fetchone()[0]

            cursor.execute(
                "SELECT COUNT(*) FROM tickets "
                "WHERE service_id=? AND status='Serving' AND DATE(created_at)=?",
                (sid, today)
            )
            serving_count = cursor.fetchone()[0]

            cursor.execute(
                "SELECT COALESCE(display_ticket_number, ticket_number) FROM tickets "
                "WHERE service_id=? AND status='Waiting' AND DATE(created_at)=? "
                "ORDER BY created_at ASC LIMIT 5",
                (sid, today)
            )
            next_tickets = [r[0] for r in cursor.fetchall()]

            result.append({
                'service_id':       sid,
                'service_name':     name,
                'service_code':     code,
                'color':            color or '#1E88E5',
                'serving':          serving[0] if serving else None,
                'waiting':          waiting,
                'serving_count':    serving_count,
                'next_tickets':     next_tickets,
                '_earliest_deploy': earliest_deploy,
            })

        conn.close()

    active   = sorted([s for s in result if s['_earliest_deploy']],
                      key=lambda s: s['_earliest_deploy'])
    inactive = [s for s in result if not s['_earliest_deploy']]
    result   = active + inactive

    for s in result:
        del s['_earliest_deploy']

    return jsonify({'success': True, 'services': result})

# CALL STATE

_call_state_store = {"queue_type": None}

@app.route('/api/call-state', methods=['GET'])
def get_call_state():
    return jsonify({
        'success':    True,
        'queue_type': _call_state_store['queue_type']
    })

@app.route('/api/call-state', methods=['POST'])
def set_call_state():
    data = request.get_json(silent=True) or {}
    qt   = data.get('queue_type')
    if qt in ('Special Lane', 'ABTC', None):
        _call_state_store['queue_type'] = qt
        print(f"[SERVER] Call state set → {qt}")
        return jsonify({'success': True, 'queue_type': qt})
    return jsonify({'success': False, 'error': 'Invalid queue_type'}), 400


# START FLASK SERVER

def start_flask_server():
    init_db()
    print("=" * 80)
    print("  ISMC OPD QUEUE MANAGEMENT SYSTEM - SERVER STARTED")
    print("=" * 80)
    print(f"  Local URL  : http://localhost:{SERVER_PORT}")
    print(f"  Network URL: http://{SERVER_IP}:{SERVER_PORT}")
    print("=" * 80)
    app.run(host='0.0.0.0', port=SERVER_PORT, debug=False, threaded=True, use_reloader=False)


if IS_SERVER:
    server_thread = threading.Thread(target=start_flask_server, daemon=True)
    server_thread.start()
    time.sleep(2)
else:
    print("=" * 80)
    print("  ISMC OPD QUEUE MANAGEMENT SYSTEM - CLIENT MODE")
    print(f"  Connecting to: {SERVER_URL}")
    print("=" * 80)

# ─────────────────────────────────────────────────────────────────────────────
# TERMS AND CONDITIONS TEXT
# ─────────────────────────────────────────────────────────────────────────────
TERMS_AND_CONDITIONS_TEXT = """TERMS AND CONDITIONS OF USE
ISMC OPD Queue Management System
Ilocos Sur Medical Center

Last Updated: 2026

Please read these Terms and Conditions carefully before using the ISMC OPD Queue Management System. By registering and using this system, you agree to be bound by these terms.

─────────────────────────────────────────────
1. ACCEPTANCE OF TERMS
─────────────────────────────────────────────
By accessing or using this system, you confirm that you are an authorized personnel of Ilocos Sur Medical Center (ISMC) and that you agree to comply with and be bound by these Terms and Conditions, along with all applicable laws and regulations.

─────────────────────────────────────────────
2. APPLICABLE LAWS AND REGULATIONS
─────────────────────────────────────────────

Republic Act No. 10173 – Data Privacy Act of 2012
This system collects and processes personal data of patients and hospital personnel. All data is handled in compliance with R.A. 10173, ensuring that personal information is collected for legitimate purposes, stored securely, and protected from unauthorized access, disclosure, or misuse. Users are obligated to maintain the confidentiality of any patient information accessed through this system.

Republic Act No. 9439 – Hospital Detention Law
This Act prohibits the detention of patients in hospitals due to non-payment of hospital bills. The OPD Queue Management System is designed to facilitate efficient patient flow and service delivery in compliance with this law. Personnel must not use this system to delay or withhold services from patients for financial reasons.

Republic Act No. 7305 – Magna Carta of Public Health Workers
As authorized users of this system, public health workers are entitled to the rights and protections provided under R.A. 7305. This system supports the efficient discharge of your duties. Any misuse of the system that results in substandard patient care may be subject to administrative action.

Republic Act No. 11223 – Universal Health Care Act
In line with the Universal Health Care Act, this system is implemented to ensure that all Filipinos, especially those seeking OPD services at ISMC, receive quality, accessible, and efficient health care services. Personnel must use this system to uphold the rights of patients to timely and appropriate care.

Republic Act No. 9485 – Anti-Red Tape Act of 2007 (as amended by R.A. 11032)
This system is implemented to streamline government service delivery and reduce unnecessary steps in the OPD patient flow. Users are expected to process patient queues efficiently and without unnecessary delay, in accordance with the mandate of the Anti-Red Tape Act.

─────────────────────────────────────────────
3. USER RESPONSIBILITIES
─────────────────────────────────────────────
• You are responsible for maintaining the confidentiality of your login credentials.
• You must not share your username and password with any other person.
• You must only access data and functions relevant to your authorized role.
• Any action performed under your account is your sole responsibility.
• You must immediately report any unauthorized use of your account to the system administrator.

─────────────────────────────────────────────
4. DATA PRIVACY AND CONFIDENTIALITY
─────────────────────────────────────────────
All patient information, queue data, and operational records accessed through this system are confidential. Users are strictly prohibited from:
• Disclosing patient information to unauthorized individuals.
• Copying, printing, or transmitting patient data outside of authorized workflows.
• Using patient data for purposes other than the delivery of hospital services.

Violation of data privacy obligations may result in administrative, civil, or criminal liability under R.A. 10173.

─────────────────────────────────────────────
5. SYSTEM USE AND INTEGRITY
─────────────────────────────────────────────
Users must not attempt to:
• Gain unauthorized access to other accounts or system functions.
• Manipulate queue data, ticket numbers, or patient records fraudulently.
• Introduce malicious software, scripts, or commands into the system.
• Disrupt the normal operation of the system in any way.

─────────────────────────────────────────────
6. DISCIPLINARY ACTION
─────────────────────────────────────────────
Misuse of this system, including but not limited to unauthorized access, data breaches, fraudulent manipulation of records, or violations of these Terms and Conditions, may result in:
• Suspension or permanent revocation of system access.
• Administrative disciplinary proceedings.
• Civil or criminal liability under applicable Philippine laws.

─────────────────────────────────────────────
7. AMENDMENTS
─────────────────────────────────────────────
ISMC reserves the right to update or modify these Terms and Conditions at any time. Users will be notified of significant changes. Continued use of the system after any amendments constitutes acceptance of the updated terms.

─────────────────────────────────────────────
8. CONTACT AND REPORTING
─────────────────────────────────────────────
For concerns, questions, or to report violations related to these Terms and Conditions, please contact the ISMC ICT Department or the Data Protection Officer (DPO).

─────────────────────────────────────────────
By checking the "I agree to the Terms and Conditions" box during registration, you acknowledge that you have read, understood, and agree to be bound by these Terms and Conditions.
─────────────────────────────────────────────
"""


# ─────────────────────────────────────────────────────────────────────────────
# TERMS AND CONDITIONS POPUP
# ─────────────────────────────────────────────────────────────────────────────
def show_terms_popup(parent_window):
    """Opens a professional Terms and Conditions popup window with scrollbar."""
    popup = tk.Toplevel(parent_window)
    popup.title("Terms and Conditions — ISMC OPD Queue Management System")
    popup.geometry("700x580")
    popup.configure(bg="#F0F4F8")
    popup.resizable(False, False)
    popup.grab_set()
    popup.update_idletasks()
    x = (popup.winfo_screenwidth() // 2) - 350
    y = (popup.winfo_screenheight() // 2) - 290
    popup.geometry(f"700x580+{x}+{y}")

    # ── Header ──
    header = tk.Frame(popup, bg="#1565C0", height=64)
    header.pack(fill="x")
    header.pack_propagate(False)
    header_inner = tk.Frame(header, bg="#1565C0")
    header_inner.place(relx=0.5, rely=0.5, anchor="center")
    tk.Label(header_inner, text="📋  Terms and Conditions",
             font=("Segoe UI", 15, "bold"), bg="#1565C0", fg="white").pack()
    tk.Label(header_inner, text="ISMC OPD Queue Management System",
             font=("Segoe UI", 9), bg="#1565C0", fg="#90CAF9").pack()

    # ── Subheader strip ──
    sub = tk.Frame(popup, bg="#E3F2FD", height=30)
    sub.pack(fill="x")
    sub.pack_propagate(False)
    tk.Label(sub, text="Please read carefully before registering.",
             font=("Segoe UI", 9, "italic"), bg="#E3F2FD", fg="#1565C0").pack(
             side="left", padx=16, pady=6)

    # ── Text area + scrollbar ──
    text_frame = tk.Frame(popup, bg="#F0F4F8")
    text_frame.pack(fill="both", expand=True, padx=16, pady=(12, 0))

    scrollbar = tk.Scrollbar(text_frame, orient="vertical", width=14,
                             troughcolor="#E8EFF5", bg="#B0BEC5",
                             activebackground="#90A4AE")
    scrollbar.pack(side="right", fill="y")

    text_widget = tk.Text(
        text_frame,
        font=("Segoe UI", 10),
        bg="white", fg="#263238",
        relief="flat", bd=0,
        wrap="word",
        padx=20, pady=16,
        yscrollcommand=scrollbar.set,
        cursor="arrow",
        state="normal",
        selectbackground="#BBDEFB"
    )
    text_widget.pack(side="left", fill="both", expand=True)
    scrollbar.config(command=text_widget.yview)

    text_widget.insert("1.0", TERMS_AND_CONDITIONS_TEXT)
    text_widget.config(state="disabled")

    # ── Footer ──
    # FIX 1: height increased 70 → 90 so the Close button has comfortable
    #         top and bottom spacing and is not cramped against the edges.
    footer = tk.Frame(popup, bg="#F0F4F8", height=90)
    footer.pack(fill="x", padx=16, pady=12)
    footer.pack_propagate(False)

    tk.Label(footer, text="© 2026 Ilocos Sur Medical Center  |  ICT Department",
             font=("Segoe UI", 8), bg="#F0F4F8", fg="#90A4AE").pack(
             side="left", pady=12)

    # FIX 1: ipady increased 13 → 16 so the Close button has more internal
    #         top/bottom padding, making it look taller and easier to click.


# ─────────────────────────────────────────────────────────────────────────────
# FORGOT PASSWORD POPUP
# ─────────────────────────────────────────────────────────────────────────────
def forgot_password_popup():
    """Opens a Forgot Password dialog — verifies username then resets password."""
    popup = tk.Toplevel(root)
    popup.title("Forgot Password — ISMC OPD Queue")
    popup.geometry("480x490")
    popup.configure(bg="#E8F4F8")
    popup.resizable(False, False)
    popup.grab_set()
    popup.update_idletasks()
    x = (popup.winfo_screenwidth() // 2) - 240
    y = (popup.winfo_screenheight() // 2) - 245
    popup.geometry(f"480x490+{x}+{y}")

    shadow = tk.Frame(popup, bg="#B0BEC5")
    shadow.place(relx=0.5, rely=0.5, anchor="center", width=454, height=464)
    card = tk.Frame(shadow, bg="white")
    card.pack(fill="both", expand=True, padx=3, pady=3)

    # Header
    hdr = tk.Frame(card, bg="#1E88E5", height=62)
    hdr.pack(fill="x")
    hdr.pack_propagate(False)
    tk.Label(hdr, text="Reset Password", font=("Segoe UI", 16, "bold"),
             bg="#1E88E5", fg="white").pack(expand=True)

    body = tk.Frame(card, bg="white")
    body.pack(fill="both", expand=True, padx=36, pady=20)

    tk.Label(body,
             text="Enter your username and a new password.\n"
                  "If your username is not found, please register a new account.",
             font=("Segoe UI", 10), bg="white", fg="#546E7A",
             justify="left", wraplength=380).pack(anchor="w", pady=(0, 16))

    def make_field(label_text, show=None):
        tk.Label(body, text=label_text, font=("Segoe UI", 10, "bold"),
                 bg="white", fg="#37474F").pack(anchor="w")
        entry = tk.Entry(body, font=("Segoe UI", 11), bg="#F5F5F5", fg="#263238",
                         relief="flat", bd=0, show=show)
        entry.pack(fill="x", ipady=9, pady=(4, 0))
        border = tk.Frame(body, bg="#BDBDBD", height=2)
        border.pack(fill="x", pady=(0, 12))
        entry.bind("<FocusIn>",  lambda e: [border.config(bg="#1E88E5"), entry.config(bg="white")])
        entry.bind("<FocusOut>", lambda e: [border.config(bg="#BDBDBD"), entry.config(bg="#F5F5F5")])
        return entry

    fp_username_entry  = make_field("Username")
    fp_new_pass_entry  = make_field("New Password", show="*")
    fp_confirm_entry   = make_field("Confirm New Password", show="*")

    def do_reset():
        username     = fp_username_entry.get().strip()
        new_password = fp_new_pass_entry.get().strip()
        confirm      = fp_confirm_entry.get().strip()

        if not username or not new_password or not confirm:
            messagebox.showerror("Error", "Please fill in all fields.", parent=popup)
            return
        if len(new_password) < 6:
            messagebox.showerror("Error", "Password must be at least 6 characters.", parent=popup)
            return
        if len(new_password) > 18:
            messagebox.showerror("Error", "Password must not exceed 18 characters.", parent=popup)
            return
        if new_password != confirm:
            messagebox.showerror("Error", "Passwords do not match.", parent=popup)
            return

        try:
            with db_lock:
                conn   = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute("SELECT user_id FROM users WHERE username=?", (username,))
                user = cursor.fetchone()
                if not user:
                    conn.close()
                    messagebox.showerror(
                        "Username Not Found",
                        "No account found with that username.\n\n"
                        "Please check your username or register a new account.",
                        parent=popup
                    )
                    return
                cursor.execute(
                    "UPDATE users SET password_hash=? WHERE username=?",
                    (hash_password(new_password), username)
                )
                conn.commit()
                conn.close()
            messagebox.showinfo("Success",
                "Password has been reset successfully.\nYou may now log in with your new password.",
                parent=popup)
            popup.destroy()
        except Exception as e:
            messagebox.showerror("Error", f"Could not reset password:\n{str(e)}", parent=popup)

    btn_row = tk.Frame(body, bg="white")
    btn_row.pack(fill="x", pady=(4, 0))
    for text, cmd, bg, hv in [
        ("Reset Password", do_reset,      "#1E88E5", "#1565C0"),
        ("Cancel",         popup.destroy, "#757575", "#616161"),
    ]:
        b = tk.Button(btn_row, text=text, font=("Segoe UI", 11, "bold"),
                      bg=bg, fg="white", bd=0, relief="flat",
                      cursor="hand2", command=cmd)
        b.pack(side="left", expand=True, fill="x", ipady=11, padx=5)
        b.bind("<Enter>", lambda e, h=hv, btn=b: btn.config(bg=h))
        b.bind("<Leave>", lambda e, c=bg,  btn=b: btn.config(bg=c))


# ─────────────────────────────────────────────────────────────────────────────
# REGISTER POPUP
# ─────────────────────────────────────────────────────────────────────────────
def register_popup():
    popup = tk.Toplevel(root)
    popup.title("Register - ISMC OPD Queue")
    popup.geometry("600x760")
    popup.configure(bg="#E8F4F8")
    popup.resizable(False, False)
    popup.grab_set()
    popup.update_idletasks()
    x = (popup.winfo_screenwidth() // 2) - 300
    y = (popup.winfo_screenheight() // 2) - 380
    popup.geometry(f"600x760+{x}+{y}")

    shadow_frame = tk.Frame(popup, bg="#B0BEC5")
    shadow_frame.place(relx=0.5, rely=0.5, anchor="center", width=570, height=730)
    frame = tk.Frame(shadow_frame, bg="white")
    frame.pack(fill="both", expand=True, padx=3, pady=3)
    header = tk.Frame(frame, bg="#1E88E5", height=75)
    header.pack(fill="x")
    header.pack_propagate(False)
    tk.Label(header, text="Create New Account", font=("Segoe UI", 19, "bold"),
             bg="#1E88E5", fg="white").pack(expand=True)
    form_frame = tk.Frame(frame, bg="white")
    form_frame.pack(fill="both", expand=True, padx=50, pady=20)

    # ── Password max-length trace helper ──
    PASSWORD_MAX = 18

    def enforce_max_length(var, max_len=PASSWORD_MAX):
        val = var.get()
        if len(val) > max_len:
            var.set(val[:max_len])

    def create_field(label_text, show=None, is_required=True, textvariable=None):
        container = tk.Frame(form_frame, bg="white")
        container.pack(fill="x", pady=8)
        lf = tk.Frame(container, bg="white")
        lf.pack(fill="x")
        tk.Label(lf, text=label_text, font=("Segoe UI", 11, "bold"),
                 bg="white", fg="#37474F").pack(side="left")
        if is_required:
            tk.Label(lf, text="*", font=("Segoe UI", 11, "bold"),
                     bg="white", fg="#E53935").pack(side="left", padx=2)
        entry_kwargs = dict(font=("Segoe UI", 12), bg="#F5F5F5", fg="#263238",
                            relief="flat", bd=0)
        if show:
            entry_kwargs["show"] = show
        if textvariable:
            entry_kwargs["textvariable"] = textvariable
        entry = tk.Entry(container, **entry_kwargs)
        entry.pack(fill="x", ipady=11, pady=(5, 0))
        border = tk.Frame(container, bg="#BDBDBD", height=2)
        border.pack(fill="x")
        entry.bind("<FocusIn>",  lambda e: [border.config(bg="#1E88E5"), entry.config(bg="white")])
        entry.bind("<FocusOut>", lambda e: [border.config(bg="#BDBDBD"), entry.config(bg="#F5F5F5")])
        return entry

    name_entry         = create_field("Full Name")
    spec_entry         = create_field("Specialization", is_required=False)
    reg_username_entry = create_field("Username")

    # Password fields with max-18 enforcement
    pw_var      = tk.StringVar()
    confirm_var = tk.StringVar()
    pw_var.trace_add("write",      lambda *_: enforce_max_length(pw_var))
    confirm_var.trace_add("write", lambda *_: enforce_max_length(confirm_var))

    # Password field with counter label
    pw_container = tk.Frame(form_frame, bg="white")
    pw_container.pack(fill="x", pady=8)
    pw_lf = tk.Frame(pw_container, bg="white")
    pw_lf.pack(fill="x")
    tk.Label(pw_lf, text="Password", font=("Segoe UI", 11, "bold"),
             bg="white", fg="#37474F").pack(side="left")
    tk.Label(pw_lf, text="*", font=("Segoe UI", 11, "bold"),
             bg="white", fg="#E53935").pack(side="left", padx=2)
    pw_counter_lbl = tk.Label(pw_lf, text="0 / 18",
                              font=("Segoe UI", 9), bg="white", fg="#90A4AE")
    pw_counter_lbl.pack(side="right", padx=4)
    reg_password_entry = tk.Entry(pw_container, textvariable=pw_var,
                                  font=("Segoe UI", 12), bg="#F5F5F5", fg="#263238",
                                  relief="flat", bd=0, show="*")
    reg_password_entry.pack(fill="x", ipady=11, pady=(5, 0))
    pw_border = tk.Frame(pw_container, bg="#BDBDBD", height=2)
    pw_border.pack(fill="x")
    reg_password_entry.bind("<FocusIn>",  lambda e: [pw_border.config(bg="#1E88E5"), reg_password_entry.config(bg="white")])
    reg_password_entry.bind("<FocusOut>", lambda e: [pw_border.config(bg="#BDBDBD"), reg_password_entry.config(bg="#F5F5F5")])

    def update_pw_counter(*_):
        n = len(pw_var.get())
        color = "#E53935" if n >= PASSWORD_MAX else ("#FB8C00" if n >= 14 else "#90A4AE")
        pw_counter_lbl.config(text=f"{n} / {PASSWORD_MAX}", fg=color)

    pw_var.trace_add("write", update_pw_counter)

    # Confirm password field with counter
    cf_container = tk.Frame(form_frame, bg="white")
    cf_container.pack(fill="x", pady=8)
    cf_lf = tk.Frame(cf_container, bg="white")
    cf_lf.pack(fill="x")
    tk.Label(cf_lf, text="Confirm Password", font=("Segoe UI", 11, "bold"),
             bg="white", fg="#37474F").pack(side="left")
    tk.Label(cf_lf, text="*", font=("Segoe UI", 11, "bold"),
             bg="white", fg="#E53935").pack(side="left", padx=2)
    cf_counter_lbl = tk.Label(cf_lf, text="0 / 18",
                               font=("Segoe UI", 9), bg="white", fg="#90A4AE")
    cf_counter_lbl.pack(side="right", padx=4)
    confirm_entry = tk.Entry(cf_container, textvariable=confirm_var,
                             font=("Segoe UI", 12), bg="#F5F5F5", fg="#263238",
                             relief="flat", bd=0, show="*")
    confirm_entry.pack(fill="x", ipady=11, pady=(5, 0))
    cf_border = tk.Frame(cf_container, bg="#BDBDBD", height=2)
    cf_border.pack(fill="x")
    confirm_entry.bind("<FocusIn>",  lambda e: [cf_border.config(bg="#1E88E5"), confirm_entry.config(bg="white")])
    confirm_entry.bind("<FocusOut>", lambda e: [cf_border.config(bg="#BDBDBD"), confirm_entry.config(bg="#F5F5F5")])

    def update_cf_counter(*_):
        n = len(confirm_var.get())
        color = "#E53935" if n >= PASSWORD_MAX else ("#FB8C00" if n >= 14 else "#90A4AE")
        cf_counter_lbl.config(text=f"{n} / {PASSWORD_MAX}", fg=color)

    confirm_var.trace_add("write", update_cf_counter)

    # ── Terms & Conditions checkbox row ──
    terms_var = tk.BooleanVar(value=False)
    terms_row = tk.Frame(form_frame, bg="white")
    terms_row.pack(fill="x", pady=(14, 4))

    terms_cb = tk.Checkbutton(
        terms_row, variable=terms_var,
        bg="white", activebackground="white",
        relief="flat", cursor="hand2"
    )
    terms_cb.pack(side="left")

    tk.Label(terms_row, text="I agree to the",
             font=("Segoe UI", 10), bg="white", fg="#546E7A").pack(side="left")

    read_link = tk.Label(terms_row,
                         text=" Terms and Conditions",
                         font=("Segoe UI", 10, "underline", "bold"),
                         bg="white", fg="#1E88E5", cursor="hand2")
    read_link.pack(side="left")
    read_link.bind("<Button-1>", lambda e: show_terms_popup(popup))
    read_link.bind("<Enter>",    lambda e: read_link.config(fg="#1565C0"))
    read_link.bind("<Leave>",    lambda e: read_link.config(fg="#1E88E5"))

    def save_doctor():
        full_name        = name_entry.get().strip()
        specialization   = spec_entry.get().strip()
        username         = reg_username_entry.get().strip()
        password         = pw_var.get().strip()
        confirm_password = confirm_var.get().strip()

        if not full_name or not username or not password:
            messagebox.showerror("Error", "Please fill in all required fields (*)", parent=popup)
            return
        if password != confirm_password:
            messagebox.showerror("Error", "Passwords do not match", parent=popup)
            return
        if len(password) < 6:
            messagebox.showerror("Error", "Password must be at least 6 characters", parent=popup)
            return
        if len(password) > PASSWORD_MAX:
            messagebox.showerror("Error", f"Password must not exceed {PASSWORD_MAX} characters", parent=popup)
            return
        if not terms_var.get():
            messagebox.showerror("Error",
                "You must agree to the Terms and Conditions before registering.",
                parent=popup)
            return

        try:
            response = requests.post(f"{API_BASE_URL}/auth/register", json={
                'full_name': full_name, 'specialization': specialization or None,
                'username': username, 'password': password
            }, timeout=REQUEST_TIMEOUT)
            data = response.json()
            if response.status_code == 200 and data.get('success'):
                messagebox.showinfo("Success", "Account registered! You can now login.", parent=popup)
                popup.destroy()
            elif response.status_code == 409:
                messagebox.showwarning("Error", "Username already exists.", parent=popup)
            else:
                messagebox.showerror("Error", data.get('message', 'Registration failed'), parent=popup)
        except Exception as e:
            messagebox.showerror("Error", f"Failed: {str(e)}", parent=popup)

    btn_container = tk.Frame(form_frame, bg="white")
    btn_container.pack(fill="x", pady=(16, 0))
    for text, cmd, color, hover in [
        ("Confirm", save_doctor,   "#43A047", "#2E7D32"),
        ("Cancel",  popup.destroy, "#757575", "#616161")
    ]:
        btn = tk.Button(btn_container, text=text, font=("Segoe UI", 12, "bold"),
                        bg=color, fg="white", bd=0, relief="flat",
                        cursor="hand2", command=cmd)
        btn.pack(side="left", expand=True, fill="x", ipady=13, padx=8)
        btn.bind("<Enter>", lambda e, h=hover, b=btn: b.config(bg=h))
        btn.bind("<Leave>", lambda e, c=color, b=btn: b.config(bg=c))


def do_login():
    username = username_entry.get().strip()
    password = password_entry.get().strip()
    if not username or not password:
        messagebox.showerror("Login Error", "Please enter both username and password")
        return
    try:
        response = requests.post(f"{API_BASE_URL}/auth/login",
                                 json={'username': username, 'password': password},
                                 timeout=REQUEST_TIMEOUT)
        data = response.json()
        if response.status_code == 200 and data.get('success'):
            root.destroy()
            from dashboard import open_dashboard
            open_dashboard(data.get('full_name'))
        else:
            messagebox.showerror("Login Failed", "Invalid username or password")
            password_entry.delete(0, tk.END)
    except Exception as e:
        messagebox.showerror("Connection Error",
            f"Cannot connect to server.\n\n{str(e)}\n\nMake sure:\n"
            f"1. Server laptop is running (IS_SERVER=True)\n"
            f"2. Firewall allows port {SERVER_PORT}\n"
            f"3. Both laptops are on the same WiFi/network")

# MAIN WINDOW
if __name__ == "__main__":
    root = tk.Tk()
    root.title("ISMC OPD Queue Management System - Login")
    # FIX 2: Height increased 600 → 640 so the Copyright label at the bottom
    #         is no longer clipped by the window edge.
    root.geometry("900x640")
    root.configure(bg="#E8F4F8")
    root.resizable(False, False)
    root.update_idletasks()
    root.geometry(f"900x640+{(root.winfo_screenwidth()-900)//2}+{(root.winfo_screenheight()-640)//2}")

    main_container = tk.Frame(root, bg="#E8F4F8")
    main_container.pack(fill="both", expand=True)

    left_panel = tk.Frame(main_container, bg="#1E88E5", width=400)
    left_panel.pack(side="left", fill="both", expand=True)
    branding_container = tk.Frame(left_panel, bg="#1E88E5")
    branding_container.place(relx=0.5, rely=0.5, anchor="center")
    logo_frame = tk.Frame(branding_container, bg="white", width=140, height=140)
    logo_frame.pack(pady=(0, 20))
    logo_frame.pack_propagate(False)

    try:
        _logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ismc_logo.png")
        logo_img = ImageTk.PhotoImage(Image.open(_logo_path).resize((130, 130), Image.LANCZOS))
        lbl = tk.Label(logo_frame, image=logo_img, bg="white")
        lbl.image = logo_img
        lbl.place(relx=0.5, rely=0.5, anchor="center")
    except Exception as _logo_err:
        print(f"[LOGIN] Logo not loaded: {_logo_err}")
        tk.Label(logo_frame, text="ISMC", font=("Segoe UI", 32, "bold"),
                 bg="white", fg="#1E88E5").place(relx=0.5, rely=0.5, anchor="center")

    tk.Label(branding_container, text="OPD Queue Management",
             font=("Segoe UI", 24, "bold"), bg="#1E88E5", fg="white").pack()
    tk.Label(branding_container, text="Ilocos Sur Medical Center",
             font=("Segoe UI", 16), bg="#1E88E5", fg="#B3E5FC").pack(pady=(5, 0))

    right_panel = tk.Frame(main_container, bg="white", width=500)
    right_panel.pack(side="right", fill="both")
    right_panel.pack_propagate(False)
    login_container = tk.Frame(right_panel, bg="white")
    login_container.place(relx=0.5, rely=0.5, anchor="center", width=380)

    tk.Label(login_container, text="Welcome Back!", font=("Segoe UI", 26, "bold"),
             bg="white", fg="#263238").pack(pady=(0, 5))
    tk.Label(login_container, text="Login to access the system",
             font=("Segoe UI", 11), bg="white", fg="#78909C").pack(pady=(0, 30))

    username_container = tk.Frame(login_container, bg="white")
    username_container.pack(fill="x", pady=8)
    tk.Label(username_container, text="Username", font=("Segoe UI", 10, "bold"),
             bg="white", fg="#37474F").pack(anchor="w")
    username_entry = tk.Entry(username_container, font=("Segoe UI", 12),
                              bg="#F5F5F5", fg="#263238", relief="flat", bd=0)
    username_entry.pack(fill="x", ipady=10, pady=(6, 0))
    u_border = tk.Frame(username_container, bg="#BDBDBD", height=2)
    u_border.pack(fill="x")
    username_entry.bind("<FocusIn>",  lambda e: [u_border.config(bg="#1E88E5"), username_entry.config(bg="white")])
    username_entry.bind("<FocusOut>", lambda e: [u_border.config(bg="#BDBDBD"), username_entry.config(bg="#F5F5F5")])
    username_entry.bind("<Return>", lambda e: password_entry.focus())

    password_container = tk.Frame(login_container, bg="white")
    password_container.pack(fill="x", pady=8)
    tk.Label(password_container, text="Password", font=("Segoe UI", 10, "bold"),
             bg="white", fg="#37474F").pack(anchor="w")
    password_entry = tk.Entry(password_container, font=("Segoe UI", 12),
                              bg="#F5F5F5", fg="#263238", relief="flat", bd=0, show="*")
    password_entry.pack(fill="x", ipady=10, pady=(6, 0))
    p_border = tk.Frame(password_container, bg="#BDBDBD", height=2)
    p_border.pack(fill="x")
    password_entry.bind("<FocusIn>",  lambda e: [p_border.config(bg="#1E88E5"), password_entry.config(bg="white")])
    password_entry.bind("<FocusOut>", lambda e: [p_border.config(bg="#BDBDBD"), password_entry.config(bg="#F5F5F5")])
    password_entry.bind("<Return>", lambda e: do_login())

    login_btn = tk.Button(login_container, text="LOGIN", font=("Segoe UI", 12, "bold"),
                          bg="#1E88E5", fg="white", bd=0, relief="flat", cursor="hand2", command=do_login)
    login_btn.pack(fill="x", ipady=12, pady=(25, 15))
    login_btn.bind("<Enter>", lambda e: login_btn.config(bg="#1565C0"))
    login_btn.bind("<Leave>", lambda e: login_btn.config(bg="#1E88E5"))

    # ── Forgot Password link ──
    forgot_link = tk.Label(login_container, text="Forgot Password?",
                           font=("Segoe UI", 10, "underline"),
                           bg="white", fg="#1E88E5", cursor="hand2")
    forgot_link.pack(anchor="e", pady=(0, 10))
    forgot_link.bind("<Button-1>", lambda e: forgot_password_popup())
    forgot_link.bind("<Enter>",    lambda e: forgot_link.config(fg="#1565C0"))
    forgot_link.bind("<Leave>",    lambda e: forgot_link.config(fg="#1E88E5"))

    divider_frame = tk.Frame(login_container, bg="white")
    divider_frame.pack(fill="x", pady=15)
    tk.Frame(divider_frame, bg="#E0E0E0", height=1).pack(side="left", fill="x", expand=True)
    tk.Label(divider_frame, text="OR", font=("Segoe UI", 9), bg="white", fg="#9E9E9E").pack(side="left", padx=10)
    tk.Frame(divider_frame, bg="#E0E0E0", height=1).pack(side="right", fill="x", expand=True)

    register_btn = tk.Button(login_container, text="Register", font=("Segoe UI", 11, "bold"),
                             bg="white", fg="#1E88E5", bd=2, relief="solid", cursor="hand2",
                             command=register_popup)
    register_btn.pack(fill="x", ipady=10, pady=(5, 0))
    register_btn.bind("<Enter>", lambda e: register_btn.config(bg="#E3F2FD"))
    register_btn.bind("<Leave>", lambda e: register_btn.config(bg="white"))

    server_status_frame = tk.Frame(login_container, bg="white")
    server_status_frame.pack(pady=(20, 0))

    def check_server_status():
        try:
            response = requests.get(f"{SERVER_URL}/api/health", timeout=2)
            if response.status_code == 200:
                mode_text = "SERVER" if IS_SERVER else "CLIENT"
                server_status_label.config(
                    text=f"✓ {mode_text}: {SERVER_IP}:{SERVER_PORT}", fg="#43A047")
            else:
                server_status_label.config(text="✗ SERVER ERROR", fg="#E53935")
        except:
            server_status_label.config(
                text=f"✗ OFFLINE: {SERVER_IP}:{SERVER_PORT}", fg="#E53935")
        try:
            root.after(5000, check_server_status)
        except:
            pass

    server_status_label = tk.Label(server_status_frame, text="[CONNECTING...]",
                                   font=("Segoe UI", 9), bg="white", fg="#FB8C00")
    server_status_label.pack()
    check_server_status()

    tk.Label(login_container, text="© 2026 Ilocos Sur Medical Center",
             font=("Segoe UI", 9), bg="white", fg="#9E9E9E").pack(pady=(15, 0))

    username_entry.focus()
    root.mainloop()