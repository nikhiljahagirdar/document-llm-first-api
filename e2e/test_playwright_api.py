import pytest
from playwright.sync_api import Playwright, APIRequestContext
from typing import Generator
import os
import json
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "http://127.0.0.1:8001"

@pytest.fixture(scope="session")
def api_request_context(
    playwright: Playwright,
) -> Generator[APIRequestContext, None, None]:
    request_context = playwright.request.new_context(base_url=BASE_URL, timeout=300000)
    yield request_context
    request_context.dispose()

def get_token(api_request_context: APIRequestContext):
    response = api_request_context.post(
        "/api/users/login",
        form={
            "username": "admin@demo.com",
            "password": "admin123",
        }
    )
    if not response.ok:
        print(f"Login failed: {response.status} {response.text()}")
    assert response.ok
    return response.json()["access_token"]

def test_health_check(api_request_context: APIRequestContext):
    response = api_request_context.get("/")
    assert response.ok
    assert response.json() == {"message": "Welcome to the Document Management System API!"}

def test_upload_and_status_flow(api_request_context: APIRequestContext):
    token = get_token(api_request_context)
    headers = {"Authorization": f"Bearer {token}"}
    
    # 1. Upload a small test file
    file_path = "docs/ac.pdf"
    if not os.path.exists(file_path):
        # Create a dummy file if it doesn't exist
        with open(file_path, "wb") as f:
            f.write(b"%PDF-1.4\n1 0 obj\n<< /Title (Test) >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF")
            
    with open(file_path, "rb") as f:
        file_content = f.read()
        
    import uuid
    random_filename = f"test_{uuid.uuid4().hex[:8]}.pdf"
    
    upload_response = api_request_context.post(
        "/api/documents/upload",
        headers=headers,
        multipart={
            "file": {
                "name": random_filename,
                "mimeType": "application/pdf",
                "buffer": file_content,
            }
        }
    )
    
    assert upload_response.status == 202
    doc_data = upload_response.json()
    doc_id = doc_data["document_id"]
    assert doc_id is not None
    
    # 2. Poll for status and verify it changes
    # We expect: processing -> extracting -> (processed or failed)
    import time
    max_retries = 150
    found_statuses = set()
    
    for _ in range(max_retries):
        status_res = api_request_context.get(f"/api/documents/{doc_id}", headers=headers)
        assert status_res.ok
        status_data = status_res.json()
        current_status = status_data["status"]
        found_statuses.add(current_status)
        
        if current_status in ["processed", "failed"]:
            break
        time.sleep(2)
    
    print(f"Document {doc_id} reached final status: {current_status}")
    print(f"History of statuses seen: {found_statuses}")
    
    # Verify that we saw more than just 'processing'
    assert len(found_statuses) > 1, f"Status never changed from {list(found_statuses)[0]}"
    
    # 3. Check document_statuseses table indirectly via history or logs if available
    # Or just verify the final state
    assert current_status in ["processed", "failed"]
