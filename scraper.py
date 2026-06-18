import os
import time
import re
import random
import sys
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright
from logger import log

def scrape_linkedin_profile(profile_url: str, headless: bool = True, li_at_cookie: str = None, check_activity: bool = False) -> dict | None:
    """
    Opens a LinkedIn profile URL, scrolls to load content, expands 'About', and extracts visible text.
    Optionally checks for recent activity.
    Returns a dictionary with 'visible_text', 'is_active', and 'latest_activity_date' or None if failed.
    """
    with sync_playwright() as p:
        # User-Agent list for rotation
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0"
        ]
        selected_ua = random.choice(user_agents)

        # Use plain Chromium
        browser = p.chromium.launch(headless=headless, args=["--no-sandbox", "--disable-dev-shm-usage"])
        
        # Prepare context options
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
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
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

        page = context.new_page()

        # STEP 0: Homepage Pre-visit
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
                response = page.goto(profile_url, timeout=60000, wait_until="domcontentloaded")
                
                status = response.status if response else None
                
                if status == 999:
                    log(f"LinkedIn Status 999 detected. Possible block. Waiting {backoff}s before retry...")
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                
                if not response or status >= 400:
                    print(f"Navigation failed with status {status}")

                if "login" in page.url or "authwall" in page.url:
                    print("Hit login/auth wall. Ensure you are logged in or have a session.")
                    return None
                
                break
            else:
                log("Failed to navigate after multiple retries due to LinkedIn blocks.")
                return None

            # Scroll slowly to trigger lazy load — scroll MORE to load Activity section
            log("Scrolling page to load all sections...")
            for i in range(8):
                page.mouse.wheel(0, 600)
                time.sleep(0.8)
            time.sleep(2)
            
            # Expand "About" section if visible
            try:
                see_more = page.get_by_text("see more", exact=False).first
                if see_more.is_visible():
                    see_more.click(timeout=3000)
                    time.sleep(1)
            except Exception as e:
                print(f"Could not expand 'About': {e}")

            # CLICK "Contact info" to get the website!
            contact_text = ""
            try:
                contact_link = page.locator("a[id*='top-card-text-details-contact-info']").first
                if not contact_link.is_visible():
                    contact_link = page.get_by_text("Contact info", exact=True).first
                
                if contact_link.is_visible():
                    log("Opening Contact Info modal...")
                    contact_link.click(timeout=3000)
                    time.sleep(2)
                    
                    modal = page.locator("div.pv-contact-info__content, #artdeco-modal-outlet").first
                    if modal.is_visible():
                        modal_text = modal.inner_text()
                        contact_text = f"\n\n--- CONTACT INFO SECTION ---\n{modal_text}\n----------------------------\n"
                        log("Contact Info extracted from modal.")
                    
                    close_btn = page.locator("button[aria-label='Dismiss']").first
                    if close_btn.is_visible():
                        close_btn.click(timeout=3000)
            except Exception as e:
                print(f"Could not extract 'Contact Info': {e}")

            # Capture visible text
            content_locator = page.locator("main")
            if not content_locator.count():
                content_locator = page.locator("body")
            
            visible_text = content_locator.inner_text()
            full_text = visible_text + contact_text

            # --- ACTIVITY CHECK (on-page, no navigation) ---
            is_active = False
            latest_activity_date = "No posts found"

            if check_activity:
                try:
                    log("Checking activity from profile page (no navigation)...")
                    
                    # Strategy 1: Look for the Activity section on the profile page
                    # LinkedIn shows "Activity" section with recent posts inline
                    activity_section = None
                    sections = page.locator("section").all()
                    for sec in sections:
                        try:
                            header = sec.locator("h2, .pvs-header__title, [class*='header']").first
                            if header.count() and 'activity' in header.inner_text().strip().lower():
                                activity_section = sec
                                break
                        except:
                            continue
                    
                    if activity_section:
                        activity_text = activity_section.inner_text().lower()
                        log(f"Found Activity section on profile ({len(activity_text)} chars)")
                        
                        # Parse time indicators from the activity section text
                        # Look for patterns like "1h", "2d", "3w", "1mo", "2yr", "just now"
                        time_match = re.search(
                            r'(\d+)\s*(h|hr|hour|d|day|w|wk|week|mo|month|yr|year)s?\b',
                            activity_text
                        )
                        if time_match:
                            amount = int(time_match.group(1))
                            unit = time_match.group(2)
                            latest_activity_date = time_match.group(0).strip()
                            
                            if unit in ('yr', 'year'):
                                is_active = False  # Too old
                            elif unit in ('mo', 'month'):
                                is_active = amount <= 2  # Active if within 2 months
                            else:
                                is_active = True  # h, d, w = very recent
                        elif 'just now' in activity_text or 'today' in activity_text:
                            is_active = True
                            latest_activity_date = "just now"
                    else:
                        log("No Activity section found on profile page.")
                    
                    # Strategy 2: If no section found, scan the full page text
                    # for any time-related text near "posted", "shared", "commented"
                    if not is_active and latest_activity_date == "No posts found":
                        page_text = full_text.lower()
                        # Check if there's any post activity mentioned on the page
                        activity_indicators = re.findall(
                            r'(?:posted|shared|reposted|commented|liked)\s+.*?(\d+\s*(?:h|d|w|mo|yr)\b)',
                            page_text
                        )
                        if activity_indicators:
                            latest = activity_indicators[0].strip()
                            latest_activity_date = latest
                            if 'yr' not in latest:
                                if 'mo' in latest:
                                    mo_match = re.search(r'(\d+)\s*mo', latest)
                                    is_active = mo_match and int(mo_match.group(1)) <= 2
                                else:
                                    is_active = True
                    
                    log(f"Activity check complete: active={is_active}, date={latest_activity_date}")
                except Exception as e:
                    log(f"Activity check failed: {e}")


            return {
                "visible_text": full_text,
                "is_active": is_active,
                "latest_activity_date": latest_activity_date
            }

        except Exception as e:
            try:
                print(f"Scraping error: {e}")
            except:
                log(f"Scraping error (print failed): {type(e).__name__}")
            return None
        finally:
            browser.close()

if __name__ == "__main__":
    # Test run
    result = scrape_linkedin_profile("https://www.linkedin.com/in/williamhgates", check_activity=True) 
    if result:
        print(f"Text Snippet: {result['visible_text'][:200]}...")
        print(f"Active: {result['is_active']}")
        print(f"Latest Activity: {result['latest_activity_date']}")
    else:
        print("Scrape failed.")

