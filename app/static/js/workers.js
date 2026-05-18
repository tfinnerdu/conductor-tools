/**
 * workers.js — Workers tab logic with auto-refresh
 */

(function () {
    'use strict';

    let refreshInterval = null;
    let lastRefreshTime = null;
    let refreshCounterInterval = null;

    function renderWorkerTable(data) {
        const tbody = document.getElementById('workers-tbody');
        const summary = document.getElementById('workers-summary');
        if (!tbody) return;

        const workers = data.workers || [];
        const counts = data.summaryCounts || {};

        if (summary) {
            summary.innerHTML = `
                <div class="grid-3" style="grid-template-columns:repeat(4,1fr)">
                    <div class="stat-box stat-box--green">
                        <div class="stat-box__value">${counts.healthy || 0}</div>
                        <div class="stat-box__label">Healthy</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-box__value" style="color:#856404">${counts.slow_poll || 0}</div>
                        <div class="stat-box__label">Slow Poll</div>
                    </div>
                    <div class="stat-box stat-box--red">
                        <div class="stat-box__value">${counts.down || 0}</div>
                        <div class="stat-box__label">Down</div>
                    </div>
                    <div class="stat-box stat-box--red">
                        <div class="stat-box__value">${counts.no_workers || 0}</div>
                        <div class="stat-box__label">No Workers</div>
                    </div>
                </div>
            `;
        }

        if (workers.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted" style="padding:2rem">No task types found.</td></tr>';
            return;
        }

        tbody.innerHTML = workers.map(w => {
            const statusClass = 'status-' + w.status.replace('_', '-');
            const ago = w.lastPollAgoSeconds !== null ? formatDurationMs(w.lastPollAgoSeconds * 1000) : 'never';
            return `
                <tr class="${statusClass}" style="cursor:pointer" onclick="loadWorkerPerf('${escapeHtml(w.taskType)}')">
                    <td><strong>${escapeHtml(w.taskType)}</strong></td>
                    <td>${w.workerCount}</td>
                    <td>${ago}</td>
                    <td>${w.queueDepth}</td>
                    <td>${statusBadge(w.status)}</td>
                </tr>
            `;
        }).join('');
    }

    async function refreshWorkers() {
        try {
            const data = await apiGet('/api/v1/workers/status');
            renderWorkerTable(data);
            lastRefreshTime = Date.now();
        } catch (err) {
            showToast('Workers refresh failed: ' + err.message, 'error');
        }
    }

    function updateRefreshCounter() {
        const el = document.getElementById('workers-last-refreshed');
        if (!el || !lastRefreshTime) return;
        const ago = Math.round((Date.now() - lastRefreshTime) / 1000);
        el.textContent = 'Last refreshed: ' + ago + 's ago';
    }

    window.loadWorkerPerf = async function (taskType) {
        const panel = document.getElementById('worker-perf-panel');
        if (!panel) return;

        panel.classList.remove('d-none');
        document.getElementById('worker-perf-task-type').textContent = taskType;

        try {
            const perf = await apiGet('/api/v1/workers/' + encodeURIComponent(taskType) + '/performance');
            const el = document.getElementById('worker-perf-content');
            if (!el) return;

            el.innerHTML = `
                <div class="grid-3" style="grid-template-columns:repeat(3,1fr);margin-bottom:1rem">
                    <div class="stat-box">
                        <div class="stat-box__value">${perf.totalExecutions || 0}</div>
                        <div class="stat-box__label">Total Executions</div>
                    </div>
                    <div class="stat-box stat-box--green">
                        <div class="stat-box__value">${perf.successRate || 0}%</div>
                        <div class="stat-box__label">Success Rate</div>
                    </div>
                    <div class="stat-box stat-box--red">
                        <div class="stat-box__value">${perf.failedCount || 0}</div>
                        <div class="stat-box__label">Failures</div>
                    </div>
                </div>
                <table class="data-table">
                    <thead><tr><th>Metric</th><th>Value</th></tr></thead>
                    <tbody>
                        <tr><td>Avg Duration</td><td>${formatDurationMs(perf.avgDurationMs)}</td></tr>
                        <tr><td>Min Duration</td><td>${formatDurationMs(perf.minDurationMs)}</td></tr>
                        <tr><td>Max Duration</td><td>${formatDurationMs(perf.maxDurationMs)}</td></tr>
                        <tr><td>p50 Duration</td><td>${formatDurationMs(perf.p50DurationMs)}</td></tr>
                        <tr><td>p95 Duration</td><td>${formatDurationMs(perf.p95DurationMs)}</td></tr>
                        <tr><td>p99 Duration</td><td>${formatDurationMs(perf.p99DurationMs)}</td></tr>
                    </tbody>
                </table>
            `;
        } catch (err) {
            showToast('Could not load performance data', 'error');
        }
    };

    function startAutoRefresh() {
        if (refreshInterval) clearInterval(refreshInterval);
        if (refreshCounterInterval) clearInterval(refreshCounterInterval);

        refreshWorkers();
        refreshInterval = setInterval(refreshWorkers, 5000);
        refreshCounterInterval = setInterval(updateRefreshCounter, 1000);
    }

    function stopAutoRefresh() {
        if (refreshInterval) { clearInterval(refreshInterval); refreshInterval = null; }
        if (refreshCounterInterval) { clearInterval(refreshCounterInterval); refreshCounterInterval = null; }
    }

    function initWorkers() {
        const manualRefreshBtn = document.getElementById('workers-refresh-btn');
        if (manualRefreshBtn) manualRefreshBtn.addEventListener('click', refreshWorkers);
    }

    document.addEventListener('tabActivated', function (e) {
        if (e.detail.tab === 'workers') {
            startAutoRefresh();
        } else {
            stopAutoRefresh();
        }
    });

    document.addEventListener('DOMContentLoaded', initWorkers);
})();
