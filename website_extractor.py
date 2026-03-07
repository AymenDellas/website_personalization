
import os
import json
from openai import OpenAI

def extract_website_data(website_text: str, structural_signals: dict | None = None) -> dict | None:
    """
    Analyzes website text + structural signals using AI to extract 
    accurate, evidence-based landing page insights.
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("Error: OPENROUTER_API_KEY not found.")
        return None

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )

    system_prompt = """You are an expert landing page conversion analyst. Your job is to perform a thorough, honest audit.

RULES FOR ACCURACY:
1. For SOCIAL PROOF specifically: check the structural_signals data. If social_proof_count > 0, social proof EXISTS — acknowledge it in strengths, do NOT flag it as missing.
2. For HEADLINES specifically: read the actual h1/h2 text from structural signals. A headline that states a benefit, outcome, or clear value proposition is NOT ambiguous. Only flag a headline as ambiguous if it truly gives zero indication of what the page offers.
3. For ALL OTHER friction points: be thorough and critical. Most pages have real conversion issues — find them.

Return STRICT JSON using the schema below.

SCHEMA:
{
  "page_type": "vsl" | "lead-magnet" | "homepage" | "direct-to-call" | "booking_page" | "service_page" | "opt-in" | null,
  "direct_goal": string | null,
  "primary_cta_text": string | null,
  "logical_cta_action": string | null,
  "cta_destination": "calendar" | "form" | "email" | "external" | null,
  "all_ctas_found": [string],
  "strengths": string | null,
  "roadblock": string | null,
  "audience": string | null
}

ANALYSIS PROCESS:

1. IDENTIFY PAGE TYPE:
   - Classify as: vsl, lead-magnet, homepage, direct-to-call, booking_page, service_page, or opt-in.

2. HEADLINE ASSESSMENT:
   - Read the actual h1/h2 headlines from structural signals.
   - CLEAR = communicates a specific benefit, outcome, or value prop (e.g., "Grow revenue 3x" or "AI analytics for marketers").
   - AMBIGUOUS = vague filler with no supporting subheadline (e.g., "Welcome" or "Hello World").
   - If ambiguous, flag it. If clear, note it as a strength.

3. SOCIAL PROOF ASSESSMENT:
   - Check structural_signals for social_proof_count.
   - If social_proof_count > 0: social proof EXISTS. Note types present in strengths.
   - If social_proof_count is 0 AND visible text has no testimonials/reviews/stats/trust indicators: flag as missing.

4. CTA IDENTIFICATION:
   - Use cta_buttons and cta_links from structural signals + scan visible text.
   - List all in "all_ctas_found", pick the most prominent as primary.
   - "logical_cta_action": translate button text to the real action (max 5-7 words).

5. STRENGTHS:
   - Identify 2-4 things the page does well.
   - Format as comma-separated string.

6. ROADBLOCK / FRICTION — BE THOROUGH:
   - Analyze the page critically for ALL of these conversion killers:
     * Overwhelming text / wall of text: long paragraphs without bullet points or visual breaks
     * Form friction: too many fields, asking for phone number upfront, multi-step forms
     * No clear CTA or CTA buried below the fold
     * Too many competing CTAs pulling attention in different directions
     * Navigation clutter: too many links/menus that distract from the primary goal
     * Information gap: asking for a call/demo before explaining what the product does
     * Unclear pricing or hidden pricing
     * No urgency or scarcity elements
     * Weak or generic copy that doesn't differentiate from competitors
     * Missing social proof (ONLY if social_proof_count is 0 — see rule above)
     * Ambiguous headline (ONLY if h1 truly has no benefit/value — see rule above)
   - Most pages have AT LEAST 1-2 genuine friction points. Identify them honestly.
   - Format: comma-separated list of PROBLEMS only. Do NOT suggest solutions.
   - Only say "None identified" if the page genuinely has excellent conversion design with no issues.

7. AUDIENCE:
   - Identify the target persona based on language, offering, and industry signals.

CONSTRAINTS:
- Output JSON ONLY. No markdown wrapping.
- Be thorough and honest. Find real problems, but do not fabricate issues about social proof or headlines when the evidence contradicts you.
"""

    try:
        # Build the user message with both text and structural context
        truncated_text = website_text[:25000]
        
        user_content = f"Website Visible Text:\n{truncated_text}"
        
        if structural_signals:
            # Summarize structural signals concisely to stay within token limits
            signals_summary = _summarize_signals(structural_signals)
            user_content += f"\n\n---\n\nSTRUCTURAL SIGNALS (extracted from HTML):\n{signals_summary}"

        completion = client.chat.completions.create(
            model="openai/gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            temperature=0, 
        )

        content = completion.choices[0].message.content.strip()
        
        # Helper to parse strict JSON (strip potential markdown wrapping)
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        
        return json.loads(content)

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Website Extraction error: {e}")
        return None


def _summarize_signals(signals: dict) -> str:
    """Convert raw structural signals dict into a concise text summary for the AI."""
    parts = []
    
    # Page metadata
    title = signals.get('page_title', '')
    if title:
        parts.append(f"Page Title: {title}")
    
    meta = signals.get('meta_description', '')
    if meta:
        parts.append(f"Meta Description: {meta}")
    
    # Headlines
    headlines = signals.get('headlines', [])
    if headlines:
        hl_list = []
        for h in headlines[:10]:
            hl_list.append(f"  <{h['tag']}> {h['text']}")
        parts.append("Headlines found:\n" + "\n".join(hl_list))
    
    # Social proof
    sp_count = signals.get('social_proof_count', 0)
    sp_signals = signals.get('social_proof_signals', [])
    parts.append(f"\nSocial Proof Elements Found: {sp_count}")
    if sp_signals:
        sp_list = []
        for sp in sp_signals[:15]:  # Cap to avoid token bloat
            sp_type = sp.get('type', 'unknown')
            snippet = sp.get('snippet', sp.get('alt', sp.get('keyword', '')))
            sp_list.append(f"  [{sp_type}] {snippet}")
        parts.append("Social Proof Details:\n" + "\n".join(sp_list))
    else:
        parts.append("Social Proof Details: NONE DETECTED in HTML structure.")
    
    # CTAs
    buttons = signals.get('cta_buttons', [])
    links = signals.get('cta_links', [])
    if buttons:
        btn_texts = [b['text'] for b in buttons[:10]]
        parts.append(f"\nCTA Buttons Found: {', '.join(btn_texts)}")
    if links:
        link_texts = [f"{l['text']} -> {l['href']}" for l in links[:10]]
        parts.append(f"CTA Links Found: {', '.join(link_texts)}")
    if not buttons and not links:
        parts.append("\nCTA Buttons/Links: NONE DETECTED")
    
    # Forms
    forms = signals.get('forms', [])
    if forms:
        for i, f in enumerate(forms[:3]):
            field_labels = [fld.get('label', fld.get('type', '?')) for fld in f.get('fields', [])]
            parts.append(f"Form {i+1}: {f['field_count']} fields ({', '.join(field_labels)})")
    
    # Images
    images = signals.get('images_with_context', [])
    if images:
        parts.append(f"\nImages with alt text: {', '.join(images[:10])}")
    
    return "\n".join(parts)
