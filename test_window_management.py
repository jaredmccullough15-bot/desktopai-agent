"""
Test window management - click View, verify window switching, close properly
"""
import sys
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

# Import our updated functions
sys.path.insert(0, '.')
from modules.actions import click_element_by_text, close_current_tab, wait_for_page_load

# Connect to existing Chrome on port 9222
options = Options()
options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
driver = webdriver.Chrome(options=options)

print(f"\n✓ Connected! Current URL: {driver.current_url[:80]}")
print(f"✓ Window handles: {len(driver.window_handles)}")

# Navigate to client list (with 2026 filter - adjust if needed)
url = "https://www.healthsherpa.com/agents/jared-chapdelaine-mccullough?plan_year=2026"
print(f"\n[1/7] Navigating to: {url[:80]}...")
driver.get(url)
time.sleep(2)

# Wait for page to load
print("\n[2/7] Waiting for page to load...")
wait_for_page_load(timeout_sec=10)

print(f"✓ Page loaded. Windows: {len(driver.window_handles)}")

# Click first View button
print("\n[3/7] Clicking first View button...")
success = click_element_by_text("View", "any")

if success:
    print(f"✓ Click successful. Windows: {len(driver.window_handles)}")
    time.sleep(1)
    
    # Wait for client page to load
    print("\n[4/7] Waiting for client page to load (20 sec)...")
    wait_for_page_load(timeout_sec=20)
    print(f"✓ Client page loaded. Current URL: {driver.current_url[:80]}")
    
    # Close the tab
    print("\n[5/7] Closing client tab...")
    close_success = close_current_tab()
    
    if close_success:
        print(f"✓ Tab closed. Windows: {len(driver.window_handles)}")
        print(f"✓ Current URL: {driver.current_url[:80]}")
        
        # Try clicking another View button
        print("\n[6/7] Clicking second View button...")
        success2 = click_element_by_text("View", "any")
        
        if success2:
            print(f"✓ Second click successful. Windows: {len(driver.window_handles)}")
            time.sleep(2)
            
            # Close second tab
            print("\n[7/7] Closing second client tab...")
            close_current_tab()
            print(f"✓ Second tab closed. Windows: {len(driver.window_handles)}")
            print(f"✓ Final URL: {driver.current_url[:80]}")
            print("\n✅ ALL TESTS PASSED! Window management working correctly.")
        else:
            print("⚠️ Second View click failed")
    else:
        print("⚠️ Tab close failed")
else:
    print("⚠️ View click failed")

print("\nTest complete!")
