import requests
import json
import uuid
import os

BASE_URL = "http://localhost:8001/api"

def test_full_flow():
    # 1. Register a new user
    email = f"tester_{uuid.uuid4().hex[:6]}@example.com"
    password = "SecurePass123!"
    print(f"Registering user: {email}...")
    
    reg_data = {
        "email": email,
        "password": password,
        "first_name": "Test",
        "last_name": "FullFlow"
    }
    
    reg_res = requests.post(f"{BASE_URL}/users/register", json=reg_data)
    if reg_res.status_code not in [200, 201]:
        print(f"Registration failed: {reg_res.text}")
        return
    
    # 2. Login
    print("Logging in...")
    login_data = {
        "username": email,
        "password": password
    }
    response = requests.post(f"{BASE_URL}/users/login", data=login_data)
    if response.status_code != 200:
        print(f"Login failed: {response.text}")
        return
    
    token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("Login successful!")

    # 3. Upload a document
    print("Uploading document...")
    sample_file = "docs/Statistical_Analysis_Plan_Redacted-v1.pdf"
    if not os.path.exists(sample_file):
        # Fallback to creating a small text file if PDF doesn't exist
        sample_file = "sample.txt"
        with open(sample_file, "w") as f:
            f.write("This is a sample service agreement for testing purposes. Monthly fee is $2000. Due on 15th.")
    
    with open(sample_file, "rb") as f:
        files = {"file": (os.path.basename(sample_file), f, "application/pdf" if sample_file.endswith(".pdf") else "text/plain")}
        upload_res = requests.post(f"{BASE_URL}/documents/upload", headers=headers, files=files)
    
    if upload_res.status_code not in [200, 201, 202]:
        print(f"Upload failed: {upload_res.text}")
        return
    
    doc_id = upload_res.json()["document_id"]
    print(f"Document uploaded! ID: {doc_id}")
    print("Waiting for processing (simulated)...")
    # In a real scenario, we'd wait for status to be 'processed'
    # But for demo, we might hit the DB directly to ensure it's 'processed' and has content
    # Or just try our luck after a short sleep
    import time
    # time.sleep(5) 

    # 4. Chat with document
    print("\n--- CHAT WITH DOCUMENT REQUEST ---")
    chat_payload = {
        "document_id": doc_id,
        "user_input": "What is the primary objective of this document?"
    }
    print(f"Request: {json.dumps(chat_payload, indent=2)}")
    
    chat_res = requests.post(f"{BASE_URL}/llm/chat/document", headers=headers, json=chat_payload)
    
    if chat_res.status_code == 200:
        print("\n--- API RESPONSE ---")
        print(json.dumps(chat_res.json(), indent=2))
    else:
        print(f"\nChat failed ({chat_res.status_code}): {chat_res.text}")

if __name__ == "__main__":
    test_full_flow()
