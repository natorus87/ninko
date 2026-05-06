/**
 * GLPI Helpdesk Dashboard Tab – JavaScript
 */
const GlpiTab = {
    API_PREFIX: '/api/glpi',
    pollInterval: null,
    glpiBaseUrl: '',
    currentConnectionId: '',

    esc(s) {
        if (s == null) return '';
        const d = document.createElement('div');
        d.textContent = String(s);
        return d.innerHTML;
    },

    async init() {
        await this.loadConnections();

        if (this.currentConnectionId) {
            await this.loadBaseUrl();
            await this.refresh();
            this.startPolling();
        }

        document.getElementById('glpi-connection-select')
            ?.addEventListener('change', async (e) => {
                this.currentConnectionId = e.target.value;
                await this.loadBaseUrl();
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
            const res = await fetch('/api/connections/glpi');
            const data = await res.json();
            const conns = data.connections || [];
            const select = document.getElementById('glpi-connection-select');
            if (!select) return;

            if (conns.length === 0) {
                select.innerHTML = '<option value="">' + I18n.t('modules.glpi.noConnections') + '</option>';
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
            console.error('GLPI Connections Fehler:', err);
        }
    },

    async refresh() {
        if (!this.currentConnectionId) return;
        await Promise.all([
            this.loadStats(),
            this.loadRecentTickets(),
        ]);
    },

    async loadBaseUrl() {
        try {
            const res = await fetch(`${this.API_PREFIX}/base-url${this.getQueryParams()}`);
            if (!res.ok) throw new Error("Base URL API error");
            const data = await res.json();
            this.glpiBaseUrl = data.base_url || '';
            const link = document.getElementById('glpi-direct-link');
            if (link && this.glpiBaseUrl) {
                link.href = this.glpiBaseUrl;
            }
        } catch (err) {
            console.error('GLPI Base-URL Fehler:', err);
        }
    },

    async loadStats() {
        try {
            const res = await fetch(`${this.API_PREFIX}/stats${this.getQueryParams()}`);
            if (!res.ok) throw new Error("Stats API error");
            const stats = await res.json();
            document.getElementById('glpi-new').textContent = stats.new ?? 0;
            document.getElementById('glpi-processing').textContent = stats.processing ?? 0;
            document.getElementById('glpi-pending').textContent = stats.pending ?? 0;
            document.getElementById('glpi-solved').textContent = stats.solved ?? 0;
            document.getElementById('glpi-closed').textContent = stats.closed ?? 0;
        } catch (err) {
            console.error('GLPI Stats Fehler:', err);
            document.getElementById('glpi-new').textContent = '-';
            document.getElementById('glpi-processing').textContent = '-';
            document.getElementById('glpi-pending').textContent = '-';
            document.getElementById('glpi-solved').textContent = '-';
            document.getElementById('glpi-closed').textContent = '-';
        }
    },

    async loadRecentTickets() {
        const tbody = document.getElementById('glpi-tickets-tbody');
        if (!tbody) return;

        try {
            // Include limit in query params
            const res = await fetch(`${this.API_PREFIX}/tickets${this.getQueryParams({ limit: 10 })}`);
            if (!res.ok) throw new Error("Tickets API error");
            const tickets = await res.json();

            if (!tickets || tickets.length === 0) {
                tbody.innerHTML = '<tr><td colspan="5" class="empty-state">' + I18n.t('modules.glpi.noTickets') + '</td></tr>';
                return;
            }

            tbody.innerHTML = tickets.map(t => {
                const prioClass = this.getPriorityClass(t.priority);
                const statusClass = this.getStatusClass(t.status);
                const dateStr = t.date_creation ? new Date(t.date_creation).toLocaleDateString('de-DE') : '-';

                return `<tr>
                    <td><a href="${this.glpiBaseUrl}/front/ticket.form.php?id=${this.esc(t.id)}" target="_blank">#${this.esc(t.id)}</a></td>
                    <td class="ticket-title">${this.esc(t.title)}</td>
                    <td><span class="priority-badge ${prioClass}">${this.esc(t.priority_name || t.priority)}</span></td>
                    <td><span class="status-badge ${statusClass}">${this.esc(t.status_name || t.status)}</span></td>
                    <td>${this.esc(dateStr)}</td>
                </tr>`;
            }).join('');
        } catch (err) {
            console.error('GLPI Tickets Fehler:', err);
            tbody.innerHTML = '<tr><td colspan="5" class="empty-state text-error">' + I18n.t('modules.glpi.loadError') + '</td></tr>';
        }
    },

    newTicket() {
        // Chat mit vorausgefülltem Prompt öffnen
        const chatInput = document.getElementById('chat-input');
        if (chatInput) {
            chatInput.value = 'Erstelle ein neues Ticket: ';
            chatInput.focus();
        }
        // Zum Chat-Tab wechseln
        if (typeof switchTab === 'function') {
            switchTab('chat');
        }
    },

    getPriorityClass(priority) {
        const map = {
            1: 'prio-very-low', 2: 'prio-low', 3: 'prio-medium',
            4: 'prio-high', 5: 'prio-very-high', 6: 'prio-critical'
        };
        return map[priority] || 'prio-medium';
    },

    getStatusClass(status) {
        const map = {
            1: 'status-new', 2: 'status-processing', 3: 'status-pending',
            4: 'status-pending', 5: 'status-solved', 6: 'status-closed'
        };
        return map[status] || 'status-unknown';
    },

    destroy() {
        this.stopPolling();
    }
};

if (typeof Ninko !== 'undefined') Ninko._pluginTabs['glpi'] = GlpiTab;
