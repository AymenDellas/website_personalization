import sys
import json
import os
from dotenv import load_dotenv
from scraper import scrape_linkedin_profile
from extractor import extract_profile_data

# Load environment variables
load_dotenv()

def main():
    if len(sys.argv) < 2:
        print("Usage: python main.py <linkedin_url>")
        sys.exit(1)

    url = sys.argv[1]
    print(f"Starting job for: {url}")

    # Step 1: Scrape
    print("Step 1: Scraping profile...")
    
    li_at = os.getenv("LI_AT")
    if not li_at:
        print("WARNING: LI_AT (LinkedIn session cookie) not found in .env. Scrape may fail due to login wall.")
    
    result = scrape_linkedin_profile(url, headless=True, li_at_cookie=li_at, check_activity=True)
    
    if not result:
        print("Failed to extract text from profile.")
        sys.exit(1)
    
    # Debug: Save raw text
    # with open("debug_raw.txt", "w", encoding="utf-8") as f:
    #    f.write(text)

    # Step 2: Extract
    print("Step 2: Extracting data...")
    data = extract_profile_data(result['visible_text'])

    if data:
        data['is_active'] = result['is_active']
        data['latest_activity_date'] = result['latest_activity_date']
        print(json.dumps(data, indent=2))
        
        # Save to output file
        with open("output.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print("Saved to output.json")
    else:
        print("Extraction failed.")

if __name__ == "__main__":
    main()
