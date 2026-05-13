import requests
import os
import sys

BASE_URL = "http://localhost:8001/api"

def test_upload():
    # Step 1: Log in
    print("Attempting login...")
    login_data = {
        "username": "admin@demo.com",
        "password": "Password@123"
    }
    try:
        r = requests.post(f"{BASE_URL}/users/login", data=login_data)
        if r.status_code != 200:
            print(f"Login Failed: {r.status_code} {r.text}")
            return
        token = r.json()["access_token"]
        print("Login Successful. Got token.")
    except Exception as e:
        print(f"Connection failure: {e}")
        return

    headers = {
        "Authorization": f"Bearer {token}"
    }

    # Step 2: Create test file
    import time
    test_filename = f"diagnostic_test_doc_{int(time.time())}.txt"
    with open(test_filename, "w") as f:
        f.write("This is a test document created for diagnosing document upload functionality.")

    # Step 3: Perform upload
    print(f"Uploading {test_filename}...")
    try:
        with open(test_filename, "rb") as f:
            files = {"file": (test_filename, f, "text/plain")}
            r = requests.post(f"{BASE_URL}/documents/upload", headers=headers, files=files)
            print(f"Status Code: {r.status_code}")
            print(f"Response: {r.text}")
    except Exception as e:
        print(f"Upload execution failure: {e}")
    finally:
        if os.path.exists(test_filename):
            os.remove(test_filename)

if __name__ == "__main__":
    test_upload()
