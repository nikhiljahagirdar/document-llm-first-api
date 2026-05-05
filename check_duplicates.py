#!/usr/bin/env python3
"""
Check for duplicate endpoints in OpenAPI schema
"""

import urllib.request
import json
from collections import defaultdict

def check_duplicate_endpoints():
    """Analyze OpenAPI schema for duplicate endpoints"""
    print("🔍 CHECKING FOR DUPLICATE ENDPOINTS")
    print("=" * 50)
    
    try:
        # Get OpenAPI JSON
        url = "http://localhost:8001/openapi.json"
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read().decode('utf-8'))
        
        paths = data.get('paths', {})
        print(f"📊 Total endpoints found: {len(paths)}")
        
        # Analyze endpoints by path
        path_analysis = defaultdict(list)
        for path, methods in paths.items():
            for method in methods.keys():
                path_analysis[path].append(method.upper())
        
        # Group by base path (remove parameters)
        base_paths = defaultdict(list)
        for path in paths.keys():
            # Extract base path (before first parameter)
            base = path.split('{')[0].rstrip('/')
            if not base:
                base = '/'
            base_paths[base].append(path)
        
        print(f"📂 Base paths: {len(base_paths)}")
        
        # Check for potential duplicates
        duplicates_found = False
        for base_path, full_paths in base_paths.items():
            if len(full_paths) > 1:
                duplicates_found = True
                print(f"\n⚠️  DUPLICATE BASE PATH: {base_path}")
                for path in sorted(full_paths):
                    methods = list(paths[path].keys())
                    print(f"   {path} -> {', '.join(methods.upper() for method in methods)}")
        
        if not duplicates_found:
            print("\n✅ No duplicate base paths found")
        
        # Check for exact duplicates
        exact_duplicates = []
        seen_paths = set()
        for path in paths.keys():
            if path in seen_paths:
                exact_duplicates.append(path)
            seen_paths.add(path)
        
        if exact_duplicates:
            print(f"\n❌ EXACT DUPLICATES: {len(exact_duplicates)}")
            for path in exact_duplicates:
                print(f"   {path}")
        else:
            print("\n✅ No exact duplicate paths found")
        
        # Show endpoint breakdown by router/tag
        print(f"\n📋 ENDPOINT BREAKDOWN:")
        tag_counts = defaultdict(int)
        for path, methods in paths.items():
            for method, details in methods.items():
                tags = details.get('tags', ['unknown'])
                for tag in tags:
                    tag_counts[tag] += 1
        
        for tag, count in sorted(tag_counts.items()):
            print(f"   {tag}: {count} endpoints")
        
        # Show sample of endpoints by category
        print(f"\n📍 SAMPLE ENDPOINTS BY CATEGORY:")
        categories = {
            'Users': [],
            'Documents': [],
            'Auth': [],
            'Health': [],
            'Other': []
        }
        
        for path, methods in paths.items():
            categorized = False
            for method in methods.keys():
                details = methods[method]
                tags = details.get('tags', [])
                
                if any('user' in tag.lower() for tag in tags):
                    categories['Users'].append(f"{path} [{method.upper()}]")
                    categorized = True
                elif any('doc' in tag.lower() for tag in tags):
                    categories['Documents'].append(f"{path} [{method.upper()}]")
                    categorized = True
                elif any('auth' in tag.lower() or 'token' in tag.lower() for tag in tags):
                    categories['Auth'].append(f"{path} [{method.upper()}]")
                    categorized = True
                elif 'health' in path.lower() or 'metrics' in path.lower():
                    categories['Health'].append(f"{path} [{method.upper()}]")
                    categorized = True
            
            if not categorized:
                for method in methods.keys():
                    categories['Other'].append(f"{path} [{method.upper()}]")
        
        for category, endpoints in categories.items():
            if endpoints:
                print(f"\n   {category} ({len(endpoints)}):")
                for endpoint in endpoints[:5]:  # Show first 5
                    print(f"      {endpoint}")
                if len(endpoints) > 5:
                    print(f"      ... and {len(endpoints) - 5} more")
        
        return duplicates_found
        
    except Exception as e:
        print(f"❌ Error analyzing endpoints: {e}")
        return False

if __name__ == "__main__":
    check_duplicate_endpoints()
