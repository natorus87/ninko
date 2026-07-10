/**
 * Ninko LLM Provider Settings Feature Module
 *
 * Multi-Provider-Verwaltung (CRUD, Test, Default), Embedding-Provider,
 * Modul-Routing (Function-Calling). Aus app.js extrahiert; via Object.assign
 * gemergt. loadLlmSettings (Legacy-Single-Provider) bleibt in app.js.
 */

(function() {
    'use strict';

    const LlmProviderFeature = {
        async loadLlmProviders() {
            const container = document.getElementById('llm-providers-list');
            if (!container) return;
            try {
                const res = await fetch('/api/settings/llm/providers');
                if (!res.ok) throw new Error(res.statusText);
                const providers = await res.json();
                if (!providers.length) {
                    container.innerHTML = '<p class="text-muted" style="font-size:0.85rem;">Noch keine Provider konfiguriert.</p>';
                    return;
                }
                const statusDot = { connected: '<span class="status-dot connected"></span>', unreachable: '<span class="status-dot disconnected"></span>', unknown: '<span class="status-dot"></span>' };
                container.innerHTML = providers.map(p => `
                    <div class="provider-card ${p.is_default ? 'provider-default' : ''}">
                        <div class="provider-card-header">
                            <div>
                                <span class="provider-name">${this._escapeHtml(p.name)}</span>
                                ${p.is_default ? '<span class="badge-default">Standard</span>' : ''}
                            </div>
                            <div class="provider-actions">
                                <span class="provider-status" title="${this._escapeHtml(p.status || '')}">${statusDot[p.status] || statusDot.unknown}</span>
                                <button class="btn btn-sm btn-outline" data-action="testLlmProvider" data-args="${JSON.stringify([p.id]).replace(/\"/g, '&quot;')}">Test</button>
                                <button class="btn-icon btn-icon-sm" data-action="openProviderEditor" data-args="${JSON.stringify([p.id]).replace(/\"/g, '&quot;')}">${this._ic.edit}</button>
                                <button class="btn-icon btn-icon-sm" data-action="deleteLlmProvider" data-args="${JSON.stringify([p.id, p.name]).replace(/\"/g, '&quot;')}" style="color:var(--error-color)">${this._ic.trash}</button>
                            </div>
                        </div>
                        <div class="provider-meta">
                            <span>${this._escapeHtml({ollama:'Ollama',lmstudio:'LM Studio',mlx_server:'MLX Server',openai_compatible:'OpenAI',litellm:'LiteLLM'}[p.backend] || p.backend || '')}</span> · <span>${this._escapeHtml(p.base_url || '')}</span> · <span>${this._escapeHtml(p.model || '')}</span>${p.context_window > 0 ? ` · <span>${(p.context_window >= 1000 ? (p.context_window/1000).toFixed(0)+'k' : p.context_window)} ctx</span>` : ''}${p.verify_ssl === false ? ' · <span style="color:var(--warning-color,#f0b429)" title="SSL-Verifizierung deaktiviert">⚠ SSL off</span>' : ''}
                        </div>
                        ${!p.is_default ? `<button class="btn btn-sm btn-outline" style="margin-top:0.5rem;" data-action="setDefaultProvider" data-args="${JSON.stringify([p.id]).replace(/\"/g, '&quot;')}">Als Standard setzen</button>` : ''}
                    </div>
                `).join('');
            } catch { container.innerHTML = '<p class="empty-state">Fehler beim Laden.</p>'; }
        },

        async openProviderEditor(providerId) {
            const editor = document.getElementById('llm-provider-editor');
            document.getElementById('provider-edit-id').value = providerId || '';
            document.getElementById('provider-editor-title').textContent = providerId ? 'Provider bearbeiten' : 'Neuer Provider';
            document.getElementById('provider-name').value = '';
            document.getElementById('provider-backend').value = 'ollama';
            document.getElementById('provider-url').value = '';
            document.getElementById('provider-model').value = '';
            document.getElementById('provider-api-key').value = '';
            document.getElementById('provider-api-key').dataset.hasKey = '0';
            document.getElementById('provider-context-window').value = 0;
            document.getElementById('provider-verify-ssl').checked = true;
            document.getElementById('provider-is-default').checked = false;

            if (providerId) {
                try {
                    const res = await fetch('/api/settings/llm/providers');
                    const providers = await res.json();
                    const p = providers.find(x => x.id === providerId);
                    if (p) {
                        document.getElementById('provider-name').value = p.name;
                        document.getElementById('provider-backend').value = p.backend;
                        document.getElementById('provider-url').value = p.base_url;
                        document.getElementById('provider-model').value = p.model;
                        document.getElementById('provider-api-key').value = p.api_key_set ? '••••••••' : '';
                        document.getElementById('provider-api-key').dataset.hasKey = p.api_key_set ? '1' : '0';
                        document.getElementById('provider-context-window').value = p.context_window || 0;
                        document.getElementById('provider-verify-ssl').checked = p.verify_ssl !== false;
                        document.getElementById('provider-is-default').checked = p.is_default;
                    }
                } catch (err) { console.warn('loadLLMProviders failed', err); }
            }
            this.toggleProviderApiKey();
            editor.classList.remove('hidden');
        },

        closeProviderEditor() {
            document.getElementById('llm-provider-editor').classList.add('hidden');
        },

        async saveLlmProvider() {
            const statusEl = document.getElementById('provider-save-status');
            statusEl.textContent = 'Speichere…';
            const keyEl = document.getElementById('provider-api-key');
            const keyVal = keyEl?.value || '';
            const apiKey = keyVal && keyVal !== '••••••••' ? keyVal : '';
            const body = {
                name: document.getElementById('provider-name').value,
                backend: document.getElementById('provider-backend').value,
                base_url: document.getElementById('provider-url').value,
                model: document.getElementById('provider-model').value,
                api_key: apiKey,
                is_default: document.getElementById('provider-is-default').checked,
                context_window: parseInt(document.getElementById('provider-context-window').value || '0', 10),
                verify_ssl: document.getElementById('provider-verify-ssl').checked,
            };
            const id = document.getElementById('provider-edit-id').value;
            try {
                const url = id ? `/api/settings/llm/providers/${id}` : '/api/settings/llm/providers';
                const method = id ? 'PUT' : 'POST';
                const res = await fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
                if (res.ok) {
                    statusEl.textContent = 'Gespeichert';
                    if (keyEl && body.api_key) {
                        keyEl.value = '••••••••';
                        keyEl.dataset.hasKey = '1';
                    }
                    showNotification(`Provider "${body.name}" gespeichert`, 'success');
                    this.closeProviderEditor();
                    this.loadLlmProviders();
                } else { statusEl.textContent = 'Fehler'; }
            } catch { statusEl.textContent = 'Verbindungsfehler'; }
        },

        async deleteLlmProvider(id, name) {
            if (!confirm(`Provider "${name}" löschen?`)) return;
            try {
                const res = await fetch(`/api/settings/llm/providers/${id}`, { method: 'DELETE' });
                if (res.ok) { showNotification(`Provider "${name}" gelöscht`, 'info'); this.loadLlmProviders(); }
            } catch { showNotification('Verbindungsfehler', 'error'); }
        },

        async testLlmProvider(id) {
            showNotification('Teste Verbindung…', 'info');
            try {
                const res = await fetch(`/api/settings/llm/providers/${id}/test`, { method: 'POST' });
                const data = await res.json();
                if (data.status === 'connected') showNotification('Verbindung erfolgreich', 'success');
                else showNotification(`Nicht erreichbar: ${data.error || ''}`, 'error');
                this.loadLlmProviders();
            } catch { showNotification('Verbindungsfehler', 'error'); }
        },

        async setDefaultProvider(id) {
            try {
                const res = await fetch('/api/settings/llm/default', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ provider_id: id }) });
                if (res.ok) { showNotification('Standard-Provider gesetzt', 'success'); this.loadLlmProviders(); }
            } catch { showNotification('Fehler', 'error'); }
        },

        toggleProviderApiKey() {
            const backend = document.getElementById('provider-backend').value;
            const row = document.getElementById('provider-api-key-row');
            if (row) row.style.display = (backend === 'openai_compatible' || backend === 'litellm' || backend === 'mlx_server') ? '' : 'none';
        },

        async loadEmbedModel() {
            // Legacy-Wrapper – lädt jetzt den vollen Provider
            await this.loadEmbedProvider();
        },

        async loadEmbedProvider() {
            try {
                const res = await fetch('/api/settings/llm/embed-provider');
                if (!res.ok) return;
                const data = await res.json();

                const useCustom = !!data.use_custom;
                const cbEl = document.getElementById('embed-use-custom');
                if (cbEl) {
                    cbEl.checked = useCustom;
                    this.toggleEmbedCustom();
                }
                const backendEl = document.getElementById('embed-backend');
                if (backendEl && data.backend) backendEl.value = data.backend;
                const urlEl = document.getElementById('embed-base-url');
                if (urlEl) urlEl.value = data.base_url || '';
                // API-Key: nicht vorab befüllen (Sicherheit); Placeholder zeigen
                const modelEl = document.getElementById('embed-model');
                if (modelEl) modelEl.value = data.model || '';
                this.toggleEmbedApiKey();
            } catch { }
        },

        toggleEmbedCustom() {
            const checked = document.getElementById('embed-use-custom')?.checked;
            const fields = document.getElementById('embed-custom-fields');
            if (fields) fields.style.display = checked ? '' : 'none';
        },

        toggleEmbedApiKey() {
            const backend = document.getElementById('embed-backend')?.value;
            const row = document.getElementById('embed-api-key-row');
            if (row) row.style.display = (backend === 'openai_compatible' || backend === 'litellm') ? '' : 'none';
        },

        async loadRoutingMode() {
            try {
                const res = await fetch('/api/settings/routing/mode');
                if (!res.ok) return;
                const data = await res.json();
                const cb = document.getElementById('fn-call-enabled');
                if (cb) cb.checked = data.function_calling_enabled;
                const tcRow = document.getElementById('fn-call-tool-choice-row');
                if (tcRow) tcRow.style.display = data.function_calling_enabled ? '' : 'none';
                const tcEl = document.getElementById('fn-call-tool-choice');
                if (tcEl && data.tool_choice) tcEl.value = data.tool_choice;
            } catch { }
        },

        toggleFnCall() {
            const cb = document.getElementById('fn-call-enabled');
            const tcRow = document.getElementById('fn-call-tool-choice-row');
            if (tcRow) tcRow.style.display = cb?.checked ? '' : 'none';
        },

        async testFnCall() {
            const resultEl = document.getElementById('fn-call-test-result');
            if (resultEl) resultEl.textContent = 'Teste…';
            try {
                const res = await fetch('/api/settings/routing/mode/smoke-test', { method: 'POST' });
                const data = await res.json();
                if (resultEl) {
                    if (data.supported) {
                        resultEl.innerHTML = '<span style="color:var(--success-color,#22c55e)">✓ Function Calling wird unterstützt</span>';
                    } else {
                        resultEl.innerHTML = `<span style="color:var(--error-color)">✗ Nicht unterstützt: ${this._escapeHtml(data.error || data.recommendation || 'Unbekannt')}</span>`;
                    }
                }
            } catch (e) {
                if (resultEl) resultEl.textContent = 'Fehler: ' + e.message;
            }
        },

        async saveRoutingMode() {
            const statusEl = document.getElementById('fn-call-status');
            const enabled = document.getElementById('fn-call-enabled')?.checked ?? true;
            const toolChoice = document.getElementById('fn-call-tool-choice')?.value || 'auto';
            if (statusEl) statusEl.textContent = 'Speichere…';
            try {
                const res = await fetch('/api/settings/routing/mode', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ function_calling_enabled: enabled, tool_choice: toolChoice }),
                });
                if (res.ok) {
                    if (statusEl) statusEl.textContent = 'Gespeichert';
                    showNotification('Routing-Modus gespeichert', 'success');
                } else {
                    if (statusEl) statusEl.textContent = 'Fehler';
                }
            } catch {
                if (statusEl) statusEl.textContent = 'Verbindungsfehler';
            }
        },

        async saveEmbedProvider() {
            const statusEl = document.getElementById('embed-provider-status');
            const model = document.getElementById('embed-model')?.value.trim();
            if (!model) {
                if (statusEl) statusEl.textContent = t('settings.embedModelRequired') || 'Modellname darf nicht leer sein';
                return;
            }
            if (statusEl) statusEl.textContent = t('settings.saving') || 'Speichere…';

            const useCustom = !!document.getElementById('embed-use-custom')?.checked;
            const backend = document.getElementById('embed-backend')?.value || 'lmstudio';
            const baseUrl = document.getElementById('embed-base-url')?.value.trim() || '';
            const apiKey = document.getElementById('embed-api-key')?.value.trim() || '';

            try {
                const res = await fetch('/api/settings/llm/embed-provider', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ use_custom: useCustom, backend, base_url: baseUrl, api_key: apiKey, model }),
                });
                if (res.ok) {
                    if (statusEl) statusEl.textContent = t('settings.saved') || 'Gespeichert';
                    showNotification(t('settings.embedSaved') || 'Embedding-Provider gespeichert', 'success');
                } else {
                    const err = await res.json().catch(() => ({}));
                    if (statusEl) statusEl.textContent = err.detail || 'Fehler';
                }
            } catch {
                if (statusEl) statusEl.textContent = t('settings.connectionError') || 'Verbindungsfehler';
            }
        },

        // Legacy – falls irgendwo noch direkt aufgerufen
        async saveEmbedModel() { await this.saveEmbedProvider(); },
    };

    if (typeof window.Ninko !== 'undefined') {
        Object.assign(window.Ninko, LlmProviderFeature);
    } else {
        window.LlmProviderFeature = LlmProviderFeature;
    }
})();
