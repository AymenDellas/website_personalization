"""
leads_store.py
Manages the persistent leads file (discovered_leads.txt).
- Deduplicates against existing leads on every save
- Thread-safe (uses a file lock)
- Survives server restarts — file is never wiped
- Uses shared normalisation from utils.py
"""

import os
import threading
from logger import log
from utils import normalise_linkedin_url

# Leads file lives in the project root — persists across restarts
LEADS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "discovered_leads.txt")

_lock = threading.Lock()


def _normalise(url: str) -> str:
    """Normalise a LinkedIn URL to a canonical form using shared utils."""
    result = normalise_linkedin_url(url)
    return result if result else url.strip().rstrip('/')


def load_existing() -> set[str]:
    """Load all existing leads from file as a set of normalised URLs."""
    if not os.path.exists(LEADS_FILE):
        return set()
    with open(LEADS_FILE, "r", encoding="utf-8") as f:
        lines = [_normalise(line) for line in f if line.strip()]
    return set(lines)


def save_new_leads(new_urls: list[str]) -> dict:
    """
    Save new leads to file, deduplicating against both the local file
    AND Google Sheets (Sheet2 in "Leads Inbox").

    After saving locally, net-new leads are also appended to Sheet2.

    Args:
        new_urls: List of LinkedIn URLs discovered this run.

    Returns:
        {
            "added": int,       # net-new leads saved
            "duplicates": int,  # how many were already known (local + sheet)
            "total": int        # total leads in file after save
        }
    """
    with _lock:
        existing_local = load_existing()
        normalised_new = {_normalise(u) for u in new_urls if u.strip()}

        # --- Check Google Sheets for additional duplicates ---
        sheet_dupes = set()
        try:
            from sheets_sync import load_existing_from_sheet
            existing_sheet = load_existing_from_sheet()
            sheet_dupes = normalised_new & existing_sheet
            if sheet_dupes:
                log(f"[LeadsStore] {len(sheet_dupes)} duplicates found in Google Sheet.")
        except Exception as e:
            log(f"[LeadsStore] Google Sheets dedup check failed (continuing anyway): {e}")

        # Combine all known duplicates (local file + sheet)
        all_known = existing_local | sheet_dupes
        duplicates = normalised_new & all_known
        net_new = normalised_new - all_known

        # Save net-new to local file
        if net_new:
            with open(LEADS_FILE, "a", encoding="utf-8") as f:
                for url in sorted(net_new):
                    f.write(url + "\n")

        total = len(existing_local) + len(net_new)

        # --- Push net-new leads to Google Sheets (Sheet2) ---
        if net_new:
            try:
                from sheets_sync import append_to_sheet
                append_to_sheet(list(net_new))
            except Exception as e:
                log(f"[LeadsStore] Google Sheets append failed (leads saved locally): {e}")

        log(f"[LeadsStore] Saved {len(net_new)} new leads | "
            f"{len(duplicates)} duplicates skipped | "
            f"{total} total in file")

        return {
            "added": len(net_new),
            "duplicates": len(duplicates),
            "total": total
        }


def get_all_leads() -> list[str]:
    """Return all leads currently in the file as a sorted list."""
    return sorted(load_existing())


def get_lead_count() -> int:
    """Return count of leads in file."""
    return len(load_existing())


def clear_all_leads() -> int:
    """Clear the leads file. Returns count of leads deleted."""
    with _lock:
        count = len(load_existing())
        if os.path.exists(LEADS_FILE):
            os.remove(LEADS_FILE)
        log(f"[LeadsStore] Cleared {count} leads from file.")
        return count


def delete_lead(url: str) -> bool:
    """Remove a specific lead from the file. Returns True if found and removed."""
    with _lock:
        existing = load_existing()
        target = _normalise(url)
        if target not in existing:
            return False
        remaining = existing - {target}
        with open(LEADS_FILE, "w", encoding="utf-8") as f:
            for u in sorted(remaining):
                f.write(u + "\n")
        log(f"[LeadsStore] Deleted lead: {target}")
        return True


if __name__ == "__main__":
    # Quick test
    test_urls = [
        "https://www.linkedin.com/in/john-smith/",
        "https://linkedin.com/in/jane-doe",
        "  https://www.linkedin.com/in/John-Smith  ",  # duplicate (case-insensitive now)
        "https://www.linkedin.com/in/bob-coach/",
    ]
    result = save_new_leads(test_urls)
    print(f"Result: {result}")
    print(f"All leads: {get_all_leads()}")
