/**
 * Security Tab – Targets, Scan-Runs, Findings.
 *
 * WICHTIG: loadModules() in app.js rendert tab.html ueber
 * DOMPurify.sanitize(html, { FORBID_ATTR: ['onclick', 'onchange', ...] }) —
 * Inline-Event-Attribute werden entfernt. Alle Interaktionen laufen daher
 * ueber Event-Delegation auf data-sec-action/data-sec-change Attribute,
 * nicht ueber onclick="..." Strings.
 */
(function () {
    const SEVERITY_COLORS = {
        critical: '#c0392b', high: '#e05252', medium: '#e0a52b',
        low: '#4a9eff', info: 'var(--text-muted)',
    };
    const SEVERITY_LABELS = { critical: 'Critical', high: 'High', medium: 'Medium', low: 'Low', info: 'Info' };
    const ORDERED_SEVERITIES = ['critical', 'high', 'medium', 'low', 'info'];
    const FINDING_STATUS_OPTIONS = [
        'acknowledged', 'in_progress', 'mitigated', 'resolved', 'false_positive', 'risk_accepted', 'reopened',
    ];

    const SecurityTab = {
        API_PREFIX: '/api/security',
        _activeSubTab: 'overview',
        _bound: false,

        init() {
            this._bindEvents();
            this.switchSubTab('overview');
        },

        destroy() {},

        // ── Event-Delegation ───────────────────────────────────────

        _bindEvents() {
            const container = document.getElementById('security-tab-content');
            if (!container || this._bound) return;
            this._bound = true;

            container.addEventListener('click', (e) => {
                const el = e.target.closest('[data-sec-action]');
                if (!el || !container.contains(el)) return;
                const action = el.dataset.secAction;
                if (typeof this[action] !== 'function') return;
                const arg = el.dataset.secArg;
                const arg2raw = el.dataset.secArg2;
                const arg2 = arg2raw === 'true' ? true : arg2raw === 'false' ? false : arg2raw;
                if (arg2raw !== undefined) this[action](arg, arg2);
                else if (arg !== undefined) this[action](arg);
                else this[action]();
            });

            container.addEventListener('change', (e) => {
                const el = e.target.closest('[data-sec-change]');
                if (!el) return;
                const action = el.dataset.secChange;
                if (typeof this[action] === 'function') this[action]();
            });
        },

        // ── Helpers ────────────────────────────────────────────────

        _esc(value) {
            const div = document.createElement('div');
            div.textContent = value === null || value === undefined ? '' : String(value);
            return div.innerHTML;
        },

        async _fetchJson(path, options) {
            const res = await fetch(`${this.API_PREFIX}${path}`, options);
            let body = null;
            try { body = await res.json(); } catch { body = null; }
            if (!res.ok) {
                const detail = body && body.detail ? body.detail : res.statusText;
                throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
            }
            return body;
        },

        _fmtTime(value) {
            if (!value && value !== 0) return '–';
            try {
                const ms = value > 1e12 ? value : value * 1000;
                return new Date(ms).toLocaleString();
            } catch { return String(value); }
        },

        _severityBadge(sev) {
            const color = SEVERITY_COLORS[sev] || 'var(--text-muted)';
            const label = SEVERITY_LABELS[sev] || sev;
            return `<span style="display:inline-block; padding:0.1rem 0.5rem; border-radius:99px; font-size:0.72rem; font-weight:600; color:#fff; background:${color};">${this._esc(label)}</span>`;
        },

        _statusBadge(status) {
            const colors = {
                completed: '#2ecc71', partially_completed: '#e0a52b', failed: '#e05252',
                waiting_for_approval: '#e0a52b', running: '#4a9eff', queued: 'var(--text-muted)',
                cancelled: 'var(--text-muted)', timed_out: '#e05252', policy_blocked: '#e05252',
            };
            const color = colors[status] || 'var(--text-muted)';
            return `<span style="color:${color}; font-weight:600;">${this._esc(status)}</span>`;
        },

        // ── Sub-Tab Switching ──────────────────────────────────────

        switchSubTab(tabId) {
            this._activeSubTab = tabId;
            ['overview', 'targets', 'runs', 'findings'].forEach((id) => {
                const panel = document.getElementById(`sec-panel-${id}`);
                const btn = document.getElementById(`sec-subtab-${id}`);
                if (panel) panel.style.display = id === tabId ? '' : 'none';
                if (btn) {
                    const isActive = id === tabId;
                    btn.className = isActive ? 'btn btn-sm btn-action' : 'btn btn-sm';
                    btn.style.cssText = isActive ? '' : 'border:1px solid var(--border-color); background:var(--bg-card); color:var(--text-color);';
                }
            });
            if (tabId === 'overview') this.loadOverview();
            else if (tabId === 'targets') this.loadTargets();
            else if (tabId === 'runs') this.loadRuns();
            else if (tabId === 'findings') this.loadFindings();
        },

        refreshAll() {
            this.switchSubTab(this._activeSubTab);
        },

        // ── Overview ───────────────────────────────────────────────

        async loadOverview() {
            const cardsEl = document.getElementById('sec-severity-cards');
            const runsEl = document.getElementById('sec-recent-runs');
            if (cardsEl) cardsEl.textContent = 'Lädt…';
            try {
                const findings = await this._fetchJson('/findings?limit=1000');
                const counts = {};
                ORDERED_SEVERITIES.forEach((s) => { counts[s] = 0; });
                findings
                    .filter((f) => !['resolved', 'false_positive', 'risk_accepted'].includes(f.status))
                    .forEach((f) => { counts[f.severity] = (counts[f.severity] || 0) + 1; });

                if (cardsEl) {
                    cardsEl.innerHTML = ORDERED_SEVERITIES.map((sev) => `
                        <div style="background:var(--bg-card); border:1px solid var(--border-color); border-radius:6px; padding:0.75rem; text-align:center;">
                            <div style="font-size:1.6rem; font-weight:700; color:${SEVERITY_COLORS[sev]};">${counts[sev]}</div>
                            <div style="font-size:0.75rem; color:var(--text-muted); margin-top:0.25rem;">${SEVERITY_LABELS[sev]}</div>
                        </div>
                    `).join('');
                }

                const runs = await this._fetchJson('/runs?limit=10');
                if (runsEl) {
                    runsEl.innerHTML = runs.length
                        ? this._runsTable(runs)
                        : '<p class="empty-state">Noch keine Scan-Runs.</p>';
                }
            } catch (err) {
                if (cardsEl) cardsEl.innerHTML = `<p class="empty-state">Fehler: ${this._esc(err.message)}</p>`;
            }
        },

        // ── Targets ────────────────────────────────────────────────

        toggleTargetForm() {
            const form = document.getElementById('sec-target-form');
            if (!form) return;
            form.style.display = form.style.display === 'none' ? '' : 'none';
        },

        async createTarget() {
            const name = document.getElementById('sec-target-name')?.value.trim();
            const target_type = document.getElementById('sec-target-type')?.value;
            const locator = document.getElementById('sec-target-locator')?.value.trim();
            const environment = document.getElementById('sec-target-environment')?.value.trim() || 'production';
            const errEl = document.getElementById('sec-target-form-error');
            if (errEl) errEl.style.display = 'none';

            if (!name || !locator) {
                if (errEl) { errEl.textContent = 'Name und Locator sind erforderlich.'; errEl.style.display = ''; }
                return;
            }
            try {
                await this._fetchJson('/targets', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name, target_type, locator, environment }),
                });
                document.getElementById('sec-target-name').value = '';
                document.getElementById('sec-target-locator').value = '';
                this.toggleTargetForm();
                this.loadTargets();
            } catch (err) {
                if (errEl) { errEl.textContent = err.message; errEl.style.display = ''; }
            }
        },

        async deleteTarget(targetId) {
            try {
                await this._fetchJson(`/targets/${encodeURIComponent(targetId)}`, { method: 'DELETE' });
                this.loadTargets();
            } catch (err) {
                alert(`Löschen fehlgeschlagen: ${err.message}`);
            }
        },

        async loadTargets() {
            const el = document.getElementById('sec-targets-table');
            if (!el) return;
            el.textContent = 'Lädt…';
            try {
                const targets = await this._fetchJson('/targets');
                if (!targets.length) {
                    el.innerHTML = '<p class="empty-state">Noch keine Security-Targets angelegt.</p>';
                    return;
                }
                const rows = targets.map((t) => `
                    <tr>
                        <td>${this._esc(t.name)}</td>
                        <td>${this._esc(t.target_type)}</td>
                        <td style="max-width:280px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${this._esc(t.locator)}</td>
                        <td>${this._esc(t.environment)}</td>
                        <td>${t.enabled ? '✅' : '❌'}</td>
                        <td>
                            <button class="btn btn-sm btn-action" data-sec-action="startScanFor" data-sec-arg="${this._esc(t.id)}">Scan starten</button>
                            <button class="btn btn-sm" data-sec-action="deleteTarget" data-sec-arg="${this._esc(t.id)}" style="border:1px solid var(--border-color); background:var(--bg-card); color:#e05252;">Löschen</button>
                        </td>
                    </tr>
                `).join('');
                el.innerHTML = `
                    <table class="data-table" style="width:100%; border-collapse:collapse;">
                        <thead><tr><th>Name</th><th>Typ</th><th>Locator</th><th>Environment</th><th>Aktiv</th><th>Aktionen</th></tr></thead>
                        <tbody>${rows}</tbody>
                    </table>
                `;
            } catch (err) {
                el.innerHTML = `<p class="empty-state">Fehler: ${this._esc(err.message)}</p>`;
            }
        },

        startScanFor(targetId) {
            // Öffnet den Chat mit vorausgefülltem Prompt statt einer eigenen Scanner-Auswahl-UI —
            // der Security Orchestrator Agent löst Scanner/Profil-Auswahl selbst auf.
            if (typeof Ninko !== 'undefined' && typeof Ninko.setForcedModule === 'function') {
                Ninko.setForcedModule('security', 'Security');
            }
            if (typeof Ninko !== 'undefined' && typeof Ninko.switchTab === 'function') {
                Ninko.switchTab('chat');
            }
            const input = document.getElementById('chat-input');
            if (input) {
                input.value = `Starte einen passiven Security-Scan für Target ${targetId}.`;
                input.focus();
            }
        },

        // ── Scan Runs ──────────────────────────────────────────────

        _runsTable(runs) {
            const rows = runs.map((r) => `
                <tr style="cursor:pointer;" data-sec-action="showRunDetail" data-sec-arg="${this._esc(r.id)}">
                    <td>${this._esc(r.scanner_id)}</td>
                    <td>${this._esc(r.profile_id)}</td>
                    <td>${this._statusBadge(r.status)}</td>
                    <td>${r.finding_count}</td>
                    <td>${this._fmtTime(r.created_at)}</td>
                </tr>
            `).join('');
            return `
                <table class="data-table" style="width:100%; border-collapse:collapse;">
                    <thead><tr><th>Scanner</th><th>Profil</th><th>Status</th><th>Findings</th><th>Erstellt</th></tr></thead>
                    <tbody>${rows}</tbody>
                </table>
            `;
        },

        async loadRuns() {
            const el = document.getElementById('sec-runs-table');
            if (!el) return;
            el.textContent = 'Lädt…';
            try {
                const runs = await this._fetchJson('/runs?limit=100');
                el.innerHTML = runs.length ? this._runsTable(runs) : '<p class="empty-state">Noch keine Scan-Runs.</p>';
            } catch (err) {
                el.innerHTML = `<p class="empty-state">Fehler: ${this._esc(err.message)}</p>`;
            }
        },

        async showRunDetail(runId) {
            const el = document.getElementById('sec-run-detail');
            if (!el) return;
            el.style.display = '';
            el.textContent = 'Lädt…';
            try {
                const run = await this._fetchJson(`/runs/${encodeURIComponent(runId)}`);
                const approveBtns = run.status === 'waiting_for_approval' ? `
                    <button class="btn btn-sm btn-action" data-sec-action="decideRun" data-sec-arg="${this._esc(runId)}" data-sec-arg2="true">✅ Freigeben</button>
                    <button class="btn btn-sm" data-sec-action="decideRun" data-sec-arg="${this._esc(runId)}" data-sec-arg2="false" style="border:1px solid var(--border-color); background:var(--bg-card); color:#e05252;">❌ Ablehnen</button>
                ` : '';
                const cancelBtn = ['queued', 'waiting_for_approval'].includes(run.status) ? `
                    <button class="btn btn-sm" data-sec-action="cancelRun" data-sec-arg="${this._esc(runId)}" style="border:1px solid var(--border-color); background:var(--bg-card); color:var(--text-color);">Abbrechen</button>
                ` : '';
                el.innerHTML = `
                    <h4 style="margin-top:0;">Run ${this._esc(run.id)}</h4>
                    <p><strong>Scanner:</strong> ${this._esc(run.scanner_id)} · <strong>Profil:</strong> ${this._esc(run.profile_id)} · <strong>Status:</strong> ${this._statusBadge(run.status)}</p>
                    <p><strong>Findings:</strong> ${run.finding_count} · <strong>Erstellt:</strong> ${this._fmtTime(run.created_at)}</p>
                    ${run.error ? `<p style="color:#e05252;"><strong>Fehler:</strong> ${this._esc(run.error)}</p>` : ''}
                    <div style="display:flex; gap:0.5rem; margin-top:0.75rem;">${approveBtns}${cancelBtn}</div>
                `;
            } catch (err) {
                el.innerHTML = `<p class="empty-state">Fehler: ${this._esc(err.message)}</p>`;
            }
        },

        async decideRun(runId, approved) {
            try {
                await this._fetchJson(`/runs/${encodeURIComponent(runId)}/approve`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ approved }),
                });
                this.showRunDetail(runId);
                this.loadRuns();
            } catch (err) {
                alert(`Aktion fehlgeschlagen: ${err.message}`);
            }
        },

        async cancelRun(runId) {
            try {
                await this._fetchJson(`/runs/${encodeURIComponent(runId)}/cancel`, { method: 'POST' });
                this.showRunDetail(runId);
                this.loadRuns();
            } catch (err) {
                alert(`Abbrechen fehlgeschlagen: ${err.message}`);
            }
        },

        // ── Findings ───────────────────────────────────────────────

        async loadFindings() {
            const el = document.getElementById('sec-findings-table');
            if (!el) return;
            el.textContent = 'Lädt…';
            const severity = document.getElementById('sec-findings-severity-filter')?.value || '';
            const status = document.getElementById('sec-findings-status-filter')?.value || '';
            const params = new URLSearchParams();
            if (severity) params.set('severity', severity);
            if (status) params.set('status', status);
            params.set('limit', '200');
            try {
                const findings = await this._fetchJson(`/findings?${params.toString()}`);
                if (!findings.length) {
                    el.innerHTML = '<p class="empty-state">Keine Findings für diese Filter.</p>';
                    return;
                }
                const rows = findings.map((f) => `
                    <tr style="cursor:pointer;" data-sec-action="showFindingDetail" data-sec-arg="${this._esc(f.id)}">
                        <td>${this._severityBadge(f.severity)}</td>
                        <td>${this._esc(f.title)}</td>
                        <td>${this._esc(f.cve || '–')}</td>
                        <td>${this._esc(f.resource_identifier || '–')}</td>
                        <td>${this._esc(f.status)}</td>
                        <td>${f.occurrence_count}</td>
                    </tr>
                `).join('');
                el.innerHTML = `
                    <table class="data-table" style="width:100%; border-collapse:collapse;">
                        <thead><tr><th>Severity</th><th>Titel</th><th>CVE</th><th>Resource</th><th>Status</th><th>Häufigkeit</th></tr></thead>
                        <tbody>${rows}</tbody>
                    </table>
                `;
            } catch (err) {
                el.innerHTML = `<p class="empty-state">Fehler: ${this._esc(err.message)}</p>`;
            }
        },

        async showFindingDetail(findingId) {
            const el = document.getElementById('sec-finding-detail');
            if (!el) return;
            el.style.display = '';
            el.textContent = 'Lädt…';
            try {
                const f = await this._fetchJson(`/findings/${encodeURIComponent(findingId)}`);
                const buttons = FINDING_STATUS_OPTIONS.map((s) => `
                    <button class="btn btn-sm" data-sec-action="setFindingStatus" data-sec-arg="${this._esc(findingId)}" data-sec-arg2="${s}" style="border:1px solid var(--border-color); background:var(--bg-card); color:var(--text-color);">${this._esc(s)}</button>
                `).join('');
                el.innerHTML = `
                    <h4 style="margin-top:0;">${this._esc(f.title)}</h4>
                    <p>${this._severityBadge(f.severity)} <span style="color:var(--text-muted); font-size:0.8rem;">(ursprünglich: ${this._esc(f.original_severity)})</span></p>
                    <p>${this._esc(f.description || 'Keine Beschreibung.')}</p>
                    <p><strong>Resource:</strong> ${this._esc(f.resource_identifier || '–')} · <strong>Ort:</strong> ${this._esc(f.location || '–')}</p>
                    ${f.cve ? `<p><strong>CVE:</strong> ${this._esc(f.cve)}</p>` : ''}
                    ${f.remediation ? `<p><strong>Remediation:</strong> ${this._esc(f.remediation)}</p>` : ''}
                    <p><strong>Status:</strong> ${this._esc(f.status)} · <strong>Häufigkeit:</strong> ${f.occurrence_count} · <strong>Zuletzt gesehen:</strong> ${this._fmtTime(f.last_seen_at)}</p>
                    <div style="display:flex; gap:0.4rem; flex-wrap:wrap; margin-top:0.75rem;">${buttons}</div>
                `;
            } catch (err) {
                el.innerHTML = `<p class="empty-state">Fehler: ${this._esc(err.message)}</p>`;
            }
        },

        async setFindingStatus(findingId, status) {
            try {
                await this._fetchJson(`/findings/${encodeURIComponent(findingId)}`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ status }),
                });
                this.showFindingDetail(findingId);
                this.loadFindings();
            } catch (err) {
                alert(`Status-Update fehlgeschlagen: ${err.message}`);
            }
        },
    };

    window.SecurityTab = SecurityTab;
})();
