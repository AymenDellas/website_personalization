#!/usr/bin/env bash
set -o errexit

# Install Python deps — skip Playwright's auto browser download
# so Render's buildpack doesn't try to sudo-install system deps
PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 pip install -r requirements.txt

# Now install Chromium manually to a writable path
export PLAYWRIGHT_BROWSERS_PATH=/opt/render/project/.browsers
playwright install chromium
