import os
import json
import time
from openai import OpenAI

def extract_website_data(website_text: str, structural_signals: dict | None = None, screenshot_b64: str | None = None) -> dict | None:
    """
    Analyzes website text + structural signals using AI
    to generate a single personalized hook line for cold email outreach.
    Primary: Groq (llama-3.3-70b-versatile) with automatic fallback across multiple keys.
    Fallback: Cerebras (llama3.1-8b).
    """
    cerebras_key = os.getenv("CEREBRAS_API_KEY")
    groq_key_1 = os.getenv("GROQ_API_KEY")
    groq_key_2 = os.getenv("GROQ_API_KEY_2")
    
    groq_keys = [k for k in [groq_key_1, groq_key_2] if k]
    
    if not cerebras_key and not groq_keys:
        print("Error: No API keys found.", flush=True)
        return None

    # Setup clients in order of preference
    clients = []
    for idx, key in enumerate(groq_keys):
        clients.append(("Groq (Key " + str(idx+1) + ")", "llama-3.3-70b-versatile", OpenAI(base_url="https://api.groq.com/openai/v1", api_key=key)))
    if cerebras_key:
        clients.append(("Cerebras", "llama3.1-8b", OpenAI(base_url="https://api.cerebras.ai/v1", api_key=cerebras_key)))

    system_prompt = """You are an expert at writing personalized cold email opening lines for a funnel agency targeting coaches.

Your job is to read a coach's website and write ONE opening line that will be used as the first sentence of a cold email.

RULES:
- The line must reference something SPECIFIC from their website: their niche, their method, their audience, their results, their story, or their positioning.
- It must feel like the sender actually read their site, not generic flattery.
- It must be conversational and flow naturally as a standalone sentence.
- Max 20 words.
- No em dashes. No quotes. No filler like "I noticed" or "I came across your site".
- ALWAYS start with "Your" — never start with the person's name, company name, or any third-party reference.
- Capitalize normally as a real sentence. Proper nouns capitalized.
- Output STRICT JSON only. No markdown. No backticks.

SCHEMA:
{"hook": string}

GOOD EXAMPLES:
{"hook": "Your three decades of expertise in exit strategies suggest you appreciate systems built on actual performance."}
{"hook": "Your blend of trauma-informed coaching and corporate pricing expertise creates a powerful differentiator for executive women."}
{"hook": "Building a practice around helping burned-out executives reclaim clarity puts you in a category most coaches never reach."}

BAD EXAMPLES:
{"hook": "I noticed you have a coaching business."} — too generic
{"hook": "Your website is impressive."} — flattery, not specific
{"hook": "As a life coach, you help people."} — no differentiation
{"hook": "Alex Wisch's 360-degree approach..."} — starts with name, not "Your"
"""

    try:
        truncated_text = website_text[:8000]
        text_content = f"Website Visible Text:\n{truncated_text}"

        if structural_signals:
            signals_summary = _summarize_signals(structural_signals)
            text_content += f"\n\n---\n\nSTRUCTURAL SIGNALS (extracted from HTML):\n{signals_summary}"

        user_message = {"role": "user", "content": text_content}

        completion = None
        success = False
        last_error = None
        
        for provider_name, model_name, ai_client in clients:
            print(f"Using {provider_name} ({model_name}) for hook generation", flush=True)
            max_retries = 2
            
            for attempt in range(max_retries):
                try:
                    completion = ai_client.chat.completions.create(
                        model=model_name,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            user_message
                        ],
                        temperature=0,
                        timeout=20.0,
                    )
                    success = True
                    break
                except Exception as e:
                    last_error = e
                    error_str = str(e).lower()
                    if "429" in error_str or "rate limit" in error_str or "too many requests" in error_str or "resource_exhausted" in error_str:
                        print(f"[{provider_name}] Rate limit hit on attempt {attempt + 1}.", flush=True)
                        if attempt < max_retries - 1:
                            sleep_time = (attempt + 1) * 2
                            print(f"[{provider_name}] Waiting {sleep_time}s before retry...", flush=True)
                            time.sleep(sleep_time)
                        else:
                            print(f"[{provider_name}] Exhausted retries. Moving to next fallback client...", flush=True)
                    else:
                        print(f"[{provider_name}] Error: {e}. Moving to fallback...", flush=True)
                        break
            
            if success:
                break
                
        if not success:
            print(f"Hook extraction failed. All AI clients exhausted. Last error: {last_error}", flush=True)
            return None

        content = completion.choices[0].message.content.strip()

        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        json_start = content.find('{')
        if json_start != -1:
            brace_count = 0
            json_end = json_start
            for i in range(json_start, len(content)):
                if content[i] == '{':
                    brace_count += 1
                elif content[i] == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        json_end = i + 1
                        break
            content = content[json_start:json_end]

        print(f"RAW AI OUTPUT: {content}", flush=True)
        parsed = json.loads(content)
        return parsed

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Hook extraction fatal error: {e}", flush=True)
        return None


def _summarize_signals(signals: dict) -> str:
    """Converts the structural signals dict from the scraper into a clean, AI-readable string."""
    parts = []

    if signals.get('page_title'):
        parts.append(f"PAGE TITLE: {signals['page_title']}")
    if signals.get('meta_description'):
        parts.append(f"META DESCRIPTION: {signals['meta_description']}")

    headlines = signals.get('headlines', [])
    if headlines:
        parts.append("HEADLINES FOUND ON PAGE:")
        for h in headlines[:8]:
            parts.append(f"  [{h.get('tag', 'h?')}] {h.get('text', '')}")

    cta_buttons = signals.get('cta_buttons', [])
    if cta_buttons:
        parts.append(f"\nCTA BUTTONS ({len(cta_buttons)} found):")
        for btn in cta_buttons[:5]:
            parts.append(f"  • Button: \"{btn.get('text', '')}\"")

    cta_links = signals.get('cta_links', [])
    if cta_links:
        parts.append(f"\nCTA LINKS ({len(cta_links)} found):")
        for link in cta_links[:5]:
            href = link.get('href', '')
            text = link.get('text', '')
            parts.append(f"  • Link: \"{text}\" → {href}")

    forms = signals.get('forms', [])
    if forms:
        parts.append(f"\nFORMS ({len(forms)} found):")
        for form in forms[:3]:
            if isinstance(form, dict):
                fields = form.get('fields', [])
                parts.append(f"  • Form with {len(fields)} fields: {', '.join(f.get('type', 'text') if isinstance(f, dict) else str(f) for f in fields[:8])}")
            else:
                parts.append(f"  • Form: {str(form)[:100]}")

    sp_count = signals.get('social_proof_count', 0)
    sp_signals = signals.get('social_proof_signals', [])
    if sp_count > 0 or sp_signals:
        parts.append(f"\nSOCIAL PROOF: {sp_count} testimonial/proof elements detected")
        for sp in sp_signals[:3]:
            parts.append(f"  • \"{str(sp)[:120]}\"")

    images = signals.get('images_with_context', [])
    if images:
        parts.append(f"\nIMAGES ({len(images)} with context):")
        for img in images[:4]:
            if isinstance(img, dict):
                alt = img.get('alt', 'no alt text')
            else:
                alt = str(img)[:80]
            parts.append(f"  • Image: \"{alt}\"")

    return "\n".join(parts)