/**
 * migrations.js — Migrations (Batches) tab logic
 */

(function () {
    'use strict';

    async function loadBatches() {
        const listEl = document.getElementById('batches-list');
        if (!listEl) return;

        try {
            const batches = await apiGet('/api/v1/batches');

            if (batches.length === 0) {
                listEl.innerHTML = '<p class="text-muted">No batches yet. Create one below.</p>';
                return;
            }

            listEl.innerHTML = batches.map(b => `
                <div class="card" id="batch-card-${b.id}">
                    <div class="d-flex align-center gap-1">
                        <div style="flex:1">
                            <strong>${escapeHtml(b.name)}</strong>
                            <span class="text-muted"> — ${escapeHtml(b.workflowName)}</span>
                        </div>
                        <button class="btn btn-outline btn-sm" onclick="pollBatchStatus(${b.id})">Refresh</button>
                        <button class="btn btn-secondary btn-sm" onclick="retryFailures(${b.id})">Retry Failures</button>
                        <button class="btn btn-outline btn-sm" onclick="exportBatch(${b.id})">Export CSV</button>
                    </div>
                    <div id="batch-status-${b.id}" class="mt-1">
                        <span class="text-muted font-sm">Click Refresh to load status</span>
                    </div>
                </div>
            `).join('');
        } catch (err) {
            listEl.innerHTML = '<p class="text-muted">Could not load batches.</p>';
            showToast('Failed to load batches: ' + err.message, 'error');
        }
    }

    window.pollBatchStatus = async function (batchId) {
        const statusEl = document.getElementById('batch-status-' + batchId);
        if (!statusEl) return;

        statusEl.innerHTML = '<span class="spinner"></span> Loading...';

        try {
            const s = await apiGet('/api/v1/batches/' + batchId + '/status');
            const pct = s.progressPercent || 0;

            statusEl.innerHTML = `
                <div class="mt-1">
                    <div class="d-flex align-center gap-1 mb-1">
                        <span class="font-sm"><strong>${s.completed}</strong> completed</span>
                        <span class="font-sm text-muted">/</span>
                        <span class="font-sm">${s.totalExpected} expected</span>
                        <span class="font-sm" style="margin-left:auto">${pct}%</span>
                    </div>
                    <div class="progress">
                        <div class="progress-bar" style="width:${pct}%"></div>
                    </div>
                    <div class="d-flex gap-2 mt-1 font-sm">
                        <span>${statusBadge('COMPLETED')} ${s.completed}</span>
                        <span>${statusBadge('FAILED')} ${s.failed}</span>
                        <span>${statusBadge('RUNNING')} ${s.running}</span>
                    </div>
                </div>
            `;
        } catch (err) {
            statusEl.innerHTML = '<span class="text-muted font-sm">Error loading status</span>';
            showToast('Status check failed: ' + err.message, 'error');
        }
    };

    window.retryFailures = async function (batchId) {
        if (!confirmAction(
            'Retry all FAILED executions in this batch',
            'Every failed workflow re-runs against Conductor and re-triggers its task side effects.'
        )) return;
        try {
            const result = await apiFetch('/api/v1/batches/' + batchId + '/retry-failures', { method: 'POST' });
            showToast('Retried ' + result.retriedCount + ' workflows' +
                (result.errorCount > 0 ? ' (' + result.errorCount + ' errors)' : ''), 'success');
            pollBatchStatus(batchId);
        } catch (err) {
            showToast('Retry failed: ' + err.message, 'error');
        }
    };

    window.exportBatch = async function (batchId) {
        try {
            const resp = await fetch('/api/v1/batches/' + batchId + '/export');
            if (!resp.ok) {
                showToast('Export failed', 'error');
                return;
            }
            const blob = await resp.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'batch_' + batchId + '_failures.csv';
            a.click();
            URL.revokeObjectURL(url);
            showToast('Exported failures CSV', 'success');
        } catch (err) {
            showToast('Export failed: ' + err.message, 'error');
        }
    };

    async function createBatch(e) {
        e.preventDefault();

        const name = (document.getElementById('batch-name') || {}).value || '';
        const workflowName = (document.getElementById('batch-workflow-name') || {}).value || '';
        const correlationIdPrefix = (document.getElementById('batch-correlation-prefix') || {}).value || '';
        const totalExpected = parseInt((document.getElementById('batch-total-expected') || {}).value || '0', 10);

        if (!name || !workflowName) {
            showToast('Name and Workflow Name are required', 'warning');
            return;
        }
        if (!confirmAction(
            'Create migration batch "' + name + '"',
            'This adds a new batch record to the Conductor Companion database.'
        )) return;

        const btn = document.getElementById('create-batch-btn');
        if (btn) { btn.disabled = true; btn.textContent = 'Creating...'; }

        try {
            await apiPost('/api/v1/batches', { name, workflowName, correlationIdPrefix, totalExpected });
            showToast('Batch created: ' + name, 'success');

            // Reset form
            const form = document.getElementById('create-batch-form');
            if (form) form.reset();

            loadBatches();
        } catch (err) {
            showToast('Create failed: ' + err.message, 'error');
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = 'Create Batch'; }
        }
    }

    function initMigrations() {
        const form = document.getElementById('create-batch-form');
        if (form) form.addEventListener('submit', createBatch);

        // Populate workflow name dropdown
        const wfSelect = document.getElementById('batch-workflow-name');
        if (wfSelect) {
            apiGet('/api/v1/diff/workflows').then(defs => {
                defs.forEach(wf => {
                    const opt = document.createElement('option');
                    opt.value = wf.name;
                    opt.textContent = wf.name;
                    wfSelect.appendChild(opt);
                });
            }).catch(() => {});
        }
    }

    document.addEventListener('tabActivated', function (e) {
        if (e.detail.tab === 'migrations') {
            loadBatches();
        }
    });

    document.addEventListener('DOMContentLoaded', initMigrations);
})();
