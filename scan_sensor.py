"""Scan the fingerprint sensor to find which slots have templates."""
import requests

ESP32_IP = "192.168.0.103"

print("Scanning sensor slots 0-99...")
found = []
for i in range(100):
    try:
        r = requests.get(f"http://{ESP32_IP}/get_template", params={"id": i}, timeout=5)
        data = r.json()
        if data.get("status") == "success":
            found.append(i)
            print(f"  Slot {i}: template found ({data.get('size')} bytes)")
    except Exception as e:
        print(f"  Slot {i}: error - {e}")
        break

print(f"\nTotal templates found: {len(found)}")
print(f"Slots with templates: {found}")
