/**
 * Ninko Scripting Feature Module
 * 
 * Enthält alle Scripting-bezogenen Funktionen:
 * - Script-Liste und CRUD
 * - Script-Editor mit Code-Area
 * - Script-Ausführung und Status-Anzeige
 * - Ausführungshistorie
 */

(function() {
    'use strict';

    const ScriptingFeature = {
        _scripts: [],
        _currentScriptId: null,

        initScriptingFeature() {
            return this.loadScripts();
        },

        async loadScripts() {
            const container = document.getElementById('scripts-list');
            if (!container) return;
            container.innerHTML = `<p class="empty-state">${this._escapeHtml(t('common.loading'))}</p>`;
            try {
                const res = await fetch('/api/scripting/scripts');
                if (!res.ok) throw new Error(res.statusText);
                const data = await res.json();
                this._scripts = data.scripts || [];
                
                if (!this._scripts.length) {
                    container.innerHTML = this._renderEmptyStateCard({
                        icon: '<svg viewBox="0 0 24 24" width="36" height="36" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>',
                        title: t('empty.scripts.title'),
                        hint: t('empty.scripts.hint'),
                        actions: [{ label: t('empty.scripts.cta'), action: 'openScriptEditor', args: [null], primary: true }],
                    });
                    return;
                }
                
                container.innerHTML = this._scripts.map(s => `
                    <div class="script-card" data-script-id="${this._escapeHtml(s.id)}">
                        <div class="script-card-header">
                            <span class="script-card-name">${this._escapeHtml(s.name)}</span>
                            <div style="display:flex;gap:0.5rem;align-items:center;">
                                ${s.tool_enabled ? '<span class="tool-badge">Tool aktiv</span>' : ''}
                                <span class="run-status-badge run-${this._escapeHtml(s.last_run_status || 'idle')}">${this._escapeHtml(s.last_run_status || 'idle')}</span>
                            </div>
                        </div>
                        <p class="script-card-desc">${this._escapeHtml(s.description || '')}</p>
                        <div class="script-card-meta">
                            <span>${s.language || 'python'}</span>
                            <span>${s.timeout || 30}s timeout</span>
                            ${s.run_count ? `<span>${s.run_count} Runs</span>` : ''}
                            ${s.last_run_at ? `<span>Letzter Run: ${new Date(s.last_run_at).toLocaleString('de')}</span>` : ''}
                        </div>
                        <div class="script-card-actions">
                            <button class="btn btn-sm btn-primary" onclick="Ninko.runScript('${s.id}')">▶ Ausführen</button>
                            <button class="btn btn-sm btn-outline" onclick="Ninko.openScriptEditor('${s.id}')">Bearbeiten</button>
                            <button class="btn btn-sm btn-outline" onclick="Ninko.deleteScript('${s.id}')" style="color:var(--error-color)">Löschen</button>
                        </div>
                    </div>
                `).join('');
            } catch (e) {
                container.innerHTML = `<p class="empty-state text-error">${this._escapeHtml(t('common.loadError'))}</p>`;
            }
        },

        async openScriptEditor(scriptId) {
            this._currentScriptId = scriptId;
            document.getElementById('scripting-overview').classList.add('hidden');
            document.getElementById('scripting-editor').classList.remove('hidden');
            
            document.getElementById('script-execution-status').style.display = 'none';
            document.getElementById('script-execution-history').innerHTML = `<p class="text-muted">${this._escapeHtml(t('common.loading'))}</p>`;
            
            if (scriptId) {
                document.getElementById('script-editor-title').textContent = 'Script bearbeiten';
                try {
                    const res = await fetch(`/api/scripting/scripts/${scriptId}`);
                    const s = await res.json();
                    document.getElementById('script-edit-id').value = scriptId;
                    document.getElementById('script-name').value = s.name || '';
                    document.getElementById('script-description').value = s.description || '';
                    document.getElementById('script-timeout').value = s.timeout || 30;
                    document.getElementById('script-tags').value = (s.tags || []).join(', ');

                    document.getElementById('script-tool-enabled').checked = s.tool_enabled || false;
                    document.getElementById('script-tool-name').value = s.tool_name || '';
                    document.getElementById('script-tool-description').value = s.tool_description || '';
                    document.getElementById('script-tool-schema').value = s.tool_input_schema ? JSON.stringify(s.tool_input_schema, null, 2) : '';
                    this.toggleToolFields();

                    const codeRes = await fetch(`/api/scripting/scripts/${scriptId}/code`);
                    const codeData = await codeRes.json();
                    document.getElementById('script-code').value = codeData.code || '';
                    await this._loadScriptExecutionHistory(scriptId);
                } catch {
                    showNotification(t('common.loadError'), 'error');
                }
            } else {
                document.getElementById('script-editor-title').textContent = 'Neues Script';
                document.getElementById('script-edit-id').value = '';
                document.getElementById('script-name').value = '';
                document.getElementById('script-description').value = '';
                document.getElementById('script-timeout').value = 30;
                document.getElementById('script-tags').value = '';
                document.getElementById('script-code').value = '#!/usr/bin/env python3\n# Dein Python-Code hier\nprint("Hello, World!")';
                document.getElementById('script-execution-history').innerHTML = `<p class="text-muted">${this._escapeHtml(t('script.noRuns'))}</p>`;
                document.getElementById('script-tool-enabled').checked = false;
                document.getElementById('script-tool-name').value = '';
                document.getElementById('script-tool-description').value = '';
                document.getElementById('script-tool-schema').value = '';
                this.toggleToolFields();
            }
        },

        closeScriptEditor() {
            document.getElementById('scripting-editor').classList.add('hidden');
            document.getElementById('scripting-overview').classList.remove('hidden');
            this.loadScripts();
        },

        toggleToolFields() {
            const enabled = document.getElementById('script-tool-enabled').checked;
            const fields = document.getElementById('script-tool-fields');
            fields.style.display = enabled ? 'block' : 'none';
            if (enabled) {
                document.getElementById('script-tool-name').focus();
            }
        },

        async saveScript() {
            const scriptId = document.getElementById('script-edit-id').value;
            const name = document.getElementById('script-name').value.trim();
            const description = document.getElementById('script-description').value.trim();
            const timeout = parseInt(document.getElementById('script-timeout').value) || 30;
            const tagsStr = document.getElementById('script-tags').value.trim();
            const code = document.getElementById('script-code').value;
            const toolEnabled = document.getElementById('script-tool-enabled').checked;
            const toolName = document.getElementById('script-tool-name').value.trim();
            const toolDescription = document.getElementById('script-tool-description').value.trim();
            const toolSchemaStr = document.getElementById('script-tool-schema').value.trim();

            if (!name) {
                showNotification(t('common.nameRequired'), 'error');
                return;
            }
            if (!code) {
                showNotification(t('script.codeRequired'), 'error');
                return;
            }
            if (toolEnabled && !toolName) {
                showNotification(t('script.toolNameRequired'), 'error');
                return;
            }

            const tags = tagsStr ? tagsStr.split(',').map(t => t.trim()).filter(Boolean) : [];
            const body = {
                name,
                description,
                code,
                timeout,
                tags,
                language: 'python',
                tool_enabled: toolEnabled
            };

            if (toolEnabled) {
                body.tool_name = toolName;
                body.tool_description = toolDescription || null;
                if (toolSchemaStr) {
                    try {
                        body.tool_input_schema = JSON.parse(toolSchemaStr);
                    } catch (e) {
                        showNotification(t('script.schemaInvalid'), 'error');
                        return;
                    }
                } else {
                    body.tool_input_schema = null;
                }
            }

            const saveBtn = document.getElementById('script-save-btn');
            if (saveBtn) { saveBtn.disabled = true; saveBtn.textContent = 'Speichern…'; }

            try {
                const url = scriptId ? `/api/scripting/scripts/${scriptId}` : '/api/scripting/scripts';
                const method = scriptId ? 'PUT' : 'POST';
                const res = await fetch(url, {
                    method,
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body)
                });

                if (res.ok) {
                    const result = await res.json();
                    showNotification(`${t('script.saved')}: "${name}"`, 'success');
                    this._currentScriptId = result.id || scriptId;
                    document.getElementById('script-edit-id').value = this._currentScriptId;
                    document.getElementById('script-editor-title').textContent = 'Script bearbeiten';
                } else {
                    const err = await res.json().catch(() => ({}));
                    showNotification(`${t('common.error')}: ` + (err.detail || res.statusText), 'error');
                }
            } catch {
                showNotification(t('common.connectionError'), 'error');
            } finally {
                if (saveBtn) { saveBtn.disabled = false; saveBtn.textContent = 'Speichern'; }
            }
        },

        async deleteScript(scriptId) {
            if (!await this.confirm(t('script.deleteConfirm'))) return;
            try {
                const res = await fetch(`/api/scripting/scripts/${scriptId}`, { method: 'DELETE' });
                if (res.ok) {
                    showNotification(t('script.deleted'), 'info');
                    this.loadScripts();
                } else {
                    showNotification(t('common.deleteFailed'), 'error');
                }
            } catch {
                showNotification(t('common.connectionError'), 'error');
            }
        },

        async runScript(scriptId) {
            try {
                showNotification(t('script.running'), 'info');
                const res = await fetch(`/api/scripting/scripts/${scriptId}/execute`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                });
                
                if (!res.ok) throw new Error(res.statusText);
                const result = await res.json();
                
                const ok = result.status === 'succeeded';
                const statusText = ok ? t('script.runSucceeded') : t('script.runFailed');
                showNotification(`${statusText} (${result.duration_ms.toFixed(0)}ms)`, ok ? 'success' : 'error');
                
                this.loadScripts();
                
                return result;
            } catch (e) {
                showNotification(`${t('script.runFailed')}: ` + e.message, 'error');
                throw e;
            }
        },

        async runCurrentScript() {
            const scriptId = document.getElementById('script-edit-id').value;
            if (!scriptId) {
                showNotification(t('script.saveFirst'), 'warning');
                return;
            }
            
            const statusEl = document.getElementById('script-execution-status');
            const outputEl = document.getElementById('script-run-output');
            const statusBadge = document.getElementById('script-run-status');
            
            statusEl.style.display = 'block';
            statusBadge.className = 'run-status-badge run-running';
            statusBadge.textContent = 'läuft…';
            outputEl.textContent = '';
            
            try {
                const result = await this.runScript(scriptId);
                
                statusBadge.className = `run-status-badge run-${result.status}`;
                statusBadge.textContent = result.status;
                
                let output = '';
                if (result.stdout) output += `STDOUT:\n${result.stdout}\n`;
                if (result.stderr) output += `STDERR:\n${result.stderr}\n`;
                if (result.exit_code !== 0 && result.exit_code !== null) {
                    output += `Exit Code: ${result.exit_code}`;
                }
                outputEl.textContent = output || 'Keine Ausgabe';
                await this._loadScriptExecutionHistory(scriptId);
            } catch {
                statusBadge.className = 'run-status-badge run-failed';
                statusBadge.textContent = 'fehlgeschlagen';
            }
        },

        async _loadScriptExecutionHistory(scriptId) {
            const container = document.getElementById('script-execution-history');
            try {
                const res = await fetch(`/api/scripting/scripts/${scriptId}/executions?limit=10`);
                const data = await res.json();
                const executions = data.executions || [];
                
                if (!executions.length) {
                    container.innerHTML = `<p class="text-muted">${this._escapeHtml(t('script.noRuns'))}</p>`;
                    return;
                }
                
                container.innerHTML = executions.map(e => `
                    <div style="padding:0.5rem;border-bottom:1px solid var(--border-color);font-size:0.8rem;">
                        <div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.25rem;">
                            <span class="run-status-badge run-${e.status}" style="font-size:0.7rem;">${e.status}</span>
                            <span style="color:var(--text-muted);">${e.started_at ? new Date(e.started_at).toLocaleString('de') : '–'}</span>
                        </div>
                        <div>${e.duration_ms.toFixed(0)}ms</div>
                        ${e.exit_code !== 0 && e.exit_code !== null ? `<div style="color:var(--error-color);">Exit: ${e.exit_code}</div>` : ''}
                    </div>
                `).join('');
            } catch {
                container.innerHTML = `<p class="text-muted">${this._escapeHtml(t('common.loadError'))}</p>`;
            }
        }
    };

    if (typeof window.Ninko !== 'undefined') {
        Object.assign(window.Ninko, ScriptingFeature);
    } else {
        window.ScriptingFeature = ScriptingFeature;
    }
})();
