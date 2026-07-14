/**
 * dob_repair.js — DOB Repair tab logic (PD0002124)
 *
 * Upload a PERSON export, review the HIGH/MEDIUM/REVIEW candidate queue and
 * elevated-risk worklist, record accept/reject/defer decisions, and export
 * approved corrections as CSV. Nothing here writes to Colleague — decisions
 * are stored in Conductor Companion's own database; the export is the only
 * hand-off point to a separate, sanctioned apply step.
 */

(function () {
    'use strict';

    const BUCKET_PILL = {
        HIGH: 'pill-status-error',
        MEDIUM: 'pill-status-warning',
        REVIEW: 'pill-task',
    };

    // -----------------------------------------------------------------------
    // Status + analyze
    // -----------------------------------------------------------------------

    async function dobLoadStatus() {
        try {
            const s = await apiGet('/api/v1/dob-repair/status');
            const statusEl = document.getElementById('dob-analyze-status');
            const reloadBtn = document.getElementById('dob-reload-configured-btn');

            if (statusEl) {
                statusEl.textContent = s.analyzed
                    ? 'Last analyzed: ' + formatTimestamp(s.analyzedAt) + ' — source: ' + s.source
                    : 'No analysis has been run yet.';
            }
            if (reloadBtn) reloadBtn.classList.toggle('d-none', !s.configuredInputPath);
        } catch (err) {
            // Status is informational only — fail quietly, upload still works.
        }
    }

    async function dobAnalyze(useConfiguredPath) {
        const fileInput = document.getElementById('dob-csv-file');
        const thresholdInput = document.getElementById('dob-threshold');
        const btn = document.getElementById('dob-analyze-btn');
        const statusEl = document.getElementById('dob-analyze-status');

        const file = fileInput && fileInput.files ? fileInput.files[0] : null;
        if (!file && !useConfiguredPath) {
            showToast('Choose a CSV file first', 'warning');
            return;
        }

        const form = new FormData();
        if (file && !useConfiguredPath) form.append('csv_file', file);
        form.append('threshold', (thresholdInput && thresholdInput.value) || '6');

        if (btn) { btn.disabled = true; btn.textContent = 'Analyzing...'; }
        if (statusEl) statusEl.innerHTML = '<span class="spinner"></span> Analyzing...';

        try {
            const resp = await fetch('/api/v1/dob-repair/analyze', { method: 'POST', body: form });
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.error || 'Analyze failed');

            showToast(
                'Analyzed ' + data.summary.total_records + ' records — ' +
                data.summary.high + ' HIGH, ' + data.summary.medium + ' MEDIUM, ' +
                data.summary.review + ' REVIEW',
                'success'
            );
            await dobLoadStatus();
            await dobLoadCandidates();
        } catch (err) {
            showToast('Analyze failed: ' + err.message, 'error');
            if (statusEl) statusEl.textContent = 'Analyze failed: ' + err.message;
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = 'Analyze'; }
        }
    }

    // -----------------------------------------------------------------------
    // Candidates + rendering
    // -----------------------------------------------------------------------

    async function dobLoadCandidates() {
        const tbody = document.getElementById('dob-candidates-tbody');
        try {
            const data = await apiGet('/api/v1/dob-repair/candidates');
            dobRenderSummary(data.summary);
            dobRenderCandidates(data.candidates || []);
            dobRenderElevated(data.elevatedRisk || []);
            dobRenderUnparseable(data.unparseableDob || []);
        } catch (err) {
            // 404 NOT_ANALYZED is expected before the first analysis — show
            // the placeholder state rather than an error toast.
            if (tbody && !/analysis/i.test(err.message)) {
                tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted" style="padding:2rem">' +
                    'Error loading candidates: ' + escapeHtml(err.message) + '</td></tr>';
            }
        }
    }

    function dobRenderSummary(summary) {
        const el = document.getElementById('dob-summary-tiles');
        if (!el || !summary) return;

        const tiles = [
            { label: 'Records', value: summary.total_records, cls: '' },
            { label: 'HIGH', value: summary.high, cls: 'stat-box--red' },
            { label: 'MEDIUM', value: summary.medium, cls: 'stat-box--orange' },
            { label: 'REVIEW', value: summary.review, cls: '' },
            { label: 'Elevated Risk', value: summary.elevated_risk, cls: '' },
            { label: 'Unparseable DOB', value: summary.unparseable_dob, cls: '' },
        ];

        el.innerHTML = '<div class="grid-3" style="grid-template-columns:repeat(3,1fr);gap:0.6rem">' +
            tiles.map(function (t) {
                return '<div class="stat-box ' + t.cls + '">' +
                    '<div class="stat-box__value">' + (t.value || 0) + '</div>' +
                    '<div class="stat-box__label">' + t.label + '</div>' +
                    '</div>';
            }).join('') + '</div>';
    }

    function dobDecisionBadge(decision) {
        if (!decision) return '<span class="badge badge-unknown">undecided</span>';
        const cls = decision.action === 'accept' ? 'badge-completed' :
            decision.action === 'reject' ? 'badge-failed' : 'badge-paused';
        return '<span class="badge ' + cls + '">' + escapeHtml(decision.action) + '</span>' +
            '<div class="text-muted" style="font-size:0.72rem">' +
            escapeHtml(decision.reviewer || '') + ' &middot; ' + formatTimestamp(decision.decidedAt) +
            '</div>';
    }

    function dobRenderCandidates(candidates) {
        const tbody = document.getElementById('dob-candidates-tbody');
        if (!tbody) return;

        if (!candidates || candidates.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted" style="padding:2rem">' +
                'No candidates found in this export.</td></tr>';
            return;
        }

        tbody.innerHTML = candidates.map(function (c) {
            const pillCls = BUCKET_PILL[c.bucket] || 'pill-task';
            const earlierChecked = c.suggested_true_dob && c.suggested_true_dob === c.earlier_dob ? 'checked' : '';
            const laterChecked = c.suggested_true_dob && c.suggested_true_dob === c.later_dob ? 'checked' : '';
            const radioName = 'dob-true-' + escapeHtml(c.candidate_id);

            return '<tr data-candidate-id="' + escapeHtml(c.candidate_id) + '" ' +
                'data-earlier-dob="' + escapeHtml(c.earlier_dob) + '" ' +
                'data-later-dob="' + escapeHtml(c.later_dob) + '">' +
                '<td><span class="pill ' + pillCls + '">' + escapeHtml(c.bucket) + '</span></td>' +
                '<td>' + escapeHtml(c.name) + '</td>' +
                '<td>' + escapeHtml(c.earlier_dob) + ' <span class="text-muted font-sm">(' +
                    escapeHtml(c.earlier_origin) + ')</span></td>' +
                '<td>' + escapeHtml(c.later_dob) + ' <span class="text-muted font-sm">(' +
                    escapeHtml(c.later_origin) + ')</span></td>' +
                '<td>' + c.identity_score + '</td>' +
                '<td class="font-sm" style="max-width:280px">' + escapeHtml(c.rationale) + '</td>' +
                '<td style="min-width:230px">' +
                    '<div class="mb-1">' + dobDecisionBadge(c.decision) + '</div>' +
                    '<div class="radio-group" style="flex-direction:column;align-items:flex-start;gap:0.15rem;font-size:0.78rem">' +
                        '<label><input type="radio" name="' + radioName + '" class="dob-true-radio" ' +
                            'value="' + escapeHtml(c.earlier_dob) + '" ' + earlierChecked + '/> Earlier is true</label>' +
                        '<label><input type="radio" name="' + radioName + '" class="dob-true-radio" ' +
                            'value="' + escapeHtml(c.later_dob) + '" ' + laterChecked + '/> Later is true</label>' +
                    '</div>' +
                    '<div class="d-flex gap-1 mt-1">' +
                        '<button class="btn btn-primary btn-sm dob-decide-btn" data-action="accept">Accept</button>' +
                        '<button class="btn btn-outline btn-sm dob-decide-btn" data-action="reject">Reject</button>' +
                        '<button class="btn btn-outline btn-sm dob-decide-btn" data-action="defer">Defer</button>' +
                    '</div>' +
                '</td>' +
                '</tr>';
        }).join('');
    }

    function dobRenderElevated(list) {
        const tbody = document.getElementById('dob-elevated-tbody');
        const count = document.getElementById('dob-elevated-count');
        if (count) count.textContent = list.length + ' record' + (list.length === 1 ? '' : 's');
        if (!tbody) return;

        if (!list || list.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="text-center text-muted" style="padding:1rem">None.</td></tr>';
            return;
        }
        tbody.innerHTML = list.map(function (r) {
            return '<tr>' +
                '<td>' + escapeHtml(r.personId) + '</td>' +
                '<td>' + escapeHtml(r.name) + '</td>' +
                '<td>' + escapeHtml(r.dob) + '</td>' +
                '<td>' + escapeHtml(r.state) + '</td>' +
                '</tr>';
        }).join('');
    }

    function dobRenderUnparseable(list) {
        const card = document.getElementById('dob-unparseable-card');
        const tbody = document.getElementById('dob-unparseable-tbody');
        if (!card || !tbody) return;

        if (!list || list.length === 0) {
            card.classList.add('d-none');
            return;
        }
        card.classList.remove('d-none');
        tbody.innerHTML = list.map(function (r) {
            return '<tr>' +
                '<td>' + escapeHtml(r.personId) + '</td>' +
                '<td>' + escapeHtml(r.name) + '</td>' +
                '<td>' + escapeHtml(r.rawBirthDate) + '</td>' +
                '</tr>';
        }).join('');
    }

    // -----------------------------------------------------------------------
    // Decisions
    // -----------------------------------------------------------------------

    async function dobDecide(row, action) {
        const candidateId = row.dataset.candidateId;
        let trueDob = '';

        if (action === 'accept') {
            const checked = row.querySelector('.dob-true-radio:checked');
            if (!checked) {
                showToast('Pick which date is true before accepting', 'warning');
                return;
            }
            trueDob = checked.value;
            if (!confirmAction(
                'Accept correction for candidate ' + candidateId,
                'This marks a specific person record as needing its DOB corrected ' +
                'to ' + trueDob + ' and adds it to the corrections export. It does ' +
                'not write to Colleague by itself.'
            )) return;
        }

        try {
            await apiPost('/api/v1/dob-repair/decision', {
                candidate_id: candidateId,
                action: action,
                true_dob: trueDob,
                reviewer: (window.ConductorEnv && window.ConductorEnv.reviewer) || 'user',
            });
            showToast('Decision recorded: ' + action, 'success');
            await dobLoadCandidates();
        } catch (err) {
            showToast('Decision failed: ' + err.message, 'error');
        }
    }

    // -----------------------------------------------------------------------
    // Export
    // -----------------------------------------------------------------------

    async function dobExportCorrections() {
        try {
            const resp = await fetch('/api/v1/dob-repair/export/corrections');
            if (!resp.ok) {
                showToast('Export failed', 'error');
                return;
            }
            const blob = await resp.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'dob_corrections.csv';
            a.click();
            URL.revokeObjectURL(url);
            showToast('Exported corrections CSV', 'success');
        } catch (err) {
            showToast('Export failed: ' + err.message, 'error');
        }
    }

    // -----------------------------------------------------------------------
    // Initialization
    // -----------------------------------------------------------------------

    document.addEventListener('tabActivated', function (e) {
        if (e.detail.tab === 'dob-repair') {
            dobLoadStatus();
            dobLoadCandidates();
        }
    });

    document.addEventListener('DOMContentLoaded', function () {
        const analyzeBtn = document.getElementById('dob-analyze-btn');
        if (analyzeBtn) analyzeBtn.addEventListener('click', function () { dobAnalyze(false); });

        const reloadBtn = document.getElementById('dob-reload-configured-btn');
        if (reloadBtn) reloadBtn.addEventListener('click', function () { dobAnalyze(true); });

        const exportBtn = document.getElementById('dob-export-btn');
        if (exportBtn) exportBtn.addEventListener('click', dobExportCorrections);

        const elevatedToggle = document.getElementById('dob-elevated-toggle-btn');
        if (elevatedToggle) {
            elevatedToggle.addEventListener('click', function () {
                const content = document.getElementById('dob-elevated-content');
                if (!content) return;
                const nowHidden = content.classList.toggle('d-none');
                elevatedToggle.textContent = nowHidden ? 'Show' : 'Hide';
            });
        }

        const tbody = document.getElementById('dob-candidates-tbody');
        if (tbody) {
            tbody.addEventListener('click', function (e) {
                const btn = e.target.closest('.dob-decide-btn');
                if (!btn) return;
                const row = btn.closest('tr[data-candidate-id]');
                if (!row) return;
                dobDecide(row, btn.dataset.action);
            });
        }
    });
})();
