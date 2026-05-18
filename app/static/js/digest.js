/**
 * digest.js — Performance Digest tab logic
 */

// ---------------------------------------------------------------------------
// Load digest data
// ---------------------------------------------------------------------------

async function loadDigest() {
    const tbody = document.getElementById('digest-workflows-tbody');
    const lastGen = document.getElementById('digest-last-generated');

    if (tbody) {
        tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted" style="padding:2rem">' +
            '<span class="spinner"></span> Loading digest...</td></tr>';
    }

    try {
        const data = await apiGet('/api/v1/digest/daily');
        renderWorkflowTable(data.workflows || []);

        if (lastGen && data.generated_at) {
            lastGen.textContent = 'Generated: ' + new Date(data.generated_at).toLocaleString();
        }

        renderRegressions(data.regressions || []);
        await loadRecommendations();
    } catch (err) {
        if (tbody) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted" style="padding:2rem">' +
                'Failed to load digest: ' + escapeHtml(err.message) + '</td></tr>';
        }
        showToast('Digest error: ' + err.message, 'error');
    }
}

function renderWorkflowTable(workflows) {
    const tbody = document.getElementById('digest-workflows-tbody');
    if (!tbody) return;

    if (!workflows || workflows.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted" style="padding:2rem">No workflow data available.</td></tr>';
        return;
    }

    tbody.innerHTML = workflows.map(function (wf) {
        const failRateClass = wf.failure_rate_pct > 20 ? 'color:#b31d28;font-weight:bold' :
            wf.failure_rate_pct > 5 ? 'color:#856404' : '';
        const trendArrow = _trendArrow(wf.trend);
        const trendColor = wf.trend === 'up' ? 'color:#b31d28' : wf.trend === 'down' ? 'color:#155724' : 'color:#6c757d';

        return '<tr>' +
            '<td><strong>' + escapeHtml(wf.name || '') + '</strong></td>' +
            '<td>' + (wf.total || 0) + '</td>' +
            '<td>' + (wf.failed || 0) + '</td>' +
            '<td style="' + failRateClass + '">' + (wf.failure_rate_pct || 0) + '%</td>' +
            '<td>' + formatDurationMs(wf.avg_ms || 0) + '</td>' +
            '<td style="' + trendColor + '">' + trendArrow + '</td>' +
            '</tr>';
    }).join('');
}

function _trendArrow(trend) {
    const arrows = { up: '&uarr;', down: '&darr;', stable: '&rarr;', new: 'new' };
    return arrows[trend] || '&mdash;';
}

function renderRegressions(regressions) {
    const card = document.getElementById('digest-regressions-card');
    const content = document.getElementById('digest-regressions-content');
    if (!card || !content) return;

    if (!regressions || regressions.length === 0) {
        card.classList.add('d-none');
        return;
    }

    card.classList.remove('d-none');
    content.innerHTML = regressions.map(function (r) {
        return '<div style="padding:0.5rem;background:#ffeef0;border-radius:4px;margin-bottom:0.5rem;font-size:0.85rem">' +
            '<strong>' + escapeHtml(r.workflow_name) + '</strong>' +
            ' is <strong>' + r.pct_slower + '% slower</strong> than 7-day average ' +
            '(' + formatDurationMs(r.current_avg_ms) + ' vs ' + formatDurationMs(r.historical_avg_ms) + ' avg)' +
            '</div>';
    }).join('');
}

// ---------------------------------------------------------------------------
// Recommendations
// ---------------------------------------------------------------------------

async function loadRecommendations() {
    const el = document.getElementById('digest-recommendations');
    if (!el) return;

    try {
        const data = await apiGet('/api/v1/digest/recommendations');
        renderRecommendations(data.recommendations || []);
    } catch (err) {
        el.innerHTML = '<p class="text-muted font-sm">Could not load recommendations.</p>';
    }
}

function renderRecommendations(recs) {
    const el = document.getElementById('digest-recommendations');
    if (!el) return;

    if (!recs || recs.length === 0) {
        el.innerHTML = '<div style="color:#155724;background:#d4edda;padding:0.5rem 0.75rem;border-radius:4px;font-size:0.85rem">' +
            'No issues found — all workflows are healthy.</div>';
        return;
    }

    el.innerHTML = recs.map(function (rec) {
        const bg = rec.severity === 'error' ? '#ffeef0' : '#fff3cd';
        const color = rec.severity === 'error' ? '#b31d28' : '#856404';
        const badge = '<span class="badge" style="background:' + (rec.severity === 'error' ? '#b31d28' : '#856404') +
            ';color:#fff;font-size:0.7rem;margin-right:6px">' + escapeHtml(rec.severity.toUpperCase()) + '</span>';
        const catBadge = '<span class="badge badge-unknown" style="font-size:0.7rem;margin-right:6px">' +
            escapeHtml(rec.category) + '</span>';

        return '<div style="background:' + bg + ';color:' + color + ';padding:0.5rem 0.75rem;border-radius:4px;margin-bottom:0.4rem;font-size:0.85rem">' +
            badge + catBadge + escapeHtml(rec.message) +
            '</div>';
    }).join('');
}

// ---------------------------------------------------------------------------
// Initialization
// ---------------------------------------------------------------------------

document.addEventListener('tabActivated', function (e) {
    if (e.detail.tab === 'digest') {
        loadDigest();
    }
});

document.addEventListener('DOMContentLoaded', function () {
    const refreshBtn = document.getElementById('digest-refresh-btn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', loadDigest);
    }
});
