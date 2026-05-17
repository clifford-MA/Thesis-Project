import sqlite3

conn = sqlite3.connect("database/opd_queue.db")
cursor = conn.cursor()

# doctors
cursor.execute("""
CREATE TABLE IF NOT EXISTS doctors (
    doctor_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    specialization TEXT,
    username TEXT UNIQUE,
    password TEXT,
    status TEXT
)
""")

# patients
cursor.execute("""
CREATE TABLE IF NOT EXISTS patients (
    patient_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    phone TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")

# opd_services
cursor.execute("""
CREATE TABLE IF NOT EXISTS opd_services (
    service_id INTEGER PRIMARY KEY AUTOINCREMENT,
    service_name TEXT,
    service_code TEXT,
    color TEXT,
    operating_hours TEXT,
    max_daily_ticket INTEGER,
    status TEXT
)
""")

# diagnoses
cursor.execute("""
CREATE TABLE IF NOT EXISTS diagnoses (
    diagnosis_id INTEGER PRIMARY KEY AUTOINCREMENT,
    diagnosis_name TEXT
)
""")

# queues
cursor.execute("""
CREATE TABLE IF NOT EXISTS queues (
    queue_id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER,
    service_id INTEGER,
    queue_number TEXT,
    queue_type TEXT,
    diagnosis_id INTEGER,
    status TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")

# recent_activity
cursor.execute("""
CREATE TABLE IF NOT EXISTS recent_activity (
    activity_id INTEGER PRIMARY KEY AUTOINCREMENT,
    queue_id INTEGER,
    action TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")

# tickets (if not exists already)
cursor.execute("""
CREATE TABLE IF NOT EXISTS tickets (
    ticket_id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_number TEXT UNIQUE NOT NULL,
    service_id INTEGER,
    patient_name TEXT,
    status TEXT DEFAULT 'Waiting',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    served_at DATETIME,
    FOREIGN KEY (service_id) REFERENCES opd_services(service_id)
)
""")

# activity_log (if not exists already)
cursor.execute("""
CREATE TABLE IF NOT EXISTS activity_log (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_number TEXT,
    service_name TEXT,
    status TEXT,
    action TEXT,
    date TEXT,
    time TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")

# announcements (NEW TABLE FOR DISPLAY SCREEN)
cursor.execute("""
CREATE TABLE IF NOT EXISTS announcements (
    announcement_id INTEGER PRIMARY KEY AUTOINCREMENT,
    message TEXT NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")

# Insert default announcement if table is empty
cursor.execute("SELECT COUNT(*) FROM announcements")
if cursor.fetchone()[0] == 0:
    cursor.execute("""
        INSERT INTO announcements (message, created_at) 
        VALUES ('Welcome to ISMC OPD. Please wait for your ticket number to be called.', datetime('now'))
    """)

conn.commit()
conn.close()

print("Database and tables created successfully.")