import sys
sys.path.insert(0, 'c:\\Ai Agent\\desktop-ai-agent')

from modules.actions import click_element_by_text, _get_selenium_driver
import time

print("Testing updated click_element_by_text function...")

driver = _get_selenium_driver()
if not driver:
    print("Failed to get driver")
    sys.exit(1)

print(f"Initial windows: {len(driver.window_handles)}")
print(f"Current URL: {driver.current_url[:60]}...")

print("\nClicking first 'View' button...")
success = click_element_by_text("View", "any")

time.sleep(2)
print(f"\nAfter click:")
print(f"  Success: {success}")
print(f"  Windows: {len(driver.window_handles)}")

if len(driver.window_handles) > 1:
    print(f"  ✓ NEW TAB OPENED!")
    driver.switch_to.window(driver.window_handles[-1])
    print(f"  New tab URL: {driver.current_url[:70]}...")
    
    # Close it
    driver.close()
    driver.switch_to.window(driver.window_handles[0])
    print(f"  Closed tab, back to main window")
else:
    print(f"  ✗ No new tab opened")
