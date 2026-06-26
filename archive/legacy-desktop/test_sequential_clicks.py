"""
Test sequential View button clicking with client name tracking
"""
import sys
import time

# Import our new functions
sys.path.insert(0, '.')
from modules.actions import click_next_view_button, reset_view_button_counter, wait_for_element_with_text, close_current_tab

print("\n=== Testing Sequential View Button Clicks ===\n")

# Navigate to the page first (assumes Chrome is already open on port 9222)
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

options = Options()
options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
driver = webdriver.Chrome(options=options)

# Navigate to client list
url = "https://www.healthsherpa.com/agents/jared-chapdelaine-mccullough/clients?plan_year=2026&per_page=50"
print(f"Navigating to: {url[:80]}...")
driver.get(url)
time.sleep(3)

# Reset counter to start from the beginning
print("\n[1] Resetting View button counter...")
reset_view_button_counter()

# Test clicking 3 clients sequentially
for i in range(1, 4):
    print(f"\n[{i+1}] Clicking next View button...")
    result = click_next_view_button()
    
    if result.get("success"):
        client_name = result.get("client_name", "Unknown")
        index = result.get("index", -1)
        print(f"✅ Successfully opened client #{index + 1}: {client_name}")
        
        # Wait for "Sync Complete" to appear (20 seconds)
        print(f"   Waiting up to 20 seconds for 'Sync Complete'...")
        found = wait_for_element_with_text("Sync Complete", timeout_sec=20)
        
        if found:
            print(f"   ✅ 'Sync Complete' appeared!")
        else:
            print(f"   ⚠️ 'Sync Complete' did not appear within 20 seconds")
        
        # Close the tab
        print(f"   Closing client tab...")
        close_success = close_current_tab()
        
        if close_success:
            print(f"   ✅ Tab closed, back to client list")
        else:
            print(f"   ⚠️ Failed to close tab")
            break
    else:
        print(f"❌ Failed to click View button")
        break
    
    time.sleep(1)

print("\n=== Test Complete ===\n")
print("Summary:")
print("- Counter resets to 0 at start")
print("- Each click_next_view_button() clicks the next client in sequence")
print("- Client names are extracted from the table rows")
print("- wait_for_element_with_text() waits up to 20s for 'Sync Complete'")
print("- Tabs close properly and return to client list")
