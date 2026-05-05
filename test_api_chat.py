import requests
import json
import uuid

BASE_URL = "http://localhost:8001/api"

def test_chat():
    # 1. Register a new user
    email = f"demo_{uuid.uuid4().hex[:6]}@example.com"
    password = "SecurePass123!"
    print(f"Registering user: {email}...")
    
    reg_data = {
        "email": email,
        "password": password,
        "first_name": "Demo",
        "last_name": "User"
    }
    
    reg_res = requests.post(f"{BASE_URL}/users/register", json=reg_data)
    if reg_res.status_code not in [200, 201]:
        print(f"Registration failed: {reg_res.text}")
        # Try login directly in case it already exists (unlikely with UUID)
    
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
    
    token_data = response.json()
    token = token_data["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("Login successful!")

    # 3. We need a document. Since we just registered, we have none.
    # But wait, I seeded the Neon DB. If the API is using Neon, I should see documents.
    # If the API is using local, I should see none.
    
    print("Fetching documents...")
    docs_res = requests.get(f"{BASE_URL}/documents", headers=headers)
    docs = docs_res.json()
    
    if not docs:
        print("No documents found. Seeding a document via API if possible (or checking Neon)...")
        # I'll just check if any document exists in the DB for THIS user
        # Actually, let's just try the RAG agent which doesn't need a specific doc if we use /rag-agent
        
    # Let's try to find ANY document in the system if superadmin?
    # No, I'll just use the /llm/rag-agent endpoint for a general query.
    
    print("\n--- GENERAL RAG AGENT REQUEST ---")
    rag_payload = {
        "user_input": "What are the standard terms for service agreements?"
    }
    print(f"Request: {json.dumps(rag_payload, indent=2)}")
    
    rag_res = requests.post(f"{BASE_URL}/llm/rag-agent", headers=headers, json=rag_payload)
    
    if rag_res.status_code == 200:
        print("\n--- API RESPONSE (RAG AGENT) ---")
        print(json.dumps(rag_res.json(), indent=2))
    else:
        print(f"\nRAG Agent failed ({rag_res.status_code}): {rag_res.text}")

if __name__ == "__main__":
    test_chat()
