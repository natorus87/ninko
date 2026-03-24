/**
 * Pi-hole Dashboard Tab – JavaScript
 */
const PiholeTab = {
    API_PREFIX: '/api/pihole',
    pollInterval: null,
    blockingEnabled: true,
    currentConnectionId: '',

    async init() {
        await this.loadConnections();

        if (this.currentConnectionId) {
            await this.refresh();
            this.startPolling();
        }

        document.getElementById('pihole-connection-select')
            ?.addEventListener('change', async (e) => {
                this.currentConnectionId = e.target.value;
                this.refresh();
            });
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
            const res = await fetch('/api/connections/pihole');
            const data = await res.json();
            const conns = data.connections || [];
            const select = document.getElementById('pihole-connection-select');
            if (!select) return;

            if (conns.length === 0) {
                select.innerHTML = '<option value="">Keine Pi-hole Verbindungen</option>';
                this.currentConnectionId = '';
                return;
            }

            select.innerHTML = conns.map(c =>
                `<option value="${c.id}" ${c.is_default ? 'selected' : ''}>${c.name} (${c.environment})</option>`
            ).join('');

            // Set initial connection
            const defaultConn = conns.find(c => c.is_default) || conns[0];
            this.currentConnectionId = defaultConn.id;
        } catch (err) {
            console.error('Pi-hole Connections Fehler:', err);
        }
    },

    async refresh() {
        if (!this.currentConnectionId) return;
        await Promise.all([
            this.loadSummary(),
            this.loadTopDomains(),
            this.loadQueries(),
        ]);
    },

    async loadSummary() {
        try {
            const res = await fetch(`${this.API_PREFIX}/summary${this.getQueryParams()}`);
            if (!res.ok) throw new Error("Summary API error");
            const data = await res.json();

            document.getElementById('pihole-total-queries').textContent =
                (data.dns_queries_today ?? 0).toLocaleString('de-DE');
            document.getElementById('pihole-blocked').textContent =
                (data.ads_blocked_today ?? 0).toLocaleString('de-DE');
            document.getElementById('pihole-percent').textContent =
                (data.ads_percentage_today ?? 0) + '%';
            document.getElementById('pihole-domains-blocked').textContent =
                (data.domains_blocked ?? 0).toLocaleString('de-DE');
            document.getElementById('pihole-clients').textContent =
                data.unique_clients ?? '-';

            // Blocking Status
            this.blockingEnabled = data.status === 'enabled';
            const badge = document.getElementById('pihole-blocking-status');
            if (badge) {
                badge.textContent = this.blockingEnabled ? '🟢 Aktiv' : '🔴 Deaktiviert';
                badge.className = `pihole-blocking-badge ${this.blockingEnabled ? 'blocking-on' : 'blocking-off'}`;
            }
        } catch (err) {
            console.error('Pi-hole Summary Fehler:', err);
            this._resetSummary();
        }
    },

    _resetSummary() {
        document.getElementById('pihole-total-queries').textContent = '-';
        document.getElementById('pihole-blocked').textContent = '-';
        document.getElementById('pihole-percent').textContent = '-';
        document.getElementById('pihole-domains-blocked').textContent = '-';
        document.getElementById('pihole-clients').textContent = '-';
        const badge = document.getElementById('pihole-blocking-status');
        if (badge) {
            badge.textContent = '—';
            badge.className = 'pihole-blocking-badge blockoff-off';
        }
    },

    async loadTopDomains() {
        const permitted = document.getElementById('pihole-top-permitted');
        const blocked = document.getElementById('pihole-top-blocked');

        try {
            const res = await fetch(`${this.API_PREFIX}/top-domains${this.getQueryParams({ count: 10 })}`);
            if (!res.ok) throw new Error("Top Domains API error");
            const data = await res.json();

            if (permitted) {
                const items = Object.entries(data.top_permitted || {});
                permitted.innerHTML = items.length === 0
                    ? '<p class="empty-state">Keine Daten</p>'
                    : items.map(([domain, count]) =>
                        `<div class="top-item">
                            <span class="top-domain">${domain}</span>
                            <span class="top-count">${count.toLocaleString('de-DE')}</span>
                        </div>`
                    ).join('');
            }

            if (blocked) {
                const items = Object.entries(data.top_blocked || {});
                blocked.innerHTML = items.length === 0
                    ? '<p class="empty-state">Keine Daten</p>'
                    : items.map(([domain, count]) =>
                        `<div class="top-item">
                            <span class="top-domain">${domain}</span>
                            <span class="top-count">${count.toLocaleString('de-DE')}</span>
                        </div>`
                    ).join('');
            }
        } catch (err) {
            console.error('Pi-hole Top Domains Fehler:', err);
            if (permitted) permitted.innerHTML = '<p class="empty-state text-error">Fehler</p>';
            if (blocked) blocked.innerHTML = '<p class="empty-state text-error">Fehler</p>';
        }
    },

    async loadQueries() {
        const tbody = document.getElementById('pihole-queries-tbody');
        if (!tbody) return;

        try {
            const res = await fetch(`${this.API_PREFIX}/queries${this.getQueryParams({ count: 50 })}`);
            if (!res.ok) throw new Error("Queries API error");
            const queries = await res.json();

            if (!queries || queries.length === 0) {
                tbody.innerHTML = '<tr><td colspan="5" class="empty-state">Keine Queries.</td></tr>';
                return;
            }

            tbody.innerHTML = queries.map(q => {
                const statusClass = this.getQueryStatusClass(q.status);
                return `<tr>
                    <td class="pod-name">${q.domain}</td>
                    <td>${q.client}</td>
                    <td>${q.type}</td>
                    <td><span class="status-badge ${statusClass}">${q.status}</span></td>
                    <td>${q.duration_ms ? q.duration_ms.toFixed(1) : '-'}</td>
                </tr>`;
            }).join('');
        } catch (err) {
            console.error('Pi-hole Queries Fehler:', err);
            tbody.innerHTML = '<tr><td colspan="5" class="empty-state text-error">Fehler beim Laden der Queries.</td></tr>';
        }
    },

    async toggleBlocking() {
        const newState = !this.blockingEnabled;
        const label = newState ? 'aktivieren' : 'deaktivieren';

        if (!newState && !confirm('DNS-Blocking wirklich deaktivieren?')) return;

        try {
            const res = await fetch(`${this.API_PREFIX}/blocking${this.getQueryParams({ enable: newState })}`, { method: 'POST' });
            const data = await res.json();
            if (res.ok) {
                showNotification(data.message || `Blocking ${label}`, newState ? 'success' : 'warning');
            } else {
                showNotification('Fehler: ' + (data.detail || 'Unbekannt'), 'error');
            }
            setTimeout(() => this.loadSummary(), 1000);
        } catch (err) {
            showNotification('Fehler beim Umschalten des Blockings', 'error');
        }
    },

    getQueryStatusClass(status) {
        if (!status) return 'status-unknown';
        const s = status.toLowerCase();
        if (s.includes('block') || s.includes('denied') || s.includes('gravity')) return 'status-error';
        if (s.includes('forward') || s.includes('answered')) return 'status-ok';
        if (s.includes('cache')) return 'status-warning';
        return 'status-unknown';
    },

    destroy() {
        this.stopPolling();
    }
};
