/**
 * OPNsense Dashboard Tab – JavaScript
 *
 * WICHTIG:
 * - Kein import/export (ES Modules) — Datei wird per <script>-Tag ohne type="module" geladen.
 * - Das globale Objekt (OPNsenseTab) MUSS existieren, damit app.js:getTabObject()
 *   es findet und init() aufrufen kann.
 * - Event-Delegation statt inline-onclick in HTML-Strings (data-action Pattern).
 * - Kein nativer <select> — cl-select div-Pattern für Dark/Light-Theme-Kompatibilität.
 */
const OPNsenseTab = {
    API_PREFIX: '/api/opnsense',
    pollInterval: null,
    currentConnectionId: '',

    esc(s) {
        if (s == null) return '';
        const d = document.createElement('div');
        d.textContent = String(s);
        return d.innerHTML;
    },

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
        document.getElementById('opnsense-tab-content')
            ?.addEventListener('click', (e) => {
                const action = e.target.closest('[data-action]')?.dataset.action;
                if (action === 'opnsense-refresh') this.refresh();
            });
    },

    toggleSelect(selectId) {
        const el = document.getElementById(selectId);
        if (!el) return;
        const isOpen = el.classList.contains('open');
        document.querySelectorAll('#opnsense-tab-content .cl-select.open')
            .forEach(s => s.classList.remove('open'));
        if (!isOpen) el.classList.add('open');
    },

    _setupClickOutside() {
        document.addEventListener('click', (e) => {
            if (!e.target.closest('#opnsense-tab-content .cl-select')) {
                document.querySelectorAll('#opnsense-tab-content .cl-select.open')
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
            const res = await fetch('/api/connections/opnsense');
            const data = await res.json();
            const conns = data.connections || [];

            if (conns.length === 0) {
                this._setSelectLabel('opnsense-conn-select', I18n.t('modules.opnsense.noConnections'));
                this.currentConnectionId = '';
                return;
            }

            const defaultConn = conns.find(c => c.is_default) || conns[0];
            this.currentConnectionId = defaultConn.id;

            this._setSelectOptions(
                'opnsense-conn-options',
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
            this._setSelectLabel('opnsense-conn-select', `${defaultConn.name} (${defaultConn.environment})`);
        } catch (err) {
            console.error('OPNsense Connections Fehler:', err);
            this._setSelectLabel('opnsense-conn-select', 'Fehler beim Laden');
        }
    },

    async refresh() {
        if (!this.currentConnectionId) return;
        try {
            const [statusRes, interfacesRes, servicesRes] = await Promise.all([
                fetch(`${this.API_PREFIX}/status${this.getQueryParams()}`),
                fetch(`${this.API_PREFIX}/interfaces${this.getQueryParams()}`),
                fetch(`${this.API_PREFIX}/services${this.getQueryParams()}`),
            ]);

            const statusData = await statusRes.json();
            const interfacesData = await interfacesRes.json();
            const servicesData = await servicesRes.json();

            const container = document.getElementById('opnsense-content');
            if (!container) return;

            // Prüfe auf API-Fehler
if (statusData.status === 'error') {
                container.innerHTML = `<p class="empty-state text-error">Status Fehler: ${this.esc(statusData.detail) || 'Unbekannter Fehler'}</p>`;
                return;
            }

            const status = statusData.data || {};
            const interfaces = interfacesData.data || [];
            const services = servicesData.data || [];

            if (status.error) {
                container.innerHTML = `<p class="empty-state text-error">OPNsense Fehler: ${this.esc(status.error)}</p>`;
                return;
            }

            const status = statusData.data || {};
            const interfaces = interfacesData.data || [];
            const services = servicesData.data || [];

            // Prüfe auf Tool-Fehler in den Daten
            if (status.error) {
                container.innerHTML = `<p class="empty-state text-error">OPNsense Fehler: ${esc(status.error)}</p>`;
                return;
            }

            const getStatusClass = (st) => {
                if (st === 'online' || st === 'up') return 'status-online';
                if (st === 'down' || st === 'offline') return 'status-offline';
                return 'status-warning';
            };

container.innerHTML = `
                <div class="opnsense-card">
                    <h4>🖥️ System</h4>
                    <div class="opnsense-stat">
                        <span class="opnsense-stat-label">Version</span>
                        <span class="opnsense-stat-value">${this.esc(status.version) || '-'}</span>
                    </div>
                    <div class="opnsense-stat">
                        <span class="opnsense-stat-label">Firmware</span>
                        <span class="opnsense-stat-value">${this.esc(status.firmware) || '-'}</span>
                    </div>
                    <div class="opnsense-stat">
                        <span class="opnsense-stat-label">Uptime</span>
                        <span class="opnsense-stat-value">${this.esc(status.uptime) || '-'}</span>
                    </div>
                    <div class="opnsense-stat">
                        <span class="opnsense-stat-label">Load (1m)</span>
                        <span class="opnsense-stat-value">${status.cpu !== undefined ? status.cpu.toFixed(2) : '-'}</span>
                    </div>
                    <div class="opnsense-stat">
                        <span class="opnsense-stat-label">Memory</span>
                        <span class="opnsense-stat-value">${this.esc(status.memory) || 0}%</span>
                    </div>
                    <div class="opnsense-stat">
                        <span class="opnsense-stat-label">Disk</span>
                        <span class="opnsense-stat-value">${this.esc(status.disk) || 0}%</span>
                    </div>
                </div>

                <div class="opnsense-card">
                    <h4>🌐 Interfaces (${interfaces.length})</h4>
                    ${interfaces.slice(0, 5).map(iface => `
                        <div class="opnsense-stat">
                            <span class="opnsense-stat-label">${this.esc(iface.descr) || this.esc(iface.name)}</span>
                            <span class="opnsense-stat-value ${getStatusClass(iface.status)}">${this.esc(iface.ipaddr) || '-'} ${iface.status ? '(' + this.esc(iface.status) + ')' : ''}</span>
                        </div>
                    `).join('')}
                    ${interfaces.length > 5 ? `<div class="opnsense-stat"><span class="opnsense-stat-label">...</span><span class="opnsense-stat-value">+${interfaces.length - 5} weitere</span></div>` : ''}
                </div>

                <div class="opnsense-card">
                    <h4>⚙️ Services (${services.length})</h4>
                    ${services.slice(0, 8).map(svc => `
                        <div class="opnsense-stat">
                            <span class="opnsense-stat-label">${this.esc(svc.description) || this.esc(svc.name)}</span>
                            <span class="opnsense-stat-value ${svc.running ? 'status-online' : 'status-offline'}">${svc.running ? 'Aktiv' : 'Inaktiv'}</span>
                        </div>
                    `).join('')}
                </div>

                <div class="opnsense-card">
                    <h4>🔧 Write-Operationen</h4>
                    <div class="opnsense-stat">
                        <span class="opnsense-stat-label">Firewall-Regel erstellen</span>
                        <span class="opnsense-stat-value"><button class="btn btn-sm" onclick="OPNsenseTab.showCreateRuleDialog()">➕ Regel</button></span>
                    </div>
                    <div class="opnsense-stat">
                        <span class="opnsense-stat-label">NAT-Regel erstellen</span>
                        <span class="opnsense-stat-value"><button class="btn btn-sm" onclick="OPNsenseTab.showCreateNatRuleDialog()">➕ NAT</button></span>
                    </div>
                </div>
            `;
        } catch (err) {
            console.error('OPNsense Refresh Fehler:', err);
            const container = document.getElementById('opnsense-content');
            if (container) container.innerHTML = '<p class="empty-state text-error">' + I18n.t('modules.opnsense.loadError') + '</p>';
        }
    },

    showCreateRuleDialog() {
        const msg = `Ich möchte eine Firewall-Regel erstellen. Bitte frage mich nach den Details (Interface, Aktion, Quelle, Ziel, Protokoll, Beschreibung).`;
        Ninko.sendMessage(msg, 'opnsense');
    },

    showCreateNatRuleDialog() {
        const msg = `Ich möchte eine NAT-Regel erstellen. Bitte frage mich nach den Details (Interface, Protokoll, Quelle, Ziel, Target, Port, Beschreibung).`;
        Ninko.sendMessage(msg, 'opnsense');
    },

    destroy() {
        this.stopPolling();
    },
};

if (typeof Ninko !== 'undefined') Ninko._pluginTabs['opnsense'] = OPNsenseTab;
