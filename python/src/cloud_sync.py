"""
Cloud Sync Module for GWASOAT.
Handles uploading/downloading fingerprint templates and attendance records
to/from the cloud backend.

Configure CLOUD_BASE_URL to point to your cloud API server.
"""

import base64
import json
import os
import threading
import time
from typing import Optional, Dict, List, Any

import requests

# Cloud API configuration
CLOUD_BASE_URL = os.environ.get("GWASOAT_CLOUD_URL", "http://localhost:8080/api")
CLOUD_API_KEY = os.environ.get("GWASOAT_API_KEY", "")

# Local cache directory for offline operation
CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "cloud_cache")


class CloudSync:
    """Manages synchronization with cloud backend."""

    def __init__(self, base_url: str = CLOUD_BASE_URL, api_key: str = CLOUD_API_KEY):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._lock = threading.Lock()
        self._online = False
        self._ensure_cache_dir()

    def _ensure_cache_dir(self):
        """Create local cache directory if needed."""
        os.makedirs(CACHE_DIR, exist_ok=True)
        os.makedirs(os.path.join(CACHE_DIR, "templates"), exist_ok=True)
        os.makedirs(os.path.join(CACHE_DIR, "attendance"), exist_ok=True)

    def _headers(self) -> Dict[str, str]:
        """Get request headers with auth."""
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def _request(self, method: str, path: str,
                 json_data: dict = None, timeout: float = 10.0) -> Optional[Dict]:
        """Make authenticated request to cloud API."""
        url = f"{self.base_url}{path}"
        try:
            resp = requests.request(
                method, url, json=json_data,
                headers=self._headers(), timeout=timeout
            )
            self._online = True
            if resp.status_code in (200, 201):
                return resp.json()
            print(f"[CLOUD] {method} {path} → {resp.status_code}")
            return None
        except requests.RequestException as e:
            self._online = False
            print(f"[CLOUD] Request failed: {e}")
            return None

    @property
    def is_online(self) -> bool:
        return self._online

    def check_connection(self) -> bool:
        """Ping cloud to check connectivity."""
        result = self._request("GET", "/health")
        return result is not None

    # ─── Template Management ─────────────────────────────────

    def upload_template(self, class_id: int, student_id: int,
                        name: str, template_bytes: bytes) -> bool:
        """Upload a fingerprint template to cloud."""
        b64 = base64.b64encode(template_bytes).decode()
        data = {
            "student_id": student_id,
            "class_id": class_id,
            "name": name,
            "template": b64,
            "size": len(template_bytes)
        }

        # Always save to local cache
        self._cache_template(class_id, student_id, name, template_bytes)

        # Try cloud upload
        result = self._request("PUT", f"/students/{student_id}/template", data)
        if result:
            print(f"[CLOUD] Template uploaded: student {student_id}")
            return True

        # Queue for later sync if offline
        self._queue_upload(class_id, student_id, name, b64)
        return False

    def download_template(self, student_id: int) -> Optional[bytes]:
        """Download a single template from cloud."""
        result = self._request("GET", f"/students/{student_id}/template")
        if result and "template" in result:
            return base64.b64decode(result["template"])

        # Fall back to local cache
        return self._load_cached_template(student_id)

    def download_class_templates(self, class_id: int) -> List[Dict]:
        """
        Download all templates for a class from cloud.
        Returns list of {student_id, name, template_bytes}
        """
        result = self._request("GET", f"/classes/{class_id}/templates")
        templates = []

        if result and "students" in result:
            for student in result["students"]:
                sid = student.get("student_id") or student.get("id")
                name = student.get("name", "Unknown")
                b64 = student.get("template", "")
                if b64:
                    tpl_bytes = base64.b64decode(b64)
                    templates.append({
                        "student_id": sid,
                        "name": name,
                        "template_bytes": tpl_bytes
                    })
                    # Update local cache
                    self._cache_template(class_id, sid, name, tpl_bytes)
            print(f"[CLOUD] Downloaded {len(templates)} templates for class {class_id}")
            return templates

        # Offline: load from local cache
        return self._load_cached_class(class_id)

    # ─── Attendance Sync ─────────────────────────────────────

    def upload_attendance(self, class_id: int, session_id: int,
                          records: List[Dict]) -> bool:
        """Upload attendance records to cloud."""
        data = {
            "class_id": class_id,
            "session_id": session_id,
            "records": records
        }

        result = self._request("POST", "/attendance/sync", data)
        if result:
            print(f"[CLOUD] Attendance synced: {len(records)} records")
            return True

        # Cache locally for later sync
        cache_file = os.path.join(
            CACHE_DIR, "attendance",
            f"session_{session_id}_{int(time.time())}.json"
        )
        with open(cache_file, "w") as f:
            json.dump(data, f)
        return False

    def sync_pending_attendance(self) -> int:
        """Upload any cached attendance records that failed earlier."""
        att_dir = os.path.join(CACHE_DIR, "attendance")
        synced = 0
        for fname in os.listdir(att_dir):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(att_dir, fname)
            try:
                with open(fpath, "r") as f:
                    data = json.load(f)
                result = self._request("POST", "/attendance/sync", data)
                if result:
                    os.remove(fpath)
                    synced += 1
            except (json.JSONDecodeError, IOError):
                continue
        return synced

    # ─── Local Cache ─────────────────────────────────────────

    def _cache_template(self, class_id: int, student_id: int,
                        name: str, template_bytes: bytes):
        """Save template to local cache."""
        class_dir = os.path.join(CACHE_DIR, "templates", str(class_id))
        os.makedirs(class_dir, exist_ok=True)
        
        # Save binary template
        tpl_path = os.path.join(class_dir, f"{student_id}.bin")
        with open(tpl_path, "wb") as f:
            f.write(template_bytes)
        
        # Save metadata
        meta_path = os.path.join(class_dir, f"{student_id}.json")
        with open(meta_path, "w") as f:
            json.dump({"student_id": student_id, "name": name,
                       "class_id": class_id, "size": len(template_bytes)}, f)

    def _load_cached_template(self, student_id: int) -> Optional[bytes]:
        """Load template from local cache (searches all classes)."""
        tpl_dir = os.path.join(CACHE_DIR, "templates")
        if not os.path.exists(tpl_dir):
            return None
        for class_dir in os.listdir(tpl_dir):
            tpl_path = os.path.join(tpl_dir, class_dir, f"{student_id}.bin")
            if os.path.exists(tpl_path):
                with open(tpl_path, "rb") as f:
                    return f.read()
        return None

    def _load_cached_class(self, class_id: int) -> List[Dict]:
        """Load all templates for a class from local cache."""
        class_dir = os.path.join(CACHE_DIR, "templates", str(class_id))
        if not os.path.exists(class_dir):
            return []
        
        templates = []
        for fname in os.listdir(class_dir):
            if not fname.endswith(".bin"):
                continue
            student_id = int(fname.replace(".bin", ""))
            tpl_path = os.path.join(class_dir, fname)
            meta_path = os.path.join(class_dir, f"{student_id}.json")
            
            with open(tpl_path, "rb") as f:
                tpl_bytes = f.read()
            
            name = "Unknown"
            if os.path.exists(meta_path):
                with open(meta_path, "r") as f:
                    meta = json.load(f)
                    name = meta.get("name", "Unknown")
            
            templates.append({
                "student_id": student_id,
                "name": name,
                "template_bytes": tpl_bytes
            })
        
        print(f"[CACHE] Loaded {len(templates)} cached templates for class {class_id}")
        return templates

    def _queue_upload(self, class_id: int, student_id: int,
                      name: str, b64_template: str):
        """Queue a template upload for when cloud becomes available."""
        queue_dir = os.path.join(CACHE_DIR, "upload_queue")
        os.makedirs(queue_dir, exist_ok=True)
        queue_file = os.path.join(queue_dir, f"{student_id}_{int(time.time())}.json")
        with open(queue_file, "w") as f:
            json.dump({
                "class_id": class_id,
                "student_id": student_id,
                "name": name,
                "template": b64_template
            }, f)

    def sync_pending_templates(self) -> int:
        """Upload any queued templates."""
        queue_dir = os.path.join(CACHE_DIR, "upload_queue")
        if not os.path.exists(queue_dir):
            return 0
        synced = 0
        for fname in os.listdir(queue_dir):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(queue_dir, fname)
            try:
                with open(fpath, "r") as f:
                    data = json.load(f)
                result = self._request("PUT",
                    f"/students/{data['student_id']}/template", data)
                if result:
                    os.remove(fpath)
                    synced += 1
            except (json.JSONDecodeError, IOError):
                continue
        return synced


# Global instance
_cloud: Optional[CloudSync] = None


def get_cloud() -> CloudSync:
    """Get or create global cloud sync instance."""
    global _cloud
    if _cloud is None:
        _cloud = CloudSync()
    return _cloud
