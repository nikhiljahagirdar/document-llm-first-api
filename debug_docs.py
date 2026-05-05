#!/usr/bin/env python3
"""
Debug OpenAPI docs issue
"""

import urllib.request
import json

def debug_docs():
    """Debug why docs aren't loading properly"""
    print("🔍 Debugging OpenAPI/Swagger docs...")
    
    # Check OpenAPI JSON
    try:
        url = "http://localhost:8001/openapi.json"
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read().decode('utf-8'))
            
        print(f"✅ OpenAPI JSON: {response.status}")
        print(f"   Title: {data.get('info', {}).get('title', 'N/A')}")
        print(f"   Version: {data.get('info', {}).get('version', 'N/A')}")
        print(f"   Paths: {len(data.get('paths', {}))} endpoints")
        print(f"   Components: {len(data.get('components', {}).get('schemas', {}))} schemas")
        
        # Check for security schemes
        if 'components' in data and 'securitySchemes' in data['components']:
            print(f"   Security Schemes: {len(data['components']['securitySchemes'])}")
        else:
            print("   ❌ Security Schemes: Missing")
            
    except Exception as e:
        print(f"❌ OpenAPI JSON failed: {e}")
    
    # Check Swagger UI HTML
    try:
        url = "http://localhost:8001/docs"
        with urllib.request.urlopen(url) as response:
            html = response.read().decode('utf-8')
            
        print(f"✅ Swagger UI: {response.status}")
        print(f"   HTML length: {len(html)} characters")
        
        # Check for key elements
        checks = {
            'swagger-ui.css': 'swagger-ui.css' in html,
            'swagger-ui-bundle.js': 'swagger-ui-bundle.js' in html,
            'swagger-ui-standalone-preset.js': 'swagger-ui-standalone-preset.js' in html,
            'SwaggerUI object': 'SwaggerUIBundle' in html,
            'openapi.json reference': '/openapi.json' in html
        }
        
        for check, passed in checks.items():
            status = "✅" if passed else "❌"
            print(f"   {status} {check}")
            
    except Exception as e:
        print(f"❌ Swagger UI failed: {e}")
    
    # Check ReDoc HTML
    try:
        url = "http://localhost:8001/redoc"
        with urllib.request.urlopen(url) as response:
            html = response.read().decode('utf-8')
            
        print(f"✅ ReDoc: {response.status}")
        print(f"   HTML length: {len(html)} characters")
        
        # Check for key elements
        checks = {
            'redoc.standalone.js': 'redoc.standalone.js' in html,
            'Redoc init': 'Redoc.init' in html,
            'openapi.json reference': '/openapi.json' in html
        }
        
        for check, passed in checks.items():
            status = "✅" if passed else "❌"
            print(f"   {status} {check}")
            
    except Exception as e:
        print(f"❌ ReDoc failed: {e}")
    
    # Test a simple API endpoint
    try:
        url = "http://localhost:8001/"
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read().decode('utf-8'))
            
        print(f"✅ Root API: {response.status}")
        print(f"   Message: {data.get('message', 'N/A')}")
        print(f"   Version: {data.get('version', 'N/A')}")
        
    except Exception as e:
        print(f"❌ Root API failed: {e}")

if __name__ == "__main__":
    debug_docs()
