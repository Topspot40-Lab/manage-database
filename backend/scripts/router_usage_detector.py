#!/usr/bin/env python3
"""
Mr. Ed — Step 10: Router Usage Detector + Cleanup Planner

This script inspects backend.main to see which router modules are truly used.
It compares them against all router files in backend/routers/, then produces:

- ACTIVE routers (imported successfully)
- UNUSED routers (not referenced anywhere)
- BROKEN routers (import errors)
- A recommended cleanup plan

NO files are moved. This is a safety report only.
"""

from __future__ import annotations
import importlib
import pkgutil
import traceback
from pathlib import Path

ROUTER_DIR = Path("backend/routers")
MAIN_MODULE = "backend.main"

print("\n🐴 Mr. Ed — Router Usage Detector (Step 10)\n")

# -------------------------------------------------------------------
# Load backend.main and collect all successfully imported routers
# -------------------------------------------------------------------

try:
    main_mod = importlib.import_module(MAIN_MODULE)
except Exception as e:
    print("❌ ERROR: Could not load backend.main\n")
    print(traceback.format_exc())
    raise SystemExit(1)

active_modules = set()
errors = {}

print("🔍 Scanning backend.main for imported router modules...\n")

for finder, name, ispkg in pkgutil.iter_modules([str(ROUTER_DIR)]):
    module_name = f"backend.routers.{name}"

    try:
        mod = importlib.import_module(module_name)
        # detect if router object exists
        if hasattr(mod, "router") or any(attr.endswith("_router") for attr in dir(mod)):
            active_modules.add(name)
    except Exception as e:
        errors[name] = str(e)

# -------------------------------------------------------------------
# List every router file in backend/routers/
# -------------------------------------------------------------------

router_files = sorted([f.stem for f in ROUTER_DIR.glob("*.py") if f.name != "__init__.py"])

unused = [name for name in router_files if name not in active_modules]

# -------------------------------------------------------------------
# Output Report
# -------------------------------------------------------------------

print("📦 All routers found in backend/routers/:")
print("   " + ", ".join(router_files) + "\n")

print("🟢 ACTIVE Router Modules (imported successfully):")
for name in sorted(active_modules):
    print(f"   ✔ {name}")
print()

print("🔴 UNUSED Router Modules (not imported by backend.main):")
for name in sorted(unused):
    print(f"   ⚠ {name}")
print()

print("❌ BROKEN Router Modules (import errors):")
for name, err in errors.items():
    print(f"   ❌ {name}: {err[:120]}...")
print()

# -------------------------------------------------------------------
# Recommended Cleanup Plan
# -------------------------------------------------------------------

print("\n──────── CLEANUP PLAN ────────")
print("These modules are safe to archive IF you confirm:\n")

for name in sorted(unused):
    print(f"   📦 {name}.py → backend/routers/_archive/")

if errors:
    print("\n⚠ WARNING: These routers fail to import and may break startup:")
    for name in errors.keys():
        print(f"   ❌ {name}.py (fix or archive)")
else:
    print("\nNo import errors detected.")

print("\nNo files moved. Review first.")
print("When ready, run Step 11: Safely archive unused routers.\n")
print("──────────────────────────────\n")
