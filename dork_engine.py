"""
dork_engine.py  — v4.0 (Insane Mode)
Discovers LinkedIn profile URLs using Serper.dev (Google Search API).

Three-layer quality filtering:
  Layer 1: Parse actual job headline from Google result title (not fuzzy keyword match)
  Layer 2: HTTP pre-qualification — grab LinkedIn <title> tag (no login) to verify headline
  Layer 3: Negative keywords in queries to exclude noise at the Google level

Plus: compound-phrase relevance, smart dedup, retry with backoff, quota tracking.

Serper.dev:
- 2,500 free queries (no credit card)
- Returns real Google results as clean JSON
- No CAPTCHAs, no proxies, no org policies

Setup:
1. Go to https://serper.dev and sign up (free, 30 seconds)
2. Copy your API key from the dashboard
3. Add to .env: SERPER_API_KEY=your_key
"""

import re
import os
import time
import random
import json
import requests
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from logger import log
from utils import normalise_linkedin_url

load_dotenv()

# ── Serper quota tracking ─────────────────────────────────────────────────
QUOTA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "serper_quota.json")
FREE_TIER_LIMIT = 2500


def _load_quota() -> dict:
    """Load persistent quota tracker."""
    if os.path.exists(QUOTA_FILE):
        try:
            with open(QUOTA_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"total_used": 0, "last_reset": None}


def _save_quota(data: dict):
    """Save quota tracker to disk."""
    try:
        with open(QUOTA_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        log(f"[DorkEngine] Warning: could not save quota file: {e}")


def _increment_quota(count: int = 1):
    """Track Serper API usage."""
    q = _load_quota()
    q["total_used"] = q.get("total_used", 0) + count
    _save_quota(q)
    used = q["total_used"]
    remaining = FREE_TIER_LIMIT - used
    if remaining < 500:
        log(f"[DorkEngine] ⚠️  Serper quota warning: {used}/{FREE_TIER_LIMIT} used, {remaining} remaining")
    return used


# ── Noise domain filtering ────────────────────────────────────────────────
# Directory / aggregator domains — results linking to these are listing pages, not real profiles
NOISE_DOMAINS = frozenset({
    'coachfoundation.com', 'noomii.com', 'thumbtack.com', 'bark.com',
    'yelp.com', 'glassdoor.com', 'indeed.com', 'ziprecruiter.com',
    'crunchbase.com', 'clutch.co', 'g2.com', 'trustpilot.com',
    'topresume.com', 'thecoachingacademy.com', 'lifecoachmagazine.com',
    'coaching-online.org', 'life-coach-directory.com', 'findacoach.com',
    'coachingfederation.org', 'coachingaggregator.com', 'betterup.com',
    'tonyrobbins.com', 'udemy.com', 'coursera.org',
})

# Negative keywords — exclude profiles with these in their headline
# These are people who have "coach" somewhere but aren't actually coaches
NEGATIVE_KEYWORDS = [
    'recruiter', 'software engineer', 'developer', 'sales manager',
    'project manager', 'product manager', 'data scientist', 'accountant',
    'human resources', 'HR manager', 'marketing manager', 'nurse',
    'teacher', 'professor', 'attorney', 'lawyer', 'dentist', 'doctor',
    'real estate', 'insurance agent',
]


def _is_noise_domain(url: str) -> bool:
    """Check if URL comes from a known directory/noise domain using proper parsing."""
    try:
        host = urlparse(url).hostname or ""
        host = host.lower()
        for d in NOISE_DOMAINS:
            if host == d or host.endswith("." + d):
                return True
    except Exception:
        pass
    return False


# ── Niche relevance filtering ─────────────────────────────────────────────

def _extract_niche_signals(job_titles: list[str]) -> dict:
    """
    Build a multi-tier relevance filter from job titles.

    Returns:
        {
            "phrases": {"business coach", "life coach", ...},
            "role_words": {"coach", "mentor", "consultant"},
            "titles_lower": ["business coach", "life coach", ...],  # For headline parsing
        }
    """
    phrases = set()
    role_words = set()
    titles_lower = []

    # Known role-defining words and their variants
    ROLE_STEMS = {
        'coach': ['coach', 'coaching'],
        'mentor': ['mentor', 'mentoring', 'mentorship'],
        'consultant': ['consultant', 'consulting'],
        'trainer': ['trainer', 'training'],
        'advisor': ['advisor', 'adviser', 'advisory'],
        'strategist': ['strategist', 'strategy'],
        'counselor': ['counselor', 'counsellor', 'counseling', 'counselling'],
        'therapist': ['therapist', 'therapy'],
        'facilitator': ['facilitator', 'facilitation'],
    }

    for title in job_titles:
        title_lower = title.lower().strip()
        titles_lower.append(title_lower)

        # Add the full title as a phrase
        phrases.add(title_lower)

        words = title_lower.split()

        # Build bigrams (e.g., "business coach", "life mentor")
        for i in range(len(words) - 1):
            bigram = f"{words[i]} {words[i+1]}"
            phrases.add(bigram)

        # Extract role words and their variants
        for word in words:
            for stem, variants in ROLE_STEMS.items():
                if word in variants or word == stem:
                    role_words.update(variants)

    # Remove overly generic words that snuck in
    GENERIC_WORDS = {'a', 'an', 'the', 'and', 'or', 'of', 'for', 'in', 'at', 'to',
                     'business', 'life', 'career', 'executive', 'leadership',
                     'performance', 'personal', 'professional', 'senior', 'chief'}

    # Keep these ONLY in phrases, never as standalone keywords
    role_words -= GENERIC_WORDS

    log(f"[DorkEngine] Relevance filter — phrases: {sorted(phrases)}")
    log(f"[DorkEngine] Relevance filter — role words: {sorted(role_words)}")
    return {"phrases": phrases, "role_words": role_words, "titles_lower": titles_lower}


# ═══════════════════════════════════════════════════════════════════════════
# LAYER 1: Parse headline from Google result title
# ═══════════════════════════════════════════════════════════════════════════

def _extract_headline_from_google_title(google_title: str) -> str | None:
    """
    Parse the actual LinkedIn headline from a Google result title.

    LinkedIn's Google listing format is always one of:
        "John Smith - Business Coach - LinkedIn"
        "John Smith - Business Coach at CoachCo | LinkedIn"
        "John Smith - Business Coach | LinkedIn"
        "John Smith – Business Coach – LinkedIn"  (em-dash variant)

    Returns the headline portion (e.g. "Business Coach at CoachCo") or None.
    """
    if not google_title:
        return None

    # Normalize dashes (em-dash, en-dash → regular dash)
    title = google_title.replace('–', '-').replace('—', '-')

    # Remove " | LinkedIn" or " - LinkedIn" from the end
    title = re.sub(r'\s*[\|\-]\s*LinkedIn\s*$', '', title, flags=re.IGNORECASE).strip()

    # Now split on " - " to get [Name, Headline, ...]
    parts = [p.strip() for p in title.split(' - ') if p.strip()]

    if len(parts) >= 2:
        # The headline is everything after the first part (name)
        # Rejoin in case there are multiple dashes in the headline
        headline = ' - '.join(parts[1:])
        return headline.lower()

    return None


def _is_result_relevant(item: dict, niche_signals: dict) -> tuple[bool, str]:
    """
    Check whether a Google result is actually relevant to the target niche.

    LAYER 1 — Headline parsing (highest precision):
      Parse the actual job title from the Google result title format
      "Name - Headline | LinkedIn" and check if the HEADLINE matches.

    Returns:
        (is_relevant, confidence)
        confidence can be 'high' (exact phrase match in headline),
        'low' (role word match or fallback snippet match), or 'none'.
    """
    title = (item.get("title") or "")
    snippet = (item.get("snippet") or "").lower()
    link = (item.get("link") or "").lower()

    # Skip noise domains
    if _is_noise_domain(link):
        return False, "none"

    # ── LAYER 1: Parse headline from Google result title ──
    headline = _extract_headline_from_google_title(title)

    if headline:
        # Check if any target phrase appears in the parsed headline
        for phrase in niche_signals["phrases"]:
            if phrase in headline:
                return True, "high"

        # Check if any role word appears in the headline
        for rw in niche_signals["role_words"]:
            # Use word boundary check — "coach" shouldn't match "coachella"
            if re.search(r'\b' + re.escape(rw) + r'\b', headline):
                return True, "low"

        # Headline was parsed but contains NO niche signal — this person
        # is not a coach/mentor. Reject even if snippet mentions coaching.
        return False, "none"

    # ── Fallback: headline parsing failed — use combined text ──
    combined = f"{title.lower()} {snippet}"

    for phrase in niche_signals["phrases"]:
        if phrase in combined:
            return True, "low"

    for rw in niche_signals["role_words"]:
        if rw in combined:
            return True, "low"

    return False, "none"


# ═══════════════════════════════════════════════════════════════════════════
# LAYER 2: Google Cache Verification (no login, no li_at, no 999 blocks)
# ═══════════════════════════════════════════════════════════════════════════
#
# LinkedIn blocks unauthenticated HTTP requests with status 999.
# But Google has already cached every profile's headline in its index.
# We use Serper to query Google's cached version of each profile.
#
# Cost: 1 Serper credit per candidate URL (~200ms each).
# This is worth it because each URL that passes here will cost your
# worker pipeline 30-60 seconds of browser time. Spending 1 credit
# to avoid a 60-second false positive is a massive win.


def _prequalify_via_google(url: str, api_keys: list[str], niche_signals: dict) -> tuple[str, bool, str]:
    """
    Pre-qualify a LinkedIn URL by asking Google what the person's headline is.
    Uses a targeted site-specific Serper query.

    No li_at cookie needed. No direct LinkedIn contact. Uses Google's cache.

    Returns: (url, passed, reason)
    """
    try:
        # Extract the slug from the URL
        slug_match = re.search(r'/in/([\w\-]+)', url)
        if not slug_match:
            return (url, True, "bad_url")

        slug = slug_match.group(1)

        # Ask Google specifically about this profile
        query = f'site:linkedin.com/in/{slug}'
        resp = None
        for api_key in api_keys:
            resp = requests.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                json={"q": query, "num": 1},
                timeout=10,
            )
            if resp.status_code in (403, 401) or (resp.status_code == 400 and "credit" in resp.text.lower()):
                continue # Key exhausted, rotate
            break

        if resp is None or resp.status_code != 200:
            return (url, True, f"serper_http_{resp.status_code if resp else 'error'}")

        _increment_quota(1)

        results = resp.json().get("organic", [])
        if not results:
            # Google doesn't have this profile indexed — keep it, Layer 1 already approved
            return (url, True, "not_indexed")

        # Parse headline from Google's cached result title
        google_title = results[0].get("title", "")
        headline = _extract_headline_from_google_title(google_title)

        if not headline:
            return (url, True, "parse_failed")

        # Check if the REAL headline (from Google's cache) matches our niche
        for phrase in niche_signals["phrases"]:
            if phrase in headline:
                return (url, True, f"verified:{phrase}")

        for rw in niche_signals["role_words"]:
            if re.search(r'\b' + re.escape(rw) + r'\b', headline):
                return (url, True, f"verified:{rw}")

        # Google's cached headline does NOT contain any coaching signal
        return (url, False, f"off_niche:{headline[:60]}")

    except Exception as e:
        # On any error, give benefit of the doubt (Layer 1 already approved)
        return (url, True, f"error:{str(e)[:40]}")


def _prequalify_batch(urls: list[str], api_keys: list[str], niche_signals: dict,
                      max_workers: int = 3, stop_event=None) -> list[str]:
    """
    Pre-qualify a batch of LinkedIn URLs using Google Cache verification.
    Uses parallel Serper queries (3 concurrent by default to be polite).

    Cost: 1 Serper credit per URL checked.

    Returns only the URLs that pass pre-qualification.
    """
    if not urls:
        return []

    log(f"[PreQual] Layer 2: Verifying {len(urls)} URLs via Google cache (no login)...")
    passed = []
    rejected = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_prequalify_via_google, url, api_keys, niche_signals): url
            for url in urls
        }

        for future in as_completed(futures):
            if stop_event and stop_event.is_set():
                break

            url, is_valid, reason = future.result()

            if is_valid:
                passed.append(url)
                if "verified:" in reason:
                    log(f"[PreQual]   VERIFIED: {url.split('/in/')[-1][:30]} ({reason})")
            else:
                rejected += 1
                log(f"[PreQual]   REJECTED: {url.split('/in/')[-1][:30]} -- {reason}")

    log(f"[PreQual] Result: {len(passed)} passed, {rejected} rejected "
        f"({len(passed)}/{len(urls)} = {len(passed)*100//max(len(urls),1)}% pass rate)")
    return passed


# ── Query generation ──────────────────────────────────────────────────────

def _build_negative_string(config: dict) -> str:
    """
    Build the negative keyword exclusion string for Google queries.
    Uses config-level overrides if provided, otherwise uses defaults.
    """
    negatives = config.get("negative_keywords", NEGATIVE_KEYWORDS)
    if not negatives:
        return ""
    # Limit to 8 negative keywords per query (Google has a length limit)
    negatives = negatives[:8]
    return " " + " ".join(f'-"{n}"' for n in negatives)


def _build_queries(config: dict) -> list[str]:
    """
    Build targeted search queries from config.
    Uses ONLY the site: operator strategy (Serper handles it correctly).
    Includes negative keywords to exclude noise at the Google level.
    """
    queries = []
    titles = config.get("job_titles", [])
    locations = config.get("locations", [])
    neg_string = _build_negative_string(config)

    for title in titles:
        for location in locations:
            # site: operator + exact title + location + negative exclusions
            queries.append(f'site:linkedin.com/in "{title}" "{location}"{neg_string}')

    # Deduplicate and shuffle for even coverage
    seen = set()
    unique = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            unique.append(q)

    random.shuffle(unique)
    log(f"[DorkEngine] Generated {len(unique)} queries with {len(config.get('negative_keywords', NEGATIVE_KEYWORDS)[:8])} negative filters")
    return unique


# ── Serper API call with retry ────────────────────────────────────────────

def _serper_search(query: str, api_keys: list[str], num: int = 10, page: int = 1,
                   max_retries: int = 3) -> list[dict] | None:
    """
    Search via Serper.dev API with exponential backoff on 429s.
    Returns list of organic results, empty list on exhaustion, or None on auth error.
    """
    url = "https://google.serper.dev/search"
    payload = {
        "q": query,
        "num": num,
        "page": page,
    }

    for api_key in api_keys:
        headers = {
            "X-API-KEY": api_key,
            "Content-Type": "application/json"
        }
        
        for attempt in range(max_retries):
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=15)

                if resp.status_code == 429:
                    wait = 10 * (2 ** attempt)  # 10s, 20s, 40s
                    log(f"[DorkEngine] Serper rate limit (429). Retry {attempt+1}/{max_retries} in {wait}s...")
                    time.sleep(wait)
                    continue

                if resp.status_code in (403, 401):
                    log(f"[DorkEngine] Serper auth error {resp.status_code}. Rotating to next key if available.")
                    break # Break inner retry loop to go to next key

                # Detect "Not enough credits"
                if resp.status_code == 400:
                    body = resp.text[:200]
                    if "Not enough credits" in body or "not enough credits" in body:
                        log(f"[DorkEngine] CREDITS EXHAUSTED on this key. Rotating...")
                        break # Break inner retry loop to go to next key
                    log(f"[DorkEngine] Serper HTTP 400: {body}")
                    return []

                if resp.status_code != 200:
                    log(f"[DorkEngine] Serper HTTP {resp.status_code}: {resp.text[:200]}")
                    return []

                # Track quota
                _increment_quota(1)

                data = resp.json()
                return data.get("organic", [])

            except requests.exceptions.Timeout:
                log(f"[DorkEngine] Serper timeout. Retry {attempt+1}/{max_retries}...")
                time.sleep(5 * (attempt + 1))
            except Exception as e:
                log(f"[DorkEngine] Serper request failed: {e}")
                return []

    log(f"[DorkEngine] Serper: All keys or retries exhausted for query.")
    return []


# ── URL extraction from results ──────────────────────────────────────────

def _extract_urls_from_results(results: list[dict], niche_signals: dict) -> tuple[set[str], set[str], int]:
    """
    Extract LinkedIn profile URLs from Serper result items.
    Only accepts URLs from results that pass LAYER 1 relevance filtering
    (headline parsing from Google result title).

    Returns:
        (high_conf_urls, low_conf_urls, rejected_count)
    """
    high_conf = set()
    low_conf = set()
    rejected = 0

    for item in results:
        link = item.get("link", "")

        # Only accept direct LinkedIn profile links
        norm = normalise_linkedin_url(link)
        if not norm:
            continue

        # LAYER 1: headline-based relevance gate
        is_relevant, conf = _is_result_relevant(item, niche_signals)
        if is_relevant:
            if conf == "high":
                high_conf.add(norm)
            else:
                low_conf.add(norm)
        else:
            title_preview = (item.get("title") or "")[:60]
            log(f"[DorkEngine]   SKIPPED (off-niche): {title_preview}")
            rejected += 1

    return high_conf, low_conf, rejected


# ── Main runner ──────────────────────────────────────────────────────────

def run(
    proxy_pool=None,
    config: dict = None,
    stop_event=None,
    progress_callback=None
) -> list[str]:
    """
    Main search runner using Serper.dev with three-layer quality filtering.
    """
    if config is None:
        config = {}

    from utils import get_serper_keys
    api_keys = get_serper_keys()

    if not api_keys:
        log("[DorkEngine] ERROR: SERPER_API_KEY not set in .env")
        log("[DorkEngine] Setup (30 seconds):")
        log("[DorkEngine]   1. Go to https://serper.dev and sign up (free)")
        log("[DorkEngine]   2. Copy your API key from the dashboard")
        log("[DorkEngine]   3. Add to .env: SERPER_API_KEY=your_key")
        return []

    # Log quota status
    quota = _load_quota()
    remaining = FREE_TIER_LIMIT - quota.get("total_used", 0)
    log(f"[DorkEngine] Serper quota: {quota.get('total_used', 0)}/{FREE_TIER_LIMIT} used ({remaining} remaining)")

    # Build niche signals from configured job titles for relevance filtering
    niche_signals = _extract_niche_signals(config.get("job_titles", []))

    queries = _build_queries(config)
    max_target = config.get("max_urls_target", 500)
    max_pages = min(config.get("max_pages_per_dork", 3), 5)  # Cap at 5
    prequal_enabled = config.get("prequalify", True)  # Layer 2 ON by default but uses smart mode

    all_urls: set[str] = set()
    prequal_pending: set[str] = set()  # URLs awaiting Layer 2 verification
    total_queries = len(queries)
    queries_used = 0
    total_rejected_l1 = 0  # Rejected by Layer 1 (headline parsing)
    total_rejected_l2 = 0  # Rejected by Layer 2 (Google cache verification)
    auth_failed = False
    consecutive_dry_pages = 0

    log(f"[DorkEngine] Starting -- {total_queries} queries, target {max_target} URLs, max {max_pages} pages/query")
    log(f"[DorkEngine] Layer 2 pre-qualification: {'ON' if prequal_enabled else 'OFF'}")

    for q_idx, query in enumerate(queries):
        if stop_event and stop_event.is_set():
            log("[DorkEngine] Stop requested -- halting.")
            break

        if len(all_urls) + len(prequal_pending) >= max_target:
            log(f"[DorkEngine] Reached target of {max_target} URLs. Done.")
            break

        if auth_failed:
            break

        log(f"[DorkEngine] Query {q_idx + 1}/{total_queries}: {query[:100]}...")

        for page in range(1, max_pages + 1):
            if stop_event and stop_event.is_set():
                break
            if len(all_urls) + len(prequal_pending) >= max_target:
                break

            results = _serper_search(query, api_keys, num=10, page=page)
            queries_used += 1

            if results is None:
                auth_failed = True
                break

            if not results:
                break

            # Layer 1: headline-based filtering
            high_conf, low_conf, rejected = _extract_urls_from_results(results, niche_signals)
            total_rejected_l1 += rejected
            
            new_high = high_conf - all_urls - prequal_pending
            new_low = low_conf - all_urls - prequal_pending
            
            all_urls.update(new_high)
            prequal_pending.update(new_low)

            if new_high or new_low:
                consecutive_dry_pages = 0
                log(f"[DorkEngine] Page {page}: +{len(new_high)} high-conf, +{len(new_low)} low-conf "
                    f"(pending L2: {len(prequal_pending)}, L1 rejected: {rejected})")
            else:
                consecutive_dry_pages += 1
                log(f"[DorkEngine] Page {page}: no new profiles -- next query")
                if consecutive_dry_pages >= 2:
                    log(f"[DorkEngine] Diminishing returns detected — skipping remaining pages")
                break

            # Progress callback (show pending count for now)
            if progress_callback:
                progress_callback(len(all_urls) + len(prequal_pending), total_queries, q_idx + 1, query)

            if page < max_pages:
                time.sleep(random.uniform(0.3, 0.8))

        # ── Run Layer 2 pre-qualification in batches ──
        # Process every ~30 URLs or at the end of each query to keep feedback flowing
        if prequal_enabled and len(prequal_pending) >= 30:
            batch = list(prequal_pending)
            prequal_pending.clear()
            verified = _prequalify_batch(batch, api_keys, niche_signals, max_workers=3, stop_event=stop_event)
            total_rejected_l2 += len(batch) - len(verified)
            all_urls.update(verified)
            log(f"[DorkEngine] After Layer 2: {len(all_urls)} verified leads total")

        # Delay between queries
        if q_idx < total_queries - 1 and not auth_failed:
            time.sleep(random.uniform(0.5, 1.5))

        # Update progress
        if progress_callback:
            progress_callback(len(all_urls) + len(prequal_pending), total_queries, q_idx + 1, query)

    # ── Final Layer 2 pass on remaining pending URLs ──
    if prequal_enabled and prequal_pending:
        batch = list(prequal_pending)
        prequal_pending.clear()
        verified = _prequalify_batch(batch, api_keys, niche_signals, max_workers=3, stop_event=stop_event)
        total_rejected_l2 += len(batch) - len(verified)
        all_urls.update(verified)
    elif not prequal_enabled:
        # If pre-qual is off, accept all pending URLs
        all_urls.update(prequal_pending)

    result = sorted(list(all_urls))
    log(f"[DorkEngine] ═══ COMPLETE ═══")
    log(f"[DorkEngine] {len(result)} verified LinkedIn URLs discovered")
    log(f"[DorkEngine] {queries_used} Serper queries used")
    log(f"[DorkEngine] {total_rejected_l1} rejected by Layer 1 (headline parse)")
    log(f"[DorkEngine] {total_rejected_l2} rejected by Layer 2 (Google cache verification)")
    log(f"[DorkEngine] Pipeline: {total_rejected_l1 + total_rejected_l2 + len(result)} total candidates "
        f"→ {len(result)} verified ({len(result)*100//max(total_rejected_l1+total_rejected_l2+len(result),1)}% pass rate)")
    return result


if __name__ == "__main__":
    """Quick standalone test"""
    import threading

    with open("dorks_config.json") as f:
        cfg = json.load(f)

    cfg["max_urls_target"] = 20
    cfg["max_pages_per_dork"] = 1
    cfg["job_titles"] = ["Executive Coach"]
    cfg["locations"] = ["London"]

    stop = threading.Event()
    urls = run(config=cfg, stop_event=stop)
    print(f"\nFound {len(urls)} LinkedIn URLs:")
    for u in urls:
        print(f"  {u}")
