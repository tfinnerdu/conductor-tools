/**
 * diff.js — Diff tab logic
 */

(function () {
    'use strict';

    let currentVersions = {};

    async function loadDiffWorkflows() {
        const nameSelect = document.getElementById('diff-workflow-name');
        if (!nameSelect) return;

        try {
            const workflows = await apiGet('/api/v1/diff/workflows');
            nameSelect.innerHTML = '<option value="">-- Select Workflow --</option>';
            workflows.forEach(wf => {
                const opt = document.createElement('option');
                opt.value = wf.name;
                opt.textContent = wf.name + ' (' + (wf.versions || []).join(', ') + ')';
                opt.dataset.versions = JSON.stringify(wf.versions || []);
                nameSelect.appendChild(opt);
            });
            currentVersions = {};
        } catch (err) {
            showToast('Could not load workflows: ' + err.message, 'error');
        }
    }

    function onWorkflowSelected() {
        const nameSelect = document.getElementById('diff-workflow-name');
        const versionASelect = document.getElementById('diff-version-a');
        const versionBSelect = document.getElementById('diff-version-b');

        if (!nameSelect || !versionASelect || !versionBSelect) return;

        const selected = nameSelect.options[nameSelect.selectedIndex];
        if (!selected || !selected.value) return;

        let versions = [];
        try {
            versions = JSON.parse(selected.dataset.versions || '[]');
        } catch (e) {
            versions = [];
        }

        versionASelect.innerHTML = versions.map(v => `<option value="${v}">v${v}</option>`).join('');
        versionBSelect.innerHTML = versions.map(v => `<option value="${v}">v${v}</option>`).join('');

        // Default: version A = lowest, version B = highest
        if (versions.length >= 2) {
            versions.sort((a, b) => a - b);
            versionASelect.value = versions[0];
            versionBSelect.value = versions[versions.length - 1];
        }
    }

    async function runDiff() {
        const workflowName = (document.getElementById('diff-workflow-name') || {}).value || '';
        const versionA = (document.getElementById('diff-version-a') || {}).value;
        const versionB = (document.getElementById('diff-version-b') || {}).value;
        const mode = (document.querySelector('input[name="diff-mode"]:checked') || { value: 'full' }).value;
        const resultEl = document.getElementById('diff-result');

        if (!workflowName) {
            showToast('Select a workflow', 'warning');
            return;
        }
        if (versionA === versionB) {
            showToast('Select different versions to compare', 'warning');
            return;
        }

        const btn = document.getElementById('diff-run-btn');
        if (btn) { btn.disabled = true; btn.textContent = 'Diffing...'; }
        if (resultEl) resultEl.innerHTML = '<span class="spinner"></span> Computing diff...';

        try {
            const data = await apiPost('/api/v1/diff/workflow', {
                workflowName,
                versionA: parseInt(versionA, 10),
                versionB: parseInt(versionB, 10),
                mode,
            });

            const summaryEl = document.getElementById('diff-summary');
            if (summaryEl) {
                summaryEl.innerHTML = `
                    <span class="badge badge-completed">+${data.summary.addedLines} lines</span>
                    <span class="badge badge-failed">-${data.summary.removedLines} lines</span>
                    <span class="text-muted font-sm">${data.diffLines.length} diff lines total</span>
                `;
            }

            if (resultEl) {
                if (data.diffLines.length === 0) {
                    resultEl.innerHTML = '<p class="text-muted text-center" style="padding:2rem">No differences found between v' + versionA + ' and v' + versionB + '.</p>';
                } else {
                    resultEl.innerHTML = '<div class="diff-container">' +
                        data.diffLines.map(line =>
                            '<div class="diff-line ' + escapeHtml(line.type) + '">' + escapeHtml(line.line) + '</div>'
                        ).join('') +
                        '</div>';
                }
            }
        } catch (err) {
            if (resultEl) resultEl.innerHTML = '';
            showToast('Diff failed: ' + err.message, 'error');
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = 'Compare'; }
        }
    }

    function renderDependencyTree(nodes) {
        // nodes is [{workflowName, version, taskTypes}]
        // Group by workflowName, collect all task types across versions
        if (!nodes.length) return '<p class="text-muted">No workflows found.</p>';

        const byName = {};
        nodes.forEach(n => {
            const name = n.workflowName;
            if (!byName[name]) byName[name] = { taskTypes: new Set(), versions: [] };
            byName[name].versions.push(n.version);
            (n.taskTypes || []).forEach(t => byName[name].taskTypes.add(t));
        });

        const names = Object.keys(byName).sort();
        const rows = names.map(name => {
            const node = byName[name];
            const tasks = Array.from(node.taskTypes).sort();
            const versions = node.versions.sort((a, b) => a - b);
            const hasChildren = tasks.length > 0;
            const taskPills = tasks.map(t =>
                `<span class="pill pill-task">${escapeHtml(t)}</span>`
            ).join('');
            const subRows = tasks.map(t =>
                `<div class="dep-child"><span class="dep-arrow">&#8627;</span> <span class="dep-name">${escapeHtml(t)}</span></div>`
            ).join('');
            const versionLabel = versions.map(v => 'v' + v).join(', ');

            return `
                <div class="dep-row ${hasChildren ? 'dep-expandable' : ''}" data-name="${escapeHtml(name)}">
                  <div class="dep-header" ${hasChildren ? 'onclick="this.parentElement.classList.toggle(\'open\')"' : ''}>
                    <span class="dep-toggle">${hasChildren ? '&#9654;' : ' '}</span>
                    <span class="dep-name">${escapeHtml(name)}</span>
                    <span class="text-muted font-sm" style="margin-left:0.5rem">(${escapeHtml(versionLabel)})</span>
                    <span class="dep-tasks">${taskPills}</span>
                  </div>
                  ${hasChildren ? `<div class="dep-children">${subRows}</div>` : ''}
                </div>
            `;
        }).join('');

        return `<div class="dep-tree">${rows}</div>`;
    }

    async function loadDependencyMap() {
        const el = document.getElementById('dependency-map-content');
        if (!el) return;

        el.innerHTML = '<span class="spinner"></span> Loading dependency map...';

        try {
            const data = await apiGet('/api/v1/diff/dependency-map');
            const nodes = data.nodes || [];

            if (nodes.length === 0) {
                el.innerHTML = '<p class="text-muted">No workflows found.</p>';
                return;
            }

            el.innerHTML = `<p class="text-muted font-sm mb-1">${nodes.length} workflow versions indexed</p>` +
                renderDependencyTree(nodes);
        } catch (err) {
            el.innerHTML = '<p class="text-muted">Could not load dependency map.</p>';
            showToast('Dependency map failed: ' + err.message, 'error');
        }
    }

    async function runImpactAnalysis() {
        const taskTypeEl = document.getElementById('impact-task-type');
        const taskType = (taskTypeEl || {}).value || '';

        if (!taskType) {
            showToast('Enter a task type name', 'warning');
            return;
        }

        const btn = document.getElementById('impact-run-btn');
        const resultEl = document.getElementById('impact-result');

        if (btn) { btn.disabled = true; btn.textContent = 'Analyzing...'; }
        if (resultEl) resultEl.innerHTML = '<span class="spinner"></span>';

        try {
            const data = await apiPost('/api/v1/diff/impact', { taskType });

            if (resultEl) {
                if (data.impactedCount === 0) {
                    resultEl.innerHTML = '<p class="text-muted">No workflows reference task type <strong>' + escapeHtml(taskType) + '</strong>.</p>';
                } else {
                    resultEl.innerHTML = `
                        <p class="font-sm"><strong>${data.impactedCount}</strong> workflow(s) use <strong>${escapeHtml(taskType)}</strong></p>
                        <table class="data-table">
                            <thead>
                                <tr><th>Workflow</th><th>Version</th><th>Task References</th></tr>
                            </thead>
                            <tbody>
                                ${data.impactedWorkflows.map(w => `
                                    <tr>
                                        <td>${escapeHtml(w.workflowName)}</td>
                                        <td>v${w.version}</td>
                                        <td>${w.taskReferences.join(', ')}</td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    `;
                }
            }
        } catch (err) {
            if (resultEl) resultEl.innerHTML = '';
            showToast('Impact analysis failed: ' + err.message, 'error');
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = 'Analyze Impact'; }
        }
    }

    function initDiff() {
        const nameSelect = document.getElementById('diff-workflow-name');
        if (nameSelect) nameSelect.addEventListener('change', onWorkflowSelected);

        const runBtn = document.getElementById('diff-run-btn');
        if (runBtn) runBtn.addEventListener('click', runDiff);

        const depMapBtn = document.getElementById('dependency-map-btn');
        if (depMapBtn) depMapBtn.addEventListener('click', loadDependencyMap);

        const impactBtn = document.getElementById('impact-run-btn');
        if (impactBtn) impactBtn.addEventListener('click', runImpactAnalysis);

        loadDiffWorkflows();
    }

    document.addEventListener('tabActivated', function (e) {
        if (e.detail.tab === 'diff') {
            loadDiffWorkflows();
        }
    });

    document.addEventListener('DOMContentLoaded', initDiff);
})();
