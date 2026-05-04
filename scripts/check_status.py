import requests

BASE_URL = "http://127.0.0.1:8001"
DOC_ID = "6d7522f9-9e2a-498d-8a59-56a5eb4eb938"

def check():
    res = requests.post(f"{BASE_URL}/api/users/login", data={"username": "admin@demo.com", "password": "admin123"})
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    res = requests.get(f"{BASE_URL}/api/documents/{DOC_ID}", headers=headers)
    print(res.json()["status"])

if __name__ == "__main__":
    check()
