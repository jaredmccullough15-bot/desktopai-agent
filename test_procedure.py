import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

print("Testing Selenium connection...")

# Connect to Chrome debug port
chrome_options = Options()
chrome_options.debugger_address = "127.0.0.1:9222"

try:
    driver = webdriver.Chrome(options=chrome_options)
    print(f"✓ Connected! Current URL: {driver.current_url}")
    print(f"✓ Window handles: {len(driver.window_handles)}")
    
    # Test clicking View button
    print("\nSearching for 'View' button...")
    script = """
    var elements = document.querySelectorAll('button, a, div[onclick], span[onclick]');
    var found = null;
    for (var i = 0; i < elements.length; i++) {
        if (elements[i].textContent.trim().toLowerCase() === 'view') {
            found = elements[i];
            break;
        }
    }
    if (found) {
        return {found: true, text: found.textContent, tag: found.tagName};
    } else {
        return {found: false};
    }
    """
    result = driver.execute_script(script)
    print(f"Search result: {result}")
    
    print("\n✓ Test complete - Selenium is working")
    
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()
