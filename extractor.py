import os
import json
from openai import OpenAI

def extract_profile_data(profile_text: str) -> dict | None:
    """
    Sends profile text to OpenRouter API to extract specific fields into JSON.
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("Error: OPENROUTER_API_KEY not found in environment variables.")
        return None

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )

    system_prompt = """You are an autonomous scraping and data-extraction agent.
Your job is to extract specific LinkedIn profile data into strict JSON only.

Schema:
{
  "website_url": string | null,
  "company_name": string | null
}

EXTRACTION RULES:
1. website_url: Look for any personal or company website link. 
   - **PRIORITY:** Check the "--- CONTACT INFO SECTION ---" first. This contains the most accurate links.
   - Check the "Headline" or "About" section as a backup.
   - Look for patterns like "bossname.com" or "company-site.io".
   - IGNORE Social Media links (linkedin.com, twitter.com, x.com, facebook.com, instagram.com).
   - If multiple are found, prioritize the professional company website.
   - Return the full absolute URL (including https://).

2. company_name: Extract the name of the CURRENT company they work for.
   - Check the "Headline" (e.g., "CEO at Acme Corp").
   - Check the "About" section.
   - If self-employed, extract their business name.

CONSTRAINTS:
- Do NOT fabricate info.
- If no website is found, return null.
- Output JSON ONLY.
"""

    try:
        completion = client.chat.completions.create(
            model="openai/gpt-4o-mini", # Upgraded for better reasoning
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Profile Text:\n{profile_text}"}
            ],
            temperature=0, 
        )

        content = completion.choices[0].message.content.strip()
        
        # Helper to parse strict JSON (strip potential markdown wrapping)
        if content.startswith("```json"):
            content = content[7:]
        if content.endswith("```"):
            content = content[:-3]
        
        return json.loads(content)

    except Exception as e:
        print(f"Extraction error: {e}")
        return None
