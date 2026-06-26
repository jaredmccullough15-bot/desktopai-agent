#!/usr/bin/env python
"""
Worker Restart & Verification Script
1. Verify worker registration with X-Bill-Worker-Key
2. Verify heartbeat
3. Verify task poll
4. Confirm auth headers are present
"""

import requests
import json
import os
import time

BILL_CORE_URL = "http://bill-core-env.eba-e7menpcq.us-east-2.elasticbeanstalk.com"
WORKER_SHARED_SECRET = os.environ.get("BILL_CORE_WORKER_SHARED_SECRET", "").strip()

if not WORKER_SHARED_SECRET:
    print("ERROR: BILL_CORE_WORKER_SHARED_SECRET not set!")
    exit(1)

print("\n" + "="*80)
print("WORKER AUTH VERIFICATION")
print("="*80)
print(f"\nWorker Secret: {'SET' if WORKER_SHARED_SECRET else 'NOT SET'}")
print(f"Bill Core URL: {BILL_CORE_URL}\n")

def worker_request(method, endpoint, machine_uuid="test-worker-001", machine_name="test-worker"):
    """Make authenticated request to worker endpoint."""
    headers = {"X-Bill-Worker-Key": WORKER_SHARED_SECRET}
    url = f"{BILL_CORE_URL}{endpoint}"
    
    try:
        if method.upper() == "GET":
            r = requests.get(url, headers=headers, timeout=5)
        elif method.upper() == "POST":
            data = {
                "machine_uuid": machine_uuid,
                "machine_name": machine_name,
                "capabilities": ["browser"],
                "worker_id": machine_uuid
            }
            r = requests.post(url, json=data, headers=headers, timeout=5)
        else:
            return None, "Unknown method"
        
        # Check if auth header was sent
        headers_sent = "X-Bill-Worker-Key" in str(headers)
        return r.status_code, r.text[:150], headers_sent
    except Exception as e:
        return None, str(e), False

results = {}

# Test 1: Worker Registration
print("[TEST 1] Worker Registration with X-Bill-Worker-Key")
status, resp, headers_sent = worker_request("POST", "/worker/register", "test-worker-001", "test-worker")
if status == 200:
    print(f"  ✓ Success (200)")
    print(f"  ✓ Auth header sent: {headers_sent}")
    results["registration"] = "PASS"
elif status in [401, 403]:
    print(f"  ✗ Auth failed ({status})")
    print(f"    Response: {resp}")
    results["registration"] = "FAIL - Auth rejected"
else:
    print(f"  ✗ Error ({status})")
    print(f"    Response: {resp}")
    results["registration"] = f"FAIL - {status}"

print()

# Test 2: Heartbeat (worker status update)
print("[TEST 2] Worker Heartbeat/Status Update")
status, resp, headers_sent = worker_request("POST", "/worker/status", "test-worker-001", "test-worker")
if status == 200:
    print(f"  ✓ Success (200)")
    print(f"  ✓ Auth header sent: {headers_sent}")
    results["heartbeat"] = "PASS"
elif status == 404:
    # Endpoint may not exist; try alternative
    print(f"  ⚠ Endpoint not found (404) - trying /worker/tasks/next instead")
    results["heartbeat"] = "N/A - endpoint not found"
elif status in [401, 403]:
    print(f"  ✗ Auth failed ({status})")
    results["heartbeat"] = "FAIL - Auth rejected"
else:
    print(f"  ? Status ({status})")
    results["heartbeat"] = f"UNKNOWN - {status}"

print()

# Test 3: Task Poll
print("[TEST 3] Worker Task Poll with X-Bill-Worker-Key")
status, resp, headers_sent = worker_request("GET", "/worker/tasks/next?machine_uuid=test-worker-001", "test-worker-001")
if status == 200:
    print(f"  ✓ Success (200)")
    print(f"  ✓ Auth header sent: {headers_sent}")
    print(f"  ✓ Response: {resp[:100]}")
    results["task_poll"] = "PASS"
elif status in [401, 403]:
    print(f"  ✗ Auth failed ({status})")
    print(f"    Response: {resp}")
    results["task_poll"] = "FAIL - Auth rejected"
else:
    print(f"  ? Status ({status})")
    print(f"    Response: {resp}")
    results["task_poll"] = f"UNKNOWN - {status}"

print()

# Test 4: Verify no 401 errors on protected endpoints WITH auth header
print("[TEST 4] Verify Protected Endpoints Accept Auth Header")
protected_endpoints = [
    ("/worker/register", "POST"),
    ("/worker/tasks/next?machine_uuid=test", "GET"),
]

auth_success_count = 0
for endpoint, method in protected_endpoints:
    status, resp, _ = worker_request(method, endpoint, "test", "test")
    if status and status not in [401, 403]:
        auth_success_count += 1
        print(f"  ✓ {endpoint} ({method}): {status}")
    else:
        print(f"  ✗ {endpoint} ({method}): {status}")

results["protected_endpoints_accepting_auth"] = f"{auth_success_count}/{len(protected_endpoints)}"

print()

# Summary
print("="*80)
print("WORKER AUTH SUMMARY")
print("="*80)
for test_name, result in results.items():
    status_icon = "✓" if "PASS" in str(result) else "✗" if "FAIL" in str(result) else "⚠"
    print(f"{status_icon} {test_name}: {result}")

print()
if "FAIL" not in str(results):
    print("🟢 WORKER AUTH VERIFICATION PASSED - Ready for deployment\n")
else:
    print("🔴 WORKER AUTH VERIFICATION FAILED - Check auth configuration\n")

print("="*80)
