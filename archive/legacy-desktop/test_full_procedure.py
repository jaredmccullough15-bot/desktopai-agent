import sys
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By

print("="*60)
print("PROCEDURE TEST - Full workflow simulation")
print("="*60)

# Step 1: Connect to Chrome
print("\n[1/6] Connecting to Chrome on port 9222...")
chrome_options = Options()
chrome_options.debugger_address = "127.0.0.1:9222"

try:
    driver = webdriver.Chrome(options=chrome_options)
    print(f"✓ Connected! Current URL: {driver.current_url[:80]}...")
    print(f"✓ Window handles: {len(driver.window_handles)}")
except Exception as e:
    print(f"✗ Connection failed: {e}")
    sys.exit(1)

# Step 2: Navigate to URL
print("\n[2/6] Navigating to Health Sherpa clients page...")
url = "https://www.healthsherpa.com/agents/jared-chapdelaine-mccullough/clients?_agent_id=jared-chapdelaine-mccullough&ffm_applications[agent_archived]=not_archived&ffm_applications[plan_year][]=2026&ffm_applications[search]=true&term=&renewal=all&desc[]=created_at&agent_id=jared-chapdelaine-mccullough&page=1&per_page=50&exchange=onEx&include_shared_applications=false&include_all_applications=false"
try:
    driver.get(url)
    print(f"✓ Navigated to page")
    time.sleep(2)
except Exception as e:
    print(f"✗ Navigation failed: {e}")
    sys.exit(1)

# Step 3: Wait for page load
print("\n[3/6] Waiting for page to load...")
try:
    wait = WebDriverWait(driver, 10)
    wait.until(lambda d: d.execute_script('return document.readyState') == 'complete')
    print(f"✓ Page loaded")
except Exception as e:
    print(f"⚠ Wait timed out: {e}")

# Step 4: Find View button
print("\n[4/6] Searching for 'View' button...")
script = """
var elements = document.querySelectorAll('button, a, div[onclick], span[onclick]');
var found = [];
for (var i = 0; i < elements.length; i++) {
    var text = elements[i].textContent.trim().toLowerCase();
    if (text === 'view') {
        found.push({
            tag: elements[i].tagName,
            text: elements[i].textContent.trim(),
            href: elements[i].href || 'N/A',
            visible: elements[i].offsetParent !== null
        });
    }
}
return found;
"""
try:
    results = driver.execute_script(script)
    print(f"✓ Found {len(results)} 'View' button(s)")
    for i, result in enumerate(results[:3]):
        print(f"  [{i+1}] {result['tag']}: '{result['text']}' (visible: {result['visible']})")
except Exception as e:
    print(f"✗ Search failed: {e}")
    sys.exit(1)

# Step 5: Click first View button
print("\n[5/6] Clicking first 'View' button...")
click_script = """
var elements = document.querySelectorAll('button, a, div[onclick], span[onclick]');
for (var i = 0; i < elements.length; i++) {
    if (elements[i].textContent.trim().toLowerCase() === 'view') {
        elements[i].click();
        return {success: true, text: elements[i].textContent.trim()};
    }
}
return {success: false, error: 'No View button found'};
"""
try:
    result = driver.execute_script(click_script)
    if result['success']:
        print(f"✓ Clicked: {result['text']}")
        time.sleep(3)
        print(f"✓ Window handles after click: {len(driver.window_handles)}")
    else:
        print(f"✗ Click failed: {result.get('error')}")
        sys.exit(1)
except Exception as e:
    print(f"✗ Click execution failed: {e}")
    sys.exit(1)

# Step 6: Handle new tab
if len(driver.window_handles) > 1:
    print("\n[6/6] New tab opened, switching to it...")
    driver.switch_to.window(driver.window_handles[-1])
    print(f"✓ Switched to new tab")
    print(f"  URL: {driver.current_url[:80]}...")
    
    time.sleep(2)
    
    print("\nSearching for 'Sync Complete'...")
    sync_script = """
    var text = document.body.textContent || document.body.innerText;
    return text.indexOf('Sync Complete') !== -1;
    """
    has_sync = driver.execute_script(sync_script)
    print(f"  'Sync Complete' found: {has_sync}")
    
    print("\nClosing tab and switching back...")
    driver.close()
    driver.switch_to.window(driver.window_handles[0])
    print(f"✓ Back to main window")
    print(f"  Remaining windows: {len(driver.window_handles)}")
else:
    print("\n[6/6] No new tab opened - View button might not have worked")

print("\n" + "="*60)
print("TEST COMPLETE")
print("="*60)
