// Licium Wiki Dashboard Tab
// Kein ES-Module-Syntax (import/export) — wird als normales Script geladen

const LiciumTab = {
    _connectionId: '',
    _connections: [],

    async init() {
        await this._loadConnections();
        await this.refresh();
    },

    async refresh() {
        await Promise.all([
            this._loadStatus(),
            this._loadLog(),
        ]);
    },

    async _loadConnections() {
        try {
            const resp = await fetch('/api/connections/licium');
            if (!resp.ok) return;
            const data = await resp.json();
            this._connections = data.connections || [];
            this._renderConnectionSelect();
        } catch (e) {
            console.warn('licium: could not load connections', e);
        }
    },

    _renderConnectionSelect() {
        const optionsEl = document.getElementById('licium-conn-options');
        const labelEl = document.querySelector('#licium-conn-select .cl-select-label');
        if (!optionsEl) return;

        optionsEl.innerHTML = '';
        if (this._connections.length === 0) {
            optionsEl.innerHTML = '<div class="cl-select-option" style="opacity:0.5">Keine Verbindungen konfiguriert</div>';
            if (labelEl) labelEl.textContent = 'Keine Verbindungen';
            return;
        }

        this._connections.forEach(conn => {
            const opt = document.createElement('div');
            opt.className = 'cl-select-option' + (conn.id === this._connectionId ? ' selected' : '');
            opt.setAttribute('role', 'option');
            opt.textContent = conn.name + (conn.is_default ? ' (Standard)' : '');
            opt.onclick = () => {
                this._connectionId = conn.id;
                if (labelEl) labelEl.textContent = opt.textContent;
                document.getElementById('licium-conn-select').classList.remove('open');
                this.refresh();
            };
            optionsEl.appendChild(opt);
        });

        const defaultConn = this._connections.find(c => c.is_default) || this._connections[0];
        if (defaultConn && !this._connectionId) {
            this._connectionId = defaultConn.id;
            if (labelEl) labelEl.textContent = defaultConn.name + (defaultConn.is_default ? ' (Standard)' : '');
        }
    },

    toggleSelect() {
        const el = document.getElementById('licium-conn-select');
        if (el) el.classList.toggle('open');
    },

    async _loadStatus() {
        const dot = document.getElementById('licium-dot');
        const statusText = document.getElementById('licium-status-text');
        const noteCount = document.getElementById('licium-note-count');
        const wikiStatus = document.getElementById('licium-wiki-status-badge');
        const version = document.getElementById('licium-version');
        if (!dot) return;

        try {
            const params = this._connectionId ? `?connection_id=${this._connectionId}` : '';
            const resp = await fetch(`/api/licium/status${params}`);
            const data = await resp.json();

            if (data.connected) {
                dot.className = 'licium-status-dot ok';
                if (statusText) statusText.textContent = 'Verbunden';
            } else {
                dot.className = 'licium-status-dot error';
                if (statusText) statusText.textContent = data.detail || 'Fehler';
            }

            if (noteCount) noteCount.textContent = data.note_count ?? '—';
            if (version) version.textContent = data.licium_version || '—';

            if (wikiStatus) {
                if (data.wiki_initialized) {
                    wikiStatus.innerHTML = '<span class="wiki-badge ok">Initialisiert</span>';
                } else {
                    wikiStatus.innerHTML = '<span class="wiki-badge warn">Nicht eingerichtet</span>';
                }
            }
        } catch (e) {
            dot.className = 'licium-status-dot error';
            if (statusText) statusText.textContent = 'Verbindungsfehler';
        }
    },

    async _loadLog() {
        const logEl = document.getElementById('licium-log-entries');
        if (!logEl) return;

        try {
            const params = this._connectionId ? `?connection_id=${this._connectionId}` : '';
            const resp = await fetch(`/api/licium/log${params}`);
            const data = await resp.json();

            if (!data.entries || data.entries.length === 0) {
                logEl.innerHTML = '<p class="empty-state">Noch keine Operationen protokolliert.</p>';
                return;
            }

            logEl.innerHTML = data.entries.slice(-10).reverse().map(entry => {
                const opType = entry.includes('ingest') ? 'ingest'
                    : entry.includes('query') ? 'query'
                    : entry.includes('lint') ? 'lint' : '';
                return `<div class="licium-log-entry ${opType}">${this._escapeHtml(entry)}</div>`;
            }).join('');
        } catch (e) {
            logEl.innerHTML = '<p class="empty-state" style="color:var(--accent-red)">Log konnte nicht geladen werden.</p>';
        }
    },

    async search() {
        const queryEl = document.getElementById('licium-search-query');
        const resultsEl = document.getElementById('licium-search-results');
        if (!queryEl || !resultsEl) return;

        const query = queryEl.value.trim();
        if (!query) return;

        resultsEl.innerHTML = '<p style="color:var(--text-muted);font-size:0.8125rem">Suche läuft…</p>';

        try {
            const resp = await fetch('/api/licium/search', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query, connection_id: this._connectionId }),
            });
            const data = await resp.json();

            if (data.status === 'error') {
                resultsEl.innerHTML = `<p style="color:var(--accent-red);font-size:0.8125rem">${this._escapeHtml(data.detail)}</p>`;
                return;
            }

            const text = data.results || '';
            if (text.includes('Keine relevanten') || text.includes('No relevant')) {
                resultsEl.innerHTML = '<p class="empty-state">Keine relevanten Einträge gefunden.</p>';
                return;
            }

            const blocks = text.split(/\n\n+/).filter(Boolean);
            resultsEl.innerHTML = blocks.map(block => {
                const lines = block.split('\n').filter(Boolean);
                const titleLine = lines.find(l => l.includes('Titel:')) || '';
                const excerptLine = lines.find(l => l.includes('Auszug:')) || '';
                const title = titleLine.replace('Titel:', '').trim();
                const excerpt = excerptLine.replace('Auszug:', '').trim();
                if (!title && !excerpt) return '';
                return `<div class="licium-result-item">
                    <div class="licium-result-title">${this._escapeHtml(title)}</div>
                    <div class="licium-result-excerpt">${this._escapeHtml(excerpt)}</div>
                </div>`;
            }).filter(Boolean).join('') || `<pre style="font-size:0.75rem;color:var(--text-secondary);white-space:pre-wrap">${this._escapeHtml(text)}</pre>`;
        } catch (e) {
            resultsEl.innerHTML = '<p style="color:var(--accent-red);font-size:0.8125rem">Suche fehlgeschlagen.</p>';
        }
    },

    async setupWiki() {
        this._setFeedback('Wiki wird eingerichtet…', 'info');
        try {
            const resp = await fetch('/api/licium/setup?connection_id=' + this._connectionId, { method: 'POST' });
            const data = await resp.json();
            if (data.status === 'ok') {
                this._setFeedback('Wiki-Struktur erfolgreich eingerichtet.', 'ok');
                await this.refresh();
            } else {
                this._setFeedback('Fehler: ' + (data.detail || 'Unbekannter Fehler'), 'error');
            }
        } catch (e) {
            this._setFeedback('Fehler beim Einrichten des Wikis.', 'error');
        }
    },

    async runLint() {
        this._setFeedback('Wiki-Lint läuft…', 'info');
        try {
            const resp = await fetch('/api/licium/lint?connection_id=' + this._connectionId, { method: 'POST' });
            const data = await resp.json();
            if (data.status === 'ok') {
                this._setFeedback('<pre style="white-space:pre-wrap;font-size:0.8rem">' + this._escapeHtml(data.report || '') + '</pre>', 'ok', true);
                await this._loadLog();
            } else {
                this._setFeedback('Fehler: ' + (data.detail || 'Unbekannter Fehler'), 'error');
            }
        } catch (e) {
            this._setFeedback('Fehler beim Lint-Check.', 'error');
        }
    },

    _setFeedback(msg, type, raw) {
        const el = document.getElementById('licium-feedback');
        if (!el) return;
        const color = type === 'ok' ? 'var(--accent-green)' : type === 'error' ? 'var(--accent-red)' : 'var(--text-secondary)';
        el.style.display = 'block';
        el.innerHTML = `<div style="padding:0.75rem;border-radius:6px;background:var(--bg-card);border:1px solid var(--border-color);font-size:0.8125rem;color:${color}">${raw ? msg : this._escapeHtml(msg)}</div>`;
        setTimeout(() => { if (type !== 'ok' || !raw) el.style.display = 'none'; }, 8000);
    },

    _escapeHtml(str) {
        return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    },

    destroy() {},
};

if (typeof Ninko !== 'undefined') {
    Ninko._pluginTabs['licium'] = LiciumTab;
}
