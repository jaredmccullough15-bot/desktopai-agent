import sys
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

print("Inspecting View button HTML structure...")

chrome_options = Options()
chrome_options.debugger_address = "127.0.0.1:9222"
driver = webdriver.Chrome(options=chrome_options)

# Get detailed info about View elements
script = """
var elements = document.querySelectorAll('a, button');
var viewElements = [];
for (var i = 0; i < elements.length && viewElements.length < 3; i++) {
    var text = elements[i].textContent.trim();
    if (text.toLowerCase() === 'view') {
        viewElements.push({
            index: i,
            tag: elements[i].tagName,
            text: text,
            innerHTML: elements[i].innerHTML,
            href: elements[i].href || null,
            target: elements[i].target || null,
            className: elements[i].className,
            id: elements[i].id || null,
            onclick: elements[i].onclick ? 'Has onclick' : 'No onclick',
            parent: elements[i].parentElement ? elements[i].parentElement.tagName : null
        });
    }
}
return viewElements;
"""

results = driver.execute_script(script)
print(f"\nFound {len(results)} View elements:\n")

for i, elem in enumerate(results):
    print(f"Element {i+1}:")
    print(f"  Tag: {elem['tag']}")
    print(f"  Text: '{elem['text']}'")
    print(f"  HTML: {elem['innerHTML'][:100]}")
    print(f"  href: {elem['href']}")
    print(f"  target: {elem['target']}")
    print(f"  class: {elem['className']}")
    print(f"  id: {elem['id']}")
    print(f"  onclick: {elem['onclick']}")
    print(f"  parent: {elem['parent']}")
    print()

print("\nNow testing if clicking actually navigates...")
# Store original URL
original_url = driver.current_url
print(f"Original URL: {original_url[:60]}...")

# Try clicking with ActionChains
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By

try:
    # Find the element using a more flexible XPath
    view_link = driver.find_element(By.XPATH, "//a[contains(text(), 'View')]")
    print(f"\nFound element via XPath")
    print(f"  href: {view_link.get_attribute('href')}")
    
    # Scroll into view
    driver.execute_script("arguments[0].scrollIntoView(true);", view_link)
    time.sleep(0.5)
    
    # Try normal click
    print("  Attempting normal click...")
    view_link.click()
    time.sleep(2)
    
    new_url = driver.current_url
    print(f"  Current URL after click: {new_url[:60]}...")
    print(f"  Windows: {len(driver.window_handles)}")
    
except Exception as e:
    print(f"Error: {e}")
