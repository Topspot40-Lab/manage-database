#!/usr/bin/env python3
"""
Mr. Ed — Full Live Endpoint Test Suite (Step 9)

Discovers all routes exposed by FastAPI and performs safe GET/OPTIONS requests
to ensure everything responds without errors.
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import List

import httpx
from fastapi import FastAPI
from importlib import import_module

# ─────────────────────────────────────────────
# Ensure project root is on sys.path
# so `import backend.main` works when run as a script
# ─────────────────────────────────────────────
here = Path(__file__).resolve()
# .../topspot_json_creator/backend/scripts/test_all_endpoints.py
# parents[0] = scripts, parents[1] = backend, parents[2] = project root
project_root = here.parents[2]

if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

BASE_URL = "http://127.0.0.1:8000"


def get_app() -> FastAPI:
    """Import and return the FastAPI app."""
    module = import_module("backend.main")
    return module.app


def discover_routes(app: FastAPI) -> List[str]:
    """Extract full route paths."""
    routes = []
    for route in app.routes:
        if hasattr(route, "path") and route.path not in {
            "/openapi.json",
            "/docs",
            "/redoc",
        }:
            routes.append(route.path)
    return sorted(set(routes))


async def probe_route(client: httpx.AsyncClient, path: str):
    """Try GET, then OPTIONS, return result."""
    url = f"{BASE_URL}{path}"
    try:
        response = await client.get(url, timeout=4)
        return path, response.status_code, None
    except Exception:
        # Try OPTIONS as a fallback (safe & common)
        try:
            response = await client.options(url, timeout=4)
            return path, response.status_code, None
        except Exception as e2:
            return path, None, str(e2)


async def run_tests():
    app = get_app()
    routes = discover_routes(app)

    print("\n🐴 Mr. Ed — Live Endpoint Test Suite (Step 9)\n")
    print(f"🔍 Found {len(routes)} routes. Beginning probes…\n")

    results = []

    async with httpx.AsyncClient() as client:
        tasks = [probe_route(client, path) for path in routes]
        for coro in asyncio.as_completed(tasks):
            results.append(await coro)

    # Sort results by path
    results.sort(key=lambda x: x[0])

    ok = 0
    failed = 0

    for path, status, error in results:
        if status is not None and status < 500:
            print(f"✅ {path:<40} → {status}")
            ok += 1
        else:
            print(f"❌ {path:<40} → ERROR: {error}")
            failed += 1

    print("\n──────── SUMMARY ────────")
    print(f"🟢 OK: {ok}")
    print(f"🔴 Failed: {failed}")
    print("─────────────────────────\n")


if __name__ == "__main__":
    asyncio.run(run_tests())
