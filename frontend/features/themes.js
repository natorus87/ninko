/**
 * Ninko Themes Feature Module
 *
 * Theme-Katalog, Custom-Theme-Editor und Theme-Repos. Aus app.js extrahiert;
 * via Object.assign gemergt. Der _themes/_activeThemeId/_themeRepos-State und
 * loadActiveTheme/applyActiveThemeTokens bleiben in app.js (Init-Bereich);
 * initBackgroundSettingsUI liegt in features/background_settings.js.
 */

(function() {
    'use strict';

    const ThemesFeature = {
        async loadThemesSettings() {
            await this.loadActiveTheme();
            await this.loadThemesCatalog();
            await this.loadThemeRepos();
            this._renderThemeCards();
            this.initBackgroundSettingsUI();
        },

        async loadThemesCatalog() {
            try {
                const res = await fetch('/api/themes/', { cache: 'no-store' });
                if (!res.ok) throw new Error(res.statusText);
                const data = await res.json();
                this._themes = data.themes || [];
                this._activeThemeId = data.active_theme_id || this._activeThemeId || 'default';
            } catch (e) {
                const container = document.getElementById('themes-presets-list');
                if (container) container.innerHTML = '<p class="text-muted">Themes konnten nicht geladen werden.</p>';
                console.error('loadThemesCatalog:', e);
            }
        },

        _renderThemeCards() {
            const container = document.getElementById('themes-presets-list');
            const indicator = document.getElementById('themes-active-indicator');
            if (!container) return;
            if (indicator) indicator.textContent = `Aktiv: ${this._activeThemeId || 'default'}`;
            if (!this._themes.length) {
                container.innerHTML = '<p class="text-muted">Keine Themes gefunden.</p>';
                return;
            }
            container.innerHTML = this._themes.map((th) => {
                const active = th.id === this._activeThemeId;
                return `
                    <div class="module-config-card">
                        <div class="module-config-header">
                            <div class="module-config-info">
                                <span class="module-config-name">${this._escapeHtml(th.name || th.id)}</span>
                                <span class="module-config-version">${this._escapeHtml(th.version || '')}</span>
                                ${active ? '<span class="module-config-version" style="background:rgba(34,197,94,0.2);border-color:rgba(34,197,94,0.35);">Aktiv</span>' : ''}
                                ${th.source === 'builtin' ? '<span class="module-config-version">Built-in</span>' : '<span class="module-config-version">Custom</span>'}
                            </div>
                            <div style="display:flex; gap:0.35rem;">
                                ${active ? '' : `<button class="btn btn-primary btn-sm" data-action="activateTheme" data-args="${JSON.stringify([th.id]).replace(/\"/g, '&quot;')}">Aktivieren</button>`}
                                <button class="btn btn-outline btn-sm" data-action="openThemeEditor" data-args="${JSON.stringify([th.id]).replace(/\"/g, '&quot;')}">Editor</button>
                            </div>
                        </div>
                        ${th.description ? `<p class="module-config-desc">${this._escapeHtml(th.description)}</p>` : ''}
                    </div>
                `;
            }).join('');
        },

        async openThemeEditor(themeId) {
            const status = document.getElementById('theme-editor-status');
            try {
                const res = await fetch(`/api/themes/item/${encodeURIComponent(themeId)}`, { cache: 'no-store' });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) throw new Error(data.detail || 'Theme nicht gefunden.');
                const th = data.theme || {};
                const setVal = (id, value) => {
                    const el = document.getElementById(id);
                    if (el) el.value = value || '';
                };
                setVal('theme-editor-id', th.id || '');
                setVal('theme-editor-name', th.name || '');
                setVal('theme-editor-description', th.description || '');
                setVal('theme-editor-author', th.author || '');
                setVal('theme-editor-version', th.version || '1.0.0');
                setVal('theme-editor-preview', th.preview_url || '');
                setVal('theme-editor-tokens-dark', JSON.stringify(th.tokens_dark || {}, null, 2));
                setVal('theme-editor-tokens-light', JSON.stringify(th.tokens_light || {}, null, 2));
                if (status) {
                    status.textContent = `Editor: ${themeId}`;
                    status.className = 'save-status save-ok';
                }
            } catch (e) {
                if (status) {
                    status.textContent = e.message || 'Theme konnte nicht geladen werden.';
                    status.className = 'save-status save-error';
                }
            }
        },

        resetThemeEditor() {
            const setVal = (id, value = '') => {
                const el = document.getElementById(id);
                if (el) el.value = value;
            };
            setVal('theme-editor-id', '');
            setVal('theme-editor-name', '');
            setVal('theme-editor-description', '');
            setVal('theme-editor-author', 'Ninko User');
            setVal('theme-editor-version', '1.0.0');
            setVal('theme-editor-preview', '');
            setVal('theme-editor-tokens-dark', '{}');
            setVal('theme-editor-tokens-light', '{}');
            const st = document.getElementById('theme-editor-status');
            if (st) { st.textContent = ''; st.className = 'save-status'; }
        },

        _readThemeEditorPayload() {
            const get = (id) => document.getElementById(id)?.value?.trim() || '';
            const parseJson = (value, fieldName) => {
                try {
                    if (!value) return {};
                    const parsed = JSON.parse(value);
                    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
                        throw new Error(`${fieldName} muss ein JSON-Objekt sein.`);
                    }
                    return parsed;
                } catch {
                    throw new Error(`${fieldName} enthält ungültiges JSON.`);
                }
            };
            const payload = {
                id: get('theme-editor-id'),
                name: get('theme-editor-name'),
                description: get('theme-editor-description'),
                author: get('theme-editor-author') || 'Ninko User',
                version: get('theme-editor-version') || '1.0.0',
                preview_url: get('theme-editor-preview'),
                tokens_dark: parseJson(get('theme-editor-tokens-dark'), 'Tokens Dark'),
                tokens_light: parseJson(get('theme-editor-tokens-light'), 'Tokens Light'),
            };
            if (!/^[a-zA-Z0-9_-]{1,64}$/.test(payload.id)) {
                throw new Error('Theme ID ungültig. Erlaubt: a-z, A-Z, 0-9, _, -');
            }
            if (!payload.name) throw new Error('Theme Name fehlt.');
            return payload;
        },

        async saveThemeFromEditor() {
            const st = document.getElementById('theme-editor-status');
            if (st) { st.textContent = 'Speichere…'; st.className = 'save-status save-pending'; }
            try {
                const payload = this._readThemeEditorPayload();
                const existing = this._themes.find(t => t.id === payload.id);
                if (existing?.source === 'builtin') {
                    throw new Error('Built-in Themes können nicht überschrieben werden. Bitte neue ID verwenden.');
                }
                const isUpdate = !!existing && existing.source === 'custom';
                const url = isUpdate ? `/api/themes/custom/${encodeURIComponent(payload.id)}` : '/api/themes/custom';
                const method = isUpdate ? 'PUT' : 'POST';
                const res = await fetch(url, {
                    method,
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) throw new Error(data.detail || 'Speichern fehlgeschlagen.');

                await this.loadThemesCatalog();
                await this.openThemeEditor(payload.id);
                showNotification('Theme gespeichert', 'success');
                if (st) { st.textContent = 'Gespeichert'; st.className = 'save-status save-ok'; }
            } catch (e) {
                if (st) { st.textContent = e.message || 'Fehler'; st.className = 'save-status save-error'; }
                showNotification(e.message || 'Theme konnte nicht gespeichert werden.', 'error');
            }
        },

        async duplicateThemeFromEditor() {
            const sourceId = document.getElementById('theme-editor-id')?.value?.trim();
            const st = document.getElementById('theme-editor-status');
            if (!sourceId) {
                if (st) { st.textContent = 'Zum Duplizieren erst ein Theme laden.'; st.className = 'save-status save-error'; }
                return;
            }
            if (st) { st.textContent = 'Dupliziere…'; st.className = 'save-status save-pending'; }
            try {
                const res = await fetch(`/api/themes/custom/${encodeURIComponent(sourceId)}/duplicate`, { method: 'POST' });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) throw new Error(data.detail || 'Duplizieren fehlgeschlagen.');
                await this.loadThemesCatalog();
                await this.openThemeEditor(data.theme_id);
                this._renderThemeCards();
                if (st) { st.textContent = `Dupliziert als ${data.theme_id}`; st.className = 'save-status save-ok'; }
            } catch (e) {
                if (st) { st.textContent = e.message || 'Fehler'; st.className = 'save-status save-error'; }
            }
        },

        async deleteThemeFromEditor() {
            const themeId = document.getElementById('theme-editor-id')?.value?.trim();
            const st = document.getElementById('theme-editor-status');
            if (!themeId) {
                if (st) { st.textContent = 'Kein Theme ausgewählt.'; st.className = 'save-status save-error'; }
                return;
            }
            const existing = this._themes.find(t => t.id === themeId);
            if (existing?.source === 'builtin') {
                if (st) { st.textContent = 'Built-in Themes können nicht gelöscht werden.'; st.className = 'save-status save-error'; }
                return;
            }
            if (!await this.confirm(`Theme "${themeId}" wirklich löschen?`)) return;
            try {
                const res = await fetch(`/api/themes/custom/${encodeURIComponent(themeId)}`, { method: 'DELETE' });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) throw new Error(data.detail || 'Löschen fehlgeschlagen.');
                this.resetThemeEditor();
                await this.loadThemesCatalog();
                await this.loadActiveTheme();
                this.applyActiveThemeTokens();
                this._renderThemeCards();
                if (st) { st.textContent = 'Theme gelöscht'; st.className = 'save-status save-ok'; }
            } catch (e) {
                if (st) { st.textContent = e.message || 'Fehler'; st.className = 'save-status save-error'; }
            }
        },

        /** Kuratierte Liste aller themebaren CSS-Custom-Properties (frontend/style.css :root). */
        _THEMEABLE_TOKENS: [
            '--bg-main', '--bg-tint', '--bg-tint-mid', '--bg-tint-deep', '--bg-accent-1', '--bg-accent-2',
            '--bg-primary', '--bg-secondary', '--bg-tertiary',
            '--bg-panel', '--bg-panel-rgb', '--bg-panel-strong', '--bg-panel-soft', '--bg-panel-soft-rgb',
            '--bg-card', '--bg-card-solid', '--bg-card-solid-rgb', '--bg-sidenav',
            '--bg-chat-user', '--bg-hover', '--bg-active', '--bg-body',
            '--bg-surface', '--bg-surface-rgb',
            '--text-primary', '--text-secondary', '--text-muted',
            '--border-color', '--border-soft', '--border-strong', '--border-active',
            '--shadow-sm', '--shadow-md', '--shadow-lg', '--shadow-glow', '--shadow-card', '--shadow-surface',
            '--primary-color', '--primary-color-rgb', '--primary-gradient', '--primary-gradient-hover',
            '--accent-gradient-soft',
            '--accent-blue', '--accent-blue-rgb', '--accent-blue-soft', '--accent-blue-soft-rgb',
            '--accent-cyan', '--accent-cyan-rgb',
            '--accent-purple', '--accent-green', '--accent-green-rgb',
            '--accent-yellow', '--accent-yellow-rgb', '--accent-orange', '--accent-orange-rgb',
            '--accent-red', '--error-color', '--error-color-rgb',
            '--fg-rgb', '--shadow-rgb',
            '--status-ok', '--status-ok-rgb', '--status-warning', '--status-warning-rgb',
            '--status-danger', '--status-danger-rgb', '--status-pending', '--status-pending-rgb',
            '--status-neutral-rgb',
            '--sg-destructive', '--sg-destructive-rgb', '--sg-state-changing', '--sg-state-changing-rgb',
            '--sg-injection', '--sg-injection-rgb', '--sg-auto', '--sg-auto-rgb',
            '--accent-favorite',
            '--wf-node-trigger', '--wf-node-trigger-rgb', '--wf-node-agent', '--wf-node-agent-rgb',
            '--wf-node-condition', '--wf-node-condition-rgb', '--wf-node-loop', '--wf-node-loop-rgb',
            '--wf-node-variable', '--wf-node-variable-rgb', '--wf-node-end', '--wf-node-end-rgb',
        ],

        /** Schreibt die aktuell wirksamen Werte aller themebaren Tokens als JSON in den Dark-Editor. */
        prefillThemeEditorTokens() {
            const st = document.getElementById('theme-editor-status');
            const textarea = document.getElementById('theme-editor-tokens-dark');
            if (!textarea) return;
            const computed = getComputedStyle(document.documentElement);
            const snapshot = {};
            for (const token of this._THEMEABLE_TOKENS) {
                const value = computed.getPropertyValue(token).trim();
                if (value) snapshot[token] = value;
            }
            textarea.value = JSON.stringify(snapshot, null, 2);
            if (st) { st.textContent = `${Object.keys(snapshot).length} Tokens übernommen`; st.className = 'save-status save-ok'; }
        },

        async loadThemeRepos() {
            const container = document.getElementById('theme-repos-list');
            if (!container) return;
            try {
                const res = await fetch('/api/themes/repos', { cache: 'no-store' });
                if (!res.ok) throw new Error(res.statusText);
                const data = await res.json();
                this._themeRepos = data.repos || [];
                this._renderThemeRepos();
            } catch (e) {
                container.innerHTML = '<p class="text-muted">Theme-Repos konnten nicht geladen werden.</p>';
                console.error('loadThemeRepos:', e);
            }
        },

        _renderThemeRepos() {
            const container = document.getElementById('theme-repos-list');
            if (!container) return;
            if (!this._themeRepos.length) {
                container.innerHTML = '<p class="text-muted">Keine Theme-Repos konfiguriert.</p>';
                return;
            }
            container.innerHTML = this._themeRepos.map((repo) => `
                <div class="module-config-card" id="theme-repo-card-${this._escapeHtml(repo.id)}" style="margin-bottom:0.75rem;">
                    <div class="module-config-header">
                        <div class="module-config-info">
                            <span class="module-config-name">${this._escapeHtml(repo.name)}</span>
                            ${repo.id === 'official' ? '<span class="module-config-version">Official</span>' : ''}
                            <span class="text-muted" style="font-size:0.76rem;">${this._escapeHtml(repo.repo_url)} · ${this._escapeHtml(repo.branch || 'main')}</span>
                        </div>
                        <div style="display:flex; gap:0.35rem;">
                            <button class="btn btn-outline btn-sm" data-action="loadThemesFromRepo" data-args="${JSON.stringify([repo.id]).replace(/\"/g, '&quot;')}">Themes laden</button>
                            ${repo.id === 'official' ? '' : `<button class="btn btn-outline btn-sm" style="color:var(--error-color);" data-action="deleteThemeRepo" data-args="${JSON.stringify([repo.id]).replace(/\"/g, '&quot;')}">Repo löschen</button>`}
                        </div>
                    </div>
                    <div id="theme-repo-themes-${this._escapeHtml(repo.id)}" style="margin-top:0.5rem;"></div>
                </div>
            `).join('');
        },

        async addThemeRepo() {
            const st = document.getElementById('theme-repo-status');
            const get = (id) => document.getElementById(id)?.value?.trim() || '';
            const body = {
                name: get('theme-repo-name'),
                repo_url: get('theme-repo-url'),
                branch: get('theme-repo-branch') || 'main',
                themes_path: get('theme-repo-path') || 'backend/themes',
                github_token: get('theme-repo-token'),
            };
            if (!body.name || !body.repo_url) {
                if (st) { st.textContent = 'Name und GitHub URL sind erforderlich.'; st.className = 'save-status save-error'; }
                return;
            }
            if (st) { st.textContent = 'Füge Repo hinzu…'; st.className = 'save-status save-pending'; }
            try {
                const res = await fetch('/api/themes/repos', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) throw new Error(data.detail || 'Repo konnte nicht hinzugefügt werden.');
                ['theme-repo-name', 'theme-repo-url', 'theme-repo-branch', 'theme-repo-path', 'theme-repo-token'].forEach((id) => {
                    const el = document.getElementById(id);
                    if (el) el.value = '';
                });
                if (st) { st.textContent = 'Repo hinzugefügt'; st.className = 'save-status save-ok'; }
                await this.loadThemeRepos();
            } catch (e) {
                if (st) { st.textContent = e.message || 'Fehler'; st.className = 'save-status save-error'; }
            }
        },

        async deleteThemeRepo(repoId) {
            if (!await this.confirm('Theme-Repo wirklich löschen?')) return;
            try {
                const res = await fetch(`/api/themes/repos/${encodeURIComponent(repoId)}`, { method: 'DELETE' });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) throw new Error(data.detail || 'Repo konnte nicht gelöscht werden.');
                await this.loadThemeRepos();
            } catch (e) {
                showNotification(e.message || 'Repo konnte nicht gelöscht werden.', 'error');
            }
        },

        async loadThemesFromRepo(repoId) {
            const container = document.getElementById(`theme-repo-themes-${repoId}`);
            if (!container) return;
            container.innerHTML = '<p class="text-muted" style="font-size:0.82rem;">Lade Themes…</p>';
            try {
                const res = await fetch(`/api/themes/repos/${encodeURIComponent(repoId)}/themes`);
                const data = await res.json().catch(() => ({}));
                if (!res.ok) throw new Error(data.detail || 'Theme-Liste konnte nicht geladen werden.');
                const themes = data.themes || [];
                if (!themes.length) {
                    container.innerHTML = '<p class="text-muted" style="font-size:0.82rem;">Keine Themes gefunden.</p>';
                    return;
                }
                container.innerHTML = themes.map((th) => `
                    <div class="module-config-card" id="theme-repo-theme-${this._escapeHtml(repoId)}-${this._escapeHtml(th.id)}" style="margin-top:0.5rem;">
                        <div class="module-config-header">
                            <div class="module-config-info">
                                <span class="module-config-name">${this._escapeHtml(th.name || th.id)}</span>
                                <span class="module-config-version">${this._escapeHtml(th.version || '')}</span>
                            </div>
                            <button class="btn btn-primary btn-sm" id="theme-install-btn-${this._escapeHtml(repoId)}-${this._escapeHtml(th.id)}"
                                data-action="installThemeFromRepo" data-args="${JSON.stringify([th.id, repoId]).replace(/\"/g, '&quot;')}">
                                Installieren
                            </button>
                        </div>
                        ${th.description ? `<p class="module-config-desc">${this._escapeHtml(th.description)}</p>` : ''}
                    </div>
                `).join('');
            } catch (e) {
                container.innerHTML = `<p style="font-size:0.82rem;color:var(--error-color);">${this._escapeHtml(e.message || 'Fehler')}</p>`;
            }
        },

        async installThemeFromRepo(themeId, repoId = 'official') {
            const btn = document.getElementById(`theme-install-btn-${repoId}-${themeId}`);
            if (btn) { btn.disabled = true; btn.textContent = 'Installiere…'; }
            try {
                const res = await fetch(`/api/themes/install-from-repo/${encodeURIComponent(themeId)}?repo_id=${encodeURIComponent(repoId)}`, {
                    method: 'POST',
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) throw new Error(data.detail || 'Installation fehlgeschlagen.');
                await this.loadThemesCatalog();
                this._renderThemeCards();
                showNotification(`Theme "${themeId}" installiert`, 'success');
            } catch (e) {
                showNotification(e.message || 'Theme konnte nicht installiert werden.', 'error');
                if (btn) { btn.disabled = false; btn.textContent = 'Installieren'; }
            }
        },
    };

    if (typeof window.Ninko !== 'undefined') {
        Object.assign(window.Ninko, ThemesFeature);
    } else {
        window.ThemesFeature = ThemesFeature;
    }
})();
