"""Quick test of the vision-powered website audit."""
import os, json, sys
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv()

from website_scraper import scrape_website_rich
from website_extractor import extract_website_data

url = "https://youronlinelifecoach.com"
print(f"[1/3] Scraping {url}...")

scraped = scrape_website_rich(url)
if not scraped:
    print("ERROR: Scraping failed!")
    sys.exit(1)

print(f"[2/3] Scrape complete.")
print(f"  - Text length: {len(scraped.get('visible_text', ''))}")
print(f"  - Structural signals keys: {list(scraped.get('structural_signals', {}).keys())}")
print(f"  - Screenshot captured: {'Yes' if scraped.get('screenshot_b64') else 'No'}")
if scraped.get('screenshot_b64'):
    print(f"  - Screenshot base64 size: {len(scraped['screenshot_b64'])} chars")

print(f"\n[3/3] Running AI extraction...")
result = extract_website_data(
    scraped.get('visible_text', ''),
    structural_signals=scraped.get('structural_signals'),
    screenshot_b64=scraped.get('screenshot_b64')
)

if result:
    print("\n=== AI AUDIT RESULT ===")
    print(json.dumps(result, indent=2, ensure_ascii=False))
else:
    print("\nERROR: AI extraction returned None!")
