/**
 * Checkmk Dashboard Tab – JavaScript
 */
const CheckmkTab = {
    API_PREFIX: '/api/modules/checkmk',
    pollInterval: null,
    currentConnectionId: '',

    async init() {
        this._setupEvents();
        this._setupClickOutside();
        await this.loadConnections();

        if (this.currentConnectionId) {
            await this.refresh();
            this.startPolling();
        }
    },

    _setupEvents() {
        document.getElementById('checkmk-tab-content')
            ?.addEventListener('click', (e) => {
                const action = e.target.closest('[data-action]')?.dataset.action;
                if (action === 'checkmk-refresh') this.refresh();
            });
    },

    toggleSelect(selectId) {
        const el = document.getElementById(selectId);
        if (!el) return;
        const isOpen = el.classList.contains('open');
        document.querySelectorAll('#checkmk-tab-content .cl-select.open')
            .forEach(s => s.classList.remove('open'));
        if (!isOpen) el.classList.add('open');
    },

    _setupClickOutside() {
        document.addEventListener('click', (e) => {
            if (!e.target.closest('#checkmk-tab-content .cl-select')) {
                document.querySelectorAll('#checkmk-tab-content .cl-select.open')
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

    startPolling() {
        this.stopPolling();
        this.pollInterval = setInterval(() => this.refresh(), 60000);
    },

    stopPolling() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }
    },

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

    async loadConnections() {
        try {
            const res = await fetch('/api/connections/checkmk');
            const data = await res.json();
            const conns = data.connections || [];

            if (conns.length === 0) {
                this._setSelectLabel('checkmk-conn-select', 'Keine Verbindungen');
                this.currentConnectionId = '';
                return;
            }

            const defaultConn = conns.find(c => c.is_default) || conns[0];
            this.currentConnectionId = defaultConn.id;

            this._setSelectOptions(
                'checkmk-conn-options',
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
            this._setSelectLabel('checkmk-conn-select', `${defaultConn.name} (${defaultConn.environment})`);
        } catch (err) {
            console.error('Checkmk Connections Fehler:', err);
            this._setSelectLabel('checkmk-conn-select', 'Fehler beim Laden');
        }
    },

    async refresh() {
        if (!this.currentConnectionId) return;
        try {
            const res = await fetch(`${this.API_PREFIX}/status${this.getQueryParams()}`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            this._render(data);
        } catch (err) {
            console.error('Checkmk Refresh Fehler:', err);
            const alertsDiv = document.getElementById('checkmk-alerts');
            if (alertsDiv) alertsDiv.innerHTML = '<p class="empty-state text-error">Fehler beim Laden.</p>';
        }
    },

    _render(data) {
        const hostsEl = document.getElementById('checkmk-host-count');
        const servicesEl = document.getElementById('checkmk-service-count');
        const critEl = document.getElementById('checkmk-crit-count');
        const warnEl = document.getElementById('checkmk-warn-count');
        const alertsEl = document.getElementById('checkmk-alerts');

        if (hostsEl) {
            const hostsText = data.hosts || "0";
            const match = hostsText.match(/^Hosts \((\d+)\)/);
            hostsEl.textContent = match ? match[1] : '-';
        }

        if (servicesEl) {
            const servicesText = data.services || "0";
            const match = servicesText.match(/^Services \((\d+)\)/);
            servicesEl.textContent = match ? match[1] : '-';
        }

        let critCount = 0;
        let warnCount = 0;

        if (critEl) {
            const critMatch = (data.alerts || "").match(/🔴 CRIT/g);
            critCount = critMatch ? critMatch.length : 0;
            critEl.textContent = critCount;
        }

        if (warnEl) {
            const warnMatch = (data.alerts || "").match(/⚠️ WARN/g);
            warnCount = warnMatch ? warnMatch.length : 0;
            warnEl.textContent = warnCount;
        }

        if (alertsEl) {
            const alertsText = data.alerts || "";
            if (alertsText.includes("Keine aktuellen Probleme")) {
                alertsEl.innerHTML = '<p class="empty-state" style="color:var(--accent-green)">✓ Keine aktuellen Probleme</p>';
            } else if (alertsText) {
                const lines = alertsText.split('\n').slice(1);
                alertsEl.innerHTML = lines.map(line => {
                    const isCrit = line.includes('🔴 CRIT');
                    const isWarn = line.includes('⚠️ WARN');
                    const cls = isCrit ? 'alert-crit' : (isWarn ? 'alert-warn' : '');
                    return `<div class="alert-item ${cls}">${line}</div>`;
                }).join('');
            } else {
                alertsEl.innerHTML = '<p class="empty-state">Keine Daten verfügbar</p>';
            }
        }
    },

    destroy() {
        this.stopPolling();
    },
};
