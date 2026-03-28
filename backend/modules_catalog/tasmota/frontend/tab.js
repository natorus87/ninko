/**
 * Tasmota Dashboard Tab – JavaScript
 *
 * WICHTIG:
 * - Kein import/export (ES Modules) — Datei wird per <script>-Tag ohne type="module" geladen.
 * - Das globale Objekt (TasmotaTab) MUSS existieren, damit app.js:getTabObject()
 *   es findet und init() aufrufen kann.
 * - Event-Delegation statt inline-onclick in HTML-Strings (data-action Pattern).
 * - Kein nativer <select> — cl-select div-Pattern für Dark/Light-Theme-Kompatibilität.
 */
const TasmotaTab = {
    API_PREFIX: '/api/tasmota',
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

    _setupEvents() {
        document.getElementById('tasmota-tab-content')
            ?.addEventListener('click', (e) => {
                const action = e.target.closest('[data-action]')?.dataset.action;
                if (action === 'tasmota-refresh') this.refresh();
            });
    },

    toggleSelect(selectId) {
        const el = document.getElementById(selectId);
        if (!el) return;
        const isOpen = el.classList.contains('open');
        document.querySelectorAll('#tasmota-tab-content .cl-select.open')
            .forEach(s => s.classList.remove('open'));
        if (!isOpen) el.classList.add('open');
    },

    _setupClickOutside() {
        document.addEventListener('click', (e) => {
            if (!e.target.closest('#tasmota-tab-content .cl-select')) {
                document.querySelectorAll('#tasmota-tab-content .cl-select.open')
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
        this.pollInterval = setInterval(() => this.refresh(), 30000);
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
            const res = await fetch('/api/connections/tasmota');
            const data = await res.json();
            const conns = data.connections || [];

            if (conns.length === 0) {
                this._setSelectLabel('tasmota-conn-select', 'Keine Verbindungen');
                this.currentConnectionId = '';
                return;
            }

            const defaultConn = conns.find(c => c.is_default) || conns[0];
            this.currentConnectionId = defaultConn.id;

            this._setSelectOptions(
                'tasmota-conn-options',
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
            this._setSelectLabel('tasmota-conn-select', `${defaultConn.name} (${defaultConn.environment})`);
        } catch (err) {
            console.error('Tasmota Connections Fehler:', err);
            this._setSelectLabel('tasmota-conn-select', 'Fehler beim Laden');
        }
    },

    async refresh() {
        if (!this.currentConnectionId) return;
        try {
            const [statusRes, sensorsRes, powerRes] = await Promise.all([
                fetch(`${this.API_PREFIX}/status${this.getQueryParams()}`),
                fetch(`${this.API_PREFIX}/sensors${this.getQueryParams()}`),
                fetch(`${this.API_PREFIX}/power${this.getQueryParams()}`),
            ]);

            const statusData = await statusRes.json();
            const sensorsData = await sensorsRes.json();
            const powerData = await powerRes.json();

            const container = document.getElementById('tasmota-content');
            if (!container) return;

            const status = statusData.data || {};
            const sensors = sensorsData.data || {};
            const power = powerData.data || {};

            const formatUptime = (secs) => {
                const d = Math.floor(secs / 86400);
                const h = Math.floor((secs % 86400) / 3600);
                const m = Math.floor((secs % 3600) / 60);
                return `${d}d ${h}h ${m}m`;
            };

            const rssiClass = (rssi) => rssi > -50 ? 'power-on' : rssi > -70 ? '' : 'power-off';

            container.innerHTML = `
                <div class="tasmota-card">
                    <h4>⚡ Allgemein</h4>
                    <div class="tasmota-stat">
                        <span class="tasmota-stat-label">Hostname</span>
                        <span class="tasmota-stat-value">${status.hostname || '-'}</span>
                    </div>
                    <div class="tasmota-stat">
                        <span class="tasmota-stat-label">IP-Adresse</span>
                        <span class="tasmota-stat-value">${status.ip_address || '-'}</span>
                    </div>
                    <div class="tasmota-stat">
                        <span class="tasmota-stat-label">Modell</span>
                        <span class="tasmota-stat-value">${status.model || '-'}</span>
                    </div>
                    <div class="tasmota-stat">
                        <span class="tasmota-stat-label">Firmware</span>
                        <span class="tasmota-stat-value">${status.firmware || '-'}</span>
                    </div>
                    <div class="tasmota-stat">
                        <span class="tasmota-stat-label">Uptime</span>
                        <span class="tasmota-stat-value">${formatUptime(status.uptime)}</span>
                    </div>
                    <div class="tasmota-stat">
                        <span class="tasmota-stat-label">WLAN RSSI</span>
                        <span class="tasmota-stat-value ${rssiClass(status.wifi_rssi)}">${status.wifi_rssi || 0} dBm</span>
                    </div>
                </div>

                <div class="tasmota-card">
                    <h4>🔌 Power</h4>
                    <div class="tasmota-stat">
                        <span class="tasmota-stat-label">Relais 1</span>
                        <span class="tasmota-stat-value ${power.power1 ? 'power-on' : 'power-off'}">${power.power1 ? 'AN' : 'AUS'}</span>
                    </div>
                </div>

                <div class="tasmota-card">
                    <h4>🌡️ Sensoren</h4>
                    <div class="tasmota-stat">
                        <span class="tasmota-stat-label">Temperatur</span>
                        <span class="tasmota-stat-value">${sensors.temperature != null ? sensors.temperature + ' °C' : '-'}</span>
                    </div>
                    <div class="tasmota-stat">
                        <span class="tasmota-stat-label">Feuchtigkeit</span>
                        <span class="tasmota-stat-value">${sensors.humidity != null ? sensors.humidity + ' %' : '-'}</span>
                    </div>
                    <div class="tasmota-stat">
                        <span class="tasmota-stat-label">Luftdruck</span>
                        <span class="tasmota-stat-value">${sensors.pressure != null ? sensors.pressure + ' hPa' : '-'}</span>
                    </div>
                    <div class="tasmota-stat">
                        <span class="tasmota-stat-label">Leistung</span>
                        <span class="tasmota-stat-value">${sensors.power != null ? sensors.power + ' W' : '-'}</span>
                    </div>
                    <div class="tasmota-stat">
                        <span class="tasmota-stat-label">Strom</span>
                        <span class="tasmota-stat-value">${sensors.current != null ? sensors.current + ' A' : '-'}</span>
                    </div>
                    <div class="tasmota-stat">
                        <span class="tasmota-stat-label">Spannung</span>
                        <span class="tasmota-stat-value">${sensors.voltage != null ? sensors.voltage + ' V' : '-'}</span>
                    </div>
                    <div class="tasmota-stat">
                        <span class="tasmota-stat-label">Energie heute</span>
                        <span class="tasmota-stat-value">${sensors.energy_today != null ? sensors.energy_today + ' Wh' : '-'}</span>
                    </div>
                </div>
            `;
        } catch (err) {
            console.error('Tasmota Refresh Fehler:', err);
            const container = document.getElementById('tasmota-content');
            if (container) container.innerHTML = '<p class="empty-state text-error">Fehler beim Laden.</p>';
        }
    },

    destroy() {
        this.stopPolling();
    },
};
