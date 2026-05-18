/**
 * app.js — Tab router and shared utilities for Conductor Companion
 */

// ---------------------------------------------------------------------------
// Tab router
// ---------------------------------------------------------------------------

const TAB_PANELS = ['search', 'jq-lab', 'workers', 'migrations', 'diff', 'traces', 'digest'];

function activateTab(tabName) {
    TAB_PANELS.forEach(name => {
        const panel = document.getElementById('panel-' + name);
        const link = document.getElementById('tab-' + name);
        if (panel) panel.classList.toggle('active', name === tabName);
        if (link) link.classList.toggle('active', name === tabName);
    });

    // Persist active tab in URL hash
    history.replaceState(null, '', '#' + tabName);

    // Trigger tab-specific initialization
    const event = new CustomEvent('tabActivated', { detail: { tab: tabName } });
    document.dispatchEvent(event);
}

function initRouter() {
    // Wire nav links
    TAB_PANELS.forEach(name => {
        const link = document.getElementById('tab-' + name);
        if (link) {
            link.addEventListener('click', function (e) {
                e.preventDefault();
                activateTab(name);
            });
        }
    });

    // Restore from URL hash or default to 'search'
    const hash = window.location.hash.replace('#', '');
    const initialTab = TAB_PANELS.includes(hash) ? hash : 'search';
    activateTab(initialTab);
}

// ---------------------------------------------------------------------------
// Toast notifications
// ---------------------------------------------------------------------------

function showToast(message, type = 'info', durationMs = 4000) {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = 'toast toast-' + type;

    const msgSpan = document.createElement('span');
    msgSpan.textContent = message;

    const closeBtn = document.createElement('button');
    closeBtn.className = 'toast__close';
    closeBtn.innerHTML = '&times;';
    closeBtn.addEventListener('click', () => toast.remove());

    toast.appendChild(msgSpan);
    toast.appendChild(closeBtn);
    container.appendChild(toast);

    if (durationMs > 0) {
        setTimeout(() => toast.remove(), durationMs);
    }
}

// ---------------------------------------------------------------------------
// HTTP helpers
// ---------------------------------------------------------------------------

async function apiFetch(url, options = {}) {
    const defaults = {
        headers: { 'Content-Type': 'application/json' }
    };
    const merged = Object.assign({}, defaults, options);
    if (options.headers) {
        merged.headers = Object.assign({}, defaults.headers, options.headers);
    }

    try {
        const resp = await fetch(url, merged);
        const data = await resp.json();
        if (!resp.ok) {
            const msg = data.error || 'Request failed (' + resp.status + ')';
            throw new Error(msg);
        }
        return data;
    } catch (err) {
        if (err.name === 'SyntaxError') {
            throw new Error('Invalid JSON response from server');
        }
        throw err;
    }
}

async function apiGet(url) {
    return apiFetch(url, { method: 'GET' });
}

async function apiPost(url, body) {
    return apiFetch(url, {
        method: 'POST',
        body: JSON.stringify(body)
    });
}

async function apiDelete(url) {
    return apiFetch(url, { method: 'DELETE' });
}

// ---------------------------------------------------------------------------
// Utility helpers
// ---------------------------------------------------------------------------

function formatTimestamp(msOrIso) {
    if (!msOrIso) return '—';
    const d = typeof msOrIso === 'number' ? new Date(msOrIso) : new Date(msOrIso);
    if (isNaN(d.getTime())) return String(msOrIso);
    return d.toLocaleString();
}

function formatDurationMs(ms) {
    if (!ms && ms !== 0) return '—';
    if (ms < 1000) return ms + 'ms';
    if (ms < 60000) return (ms / 1000).toFixed(1) + 's';
    return (ms / 60000).toFixed(1) + 'min';
}

function statusBadge(status) {
    const cls = {
        COMPLETED: 'badge-completed',
        FAILED: 'badge-failed',
        RUNNING: 'badge-running',
        PAUSED: 'badge-paused',
        TERMINATED: 'badge-unknown',
        TIMED_OUT: 'badge-failed',
        healthy: 'badge-healthy',
        slow_poll: 'badge-slow-poll',
        down: 'badge-down',
        no_workers: 'badge-no-workers',
    }[status] || 'badge-unknown';
    return '<span class="badge ' + cls + '">' + (status || 'UNKNOWN') + '</span>';
}

function escapeHtml(str) {
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function copyToClipboard(text) {
    if (navigator.clipboard) {
        navigator.clipboard.writeText(text).then(() => {
            showToast('Copied to clipboard', 'success', 2000);
        }).catch(() => {
            showToast('Copy failed', 'error');
        });
    }
}

// ---------------------------------------------------------------------------
// Populate workflow dropdown from API
// ---------------------------------------------------------------------------

async function populateWorkflowDropdown(selectEl) {
    if (!selectEl) return;
    try {
        const defs = await apiGet('/api/v1/diff/workflows');
        selectEl.innerHTML = '<option value="">-- All Workflows --</option>';
        defs.forEach(wf => {
            const opt = document.createElement('option');
            opt.value = wf.name;
            opt.textContent = wf.name;
            selectEl.appendChild(opt);
        });
    } catch (err) {
        console.warn('Could not load workflow list:', err.message);
    }
}

// ---------------------------------------------------------------------------
// Initialization
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', function () {
    initRouter();
    console.log('Conductor Companion initialized');
});
