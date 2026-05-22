/**
 * search.js — Advanced Search tab logic
 */

(function () {
    'use strict';

    let filterCount = 0;

    function buildFilterRow(index) {
        return `
            <div class="filter-row" id="filter-row-${index}">
                <input type="text" class="form-control filter-path" placeholder="JSON path (e.g. input.orderId)" />
                <select class="form-control filter-op">
                    <option value="eq">equals</option>
                    <option value="neq">not equals</option>
                    <option value="contains">contains</option>
                    <option value="not_contains">not contains</option>
                    <option value="exists">exists</option>
                    <option value="not_exists">not exists</option>
                </select>
                <input type="text" class="form-control filter-value" placeholder="Value" />
                <button class="btn btn-outline btn-sm" onclick="removeFilterRow(${index})">Remove</button>
            </div>
        `;
    }

    window.addFilterRow = function () {
        filterCount++;
        const container = document.getElementById('filter-rows');
        if (!container) return;
        const div = document.createElement('div');
        div.innerHTML = buildFilterRow(filterCount);
        container.appendChild(div.firstElementChild);
    };

    window.removeFilterRow = function (index) {
        const row = document.getElementById('filter-row-' + index);
        if (row) row.remove();
    };

    function gatherFilters() {
        const rows = document.querySelectorAll('.filter-row');
        const filters = [];
        rows.forEach(row => {
            const path = row.querySelector('.filter-path').value.trim();
            const operator = row.querySelector('.filter-op').value;
            const value = row.querySelector('.filter-value').value.trim();
            if (path) {
                filters.push({ path, operator, value });
            }
        });
        return filters;
    }

    function renderStatusSummary(statusCounts) {
        const el = document.getElementById('search-status-summary');
        if (!el) return;
        const entries = Object.entries(statusCounts || {});
        if (entries.length === 0) {
            el.innerHTML = '';
            return;
        }
        const parts = entries.map(([s, count]) =>
            '<span class="badge ' + (s === 'COMPLETED' ? 'badge-completed' : s === 'FAILED' ? 'badge-failed' : 'badge-unknown') + '">' +
            s + ': ' + count + '</span>'
        );
        el.innerHTML = '<strong>Status summary:</strong> ' + parts.join(' ');
    }

    function renderResults(results) {
        const tbody = document.getElementById('search-results-body');
        const countEl = document.getElementById('search-result-count');
        if (!tbody) return;

        if (countEl) countEl.textContent = results.length + ' result(s)';

        if (results.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted" style="padding:2rem">No results found.</td></tr>';
            return;
        }

        tbody.innerHTML = results.map(r => `
            <tr>
                <td><span class="font-mono font-sm">${escapeHtml(r.workflowId || '')}</span></td>
                <td>${escapeHtml(r.workflowType || '')}</td>
                <td>${statusBadge(r.status)}</td>
                <td>${escapeHtml(r.correlationId || '—')}</td>
                <td>${formatTimestamp(r.startTime)}</td>
                <td>${formatTimestamp(r.endTime)}</td>
                <td>${escapeHtml(r.version || '1')}</td>
            </tr>
        `).join('');
    }

    async function runSearch() {
        const btn = document.getElementById('search-btn');
        if (btn) { btn.disabled = true; btn.textContent = 'Searching...'; }

        try {
            const workflowType = (document.getElementById('search-workflow-type') || {}).value || '';
            const statusInput = document.querySelector('input[name="search-status"]:checked');
            const status = statusInput ? statusInput.value : '';
            const freeText = (document.getElementById('search-free-text') || {}).value || '';
            const filters = gatherFilters();

            const data = await apiPost('/api/v1/search/advanced', {
                workflowType,
                status,
                freeText,
                filters,
                size: 100,
            });

            renderStatusSummary(data.statusCounts);
            renderResults(data.results || []);
        } catch (err) {
            showToast('Search failed: ' + err.message, 'error');
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = 'Search'; }
        }
    }

    async function exportCsv() {
        try {
            const workflowType = (document.getElementById('search-workflow-type') || {}).value || '';
            const statusInput = document.querySelector('input[name="search-status"]:checked');
            const status = statusInput ? statusInput.value : '';
            const filters = gatherFilters();

            const resp = await fetch('/api/v1/search/export', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ workflowType, status, filters }),
            });

            if (!resp.ok) {
                showToast('Export failed', 'error');
                return;
            }

            const blob = await resp.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'workflow_search_results.csv';
            a.click();
            URL.revokeObjectURL(url);
            showToast('CSV exported', 'success');
        } catch (err) {
            showToast('Export failed: ' + err.message, 'error');
        }
    }

    async function loadSavedSearches() {
        const list = document.getElementById('saved-searches-list');
        if (!list) return;
        try {
            const searches = await apiGet('/api/v1/search/saved');
            if (searches.length === 0) {
                list.innerHTML = '<p class="text-muted font-sm">No saved searches yet.</p>';
                return;
            }
            list.innerHTML = searches.map(s => `
                <div class="d-flex align-center gap-1 mb-1">
                    <button class="btn btn-outline btn-sm w-100 text-right"
                        onclick="loadSavedSearch(${JSON.stringify(s.searchConfig).replace(/"/g, '&quot;')})"
                        style="text-align:left">
                        <strong>${escapeHtml(s.name)}</strong>
                        <span class="text-muted"> &mdash; ${escapeHtml(s.description || '')}</span>
                    </button>
                    <button class="btn btn-danger btn-sm" onclick="deleteSavedSearch(${s.id}, this)">X</button>
                </div>
            `).join('');
        } catch (err) {
            list.innerHTML = '<p class="text-muted font-sm">Could not load saved searches.</p>';
        }
    }

    window.loadSavedSearch = function (config) {
        if (config.workflowType) {
            const sel = document.getElementById('search-workflow-type');
            if (sel) sel.value = config.workflowType;
        }
        if (config.status) {
            const radio = document.querySelector('input[name="search-status"][value="' + config.status + '"]');
            if (radio) radio.checked = true;
        }
        showToast('Saved search loaded', 'info', 2000);
        runSearch();
    };

    window.deleteSavedSearch = async function (id, btn) {
        if (!confirmAction(
            'Delete this saved search',
            'This removes the saved search from the Conductor Companion database.'
        )) return;
        try {
            await apiDelete('/api/v1/search/saved/' + id);
            showToast('Deleted', 'success', 2000);
            loadSavedSearches();
        } catch (err) {
            showToast('Delete failed: ' + err.message, 'error');
        }
    };

    async function saveCurrentSearch() {
        const name = prompt('Name for this saved search:');
        if (!name) return;
        const workflowType = (document.getElementById('search-workflow-type') || {}).value || '';
        const statusInput = document.querySelector('input[name="search-status"]:checked');
        const status = statusInput ? statusInput.value : '';
        if (!confirmAction(
            'Save search "' + name + '"',
            'This adds a saved search to the Conductor Companion database.'
        )) return;
        try {
            await apiPost('/api/v1/search/saved', {
                name,
                searchConfig: { workflowType, status },
            });
            showToast('Search saved: ' + name, 'success');
            loadSavedSearches();
        } catch (err) {
            showToast('Save failed: ' + err.message, 'error');
        }
    }

    function initSearch() {
        const searchBtn = document.getElementById('search-btn');
        if (searchBtn) searchBtn.addEventListener('click', runSearch);

        const exportBtn = document.getElementById('search-export-btn');
        if (exportBtn) exportBtn.addEventListener('click', exportCsv);

        const addFilterBtn = document.getElementById('add-filter-btn');
        if (addFilterBtn) addFilterBtn.addEventListener('click', addFilterRow);

        const saveSearchBtn = document.getElementById('save-search-btn');
        if (saveSearchBtn) saveSearchBtn.addEventListener('click', saveCurrentSearch);

        // Populate workflow dropdown
        const wfSelect = document.getElementById('search-workflow-type');
        populateWorkflowDropdown(wfSelect);

        // Load saved searches
        loadSavedSearches();
    }

    document.addEventListener('tabActivated', function (e) {
        if (e.detail.tab === 'search') {
            loadSavedSearches();
        }
    });

    document.addEventListener('DOMContentLoaded', initSearch);
})();
