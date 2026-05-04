import requests
import os
import time

BASE_URL = "http://127.0.0.1:8001"

def get_token():
    res = requests.post(f"{BASE_URL}/api/users/login", data={"username": "admin@demo.com", "password": "admin123"})
    res.raise_for_status()
    return res.json()["access_token"]

def upload_file(file_path):
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    print(f"Uploading {file_path} ({os.path.getsize(file_path)} bytes)...")
    with open(file_path, "rb") as f:
        files = {"file": (os.path.basename(file_path), f, "application/pdf")}
        res = requests.post(f"{BASE_URL}/api/documents/upload", headers=headers, files=files)
        
    print(f"Upload Status: {res.status_code}")
    if res.ok:
        doc_id = res.json()["document_id"]
        print(f"Document ID: {doc_id}")
        return doc_id
    else:
        print(f"Error: {res.text}")
        return None

if __name__ == "__main__":
    file_to_upload = "docs/CSR_Redacted.pdf"
    doc_id = upload_file(file_to_upload)
