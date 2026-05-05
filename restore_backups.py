#!/usr/bin/env python3
"""
Restore all backup files
"""

import os
import shutil

def restore_backups():
    """Restore all .backup files to original"""
    print("🔄 RESTORING BACKUP FILES")
    print("=" * 40)
    
    router_dir = "app/routers"
    restored = 0
    
    for file in os.listdir(router_dir):
        if file.endswith('.backup'):
            backup_path = os.path.join(router_dir, file)
            original_path = backup_path.replace('.backup', '')
            
            try:
                shutil.copy2(backup_path, original_path)
                print(f"   ✅ Restored: {file} -> {os.path.basename(original_path)}")
                restored += 1
            except Exception as e:
                print(f"   ❌ Failed to restore {file}: {e}")
    
    print(f"\n📊 Restored {restored} files")
    return restored

if __name__ == "__main__":
    restore_backups()
