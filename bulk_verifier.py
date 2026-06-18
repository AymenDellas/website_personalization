import os
import json
import time
import pandas as pd
from openai import OpenAI
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

load_dotenv()

def verify_coach(headline: str) -> dict:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        print("Error: GROQ_API_KEY not found in environment variables.")
        return {"is_coach": False, "reason": "No API Key"}

    client = OpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=api_key,
    )

    system_prompt = """You are an strict lead qualification agent for a B2B agency.
Your ONLY job is to determine if a LinkedIn headline belongs to a coach, consultant, or mentor who sells high-ticket services.

RULES:
1. Return true if they are a Business Coach, Life Coach, Executive Coach, Leadership Coach, Career Coach, Consultant, Mentor, or Advisor.
2. Return false for: Software Engineers, Developers, Recruiters, HR Managers, Students, Teachers, Professors, Nurses, Doctors, Dentists, Real Estate Agents.
3. Return false for Sports coaches (Basketball coach, Football coach).
4. Output strict JSON only.

Schema:
{
  "is_coach": boolean,
  "reason": "Brief 1-sentence reason"
}"""

    for attempt in range(3):
        try:
            completion = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Headline:\n{headline}"}
                ],
                temperature=0,
            )
            content = completion.choices[0].message.content.strip()
            return json.loads(content)
        except Exception as e:
            if "429" in str(e):
                time.sleep(2 ** attempt)
            else:
                return {"is_coach": False, "reason": f"Error: {e}"}
    return {"is_coach": False, "reason": "Rate limited"}

def process_file(input_file: str, output_file: str):
    print(f"Reading file: {input_file}")
    if input_file.endswith(".csv"):
        df = pd.read_csv(input_file)
    elif input_file.endswith(".xlsx"):
        df = pd.read_excel(input_file)
    else:
        print("Unsupported file format. Use .csv or .xlsx")
        return

    # Look for headline column
    col_name = None
    for col in df.columns:
        if "headline" in col.lower() or "title" in col.lower():
            col_name = col
            break
            
    if not col_name:
        print("Could not find a 'headline' or 'title' column in the file!")
        print("Available columns:", list(df.columns))
        return

    print(f"Loaded {len(df)} rows. Verifying headlines using column '{col_name}'...")
    
    df['is_coach'] = False
    df['reason'] = ''
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        # Submit all tasks
        future_to_idx = {}
        for idx, row in df.iterrows():
            headline = str(row[col_name])
            if pd.isna(row[col_name]) or not headline.strip() or headline.lower() == 'nan':
                df.at[idx, 'reason'] = 'Empty headline'
                continue
            future_to_idx[executor.submit(verify_coach, headline)] = idx
        
        # Wait for results
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            res = future.result()
            df.at[idx, 'is_coach'] = res.get('is_coach', False)
            df.at[idx, 'reason'] = res.get('reason', '')
            
            status = '✅ Coach' if res.get('is_coach') else '❌ Rejected'
            headline_preview = str(df.at[idx, col_name]).replace('\n', ' ')[:60]
            print(f"[{idx+1}/{len(df)}] {status} | {headline_preview}... | {res.get('reason')}")

    # Save to output
    if output_file.endswith(".csv"):
        df.to_csv(output_file, index=False)
    else:
        df.to_excel(output_file, index=False)
    
    clean_count = df[df['is_coach'] == True].shape[0]
    print(f"\n====================================")
    print(f"Done! {clean_count}/{len(df)} were verified as coaches.")
    print(f"Saved results to: {output_file}")
    print(f"You can now sort the file by 'is_coach' and delete the False rows.")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python bulk_verifier.py input.csv [output.csv]")
    else:
        in_f = sys.argv[1]
        out_f = sys.argv[2] if len(sys.argv) > 2 else "verified_" + in_f
        process_file(in_f, out_f)
