"""
sheets_sync.py
Google Sheets integration for the Leads pipeline.

- Reads existing leads from "Leads Inbox" → Sheet2 (Column A) for deduplication
- Appends net-new leads to Sheet2 after local save
- Gracefully degrades if credentials are missing or API fails
- Uses shared normalisation from utils.py
"""

import os
import gspread
from google.oauth2.service_account import Credentials
from logger import log
from utils import normalise_linkedin_url

# Google Sheets API scopes
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
]

SHEET_TAB_NAME = "Sheet2"

# ── In-memory cache to avoid re-fetching Sheet data every call ──────────
_sheet_cache = {"data": None, "timestamp": 0}
_CACHE_TTL = 300  # 5 minutes


def _normalise(url: str) -> str:
    """Normalise a LinkedIn URL to canonical form using shared utils."""
    result = normalise_linkedin_url(url)
    return result if result else url.strip().rstrip('/')


def _get_client() -> gspread.Client | None:
    """Authenticate with Google Sheets using service account credentials."""
    creds_file = os.getenv("GOOGLE_SHEETS_CREDS", "").strip()
    if not creds_file:
        log("[SheetsSync] GOOGLE_SHEETS_CREDS not set in .env — skipping Sheets sync.")
        return None

    # Resolve relative path to absolute
    if not os.path.isabs(creds_file):
        creds_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), creds_file)

    if not os.path.exists(creds_file):
        log(f"[SheetsSync] Credentials file not found: {creds_file} — skipping Sheets sync.")
        return None

    try:
        creds = Credentials.from_service_account_file(creds_file, scopes=SCOPES)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        log(f"[SheetsSync] Auth failed: {e}")
        return None


def _get_worksheet() -> gspread.Worksheet | None:
    """Get the Sheet2 worksheet from the Leads Inbox spreadsheet."""
    sheet_id = os.getenv("GOOGLE_SHEET_ID", "").strip()
    if not sheet_id:
        log("[SheetsSync] GOOGLE_SHEET_ID not set in .env — skipping Sheets sync.")
        return None

    client = _get_client()
    if not client:
        return None

    try:
        spreadsheet = client.open_by_key(sheet_id)
        worksheet = spreadsheet.worksheet(SHEET_TAB_NAME)
        return worksheet
    except gspread.exceptions.WorksheetNotFound:
        log(f"[SheetsSync] Tab '{SHEET_TAB_NAME}' not found in spreadsheet. Creating it...")
        try:
            spreadsheet = client.open_by_key(sheet_id)
            worksheet = spreadsheet.add_worksheet(title=SHEET_TAB_NAME, rows=1000, cols=5)
            return worksheet
        except Exception as e:
            log(f"[SheetsSync] Failed to create tab: {e}")
            return None
    except Exception as e:
        log(f"[SheetsSync] Failed to open spreadsheet: {e}")
        return None


def load_existing_from_sheet() -> set[str]:
    """
    Read all LinkedIn URLs from Sheet2 Column A.
    Returns a set of normalised URLs.
    Uses in-memory cache to avoid hammering the Google Sheets API.
    """
    import time as _time

    # Check cache
    now = _time.time()
    if _sheet_cache["data"] is not None and (now - _sheet_cache["timestamp"]) < _CACHE_TTL:
        return _sheet_cache["data"]

    worksheet = _get_worksheet()
    if not worksheet:
        return set()

    try:
        # Get all values from Column A (skip header if present)
        col_a = worksheet.col_values(1)
        urls = set()
        for val in col_a:
            val = val.strip()
            if val and 'linkedin.com' in val.lower():
                urls.add(_normalise(val))
        log(f"[SheetsSync] Loaded {len(urls)} existing leads from Sheet2.")

        # Update cache
        _sheet_cache["data"] = urls
        _sheet_cache["timestamp"] = now

        return urls
    except Exception as e:
        log(f"[SheetsSync] Error reading from Sheet2: {e}")
        return set()


def invalidate_cache():
    """Force-clear the sheet cache (call after appending new rows)."""
    _sheet_cache["data"] = None
    _sheet_cache["timestamp"] = 0


def check_duplicates(new_urls: list[str]) -> tuple[set[str], set[str]]:
    """
    Check a list of candidate URLs against Sheet2 for duplicates.

    Args:
        new_urls: List of LinkedIn URLs to check.

    Returns:
        (net_new, duplicates) — both as sets of normalised URLs.
    """
    sheet_existing = load_existing_from_sheet()
    normalised = {_normalise(u) for u in new_urls if u.strip()}

    duplicates = normalised & sheet_existing
    net_new = normalised - sheet_existing

    if duplicates:
        log(f"[SheetsSync] {len(duplicates)} duplicates found in Sheet2.")

    return net_new, duplicates


def append_to_sheet(urls: list[str]) -> int:
    """
    Append new LinkedIn URLs as rows to Sheet2 Column A.

    Args:
        urls: List of LinkedIn URLs to append.

    Returns:
        Number of rows successfully appended.
    """
    if not urls:
        return 0

    worksheet = _get_worksheet()
    if not worksheet:
        return 0

    try:
        # Build rows — each row is a list with one element (Column A)
        rows = [[url] for url in sorted(urls)]
        worksheet.append_rows(rows, value_input_option="RAW")
        log(f"[SheetsSync] Appended {len(rows)} new leads to Sheet2.")

        # Invalidate cache since we just added rows
        invalidate_cache()

        return len(rows)
    except Exception as e:
        log(f"[SheetsSync] Error appending to Sheet2: {e}")
        return 0


if __name__ == "__main__":
    """Quick test — reads existing leads and prints count."""
    from dotenv import load_dotenv
    load_dotenv()

    print("Testing Google Sheets connection...")
    existing = load_existing_from_sheet()
    print(f"Found {len(existing)} existing leads in Sheet2.")

    # Test append with a dummy URL (comment out if you don't want to write)
    # test_result = append_to_sheet(["https://www.linkedin.com/in/test-user-12345/"])
    # print(f"Appended: {test_result}")
