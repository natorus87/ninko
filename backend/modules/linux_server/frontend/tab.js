/**
 * Linux Server Dashboard Tab – JavaScript
 * Globales Objekt: LinuxServerTab (für app.js:getTabObject())
 */
const LinuxServerTab = {
    API_PREFIX: '/api/linux_server',
    pollInterval: null,
    currentConnectionId: '',

    async init() {
        await this.loadConnections();

        if (this.currentConnectionId) {
            await this.refresh();
            this.startPolling();
        }

        document.getElementById('linux-server-connection-select')
            ?.addEventListener('change', async (e) => {
                this.currentConnectionId = e.target.value;
                this.refresh();
            });
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
            const res = await fetch('/api/connections/linux_server');
            const data = await res.json();
            const conns = data.connections || [];
            const select = document.getElementById('linux-server-connection-select');
            if (!select) return;

            if (conns.length === 0) {
                select.innerHTML = '<option value="">Keine Linux Server Verbindungen</option>';
                this.currentConnectionId = '';
                return;
            }

            select.innerHTML = conns.map(c =>
                `<option value="${c.id}" ${c.is_default ? 'selected' : ''}>${c.name} (${c.environment})</option>`
            ).join('');

            const defaultConn = conns.find(c => c.is_default) || conns[0];
            this.currentConnectionId = defaultConn.id;
        } catch (err) {
            console.error('Linux Server Connections Fehler:', err);
        }
    },

    async refresh() {
        if (!this.currentConnectionId) return;
        await Promise.all([
            this.loadSystemInfo(),
            this.loadServices('running'),
            this.loadProcesses('cpu'),
        ]);
    },

    async loadSystemInfo() {
        try {
            const res = await fetch(`${this.API_PREFIX}/info${this.getQueryParams()}`);
            if (!res.ok) throw new Error("Info API error");
            const info = await res.json();
            const container = document.getElementById('linux-server-info');
            if (!container) return;

            if (info.error) {
                container.innerHTML = `<p class="empty-state text-error">${this.escapeHtml(info.error)}</p>`;
                return;
            }

            container.innerHTML = `
                <div class="info-card">
                    <div class="info-label">Hostname</div>
                    <div class="info-value">${this.escapeHtml(info.hostname || '?')}</div>
                </div>
                <div class="info-card">
                    <div class="info-label">OS</div>
                    <div class="info-value">${this.escapeHtml(info.os || '?')}</div>
                </div>
                <div class="info-card">
                    <div class="info-label">Kernel</div>
                    <div class="info-value">${this.escapeHtml(info.kernel || '?')}</div>
                </div>
                <div class="info-card">
                    <div class="info-label">Uptime</div>
                    <div class="info-value">${this.escapeHtml(info.uptime || '?')}</div>
                </div>
                <div class="info-card">
                    <div class="info-label">CPU</div>
                    <div class="info-value">${this.escapeHtml(info.cpu_info || '?')} (${info.cpu_cores || '?'} Kerne)</div>
                </div>
                <div class="info-card">
                    <div class="info-label">RAM</div>
                    <div class="info-value">${this.escapeHtml(info.ram_used || '?')} / ${this.escapeHtml(info.ram_total || '?')} (${info.ram_percent || '?'}%)</div>
                </div>
                <div class="info-card">
                    <div class="info-label">Disk (/)</div>
                    <div class="info-value">${this.escapeHtml(info.disk || '?')}</div>
                </div>
                <div class="info-card">
                    <div class="info-label">Load</div>
                    <div class="info-value">${this.escapeHtml(info.load || '?')}</div>
                </div>
            `;
        } catch (err) {
            console.error('Linux Server Info Fehler:', err);
            const container = document.getElementById('linux-server-info');
            if (container) container.innerHTML = '<p class="empty-state text-error">Fehler beim Laden der System-Info.</p>';
        }
    },

    async loadServices(filter) {
        try {
            const res = await fetch(`${this.API_PREFIX}/services${this.getQueryParams({ status_filter: filter })}`);
            if (!res.ok) throw new Error("Services API error");
            const text = await res.text();
            const container = document.getElementById('linux-server-services');
            if (container) container.textContent = text;
        } catch (err) {
            console.error('Linux Server Services Fehler:', err);
            const container = document.getElementById('linux-server-services');
            if (container) container.textContent = 'Fehler beim Laden der Services.';
        }
    },

    async loadJournal() {
        try {
            const serviceInput = document.getElementById('linux-server-log-service');
            const service = serviceInput ? serviceInput.value : '';
            const params = { lines: 100 };
            if (service) params.service = service;

            const res = await fetch(`${this.API_PREFIX}/journal${this.getQueryParams(params)}`);
            if (!res.ok) throw new Error("Journal API error");
            const text = await res.text();
            const container = document.getElementById('linux-server-journal');
            if (container) container.textContent = text;
        } catch (err) {
            console.error('Linux Server Journal Fehler:', err);
            const container = document.getElementById('linux-server-journal');
            if (container) container.textContent = 'Fehler beim Laden der Logs.';
        }
    },

    async loadProcesses(sortBy) {
        try {
            const res = await fetch(`${this.API_PREFIX}/processes${this.getQueryParams({ sort_by: sortBy, count: 15 })}`);
            if (!res.ok) throw new Error("Processes API error");
            const text = await res.text();
            const container = document.getElementById('linux-server-processes');
            if (container) container.textContent = text;
        } catch (err) {
            console.error('Linux Server Processes Fehler:', err);
            const container = document.getElementById('linux-server-processes');
            if (container) container.textContent = 'Fehler beim Laden der Prozesse.';
        }
    },

    escapeHtml(str) {
        if (!str) return '';
        const div = document.createElement('div');
        div.textContent = String(str);
        return div.innerHTML;
    },

    destroy() {
        this.stopPolling();
    }
};
