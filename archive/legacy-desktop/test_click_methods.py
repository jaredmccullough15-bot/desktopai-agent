import sys
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

print("Testing different click methods...")

chrome_options = Options()
chrome_options.debugger_address = "127.0.0.1:9222"
driver = webdriver.Chrome(options=chrome_options)

print(f"Current URL: {driver.current_url[:60]}...")
print(f"Initial windows: {len(driver.window_handles)}")

# Method 1: Find element and use native Selenium click
print("\n[Method 1] Using Selenium native click...")
try:
    # Find all links with text "View"
    view_links = driver.find_elements(By.XPATH, "//a[normalize-space(text())='View']")
    print(f"Found {len(view_links)} View links via XPath")
    
    if view_links:
        first_link = view_links[0]
        print(f"  Link href: {first_link.get_attribute('href')}")
        print(f"  Link target: {first_link.get_attribute('target')}")
        print(f"  Is displayed: {first_link.is_displayed()}")
        
        print("  Clicking...")
        first_link.click()
        time.sleep(2)
        print(f"  Windows after click: {len(driver.window_handles)}")
        
        if len(driver.window_handles) > 1:
            print("  ✓ New tab opened!")
            driver.switch_to.window(driver.window_handles[-1])
            print(f"  New tab URL: {driver.current_url[:60]}...")
            driver.close()
            driver.switch_to.window(driver.window_handles[0])
        else:
            print("  ✗ No new tab - trying to navigate directly...")
            href = first_link.get_attribute('href')
            if href:
                print(f"  Opening URL in new window manually: {href[:60]}...")
                driver.execute_script(f"window.open('{href}', '_blank');")
                time.sleep(2)
                print(f"  Windows after manual open: {len(driver.window_handles)}")
except Exception as e:
    print(f"  Error: {e}")
    import traceback
    traceback.print_exc()

print("\nTest complete!")
