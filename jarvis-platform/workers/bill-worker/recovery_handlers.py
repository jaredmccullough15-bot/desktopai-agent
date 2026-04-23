"""
Smart Sherpa Sync recovery action handlers.

Implements worker-side recovery actions for paused smart_sherpa_sync tasks.
These handlers are called by the worker when it polls for recovery actions.
"""
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


async def close_extra_tabs(browser, context: dict) -> tuple[bool, str]:
    """
    Close extra browser tabs and return to main tab.
    
    Args:
        browser: Puppeteer Browser instance
        context: Recovery context dict with open_tabs_count, active_tab_index
    
    Returns:
        (success: bool, message: str)
    """
    try:
        pages = await browser.pages()
        main_page = pages[0] if pages else None
        
        if not main_page:
            return False, "No main page found"
        
        # Close all tabs except the first
        for page in pages[1:]:
            await page.close()
        
        await main_page.bringToFront()
        
        message = f"Closed {len(pages) - 1} extra tabs"
        logger.info("close_extra_tabs: %s", message)
        return True, message
    except Exception as e:
        logger.error("close_extra_tabs failed: %s", str(e))
        return False, f"Failed to close tabs: {str(e)}"


async def dismiss_product_review_modal(browser, context: dict) -> tuple[bool, str]:
    """
    Dismiss a product review modal that's blocking navigation.
    
    Args:
        browser: Puppeteer Browser instance
        context: Recovery context dict with modal_type
    
    Returns:
        (success: bool, message: str)
    """
    try:
        pages = await browser.pages()
        page = pages[0] if pages else None
        
        if not page:
            return False, "No active page"
        
        # Try common close button selectors for modals
        close_selectors = [
            'button[aria-label="Close"]',
            'button.close',
            'button[type="button"]:has-text("Close")',
            'button[type="button"]:has-text("Dismiss")',
            'button[type="button"]:has-text("No, thanks")',
            'button[type="button"]:has-text("Cancel")',
            '[role="button"][aria-label="Close"]',
        ]
        
        for selector in close_selectors:
            try:
                await page.click(selector)
                await page.waitForLoadState("load")
                logger.info("dismiss_product_review_modal: closed with selector %s", selector)
                return True, f"Modal dismissed with selector '{selector}'"
            except:
                continue
        
        # If no button worked, try pressing Escape
        await page.press("Escape")
        await page.waitForLoadState("load")
        logger.info("dismiss_product_review_modal: pressed Escape")
        return True, "Modal dismissed with Escape key"
    
    except Exception as e:
        logger.error("dismiss_product_review_modal failed: %s", str(e))
        return False, f"Failed to dismiss modal: {str(e)}"


async def return_to_client_list(browser, context: dict) -> tuple[bool, str]:
    """
    Navigate back to the client/search list page.
    Typically used after a failed client navigation.
    
    Args:
        browser: Puppeteer Browser instance
        context: Recovery context dict
    
    Returns:
        (success: bool, message: str)
    """
    try:
        pages = await browser.pages()
        page = pages[0] if pages else None
        
        if not page:
            return False, "No active page"
        
        # Try browser back button first
        try:
            await page.goBack()
            await page.waitForLoadState("load")
            logger.info("return_to_client_list: went back")
            return True, "Navigated back to previous page"
        except:
            pass
        
        # Try clicking home or back button on page
        back_selectors = [
            'button[aria-label="Back"]',
            'button.back-button',
            '[role="button"][aria-label="Back"]',
            'a:has-text("Back")',
        ]
        
        for selector in back_selectors:
            try:
                await page.click(selector)
                await page.waitForLoadState("load")
                logger.info("return_to_client_list: clicked back with selector %s", selector)
                return True, f"Clicked back button (selector: '{selector}')"
            except:
                continue
        
        return False, "Could not navigate back to client list"
    
    except Exception as e:
        logger.error("return_to_client_list failed: %s", str(e))
        return False, f"Failed to return to client list: {str(e)}"


async def retry_last_client(browser, context: dict) -> tuple[bool, str]:
    """
    Resume processing the last client that encountered an error.
    Used when the error was transient and should be retried.
    
    Args:
        browser: Puppeteer Browser instance
        context: Recovery context dict with last_client_attempted
    
    Returns:
        (success: bool, message: str)
    """
    try:
        last_client = context.get("last_client_attempted", "")
        
        if not last_client:
            return False, "No last client found in recovery context"
        
        pages = await browser.pages()
        page = pages[0] if pages else None
        
        if not page:
            return False, "No active page"
        
        # Try to find and click the last client in the list
        # This is workflow-specific; adjust selectors based on actual smart_sherpa_sync UI
        
        # Search for the client name in the page
        found = await page.evaluate(f"""
            () => {{
                const text = document.body.innerText;
                return text.includes('{last_client}');
            }}
        """)
        
        if not found:
            return False, f"Client '{last_client}' not found in current page"
        
        # Try clicking on a link/button containing the client name
        try:
            await page.click(f'text={last_client}')
            await page.waitForLoadState("load")
            logger.info("retry_last_client: clicked on client %s", last_client)
            return True, f"Clicked on client '{last_client}' to retry"
        except:
            pass
        
        return False, f"Could not click on client '{last_client}'"
    
    except Exception as e:
        logger.error("retry_last_client failed: %s", str(e))
        return False, f"Failed to retry last client: {str(e)}"


async def skip_last_client(browser, context: dict) -> tuple[bool, str]:
    """
    Mark the last client as skipped and move to the next one.
    
    Args:
        browser: Puppeteer Browser instance
        context: Recovery context dict with last_client_attempted
    
    Returns:
        (success: bool, message: str)
    """
    try:
        last_client = context.get("last_client_attempted", "")
        
        # Try to find a skip button or next button
        skip_selectors = [
            'button:has-text("Skip")',
            'button:has-text("Next")',
            'button:has-text("Continue")',
            '[role="button"]:has-text("Skip")',
        ]
        
        pages = await browser.pages()
        page = pages[0] if pages else None
        
        if not page:
            return False, "No active page"
        
        for selector in skip_selectors:
            try:
                await page.click(selector)
                await page.waitForLoadState("load")
                logger.info("skip_last_client: clicked skip/next with selector %s", selector)
                return True, f"Skipped client '{last_client}' and moved to next"
            except:
                continue
        
        return False, "Could not find skip/next button"
    
    except Exception as e:
        logger.error("skip_last_client failed: %s", str(e))
        return False, f"Failed to skip client: {str(e)}"


# Handler registry
RECOVERY_HANDLERS = {
    "close_extra_tabs": close_extra_tabs,
    "dismiss_product_review_modal": dismiss_product_review_modal,
    "return_to_client_list": return_to_client_list,
    "retry_last_client": retry_last_client,
    "skip_last_client": skip_last_client,
    "resume_sync": None,  # Implemented as state reset in main worker loop
    "restart_from_current_page": None,  # Implemented as state reset
    "restart_from_checkpoint": None,  # Implemented as state restoration
    "close_extra_tabs_and_retry": close_extra_tabs,  # Combined action
    "dismiss_modal_and_resume": dismiss_product_review_modal,  # Combined action
}


async def execute_recovery_action(
    action_name: str,
    browser,
    recovery_context: dict,
) -> tuple[bool, str]:
    """
    Execute a named recovery action.
    
    Args:
        action_name: name of the recovery action (e.g., "close_extra_tabs")
        browser: Puppeteer Browser instance
        recovery_context: recovery context dict
    
    Returns:
        (success: bool, message: str)
    """
    handler = RECOVERY_HANDLERS.get(action_name)
    
    if handler is None:
        logger.warning("Recovery handler not found for action: %s", action_name)
        return False, f"No handler for recovery action '{action_name}'"
    
    if callable(handler):
        return await handler(browser, recovery_context)
    else:
        # Handler is None, meaning it's handled elsewhere (state reset)
        logger.info("Recovery action '%s' handled via state reset", action_name)
        return True, f"Action '{action_name}' prepared (state reset)"
