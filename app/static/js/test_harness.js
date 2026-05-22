/**
 * test_harness.js — Workflow Test Harness sub-tab logic (inside JQ Lab)
 */

// ---------------------------------------------------------------------------
// Sub-tab routing for JQ Lab
// ---------------------------------------------------------------------------

function initJqSubTabs() {
    var subTabs = ['jq-sandbox', 'jq-library', 'jq-test'];

    subTabs.forEach(function (name) {
        var link = document.getElementById('subtab-' + name);
        if (link) {
            link.addEventListener('click', function (e) {
                e.preventDefault();
                activateJqSubTab(name);
            });
        }
    });
}

function activateJqSubTab(name) {
    var subTabs = ['jq-sandbox', 'jq-library', 'jq-test'];
    subTabs.forEach(function (n) {
        var panel = document.getElementById('subpanel-' + n);
        var link = document.getElementById('subtab-' + n);
        if (panel) panel.style.display = n === name ? '' : 'none';
        if (link) link.classList.toggle('active', n === name);
    });

    if (name === 'jq-test') {
        loadWorkflows();
        loadPresets();
    }
    if (name === 'jq-library') {
        loadJqLibraryDuplicate();
    }
}

// Duplicate library loader for the Library sub-tab
async function loadJqLibraryDuplicate() {
    const el = document.getElementById('jq-library-list');
    if (!el) return;
    try {
        const data = await apiGet('/api/v1/jq-lab/expressions');
        const exprs = data.expressions || [];
        if (exprs.length === 0) {
            el.innerHTML = '<p class="text-muted font-sm">No saved expressions yet.</p>';
            return;
        }
        el.innerHTML = exprs.map(function (e) {
            return '<div style="border-bottom:1px solid #f0f0f0;padding:0.5rem 0">' +
                '<strong>' + escapeHtml(e.name) + '</strong>' +
                (e.description ? ' <span class="text-muted font-sm">— ' + escapeHtml(e.description) + '</span>' : '') +
                '<br><code style="font-size:0.8rem">' + escapeHtml(e.expression) + '</code>' +
                '</div>';
        }).join('');
    } catch (err) {
        el.innerHTML = '<p class="text-muted font-sm">Error loading library.</p>';
    }
}

// ---------------------------------------------------------------------------
// Workflow list
// ---------------------------------------------------------------------------

async function loadWorkflows() {
    const sel = document.getElementById('th-workflow-select');
    if (!sel) return;

    try {
        const data = await apiGet('/api/v1/test-harness/workflows');
        const workflows = data.workflows || [];
        sel.innerHTML = '<option value="">-- Select Workflow --</option>';
        workflows.forEach(function (wf) {
            var opt = document.createElement('option');
            opt.value = wf.name;
            opt.dataset.version = wf.version || 1;
            opt.textContent = wf.name + ' v' + (wf.version || 1);
            sel.appendChild(opt);
        });
    } catch (err) {
        showToast('Could not load workflows: ' + err.message, 'error');
    }
}

// ---------------------------------------------------------------------------
// Workflow tasks
// ---------------------------------------------------------------------------

async function loadTaskRefs() {
    const sel = document.getElementById('th-workflow-select');
    const versionInput = document.getElementById('th-version');
    const card = document.getElementById('th-task-refs-card');
    const list = document.getElementById('th-task-refs-list');

    const wfName = sel ? sel.value : '';
    if (!wfName) {
        showToast('Select a workflow first', 'warning');
        return;
    }

    const version = versionInput ? versionInput.value : '';
    const url = '/api/v1/test-harness/workflows/' + encodeURIComponent(wfName) + '/tasks' +
        (version ? '?version=' + encodeURIComponent(version) : '');

    try {
        const data = await apiGet(url);
        const tasks = data.tasks || [];
        if (card) card.classList.remove('d-none');
        if (list) {
            list.innerHTML = tasks.map(function (t) {
                return '<div style="font-size:0.85rem;padding:0.3rem 0;border-bottom:1px solid #f0f0f0">' +
                    '<code>' + escapeHtml(t.ref_name || '') + '</code>' +
                    ' <span class="badge badge-unknown" style="font-size:0.7rem">' + escapeHtml(t.task_type || '') + '</span>' +
                    ' <span class="text-muted">(' + escapeHtml(t.task_name || '') + ')</span>' +
                    ' <button class="btn btn-outline btn-sm" style="padding:1px 6px;font-size:0.7rem" ' +
                    'onclick="prefillMock(' + JSON.stringify(t.ref_name) + ')">Add Mock</button>' +
                    '</div>';
            }).join('');
        }
    } catch (err) {
        showToast('Error loading tasks: ' + err.message, 'error');
    }
}

function prefillMock(refName) {
    const textarea = document.getElementById('th-task-mocks');
    if (!textarea) return;

    var existing = {};
    try { existing = JSON.parse(textarea.value || '{}'); } catch (e) { existing = {}; }

    if (!existing[refName]) {
        existing[refName] = { outputData: {} };
    }
    textarea.value = JSON.stringify(existing, null, 2);
}

// ---------------------------------------------------------------------------
// Run test
// ---------------------------------------------------------------------------

async function runTest() {
    const sel = document.getElementById('th-workflow-select');
    const versionInput = document.getElementById('th-version');
    const inputTextarea = document.getElementById('th-workflow-input');
    const mocksTextarea = document.getElementById('th-task-mocks');
    const btn = document.getElementById('th-run-btn');

    const wfName = sel ? sel.value : '';
    if (!wfName) {
        showToast('Select a workflow first', 'warning');
        return;
    }

    var workflowInput = {};
    var taskMocks = {};

    try { workflowInput = JSON.parse((inputTextarea ? inputTextarea.value : '') || '{}'); }
    catch (e) { showToast('Workflow input is not valid JSON', 'error'); return; }

    try { taskMocks = JSON.parse((mocksTextarea ? mocksTextarea.value : '') || '{}'); }
    catch (e) { showToast('Task mocks is not valid JSON', 'error'); return; }

    const version = versionInput ? parseInt(versionInput.value) || undefined : undefined;

    const payload = {
        workflow_name: wfName,
        version: version,
        input: workflowInput,
        task_mocks: taskMocks,
    };

    if (!confirmAction(
        'Run a live test of workflow "' + wfName + '"',
        "This calls Conductor's workflow test endpoint. Any task reference without a mock falls through to a real worker."
    )) return;

    if (btn) { btn.disabled = true; btn.textContent = 'Running...'; }

    try {
        const result = await apiPost('/api/v1/test-harness/run', payload);
        renderTestResult(result);
        showToast('Test complete: ' + (result.status || 'UNKNOWN'), result.status === 'COMPLETED' ? 'success' : 'warning');
    } catch (err) {
        showToast('Test run error: ' + err.message, 'error');
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = 'Run Test'; }
    }
}

function renderTestResult(result) {
    const card = document.getElementById('th-result-card');
    const content = document.getElementById('th-result-content');
    if (!card || !content) return;

    card.classList.remove('d-none');

    const statusBg = result.status === 'COMPLETED' ? '#d4edda' : '#ffeef0';
    const statusColor = result.status === 'COMPLETED' ? '#155724' : '#b31d28';
    const tasks = result.tasks || [];

    var html = '<div style="background:' + statusBg + ';color:' + statusColor +
        ';padding:0.5rem 0.75rem;border-radius:4px;margin-bottom:0.75rem">' +
        '<strong>Status: ' + escapeHtml(result.status || 'UNKNOWN') + '</strong>' +
        '<span class="text-muted" style="float:right;font-size:0.8rem">ID: ' + escapeHtml(result.workflowId || '') + '</span>' +
        '</div>';

    if (tasks.length > 0) {
        html += '<div style="margin-bottom:0.5rem;font-size:0.85rem"><strong>Task Results:</strong></div>';
        html += '<div class="table-wrapper"><table class="data-table"><thead><tr>' +
            '<th>Ref Name</th><th>Type</th><th>Status</th><th>Duration</th><th>Output</th>' +
            '</tr></thead><tbody>';

        tasks.forEach(function (t) {
            var dur = (t.startTime && t.endTime) ? formatDurationMs(t.endTime - t.startTime) : '—';
            var outStr = JSON.stringify(t.outputData || {});
            if (outStr.length > 80) outStr = outStr.substring(0, 77) + '...';
            var rowBg = t.status === 'FAILED' ? 'background:#ffeef0' : '';

            html += '<tr style="' + rowBg + '">' +
                '<td><code style="font-size:0.8rem">' + escapeHtml(t.referenceTaskName || '') + '</code></td>' +
                '<td>' + escapeHtml(t.taskType || '') + '</td>' +
                '<td>' + statusBadge(t.status) + '</td>' +
                '<td>' + escapeHtml(dur) + '</td>' +
                '<td><code style="font-size:0.75rem;word-break:break-all">' + escapeHtml(outStr) + '</code></td>' +
                '</tr>';
        });

        html += '</tbody></table></div>';
    }

    if (Object.keys(result.output || {}).length > 0) {
        html += '<div style="margin-top:0.75rem"><strong>Workflow Output:</strong>' +
            '<pre class="code-block" style="max-height:120px;overflow:auto;font-size:0.8rem">' +
            escapeHtml(JSON.stringify(result.output, null, 2)) + '</pre></div>';
    }

    content.innerHTML = html;
}

// ---------------------------------------------------------------------------
// Presets
// ---------------------------------------------------------------------------

async function loadPresets() {
    const el = document.getElementById('th-presets-list');
    if (!el) return;

    try {
        const data = await apiGet('/api/v1/test-harness/presets');
        const presets = data.presets || [];
        el.innerHTML = presets.map(function (p) {
            var safePreset = JSON.stringify(p).replace(/'/g, '&#39;');
            return '<div style="border-bottom:1px solid #f0f0f0;padding:0.4rem 0">' +
                '<strong>' + escapeHtml(p.name) + '</strong>' +
                (p.workflowName ? ' <span class="badge badge-unknown" style="font-size:0.7rem">' + escapeHtml(p.workflowName) + '</span>' : '') +
                (p.builtin ? ' <span class="badge" style="background:#FF7900;color:#fff;font-size:0.7rem">built-in</span>' : '') +
                '<br>' +
                (p.description ? '<span class="text-muted font-sm">' + escapeHtml(p.description) + '</span><br>' : '') +
                '<button class="btn btn-outline btn-sm" style="margin-top:4px" ' +
                'onclick="applyPreset(' + escapeHtml(safePreset) + ')">Apply</button>' +
                '</div>';
        }).join('') || '<p class="text-muted font-sm">No presets available.</p>';
    } catch (err) {
        el.innerHTML = '<p class="text-muted font-sm">Error loading presets.</p>';
    }
}

function applyPreset(preset) {
    const sel = document.getElementById('th-workflow-select');
    const inputTA = document.getElementById('th-workflow-input');
    const mocksTA = document.getElementById('th-task-mocks');

    if (sel && preset.workflowName) {
        // Try to select the matching option
        for (var i = 0; i < sel.options.length; i++) {
            if (sel.options[i].value === preset.workflowName) {
                sel.selectedIndex = i;
                break;
            }
        }
    }
    if (inputTA) inputTA.value = JSON.stringify(preset.input || {}, null, 2);
    if (mocksTA) mocksTA.value = JSON.stringify(preset.taskMocks || {}, null, 2);
    showToast('Preset applied: ' + preset.name, 'success');
}

async function savePreset() {
    const name = prompt('Preset name:');
    if (!name) return;

    const sel = document.getElementById('th-workflow-select');
    const inputTA = document.getElementById('th-workflow-input');
    const mocksTA = document.getElementById('th-task-mocks');

    var input = {};
    var mocks = {};
    try { input = JSON.parse((inputTA ? inputTA.value : '') || '{}'); } catch (e) {}
    try { mocks = JSON.parse((mocksTA ? mocksTA.value : '') || '{}'); } catch (e) {}

    const body = {
        name: name,
        workflow_name: sel ? sel.value : '',
        input: input,
        task_mocks: mocks,
    };

    if (!confirmAction(
        'Save test preset "' + name + '"',
        'This adds a preset to the Conductor Companion database.'
    )) return;

    try {
        await apiPost('/api/v1/test-harness/presets', body);
        showToast('Preset saved: ' + name, 'success');
        await loadPresets();
    } catch (err) {
        showToast('Error saving preset: ' + err.message, 'error');
    }
}

// ---------------------------------------------------------------------------
// Initialization
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', function () {
    initJqSubTabs();

    const runBtn = document.getElementById('th-run-btn');
    if (runBtn) runBtn.addEventListener('click', runTest);

    const loadTasksBtn = document.getElementById('th-load-tasks-btn');
    if (loadTasksBtn) loadTasksBtn.addEventListener('click', loadTaskRefs);

    const savePresetBtn = document.getElementById('th-save-preset-btn');
    if (savePresetBtn) savePresetBtn.addEventListener('click', savePreset);
});
