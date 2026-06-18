"""
utils.py
Shared utilities for the LinkedIn Lead pipeline.
Single source of truth for URL normalisation and common patterns.
"""

import re

# ── LinkedIn URL Normalisation ──────────────────────────────────────────────
# Matches linkedin.com/in/slug with any subdomain (www, uk, fr, etc.)
LI_PATTERN = re.compile(
    r'https?://(?:[\w-]+\.)?linkedin\.com/in/([\w\-]+)/?',
    re.IGNORECASE
)

# Slugs that are NOT real profiles
SKIP_SLUGS = frozenset({
    'jobs', 'company', 'school', 'pub', 'feed', 'learning',
    'pulse', 'groups', 'signup', 'login', 'directory',
})


def normalise_linkedin_url(url: str) -> str | None:
    """
    Normalise a LinkedIn profile URL to canonical form.
    - Lowercases the slug (LinkedIn slugs are case-insensitive)
    - Strips subdomains to www
    - Returns None if the URL is invalid or points to a non-profile page
    """
    if not url or not isinstance(url, str):
        return None
    url = url.strip()
    match = LI_PATTERN.search(url)
    if match:
        slug = match.group(1).lower()  # Case-insensitive dedup
        if len(slug) > 2 and slug not in SKIP_SLUGS:
            return f"https://www.linkedin.com/in/{slug}/"
    return None


def is_valid_linkedin_url(url: str) -> bool:
    """Quick check if a string is a plausible LinkedIn profile URL."""
    return normalise_linkedin_url(url) is not None


# ── Serper API helper ───────────────────────────────────────────────────────

def get_serper_keys() -> list[str]:
    import os
    keys = []
    k1 = os.getenv("SERPER_API_KEY")
    if k1: keys.append(k1)
    k2 = os.getenv("SERPER_API_KEY_2")
    if k2: keys.append(k2)
    k3 = os.getenv("SERPER_API_KEY_3")
    if k3: keys.append(k3)
    
    if not keys:
        raise ValueError("SERPER_API_KEY missing from environment")
        
    return keys


def serper_search_single(query: str, api_keys: list[str], timeout: int = 10) -> str | None:
    """
    Quick single-result Google search via Serper.dev.
    Returns the first organic result URL or None.
    Much faster than launching a browser.
    """
    import requests
    for api_key in api_keys:
        try:
            resp = requests.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                json={"q": query, "num": 3},
                timeout=timeout,
            )
            if resp.status_code in (403, 401) or (resp.status_code == 400 and "credit" in resp.text.lower()):
                continue # Key exhausted, try next
                
            if resp.status_code != 200:
                return None
            results = resp.json().get("organic", [])
            # Skip social media and return first real result
            skip = {'linkedin.com', 'facebook.com', 'instagram.com', 'twitter.com', 'x.com'}
            for r in results:
                link = r.get("link", "")
                if not any(s in link for s in skip):
                    return link
            return results[0]["link"] if results else None
        except Exception:
            continue
    return None
