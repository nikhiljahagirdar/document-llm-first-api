#!/usr/bin/env python3
"""
Simple check for duplicate endpoints
"""

import urllib.request
import json

def check_duplicates():
    """Check for duplicate endpoints"""
    print("🔍 CHECKING FOR DUPLICATE ENDPOINTS")
    print("=" * 50)
    
    try:
        url = "http://localhost:8001/openapi.json"
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read().decode('utf-8'))
        
        paths = data.get('paths', {})
        print(f"📊 Total paths: {len(paths)}")
        
        # Check for trailing slash duplicates
        base_paths = {}
        for path in paths.keys():
            base = path.rstrip('/')
            if base not in base_paths:
                base_paths[base] = []
            base_paths[base].append(path)
        
        duplicates = {base: paths for base, paths in base_paths.items() if len(paths) > 1}
        
        if duplicates:
            print(f"❌ Found {len(duplicates)} duplicate groups:")
            for base, dup_paths in list(duplicates.items())[:5]:  # Show first 5
                print(f"   {base}:")
                for path in dup_paths:
                    print(f"      {path}")
        else:
            print("✅ No duplicate paths found")
        
        # Show sample endpoints
        print(f"\n📍 Sample endpoints:")
        sample_paths = list(paths.keys())[:10]
        for path in sample_paths:
            methods = list(paths[path].keys())
            print(f"   {path:<40} -> {', '.join(methods.upper() for method in methods)}")
        
        return len(duplicates) == 0
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    check_duplicates()
