import os
import time
import json
import uuid
import threading
import random
import pandas as pd
import io
from flask import Flask, request, jsonify, send_from_directory, send_file, Response
from flask_cors import CORS
from dotenv import load_dotenv
from scraper import scrape_linkedin_profile
from extractor import extract_profile_data
from website_scraper import scrape_generic_website, scrape_website_rich
from website_extractor import extract_website_data
from google_searcher import search_google
from logger import log, log_manager

# In-memory store for bulk jobs (use a proper DB/queue for production)
bulk_jobs = {}

# Load environment variables
load_dotenv()

app = Flask(__name__, static_folder='public')
CORS(app)

@app.route('/')
def index():
    return send_from_directory('public', 'index.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('public', path)

@app.route('/api/health')
def health_check():
    import shutil
    info = {
        "status": "ok",
        "openrouter_key_set": bool(os.getenv("OPENROUTER_API_KEY")),
        "li_at_set": bool(os.getenv("LI_AT")),
        "playwright_browsers_path": os.getenv("PLAYWRIGHT_BROWSERS_PATH", "(default)"),
    }
    # Check if chromium binary exists
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            browser.close()
            info["chromium"] = "ok"
    except Exception as e:
        info["chromium"] = f"FAILED: {str(e)}"
    return jsonify(info)

@app.route('/api/logs')
def stream_logs():
    def generate():
        q = log_manager.subscribe()
        try:
            while True:
                msg = q.get()
                yield f"data: {msg}\n\n"
        finally:
            log_manager.unsubscribe(q)
            
    return Response(generate(), mimetype='text/event-stream')

@app.route('/api/scrape', methods=['POST'])
def scrape():
    data = request.json
    url = data.get('url')
    
    if not url:
        return jsonify({"error": "URL is required"}), 400
        
    print(f"Received scrape request for: {url}")
    
    try:
        # Check for LI_AT cookie
        li_at = os.getenv("LI_AT")
        if not li_at:
            print("WARNING: LI_AT cookie missing")
            return jsonify({"error": "Configuration error: LinkedIn session cookie (LI_AT) missing from server environment."}), 500
            
        # Step 1: Scrape
        text = scrape_linkedin_profile(url, headless=True, li_at_cookie=li_at)
        
        if not text:
            return jsonify({"error": "Failed to scrape profile. Ensure the URL is correct and the server has access."}), 500
            
        # Step 2: Extract
        profile_data = extract_profile_data(text)
        
        if not profile_data:
             return jsonify({"error": "Failed to extract data from the scraped text."}), 500
             
        return jsonify(profile_data)
        
    except Exception as e:
        print(f"Server error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/scrape-website', methods=['POST'])
def scrape_website():
    data = request.json
    url = data.get('url')
    
    if not url:
        return jsonify({"error": "URL is required"}), 400
        
    print(f"Received website scrape request for: {url}")
    
    try:
        scraped = scrape_website_rich(url, headless=True)
        if not scraped:
            return jsonify({"error": "Failed to scrape website."}), 500
            
        # Extract data using AI with structural signals for accuracy
        site_data = extract_website_data(
            scraped.get('visible_text', ''),
            structural_signals=scraped.get('structural_signals')
        )
        
        if not site_data:
             return jsonify({"error": "Failed to extract insights from website text."}), 500

        return jsonify(site_data)
        
    except Exception as e:
         import traceback
         tb = traceback.format_exc()
         print(tb)
         return jsonify({"error": f"Server Error: {str(e)}", "traceback": tb}), 500

def run_bulk_analysis(job_id, df, li_at, extract_only=False):
    results = []
    total = len(df)
    
    # Try to find a column with "linkedin" in the name
    li_col = next((c for c in df.columns if 'linkedin' in c.lower()), None)
    
    if not li_col:
        bulk_jobs[job_id]['status'] = 'error'
        bulk_jobs[job_id]['error'] = 'Could not find a LinkedIn URL column.'
        return

    log(f"Starting bulk analysis for job {job_id[:8]} ({total} rows)")
    for index, row in df.iterrows():
        url = str(row[li_col]).strip()
        progress = int(((index) / total) * 100)
        bulk_jobs[job_id]['progress'] = progress
        
        log(f"Processing row {index + 1}/{total}: {url}")
        if not url or 'linkedin.com' not in url:
            results.append({**row.to_dict(), "error": "Invalid URL"})
            continue
            
        try:
            # Random delay to mimic human behavior and avoid 999 blocks (LinkedIn)
            delay = random.uniform(10, 25)
            log(f"Waiting {delay:.1f}s before scraping {url}...")
            time.sleep(delay)

            # Stage 1: LinkedIn to get Website
            text = scrape_linkedin_profile(url, headless=True, li_at_cookie=li_at)
            
            p_data = {}
            extract_only_website_found = None

            if not text:
                # If scraping failed (Block/Authwall), try Ultimate Fallback if we have Company Name input
                company_input = row.get('company') or row.get('Company') or row.get('company_name') or row.get('Company Name')
                if company_input and isinstance(company_input, str):
                    print(f"LinkedIn blocked or failed. Attempting Google Search for provided company: {company_input}")
                    found_url = search_google(f"{company_input} official site")
                    if found_url:
                        # Success via fallback!
                        extract_only_website_found = found_url
                        
                        # If extract_only mode, we are done
                        if extract_only:
                             results.append({**row.to_dict(), "website_url": found_url, "enrichment_source": "Google Search (Fallback)"})
                             continue
                        
                        # Otherwise, we have the URL, proceed to Stage 2 (Website Analysis)
                        # We simulate p_data with what we found
                        p_data = {'website_url': found_url, 'company_name': company_input, 'enrichment_source': "Google Search (Fallback)"}
                    else:
                        results.append({**row.to_dict(), "error": "Profile scrape failed & Google Search failed"})
                        continue
                else:
                    results.append({**row.to_dict(), "error": "Profile scrape failed (Authwall/Block)"})
                    continue
                
            p_data = extract_profile_data(text)
            web_url = p_data.get('website_url') if p_data else None
            
            if web_url:
                log(f"Website found on LinkedIn: {web_url}")
            else:
                log("No website found on LinkedIn profile.")
                # GOOGLE SEARCH FALLBACK
                company = row.get('company') or row.get('Company') or p_data.get('company_name')
                if company:
                    log(f"Entering Fallback: Searching Google for '{company}' official site...")
                    found_url = search_google(f"{company} official site")
                    if found_url:
                        log(f"Google Fallback SUCCESS: Found {found_url}")
                        web_url = found_url
                        if not p_data: p_data = {}
                        p_data['website_url'] = found_url
                        p_data['enrichment_source'] = "Google Search"
                    else:
                        log(f"Google Fallback FAILED for '{company}'.")
                        results.append({**row.to_dict(), **(p_data or {}), "error": "No website found (Google search failed)"})
                        continue
                else:
                    log("No company name available for Google fallback.")
                    results.append({**row.to_dict(), **(p_data or {}), "error": "No website found (and no company name extracted)"})
                    continue

            if extract_only:
                results.append({**row.to_dict(), "website_url": web_url, "enrichment_source": p_data.get('enrichment_source', 'LinkedIn')})
                continue
                
            # Stage 2: Analyze Website
            site_text = scrape_generic_website(web_url, headless=True)
            if not site_text:
                results.append({**row.to_dict(), "website_url": web_url, "error": "Website scrape failed", "enrichment_source": p_data.get('enrichment_source', 'LinkedIn')})
                continue
                
            site_data = extract_website_data(site_text)
            if not site_data:
                results.append({**row.to_dict(), "website_url": web_url, "error": "AI analysis failed", "enrichment_source": p_data.get('enrichment_source', 'LinkedIn')})
                continue
                
            # Combine
            results.append({**row.to_dict(), **p_data, **site_data, "website_url": web_url})
            
        except Exception as e:
            print(f"Error processing row {index}: {e}")
            results.append({**row.to_dict(), "error": str(e)})

    # Finalize
    output_df = pd.DataFrame(results)
    bulk_jobs[job_id]['results_df'] = output_df
    bulk_jobs[job_id]['progress'] = 100
    bulk_jobs[job_id]['status'] = 'completed'

def run_bulk_website_job(job_id, df):
    try:
        results = []
        total = len(df)
        
        # Priority: exact "url" column first, then fallback to columns containing "website" or "url"
        url_col = None
        for c in df.columns:
            if c.strip().lower() == 'url':
                url_col = c
                break
        if not url_col:
            url_col = next((c for c in df.columns if 'website' in c.lower() or 'url' in c.lower()), None)
        if not url_col:
            # Fallback to first column if no obvious name matches
            url_col = df.columns[0]
        
        log(f"Bulk website job {job_id[:8]}: Using column '{url_col}' for URLs ({total} rows)")
        log(f"Available columns: {list(df.columns)}")

        # Output file path for incremental saving
        output_path = os.path.join(os.path.dirname(__file__) or '.', f'bulk_website_{job_id[:8]}.xlsx')
        
        for row_num, (index, row) in enumerate(df.iterrows()):
            url = str(row[url_col]).strip()
            progress = int(((row_num + 1) / total) * 100)
            bulk_jobs[job_id]['progress'] = progress
            
            log(f"[Website Bulk] Processing row {row_num + 1}/{total} ({progress}%): {url}")

            # skip empty
            if not url or len(url) < 4 or url.lower() == 'nan':
                results.append({**row.to_dict(), "error": "Invalid URL"})
                _save_partial_results(results, output_path, job_id)
                continue
                
            try:
                # Stage 1: Analyze Website directly
                if not url.startswith('http'):
                    url = 'https://' + url
                    
                scraped = scrape_website_rich(url, headless=True)
                if not scraped:
                    results.append({**row.to_dict(), "analyzed_url": url, "error": "Website scrape failed"})
                    _save_partial_results(results, output_path, job_id)
                    continue
                    
                site_data = extract_website_data(
                    scraped.get('visible_text', ''),
                    structural_signals=scraped.get('structural_signals')
                )
                if not site_data:
                    results.append({**row.to_dict(), "analyzed_url": url, "error": "AI analysis failed"})
                    _save_partial_results(results, output_path, job_id)
                    continue
                    
                # Combine
                results.append({**row.to_dict(), **site_data, "analyzed_url": url})
                log(f"[Website Bulk] Row {row_num + 1}/{total} analyzed successfully.")
                
            except Exception as e:
                print(f"Error processing row {row_num}: {e}")
                results.append({**row.to_dict(), "error": str(e)})

            # Save after every row (success or failure)
            _save_partial_results(results, output_path, job_id)

        # Finalize
        output_df = pd.DataFrame(results)
        bulk_jobs[job_id]['results_df'] = output_df
        bulk_jobs[job_id]['progress'] = 100
        bulk_jobs[job_id]['status'] = 'completed'
        log(f"[Website Bulk] Job {job_id[:8]} completed. {total} rows processed.")

    except Exception as e:
        import traceback
        traceback.print_exc()
        log(f"[Website Bulk] FATAL ERROR in job {job_id[:8]}: {e}")
        bulk_jobs[job_id]['status'] = 'error'
        bulk_jobs[job_id]['error'] = str(e)


def _save_partial_results(results, output_path, job_id):
    """Save current results to disk so partial data is always available."""
    try:
        partial_df = pd.DataFrame(results)
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            partial_df.to_excel(writer, index=False)
        # Also update the in-memory reference so download endpoint works mid-job
        bulk_jobs[job_id]['results_df'] = partial_df
    except Exception as e:
        print(f"Warning: Could not save partial results: {e}")

@app.route('/api/bulk-process', methods=['POST'])
def bulk_process():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Empty filename"}), 400

    li_at = os.getenv("LI_AT")
    if not li_at:
        return jsonify({"error": "LinkedIn session cookie missing on server"}), 500

    try:
        if file.filename.endswith('.csv'):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)
            
        job_id = str(uuid.uuid4())
        bulk_jobs[job_id] = {
            'status': 'processing',
            'progress': 0,
            'results_df': None
        }
        
        extract_only = request.form.get('extract_only') == 'true'

        # Start background task
        thread = threading.Thread(target=run_bulk_analysis, args=(job_id, df, li_at, extract_only))
        thread.start()
        
        return jsonify({"job_id": job_id})
        
    except Exception as e:
        return jsonify({"error": f"Failed to parse file: {str(e)}"}), 500

@app.route('/api/bulk-website-extract', methods=['POST'])
def bulk_website_extract():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Empty filename"}), 400

    try:
        if file.filename.endswith('.csv'):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)
            
        job_id = str(uuid.uuid4())
        bulk_jobs[job_id] = {
            'status': 'processing',
            'progress': 0,
            'results_df': None
        }
        
        # Start background task
        thread = threading.Thread(target=run_bulk_website_job, args=(job_id, df))
        thread.start()
        
        return jsonify({"job_id": job_id})
        
    except Exception as e:
        return jsonify({"error": f"Failed to parse file: {str(e)}"}), 500

@app.route('/api/bulk-status/<job_id>')
def bulk_status(job_id):
    job = bulk_jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
        
    return jsonify({
        "status": job['status'],
        "progress": job['progress'],
        "error": job.get('error')
    })

@app.route('/api/bulk-download/<job_id>')
def bulk_download(job_id):
    job = bulk_jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    
    df = job.get('results_df')
    if df is None or len(df) == 0:
        return jsonify({"error": "No results available yet"}), 404
        
    output = io.BytesIO()
    
    # Export to Excel by default for better compatibility
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
        
    output.seek(0)
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'analyzed_leads_{job_id[:8]}.xlsx'
    )

# ΓöÇΓöÇ First Name Extraction ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

def run_name_extraction_job(job_id, df, li_at):
    try:
        results = []
        total = len(df)
        
        # Find the LinkedIn URL column
        li_col = next((c for c in df.columns if 'linkedin' in c.lower()), None)
        if not li_col:
            li_col = next((c for c in df.columns if 'url' in c.lower()), None)
        if not li_col:
            li_col = df.columns[0]
        
        log(f"[Name Extract] Job {job_id[:8]}: Using column '{li_col}' ({total} rows)")
        
        output_path = os.path.join(os.path.dirname(__file__) or '.', f'names_{job_id[:8]}.xlsx')
        
        for row_num, (index, row) in enumerate(df.iterrows()):
            url = str(row[li_col]).strip()
            progress = int(((row_num + 1) / total) * 100)
            bulk_jobs[job_id]['progress'] = progress
            
            log(f"[Name Extract] Row {row_num + 1}/{total} ({progress}%): {url}")
            
            if not url or 'linkedin.com' not in url or url.lower() == 'nan':
                results.append({**row.to_dict(), "first_name": "", "error": "Invalid LinkedIn URL"})
                _save_partial_results(results, output_path, job_id)
                continue
            
            try:
                # Add delay between requests
                if row_num > 0:
                    delay = random.uniform(10, 25)
                    log(f"[Name Extract] Waiting {delay:.1f}s...")
                    time.sleep(delay)
                
                text = scrape_linkedin_profile(url, headless=True, li_at_cookie=li_at)
                
                if not text:
                    results.append({**row.to_dict(), "first_name": "", "error": "Scrape failed"})
                    _save_partial_results(results, output_path, job_id)
                    continue
                
                # Extract first name: LinkedIn pages start with the full name
                # The first line of visible text in <main> is typically the person's name
                first_name = ""
                for line in text.split('\n'):
                    line = line.strip()
                    # Skip empty lines and common LinkedIn UI text
                    if not line or len(line) < 2:
                        continue
                    if any(skip in line.lower() for skip in ['messaging', 'skip to', 'search', 'premium', 'try premium', 'home', 'my network', 'jobs', 'notifications']):
                        continue
                    # This should be the person's name
                    first_name = line.split()[0] if line.split() else ""
                    break
                
                log(f"[Name Extract] Found: {first_name}")
                results.append({**row.to_dict(), "first_name": first_name})
                
            except Exception as e:
                print(f"Error processing row {row_num}: {e}")
                results.append({**row.to_dict(), "first_name": "", "error": str(e)})
            
            _save_partial_results(results, output_path, job_id)
        
        # Finalize
        output_df = pd.DataFrame(results)
        bulk_jobs[job_id]['results_df'] = output_df
        bulk_jobs[job_id]['progress'] = 100
        bulk_jobs[job_id]['status'] = 'completed'
        log(f"[Name Extract] Job {job_id[:8]} completed. {total} names extracted.")
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        log(f"[Name Extract] FATAL ERROR in job {job_id[:8]}: {e}")
        bulk_jobs[job_id]['status'] = 'error'
        bulk_jobs[job_id]['error'] = str(e)

@app.route('/api/bulk-name-extract', methods=['POST'])
def bulk_name_extract():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Empty filename"}), 400

    li_at = os.getenv("LI_AT")
    if not li_at:
        return jsonify({"error": "LinkedIn session cookie missing on server"}), 500

    try:
        if file.filename.endswith('.csv'):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)
            
        job_id = str(uuid.uuid4())
        bulk_jobs[job_id] = {
            'status': 'processing',
            'progress': 0,
            'results_df': None
        }
        
        thread = threading.Thread(target=run_name_extraction_job, args=(job_id, df, li_at))
        thread.start()
        
        return jsonify({"job_id": job_id})
        
    except Exception as e:
        return jsonify({"error": f"Failed to parse file: {str(e)}"}), 500

# ΓöÇΓöÇ Personalize API ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

@app.route('/api/personalize', methods=['POST'])
def personalize():
    data = request.json
    website = data.get('website')

    if not website:
        return jsonify({"error": "website field is required"}), 400

    print(f"Received personalize request for: {website}")

    try:
        scraped = scrape_website_rich(website, headless=True)
        if not scraped:
            return jsonify({"error": "Failed to scrape website."}), 500

        site_data = extract_website_data(
            scraped.get('visible_text', ''),
            structural_signals=scraped.get('structural_signals')
        )
        if not site_data:
            return jsonify({"error": "Failed to extract insights from website text."}), 500

        return jsonify(site_data)

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(tb)
        return jsonify({"error": f"Server Error: {str(e)}", "traceback": tb}), 500


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    print(f"Starting Flask server on http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", debug=True, use_reloader=False, port=port)

