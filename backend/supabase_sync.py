import os
import urllib.request
import urllib.parse
import json
import threading

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
BUCKET_NAME = os.getenv("SUPABASE_BUCKET", "hyperlytics")

def is_configured():
    return bool(SUPABASE_URL and SUPABASE_KEY)

def make_request(path, method="GET", body=None, headers=None):
    if not is_configured():
        return None
    
    url = f"{SUPABASE_URL}/storage/v1/object/{path}"
    
    req_headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}"
    }
    if headers:
        req_headers.update(headers)
        
    try:
        req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
        with urllib.request.urlopen(req) as response:
            return response.read()
    except Exception as e:
        print(f"[Supabase Sync] Error during {method} {url}: {e}")
        return None

def download_file(remote_path, local_path):
    print(f"[Supabase Sync] Downloading {remote_path} to {local_path}...")
    # Ensure local directory exists
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    
    data = make_request(f"authenticated/{BUCKET_NAME}/{remote_path}", method="GET")
    if data:
        with open(local_path, "wb") as f:
            f.write(data)
        print(f"[Supabase Sync] Downloaded {remote_path} successfully.")
        return True
    print(f"[Supabase Sync] File {remote_path} not found or download failed.")
    return False

def upload_file_sync(local_path):
    if not os.path.exists(local_path):
        print(f"[Supabase Sync] Local file {local_path} does not exist. Skipping upload.")
        return
        
    # Get relative path inside BUCKET
    # e.g., "data/hyperlytics.db" -> "hyperlytics.db"
    # e.g., "data/shares/xyz.png" -> "shares/xyz.png"
    rel_path = os.path.relpath(local_path, start="data").replace("\\", "/")
    print(f"[Supabase Sync] Uploading {local_path} to remote {rel_path}...")
    
    try:
        with open(local_path, "rb") as f:
            file_bytes = f.read()
            
        headers = {
            "Content-Type": "application/octet-stream",
            "x-upsert": "true"
        }
        res = make_request(f"{BUCKET_NAME}/{rel_path}", method="POST", body=file_bytes, headers=headers)
        if res:
            print(f"[Supabase Sync] Uploaded {rel_path} successfully.")
        else:
            print(f"[Supabase Sync] Uploading {rel_path} failed.")
    except Exception as e:
        print(f"[Supabase Sync] Upload Exception for {rel_path}: {e}")

def sync_to_cloud(local_path):
    """Triggers background upload to avoid blocking API threads"""
    if not is_configured():
        return
    t = threading.Thread(target=upload_file_sync, args=(local_path,))
    t.daemon = True
    t.start()

def sync_from_cloud_on_startup():
    if not is_configured():
        print("[Supabase Sync] Supabase credentials not found. Running in local-only mode.")
        return
        
    print("[Supabase Sync] Initializing sync from cloud...")
    
    # 1. Download database
    db_local = os.path.join("data", "hyperlytics.db")
    download_file("hyperlytics.db", db_local)
    
    # 2. List and download all files in the storage bucket
    try:
        list_url = f"{SUPABASE_URL}/storage/v1/object/list/{BUCKET_NAME}"
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json"
        }
        # Post request to list files
        payload = json.dumps({"prefix": "", "limit": 100}).encode('utf-8')
        req = urllib.request.Request(list_url, data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(req) as res:
            files_list = json.loads(res.read().decode('utf-8'))
            
        for file_info in files_list:
            name = file_info.get("name")
            if not name or name == ".keep":
                continue
            
            # Check recursively if it's a folder or file.
            # Supabase returns id for files, and no id for folder placeholders.
            if file_info.get("id"):
                local_path = os.path.join("data", name)
                if not os.path.exists(local_path):
                    download_file(name, local_path)
                    
        # List shares directory if it exists on remote
        payload_shares = json.dumps({"prefix": "shares", "limit": 100}).encode('utf-8')
        req_shares = urllib.request.Request(list_url, data=payload_shares, headers=headers, method="POST")
        with urllib.request.urlopen(req_shares) as res:
            shares_list = json.loads(res.read().decode('utf-8'))
        for file_info in shares_list:
            name = file_info.get("name")
            if not name:
                continue
            if file_info.get("id"):
                local_path = os.path.join("data", "shares", name)
                if not os.path.exists(local_path):
                    download_file(f"shares/{name}", local_path)
                    
    except Exception as e:
        print(f"[Supabase Sync] Startup list error: {e}")
