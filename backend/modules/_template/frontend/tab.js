/**
 * Template Dashboard Tab – JavaScript
 *
 * WICHTIG:
 * - Kein import/export (ES Modules) — Datei wird per <script>-Tag ohne type="module" geladen.
 * - Das globale Objekt (TemplateTab) MUSS existieren, damit app.js:getTabObject()
 *   es findet und init() aufrufen kann.
 * - Eintrag in app.js:getTabObject() hinzufügen:
 *     'template': typeof TemplateTab !== 'undefined' ? TemplateTab : null,
 * - Event-Delegation statt inline-onclick in HTML-Strings (data-action Pattern).
 * - Kein nativer <select> — cl-select div-Pattern für Dark/Light-Theme-Kompatibilität.
 */
const TemplateTab = {
    API_PREFIX: '/api/template',
    pollInterval: null,
    currentConnectionId: '',

    async init() {
        this._setupEvents();
        this._setupClickOutside();
        await this.loadConnections();

        if (this.currentConnectionId) {
            await this.refresh();
        }
    },

    // ── Event-Delegation ───────────────────────────────────────

    _setupEvents() {
        document.getElementById('template-tab-content')
            ?.addEventListener('click', (e) => {
                const action = e.target.closest('[data-action]')?.dataset.action;
                if (action === 'template-refresh') this.refresh();
            });
    },

    // ── Custom Select ──────────────────────────────────────────

    toggleSelect(selectId) {
        const el = document.getElementById(selectId);
        if (!el) return;
        const isOpen = el.classList.contains('open');
        document.querySelectorAll('#template-tab-content .cl-select.open')
            .forEach(s => s.classList.remove('open'));
        if (!isOpen) el.classList.add('open');
    },

    _setupClickOutside() {
        document.addEventListener('click', (e) => {
            if (!e.target.closest('#template-tab-content .cl-select')) {
                document.querySelectorAll('#template-tab-content .cl-select.open')
                    .forEach(s => s.classList.remove('open'));
            }
        });
    },

    _setSelectOptions(optionsContainerId, options, onSelect) {
        const container = document.getElementById(optionsContainerId);
        if (!container) return;
        container.innerHTML = options.map(o =>
            `<div class="cl-select-option${o.selected ? ' selected' : ''}" data-value="${o.value}">${o.label}</div>`
        ).join('');
        container.querySelectorAll('.cl-select-option').forEach(opt => {
            opt.addEventListener('click', () => {
                container.querySelectorAll('.cl-select-option').forEach(o => o.classList.remove('selected'));
                opt.classList.add('selected');
                const wrapper = container.closest('.cl-select');
                if (wrapper) {
                    const lbl = wrapper.querySelector('.cl-select-label');
                    if (lbl) lbl.textContent = opt.textContent;
                    wrapper.classList.remove('open');
                }
                onSelect(opt.dataset.value);
            });
        });
    },

    _setSelectLabel(wrapperId, label) {
        const el = document.getElementById(wrapperId);
        if (el) {
            const lbl = el.querySelector('.cl-select-label');
            if (lbl) lbl.textContent = label;
        }
    },

    // ── Polling ────────────────────────────────────────────────

    startPolling() {
        this.stopPolling();
        this.pollInterval = setInterval(() => this.refresh(), 30000);
    },

    stopPolling() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }
    },

    // ── Query-Helper ───────────────────────────────────────────

    getQueryParams(additional = {}) {
        const params = new URLSearchParams();
        if (this.currentConnectionId) {
            params.append('connection_id', this.currentConnectionId);
        }
        for (const [k, v] of Object.entries(additional)) {
            params.append(k, String(v));
        }
        const str = params.toString();
        return str ? `?${str}` : '';
    },

    // ── Verbindungen laden ──────────────────────────────────────

    async loadConnections() {
        try {
            const res = await fetch('/api/connections/template');
            const data = await res.json();
            const conns = data.connections || [];

            if (conns.length === 0) {
                this._setSelectLabel('template-conn-select', 'Keine Verbindungen');
                this.currentConnectionId = '';
                return;
            }

            const defaultConn = conns.find(c => c.is_default) || conns[0];
            this.currentConnectionId = defaultConn.id;

            this._setSelectOptions(
                'template-conn-options',
                conns.map(c => ({
                    value: c.id,
                    label: `${c.name} (${c.environment})`,
                    selected: c.id === defaultConn.id,
                })),
                (id) => {
                    this.currentConnectionId = id;
                    this.refresh();
                }
            );
            this._setSelectLabel('template-conn-select', `${defaultConn.name} (${defaultConn.environment})`);
        } catch (err) {
            console.error('Template Connections Fehler:', err);
            this._setSelectLabel('template-conn-select', 'Fehler beim Laden');
        }
    },

    // ── Daten laden ────────────────────────────────────────────

    async refresh() {
        if (!this.currentConnectionId) return;
        try {
            const res = await fetch(`${this.API_PREFIX}/status${this.getQueryParams()}`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            const container = document.getElementById('template-content');
            if (!container) return;

            container.innerHTML = `<pre>${JSON.stringify(data, null, 2)}</pre>`;
        } catch (err) {
            console.error('Template Refresh Fehler:', err);
            const container = document.getElementById('template-content');
            if (container) container.innerHTML = '<p class="empty-state text-error">Fehler beim Laden.</p>';
        }
    },

    destroy() {
        this.stopPolling();
    },
};
