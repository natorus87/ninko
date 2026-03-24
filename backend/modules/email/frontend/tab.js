/**
 * Kumio Frontend Script für das Email Modul (Dashboard Dashboard)
 */
const EmailTab = {
    API_PREFIX: '/api/email',
    currentConnectionId: '',

    async init() {
        await this.loadConnections();

        if (this.currentConnectionId) {
            this.refresh();
        }

        document.getElementById('email-connection-select')
            ?.addEventListener('change', (e) => {
                this.currentConnectionId = e.target.value;
                this.refresh();
            });
    },

    async loadConnections() {
        try {
            const res = await fetch('/api/connections/email');
            const data = await res.json();
            const conns = data.connections || [];
            const select = document.getElementById('email-connection-select');
            if (!select) return;

            if (conns.length === 0) {
                select.innerHTML = '<option value="">Keine Email Verbindungen</option>';
                this.currentConnectionId = '';
                this.updateStatusUI('warning', 'Keine Verbindung konfiguriert', 'Bitte in den Zentraleinstellungen (Zahnrad) hinzufügen.');
                return;
            }

            select.innerHTML = conns.map(c =>
                `<option value="${c.id}" ${c.is_default ? 'selected' : ''}>${c.name} (${c.environment})</option>`
            ).join('');

            const defaultConn = conns.find(c => c.is_default) || conns[0];
            this.currentConnectionId = defaultConn.id;
        } catch (err) {
            console.error('Email Connections Fehler:', err);
        }
    },

    async refresh() {
        if (!this.currentConnectionId) return;

        this.updateStatusUI('loading', 'Prüfe Verbindung...', 'IMAP & SMTP Server werden kontaktiert');

        try {
            const res = await fetch(`${this.API_PREFIX}/status?connection_id=${this.currentConnectionId}`);
            if (!res.ok) throw new Error("API Fehler");
            const data = await res.json();

            if (data.status === 'ok') {
                this.updateStatusUI('ok', 'Verbunden', data.message);
            } else {
                this.updateStatusUI('error', 'Verbindungsfehler', data.message);
            }
        } catch (err) {
            this.updateStatusUI('error', 'Fehler', err.message);
        }
    },

    updateStatusUI(state, text, detail) {
        const iconEl = document.getElementById('email-status-icon');
        const textEl = document.getElementById('email-status-text');
        const detailEl = document.getElementById('email-status-detail');
        const cardEl = document.getElementById('email-status-card');

        if (!iconEl || !textEl || !detailEl || !cardEl) return;

        textEl.textContent = text;
        detailEl.textContent = detail;

        cardEl.className = 'status-card'; // Zurücksetzen der Klassen

        if (state === 'ok') {
            iconEl.innerHTML = '<svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="var(--accent-green)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><polyline points="9 12 11 14 15 10"></polyline></svg>';
        } else if (state === 'error') {
            iconEl.innerHTML = '<svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="var(--accent-red)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>';
            cardEl.classList.add('failing');
        } else if (state === 'warning') {
            iconEl.innerHTML = '<svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="var(--accent-yellow)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>';
            cardEl.classList.add('failing');
        } else {
            iconEl.innerHTML = '<svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="var(--text-muted)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>';
        }
    },

    destroy() {
        // cleanup if needed
    }
};

// Initialisieren, wenn die Tab im DOM ist
setTimeout(() => {
    if (document.getElementById('email-tab-content')) {
        EmailTab.init();
    }
}, 100);
