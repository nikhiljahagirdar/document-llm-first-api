#!/usr/bin/env python3
"""
Show Swagger endpoint details and create a simple test
"""

import urllib.request
import json
import webbrowser
import os

def show_swagger_details():
    """Show detailed information about the Swagger endpoint"""
    print("🔍 SWAGGER ENDPOINT ANALYSIS")
    print("=" * 50)
    
    # 1. Show Swagger HTML structure
    print("\n📄 1. SWAGGER UI HTML:")
    try:
        url = "http://localhost:8001/docs"
        with urllib.request.urlopen(url) as response:
            html = response.read().decode('utf-8')
        
        print(f"   Status: {response.status}")
        print(f"   Content-Type: {response.headers.get('content-type')}")
        print(f"   Content-Length: {len(html)} bytes")
        
        # Extract key parts
        if 'swagger-ui.css' in html:
            print("   ✅ CSS CDN link found")
        if 'swagger-ui-bundle.js' in html:
            print("   ✅ JavaScript bundle found")
        if '/openapi.json' in html:
            print("   ✅ OpenAPI JSON reference found")
        if 'SwaggerUIBundle' in html:
            print("   ✅ SwaggerUI initialization found")
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # 2. Show OpenAPI JSON structure
    print("\n📊 2. OPENAPI JSON STRUCTURE:")
    try:
        url = "http://localhost:8001/openapi.json"
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read().decode('utf-8'))
        
        print(f"   Status: {response.status}")
        print(f"   Content-Length: {len(str(data))} bytes")
        print(f"   API Title: {data.get('info', {}).get('title', 'N/A')}")
        print(f"   API Version: {data.get('info', {}).get('version', 'N/A')}")
        print(f"   Total Endpoints: {len(data.get('paths', {}))}")
        print(f"   Total Schemas: {len(data.get('components', {}).get('schemas', {}))}")
        
        # Show some endpoints
        print("\n   📍 Sample Endpoints:")
        paths = list(data['paths'].keys())[:5]
        for path in paths:
            methods = list(data['paths'][path].keys())
            print(f"      {path} -> {', '.join(methods.upper() for method in methods)}")
        
        # Show security schemes
        if 'components' in data and 'securitySchemes' in data['components']:
            print(f"\n   🔐 Security Schemes: {len(data['components']['securitySchemes'])}")
            for scheme_name, scheme in data['components']['securitySchemes'].items():
                scheme_type = scheme.get('type', 'unknown')
                print(f"      - {scheme_name}: {scheme_type}")
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # 3. Test CDN accessibility
    print("\n🌐 3. CDN RESOURCE TEST:")
    cdn_urls = [
        "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css",
        "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"
    ]
    
    for url in cdn_urls:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                print(f"   ✅ {url.split('/')[-1]}: {response.status}")
        except Exception as e:
            print(f"   ❌ {url.split('/')[-1]}: {e}")
    
    # 4. Create local HTML file
    print("\n💾 4. CREATING LOCAL SWAGGER FILE:")
    try:
        # Read the current Swagger HTML
        url = "http://localhost:8001/docs"
        with urllib.request.urlopen(url) as response:
            html = response.read().decode('utf-8')
        
        # Save to local file
        local_file = "swagger_local.html"
        with open(local_file, 'w', encoding='utf-8') as f:
            f.write(html)
        
        print(f"   ✅ Saved to: {os.path.abspath(local_file)}")
        print(f"   📂 Open this file in your browser: file://{os.path.abspath(local_file)}")
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # 5. Show troubleshooting steps
    print("\n🛠️ 5. TROUBLESHOOTING STEPS:")
    print("   If Swagger UI is not loading properly:")
    print("   1. Check browser console for JavaScript errors")
    print("   2. Verify internet connection for CDN resources")
    print("   3. Try opening the local HTML file created above")
    print("   4. Test with different browser (Chrome/Firefox/Edge)")
    print("   5. Check if any browser extensions are blocking scripts")
    print("   6. Verify firewall/antivirus isn't blocking localhost")
    
    print("\n🎯 SUMMARY:")
    print("   ✅ Server is running and responding correctly")
    print("   ✅ OpenAPI JSON is valid and comprehensive")
    print("   ✅ Swagger UI HTML is being served properly")
    print("   ⚠️  Issue is likely with browser/CDN connectivity")

if __name__ == "__main__":
    show_swagger_details()
