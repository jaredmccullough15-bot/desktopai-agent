import os
import sys
import time

# Ensure we can import from the project root (one level up from portable)
try:
    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if BASE_DIR not in sys.path:
        sys.path.insert(0, BASE_DIR)
except Exception:
    pass

# Lean runner to process HealthSherpa clients using Selenium attach.
# Requires Chrome started with --remote-debugging-port (default 9222).
# Optional: set CLIENTS_URL env var to the clients list page to auto-open.
# Example: set CLIENTS_URL=https://agent.healthsherpa.com/clients


def main():
    os.environ["CHROME_DEBUG_PORT"] = os.getenv("CHROME_DEBUG_PORT", "9222") or "9222"

    print("\nSmart Sherpa Sync (Lean Runner)")
    print("- Attaches to your already-open Chrome (DevTools)")
    print("- Clicks View for each client, waits for completion, paginates")
    print("- Stops when all pages are done\n")

    # Try to attach driver and optionally open clients list
    try:
        from modules.actions import _get_selenium_driver, wait_for_page_load, smart_process_all_clients
    except Exception as e:
        print(f"Error importing actions: {e}")
        sys.exit(1)

    driver = _get_selenium_driver()
    if driver is None:
        print("Could not attach to Chrome. Make sure Chrome is running with --remote-debugging-port=9222.")
        print("Tip: run start-chrome-debug.ps1, then log in to HealthSherpa in that window.")
        sys.exit(1)

    # If CLIENTS_URL is provided, and we're not already on a clients page, open it.
    clients_url = os.getenv("CLIENTS_URL", "").strip()
    try:
        cur = driver.current_url or ""
    except Exception:
        cur = ""

    if clients_url:
        if "/clients" not in (cur or ""):
            print(f"Opening clients list: {clients_url}")
            try:
                driver.get(clients_url)
                wait_for_page_load(timeout_sec=10)
                time.sleep(1.0)
            except Exception as e:
                print(f"Warning: could not open clients URL: {e}")
        else:
            print("Already on clients list; continuing.")
    else:
        print("CLIENTS_URL not set; using whatever page is currently open.")

    # Run smart process
    result = smart_process_all_clients(
        wait_text=os.getenv("SYNC_TEXT", "Sync Complete"),
        wait_timeout=float(os.getenv("SYNC_TIMEOUT", "20")),
        max_clients=int(os.getenv("MAX_CLIENTS", "10000")),
        close_after_sync=os.getenv("CLOSE_AFTER_SYNC", "true").lower() != "false",
    )

    print("\nSummary:")
    print(f"  Success: {result.get('success')}")
    print(f"  Clients processed: {result.get('clients_processed', 0)}")
    print(f"  Pages processed: {result.get('pages_processed', 0)}")
    if result.get('error'):
        print(f"  Error: {result.get('error')}")


if __name__ == "__main__":
    main()
