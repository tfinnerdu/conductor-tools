/**
 * app.js — Tab router and shared utilities for Conductor Companion
 */

// ---------------------------------------------------------------------------
// Tab router
// ---------------------------------------------------------------------------

const TAB_PANELS = ['search', 'jq-lab', 'workers', 'migrations', 'diff', 'reconciler', 'traces', 'digest', 'settings'];

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
// Mock/Live environment signal
// ---------------------------------------------------------------------------

// Populated from /api/v1/health/deep. mock === null means "not yet known".
window.ConductorEnv = { mock: null };

// True only when live (non-mock) mode has been positively confirmed.
function isLiveConductor() {
    return window.ConductorEnv.mock === false;
}

// Drives the MOCK/LIVE navbar chip, the live-environment banner, and the
// per-section destructive-action warnings. Called once the readiness probe
// resolves (see base.html).
function applyConductorEnvSignals(isMock) {
    window.ConductorEnv.mock = !!isMock;
    const live = !isMock;

    const mockChip = document.getElementById('mock-mode-chip');
    const liveChip = document.getElementById('live-mode-chip');
    const banner = document.getElementById('env-warning-banner');

    if (mockChip) mockChip.classList.toggle('d-none', live);
    if (liveChip) liveChip.classList.toggle('d-none', !live);
    if (banner) banner.classList.toggle('d-none', !live);

    // Per-section destructive-action warnings show only against a live Conductor.
    document.querySelectorAll('.live-warning').forEach(function (el) {
        el.classList.toggle('d-none', !live);
    });
}

// Confirmation guard for destructive actions. Against a live Conductor the
// prompt spells out the production impact; mock mode keeps a lightweight
// confirm so the flow is still exercised. Unknown env is treated as live.
function confirmDestructive(action, impact) {
    if (window.ConductorEnv.mock === true) {
        return confirm(action + '?');
    }
    return confirm(
        '⚠ LIVE ENVIRONMENT\n\n' +
        action + '\n\n' +
        impact + '\n\n' +
        'This affects real production data and cannot be undone here. Continue?'
    );
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
