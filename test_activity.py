import os
import time
import random
from playwright.sync_api import sync_playwright
from datetime import datetime, timedelta
import re

# Configuration
LI_AT_COOKIES = [
    "AQEDAWWqM8YAO7dHAAABnPQLTLAAAAGdGBfQsE0AeLMPTny70_-zvg3n7SNdgbc7smGd5ri4GIujvykV_q-istgN5YyQJBm9UAemK9arifULCdvj4NhelPPrKT7LBwhByDiz9reqUNz1MI7zi06tsMHg"
    # Add more cookies here
]

def check_recent_activity(page, profile_url):
    """
    Navigates to the LinkedIn profile first, then to the activity page.
    """
    print(f"Visiting profile: {profile_url}")
    page.goto(profile_url, timeout=60000, wait_until="domcontentloaded")
    time.sleep(random.uniform(3, 5))
    
    username = profile_url.split('/in/')[-1].split('?')[0].rstrip('/')
    activity_url = f"https://www.linkedin.com/in/{username}/recent-activity/all/"
    
    print(f"Checking activity at: {activity_url}")
    page.goto(activity_url, timeout=60000, wait_until="domcontentloaded")
    time.sleep(random.uniform(3, 5))
    
    # Scroll a bit
    page.mouse.wheel(0, 1000)
    time.sleep(2)
    
    # Selectors
    selectors = [
        ".update-components-text-relative-time",
        ".feed-shared-actor__sub-description",
        ".update-components-actor__sub-description"
    ]
    
    time_elements = []
    for sel in selectors:
        elements = page.locator(sel).all()
        time_elements.extend(elements)
    
    is_active = False
    latest_post_date = "No posts found"
    
    for el in time_elements:
        try:
            text = el.inner_text().strip().lower()
            if not text: continue
            
            if any(unit in text for unit in ['h', 'd', 'w', 's', 'm', 'now', 'ago']):
                if 'mo' in text:
                    match = re.search(r'(\d+)\s*mo', text)
                    if match:
                        if int(match.group(1)) <= 2:
                            is_active = True
                            latest_post_date = text
                            break
                elif 'yr' in text or 'year' in text:
                    continue
                else:
                    is_active = True
                    latest_post_date = text
                    break
        except:
            continue
            
    return is_active, latest_post_date
    return is_active, latest_post_date

def test_activity_check(urls):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        
        for i, url in enumerate(urls):
            cookie = LI_AT_COOKIES[i % len(LI_AT_COOKIES)]
            context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
            context.add_cookies([
                {
                    "name": "li_at",
                    "value": cookie,
                    "domain": ".linkedin.com",
                    "path": "/"
                },
                {
                    "name": "JSESSIONID",
                    "value": 'ajax:1234567890123456789',
                    "domain": ".linkedin.com",
                    "path": "/"
                }
            ])
            
            page = context.new_page()
            try:
                active, date = check_recent_activity(page, url)
                print(f"URL: {url} | Active: {active} | Latest: {date}")
                
                # If failed, take a screenshot
                if not active:
                    page.screenshot(path=f"failed_{i}.png")
                
            except Exception as e:
                print(f"Error checking {url}: {e}")
            finally:
                context.close()
            
            # Delay between profiles
            if i < len(urls) - 1:
                delay = random.uniform(5, 10)
                print(f"Waiting {delay:.1f}s...")
                time.sleep(delay)
                
        browser.close()

if __name__ == "__main__":
    test_urls = [
        "https://www.linkedin.com/in/-kylie-watson-/",
        "https://www.linkedin.com/in/3gt/",
        "https://www.linkedin.com/in/abalmer/",
        "https://www.linkedin.com/in/adam-bernero-819071a/",
        "https://www.linkedin.com/in/adam-garner-083449a9/"
    ]
    test_activity_check(test_urls)
