"""Reset all registrations - clears sensor and database."""
import sys
import requests
sys.path.insert(0, 'python/src')
from database import get_db, initialize_database

initialize_database()

ESP32_IP = "192.168.0.103"

# 1. Clear fingerprint sensor
print("Clearing fingerprint sensor...")
try:
    r = requests.post(f"http://{ESP32_IP}/command", json={"cmd": "clear_sensor"}, timeout=10)
    print(f"  Sensor: {r.json()}")
except Exception as e:
    print(f"  Sensor clear failed: {e}")

# 2. Clear database
print("Clearing database registrations...")
db = get_db()
db.execute("UPDATE students SET registered = 0")
db.execute("DELETE FROM fingerprint_templates")
db.commit()

remaining = db.execute("SELECT COUNT(*) as c FROM students").fetchone()['c']
print(f"  Reset {remaining} students to unregistered")
print(f"  Deleted all fingerprint templates from database")
db.close()

print("\nDone! All students need to be re-registered now.")
print("Register them fresh from the app - templates will save to database automatically.")
