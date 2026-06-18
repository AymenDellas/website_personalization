"""
google_searcher.py
Lightweight Google search using Serper.dev API.
Replaced the heavy Playwright-based browser approach — 200ms vs 5-10 seconds per query.
"""

import os
from dotenv import load_dotenv
from logger import log
from utils import serper_search_single, get_serper_keys

load_dotenv()


def search_google(query: str, headless: bool = True) -> str | None:
    """
    Searches Google for the query and returns the first organic URL.
    Returns None if no result found or on error.

    Uses Serper.dev API instead of launching a browser.
    The `headless` parameter is kept for backward compatibility but is ignored.
    """
    api_keys = get_serper_keys()

    if not api_keys:
        log("[GoogleSearch] SERPER_API_KEY not set — cannot search")
        return None

    log(f"[GoogleSearch] Searching: {query}")

    result = serper_search_single(query, api_keys)

    if result:
        log(f"[GoogleSearch] Found: {result}")
    else:
        log("[GoogleSearch] No suitable result found.")

    return result


if __name__ == "__main__":
    print(search_google("OpenAI official site"))
