/**
 * Ninko Frontend Script für das Home Assistant Modul
 */
const HomeAssistantTab = {
    API_PREFIX: '/api/homeassistant',
    currentConnectionId: '',

    async init() {
        console.log("Home Assistant Modul JS initialisiert.");
        const refreshBtn = document.getElementById("ha-refresh-btn");
        const fetchLightsBtn = document.getElementById("ha-fetch-lights-btn");
        const select = document.getElementById('ha-connection-select');

        if (refreshBtn) refreshBtn.addEventListener("click", () => this.fetchStatus());
        if (fetchLightsBtn) fetchLightsBtn.addEventListener("click", () => this.triggerAction("fetch_lights"));

        if (select) {
            select.addEventListener('change', (e) => {
                this.currentConnectionId = e.target.value;
                this.fetchStatus();
            });
        }

        await this.loadConnections();
        if (this.currentConnectionId) {
            this.fetchStatus();
        }
    },

    showNotification(msg, type = "info") {
        if (window.app && window.app.showNotification) {
            window.app.showNotification(msg, type);
        } else {
            console.log(`[${type}] ${msg}`);
        }
    },

    async loadConnections() {
        try {
            const res = await fetch('/api/connections/homeassistant');
            const data = await res.json();
            const conns = data.connections || [];
            const select = document.getElementById('ha-connection-select');

            if (!select) return;

            if (conns.length === 0) {
                select.innerHTML = '<option value="">Keine HA Verbindungen</option>';
                this.currentConnectionId = '';
                return;
            }

            select.innerHTML = conns.map(c =>
                `<option value="${c.id}" ${c.is_default ? 'selected' : ''}>${c.name} (${c.environment})</option>`
            ).join('');

            const defaultConn = conns.find(c => c.is_default) || conns[0];
            this.currentConnectionId = defaultConn ? defaultConn.id : '';
            if (this.currentConnectionId && select) {
                select.value = this.currentConnectionId;
            }
        } catch (err) {
            console.error('HA Connections Fehler:', err);
        }
    },

    async fetchStatus() {
        const statusAlert = document.getElementById("ha-status-alert");
        const contentArea = document.getElementById("ha-content-area");
        const refreshBtn = document.getElementById("ha-refresh-btn");

        if (!this.currentConnectionId) {
            if (statusAlert) {
                statusAlert.style.display = "block";
                statusAlert.style.borderColor = 'var(--accent-yellow)';
                statusAlert.innerHTML = '<span class="sf sf-warn">Bitte erst eine Home Assistant Verbindung in den Einstellungen konfigurieren.</span>';
            }
            return;
        }

        try {
            if (refreshBtn) refreshBtn.disabled = true;
            if (statusAlert) {
                statusAlert.style.display = "block";
                statusAlert.style.borderColor = 'var(--accent-blue)';
                statusAlert.innerHTML = '<span class="sf sf-loading">Lade Status…</span>';
            }

            const res = await fetch(`${this.API_PREFIX}/status?connection_id=${this.currentConnectionId}`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);

            const data = await res.json();

            if (statusAlert) {
                statusAlert.style.borderColor = 'var(--accent-green)';
                statusAlert.innerHTML = `<span class="sf sf-ok">Verbunden mit <strong>${data.location_name || 'Home Assistant'}</strong> (v${data.version || '?'}) unter <a href="${data.url}" target="_blank" style="color: var(--accent-blue);">${data.url}</a></span>`;
            }

            if (contentArea) {
                contentArea.innerHTML = `<p style="color: var(--text-muted); font-size: 0.9rem;">Home Assistant erfolgreich erreicht. Der Ninko AI Agent kann nun Smart Home Entitäten abfragen und steuern.</p>`;
            }
        } catch (err) {
            console.error(err);
            if (statusAlert) {
                statusAlert.style.borderColor = 'var(--accent-red)';
                statusAlert.innerHTML = `<span class="sf sf-error">Fehler beim Abrufen der Daten: ${err.message}</span>`;
            }
        } finally {
            if (refreshBtn) refreshBtn.disabled = false;
        }
    },

    async triggerAction(actionType) {
        const fetchLightsBtn = document.getElementById("ha-fetch-lights-btn");
        const contentArea = document.getElementById("ha-content-area");

        try {
            if (fetchLightsBtn) fetchLightsBtn.disabled = true;

            const res = await fetch(`${this.API_PREFIX}/action`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ action_type: actionType, connection_id: this.currentConnectionId })
            });

            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();

            if (data.lights && contentArea) {
                let html = `<h3>Gefundene Lichter (${data.lights.length} Beispiel${data.lights.length === 1 ? '' : 'e'} angezeigt)</h3>`;
                html += `<div style="background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); border-radius: 8px; padding: 1rem; margin-top: 1rem;">`;
                html += `<ul style="list-style: none; padding: 0; margin: 0;">`;

                if (data.lights.length === 0) {
                    html += `<li>Keine Lichter gefunden.</li>`;
                } else {
                    data.lights.forEach(l => {
                        const name = l.attributes.friendly_name || l.entity_id;
                        const state = l.state === "on" ? '<span style="color:var(--success, #10b981)">An</span>' : '<span style="color:var(--text-secondary, #9ca3af)">Aus</span>';
                        html += `<li style="padding: 0.5rem 0; border-bottom: 1px solid rgba(255,255,255,0.05); display: flex; justify-content: space-between;">
                            <span>${name} <small style="color: var(--text-secondary); margin-left:8px;">(${l.entity_id})</small></span>
                            <span>${state}</span>
                        </li>`;
                    });
                }
                html += `</ul></div>`;
                contentArea.innerHTML = html;
                this.showNotification(data.message, "success");
            } else {
                this.showNotification(data.message, "success");
            }
        } catch (err) {
            this.showNotification(`Aktion fehlgeschlagen: ${err.message}`, "error");
        } finally {
            if (fetchLightsBtn) fetchLightsBtn.disabled = false;
        }
    }
};

HomeAssistantTab.init();
