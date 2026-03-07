import time
from playwright.sync_api import sync_playwright
from logger import log

def search_google(query: str, headless: bool = True) -> str | None:
    """
    Searches Google for the query and returns the first organic URL.
    Returns None if no result found or on error.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, channel="msedge")
        
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
            }
        )
        
        page = context.new_page()
        
        try:
            log(f"Searching Google for: {query}")
            # Go to Google
            page.goto("https://www.google.com/search?q=" + query.replace(" ", "+"), timeout=30000)
            
            # Wait for results
            try:
                page.wait_for_selector("#search", timeout=5000)
            except:
                pass # Continue even if ID not found immediately
            
            # Extract first organic result
            # Selectors for standard organic results (usually div.g a)
            # We skip 'sponsored' by looking for standard 'g' class or similar
            
            # Basic strategy: Get all links in main search area
            links = page.locator("#search a[href^='http']").all()
            
            for link in links:
                url = link.get_attribute("href")
                if not url:
                    continue
                    
                # Filter out google specific links and ads
                if "google.com" in url or "googleadservices" in url:
                    continue
                
                # Filter out social media if query implies company site
                # (Optional, but user wants company sites)
                if "linkedin.com" in url or "facebook.com" in url or "instagram.com" in url:
                    continue
                    
                log(f"Found Google Result: {url}")
                return url
                
            log("No suitable organic result found.")
            return None
            
        except Exception as e:
            log(f"Google Search Error: {e}")
            return None
        finally:
            browser.close()

if __name__ == "__main__":
    print(search_google("OpenAI official site"))
