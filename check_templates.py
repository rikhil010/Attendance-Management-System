"""Check if fingerprint templates are saved in the local database."""
import sys
sys.path.insert(0, 'python/src')
from database import get_db, initialize_database

initialize_database()
db = get_db()

# Check templates table
rows = db.execute(
    "SELECT student_id, class_id, template_size, created_at FROM fingerprint_templates"
).fetchall()

print(f"\n=== Fingerprint Templates in Local Database ===")
print(f"Total saved: {len(rows)}")
if rows:
    for r in rows:
        print(f"  Student ID: {r['student_id']}, Class: {r['class_id']}, "
              f"Size: {r['template_size']} bytes, Date: {r['created_at']}")
else:
    print("  (none - templates are still only on the fingerprint sensor)")

# Check registered students
students = db.execute(
    "SELECT id, name, class_id, registered FROM students WHERE registered = 1"
).fetchall()
print(f"\n=== Registered Students ===")
print(f"Total registered: {len(students)}")
for s in students:
    has_tpl = "✓ template saved" if any(r['student_id'] == s['id'] for r in rows) else "✗ sensor only"
    print(f"  ID: {s['id']}, Name: {s['name']}, Class: {s['class_id']}, {has_tpl}")

db.close()
