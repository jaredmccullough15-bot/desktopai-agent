"""
Test loading the procedure to see if it loads correctly
"""
import sys
import json
import os
sys.path.insert(0, '.')

PROCEDURES_DIR = "data/procedures"

print("\n=== Testing Procedure Loading ===\n")

# Try to load the procedure manually first
procedure_name = "Sherpa Sync (Jared)"
manifest_path = os.path.join(PROCEDURES_DIR, procedure_name, "manifest.json")

print(f"Looking for manifest at: {manifest_path}")
print(f"File exists: {os.path.isfile(manifest_path)}")

if os.path.isfile(manifest_path):
    print("\n✅ Manifest file found")
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f"✅ JSON loaded successfully")
        print(f"   Keys in data: {list(data.keys())}")
        print(f"   Name: {data.get('name')}")
        print(f"   Events count: {len(data.get('events', []))}")
    except json.JSONDecodeError as e:
        print(f"❌ JSON decode error: {e}")
    except Exception as e:
        print(f"❌ Error reading file: {type(e).__name__}: {e}")
else:
    print(f"❌ Manifest file not found!")
    print(f"\nChecking procedures directory...")
    if os.path.isdir(PROCEDURES_DIR):
        print(f"✅ Procedures directory exists")
        print(f"Contents:")
        for item in os.listdir(PROCEDURES_DIR):
            item_path = os.path.join(PROCEDURES_DIR, item)
            if os.path.isdir(item_path):
                print(f"  📁 {item}")
                manifest = os.path.join(item_path, "manifest.json")
                if os.path.isfile(manifest):
                    print(f"     ✓ has manifest.json")
                else:
                    print(f"     ✗ no manifest.json")
    else:
        print(f"❌ Procedures directory doesn't exist!")

# Now try using the actual function
print("\n\n--- Testing _load_procedure function ---\n")
from modules.procedures import _load_procedure

info = _load_procedure(procedure_name)
if info is None:
    print("❌ _load_procedure returned None")
else:
    print(f"✅ _load_procedure succeeded")
    print(f"   Events: {len(info.events)}")
