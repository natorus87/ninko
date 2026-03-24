(async function initWebSearchTab() {

    const WebSearchTab = {
        async init() {
            await this.refresh();
        },

        async refresh() {
            try {
                const res = await fetch('/api/web-search/status');
                const data = await res.json();
                this.render(data);
            } catch (e) {
                this.renderError(String(e));
            }
        },

        render(data) {
            const connCard = document.getElementById('websearch-conn-card');
            const connIcon = document.getElementById('websearch-conn-icon');
            const connLabel = document.getElementById('websearch-conn-label');

            if (data.connected) {
                connCard.className = 'status-card running';
                connIcon.innerHTML = '<svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="var(--accent-green)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><polyline points="9 12 11 14 15 10"></polyline></svg>';
                connLabel.textContent = 'Verbunden';
            } else {
                connCard.className = 'status-card failing';
                connIcon.innerHTML = '<svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="var(--accent-red)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>';
                connLabel.textContent = data.error || 'Fehler';
            }

            document.getElementById('websearch-url').textContent = data.searxng_url || '—';

            const engines = data.engines || [];
            const okCount = engines.filter(e => e.status === 'ok').length;
            const errCount = engines.filter(e => e.status === 'error').length;

            document.getElementById('websearch-engines-ok').textContent = okCount;
            document.getElementById('websearch-engines-err').textContent = errCount;

            const tbody = document.getElementById('websearch-engine-tbody');
            if (!engines.length) {
                tbody.innerHTML = '<tr><td colspan="3" style="text-align:center;color:var(--text-muted);">Keine Engine-Daten verfügbar</td></tr>';
                return;
            }

            // Sortieren: aktive zuerst
            const sorted = [...engines].sort((a, b) => {
                if (a.status === b.status) return a.name.localeCompare(b.name);
                return a.status === 'ok' ? -1 : 1;
            });

            tbody.innerHTML = sorted.map(e => {
                const badge = e.status === 'ok'
                    ? '<span class="status-badge status-ok">aktiv</span>'
                    : '<span class="status-badge status-error">blockiert</span>';
                const reason = e.reason
                    ? `<span style="color:var(--text-muted);font-size:0.82rem;">${e.reason}</span>`
                    : '';
                return `<tr>
                    <td><strong>${e.name}</strong></td>
                    <td>${badge}</td>
                    <td>${reason}</td>
                </tr>`;
            }).join('');
        },

        renderError(msg) {
            const connCard = document.getElementById('websearch-conn-card');
            if (connCard) {
                connCard.className = 'status-card failing';
                document.getElementById('websearch-conn-icon').innerHTML = '<svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="var(--accent-red)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>';
                document.getElementById('websearch-conn-label').textContent = 'Fehler';
            }
            const tbody = document.getElementById('websearch-engine-tbody');
            if (tbody) tbody.innerHTML = `<tr><td colspan="3" style="color:var(--error-color)">${msg}</td></tr>`;
        },
    };

    window.WebSearchTab = WebSearchTab;

    // Init sobald Tab aktiv wird
    const tabEl = document.getElementById('tab-web_search');
    if (tabEl && tabEl.classList.contains('active')) {
        WebSearchTab.init();
    }

    // Observer: Tab wird eingeblendet
    const observer = new MutationObserver(() => {
        if (tabEl && tabEl.classList.contains('active')) {
            WebSearchTab.init();
            observer.disconnect();
        }
    });
    if (tabEl) observer.observe(tabEl, { attributes: true, attributeFilter: ['class'] });

})();
