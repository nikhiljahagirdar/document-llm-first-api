#!/usr/bin/env python3
"""
Check all router files for duplicate routes with trailing slashes
"""

import os
import re

def check_router_files():
    """Check all router files for duplicate routes"""
    print("🔍 CHECKING ALL ROUTER FILES FOR DUPLICATES")
    print("=" * 60)
    
    router_dir = "app/routers"
    router_files = [f for f in os.listdir(router_dir) if f.endswith('.py') and f != '__init__.py']
    
    total_duplicates = 0
    
    for router_file in sorted(router_files):
        file_path = os.path.join(router_dir, router_file)
        print(f"\n📁 Checking: {router_file}")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Find all router decorators
            router_pattern = r'@router\.(get|post|put|patch|delete)\s*\(\s*"([^"]*?)"'
            matches = re.findall(router_pattern, content)
            
            if matches:
                # Group by path (without trailing slash)
                paths = {}
                for method, path in matches:
                    clean_path = path.rstrip('/')
                    if clean_path not in paths:
                        paths[clean_path] = []
                    paths[clean_path].append((method, path))
                
                # Check for duplicates
                duplicates = []
                for clean_path, route_list in paths.items():
                    if len(route_list) > 1:
                        duplicates.append((clean_path, route_list))
                
                if duplicates:
                    total_duplicates += len(duplicates)
                    print(f"   ❌ Found {len(duplicates)} duplicate paths:")
                    for clean_path, route_list in duplicates:
                        print(f"      {clean_path}:")
                        for method, original_path in route_list:
                            print(f"        {method.upper()} {original_path}")
                else:
                    print(f"   ✅ No duplicates found ({len(matches)} routes)")
            else:
                print(f"   ℹ️  No router decorators found")
                
        except Exception as e:
            print(f"   ❌ Error reading file: {e}")
    
    print(f"\n📊 SUMMARY:")
    print(f"   Total router files checked: {len(router_files)}")
    print(f"   Total duplicate routes found: {total_duplicates}")
    
    if total_duplicates == 0:
        print("   ✅ All router files are clean!")
    else:
        print(f"   ⚠️  Need to fix {total_duplicates} duplicate routes")
    
    return total_duplicates == 0

if __name__ == "__main__":
    check_router_files()
