#!/usr/bin/env python3
"""
Debug OpenAPI structure to understand the issue
"""

import urllib.request
import json

def debug_openapi_structure():
    """Debug the OpenAPI structure to find the issue"""
    print("🔍 DEBUGGING OPENAPI STRUCTURE")
    print("=" * 50)
    
    try:
        # Get OpenAPI JSON
        url = "http://localhost:8001/openapi.json"
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read().decode('utf-8'))
        
        print(f"📊 Top-level keys: {list(data.keys())}")
        
        paths = data.get('paths', {})
        print(f"📊 Paths type: {type(paths)}")
        print(f"📊 Number of paths: {len(paths) if isinstance(paths, dict) else 'Not a dict'}")
        
        if isinstance(paths, dict):
            print(f"📊 Sample path keys: {list(paths.keys())[:5]}")
            
            # Check first few paths
            for i, (path, path_data) in enumerate(list(paths.items())[:5]):
                print(f"\n   Path {i+1}: {path}")
                print(f"   Type: {type(path_data)}")
                
                if isinstance(path_data, dict):
                    methods = list(path_data.keys())
                    print(f"   Methods: {methods}")
                elif isinstance(path_data, list):
                    print(f"   ❌ Path data is a list (should be dict)!")
                    print(f"   List items: {len(path_data)}")
                    if path_data:
                        print(f"   First item type: {type(path_data[0])}")
                        if isinstance(path_data[0], dict):
                            print(f"   First item keys: {list(path_data[0].keys())[:5]}")
                else:
                    print(f"   ❌ Unexpected type: {type(path_data)}")
        
        # Check for structure issues
        print(f"\n🔍 STRUCTURE ANALYSIS:")
        problem_paths = []
        
        for path, path_data in paths.items():
            if not isinstance(path_data, dict):
                problem_paths.append((path, type(path_data)))
        
        if problem_paths:
            print(f"   ❌ Found {len(problem_paths)} problematic paths:")
            for path, data_type in problem_paths[:10]:
                print(f"      {path} -> {data_type}")
        else:
            print("   ✅ All paths have correct structure")
        
        return len(problem_paths) > 0
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    debug_openapi_structure()
