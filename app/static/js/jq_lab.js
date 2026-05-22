/**
 * jq_lab.js — JQ Lab tab logic
 */

(function () {
    'use strict';

    async function evaluateJq() {
        const btn = document.getElementById('jq-evaluate-btn');
        const inputEl = document.getElementById('jq-input');
        const exprEl = document.getElementById('jq-expression');
        const resultEl = document.getElementById('jq-result');
        const errorEl = document.getElementById('jq-error');

        if (!inputEl || !exprEl) return;

        const input = inputEl.value.trim();
        const expression = exprEl.value.trim();

        if (!expression) {
            showToast('Enter a jq expression', 'warning');
            return;
        }

        let inputData;
        try {
            inputData = input ? JSON.parse(input) : {};
        } catch (e) {
            showToast('Input JSON is invalid: ' + e.message, 'error');
            return;
        }

        if (btn) { btn.disabled = true; btn.textContent = 'Evaluating...'; }
        if (errorEl) errorEl.classList.add('d-none');
        if (resultEl) resultEl.textContent = '';

        try {
            const data = await apiPost('/api/v1/jq/evaluate', { expression, input: inputData });

            if (data.error) {
                if (errorEl) {
                    errorEl.textContent = 'jq error: ' + data.error;
                    errorEl.classList.remove('d-none');
                }
            } else {
                if (resultEl) {
                    resultEl.textContent = JSON.stringify(data.result, null, 2);
                }
                showToast('Expression evaluated', 'success', 2000);
            }
        } catch (err) {
            showToast('Evaluation failed: ' + err.message, 'error');
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = 'Evaluate'; }
        }
    }

    async function loadFromExecution() {
        const wfIdEl = document.getElementById('jq-execution-id');
        const taskRefEl = document.getElementById('jq-task-ref');
        const inputEl = document.getElementById('jq-input');

        const workflowId = (wfIdEl || {}).value || '';
        const taskRef = (taskRefEl || {}).value || '';

        if (!workflowId) {
            showToast('Enter a workflow execution ID', 'warning');
            return;
        }

        try {
            const params = new URLSearchParams({ workflowId });
            if (taskRef) params.set('taskRef', taskRef);
            const data = await apiGet('/api/v1/jq/load-from-execution?' + params.toString());

            if (!data.found) {
                showToast('No task output found for that execution', 'warning');
                return;
            }

            if (inputEl) {
                inputEl.value = JSON.stringify(data.data, null, 2);
            }
            showToast('Loaded output from ' + (data.taskType || 'task'), 'success', 2000);
        } catch (err) {
            showToast('Load failed: ' + err.message, 'error');
        }
    }

    async function copyAsConductorTask() {
        const exprEl = document.getElementById('jq-expression');
        const expression = (exprEl || {}).value || '';
        if (!expression) {
            showToast('Enter a jq expression first', 'warning');
            return;
        }

        try {
            const data = await apiPost('/api/v1/jq/format-as-conductor-task', { expression });
            copyToClipboard(data.json);
        } catch (err) {
            showToast('Format failed: ' + err.message, 'error');
        }
    }

    async function saveToLibrary() {
        const exprEl = document.getElementById('jq-expression');
        const expression = (exprEl || {}).value || '';
        if (!expression) {
            showToast('Enter a jq expression first', 'warning');
            return;
        }

        const name = prompt('Name for this expression:');
        if (!name) return;
        const description = prompt('Description (optional):') || '';

        if (!confirmAction(
            'Save JQ expression "' + name + '"',
            'This adds an expression to the Conductor Companion database.'
        )) return;

        try {
            await apiPost('/api/v1/jq/expressions', { name, description, expression });
            showToast('Saved to library: ' + name, 'success');
            loadExpressionLibrary();
        } catch (err) {
            showToast('Save failed: ' + err.message, 'error');
        }
    }

    async function loadExpressionLibrary() {
        const listEl = document.getElementById('jq-expression-library');
        if (!listEl) return;

        try {
            const expressions = await apiGet('/api/v1/jq/expressions');

            if (expressions.length === 0) {
                listEl.innerHTML = '<p class="text-muted font-sm">No saved expressions yet.</p>';
                return;
            }

            listEl.innerHTML = expressions.map(e => `
                <div class="card" style="padding:0.75rem;margin-bottom:0.5rem">
                    <div class="d-flex align-center gap-1">
                        <div style="flex:1">
                            <strong>${escapeHtml(e.name)}</strong>
                            ${e.description ? '<br><span class="text-muted font-sm">' + escapeHtml(e.description) + '</span>' : ''}
                            ${e.tags ? '<br><span class="badge badge-orange font-sm">' + escapeHtml(e.tags) + '</span>' : ''}
                        </div>
                        <button class="btn btn-outline btn-sm" onclick="openExpressionInLab(${escapeHtml(JSON.stringify(e.expression))})">Open in Lab</button>
                    </div>
                    <div class="code-block mt-1" style="max-height:60px;overflow:hidden;font-size:0.75rem">${escapeHtml(e.expression)}</div>
                </div>
            `).join('');
        } catch (err) {
            listEl.innerHTML = '<p class="text-muted font-sm">Could not load expressions.</p>';
        }
    }

    window.openExpressionInLab = function (expression) {
        const exprEl = document.getElementById('jq-expression');
        if (exprEl) {
            exprEl.value = expression;
            showToast('Expression loaded into lab', 'info', 2000);
        }
    };

    function initJqLab() {
        const evalBtn = document.getElementById('jq-evaluate-btn');
        if (evalBtn) evalBtn.addEventListener('click', evaluateJq);

        const loadBtn = document.getElementById('jq-load-btn');
        if (loadBtn) loadBtn.addEventListener('click', loadFromExecution);

        const copyBtn = document.getElementById('jq-copy-conductor-btn');
        if (copyBtn) copyBtn.addEventListener('click', copyAsConductorTask);

        const saveBtn = document.getElementById('jq-save-btn');
        if (saveBtn) saveBtn.addEventListener('click', saveToLibrary);

        loadExpressionLibrary();
    }

    document.addEventListener('tabActivated', function (e) {
        if (e.detail.tab === 'jq-lab') {
            loadExpressionLibrary();
        }
    });

    document.addEventListener('DOMContentLoaded', initJqLab);
})();
