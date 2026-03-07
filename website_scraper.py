from __future__ import annotations

import json
import time
from playwright.sync_api import Page, sync_playwright


def _scroll_page(page, steps: int = 6, delay_s: float = 0.6) -> None:
    for _ in range(steps):
        page.mouse.wheel(0, 800)
        time.sleep(delay_s)


def _follow_linkedin_redirect(page: Page) -> None:
    warning_header = page.locator(
        "h1",
        has_text="not on LinkedIn",
    )
    if warning_header.count() == 0 or not warning_header.first.is_visible():
        return

    print("Detected LinkedIn redirect warning. Attempting to follow link...")
    redirect_link = page.locator("main a[href]").first
    if not redirect_link.is_visible():
        return

    actual_url = redirect_link.get_attribute("href")
    if not actual_url:
        return

    print(f"Found actual URL: {actual_url}")
    page.goto(actual_url, timeout=45000, wait_until="domcontentloaded")
    try:
        page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        print("Network idle timeout after LinkedIn redirect.")


def _extract_visible_text(page: Page) -> str:
    content_locator = page.locator("main")
    if content_locator.count() == 0:
        content_locator = page.locator("body")

    text = content_locator.inner_text().strip()
    if not text:
        text = page.locator("body").inner_text().strip()
    if not text:
        text = page.evaluate("() => document.body ? document.body.innerText : ''").strip()
    return text


def _extract_structural_signals(page: Page) -> dict:
    """
    Extract rich structural signals from the rendered page so the AI
    can make evidence-based judgments about social proof, headlines, CTAs, etc.
    """
    signals = page.evaluate("""() => {
        const result = {
            headlines: [],
            social_proof_signals: [],
            social_proof_count: 0,
            cta_buttons: [],
            cta_links: [],
            forms: [],
            images_with_context: [],
            meta_description: '',
            page_title: ''
        };

        // ── Page metadata ──
        result.page_title = document.title || '';
        const metaDesc = document.querySelector('meta[name="description"]');
        if (metaDesc) result.meta_description = metaDesc.getAttribute('content') || '';

        // ── Headlines (h1, h2, h3) ──
        document.querySelectorAll('h1, h2, h3').forEach((el, i) => {
            if (i < 15) {
                const text = el.innerText?.trim();
                if (text && text.length > 1 && text.length < 500) {
                    result.headlines.push({
                        tag: el.tagName.toLowerCase(),
                        text: text
                    });
                }
            }
        });

        // ── Social Proof Detection ──
        // 1. Look for testimonial / review keywords in text blocks
        const socialKeywords = [
            'testimonial', 'review', 'case study', 'success story',
            'as seen on', 'featured in', 'trusted by', 'used by',
            'companies trust', 'clients', 'customers say',
            'what people say', 'what our', 'hear from',
            'star rating', '★', '⭐', 'out of 5',
            'verified', 'certified', 'award'
        ];

        const allTextBlocks = document.querySelectorAll(
            'p, span, div, blockquote, figcaption, cite, li, h2, h3, h4, h5, h6, section'
        );

        allTextBlocks.forEach(el => {
            const text = (el.innerText || '').toLowerCase().trim();
            if (!text || text.length < 3) return;

            for (const kw of socialKeywords) {
                if (text.includes(kw)) {
                    // Get a short snippet
                    const snippet = el.innerText.trim().substring(0, 200);
                    if (snippet.length > 5) {
                        result.social_proof_signals.push({
                            type: 'text_match',
                            keyword: kw,
                            snippet: snippet
                        });
                    }
                    break;
                }
            }
        });

        // 2. Look for blockquotes (common for testimonials)
        document.querySelectorAll('blockquote').forEach(bq => {
            const text = bq.innerText?.trim();
            if (text && text.length > 10) {
                result.social_proof_signals.push({
                    type: 'blockquote',
                    snippet: text.substring(0, 200)
                });
            }
        });

        // 3. Look for star/rating elements
        const ratingSelectors = [
            '[class*="star"]', '[class*="rating"]', '[class*="review"]',
            '[class*="testimonial"]', '[class*="trust"]', '[class*="proof"]',
            '[class*="badge"]', '[class*="logo-grid"]', '[class*="client"]',
            '[class*="partner"]', '[class*="brand"]', '[class*="featured"]',
            '[data-testimonial]', '[data-review]'
        ];
        
        ratingSelectors.forEach(sel => {
            try {
                document.querySelectorAll(sel).forEach(el => {
                    const text = (el.innerText || '').trim();
                    if (text.length > 3 && text.length < 300) {
                        result.social_proof_signals.push({
                            type: 'css_class_match',
                            selector: sel,
                            snippet: text.substring(0, 200)
                        });
                    }
                });
            } catch(e) {}
        });

        // 4. Look for logo/partner images
        document.querySelectorAll('img').forEach(img => {
            const alt = (img.getAttribute('alt') || '').toLowerCase();
            const src = (img.getAttribute('src') || '').toLowerCase();
            const cls = (img.className || '').toLowerCase();
            const parentCls = (img.parentElement?.className || '').toLowerCase();

            const logoKeywords = ['logo', 'client', 'partner', 'brand', 'trust', 
                                  'company', 'featured', 'press', 'media', 'badge',
                                  'testimonial', 'review', 'avatar', 'headshot'];
            
            for (const kw of logoKeywords) {
                if (alt.includes(kw) || src.includes(kw) || cls.includes(kw) || parentCls.includes(kw)) {
                    result.social_proof_signals.push({
                        type: 'trust_image',
                        alt: img.getAttribute('alt') || '',
                        keyword: kw
                    });
                    break;
                }
            }
        });

        // 5. Count numbers that look like stats (e.g. "10,000+ customers")
        const statsPattern = /\\b\\d[\\d,\\.]+\\+?\\s*(customers?|clients?|users?|companies|businesses|teams?|reviews?|projects?|downloads?|installs?)\\b/gi;
        const bodyText = document.body?.innerText || '';
        const statsMatches = bodyText.match(statsPattern);
        if (statsMatches) {
            statsMatches.forEach(m => {
                result.social_proof_signals.push({
                    type: 'stats_number',
                    snippet: m.trim()
                });
            });
        }

        // Deduplicate and count
        const seen = new Set();
        result.social_proof_signals = result.social_proof_signals.filter(s => {
            const key = s.snippet || s.alt || s.keyword || '';
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        });
        result.social_proof_count = result.social_proof_signals.length;

        // ── CTAs (buttons and prominent links) ──
        document.querySelectorAll('button, [role="button"], input[type="submit"]').forEach(btn => {
            const text = (btn.innerText || btn.value || '').trim();
            if (text && text.length > 0 && text.length < 100) {
                result.cta_buttons.push({
                    text: text,
                    tag: btn.tagName.toLowerCase(),
                    href: btn.getAttribute('href') || null
                });
            }
        });

        document.querySelectorAll('a').forEach(link => {
            const text = link.innerText?.trim();
            const href = link.getAttribute('href') || '';
            const cls = (link.className || '').toLowerCase();
            // Only capture links that look like CTAs (have button-like classes or short actionable text)
            const isCtaLike = cls.includes('btn') || cls.includes('button') || cls.includes('cta') ||
                              cls.includes('action') || cls.includes('primary') || cls.includes('hero');
            const isShortActionable = text && text.length > 1 && text.length < 60;
            
            if (isCtaLike && isShortActionable) {
                result.cta_links.push({
                    text: text,
                    href: href.substring(0, 200),
                    classes: cls.substring(0, 100)
                });
            }
        });

        // ── Forms ──
        document.querySelectorAll('form').forEach(form => {
            const fields = [];
            form.querySelectorAll('input, select, textarea').forEach(field => {
                const type = field.getAttribute('type') || field.tagName.toLowerCase();
                const name = field.getAttribute('name') || field.getAttribute('placeholder') || '';
                if (type !== 'hidden' && type !== 'submit') {
                    fields.push({ type: type, label: name.substring(0, 50) });
                }
            });
            if (fields.length > 0) {
                result.forms.push({
                    field_count: fields.length,
                    fields: fields.slice(0, 10)
                });
            }
        });

        // ── Key images with alt text ──
        document.querySelectorAll('img').forEach((img, i) => {
            if (i < 20) {
                const alt = img.getAttribute('alt') || '';
                if (alt && alt.length > 2) {
                    result.images_with_context.push(alt.substring(0, 100));
                }
            }
        });

        return result;
    }""")

    return signals


def _do_scrape(p, url: str, headless: bool, extra_args: list | None = None, rich: bool = False) -> str | dict | None:
    """Core scrape logic, separated so we can retry with different browser args."""
    launch_args = ["--no-sandbox", "--disable-dev-shm-usage"] + (extra_args or [])
    browser = p.chromium.launch(headless=headless, args=launch_args)
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        viewport={"width": 1280, "height": 800},
        extra_http_headers={
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Referer": "https://www.google.com/",
        }
    )

    page = context.new_page()

    try:
        print(f"Navigating to {url}...")
        page.goto(url, timeout=60000, wait_until="domcontentloaded")
        time.sleep(2)
        
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            print("Network idle timeout, continuing with rendered content.")

        try:
            _follow_linkedin_redirect(page)
        except Exception as e:
            print(f"LinkedIn redirect handling warning: {e}")

        _scroll_page(page)

        text = _extract_visible_text(page)

        if rich:
            # Extract structural signals for enhanced analysis
            try:
                signals = _extract_structural_signals(page)
            except Exception as e:
                print(f"Warning: structural signal extraction failed: {e}")
                signals = {}
            
            return {
                "visible_text": text or "",
                "structural_signals": signals
            } if (text or signals) else None
        
        return text or None

    finally:
        browser.close()


def scrape_generic_website(url: str, headless: bool = True) -> str | None:
    """
    Opens a generic website and extracts the visible text from the rendered page.
    Falls back to HTTP/1.1 if an HTTP/2 protocol error occurs.
    """
    if not url.startswith('http'):
        url = 'https://' + url
    with sync_playwright() as p:
        try:
            return _do_scrape(p, url, headless)
        except Exception as e:
            if "ERR_HTTP2" in str(e):
                print(f"HTTP/2 error for {url}, retrying with HTTP/1.1...")
                try:
                    return _do_scrape(p, url, headless, extra_args=["--disable-http2"])
                except Exception as e2:
                    print(f"HTTP/1.1 fallback also failed: {e2}")
                    return None
            else:
                print(f"Website scrape error: {e}")
                return None


def scrape_website_rich(url: str, headless: bool = True) -> dict | None:
    """
    Opens a website and extracts BOTH visible text AND structural signals
    (social proof, headlines, CTAs, forms, images) for accurate AI analysis.
    Falls back to HTTP/1.1 if an HTTP/2 protocol error occurs.
    """
    if not url.startswith('http'):
        url = 'https://' + url
    with sync_playwright() as p:
        try:
            return _do_scrape(p, url, headless, rich=True)
        except Exception as e:
            if "ERR_HTTP2" in str(e):
                print(f"HTTP/2 error for {url}, retrying with HTTP/1.1...")
                try:
                    return _do_scrape(p, url, headless, extra_args=["--disable-http2"], rich=True)
                except Exception as e2:
                    print(f"HTTP/1.1 fallback also failed: {e2}")
                    return None
            else:
                print(f"Website scrape error: {e}")
                return None