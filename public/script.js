// Tabs Logic
function switchTab(tabId) {
    // Update Nav
    document.querySelectorAll('.nav-btn').forEach(btn => btn.classList.remove('active'));
    document.querySelector(`button[onclick="switchTab('${tabId}')"]`).classList.add('active');

    // Update Content
    document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
    document.getElementById(`tab-${tabId}`).classList.add('active');
}

// Toast Notification
function showToast(msg, type = 'error') {
    const toast = document.getElementById('errorToast');
    const msgEl = document.getElementById('errorMessage');

    msgEl.textContent = msg;
    toast.className = `toast ${type === 'error' ? 'bg-red' : 'bg-green'}`; // Simple toggle
    toast.classList.remove('hidden');

    setTimeout(() => {
        toast.classList.add('hidden');
    }, 4000);
}

function copyToClipboard(elementId) {
    const text = document.getElementById(elementId).textContent;
    navigator.clipboard.writeText(text).then(() => {
        showToast('Copied to clipboard', 'success');
    });
}

// LinkedIn Profile Scraper
async function scrapeProfile() {
    const urlInput = document.getElementById('urlInput');
    const url = urlInput.value.trim();

    if (!url) {
        showToast("Please enter a LinkedIn URL");
        return;
    }

    // UI State
    const btn = document.getElementById('scrapeBtn');
    const btnText = document.getElementById('btnText');
    const btnLoader = document.getElementById('btnLoader');
    const resultsArea = document.getElementById('resultsArea');

    btn.disabled = true;
    btnText.textContent = "Analyzing...";
    btnLoader.classList.remove('hidden');
    resultsArea.classList.add('hidden');

    try {
        const response = await fetch('/api/scrape', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: url })
        });

        const data = await response.json();

        if (!response.ok) throw new Error(data.error || "Profile analysis failed");

        renderProfileResult(data);

    } catch (error) {
        console.error("Scrape error:", error);
        showToast(error.message);
    } finally {
        btn.disabled = false;
        btnText.textContent = "Run Analysis";
        btnLoader.classList.add('hidden');
    }
}

function renderProfileResult(data) {
    const grid = document.getElementById('profileGrid');
    const resultsArea = document.getElementById('resultsArea');
    const jsonOutput = document.getElementById('jsonOutput');

    // Clear previous
    grid.innerHTML = '';

    // Helper to add card
    const addCard = (label, value) => {
        if (!value) return;
        const div = document.createElement('div');
        div.className = 'data-item';
        div.innerHTML = `
            <span class="data-label">${label}</span>
            <span class="data-value">${value}</span>
        `;
        grid.appendChild(div);
    };

    // Populate Key Fields
    addCard('Full Name', data.full_name || data.name);
    addCard('Headline', data.headline);
    addCard('Location', data.location);
    addCard('Current Company', data.company || data.current_company);
    addCard('Job Title', data.job_title || data.role);
    addCard('Email', data.email);
    addCard('Phone', data.phone);
    addCard('Website', data.website_url);

    // Set JSON for raw view
    jsonOutput.textContent = JSON.stringify(data, null, 2);

    resultsArea.classList.remove('hidden');
    lucide.createIcons();
}

function toggleJson() {
    document.getElementById('jsonOutput').classList.toggle('hidden');
}

// Website Audit
async function scrapeWebsite() {
    const urlInput = document.getElementById('websiteInput');
    const url = urlInput.value.trim();

    if (!url) {
        showToast("Please enter a Website URL");
        return;
    }

    const btn = document.getElementById('websiteBtn');
    const btnText = document.getElementById('webBtnText');
    const btnLoader = document.getElementById('webBtnLoader');
    const resultsArea = document.getElementById('webResults');

    btn.disabled = true;
    btnText.textContent = "Auditing...";
    btnLoader.classList.remove('hidden');
    resultsArea.classList.add('hidden');

    try {
        const response = await fetch('/api/scrape-website', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: url })
        });

        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Website audit failed");

        renderWebsiteResult(data);

    } catch (error) {
        showToast(error.message);
    } finally {
        btn.disabled = false;
        btnText.textContent = "Start Audit";
        btnLoader.classList.add('hidden');
    }
}

function renderWebsiteResult(data) {
    const resultsArea = document.getElementById('webResults');

    document.getElementById('pageTypeVal').textContent = data.page_type || "Unknown";
    document.getElementById('directGoalVal').textContent = data.direct_goal || "Unknown";
    document.getElementById('strengthsVal').textContent = data.strengths || "None identified";
    document.getElementById('roadblockVal').textContent = data.roadblock || "None identified";
    document.getElementById('primaryCtaVal').textContent = data.primary_cta_text || "None";
    document.getElementById('ctaDestVal').textContent = data.cta_destination || "--";
    document.getElementById('logicalActionVal').textContent = data.logical_cta_action || "--";

    const allCtas = data.all_ctas_found || [];
    document.getElementById('allCtasVal').textContent = allCtas.length > 0 ? allCtas.join(', ') : "None";

    document.getElementById('audienceVal').textContent = data.audience || "Not specified";

    document.getElementById('webJsonOutput').textContent = JSON.stringify(data, null, 2);

    resultsArea.classList.remove('hidden');
    lucide.createIcons();
}

function toggleWebJson() {
    document.getElementById('webJsonOutput').classList.toggle('hidden');
}

// Bulk Logic
let currentJobId = null;

// File Input Display
document.getElementById('fileInput').addEventListener('change', function (e) {
    const fileName = e.target.files[0]?.name;
    if (fileName) {
        document.getElementById('fileName').textContent = fileName;
        document.querySelector('.upload-zone').style.borderColor = 'var(--text-main)';
    }
});

function toggleBulkMode() {
    const mode = document.querySelector('input[name="bulkMode"]:checked').value;
    const extractOption = document.getElementById('extractOnlyOption');

    if (mode === 'linkedin') {
        extractOption.classList.remove('hidden');
    } else {
        extractOption.classList.add('hidden');
        document.getElementById('extractOnlyCheck').checked = false;
    }
}

async function startBulkProcess() {
    const fileInput = document.getElementById('fileInput');
    const file = fileInput.files[0];

    if (!file) {
        showToast("Please upload a file first");
        return;
    }

    // UI Transition
    const btn = document.getElementById('bulkBtn');
    const btnText = document.getElementById('bulkBtnText');
    const btnLoader = document.getElementById('bulkBtnLoader');
    const progressArea = document.getElementById('bulkProgressArea');
    const downloadArea = document.getElementById('downloadArea');

    btn.disabled = true;
    btnText.textContent = "Processing...";
    btnLoader.classList.remove('hidden');
    progressArea.classList.remove('hidden');
    downloadArea.classList.add('hidden');

    try {
        const formData = new FormData();
        formData.append('file', file);

        const mode = document.querySelector('input[name="bulkMode"]:checked').value;
        const endpoint = mode === 'website' ? '/api/bulk-website-extract' : '/api/bulk-process';

        if (mode === 'linkedin' && document.getElementById('extractOnlyCheck').checked) {
            formData.append('extract_only', 'true');
        }

        const response = await fetch(endpoint, {
            method: 'POST',
            body: formData
        });

        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Bulk start failed");

        currentJobId = data.job_id;
        pollBulkStatus();

    } catch (error) {
        showToast(error.message);
        btn.disabled = false;
        btnText.textContent = "Initialize Bulk Process";
        btnLoader.classList.add('hidden');
    }
}

async function pollBulkStatus() {
    if (!currentJobId) return;

    try {
        const response = await fetch(`/api/bulk-status/${currentJobId}`);
        const data = await response.json();

        const bar = document.getElementById('progressBar');
        const status = document.getElementById('progressStatus');
        const percent = document.getElementById('progressPercent');

        if (data.status === 'processing') {
            const p = data.progress;
            bar.style.width = p + '%';
            status.textContent = `Analyzing Row...`;
            percent.textContent = p + '%';
            setTimeout(pollBulkStatus, 2000);
        } else if (data.status === 'completed') {
            bar.style.width = '100%';
            percent.textContent = '100%';
            finishBulkUI();
        } else if (data.status === 'error') {
            throw new Error(data.error);
        }

    } catch (error) {
        showToast("Bulk Error: " + error.message);
        document.getElementById('bulkBtn').disabled = false;
        document.getElementById('bulkBtnLoader').classList.add('hidden');
    }
}

function finishBulkUI() {
    const btn = document.getElementById('bulkBtn');
    btn.disabled = false;
    document.getElementById('bulkBtnText').textContent = "Initialize Bulk Process";
    document.getElementById('bulkBtnLoader').classList.add('hidden');

    document.getElementById('downloadArea').classList.remove('hidden');
    document.getElementById('bulkProgressArea').classList.add('hidden');
}

function downloadBulkResults() {
    if (currentJobId) {
        window.location.href = `/api/bulk-download/${currentJobId}`;
    }
}

// Live Logs Logic
function initLogStream() {
    const logConsole = document.getElementById('logConsole');
    const statusDot = document.querySelector('.pulse-indicator');
    const statusText = document.getElementById('connectionStatus');

    const eventSource = new EventSource('/api/logs');

    eventSource.onmessage = (event) => {
        const entry = document.createElement('div');
        entry.className = 'log-entry';

        // Color coding
        if (event.data.toLowerCase().includes('error') || event.data.toLowerCase().includes('fail')) {
            entry.classList.add('error');
        } else if (event.data.toLowerCase().includes('success') || event.data.toLowerCase().includes('complete')) {
            entry.classList.add('success');
        } else if (event.data.startsWith('[') && event.data.includes(']')) {
            // standard log
        } else {
            entry.classList.add('system');
        }

        entry.textContent = event.data;
        logConsole.appendChild(entry);

        // Auto scroll
        logConsole.scrollTop = logConsole.scrollHeight;
    };

    eventSource.onopen = () => {
        statusText.textContent = "Connected";
        statusDot.style.background = "#238636";
    };

    eventSource.onerror = () => {
        statusText.textContent = "Reconnecting...";
        statusDot.style.background = "#f85149";
    };
}

// Initialize on load
document.addEventListener('DOMContentLoaded', () => {
    initLogStream();
    lucide.createIcons();
});

// Enter Key Support
['urlInput', 'websiteInput'].forEach(id => {
    const el = document.getElementById(id);
    if (el) {
        el.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                if (id === 'urlInput') scrapeProfile();
                else scrapeWebsite();
            }
        });
    }
});

// ── Name Extraction Logic ──────────────────────────────────────────

let nameJobId = null;

// File Input Display for Name Extractor
document.getElementById('namesFileInput').addEventListener('change', function (e) {
    const fileName = e.target.files[0]?.name;
    if (fileName) {
        document.getElementById('namesFileName').textContent = fileName;
        document.getElementById('namesDropZone').style.borderColor = 'var(--text-main)';
    }
});

async function startNameExtract() {
    const fileInput = document.getElementById('namesFileInput');
    const file = fileInput.files[0];

    if (!file) {
        showToast("Please upload a file first");
        return;
    }

    const btn = document.getElementById('namesBtn');
    const btnText = document.getElementById('namesBtnText');
    const btnLoader = document.getElementById('namesBtnLoader');
    const progressArea = document.getElementById('namesProgressArea');
    const downloadArea = document.getElementById('namesDownloadArea');

    btn.disabled = true;
    btnText.textContent = "Extracting...";
    btnLoader.classList.remove('hidden');
    progressArea.classList.remove('hidden');
    downloadArea.classList.add('hidden');

    try {
        const formData = new FormData();
        formData.append('file', file);

        const response = await fetch('/api/bulk-name-extract', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Name extraction failed");

        nameJobId = data.job_id;
        pollNameStatus();

    } catch (error) {
        showToast(error.message);
        btn.disabled = false;
        btnText.textContent = "Extract First Names";
        btnLoader.classList.add('hidden');
    }
}

async function pollNameStatus() {
    if (!nameJobId) return;

    try {
        const response = await fetch(`/api/bulk-status/${nameJobId}`);
        const data = await response.json();

        const bar = document.getElementById('namesProgressBar');
        const status = document.getElementById('namesProgressStatus');
        const percent = document.getElementById('namesProgressPercent');

        if (data.status === 'processing') {
            const p = data.progress;
            bar.style.width = p + '%';
            status.textContent = `Extracting names...`;
            percent.textContent = p + '%';
            setTimeout(pollNameStatus, 2000);
        } else if (data.status === 'completed') {
            bar.style.width = '100%';
            percent.textContent = '100%';
            finishNameUI();
        } else if (data.status === 'error') {
            throw new Error(data.error);
        }

    } catch (error) {
        showToast("Name Extract Error: " + error.message);
        document.getElementById('namesBtn').disabled = false;
        document.getElementById('namesBtnLoader').classList.add('hidden');
    }
}

function finishNameUI() {
    const btn = document.getElementById('namesBtn');
    btn.disabled = false;
    document.getElementById('namesBtnText').textContent = "Extract First Names";
    document.getElementById('namesBtnLoader').classList.add('hidden');

    document.getElementById('namesDownloadArea').classList.remove('hidden');
    document.getElementById('namesProgressArea').classList.add('hidden');
}

function downloadNameResults() {
    if (nameJobId) {
        window.location.href = `/api/bulk-download/${nameJobId}`;
    }
}
