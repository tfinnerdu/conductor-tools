/**
 * reconciler.js — Error Reconciler tab logic
 */

// Module state
var _selectedWorkflowIds = new Set();

// ---------------------------------------------------------------------------
// Failure summary
// ---------------------------------------------------------------------------

async function loadFailureSummary() {
    const el = document.getElementById('reconciler-summary-content');
    const hoursBack = (document.getElementById('reconciler-hours-back') || {}).value || 24;

    if (el) el.innerHTML = '<p class="text-muted font-sm"><span class="spinner"></span> Loading...</p>';

    try {
        const data = await apiGet('/api/v1/reconciler/summary?hours_back=' + hoursBack);
        renderFailureSummary(data);
        await loadFailureGroups(hoursBack);

        const lastRefreshed = document.getElementById('reconciler-last-refreshed');
        if (lastRefreshed) lastRefreshed.textContent = 'Refreshed: ' + new Date().toLocaleTimeString();
    } catch (err) {
        if (el) el.innerHTML = '<p class="text-muted font-sm">Error loading summary: ' + escapeHtml(err.message) + '</p>';
        showToast('Reconciler error: ' + err.message, 'error');
    }
}

function renderFailureSummary(data) {
    const el = document.getElementById('reconciler-summary-content');
    if (!el) return;

    const summary = data.summary || {};
    const total = data.total_failed || 0;
    const analyzed = data.workflows_analyzed || 0;
    const hoursBack = data.hours_back || 24;

    if (Object.keys(summary).length === 0) {
        el.innerHTML = '<div style="color:#155724;background:#d4edda;padding:0.5rem 0.75rem;border-radius:4px;font-size:0.85rem">' +
            'No failures found in the last ' + hoursBack + 'h across ' + analyzed + ' workflows.</div>';
        return;
    }

    var html = '<div style="margin-bottom:0.5rem;font-size:0.85rem"><strong>' + total + '</strong> total failures across ' +
        '<strong>' + Object.keys(summary).length + '</strong> workflows (last ' + hoursBack + 'h)</div>';
    html += renderFailureGroups(summary);
    el.innerHTML = html;
}

function renderFailureGroups(summary) {
    var html = '';
    for (var wfName in summary) {
        if (!Object.prototype.hasOwnProperty.call(summary, wfName)) continue;
        var wfData = summary[wfName];
        var wfTotal = Object.values(wfData).reduce(function (s, d) { return s + (d.count || 0); }, 0);

        html += '<div style="border:1px solid #dee2e6;border-radius:4px;margin-bottom:0.75rem">';
        html += '<div style="background:#1F3864;color:#fff;padding:0.4rem 0.75rem;border-radius:4px 4px 0 0;font-size:0.85rem">' +
            '<strong>' + escapeHtml(wfName) + '</strong>' +
            '<span style="float:right">' + wfTotal + ' failures</span></div>';
        html += '<div style="padding:0.5rem 0.75rem">';

        for (var taskType in wfData) {
            if (!Object.prototype.hasOwnProperty.call(wfData, taskType)) continue;
            var taskData = wfData[taskType];
            var count = taskData.count || 0;
            var codes = taskData.error_codes || {};

            html += '<div style="margin-bottom:0.4rem">';
            html += '<span style="font-size:0.85rem"><strong>' + escapeHtml(taskType) + '</strong>: ' + count + ' failures</span> ';

            for (var code in codes) {
                if (!Object.prototype.hasOwnProperty.call(codes, code)) continue;
                html += '<span class="badge badge-failed" style="font-size:0.7rem;margin-left:4px">' +
                    escapeHtml(code) + ' &times;' + codes[code] + '</span>';
            }
            html += '</div>';
        }

        html += '</div></div>';
    }
    return html;
}

// ---------------------------------------------------------------------------
// Load failure groups (task-type view)
// ---------------------------------------------------------------------------

async function loadFailureGroups(hoursBack) {
    const el = document.getElementById('reconciler-groups-content');
    if (!el) return;

    const hoursVal = hoursBack || (document.getElementById('reconciler-hours-back') || {}).value || 24;

    try {
        const data = await apiGet('/api/v1/reconciler/failures?hours_back=' + hoursVal + '&per_page=50');
        renderGroupsTable(data.groups || []);
    } catch (err) {
        el.innerHTML = '<p class="text-muted font-sm">Error: ' + escapeHtml(err.message) + '</p>';
    }
}

function renderGroupsTable(groups) {
    const el = document.getElementById('reconciler-groups-content');
    if (!el) return;

    if (!groups || groups.length === 0) {
        el.innerHTML = '<p class="text-muted font-sm">No failure groups found.</p>';
        _updateBulkRetryCard();
        return;
    }

    var html = '<div class="table-wrapper"><table class="data-table"><thead><tr>' +
        '<th><input type="checkbox" id="reconciler-select-all" title="Select all" /></th>' +
        '<th>Task Type</th><th>Count</th><th>Top Error Codes</th><th>Actions</th>' +
        '</tr></thead><tbody>';

    groups.forEach(function (group) {
        var taskType = group.task_type || 'unknown';
        var count = group.count || 0;
        var reasons = group.reasons || {};
        var wfIds = group.workflow_ids || [];

        var topCodes = Object.entries(reasons)
            .sort(function (a, b) { return b[1] - a[1]; })
            .slice(0, 3)
            .map(function (kv) {
                return '<span class="badge badge-failed" style="font-size:0.7rem">' +
                    escapeHtml(kv[0]) + ' &times;' + kv[1] + '</span>';
            }).join(' ');

        var safeIds = JSON.stringify(wfIds);
        html += '<tr>' +
            '<td><input type="checkbox" class="reconciler-group-checkbox" data-ids="' +
            escapeHtml(safeIds) + '" onchange="onGroupCheckboxChange()" /></td>' +
            '<td><code>' + escapeHtml(taskType) + '</code></td>' +
            '<td><strong>' + count + '</strong></td>' +
            '<td>' + (topCodes || '<span class="text-muted">—</span>') + '</td>' +
            '<td>' +
            '<button class="btn btn-outline btn-sm" onclick="retryGroup(' + escapeHtml(safeIds) + ')">Retry All</button>' +
            '</td>' +
            '</tr>';
    });

    html += '</tbody></table></div>';
    el.innerHTML = html;

    // Wire select-all checkbox
    const selectAll = document.getElementById('reconciler-select-all');
    if (selectAll) {
        selectAll.addEventListener('change', function () {
            document.querySelectorAll('.reconciler-group-checkbox').forEach(function (cb) {
                cb.checked = selectAll.checked;
            });
            onGroupCheckboxChange();
        });
    }
}

function onGroupCheckboxChange() {
    _selectedWorkflowIds.clear();
    document.querySelectorAll('.reconciler-group-checkbox:checked').forEach(function (cb) {
        var ids = JSON.parse(cb.dataset.ids || '[]');
        ids.forEach(function (id) { _selectedWorkflowIds.add(id); });
    });
    _updateBulkRetryCard();
}

function _updateBulkRetryCard() {
    const card = document.getElementById('reconciler-bulk-retry-card');
    const countEl = document.getElementById('reconciler-selected-count');
    if (!card) return;

    const count = _selectedWorkflowIds.size;
    if (count > 0) {
        card.style.display = '';
        if (countEl) countEl.textContent = count + ' execution' + (count === 1 ? '' : 's') + ' selected';
    } else {
        card.style.display = 'none';
    }
}

async function retryGroup(workflowIds) {
    if (!workflowIds || workflowIds.length === 0) return;
    await bulkRetry(workflowIds);
}

// ---------------------------------------------------------------------------
// Bulk retry
// ---------------------------------------------------------------------------

async function bulkRetry(workflowIds) {
    if (!workflowIds || workflowIds.length === 0) {
        workflowIds = Array.from(_selectedWorkflowIds);
    }
    if (workflowIds.length === 0) {
        showToast('No executions selected', 'warning');
        return;
    }
    if (!confirmAction(
        'Retry ' + workflowIds.length + ' failed workflow execution' +
            (workflowIds.length === 1 ? '' : 's'),
        'Each retry re-runs the workflow and re-triggers its real task side effects.'
    )) return;

    const btn = document.getElementById('reconciler-bulk-retry-btn');
    if (btn) { btn.disabled = true; btn.textContent = 'Retrying...'; }

    try {
        const data = await apiPost('/api/v1/reconciler/failures/bulk-retry', { workflow_ids: workflowIds });
        const retried = data.retried || 0;
        const errors = data.errors || [];

        const resultEl = document.getElementById('reconciler-retry-result');
        if (resultEl) {
            var msg = '<div style="color:#155724;background:#d4edda;padding:0.4rem 0.75rem;border-radius:4px;font-size:0.85rem">' +
                'Retried <strong>' + retried + '</strong> workflow' + (retried === 1 ? '' : 's') + '.';
            if (errors.length > 0) {
                msg += ' <span style="color:#856404">' + errors.length + ' error(s).</span>';
            }
            msg += '</div>';
            resultEl.innerHTML = msg;
        }

        showToast('Retried ' + retried + ' workflows', retried > 0 ? 'success' : 'warning');
        _selectedWorkflowIds.clear();
        _updateBulkRetryCard();

        // Refresh groups
        const hoursBack = (document.getElementById('reconciler-hours-back') || {}).value || 24;
        await loadFailureGroups(hoursBack);
    } catch (err) {
        showToast('Retry error: ' + err.message, 'error');
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = 'Bulk Retry Selected'; }
    }
}

// ---------------------------------------------------------------------------
// Initialization
// ---------------------------------------------------------------------------

document.addEventListener('tabActivated', function (e) {
    if (e.detail.tab === 'reconciler') {
        loadFailureSummary();
    }
});

document.addEventListener('DOMContentLoaded', function () {
    const refreshBtn = document.getElementById('reconciler-refresh-btn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', loadFailureSummary);
    }

    const hoursSelect = document.getElementById('reconciler-hours-back');
    if (hoursSelect) {
        hoursSelect.addEventListener('change', loadFailureSummary);
    }

    const bulkRetryBtn = document.getElementById('reconciler-bulk-retry-btn');
    if (bulkRetryBtn) {
        bulkRetryBtn.addEventListener('click', function () {
            bulkRetry(Array.from(_selectedWorkflowIds));
        });
    }
});
