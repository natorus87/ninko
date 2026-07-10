/**
 * Ninko Scheduled Tasks Feature Module
 *
 * Editor + CRUD für geplante Aufgaben (Cron/Prompt/Workflow).
 * Aus app.js extrahiert; via Object.assign auf das Ninko-Objekt gemergt,
 * daher bleiben alle this.*-Aufrufe (Helfer, State) unverändert gültig.
 */

(function() {
    'use strict';

    const TasksFeature = {
        openTaskEditor() {
            document.getElementById('tasks-overview')?.classList.add('hidden');
            document.getElementById('tasks-logs')?.classList.add('hidden');
            document.getElementById('tasks-editor')?.classList.remove('hidden');
            // Formular zurücksetzen
            document.getElementById('sched-task-id').value = ''; // Reset task ID (neue Aufgabe)
            document.getElementById('sched-name').value = '';
            document.getElementById('sched-cron').value = '';
            document.getElementById('sched-prompt').value = '';
            const agentPromptEl = document.getElementById('sched-agent-prompt');
            if (agentPromptEl) agentPromptEl.value = '';
            if (document.getElementById('sched-agent')) document.getElementById('sched-agent').value = '';
            if (document.getElementById('sched-workflow')) document.getElementById('sched-workflow').value = '';
            if (document.getElementById('sched-module')) document.getElementById('sched-module').value = '';
            document.getElementById('sched-enabled').checked = true; // Default enabled
            const typePrompt = document.querySelector('input[name="sched-type"][value="prompt"]');
            if (typePrompt) { typePrompt.checked = true; this.toggleSchedType(); }
            const status = document.getElementById('sched-save-status');
            if (status) status.textContent = '';
            // Save Button zurücksetzen
            const saveBtn = document.getElementById('sched-save-btn');
            if (saveBtn) {
                saveBtn.textContent = '➕ Erstellen';
                saveBtn.onclick = () => this.saveScheduledTask();
            }
            // Dropdowns immer frisch befüllen wenn der Editor geöffnet wird
            this._loadSchedDropdowns();
        },

        async _loadSchedDropdowns() {
            const [wfRes, agRes] = await Promise.all([
                fetch('/api/workflows/'),
                fetch('/api/agents/'),
            ]);
            const wfSelect = document.getElementById('sched-workflow');
            if (wfSelect && wfRes.ok) {
                const wfData = await wfRes.json();
                const workflows = wfData.workflows || [];
                this._wfList = workflows;
                wfSelect.innerHTML = '<option value="">Workflow auswählen…</option>' +
                    workflows.map(wf => `<option value="${this._escapeHtml(wf.id)}">${this._escapeHtml(wf.name)}</option>`).join('');
            }
            const agentSelect = document.getElementById('sched-agent');
            if (agentSelect && agRes.ok) {
                const agData = await agRes.json();
                const agents = (agData.agents || []).filter(a => a.enabled !== false);
                this._agentList = agents;
                agentSelect.innerHTML = '<option value="">Agent auswählen…</option>' +
                    agents.map(a => `<option value="${this._escapeHtml(a.id)}">${this._escapeHtml(a.name)}</option>`).join('');
            }
        },

        closeTaskEditor() {
            document.getElementById('tasks-editor')?.classList.add('hidden');
            document.getElementById('tasks-overview')?.classList.remove('hidden');
        },

        async loadScheduledTasks() {
            const container = document.getElementById('scheduler-tasks-list');
            if (!container) return;

            try {
                const [workflowsRes, agentsRes, tasksRes] = await Promise.all([
                    fetch('/api/workflows/'),
                    fetch('/api/agents/'),
                    fetch('/api/scheduler/tasks'),
                ]);

                const workflowData = workflowsRes.ok ? await workflowsRes.json() : { workflows: [] };
                const workflows = workflowData.workflows || [];
                this._wfList = workflows;

                const agentData = agentsRes.ok ? await agentsRes.json() : { agents: [] };
                const agents = agentData.agents || [];
                this._agentList = agents;

                // Dropdowns immer befüllen (auch wenn keine Tasks vorhanden)
                const wfSelect = document.getElementById('sched-workflow');
                if (wfSelect) {
                    wfSelect.innerHTML = '<option value="">Workflow auswählen…</option>' +
                        workflows.map(wf => `<option value="${this._escapeHtml(wf.id)}">${this._escapeHtml(wf.name)}</option>`).join('');
                }
                const agentSelect = document.getElementById('sched-agent');
                if (agentSelect) {
                    agentSelect.innerHTML = '<option value="">Agent auswählen…</option>' +
                        agents.filter(a => a.enabled !== false).map(a =>
                            `<option value="${this._escapeHtml(a.id)}">${this._escapeHtml(a.name)}</option>`
                        ).join('');
                }

                if (!tasksRes.ok) throw new Error(tasksRes.statusText);
                const data = await tasksRes.json();
                const tasks = data.tasks || [];

                if (tasks.length === 0) {
                    container.innerHTML = this._renderEmptyStateCard({
                        icon: '<svg viewBox="0 0 24 24" width="36" height="36" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>',
                        title: t('empty.tasks.title'),
                        hint: t('empty.tasks.hint'),
                        actions: [{ label: t('empty.tasks.cta'), action: 'openTaskEditor', primary: true }],
                    });
                    return;
                }

                container.innerHTML = tasks.map(task => {
                    const enabledClass = task.enabled ? '' : 'task-disabled';
                    const statusBadge = task.last_result === 'ok'
                        ? '<span class="status-badge status-ok">Erfolgreich</span>'
                        : task.last_result === 'error'
                            ? '<span class="status-badge status-error">Fehlgeschlagen</span>'
                            : '<span class="status-badge status-idle">Ausstehend</span>';

                    const nextRun = task.next_run ? new Date(task.next_run).toLocaleString('de-DE') : '-';
                    const lastRun = task.last_run ? new Date(task.last_run).toLocaleString('de-DE') : 'Noch nie';

                    let taskDetails = `<div class="task-prompt">${this._escapeHtml(task.prompt || '')}</div>`;
                    if (task.workflow_id) {
                        const wf = workflows.find(w => w.id === task.workflow_id);
                        taskDetails = `<div class="task-badge task-badge-workflow">${this._ic.branch} Workflow: ${this._escapeHtml(wf ? wf.name : task.workflow_id)}</div>`;
                    } else if (task.agent_id) {
                        const ag = agents.find(a => a.id === task.agent_id);
                        taskDetails = `<div class="task-badge task-badge-agent">🤖 Agent: ${this._escapeHtml(ag ? ag.name : task.agent_id)}</div>` +
                            (task.prompt ? `<div class="task-prompt" style="margin-top:0.25rem;">${this._escapeHtml(task.prompt)}</div>` : '');
                    }

                    return `
                        <div class="task-card ${enabledClass}" data-task-id="${this._escapeHtml(task.id)}">
                            <div class="task-card-header">
                                <div class="task-card-title">
                                    <strong>${this._escapeHtml(task.name)}</strong>
                                    ${statusBadge}
                                    ${task.source === 'workflow_trigger' ? '<span class="task-badge task-badge-module" title="Automatisch aus einem Workflow-Cron-Trigger erzeugt">aus Workflow</span>' : ''}
                                    ${task.target_module ? `<span class="task-badge task-badge-module">${this._escapeHtml(task.target_module)}</span>` : ''}
                                </div>
                                <div class="task-card-actions">
                                    <button class="btn-icon-sm" data-action="run" title="Jetzt ausführen">${this._ic.play}</button>
                                    <button class="btn-icon-sm" data-action="toggle" title="${task.enabled ? 'Deaktivieren' : 'Aktivieren'}">${task.enabled ? this._ic.pause : this._ic.play}</button>
                                    <button class="btn-icon-sm" data-action="edit" title="Bearbeiten">✎</button>
                                    <button class="btn-icon-sm" data-action="logs" data-task-name="${this._escapeHtml(task.name)}" title="Logs">${this._ic.list}</button>
                                    <button class="btn-icon-sm btn-danger-sm" data-action="delete" title="Löschen">${this._ic.trash}</button>
                                </div>
                            </div>
                            <div class="task-card-body">
                                ${taskDetails}
                                <div class="task-meta">
                                    <span>${this._ic.cron} <code>${this._escapeHtml(task.cron)}</code></span>
                                    <span>Nächste: ${nextRun}</span>
                                    <span>Letzte: ${lastRun}</span>
                                </div>
                            </div>
                        </div>
                    `;
                }).join('');

                // Event-Delegation
                container.querySelectorAll('.task-card').forEach(card => {
                    const id = card.dataset.taskId;
                    card.querySelector('[data-action="run"]')?.addEventListener('click', () => this.runScheduledTask(id));
                    card.querySelector('[data-action="toggle"]')?.addEventListener('click', () => this.toggleScheduledTask(id));
                    card.querySelector('[data-action="edit"]')?.addEventListener('click', () => this.editScheduledTask(id));
                    card.querySelector('[data-action="logs"]')?.addEventListener('click', e => {
                        const name = e.currentTarget.dataset.taskName || '';
                        this.viewTaskLogs(id, name);
                    });
                    card.querySelector('[data-action="delete"]')?.addEventListener('click', () => this.deleteScheduledTask(id));
                });

            } catch (err) {
                container.innerHTML = `<p class="text-error">Fehler: ${this._escapeHtml(err.message)}</p>`;
            }
        },

        async saveScheduledTask() {
            const name = document.getElementById('sched-name')?.value?.trim();
            const cron = document.getElementById('sched-cron')?.value?.trim();
            const status = document.getElementById('sched-save-status');

            const type = document.querySelector('input[name="sched-type"]:checked')?.value;
            const prompt = document.getElementById('sched-prompt')?.value?.trim() || "";
            const agentId = document.getElementById('sched-agent')?.value || null;
            const agentPrompt = document.getElementById('sched-agent-prompt')?.value?.trim() || "";
            const workflowId = document.getElementById('sched-workflow')?.value || null;
            const module = document.getElementById('sched-module')?.value || null;

            if (!name || !cron) {
                if (status) status.textContent = 'Name und Zeitplan sind Pflicht.';
                return;
            }

            if (type === 'prompt' && !prompt) {
                if (status) status.textContent = 'Prompt ist Pflicht für Agenten-Aufträge.';
                return;
            }

            if (type === 'agent' && !agentId) {
                if (status) status.textContent = 'Agent muss ausgewählt werden.';
                return;
            }

            if (type === 'workflow' && !workflowId) {
                if (status) status.textContent = 'Workflow muss ausgewählt werden.';
                return;
            }

            try {
                const body = {
                    name, cron, enabled: true,
                    target_module: module
                };

                if (type === 'prompt') {
                    body.prompt = prompt;
                } else if (type === 'agent') {
                    body.agent_id = agentId;
                    body.prompt = agentPrompt || "";
                } else {
                    body.workflow_id = workflowId;
                    body.prompt = "";
                }

                const res = await fetch('/api/scheduler/tasks', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });

                if (!res.ok) {
                    const err = await res.json();
                    throw new Error(err.detail || 'Fehler');
                }

                showNotification('Aufgabe erstellt!', 'success');
                this.closeTaskEditor();
                await this.loadScheduledTasks();
            } catch (err) {
                if (status) status.textContent = err.message || 'Fehler';
            }
        },

        toggleSchedType() {
            const type = document.querySelector('input[name="sched-type"]:checked')?.value;
            const promptRow = document.getElementById('sched-prompt-row');
            const agentRow = document.getElementById('sched-agent-row');
            const workflowRow = document.getElementById('sched-workflow-row');
            const moduleRow = document.getElementById('sched-module')?.parentElement;

            promptRow?.classList.toggle('hidden', type !== 'prompt');
            agentRow?.classList.toggle('hidden', type !== 'agent');
            workflowRow?.classList.toggle('hidden', type !== 'workflow');
            // Modul-Override nur bei Prompt sinnvoll
            moduleRow?.classList.toggle('hidden', type !== 'prompt');
        },

        async deleteScheduledTask(id) {
            if (!await this.confirm('Aufgabe wirklich löschen?')) return;

            try {
                await fetch(`/api/scheduler/tasks/${id}`, { method: 'DELETE' });
                showNotification('Aufgabe gelöscht.', 'info');
                await this.loadScheduledTasks();
            } catch (err) {
                showNotification(`Fehler: ${err.message}`, 'error');
            }
        },

        async editScheduledTask(id) {
            try {
                // Fetch task details
                const res = await fetch('/api/scheduler/tasks');
                if (!res.ok) throw new Error(res.statusText);
                const data = await res.json();
                const task = data.tasks?.find(t => t.id === id);
                if (!task) throw new Error('Aufgabe nicht gefunden');

                // Show editor
                this.openTaskEditor();

                // Fill form with task data
                document.getElementById('sched-task-id').value = task.id;
                document.getElementById('sched-name').value = task.name || '';
                document.getElementById('sched-cron').value = task.cron || '';
                document.getElementById('sched-module').value = task.target_module || '';
                document.getElementById('sched-enabled').checked = task.enabled !== false;

                // Determine type and fill accordingly
                let type = 'prompt';
                if (task.workflow_id) type = 'workflow';
                else if (task.agent_id) type = 'agent';

                // Set radio button
                const radio = document.querySelector(`input[name="sched-type"][value="${type}"]`);
                if (radio) radio.checked = true;
                this.toggleSchedType();

                // Fill type-specific fields
                if (type === 'prompt') {
                    document.getElementById('sched-prompt').value = task.prompt || '';
                } else if (type === 'agent') {
                    document.getElementById('sched-agent').value = task.agent_id || '';
                    document.getElementById('sched-agent-prompt').value = task.prompt || '';
                } else {
                    document.getElementById('sched-workflow').value = task.workflow_id || '';
                }

                // Update save button
                const saveBtn = document.getElementById('sched-save-btn');
                if (saveBtn) {
                    saveBtn.textContent = '💾 Aktualisieren';
                    saveBtn.onclick = () => this.updateScheduledTask(id);
                }
            } catch (err) {
                showNotification(`Fehler beim Laden: ${err.message}`, 'error');
            }
        },

        async updateScheduledTask(id) {
            const status = document.getElementById('sched-status');
            if (status) status.textContent = 'Speichere…';

            try {
                const name = document.getElementById('sched-name').value.trim();
                const cron = document.getElementById('sched-cron').value.trim();
                const targetModule = document.getElementById('sched-module').value.trim();
                const enabled = document.getElementById('sched-enabled').checked;
                const type = document.querySelector('input[name="sched-type"]:checked')?.value;

                if (!name || !cron) {
                    if (status) status.textContent = 'Name und Cron-Ausdruck erforderlich.';
                    return;
                }

                const body = {
                    name,
                    cron,
                    target_module: targetModule || null,
                    enabled,
                };

                if (type === 'prompt') {
                    body.prompt = document.getElementById('sched-prompt').value.trim();
                } else if (type === 'agent') {
                    body.agent_id = document.getElementById('sched-agent').value;
                    body.prompt = document.getElementById('sched-agent-prompt').value.trim();
                } else {
                    body.workflow_id = document.getElementById('sched-workflow').value;
                }

                const res = await fetch(`/api/scheduler/tasks/${id}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });

                if (!res.ok) {
                    const err = await res.json();
                    throw new Error(err.detail || 'Fehler beim Aktualisieren');
                }

                showNotification('Aufgabe aktualisiert!', 'success');
                this.closeTaskEditor();
                await this.loadScheduledTasks();
            } catch (err) {
                if (status) status.textContent = err.message || 'Fehler';
            }
        },

        async toggleScheduledTask(id) {
            try {
                const res = await fetch(`/api/scheduler/tasks/${id}/toggle`, { method: 'PUT' });
                const task = await res.json();
                showNotification(
                    `Aufgabe "${task.name}" ${task.enabled ? 'aktiviert' : 'deaktiviert'}.`,
                    'info'
                );
                await this.loadScheduledTasks();
            } catch (err) {
                showNotification(`Fehler: ${err.message}`, 'error');
            }
        },

        async runScheduledTask(id) {
            try {
                const res = await fetch(`/api/scheduler/tasks/${id}/run`, { method: 'POST' });
                const result = await res.json();
                // Läuft asynchron im Backend — Ergebnis kommt via WS-Event 'task_executed'
                showNotification(
                    result.status === 'already_running'
                        ? 'Aufgabe läuft bereits.'
                        : 'Aufgabe gestartet — Ergebnis erscheint in den Logs.',
                    'info'
                );
                await this.loadScheduledTasks();
            } catch (err) {
                showNotification(`Fehler: ${err.message}`, 'error');
            }
        },

        async viewTaskLogs(taskId, taskName) {
            const section = document.getElementById('tasks-logs');
            const list = document.getElementById('scheduler-logs-list');
            const nameEl = document.getElementById('scheduler-log-task-name');
            if (!section || !list) return;

            document.getElementById('tasks-overview')?.classList.add('hidden');
            document.getElementById('tasks-editor')?.classList.add('hidden');
            nameEl.textContent = taskName;
            section.classList.remove('hidden');
            list.innerHTML = 'Lade…';

            try {
                const res = await fetch(`/api/scheduler/tasks/${taskId}/logs?limit=20`);
                if (!res.ok) throw new Error(res.statusText);
                const logs = await res.json();

                if (!logs || logs.length === 0) {
                    list.innerHTML = '<p class="text-muted"><em>Noch keine Ausführungen.</em></p>';
                    return;
                }

                list.innerHTML = logs.map(log => {
                    const statusIcon = log.status === 'ok' ? this._ic.check : this._ic.xcircle;
                    const time = new Date(log.timestamp).toLocaleString('de-DE');
                    const response = log.response ? log.response.substring(0, 300) : '—';
                    const truncated = log.response?.length > 300 ? '…' : '';
                    return `
                        <div class="log-entry log-entry-${this._escapeHtml(log.status)}">
                            <div class="log-entry-header">
                                <span>${statusIcon} ${time}</span>
                                <span class="log-meta">${Number(log.duration_ms) || 0}ms${log.module_used ? ' · ' + this._escapeHtml(log.module_used) : ''}</span>
                            </div>
                            <div class="log-entry-response">${this._escapeHtml(response)}${truncated}</div>
                        </div>
                    `;
                }).join('');
            } catch (err) {
                list.innerHTML = `<p class="text-error">Fehler: ${this._escapeHtml(err.message)}</p>`;
            }
        },

        hideTaskLogs() {
            document.getElementById('tasks-logs')?.classList.add('hidden');
            document.getElementById('tasks-overview')?.classList.remove('hidden');
        },


        applyCronPreset() {
            const preset = document.getElementById('sched-cron-preset')?.value;
            if (preset) {
                document.getElementById('sched-cron').value = preset;
            }
        },
    };

    if (typeof window.Ninko !== 'undefined') {
        Object.assign(window.Ninko, TasksFeature);
    } else {
        window.TasksFeature = TasksFeature;
    }
})();
