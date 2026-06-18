# ── LinkedIn Scraper (Flask + Playwright) ──
# Runs on ARM64 (Oracle Cloud Ampere A1) and AMD64
FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install system dependencies for Playwright Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libxshmfence1 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install Python deps (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright Chromium browser
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers
RUN playwright install chromium && playwright install-deps chromium

# Copy application source
COPY server.py scraper.py dork_engine.py website_scraper.py \
     website_extractor.py extractor.py leads_store.py \
     sheets_sync.py google_searcher.py utils.py logger.py \
     main.py dorks_config.json ./

# Copy frontend files
COPY public/ ./public/

# Copy Google Sheets service account credentials (if present)
COPY portfolio-*.json ./

# Create directories for output files
RUN mkdir -p /app/output

# Expose Flask port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/api/health')" || exit 1

# Run the Flask server
CMD ["python", "server.py"]
