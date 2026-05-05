#!/usr/bin/env python3
"""
Analyze OpenAPI structure for duplicates and issues
"""

import urllib.request
import json

def analyze_openapi():
    """Analyze OpenAPI schema structure"""
    print("🔍 ANALYZING OPENAPI STRUCTURE")
    print("=" * 50)
    
    try:
        # Get OpenAPI JSON
        url = "http://localhost:8001/openapi.json"
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read().decode('utf-8'))
        
        paths = data.get('paths', {})
        print(f"📊 Total paths: {len(paths)}")
        
        # List all paths to identify duplicates
        print(f"\n📋 ALL PATHS:")
        all_paths = list(paths.keys())
        
        # Sort paths for better visibility
        all_paths.sort()
        
        for i, path in enumerate(all_paths, 1):
            methods = list(paths[path].keys())
            print(f"   {i:3d}. {path:<40} -> {', '.join(methods.upper() for method in methods)}")
        
        # Check for exact duplicates
        print(f"\n🔍 DUPLICATE CHECK:")
        seen_paths = set()
        duplicates = []
        
        for path in all_paths:
            if path in seen_paths:
                duplicates.append(path)
            seen_paths.add(path)
        
        if duplicates:
            print(f"   ❌ Found {len(duplicates)} duplicate paths:")
            for path in duplicates:
                print(f"      {path}")
        else:
            print("   ✅ No duplicate paths found")
        
        # Check for similar paths (potential duplicates)
        print(f"\n🔍 SIMILAR PATHS CHECK:")
        path_groups = {}
        
        for path in all_paths:
            # Remove parameters and get base
            base = path.split('{')[0].rstrip('/')
            if base not in path_groups:
                path_groups[base] = []
            path_groups[base].append(path)
        
        similar_groups = {base: paths for base, paths in path_groups.items() if len(paths) > 1}
        
        if similar_groups:
            print(f"   ⚠️  Found {len(similar_groups)} similar path groups:")
            for base, similar_paths in similar_groups.items():
                print(f"      Base: {base}")
                for path in similar_paths:
                    print(f"         {path}")
        else:
            print("   ✅ No similar path groups found")
        
        # Check router inclusion in main.py
        print(f"\n🔍 ROUTER ANALYSIS:")
        print("   Checking if routers are included multiple times...")
        
        # Look for patterns that might cause duplication
        duplicate_patterns = []
        for path in all_paths:
            if path.count('/') > 3:  # Deeply nested paths
                duplicate_patterns.append(path)
        
        if duplicate_patterns:
            print(f"   ⚠️  {len(duplicate_patterns)} deeply nested paths (potential inclusion issues):")
            for path in duplicate_patterns[:10]:  # Show first 10
                print(f"      {path}")
        else:
            print("   ✅ Path structure looks normal")
        
        return duplicates or similar_groups
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    analyze_openapi()
