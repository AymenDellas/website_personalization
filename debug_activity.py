"""
Test the rewritten on-page activity check with all 5 URLs.
"""
import os, sys, time, json, random
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.getcwd())
from dotenv import load_dotenv
load_dotenv(os.path.join(os.getcwd(), ".env"))
from scraper import scrape_linkedin_profile

li_at_raw = os.getenv("LI_AT")
cookies = [c.strip() for c in li_at_raw.split(',') if c.strip()]
print(f"Loaded {len(cookies)} cookies")

urls = [
    "https://www.linkedin.com/in/3gt/",
    "https://www.linkedin.com/in/-kylie-watson-/",
    "https://www.linkedin.com/in/abalmer/",
    "https://www.linkedin.com/in/adam-bernero-819071a/",
    "https://www.linkedin.com/in/adam-garner-083449a9/"
]

results = []
for i, url in enumerate(urls):
    cookie = cookies[i % len(cookies)]
    print(f"\n--- [{i+1}/{len(urls)}] {url} [Cookie {i % len(cookies) + 1}] ---")
    
    result = scrape_linkedin_profile(url, headless=True, li_at_cookie=cookie, check_activity=True)
    
    if result:
        entry = {"url": url, "is_active": result['is_active'], "latest_activity_date": result['latest_activity_date']}
        print(f"  => Active: {result['is_active']} | Date: {result['latest_activity_date']}")
    else:
        entry = {"url": url, "error": "Scrape failed"}
        print(f"  => SCRAPE FAILED")
    results.append(entry)
    
    # Brief delay between profiles
    if i < len(urls) - 1:
        delay = random.uniform(3, 6)
        print(f"  Waiting {delay:.1f}s...")
        time.sleep(delay)

print(f"\n{'='*60}")
print("FINAL RESULTS:")
print(json.dumps(results, indent=2))

