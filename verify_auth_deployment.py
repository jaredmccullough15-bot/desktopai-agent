#!/usr/bin/env python
"""
Post-Deployment Verification Checklist for Wave 1 Priority 3 (API Authentication)
Tests all 8 steps of the deployment verification plan.
"""

import requests
import json
import os
from datetime import datetime
from typing import Dict, List, Tuple

# Configuration
DASHBOARD_API_KEY = os.environ.get("BILL_CORE_DASHBOARD_API_KEY", "").strip()
WORKER_SHARED_SECRET = os.environ.get("BILL_CORE_WORKER_SHARED_SECRET", "").strip()

# Allow specifying custom URL via environment or default to localhost
BASE_URL = os.environ.get("BILL_CORE_URL", "http://localhost:8000").rstrip("/")

# Verification results
results = {
    "timestamp": datetime.now().isoformat(),
    "base_url": BASE_URL,
    "tests": {},
    "summary": {
        "passed": 0,
        "failed": 0,
        "total": 0
    }
}

def test_endpoint(
    test_name: str,
    method: str,
    endpoint: str,
    headers: Dict = None,
    json_data: Dict = None,
    expected_status: int = None,
    should_fail: bool = False
) -> Tuple[bool, str, int, str]:
    """
    Test an endpoint and return success status, message, status code, and response text.
    """
    url = f"{BASE_URL}{endpoint}"
    try:
        if method.upper() == "GET":
            response = requests.get(url, headers=headers, timeout=5)
        elif method.upper() == "POST":
            response = requests.post(url, headers=headers, json=json_data, timeout=5)
        else:
            return False, f"Unknown method: {method}", 0, ""
        
        response_text = response.text[:200] if response.text else "(empty)"
        
        if should_fail:
            if response.status_code >= 400:
                return True, f"Correctly rejected with {response.status_code}", response.status_code, response_text
            else:
                return False, f"Expected rejection but got {response.status_code}", response.status_code, response_text
        else:
            if expected_status and response.status_code != expected_status:
                return False, f"Expected {expected_status}, got {response.status_code}", response.status_code, response_text
            elif response.status_code >= 400:
                return False, f"Got error {response.status_code}", response.status_code, response_text
            else:
                return True, f"Success ({response.status_code})", response.status_code, response_text
    
    except requests.exceptions.ConnectionError:
        return False, "Connection refused (Bill Core not running?)", 0, ""
    except requests.exceptions.Timeout:
        return False, "Request timeout", 0, ""
    except Exception as e:
        return False, f"Exception: {str(e)}", 0, ""

def run_verification():
    """Run all 8 verification steps."""
    
    print("\n" + "="*80)
    print("POST-DEPLOYMENT VERIFICATION CHECKLIST")
    print("Wave 1 Priority 3: API Authentication & Worker Authorization")
    print("="*80)
    print(f"\nBase URL: {BASE_URL}")
    print(f"Dashboard API Key set: {bool(DASHBOARD_API_KEY)}")
    print(f"Worker Secret set: {bool(WORKER_SHARED_SECRET)}")
    print("\n" + "-"*80)
    
    # Test 1: /health works without auth
    print("\n[TEST 1] /health endpoint works WITHOUT auth (public)")
    success, msg, status, resp = test_endpoint(
        "health_public",
        "GET",
        "/health"
    )
    results["tests"]["1_health_public"] = {
        "success": success,
        "message": msg,
        "status": status,
        "response_preview": resp
    }
    results["summary"]["total"] += 1
    if success:
        results["summary"]["passed"] += 1
        print(f"  ✓ {msg}")
    else:
        results["summary"]["failed"] += 1
        print(f"  ✗ {msg}")
    
    # Test 2: Protected endpoint rejects MISSING key
    print("\n[TEST 2] Protected endpoint rejects requests with MISSING auth key")
    success, msg, status, resp = test_endpoint(
        "protected_no_key",
        "GET",
        "/api/tasks",
        should_fail=True
    )
    results["tests"]["2_protected_no_key"] = {
        "success": success,
        "message": msg,
        "status": status,
        "response_preview": resp
    }
    results["summary"]["total"] += 1
    if success:
        results["summary"]["passed"] += 1
        print(f"  ✓ {msg}")
    else:
        results["summary"]["failed"] += 1
        print(f"  ✗ {msg}")
    
    # Test 3: Protected endpoint rejects WRONG key
    print("\n[TEST 3] Protected endpoint rejects requests with WRONG dashboard key")
    success, msg, status, resp = test_endpoint(
        "protected_wrong_key",
        "GET",
        "/api/tasks",
        headers={"X-Bill-Core-Key": "wrong-key-value-12345"},
        should_fail=True
    )
    results["tests"]["3_protected_wrong_key"] = {
        "success": success,
        "message": msg,
        "status": status,
        "response_preview": resp
    }
    results["summary"]["total"] += 1
    if success:
        results["summary"]["passed"] += 1
        print(f"  ✓ {msg}")
    else:
        results["summary"]["failed"] += 1
        print(f"  ✗ {msg}")
    
    # Test 4: Protected endpoint accepts CORRECT dashboard key
    print("\n[TEST 4] Protected endpoint accepts requests with CORRECT dashboard key")
    success, msg, status, resp = test_endpoint(
        "protected_correct_key",
        "GET",
        "/api/tasks",
        headers={"X-Bill-Core-Key": DASHBOARD_API_KEY}
    )
    results["tests"]["4_protected_correct_key"] = {
        "success": success,
        "message": msg,
        "status": status,
        "response_preview": resp
    }
    results["summary"]["total"] += 1
    if success:
        results["summary"]["passed"] += 1
        print(f"  ✓ {msg}")
    else:
        results["summary"]["failed"] += 1
        print(f"  ✗ {msg}")
    
    # Test 5: Frontend proxy test (check if key is injected server-side)
    print("\n[TEST 5] Frontend proxy injects X-Bill-Core-Key header server-side")
    print("  Note: This requires accessing Amplify frontend and checking network headers.")
    print("  Manual check: Open browser DevTools → Network tab → Check /api/* requests")
    results["tests"]["5_frontend_proxy"] = {
        "success": None,
        "message": "Requires manual verification in browser",
        "status": None,
        "response_preview": "Manual check required"
    }
    print(f"  ⚠ Manual verification required (see above)")
    
    # Test 6: Worker registration with CORRECT worker key
    print("\n[TEST 6] Worker can register with CORRECT X-Bill-Worker-Key")
    success, msg, status, resp = test_endpoint(
        "worker_register_correct",
        "POST",
        "/worker/register",
        headers={"X-Bill-Worker-Key": WORKER_SHARED_SECRET},
        json_data={"worker_id": "test-worker", "capabilities": ["browser"]},
        expected_status=200
    )
    results["tests"]["6_worker_register"] = {
        "success": success,
        "message": msg,
        "status": status,
        "response_preview": resp
    }
    results["summary"]["total"] += 1
    if success:
        results["summary"]["passed"] += 1
        print(f"  ✓ {msg}")
    else:
        results["summary"]["failed"] += 1
        print(f"  ✗ {msg}")
    
    # Test 7: Worker task poll with CORRECT worker key
    print("\n[TEST 7] Worker can poll tasks with CORRECT X-Bill-Worker-Key")
    success, msg, status, resp = test_endpoint(
        "worker_task_poll",
        "GET",
        "/worker/tasks/next",
        headers={"X-Bill-Worker-Key": WORKER_SHARED_SECRET}
    )
    results["tests"]["7_worker_task_poll"] = {
        "success": success,
        "message": msg,
        "status": status,
        "response_preview": resp
    }
    results["summary"]["total"] += 1
    if success:
        results["summary"]["passed"] += 1
        print(f"  ✓ {msg}")
    else:
        results["summary"]["failed"] += 1
        print(f"  ✗ {msg}")
    
    # Test 8: Teaching mode still works (manual check)
    print("\n[TEST 8] Teaching Mode still works end-to-end")
    print("  Manual check required:")
    print("    1. Navigate to Bill Web dashboard (Amplify URL)")
    print("    2. Create new teaching session")
    print("    3. Observe browser automation starts normally")
    print("    4. Teaching session completes successfully")
    print("    5. Verify session saved to Bill Core database")
    results["tests"]["8_teaching_mode"] = {
        "success": None,
        "message": "Requires manual end-to-end verification",
        "status": None,
        "response_preview": "Manual check required"
    }
    print(f"  ⚠ Manual verification required (see above)")
    
    # Print summary
    print("\n" + "="*80)
    print("VERIFICATION SUMMARY")
    print("="*80)
    print(f"\nAutomated Tests: {results['summary']['passed']}/{results['summary']['total'] - 2} passed")
    print(f"  ✓ Passed: {results['summary']['passed']}")
    print(f"  ✗ Failed: {results['summary']['failed']}")
    print(f"  ⚠ Manual verification required: 2 tests")
    
    if results['summary']['failed'] == 0 and results['summary']['passed'] > 0:
        print("\n🟢 PRODUCTION READINESS: AUTH MIDDLEWARE ACTIVE AND WORKING")
    elif results['summary']['failed'] > 0:
        print("\n🔴 PRODUCTION READINESS: FAILURES DETECTED - INVESTIGATE ABOVE")
    else:
        print("\n🟡 PRODUCTION READINESS: UNABLE TO TEST (Bill Core not running?)")
    
    # Detailed results
    print("\n" + "-"*80)
    print("DETAILED RESULTS")
    print("-"*80)
    for test_id, test_result in sorted(results["tests"].items()):
        status_icon = "✓" if test_result["success"] is True else "✗" if test_result["success"] is False else "⚠"
        print(f"\n{status_icon} {test_id}")
        print(f"  Message: {test_result['message']}")
        if test_result['status']:
            print(f"  HTTP Status: {test_result['status']}")
        if test_result['response_preview']:
            print(f"  Response: {test_result['response_preview']}")
    
    # Save results to JSON
    output_file = "auth_verification_results.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n✓ Results saved to: {output_file}")
    
    return results

if __name__ == "__main__":
    if not DASHBOARD_API_KEY or not WORKER_SHARED_SECRET:
        print("ERROR: Missing required environment variables!")
        print("  BILL_CORE_DASHBOARD_API_KEY:", "SET" if DASHBOARD_API_KEY else "NOT SET")
        print("  BILL_CORE_WORKER_SHARED_SECRET:", "SET" if WORKER_SHARED_SECRET else "NOT SET")
        exit(1)
    
    run_verification()
