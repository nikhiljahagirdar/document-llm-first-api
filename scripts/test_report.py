import requests
import json

BASE_URL = "http://127.0.0.1:8001"
DOC_ID = "6d7522f9-9e2a-498d-8a59-56a5eb4eb938"

def test_report():
    res = requests.post(f"{BASE_URL}/api/users/login", data={"username": "admin@demo.com", "password": "admin123"})
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # 1. Get templates
    res = requests.get(f"{BASE_URL}/api/templates/public/", headers=headers)
    templates = res.json()
    if not templates:
        print("No templates found")
        return
    
    tpl_id = templates[0]["template_id"]
    
    # 2. Analyze
    payload = {
        "document_id": DOC_ID,
        "template_id": tpl_id,
        "prompt": "Extract summary"
    }
    print(f"Analyzing document {DOC_ID} with template {tpl_id}...")
    res = requests.post(f"{BASE_URL}/api/reports/analyze", headers=headers, json=payload)
    
    if res.ok:
        report = res.json()
        print("Report Generated Successfully")
        print(f"Tokens Consumed: {report.get('tokens_consumed')}")
        print(json.dumps(report, indent=2))
    else:
        print(f"Error: {res.text}")

if __name__ == "__main__":
    test_report()
