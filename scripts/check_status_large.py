import requests
import time

BASE_URL = "http://127.0.0.1:8001"
DOC_ID = "4076bbeb-927c-46be-8ffe-a85fa1d11485"

def check():
    res = requests.post(f"{BASE_URL}/api/users/login", data={"username": "admin@demo.com", "password": "admin123"})
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    for _ in range(20):
        res = requests.get(f"{BASE_URL}/api/documents/{DOC_ID}", headers=headers)
        status = res.json()["status"]
        print(f"Current Status: {status}")
        if status in ["processed", "failed"]:
            break
        time.sleep(10)

if __name__ == "__main__":
    check()
