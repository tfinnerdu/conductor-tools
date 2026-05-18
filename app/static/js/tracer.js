/**
 * tracer.js — Correlation Tracer tab logic
 */

// ---------------------------------------------------------------------------
// Tracer search
// ---------------------------------------------------------------------------

async function traceSearch(identifier, searchType) {
    if (!identifier) {
        showToast('Please enter an identifier to trace', 'warning');
        return;
    }

    const btn = document.getElementById('tracer-search-btn');
    if (btn) { btn.disabled = true; btn.textContent = 'Tracing...'; }

    const body = {};
    if (searchType === 'guid') {
        body.guid = identifier;
        body.sis_id = '';
    } else {
        body.guid = '';
        body.sis_id = identifier;
    }

    try {
        const data = await apiPost('/api/v1/tracer/person', body);
        renderTimeline(data.trace || []);
        renderDiagnosis(data.diagnosis || '', data.trace || []);

        // Show recent traces
        await loadRecentTraces();
        showToast('Trace complete: ' + (data.trace || []).length + ' events found', 'success');
    } catch (err) {
        showToast('Trace error: ' + err.message, 'error');
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = 'Trace'; }
    }
}

function renderDiagnosis(diagnosis, events) {
    const el = document.getElementById('tracer-diagnosis');
    if (!el) return;

    const hasErrors = events.some(e => e.status === 'error');
    const hasWarnings = events.some(e => e.status === 'warning');

    let bg = '#d4edda'; let color = '#155724';
    if (hasErrors) { bg = '#ffeef0'; color = '#b31d28'; }
    else if (hasWarnings) { bg = '#fff3cd'; color = '#856404'; }

    el.style.background = bg;
    el.style.color = color;
    el.textContent = diagnosis || 'Trace complete.';
    el.classList.remove('d-none');
}

function renderTimeline(events) {
    const card = document.getElementById('tracer-timeline-card');
    const list = document.getElementById('tracer-timeline');
    const count = document.getElementById('tracer-event-count');

    if (!list) return;

    if (!events || events.length === 0) {
        list.innerHTML = '<li class="text-muted font-sm" style="padding:1rem">No events found for this identifier.</li>';
        if (card) card.classList.remove('d-none');
        if (count) count.textContent = '0 events';
        return;
    }

    if (count) count.textContent = events.length + ' event' + (events.length === 1 ? '' : 's');

    list.innerHTML = events.map(function (ev) {
        const ts = ev.timestamp ? new Date(ev.timestamp).toLocaleString() : '—';
        const systemBadge = _systemBadge(ev.system);
        const statusIcon = _statusIcon(ev.status);
        const detail = ev.detail ? '<div class="font-sm text-muted" style="margin-top:2px">' + escapeHtml(ev.detail) + '</div>' : '';
        const records = (ev.records && ev.records.length > 0)
            ? '<div class="font-sm" style="margin-top:4px">' +
              ev.records.map(function (r) {
                  return '<span class="badge badge-unknown" style="margin-right:4px">' +
                      escapeHtml(r.Id || '') + ' ' + escapeHtml(r.FirstName || '') + ' ' + escapeHtml(r.LastName || '') +
                      (r.SIS_ID__c ? ' (SIS: ' + escapeHtml(r.SIS_ID__c) + ')' : '') +
                      '</span>';
              }).join(' ') + '</div>'
            : '';

        return '<li style="padding:0.6rem 0;border-bottom:1px solid #f0f0f0">' +
            '<div class="d-flex align-center gap-1">' +
            statusIcon + systemBadge +
            '<strong style="flex:1">' + escapeHtml(ev.event || '') + '</strong>' +
            '<span class="text-muted font-sm">' + escapeHtml(ts) + '</span>' +
            '</div>' + detail + records + '</li>';
    }).join('');

    if (card) card.classList.remove('d-none');
}

function _systemBadge(system) {
    const colors = {
        CONDUCTOR: '#1F3864',
        SALESFORCE: '#0070d2',
        ETHOS: '#FF7900',
    };
    const bg = colors[system] || '#6c757d';
    return '<span class="badge" style="background:' + bg + ';color:#fff;font-size:0.7rem;padding:2px 6px;margin-right:4px">' +
        escapeHtml(system || 'UNKNOWN') + '</span>';
}

function _statusIcon(status) {
    const icons = { ok: '&#9989;', error: '&#10060;', warning: '&#9888;', running: '&#9654;' };
    const icon = icons[status] || '&#8226;';
    return '<span style="margin-right:4px">' + icon + '</span>';
}

// ---------------------------------------------------------------------------
// Recent traces
// ---------------------------------------------------------------------------

async function loadRecentTraces() {
    const el = document.getElementById('tracer-recent-list');
    if (!el) return;

    try {
        const data = await apiGet('/api/v1/tracer/recent');
        const recent = data.recent || [];
        if (recent.length === 0) {
            el.innerHTML = '<p class="text-muted font-sm">No recent traces yet.</p>';
            return;
        }

        el.innerHTML = recent.map(function (t) {
            const ts = t.searched_at ? new Date(t.searched_at).toLocaleString() : '—';
            const id = t.guid || t.sis_id || '—';
            const errBadge = t.had_errors
                ? '<span class="badge badge-failed" style="margin-left:4px">errors</span>'
                : '<span class="badge badge-completed" style="margin-left:4px">ok</span>';
            return '<div style="padding:0.3rem 0;border-bottom:1px solid #f0f0f0;font-size:0.85rem">' +
                '<span class="text-muted">' + escapeHtml(ts) + '</span> &mdash; ' +
                '<strong>' + escapeHtml(id) + '</strong>' + errBadge +
                ' <span class="text-muted font-sm">(' + (t.event_count || 0) + ' events)</span>' +
                ' <a href="#" class="font-sm" onclick="retrace(' + JSON.stringify(id) + ');return false">Retrace</a>' +
                '</div>';
        }).join('');
    } catch (err) {
        el.innerHTML = '<p class="text-muted font-sm">Could not load recent traces.</p>';
    }
}

function retrace(identifier) {
    const input = document.getElementById('tracer-identifier');
    if (input) input.value = identifier;
    // Auto-detect search type
    const isGuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(identifier);
    const radio = document.querySelector('input[name="tracer-type"][value="' + (isGuid ? 'guid' : 'sis_id') + '"]');
    if (radio) radio.checked = true;
    traceSearch(identifier, isGuid ? 'guid' : 'sis_id');
}

// ---------------------------------------------------------------------------
// Initialization
// ---------------------------------------------------------------------------

function initTracer() {
    const btn = document.getElementById('tracer-search-btn');
    if (btn) {
        btn.addEventListener('click', function () {
            const identifier = (document.getElementById('tracer-identifier') || {}).value || '';
            const searchType = (document.querySelector('input[name="tracer-type"]:checked') || {}).value || 'guid';
            traceSearch(identifier.trim(), searchType);
        });
    }

    const input = document.getElementById('tracer-identifier');
    if (input) {
        input.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') btn && btn.click();
        });
    }

    loadRecentTraces();
}

document.addEventListener('tabActivated', function (e) {
    if (e.detail.tab === 'traces') {
        loadRecentTraces();
    }
});

document.addEventListener('DOMContentLoaded', function () {
    initTracer();
});
