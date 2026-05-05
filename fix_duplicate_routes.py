#!/usr/bin/env python3
"""
Fix all duplicate routes by removing trailing slash versions
"""

import os
import re
import shutil

def fix_duplicate_routes():
    """Fix duplicate routes in all router files"""
    print("🔧 FIXING DUPLICATE ROUTES")
    print("=" * 50)
    
    router_dir = "app/routers"
    router_files = [f for f in os.listdir(router_dir) if f.endswith('.py') and f != '__init__.py']
    
    total_fixes = 0
    
    for router_file in sorted(router_files):
        file_path = os.path.join(router_dir, router_file)
        print(f"\n📁 Processing: {router_file}")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            original_content = content
            
            # Find and fix duplicate routes
            # Pattern to find route decorators with trailing slashes
            router_pattern = r'(@router\.(get|post|put|patch|delete)\s*\(\s*"([^"]*?/)"\s*,[^)]*\))\s*\n((?:async\s+)?def\s+\w+\s*\([^)]*\):)'
            
            matches = re.findall(router_pattern, content)
            
            if matches:
                print(f"   Found {len(matches)} routes with trailing slashes")
                
                # Remove the duplicate routes (with trailing slashes)
                fixed_content = re.sub(
                    router_pattern,
                    '',
                    content,
                    flags=re.MULTILINE
                )
                
                # Clean up extra blank lines
                fixed_content = re.sub(r'\n\s*\n\s*\n', '\n\n', fixed_content)
                
                if fixed_content != original_content:
                    # Create backup
                    backup_path = file_path + '.backup'
                    shutil.copy2(file_path, backup_path)
                    
                    # Write fixed content
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(fixed_content)
                    
                    print(f"   ✅ Fixed {len(matches)} routes, backup created")
                    total_fixes += len(matches)
                else:
                    print(f"   ℹ️  No changes needed")
            else:
                print(f"   ✅ No duplicate routes found")
                
        except Exception as e:
            print(f"   ❌ Error processing file: {e}")
    
    print(f"\n📊 SUMMARY:")
    print(f"   Total router files processed: {len(router_files)}")
    print(f"   Total duplicate routes fixed: {total_fixes}")
    
    return total_fixes

if __name__ == "__main__":
    fix_duplicate_routes()
