// ═══════════════════════════════════════════════════════════════════════════
// TABS LOGIC
// ═══════════════════════════════════════════════════════════════════════════

function switchTab(tabId) {
    document.querySelectorAll('.nav-btn').forEach(btn => btn.classList.remove('active'));
    document.querySelector(`button[onclick="switchTab('${tabId}')"]`).classList.add('active');
    document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
    document.getElementById(`tab-${tabId}`).classList.add('active');
    if (tabId === 'discover') loadLeads();
}

// ═══════════════════════════════════════════════════════════════════════════
// TOAST NOTIFICATION
// ═══════════════════════════════════════════════════════════════════════════

function showToast(msg, type = 'error') {
    const toast = document.getElementById('errorToast');
    const msgEl = document.getElementById('errorMessage');
    msgEl.textContent = msg;
    toast.className = `toast ${type === 'error' ? 'bg-red' : 'bg-green'}`;
    toast.classList.remove('hidden');
    setTimeout(() => toast.classList.add('hidden'), 4000);
}

function copyToClipboard(elementId) {
    const text = document.getElementById(elementId).textContent;
    navigator.clipboard.writeText(text).then(() => showToast('Copied to clipboard', 'success'));
}

// ═══════════════════════════════════════════════════════════════════════════
// LEAD FINDER — DISCOVERY
// ═══════════════════════════════════════════════════════════════════════════

let discoveryJobId = null;
let discoveryPollTimer = null;
let processLeadsJobId = null;
let processLeadsPollTimer = null;

const STAGE_ORDER = ['searching', 'completed'];

function setStage(activeStage) {
    STAGE_ORDER.forEach((s, idx) => {
        const el = document.getElementById(`stage-${s}`);
        if (!el) return;
        el.classList.remove('active', 'done');
        const activeIdx = STAGE_ORDER.indexOf(activeStage);
        if (idx < activeIdx) el.classList.add('done');
        else if (idx === activeIdx) el.classList.add('active');
    });
}

// Sanitise a URL to prevent XSS — only allow http(s) LinkedIn URLs
function sanitiseUrl(url) {
    if (typeof url !== 'string') return '';
    // Strip any HTML tags
    url = url.replace(/<[^>]*>/g, '');
    // Only allow valid LinkedIn profile URLs
    const match = url.match(/^https?:\/\/(?:[\w-]+\.)?linkedin\.com\/in\/[\w-]+\/?/);
    return match ? match[0] : encodeURI(url);
}

async function startLeadDiscovery() {
    const btn = document.getElementById('findLeadsBtn');
    const btnText = document.getElementById('findLeadsBtnText');
    const loader = document.getElementById('findLeadsLoader');

    const maxLeads = parseInt(document.getElementById('maxLeadsTarget').value) || 200;
    const maxPages = parseInt(document.getElementById('maxPagesPerDork').value) || 3;
    const prequalify = document.getElementById('prequalifyToggle').checked;

    btn.disabled = true;
    btnText.textContent = 'Starting...';
    loader.classList.remove('hidden');
    document.getElementById('discoverySuccess').classList.add('hidden');
    document.getElementById('discoveryProgress').classList.remove('hidden');
    document.getElementById('discoveryProgressBar').style.width = '0%';
    document.getElementById('discoveryFoundCount').textContent = '0 found';
    document.getElementById('discoveryMessage').textContent = 'Initialising pipeline...';
    setStage('searching');

    try {
        const resp = await fetch('/api/find-leads', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                max_leads: maxLeads, 
                max_pages: maxPages,
                prequalify: prequalify 
            })
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.error || 'Failed to start discovery');

        discoveryJobId = data.job_id;
        discoveryPollTimer = setInterval(pollDiscoveryStatus, 3000);

    } catch (err) {
        showToast(err.message);
        resetDiscoveryBtn();
    }
}

async function pollDiscoveryStatus() {
    if (!discoveryJobId) return;
    try {
        const resp = await fetch(`/api/find-leads-status/${discoveryJobId}`);
        const data = await resp.json();

        // Update stage indicator
        if (data.status && STAGE_ORDER.includes(data.status)) {
            setStage(data.status);
        }

        // Update progress bar
        document.getElementById('discoveryProgressBar').style.width = (data.progress || 0) + '%';
        document.getElementById('discoveryFoundCount').textContent = (data.found_count || 0) + ' found';
        document.getElementById('discoveryMessage').textContent = data.message || '';

        if (data.status === 'completed' || data.status === 'stopped') {
            clearInterval(discoveryPollTimer);
            setStage('completed');
            document.getElementById('discoveryProgressBar').style.width = '100%';

            const sr = data.save_result || {};
            document.getElementById('discoverySuccessMsg').textContent =
                `✓ ${sr.added || 0} new leads saved — ${sr.total || 0} total in file`;
            document.getElementById('discoverySuccess').classList.remove('hidden');
            document.getElementById('discoveryProgress').classList.add('hidden');

            resetDiscoveryBtn();
            loadLeads(); // Refresh leads list

        } else if (data.status === 'error') {
            clearInterval(discoveryPollTimer);
            showToast('Discovery error: ' + data.message);
            resetDiscoveryBtn();
            document.getElementById('discoveryProgress').classList.add('hidden');
        }
    } catch (err) {
        console.error('Poll error:', err);
    }
}

async function stopLeadDiscovery() {
    if (!discoveryJobId) return;
    await fetch(`/api/find-leads-stop/${discoveryJobId}`, { method: 'POST' });
    showToast('Stop signal sent — saving discovered leads...', 'success');
}

function resetDiscoveryBtn() {
    document.getElementById('findLeadsBtn').disabled = false;
    document.getElementById('findLeadsBtnText').textContent = 'Find Leads';
    document.getElementById('findLeadsLoader').classList.add('hidden');
}

// ═══════════════════════════════════════════════════════════════════════════
// LEAD FINDER — LEADS LIST
// ═══════════════════════════════════════════════════════════════════════════

async function loadLeads() {
    try {
        const resp = await fetch('/api/leads');
        const data = await resp.json();
        renderLeadsList(data.leads || []);
        updateLeadCountBadge(data.count || 0);
    } catch (err) {
        console.error('Failed to load leads:', err);
    }
}

function renderLeadsList(leads) {
    const list = document.getElementById('leadsList');
    const countEl = document.getElementById('leadsListCount');
    countEl.textContent = `${leads.length} lead${leads.length !== 1 ? 's' : ''} saved`;

    if (leads.length === 0) {
        list.innerHTML = `
            <div class="leads-empty">
                <i data-lucide="inbox"></i>
                <p>No leads yet. Run discovery first.</p>
            </div>`;
        lucide.createIcons();
        return;
    }

    // Build leads list using DOM APIs to prevent XSS
    list.innerHTML = '';
    leads.forEach((rawUrl, idx) => {
        const url = sanitiseUrl(rawUrl);
        const row = document.createElement('div');
        row.className = 'lead-row';
        row.id = `lead-row-${idx}`;

        const span = document.createElement('span');
        span.className = 'lead-url';
        span.title = url;
        span.textContent = url;
        span.style.cursor = 'pointer';
        span.addEventListener('click', () => window.open(url, '_blank'));

        const btn = document.createElement('button');
        btn.className = 'lead-del-btn';
        btn.title = 'Remove';
        btn.innerHTML = '<i data-lucide="x"></i>';
        btn.addEventListener('click', () => deleteSingleLead(url));

        row.appendChild(span);
        row.appendChild(btn);
        list.appendChild(row);
    });
    lucide.createIcons();
}

function updateLeadCountBadge(count) {
    const badge = document.getElementById('leadsFileBadge');
    const countEl = document.getElementById('leadsFileCount');
    const navBadge = document.getElementById('navLeadCount');

    countEl.textContent = count;
    if (navBadge) {
        navBadge.textContent = count;
        navBadge.style.display = count > 0 ? 'inline' : 'none';
    }
}

async function deleteSingleLead(url) {
    try {
        await fetch('/api/leads/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url })
        });
        // Full reload to avoid index drift bugs
        await loadLeads();
    } catch (err) {
        showToast('Failed to delete lead');
    }
}

async function downloadSavedLeads() {
    try {
        const resp = await fetch('/api/leads');
        const data = await resp.json();
        const leads = data.leads || [];
        
        if (leads.length === 0) {
            showToast('No leads to download');
            return;
        }

        // Create CSV content
        const csvContent = "LinkedIn URL\n" + leads.join("\n");
        const blob = new Blob([csvContent], { type: 'text/csv' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.setAttribute('hidden', '');
        a.setAttribute('href', url);
        a.setAttribute('download', 'discovered_leads.csv');
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    } catch (err) {
        showToast('Failed to download leads');
        console.error(err);
    }
}

function confirmClearLeads() {
    document.getElementById('confirmModal').classList.remove('hidden');
}

function closeConfirmModal() {
    document.getElementById('confirmModal').classList.add('hidden');
}

async function executeClearLeads() {
    closeConfirmModal();
    try {
        await fetch('/api/leads/clear', { method: 'POST' });
        loadLeads();
        showToast('All leads cleared', 'success');
    } catch (err) {
        showToast('Failed to clear leads');
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// LEAD FINDER — PROCESS LEADS
// ═══════════════════════════════════════════════════════════════════════════

async function startProcessLeads() {
    const btn = document.getElementById('processLeadsBtn');
    const btnText = document.getElementById('processLeadsBtnText');
    const loader = document.getElementById('processLeadsLoader');
    const progressArea = document.getElementById('processProgress');
    const downloadArea = document.getElementById('processDownload');

    btn.disabled = true;
    btnText.textContent = 'Starting...';
    loader.classList.remove('hidden');
    progressArea.classList.remove('hidden');
    downloadArea.classList.add('hidden');
    document.getElementById('processProgressBar').style.width = '0%';
    document.getElementById('processStatusText').textContent = 'Loading leads from file...';

    try {
        const resp = await fetch('/api/leads/process', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.error || 'Failed to start processing');

        processLeadsJobId = data.job_id;
        showToast(`Processing ${data.total_leads} leads...`, 'success');
        processLeadsPollTimer = setInterval(pollProcessLeadsStatus, 3000);

    } catch (err) {
        showToast(err.message);
        resetProcessBtn();
        document.getElementById('processProgress').classList.add('hidden');
    }
}

async function pollProcessLeadsStatus() {
    if (!processLeadsJobId) return;
    try {
        const resp = await fetch(`/api/bulk-status/${processLeadsJobId}`);
        const data = await resp.json();

        const pct = data.progress || 0;
        document.getElementById('processProgressBar').style.width = pct + '%';
        document.getElementById('processPercent').textContent = pct + '%';
        document.getElementById('processStatusText').textContent = `Analyzing profiles... ${pct}%`;

        if (data.status === 'completed') {
            clearInterval(processLeadsPollTimer);
            document.getElementById('processProgressBar').style.width = '100%';
            document.getElementById('processPercent').textContent = '100%';
            document.getElementById('processStatusText').textContent = 'Complete!';
            document.getElementById('processDownload').classList.remove('hidden');
            resetProcessBtn();
            showToast('Processing complete!', 'success');
        } else if (data.status === 'error') {
            clearInterval(processLeadsPollTimer);
            showToast('Processing error: ' + (data.error || 'Unknown'));
            resetProcessBtn();
        }
    } catch (err) {
        console.error('Process poll error:', err);
    }
}

async function stopProcessLeads() {
    if (!processLeadsJobId) return;
    await fetch(`/api/bulk-stop/${processLeadsJobId}`, { method: 'POST' });
    showToast('Stop signal sent — waiting for current row...', 'success');
}

function downloadProcessResults() {
    if (processLeadsJobId) {
        window.location.href = `/api/bulk-download/${processLeadsJobId}`;
    }
}

function resetProcessBtn() {
    document.getElementById('processLeadsBtn').disabled = false;
    document.getElementById('processLeadsBtnText').textContent = 'Process Leads';
    document.getElementById('processLeadsLoader').classList.add('hidden');
}

// ═══════════════════════════════════════════════════════════════════════════
// PROFILE SCRAPER
// ═══════════════════════════════════════════════════════════════════════════

async function scrapeProfile() {
    const urlInput = document.getElementById('urlInput');
    const url = urlInput.value.trim();
    if (!url) { showToast("Please enter a LinkedIn URL"); return; }

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
            body: JSON.stringify({ url })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Profile analysis failed");
        renderProfileResult(data);
    } catch (error) {
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
    grid.innerHTML = '';

    const addCard = (label, value) => {
        if (!value) return;
        const div = document.createElement('div');
        div.className = 'data-item';
        div.innerHTML = `<span class="data-label">${label}</span><span class="data-value">${value}</span>`;
        grid.appendChild(div);
    };

    addCard('Full Name', data.full_name || data.name);
    addCard('Headline', data.headline);
    addCard('Location', data.location);
    addCard('Current Company', data.company || data.current_company);
    addCard('Job Title', data.job_title || data.role);
    addCard('Email', data.email);
    addCard('Phone', data.phone);
    addCard('Website', data.website_url);

    jsonOutput.textContent = JSON.stringify(data, null, 2);
    resultsArea.classList.remove('hidden');
    lucide.createIcons();
}

function toggleJson() {
    document.getElementById('jsonOutput').classList.toggle('hidden');
}

// ═══════════════════════════════════════════════════════════════════════════
// HOOK GENERATOR
// ═══════════════════════════════════════════════════════════════════════════

async function scrapeWebsite() {
    const url = document.getElementById('websiteInput').value.trim();
    if (!url) { showToast("Please enter a Website URL"); return; }

    const btn = document.getElementById('websiteBtn');
    const btnText = document.getElementById('webBtnText');
    const btnLoader = document.getElementById('webBtnLoader');
    const resultsArea = document.getElementById('webResults');

    btn.disabled = true;
    btnText.textContent = "Generating...";
    btnLoader.classList.remove('hidden');
    resultsArea.classList.add('hidden');

    try {
        const response = await fetch('/api/scrape-website', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Hook generation failed");
        renderWebsiteResult(data);
    } catch (error) {
        showToast(error.message);
    } finally {
        btn.disabled = false;
        btnText.textContent = "Generate Hook";
        btnLoader.classList.add('hidden');
    }
}

function renderWebsiteResult(data) {
    document.getElementById('hookVal').textContent = data.hook || "No hook generated";
    document.getElementById('webJsonOutput').textContent = JSON.stringify(data, null, 2);
    document.getElementById('webResults').classList.remove('hidden');
    lucide.createIcons();
}

function copyHookToClipboard() {
    const hook = document.getElementById('hookVal').textContent;
    navigator.clipboard.writeText(hook).then(() => showToast('Hook copied to clipboard', 'success'));
}

function toggleWebJson() {
    document.getElementById('webJsonOutput').classList.toggle('hidden');
}

// ═══════════════════════════════════════════════════════════════════════════
// BULK ENGINE
// ═══════════════════════════════════════════════════════════════════════════

let currentJobId = null;

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
    if (mode === 'linkedin') extractOption.classList.remove('hidden');
    else {
        extractOption.classList.add('hidden');
        document.getElementById('extractOnlyCheck').checked = false;
    }
}

async function startBulkProcess() {
    const file = document.getElementById('fileInput').files[0];
    if (!file) { showToast("Please upload a file first"); return; }

    const btn = document.getElementById('bulkBtn');
    const btnText = document.getElementById('bulkBtnText');
    const btnLoader = document.getElementById('bulkBtnLoader');

    btn.disabled = true;
    btnText.textContent = "Processing...";
    btnLoader.classList.remove('hidden');
    document.getElementById('bulkProgressArea').classList.remove('hidden');
    document.getElementById('downloadArea').classList.add('hidden');
    document.getElementById('stopBulkBtn').disabled = false;

    try {
        const formData = new FormData();
        formData.append('file', file);

        const mode = document.querySelector('input[name="bulkMode"]:checked').value;
        const endpoint = mode === 'website' ? '/api/bulk-website-extract' : '/api/bulk-process';

        const startRow = document.getElementById('startRow').value;
        const endRow = document.getElementById('endRow').value;
        if (startRow) formData.append('start_row', startRow);
        if (endRow) formData.append('end_row', endRow);

        if (mode === 'linkedin' && document.getElementById('extractOnlyCheck').checked) {
            formData.append('extract_only', 'true');
        }

        const response = await fetch(endpoint, { method: 'POST', body: formData });
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
            bar.style.width = data.progress + '%';
            status.textContent = 'Analyzing Row...';
            percent.textContent = data.progress + '%';
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
    document.getElementById('bulkBtn').disabled = false;
    document.getElementById('bulkBtnText').textContent = "Initialize Bulk Process";
    document.getElementById('bulkBtnLoader').classList.add('hidden');
    document.getElementById('downloadArea').classList.remove('hidden');
    document.getElementById('bulkProgressArea').classList.add('hidden');
    document.getElementById('stopBulkBtn').disabled = false;
    document.getElementById('stopBtnText').textContent = "Stop Processing & Download";
    document.getElementById('stopBtnLoader').classList.add('hidden');
}

async function stopBulkProcess() {
    if (!currentJobId) return;
    const stopBtn = document.getElementById('stopBulkBtn');
    stopBtn.disabled = true;
    document.getElementById('stopBtnText').textContent = "Stopping...";
    document.getElementById('stopBtnLoader').classList.remove('hidden');
    try {
        await fetch(`/api/bulk-stop/${currentJobId}`, { method: 'POST' });
        showToast("Stop signal sent. Finishing current row...", "success");
        // Resume polling so we catch when the backend actually finishes the final row and sets status='completed'
        setTimeout(pollBulkStatus, 2000);
    } catch (err) {
        showToast("Failed to send stop signal.");
        stopBtn.disabled = false;
        document.getElementById('stopBtnText').textContent = "Stop Processing & Download";
        document.getElementById('stopBtnLoader').classList.add('hidden');
    }
}

function downloadBulkResults() {
    if (currentJobId) window.location.href = `/api/bulk-download/${currentJobId}`;
}

// ═══════════════════════════════════════════════════════════════════════════
// NAME EXTRACTOR
// ═══════════════════════════════════════════════════════════════════════════

let nameJobId = null;

document.getElementById('namesFileInput').addEventListener('change', function (e) {
    const fileName = e.target.files[0]?.name;
    if (fileName) {
        document.getElementById('namesFileName').textContent = fileName;
        document.getElementById('namesDropZone').style.borderColor = 'var(--text-main)';
    }
});

async function startNameExtract() {
    const file = document.getElementById('namesFileInput').files[0];
    if (!file) { showToast("Please upload a file first"); return; }

    const btn = document.getElementById('namesBtn');
    btn.disabled = true;
    document.getElementById('namesBtnText').textContent = "Extracting...";
    document.getElementById('namesBtnLoader').classList.remove('hidden');
    document.getElementById('namesProgressArea').classList.remove('hidden');
    document.getElementById('namesDownloadArea').classList.add('hidden');

    try {
        const formData = new FormData();
        formData.append('file', file);
        const response = await fetch('/api/bulk-name-extract', { method: 'POST', body: formData });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Name extraction failed");
        nameJobId = data.job_id;
        pollNameStatus();
    } catch (error) {
        showToast(error.message);
        btn.disabled = false;
        document.getElementById('namesBtnText').textContent = "Extract First Names";
        document.getElementById('namesBtnLoader').classList.add('hidden');
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
            bar.style.width = data.progress + '%';
            status.textContent = 'Extracting names...';
            percent.textContent = data.progress + '%';
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
    document.getElementById('namesBtn').disabled = false;
    document.getElementById('namesBtnText').textContent = "Extract First Names";
    document.getElementById('namesBtnLoader').classList.add('hidden');
    document.getElementById('namesDownloadArea').classList.remove('hidden');
    document.getElementById('namesProgressArea').classList.add('hidden');
}

function downloadNameResults() {
    if (nameJobId) window.location.href = `/api/bulk-download/${nameJobId}`;
}

// ═══════════════════════════════════════════════════════════════════════════
// LIVE LOG STREAM
// ═══════════════════════════════════════════════════════════════════════════

function initLogStream() {
    const logConsole = document.getElementById('logConsole');
    const statusDot = document.querySelector('.pulse-indicator');
    const statusText = document.getElementById('connectionStatus');

    const eventSource = new EventSource('/api/logs');

    eventSource.onmessage = (event) => {
        const entry = document.createElement('div');
        entry.className = 'log-entry';
        const lc = event.data.toLowerCase();
        if (lc.includes('error') || lc.includes('fail')) entry.classList.add('error');
        else if (lc.includes('success') || lc.includes('complete') || lc.includes('saved')) entry.classList.add('success');
        else if (lc.startsWith('[')) { /* standard log */ }
        else entry.classList.add('system');
        entry.textContent = event.data;
        logConsole.appendChild(entry);
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

// ═══════════════════════════════════════════════════════════════════════════
// INIT
// ═══════════════════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {
    initLogStream();
    lucide.createIcons();
    loadLeads(); // Prime the badge count on startup
});

// Enter key support
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
