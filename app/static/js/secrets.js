// Secrets Manager — Settings tab

async function loadSecrets() {
    const container = document.getElementById('secrets-list-container');
    if (!container) return;
    try {
        const data = await apiGet('/api/v1/secrets');
        renderSecretsTable(data.secrets || []);
    } catch (err) {
        container.innerHTML = `<p class="text-error">Failed to load secrets: ${escapeHtml(String(err))}</p>`;
    }
}

function renderSecretsTable(secrets) {
    const container = document.getElementById('secrets-list-container');
    if (!secrets.length) {
        container.innerHTML = '<p class="text-muted font-sm">No secrets configured.</p>';
        return;
    }
    const rows = secrets.map(name => `
        <tr>
          <td><code>${escapeHtml(name)}</code></td>
          <td>
            <button class="btn btn-outline btn-sm" onclick="showUsages('${escapeHtml(name)}')">Usages</button>
            <button class="btn btn-outline btn-sm btn-danger ml-1" onclick="deleteSecret('${escapeHtml(name)}')">Delete</button>
          </td>
        </tr>
    `).join('');
    container.innerHTML = `
        <table class="table">
          <thead><tr><th>Secret Name</th><th>Actions</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
        <div id="usages-panel" class="card mt-1" style="display:none">
          <div class="card__title" id="usages-title"></div>
          <div id="usages-content"></div>
        </div>
    `;
}

async function showUsages(name) {
    const panel = document.getElementById('usages-panel');
    const title = document.getElementById('usages-title');
    const content = document.getElementById('usages-content');
    if (!panel) return;
    panel.style.display = 'block';
    title.textContent = `Workflows referencing "${name}"`;
    content.innerHTML = '<p class="text-muted font-sm">Loading...</p>';
    try {
        const data = await apiGet(`/api/v1/secrets/${encodeURIComponent(name)}/usages`);
        if (!data.usages.length) {
            content.innerHTML = '<p class="text-muted font-sm">No workflows reference this secret.</p>';
            return;
        }
        const items = data.usages.map(u =>
            `<li><strong>${escapeHtml(u.workflowName)}</strong> v${u.version} — task <code>${escapeHtml(u.taskRef)}</code></li>`
        ).join('');
        content.innerHTML = `<ul class="font-sm">${items}</ul>`;
    } catch (err) {
        content.innerHTML = `<p class="text-error">${escapeHtml(String(err))}</p>`;
    }
}

async function deleteSecret(name) {
    if (!confirmDestructive(
        `Delete secret "${name}"`,
        'Workflows that reference this secret will fail until it is recreated.'
    )) return;
    try {
        await apiDelete(`/api/v1/secrets/${encodeURIComponent(name)}`);
        showToast(`Secret "${name}" deleted`, 'success');
        loadSecrets();
    } catch (err) {
        showToast(`Delete failed: ${err}`, 'error');
    }
}

async function handleAddSecret(e) {
    e.preventDefault();
    const name = document.getElementById('new-secret-name').value.trim();
    const value = document.getElementById('new-secret-value').value;
    if (!name) return;
    if (!confirmDestructive(
        `Save secret "${name}" to Conductor`,
        'This creates or overwrites the secret value used by live workflows.'
    )) return;
    try {
        await apiPost(`/api/v1/secrets/${encodeURIComponent(name)}`, { value });
        showToast(`Secret "${name}" saved`, 'success');
        document.getElementById('new-secret-name').value = '';
        document.getElementById('new-secret-value').value = '';
        loadSecrets();
    } catch (err) {
        showToast(`Failed to save secret: ${err}`, 'error');
    }
}

function initSettings() {
    const form = document.getElementById('add-secret-form');
    if (form) form.addEventListener('submit', handleAddSecret);
    loadSecrets();
}

document.addEventListener('tabActivated', e => {
    if (e.detail.tab === 'settings') initSettings();
});
