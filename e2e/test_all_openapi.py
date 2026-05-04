import pytest
import json
import os
import uuid
from typing import Generator, Dict, Any
from playwright.sync_api import Playwright, APIRequestContext, expect
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "http://127.0.0.1:8001"

@pytest.fixture(scope="session")
def api_request_context(
    playwright: Playwright,
) -> Generator[APIRequestContext, None, None]:
    request_context = playwright.request.new_context(base_url=BASE_URL, timeout=120000)
    yield request_context
    request_context.dispose()

@pytest.fixture(scope="session")
def auth_token(api_request_context: APIRequestContext) -> str:
    response = api_request_context.post(
        "/api/users/login",
        form={
            "username": "admin@demo.com",
            "password": "admin123",
        }
    )
    if not response.ok:
        pytest.fail(f"Login failed: {response.status} {response.text()}")
    return response.json()["access_token"]

def load_openapi():
    if os.path.exists("openapi.json"):
        with open("openapi.json", "r") as f:
            return json.load(f)
    if os.path.exists("e2e/openapi.json"):
        with open("e2e/openapi.json", "r") as f:
            return json.load(f)
    return {"paths": {}}

openapi = load_openapi()
paths = openapi.get("paths", {})

def generate_sample_data(schema_ref: str, components: Dict[str, Any]) -> Dict[str, Any]:
    if not schema_ref:
        return {}
    schema_name = schema_ref.split("/")[-1]
    schema = components.get("schemas", {}).get(schema_name, {})
    properties = schema.get("properties", {})
    data = {}
    for prop_name, prop_info in properties.items():
        if "default" in prop_info:
            data[prop_name] = prop_info["default"]
        elif prop_info.get("type") == "string":
            if prop_info.get("format") == "uuid":
                data[prop_name] = str(uuid.uuid4())
            elif prop_name == "email":
                data[prop_name] = f"test_{uuid.uuid4().hex[:8]}@example.com"
            else:
                data[prop_name] = f"test_{prop_name}_{uuid.uuid4().hex[:4]}"
        elif prop_info.get("type") == "integer":
            data[prop_name] = 1
        elif prop_info.get("type") == "number":
            data[prop_name] = 1.0
        elif prop_info.get("type") == "boolean":
            data[prop_name] = True
    return data

@pytest.mark.parametrize("path,method", [
    (path, method) 
    for path, methods in paths.items() 
    for method in methods.keys()
    if method in ["get", "post", "patch", "delete"]
    and "{document_id}" not in path 
    and "{report_id}" not in path
    and "{template_id}" not in path
    and "{user_id}" not in path
    and "{tenant_id}" not in path
    and "{vertical_id}" not in path
    and "{service_id}" not in path
    and "{category_id}" not in path
    and "{subcategory_id}" not in path
    and "{notification_id}" not in path
    and "{plan_id}" not in path
    and "/auth/google" not in path 
    and "/webhooks" not in path 
])
def test_openapi_endpoints(api_request_context: APIRequestContext, auth_token: str, path: str, method: str):
    headers = {"Authorization": f"Bearer {auth_token}"}
    full_path = f"/api{path}" if not path.startswith("/api") else path
    
    # Replace path parameters with a generic UUID
    import re
    full_path = re.sub(r"\{.*?\}", "123e4567-e89b-12d3-a456-426614174000", full_path)
    
    method_info = paths[path][method]
    json_body = None
    
    if method in ["post", "patch"] and "requestBody" in method_info:
        content = method_info["requestBody"].get("content", {})
        if "application/json" in content:
            schema_ref = content["application/json"].get("schema", {}).get("$ref")
            json_body = generate_sample_data(schema_ref, openapi.get("components", {}))

    response = None
    if method == "get":
        response = api_request_context.get(full_path, headers=headers)
    elif method == "post":
        if "upload" in path: return
        response = api_request_context.post(full_path, headers=headers, data=json_body)
    elif method == "patch":
        response = api_request_context.patch(full_path, headers=headers, data=json_body)
    elif method == "delete":
        response = api_request_context.delete(full_path, headers=headers)

    if response:
        assert response.status < 500, f"Endpoint {method.upper()} {full_path} failed with {response.status}: {response.text()}"

def test_document_full_flow(api_request_context: APIRequestContext, auth_token: str):
    headers = {"Authorization": f"Bearer {auth_token}"}
    
    file_path = "docs/ac.pdf"
    if not os.path.exists(file_path):
        os.makedirs("docs", exist_ok=True)
        with open(file_path, "wb") as f:
            f.write(b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>\nendobj\n4 0 obj\n<< /Length 20 >>\nstream\nBT /F1 12 Tf ET\nendstream\nendobj\nxref\n0 5\n0000000000 65535 f\n0000000010 00000 n\n0000000060 00000 n\n0000000115 00000 n\n0000000215 00000 n\ntrailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n285\n%%EOF")
            
    with open(file_path, "rb") as f:
        file_content = f.read()
        
    doc_name = f"test_{uuid.uuid4().hex[:8]}.pdf"
    upload_res = api_request_context.post(
        "/api/documents/upload",
        headers=headers,
        multipart={
            "file": {
                "name": doc_name,
                "mimeType": "application/pdf",
                "buffer": file_content,
            }
        }
    )
    assert upload_res.status == 202
    doc_id = upload_res.json()["document_id"]
    
    get_res = api_request_context.get(f"/api/documents/{doc_id}", headers=headers)
    assert get_res.ok
    
    list_res = api_request_context.get("/api/documents", headers=headers)
    assert list_res.ok
    
    content_res = api_request_context.get(f"/api/documents/{doc_id}/content", headers=headers)
    assert content_res.status in [200, 404]
