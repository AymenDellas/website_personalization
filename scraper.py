import os
import time
from playwright.sync_api import sync_playwright
from logger import log

def scrape_linkedin_profile(profile_url: str, headless: bool = True, li_at_cookie: str = None) -> str | None:
    """
    Opens a LinkedIn profile URL, scrolls to load content, expands 'About', and extracts visible text.
    Returns the visible text or None if failed.
    """
    with sync_playwright() as p:
        # User-Agent list for rotation
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0"
        ]
        import random
        selected_ua = random.choice(user_agents)

        # Use plain Chromium (msedge not available on Linux/Render)
        browser = p.chromium.launch(headless=headless, args=["--no-sandbox", "--disable-dev-shm-usage"])
        
        # Prepare context options with modern User Agent and more stealthy headers
        context_args = {
            "user_agent": selected_ua,
            "viewport": {"width": 1280, "height": 800},
            "extra_http_headers": {
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Referer": "https://www.google.com/",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "cross-site",
                "Sec-Fetch-User": "?1",
            }
        }
        
        context = browser.new_context(**context_args)

        # Hide webdriver flag (basic stealth)
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        # Add cookie if provided
        if li_at_cookie:
            context.add_cookies([
                {
                    "name": "li_at",
                    "value": li_at_cookie,
                    "domain": ".www.linkedin.com",
                    "path": "/"
                },
                {
                    "name": "JSESSIONID",
                    "value": 'ajax:1234567890123456789',
                    "domain": ".www.linkedin.com",
                    "path": "/"
                }
            ])

        # Open a new page
        page = context.new_page()

        # STEP 0: Homepage Pre-visit to establish session / look human
        try:
            log("Humanizing session: Pre-visiting LinkedIn homepage...")
            page.goto("https://www.linkedin.com", timeout=30000, wait_until="domcontentloaded")
            time.sleep(random.uniform(2, 5))
        except Exception as e:
            log(f"Pre-visit failed (ignoring): {e}")

        try:
            max_retries = 3
            backoff = 20
            
            for attempt in range(max_retries):
                log(f"Navigating to {profile_url} (Attempt {attempt + 1}/{max_retries})...")
                # Use 'domcontentloaded' to grab content even if some scripts are looping
                response = page.goto(profile_url, timeout=60000, wait_until="domcontentloaded")
                
                status = response.status if response else None
                
                # Check for LinkedIn 999 block
                if status == 999:
                    log(f"LinkedIn Status 999 detected. Possible block. Waiting {backoff}s before retry...")
                    time.sleep(backoff)
                    backoff *= 2 # Exponential backoff
                    continue
                
                # Check for other failures
                if not response or status >= 400:
                    print(f"Navigation failed with status {status}")

                # Check if we hit the login wall (often redirected to /authwall or login page)
                if "login" in page.url or "authwall" in page.url:
                    print("Hit login/auth wall. Ensure you are logged in or have a session.")
                    return None
                
                # If we got here, navigation was successful or non-retryable
                break
            else:
                log("Failed to navigate after multiple retries due to LinkedIn blocks.")
                return None

            # Scroll slowly to trigger lazy load
            log("Scrolling page and checking for blocks...")
            for i in range(5):
                page.mouse.wheel(0, 500)
                time.sleep(1)
            
            # Expand "About" section if visible
            try:
                see_more = page.get_by_text("see more", exact=False).first
                if see_more.is_visible():
                    see_more.click()
                    time.sleep(1)
            except Exception as e:
                print(f"Could not expand 'About': {e}")

            # CLICK "Contact info" to get the website!
            contact_text = ""
            try:
                # Common anchor for contact info
                contact_link = page.locator("a[id*='top-card-text-details-contact-info']").first
                if not contact_link.is_visible():
                    contact_link = page.get_by_text("Contact info", exact=True).first
                
                if contact_link.is_visible():
                    log("Opening Contact Info modal...")
                    contact_link.click()
                    time.sleep(2) # Wait for modal
                    
                    # Scrape modal content
                    modal = page.locator("div.pv-contact-info__content, #artdeco-modal-outlet").first
                    if modal.is_visible():
                        modal_text = modal.inner_text()
                        contact_text = f"\n\n--- CONTACT INFO SECTION ---\n{modal_text}\n----------------------------\n"
                        log("Contact Info extracted from modal.")
                        if "http" in modal_text.lower():
                            log("I see a link in the contact info. Passing to AI for validation.")
                        else:
                            log("No direct website link visible in the Contact Info modal.")
                    
                    # Close modal to be safe (optional, but good practice)
                    close_btn = page.locator("button[aria-label='Dismiss']").first
                    if close_btn.is_visible():
                        close_btn.click()
            except Exception as e:
                print(f"Could not extract 'Contact Info': {e}")

            # Capture visible text
            # We use inner_text on the 'main' tag or body if main isn't found
            content_locator = page.locator("main")
            if not content_locator.count():
                content_locator = page.locator("body")
            
            visible_text = content_locator.inner_text()
            
            # Append the contact info we found
            return visible_text + contact_text

        except Exception as e:
            print(f"Scraping error: {e}")
            return None
        finally:
            browser.close()

if __name__ == "__main__":
    # Test run
    text = scrape_linkedin_profile("https://www.linkedin.com/in/williamhgates") 
    print(text[:500] if text else "No text extracted.")
