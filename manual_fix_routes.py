#!/usr/bin/env python3
"""
Manually fix specific known duplicate routes
"""

import os
import shutil

def fix_specific_duplicates():
    """Fix specific duplicate routes we identified"""
    print("🔧 MANUALLY FIXING SPECIFIC DUPLICATES")
    print("=" * 50)
    
    fixes = [
        # (file_path, search_pattern, replacement)
        ("app/routers/categories.py", r'@router\.get\(\s*"/"\s*,.*?\)\s*\nasync def.*?:\s*return.*?\n', ''),
        ("app/routers/documents.py", r'@router\.post\(\s*"/upload/"\s*,.*?\)\s*\nasync def.*?:.*?\n', ''),
        ("app/routers/documents.py", r'@router\.post\(\s*"/manual/"\s*,.*?\)\s*\nasync def.*?:.*?\n', ''),
        ("app/routers/documents.py", r'@router\.post\(\s*"/from-template/"\s*,.*?\)\s*\nasync def.*?:.*?\n', ''),
        ("app/routers/documents.py", r'@router\.get\(\s*"/\{document_id\}/"\s*,.*?\)\s*\nasync def.*?:.*?\n', ''),
        ("app/routers/documents.py", r'@router\.delete\(\s*"/\{document_id\}/"\s*,.*?\)\s*\nasync def.*?:.*?\n', ''),
        ("app/routers/documents.py", r'@router\.get\(\s*"/\{document_id\}/content/"\s*,.*?\)\s*\nasync def.*?:.*?\n', ''),
        ("app/routers/documents.py", r'@router\.patch\(\s*"/\{document_id\}/content/"\s*,.*?\)\s*\nasync def.*?:.*?\n', ''),
        ("app/routers/documents.py", r'@router\.post\(\s*"/\{document_id\}/reprocess/"\s*,.*?\)\s*\nasync def.*?:.*?\n', ''),
        ("app/routers/folders.py", r'@router\.get\(\s*"/"\s*,.*?\)\s*\nasync def.*?:.*?\n', ''),
        ("app/routers/folders.py", r'@router\.post\(\s*"/"\s*,.*?\)\s*\nasync def.*?:.*?\n', ''),
        ("app/routers/folders.py", r'@router\.get\(\s*"/\{folder_id\}/"\s*,.*?\)\s*\nasync def.*?:.*?\n', ''),
        ("app/routers/folders.py", r'@router\.patch\(\s*"/\{folder_id\}/"\s*,.*?\)\s*\nasync def.*?:.*?\n', ''),
        ("app/routers/folders.py", r'@router\.delete\(\s*"/\{folder_id\}/"\s*,.*?\)\s*\nasync def.*?:.*?\n', ''),
        ("app/routers/industries.py", r'@router\.get\(\s*"/"\s*,.*?\)\s*\nasync def.*?:.*?\n', ''),
        ("app/routers/industries.py", r'@router\.post\(\s*"/"\s*,.*?\)\s*\nasync def.*?:.*?\n', ''),
        ("app/routers/industries.py", r'@router\.patch\(\s*"/\{industry_id\}/"\s*,.*?\)\s*\nasync def.*?:.*?\n', ''),
        ("app/routers/industries.py", r'@router\.delete\(\s*"/\{industry_id\}/"\s*,.*?\)\s*\nasync def.*?:.*?\n', ''),
        ("app/routers/llm.py", r'@router\.post\(\s*"/detect-industry/"\s*,.*?\)\s*\nasync def.*?:.*?\n', ''),
        ("app/routers/llm.py", r'@router\.post\(\s*"/generate/"\s*,.*?\)\s*\nasync def.*?:.*?\n', ''),
        ("app/routers/llm.py", r'@router\.post\(\s*"/analyze-multimodal/"\s*,.*?\)\s*\nasync def.*?:.*?\n', ''),
        ("app/routers/llm.py", r'@router\.get\(\s*"/documents/\{document_id\}/suggestions/"\s*,.*?\)\s*\nasync def.*?:.*?\n', ''),
        ("app/routers/llm.py", r'@router\.post\(\s*"/chat/summarize/"\s*,.*?\)\s*\nasync def.*?:.*?\n', ''),
        ("app/routers/llm.py", r'@router\.post\(\s*"/chat/document/"\s*,.*?\)\s*\nasync def.*?:.*?\n', ''),
        ("app/routers/llm.py", r'@router\.post\(\s*"/rag-agent/"\s*,.*?\)\s*\nasync def.*?:.*?\n', ''),
        ("app/routers/logs.py", r'@router\.post\(\s*"/usage/"\s*,.*?\)\s*\nasync def.*?:.*?\n', ''),
        ("app/routers/logs.py", r'@router\.post\(\s*"/audit/"\s*,.*?\)\s*\nasync def.*?:.*?\n', ''),
        ("app/routers/notifications.py", r'@router\.get\(\s*"/"\s*,.*?\)\s*\nasync def.*?:.*?\n', ''),
        ("app/routers/notifications.py", r'@router\.post\(\s*"/\{notification_id\}/read/"\s*,.*?\)\s*\nasync def.*?:.*?\n', ''),
        ("app/routers/notifications.py", r'@router\.post\(\s*"/read-all/"\s*,.*?\)\s*\nasync def.*?:.*?\n', ''),
        ("app/routers/notifications.py", r'@router\.post\(\s*"/test-notify/"\s*,.*?\)\s*\nasync def.*?:.*?\n', ''),
        ("app/routers/notifications.py", r'@router\.delete\(\s*"/\{notification_id\}/"\s*,.*?\)\s*\nasync def.*?:.*?\n', ''),
        ("app/routers/plans.py", r'@router\.get\(\s*"/"\s*,.*?\)\s*\nasync def.*?:.*?\n', ''),
        ("app/routers/plans.py", r'@router\.post\(\s*"/"\s*,.*?\)\s*\nasync def.*?:.*?\n', ''),
        ("app/routers/plans.py", r'@router\.put\(\s*"/\{plan_id\}/"\s*,.*?\)\s*\nasync def.*?:.*?\n', ''),
        ("app/routers/plans.py", r'@router\.delete\(\s*"/\{plan_id\}/"\s*,.*?\)\s*\nasync def.*?:.*?\n', ''),
        ("app/routers/reports.py", r'@router\.get\(\s*"/"\s*,.*?\)\s*\nasync def.*?:.*?\n', ''),
        ("app/routers/reports.py", r'@router\.post\(\s*"/analyze/"\s*,.*?\)\s*\nasync def.*?:.*?\n', ''),
        ("app/routers/reports.py", r'@router\.get\(\s*"/\{report_id\}/"\s*,.*?\)\s*\nasync def.*?:.*?\n', ''),
        ("app/routers/reports.py", r'@router\.get\(\s*"/\{report_id\}/versions/"\s*,.*?\)\s*\nasync def.*?:.*?\n', ''),
        ("app/routers/roles.py", r'@router\.get\(\s*"/"\s*,.*?\)\s*\nasync def.*?:.*?\n', ''),
        ("app/routers/roles.py", r'@router\.post\(\s*"/"\s*,.*?\)\s*\nasync def.*?:.*?\n', ''),
        ("app/routers/roles.py", r'@router\.patch\(\s*"/\{role_id\}/"\s*,.*?\)\s*\nasync def.*?:.*?\n', ''),
        ("app/routers/roles.py", r'@router\.delete\(\s*"/\{role_id\}/"\s*,.*?\)\s*\nasync def.*?:.*?\n', ''),
        ("app/routers/subcategories.py", r'@router\.get\(\s*"/"\s*,.*?\)\s*\nasync def.*?:.*?\n', ''),
        ("app/routers/subcategories.py", r'@router\.post\(\s*"/"\s*,.*?\)\s*\nasync def.*?:.*?\n', ''),
        ("app/routers/subcategories.py", r'@router\.patch\(\s*"/\{subcategory_id\}/"\s*,.*?\)\s*\nasync def.*?:.*?\n', ''),
        ("app/routers/subcategories.py", r'@router\.delete\(\s*"/\{subcategory_id\}/"\s*,.*?\)\s*\nasync def.*?:.*?\n', ''),
        ("app/routers/templates.py", r'@router\.patch\(\s*"/\{template_id\}/"\s*,.*?\)\s*\nasync def.*?:.*?\n', ''),
        ("app/routers/templates.py", r'@router\.delete\(\s*"/\{template_id\}/"\s*,.*?\)\s*\nasync def.*?:.*?\n', ''),
        ("app/routers/tenants.py", r'@router\.get\(\s*"/\{tenant_id\}/settings/"\s*,.*?\)\s*\nasync def.*?:.*?\n', ''),
    ]
    
    total_fixes = 0
    
    for file_path, pattern, replacement in fixes:
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                original_content = content
                
                # Apply the fix
                import re
                fixed_content = re.sub(pattern, replacement, content, flags=re.MULTILINE | re.DOTALL)
                
                if fixed_content != original_content:
                    # Create backup
                    backup_path = file_path + '.backup'
                    shutil.copy2(file_path, backup_path)
                    
                    # Write fixed content
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(fixed_content)
                    
                    print(f"   ✅ Fixed: {file_path}")
                    total_fixes += 1
            except Exception as e:
                print(f"   ❌ Error fixing {file_path}: {e}")
    
    print(f"\n📊 SUMMARY:")
    print(f"   Total fixes applied: {total_fixes}")
    
    return total_fixes

if __name__ == "__main__":
    fix_specific_duplicates()
